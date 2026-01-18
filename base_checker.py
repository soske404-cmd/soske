"""
Python Base Checker Framework
A modular, extensible framework for building payment checkers.
"""

import aiohttp
import asyncio
import random
import string
import time
import re
import json
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse


class CheckResult(Enum):
    """Enumeration of possible check results"""
    LIVE = "LIVE"
    DEAD = "DEAD"
    DECLINED = "DECLINED"
    CCN = "CCN"  # Card Check Number (CVV verification)
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    SITE_ERROR = "SITE_ERROR"


@dataclass
class CardInfo:
    """Dataclass to hold card information"""
    cc: str
    month: str
    year: str
    cvv: str
    
    @classmethod
    def from_string(cls, card_string: str, delimiter: str = "|") -> "CardInfo":
        """Parse card string like '4111111111111111|12|2025|123'"""
        parts = [p.strip() for p in card_string.split(delimiter)]
        if len(parts) != 4:
            raise ValueError(f"Invalid card format. Expected: cc{delimiter}month{delimiter}year{delimiter}cvv")
        return cls(cc=parts[0], month=parts[1], year=parts[2], cvv=parts[3])
    
    @property
    def bin(self) -> str:
        """Get first 6 digits (BIN)"""
        return self.cc[:6]
    
    @property
    def last4(self) -> str:
        """Get last 4 digits"""
        return self.cc[-4:]
    
    @property
    def formatted_year(self) -> str:
        """Get year in 2-digit format"""
        return self.year[-2:] if len(self.year) == 4 else self.year
    
    @property
    def full_year(self) -> str:
        """Get year in 4-digit format"""
        if len(self.year) == 2:
            return f"20{self.year}"
        return self.year
    
    def __str__(self) -> str:
        return f"{self.cc}|{self.month}|{self.year}|{self.cvv}"


@dataclass
class CheckResponse:
    """Dataclass to hold check response"""
    result: CheckResult
    message: str
    gateway: str = "Unknown"
    extra_data: Dict[str, Any] = field(default_factory=dict)
    time_taken: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "result": self.result.value,
            "message": self.message,
            "gateway": self.gateway,
            "extra_data": self.extra_data,
            "time_taken": f"{self.time_taken:.2f}s"
        }
    
    def __str__(self) -> str:
        return f"[{self.result.value}] {self.message} | Gateway: {self.gateway} | Time: {self.time_taken:.2f}s"


