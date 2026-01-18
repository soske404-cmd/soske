"""
Utility module for the Python Base Checker Framework.
Contains helper functions for common operations.
"""

import aiohttp
import asyncio
import random
import re
import json
import base64
import hashlib
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass
from datetime import datetime


# ==================== BIN Database ====================

@dataclass
class BinInfo:
    """Information about a card BIN (Bank Identification Number)"""
    bin: str
    brand: str = "Unknown"
    card_type: str = "Unknown"  # Credit/Debit
    level: str = "Unknown"  # Classic, Gold, Platinum, etc.
    bank: str = "Unknown"
    country: str = "Unknown"
    country_code: str = "XX"
    
    def __str__(self) -> str:
        return f"{self.brand} {self.card_type} {self.level} - {self.bank} ({self.country})"


async def lookup_bin(bin_number: str, session: aiohttp.ClientSession = None) -> BinInfo:
    """
    Look up BIN information from binlist.net API.
    
    Args:
        bin_number: First 6-8 digits of the card
        session: Optional aiohttp session
    
    Returns:
        BinInfo object with card details
    """
    bin_number = bin_number[:8]
    close_session = False
    
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        async with session.get(f"https://lookup.binlist.net/{bin_number}") as resp:
            if resp.status == 200:
                data = await resp.json()
                return BinInfo(
                    bin=bin_number,
                    brand=data.get("scheme", "Unknown").title(),
                    card_type=data.get("type", "Unknown").title(),
                    level=data.get("brand", "Unknown"),
                    bank=data.get("bank", {}).get("name", "Unknown"),
                    country=data.get("country", {}).get("name", "Unknown"),
                    country_code=data.get("country", {}).get("alpha2", "XX")
                )
    except Exception:
        pass
    finally:
        if close_session:
            await session.close()
    
    return BinInfo(bin=bin_number)


# ==================== Card Validation ====================

def luhn_check(card_number: str) -> bool:
    """
    Validate card number using Luhn algorithm.
    
    Args:
        card_number: Credit card number (digits only)
    
    Returns:
        True if valid, False otherwise
    """
    digits = [int(d) for d in card_number if d.isdigit()]
    if len(digits) < 13:
        return False
    
    # Reverse digits
    digits = digits[::-1]
    
    # Double every second digit
    for i in range(1, len(digits), 2):
        digits[i] *= 2
        if digits[i] > 9:
            digits[i] -= 9
    
    return sum(digits) % 10 == 0


def identify_card_brand(card_number: str) -> str:
    """
    Identify the card brand based on the card number.
    
    Args:
        card_number: Credit card number
    
    Returns:
        Card brand name
    """
    number = re.sub(r'\D', '', card_number)
    
    patterns = [
        (r'^4[0-9]{12}(?:[0-9]{3})?$', 'Visa'),
        (r'^5[1-5][0-9]{14}$', 'Mastercard'),
        (r'^2(?:2[2-9][1-9]|2[3-9]|[3-6]|7[0-1]|720)[0-9]{12}$', 'Mastercard'),
        (r'^3[47][0-9]{13}$', 'American Express'),
        (r'^3(?:0[0-5]|[68][0-9])[0-9]{11}$', 'Diners Club'),
        (r'^6(?:011|5[0-9]{2})[0-9]{12}$', 'Discover'),
        (r'^(?:2131|1800|35\d{3})\d{11}$', 'JCB'),
        (r'^62[0-9]{14,17}$', 'UnionPay'),
    ]
    
    for pattern, brand in patterns:
        if re.match(pattern, number):
            return brand
    
    return 'Unknown'


def validate_expiry(month: str, year: str) -> bool:
    """
    Check if the card expiry date is valid and not expired.
    
    Args:
        month: Expiry month (1-12 or 01-12)
        year: Expiry year (2 or 4 digits)
    
    Returns:
        True if valid and not expired
    """
    try:
        month_int = int(month)
        year_int = int(year)
        
        if year_int < 100:
            year_int += 2000
        
        if month_int < 1 or month_int > 12:
            return False
        
        now = datetime.now()
        if year_int < now.year:
            return False
        if year_int == now.year and month_int < now.month:
            return False
        
        return True
    except ValueError:
        return False


def validate_cvv(cvv: str, card_number: str = None) -> bool:
    """
    Validate CVV length based on card type.
    
    Args:
        cvv: CVV/CVC code
        card_number: Optional card number to determine expected CVV length
    
    Returns:
        True if valid CVV format
    """
    if not cvv.isdigit():
        return False
    
    if card_number:
        brand = identify_card_brand(card_number)
        if brand == 'American Express':
            return len(cvv) == 4
    
    return len(cvv) in [3, 4]


def validate_card(cc: str, month: str, year: str, cvv: str) -> Tuple[bool, str]:
    """
    Comprehensive card validation.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check Luhn
    if not luhn_check(cc):
        return False, "Invalid card number (Luhn check failed)"
    
    # Check expiry
    if not validate_expiry(month, year):
        return False, "Card is expired or invalid expiry date"
    
    # Check CVV
    if not validate_cvv(cvv, cc):
        return False, "Invalid CVV format"
    
    return True, "Valid"


# ==================== Proxy Utils ====================

@dataclass 
class Proxy:
    """Proxy configuration"""
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: str = "http"
    
    @classmethod
    def from_string(cls, proxy_string: str) -> "Proxy":
        """
        Parse proxy string in various formats:
        - host:port
        - host:port:user:pass
        - user:pass@host:port
        - protocol://user:pass@host:port
        """
        # Remove protocol prefix if present
        if "://" in proxy_string:
            protocol, proxy_string = proxy_string.split("://", 1)
        else:
            protocol = "http"
        
        # Handle user:pass@host:port format
        if "@" in proxy_string:
            auth, hostport = proxy_string.rsplit("@", 1)
            username, password = auth.split(":", 1)
            host, port = hostport.split(":")
        # Handle host:port:user:pass format
        elif proxy_string.count(":") == 3:
            host, port, username, password = proxy_string.split(":")
        # Handle host:port format
        else:
            host, port = proxy_string.split(":")
            username = password = None
        
        return cls(
            host=host,
            port=int(port),
            username=username,
            password=password,
            protocol=protocol
        )
    
    def to_url(self) -> str:
        """Convert to URL format for aiohttp"""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"
    
    def __str__(self) -> str:
        return self.to_url()


def load_proxies(filepath: str) -> List[Proxy]:
    """Load proxies from a file (one per line)"""
    proxies = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    proxies.append(Proxy.from_string(line))
                except:
                    continue
    return proxies


class ProxyRotator:
    """Rotate through a list of proxies"""
    
    def __init__(self, proxies: List[Proxy], mode: str = "round_robin"):
        """
        Args:
            proxies: List of Proxy objects
            mode: "round_robin" or "random"
        """
        self.proxies = proxies
        self.mode = mode
        self.current_index = 0
        self.failed_proxies: set = set()
    
    def get_next(self) -> Optional[Proxy]:
        """Get the next proxy"""
        available = [p for p in self.proxies if p.to_url() not in self.failed_proxies]
        if not available:
            return None
        
        if self.mode == "random":
            return random.choice(available)
        
        # Round robin
        proxy = available[self.current_index % len(available)]
        self.current_index += 1
        return proxy
    
    def mark_failed(self, proxy: Proxy):
        """Mark a proxy as failed"""
        self.failed_proxies.add(proxy.to_url())
    
    def reset_failed(self):
        """Reset failed proxy list"""
        self.failed_proxies.clear()


# ==================== Token/Session Utils ====================

def generate_device_fingerprint() -> str:
    """Generate a random device fingerprint"""
    data = {
        "screen": f"{random.randint(1920, 2560)}x{random.randint(1080, 1440)}",
        "timezone": random.choice([-8, -7, -6, -5, -4, 0, 1, 2]),
        "plugins": random.randint(0, 10),
        "language": random.choice(["en-US", "en-GB", "en"]),
        "platform": random.choice(["Win32", "MacIntel", "Linux x86_64"])
    }
    return base64.b64encode(json.dumps(data).encode()).decode()


def generate_session_id(length: int = 32) -> str:
    """Generate a random session ID"""
    return hashlib.sha256(str(random.random()).encode()).hexdigest()[:length]


def generate_uuid() -> str:
    """Generate a UUID-like string"""
    import uuid
    return str(uuid.uuid4())


# ==================== Response Parsing ====================

class ResponseParser:
    """Helper class for parsing various response formats"""
    
    @staticmethod
    def extract_form_fields(html: str) -> Dict[str, str]:
        """Extract all form input fields from HTML"""
        fields = {}
        
        # Hidden inputs
        pattern = r'<input[^>]+type=["\']hidden["\'][^>]*>'
        for match in re.finditer(pattern, html, re.IGNORECASE):
            input_tag = match.group()
            name = re.search(r'name=["\']([^"\']+)["\']', input_tag)
            value = re.search(r'value=["\']([^"\']*)["\']', input_tag)
            if name:
                fields[name.group(1)] = value.group(1) if value else ""
        
        return fields
    
    @staticmethod
    def extract_csrf_token(html: str) -> Optional[str]:
        """Extract CSRF token from HTML"""
        patterns = [
            r'csrf[_-]?token["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']',
            r'<input[^>]+name=["\']_token["\'][^>]+value=["\']([^"\']+)["\']',
            r'<input[^>]+name=["\']authenticity_token["\'][^>]+value=["\']([^"\']+)["\']',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    @staticmethod
    def extract_json_from_script(html: str, variable_name: str) -> Optional[Dict]:
        """Extract JSON data from JavaScript variable in HTML"""
        patterns = [
            rf'var\s+{variable_name}\s*=\s*(\{{[^;]+\}});',
            rf'{variable_name}\s*=\s*(\{{[^;]+\}});',
            rf'window\.{variable_name}\s*=\s*(\{{[^;]+\}});',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
        
        return None
    
    @staticmethod
    def decode_html_entities(text: str) -> str:
        """Decode HTML entities in text"""
        import html
        return html.unescape(text)


# ==================== Stripe Utils ====================

async def get_stripe_token(card_number: str, month: str, year: str, cvv: str,
                           publishable_key: str, session: aiohttp.ClientSession = None) -> Optional[str]:
    """
    Tokenize card using Stripe API.
    
    Args:
        card_number, month, year, cvv: Card details
        publishable_key: Stripe publishable key (pk_live_... or pk_test_...)
        session: Optional aiohttp session
    
    Returns:
        Stripe token (tok_...) or None on failure
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        # Format year to 2 digits if needed
        if len(year) == 4:
            year = year[-2:]
        
        data = {
            "card[number]": card_number,
            "card[exp_month]": month,
            "card[exp_year]": year,
            "card[cvc]": cvv,
            "key": publishable_key,
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        
        async with session.post("https://api.stripe.com/v1/tokens", data=data, headers=headers) as resp:
            result = await resp.json()
            return result.get("id")
    
    except Exception:
        return None
    
    finally:
        if close_session:
            await session.close()


# ==================== Braintree Utils ====================

async def get_braintree_token(card_number: str, month: str, year: str, cvv: str,
                              authorization: str, session: aiohttp.ClientSession = None) -> Optional[str]:
    """
    Tokenize card using Braintree client API.
    
    Args:
        card_number, month, year, cvv: Card details
        authorization: Braintree client token or tokenization key
        session: Optional aiohttp session
    
    Returns:
        Braintree payment method nonce or None on failure
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {authorization}",
            "Braintree-Version": "2018-05-10",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        
        data = {
            "clientSdkMetadata": {
                "source": "client",
                "integration": "custom",
                "sessionId": generate_uuid()
            },
            "query": "mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin last4 cardholderName expirationMonth expirationYear binData { prepaid healthcare debit durbinRegulated commercial payroll issuingBank countryOfIssuance productId } } } }",
            "variables": {
                "input": {
                    "creditCard": {
                        "number": card_number,
                        "expirationMonth": month,
                        "expirationYear": year,
                        "cvv": cvv
                    }
                }
            },
            "operationName": "TokenizeCreditCard"
        }
        
        async with session.post("https://payments.braintree-api.com/graphql", 
                               json=data, headers=headers) as resp:
            result = await resp.json()
            return result.get("data", {}).get("tokenizeCreditCard", {}).get("token")
    
    except Exception:
        return None
    
    finally:
        if close_session:
            await session.close()


# ==================== Common Decline Codes ====================

DECLINE_CODES = {
    # Generic declines
    "card_declined": ("Card Declined", "DECLINED"),
    "do_not_honor": ("Do Not Honor", "CCN"),
    "insufficient_funds": ("Insufficient Funds", "CCN"),
    
    # Card errors
    "invalid_number": ("Invalid Card Number", "DEAD"),
    "invalid_expiry_month": ("Invalid Expiry Month", "DEAD"),
    "invalid_expiry_year": ("Invalid Expiry Year", "DEAD"),
    "expired_card": ("Expired Card", "DEAD"),
    "incorrect_cvc": ("Incorrect CVC", "DEAD"),
    "invalid_cvc": ("Invalid CVC", "DEAD"),
    
    # Fraud
    "fraudulent": ("Suspected Fraud", "DEAD"),
    "stolen_card": ("Stolen Card", "DEAD"),
    "lost_card": ("Lost Card", "DEAD"),
    "pickup_card": ("Pickup Card", "DEAD"),
    
    # Processing errors
    "processing_error": ("Processing Error", "ERROR"),
    "try_again_later": ("Try Again Later", "ERROR"),
    "rate_limit": ("Rate Limited", "RATE_LIMITED"),
    
    # Success
    "approved": ("Approved", "LIVE"),
    "succeeded": ("Succeeded", "LIVE"),
}


def parse_decline_code(code: str) -> Tuple[str, str]:
    """
    Parse a decline code and return (message, result_type).
    
    Args:
        code: The decline code from payment processor
    
    Returns:
        Tuple of (human-readable message, result type)
    """
    code_lower = code.lower().replace("-", "_").replace(" ", "_")
    return DECLINE_CODES.get(code_lower, (code, "UNKNOWN"))


# ==================== Rate Limiting ====================

class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, calls_per_second: float = 1.0):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Wait until we can make the next call"""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait_time = self.last_call + self.min_interval - now
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.last_call = asyncio.get_event_loop().time()


if __name__ == "__main__":
    # Example usage
    print("Checker Utilities Module")
    print("=" * 40)
    
    # Test Luhn
    test_cards = [
        ("4111111111111111", True),
        ("4111111111111112", False),
    ]
    
    print("\nLuhn Validation:")
    for card, expected in test_cards:
        result = luhn_check(card)
        status = "PASS" if result == expected else "FAIL"
        print(f"  {card[:6]}...{card[-4:]} -> {result} [{status}]")
    
    # Test brand detection
    print("\nBrand Detection:")
    brands = [
        ("4111111111111111", "Visa"),
        ("5500000000000004", "Mastercard"),
        ("340000000000009", "American Express"),
        ("6011000000000004", "Discover"),
    ]
    for card, expected in brands:
        detected = identify_card_brand(card)
        status = "PASS" if detected == expected else "FAIL"
        print(f"  {card[:6]}... -> {detected} [{status}]")
    
    # Test proxy parsing
    print("\nProxy Parsing:")
    proxy_strings = [
        "192.168.1.1:8080",
        "192.168.1.1:8080:user:pass",
        "user:pass@192.168.1.1:8080",
        "http://user:pass@192.168.1.1:8080",
    ]
    for ps in proxy_strings:
        proxy = Proxy.from_string(ps)
        print(f"  Input: {ps}")
        print(f"  Output: {proxy.to_url()}")