@dataclass
class Identity:
    """Dataclass to hold buyer identity information"""
    first_name: str
    last_name: str
    email: str
    phone: str
    address1: str
    address2: str
    city: str
    state: str
    postal_code: str
    country_code: str
    
    @classmethod
    def generate_random(cls, country: str = "US") -> "Identity":
        """Generate random identity based on country"""
        first_names = ['John', 'James', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph', 'Thomas', 'Charles']
        last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
        
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        
        # Country-specific data
        country_data = {
            "US": {
                "cities": [("New York", "NY", "10001"), ("Los Angeles", "CA", "90001"), ("Chicago", "IL", "60601"), ("Houston", "TX", "77001"), ("Phoenix", "AZ", "85001")],
                "streets": ["123 Main St", "456 Oak Ave", "789 Pine Rd", "321 Elm St", "654 Maple Dr"],
                "phone_prefix": "212"
            },
            "CA": {
                "cities": [("Toronto", "ON", "M5J2J3"), ("Vancouver", "BC", "V5K0A1"), ("Montreal", "QC", "H3B1A7")],
                "streets": ["88 Queen St", "100 King St", "50 Yonge St"],
                "phone_prefix": "416"
            },
            "GB": {
                "cities": [("London", "LND", "NW1 6XE"), ("Manchester", "MAN", "M1 1AD"), ("Birmingham", "BIR", "B1 1AA")],
                "streets": ["221B Baker Street", "10 Downing St", "1 Abbey Road"],
                "phone_prefix": "207"
            }
        }
        
        data = country_data.get(country, country_data["US"])
        city_info = random.choice(data["cities"])
        
        return cls(
            first_name=first_name,
            last_name=last_name,
            email=f"{first_name.lower()}.{last_name.lower()}{random.randint(100, 999)}@gmail.com",
            phone=f"{data['phone_prefix']}{random.randint(1000000, 9999999)}",
            address1=random.choice(data["streets"]),
            address2="",
            city=city_info[0],
            state=city_info[1],
            postal_code=city_info[2],
            country_code=country
        )


class BaseChecker(ABC):
    """
    Abstract base class for payment checkers.
    
    Extend this class to create checkers for different payment platforms.
    
    Example:
        class MyGatewayChecker(BaseChecker):
            def __init__(self):
                super().__init__("MyGateway")
            
            async def check(self, card: CardInfo, **kwargs) -> CheckResponse:
                # Implement your checking logic
                pass
    """
    
    def __init__(self, name: str, timeout: int = 30):
        """
        Initialize the base checker.
        
        Args:
            name: Name of the checker (e.g., "Shopify", "Stripe", "Braintree")
            timeout: Default timeout for HTTP requests in seconds
        """
        self.name = name
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None
        self.proxy: Optional[str] = None
        self._start_time: float = 0.0
    
    # ==================== Session Management ====================
    
    async def create_session(self, proxy: Optional[str] = None) -> aiohttp.ClientSession:
        """Create and return an aiohttp session"""
        connector = aiohttp.TCPConnector(ssl=False, limit=100)
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        )
        self.proxy = proxy
        return self.session
    
    async def close_session(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def __aenter__(self):
        await self.create_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_session()
    
    # ==================== HTTP Request Methods ====================
    
    async def get(self, url: str, headers: Optional[Dict] = None, **kwargs) -> aiohttp.ClientResponse:
        """Make an async GET request"""
        if not self.session:
            await self.create_session()
        return await self.session.get(url, headers=headers, proxy=self.proxy, **kwargs)
    
    async def post(self, url: str, data: Any = None, json_data: Any = None, 
                   headers: Optional[Dict] = None, **kwargs) -> aiohttp.ClientResponse:
        """Make an async POST request"""
        if not self.session:
            await self.create_session()
        return await self.session.post(url, data=data, json=json_data, headers=headers, proxy=self.proxy, **kwargs)
    
    # ==================== Utility Methods ====================
    
    @staticmethod
    def extract_between(text: str, start: str, end: str) -> Optional[str]:
        """Extract text between two strings"""
        try:
            start_idx = text.index(start) + len(start)
            end_idx = text.index(end, start_idx)
            return text[start_idx:end_idx]
        except ValueError:
            return None
    
    @staticmethod
    def extract_all_between(text: str, start: str, end: str) -> List[str]:
        """Extract all occurrences of text between two strings"""
        results = []
        search_start = 0
        while True:
            try:
                start_idx = text.index(start, search_start) + len(start)
                end_idx = text.index(end, start_idx)
                results.append(text[start_idx:end_idx])
                search_start = end_idx
            except ValueError:
                break
        return results
    
    @staticmethod
    def extract_json(text: str, key: str) -> Optional[str]:
        """Extract value from JSON-like string by key"""
        patterns = [
            rf'"{key}"\s*:\s*"([^"]*)"',
            rf"'{key}'\s*:\s*'([^']*)'",
            rf'{key}\s*=\s*"([^"]*)"',
            rf'{key}\s*=\s*\'([^\']*)\'',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None
    
    @staticmethod
    def generate_random_string(length: int = 16, chars: str = None) -> str:
        """Generate a random string"""
        if chars is None:
            chars = string.ascii_lowercase + string.digits
        return ''.join(random.choices(chars, k=length))
    
    @staticmethod
    def get_domain(url: str) -> str:
        """Extract domain from URL"""
        parsed = urlparse(url)
        return parsed.netloc or url.split("//")[-1].split("/")[0]
    
    @staticmethod
    def clean_url(url: str) -> str:
        """Ensure URL has proper scheme"""
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return url.rstrip("/")
    
    def start_timer(self):
        """Start the timer for measuring check duration"""
        self._start_time = time.time()
    
    def get_elapsed_time(self) -> float:
        """Get elapsed time since timer started"""
        return time.time() - self._start_time
    
    # ==================== Default Headers ====================
    
    @property
    def default_headers(self) -> Dict[str, str]:
        """Default browser headers"""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }
    
    @property
    def json_headers(self) -> Dict[str, str]:
        """Headers for JSON API requests"""
        headers = self.default_headers.copy()
        headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })
        return headers
    
    # ==================== Response Helpers ====================
    
    def make_response(self, result: CheckResult, message: str, 
                      gateway: str = None, **extra_data) -> CheckResponse:
        """Create a CheckResponse object"""
        return CheckResponse(
            result=result,
            message=message,
            gateway=gateway or self.name,
            extra_data=extra_data,
            time_taken=self.get_elapsed_time()
        )
    
    def live_response(self, message: str = "Card is Live", **extra_data) -> CheckResponse:
        """Shortcut for live card response"""
        return self.make_response(CheckResult.LIVE, message, **extra_data)
    
    def dead_response(self, message: str = "Card is Dead", **extra_data) -> CheckResponse:
        """Shortcut for dead card response"""
        return self.make_response(CheckResult.DEAD, message, **extra_data)
    
    def declined_response(self, message: str = "Card Declined", **extra_data) -> CheckResponse:
        """Shortcut for declined card response"""
        return self.make_response(CheckResult.DECLINED, message, **extra_data)
    
    def ccn_response(self, message: str = "CCN Live (CVV Match)", **extra_data) -> CheckResponse:
        """Shortcut for CCN response"""
        return self.make_response(CheckResult.CCN, message, **extra_data)
    
    def error_response(self, message: str = "Error occurred", **extra_data) -> CheckResponse:
        """Shortcut for error response"""
        return self.make_response(CheckResult.ERROR, message, **extra_data)
    
    def unknown_response(self, message: str = "Unknown result", **extra_data) -> CheckResponse:
        """Shortcut for unknown response"""
        return self.make_response(CheckResult.UNKNOWN, message, **extra_data)
    
    # ==================== Response Analysis ====================
    
    def analyze_response(self, text: str, json_data: Dict = None) -> CheckResult:
        """
        Analyze response text to determine card status.
        Override this method in subclasses for custom logic.
        """
        text_lower = text.lower() if text else ""
        
        # Live indicators
        live_keywords = [
            "approved", "success", "thank you for your order",
            "order confirmed", "payment successful", "transaction complete",
            "your order has been placed"
        ]
        
        # CCN indicators (CVV verified but not fully charged)
        ccn_keywords = [
            "insufficient funds", "insufficient_funds", "not enough funds",
            "do not honor", "card declined", "call issuer"
        ]
        
        # Dead indicators
        dead_keywords = [
            "invalid card", "card number is invalid", "expired card",
            "invalid expiry", "invalid cvv", "incorrect cvc",
            "your card number is incorrect", "invalid_number"
        ]
        
        # Rate limit indicators
        rate_limit_keywords = [
            "rate limit", "too many requests", "try again later",
            "temporarily blocked"
        ]
        
        for keyword in live_keywords:
            if keyword in text_lower:
                return CheckResult.LIVE
        
        for keyword in ccn_keywords:
            if keyword in text_lower:
                return CheckResult.CCN
        
        for keyword in dead_keywords:
            if keyword in text_lower:
                return CheckResult.DEAD
        
        for keyword in rate_limit_keywords:
            if keyword in text_lower:
                return CheckResult.RATE_LIMITED
        
        return CheckResult.UNKNOWN
    
    # ==================== Abstract Methods ====================
    
    @abstractmethod
    async def check(self, card: CardInfo, **kwargs) -> CheckResponse:
        """
        Main method to check a card. Must be implemented by subclasses.
        
        Args:
            card: CardInfo object containing card details
            **kwargs: Additional arguments (e.g., site URL, product ID)
        
        Returns:
            CheckResponse object with the result
        """
        pass
    
    # ==================== Batch Processing ====================
    
    async def check_batch(self, cards: List[CardInfo], concurrency: int = 5, 
                          delay: float = 1.0, **kwargs) -> List[CheckResponse]:
        """
        Check multiple cards with concurrency control.
        
        Args:
            cards: List of CardInfo objects
            concurrency: Maximum concurrent checks
            delay: Delay between batches in seconds
            **kwargs: Additional arguments passed to check()
        
        Returns:
            List of CheckResponse objects
        """
        semaphore = asyncio.Semaphore(concurrency)
        results = []
        
        async def check_with_semaphore(card: CardInfo) -> CheckResponse:
            async with semaphore:
                result = await self.check(card, **kwargs)
                await asyncio.sleep(delay)
                return result
        
        tasks = [check_with_semaphore(card) for card in cards]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to error responses
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(self.error_response(str(result)))
            else:
                final_results.append(result)
        
        return final_results
    
    # ==================== Logging ====================
    
    def log(self, message: str, level: str = "INFO"):
        """Simple logging method"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] [{self.name}] {message}")
    
    def log_check_result(self, card: CardInfo, response: CheckResponse):
        """Log a check result"""
        result_symbol = {
            CheckResult.LIVE: "✓",
            CheckResult.CCN: "⚡",
            CheckResult.DEAD: "✗",
            CheckResult.DECLINED: "⊘",
            CheckResult.ERROR: "!",
            CheckResult.UNKNOWN: "?",
            CheckResult.RATE_LIMITED: "⏳",
            CheckResult.SITE_ERROR: "⚠"
        }.get(response.result, "?")
        
        print(f"[{result_symbol}] {card.bin}xxxxxx{card.last4} | {response.result.value} | {response.message} | {response.time_taken:.2f}s")


# ==================== Convenience Functions ====================

def parse_card(card_string: str, delimiter: str = "|") -> CardInfo:
    """Parse a card string into CardInfo object"""
    return CardInfo.from_string(card_string, delimiter)


def parse_cards_from_file(filepath: str, delimiter: str = "|") -> List[CardInfo]:
    """Parse cards from a file (one card per line)"""
    cards = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    cards.append(CardInfo.from_string(line, delimiter))
                except ValueError:
                    continue
    return cards


async def run_checker(checker: BaseChecker, cards: List[CardInfo], **kwargs) -> List[CheckResponse]:
    """
    Convenience function to run a checker on a list of cards.
    
    Example:
        async def main():
            checker = MyChecker()
            cards = parse_cards_from_file("cards.txt")
            results = await run_checker(checker, cards, url="https://example.com")
            
            for card, result in zip(cards, results):
                print(f"{card} -> {result}")
    """
    async with checker:
        return await checker.check_batch(cards, **kwargs)


if __name__ == "__main__":
    # Example usage demonstration
    print("=" * 60)
    print("Python Base Checker Framework")
    print("=" * 60)
    print("\nThis is a base framework. Create your own checker by extending BaseChecker.")
    print("\nExample:")
    print("""
    class MyGatewayChecker(BaseChecker):
        def __init__(self):
            super().__init__("MyGateway")
        
        async def check(self, card: CardInfo, **kwargs) -> CheckResponse:
            self.start_timer()
            # Your checking logic here
            return self.live_response("Card approved!")
    
    # Usage:
    async def main():
        checker = MyGatewayChecker()
        card = CardInfo.from_string("4111111111111111|12|2025|123")
        async with checker:
            result = await checker.check(card)
            print(result)
    
    asyncio.run(main())
    """)
