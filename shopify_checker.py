"""
Shopify Checker - Built on BaseChecker
Example implementation showing how to extend the base checker for Shopify stores.
"""

import asyncio
import aiohttp
import time
import json
from typing import Optional, Tuple, Dict, Any
from base_checker import (
    BaseChecker, 
    Card, 
    CheckResult, 
    CardStatus,
    RandomDataGenerator,
    TextExtractor
)


class ShopifyChecker(BaseChecker):
    """
    Shopify platform checker extending BaseChecker.
    Supports multiple Shopify checkout flows.
    """
    
    # Currency to country mapping
    CURRENCY_COUNTRY_MAP = {
        "USD": "US",
        "CAD": "CA",
        "INR": "IN",
        "AED": "AE",
        "HKD": "HK",
        "GBP": "GB",
        "CHF": "CH",
        "EUR": "DE",
        "AUD": "AU",
        "JPY": "JP",
    }
    
    def __init__(self, store_url: str, **kwargs):
        """
        Initialize Shopify checker.
        
        Args:
            store_url: Shopify store URL (e.g., https://example.myshopify.com)
            **kwargs: Additional arguments passed to BaseChecker
        """
        super().__init__(**kwargs)
        self.store_url = store_url.rstrip('/')
        self.domain = self.store_url.replace('https://', '').replace('http://', '').rstrip('/')
        
        # Store data populated during setup
        self.access_token: Optional[str] = None
        self.product_id: Optional[str] = None
        self.product_price: Optional[float] = None
        self.checkout_url: Optional[str] = None
        self.session_token: Optional[str] = None
    
    async def fetch_product(self) -> Tuple[bool, str]:
        """Fetch cheapest available product from store"""
        try:
            url = f"{self.store_url}/products.json"
            async with self.session.get(url, headers=self.get_headers()) as resp:
                if resp.status != 200:
                    return False, "Cannot access products endpoint"
                
                data = await resp.json()
                products = data.get('products', [])
                
                if not products:
                    return False, "No products found"
                
                min_price = float('inf')
                best_product = None
                
                for product in products:
                    for variant in product.get('variants', []):
                        if not variant.get('available', False):
                            continue
                        
                        try:
                            price = float(str(variant.get('price', '0')).replace(',', ''))
                            if 0 < price < min_price:
                                min_price = price
                                best_product = {
                                    'id': str(variant['id']),
                                    'price': price,
                                    'handle': product.get('handle', '')
                                }
                        except (ValueError, TypeError):
                            continue
                
                if best_product:
                    self.product_id = best_product['id']
                    self.product_price = best_product['price']
                    return True, f"Found product: ${best_product['price']:.2f}"
                
                return False, "No available products found"
                
        except Exception as e:
            return False, f"Error fetching products: {str(e)}"
    
    async def get_store_token(self) -> Tuple[bool, str]:
        """Get Shopify storefront access token"""
        try:
            async with self.session.get(self.store_url, headers=self.get_headers()) as resp:
                text = await resp.text()
                
                # Try different extraction methods
                token = self.extractor.between(text, '"accessToken":"', '"')
                if not token:
                    token = self.extractor.between(text, 'accessToken":"', '"')
                if not token:
                    token = self.extractor.regex(text, r'accessToken["\']?\s*:\s*["\']([a-f0-9]+)["\']')
                
                if token:
                    self.access_token = token
                    return True, "Token obtained"
                
                return False, "Could not find access token"
                
        except Exception as e:
            return False, f"Error getting token: {str(e)}"
    
    async def create_cart(self) -> Tuple[bool, str]:
        """Create shopping cart using GraphQL API"""
        if not self.access_token or not self.product_id:
            return False, "Missing token or product"
        
        headers = {
            **self.get_headers(),
            'content-type': 'application/json',
            'x-shopify-storefront-access-token': self.access_token,
            'x-sdk-variant': 'portable-wallets',
            'x-start-wallet-checkout': 'true',
        }
        
        query = '''
        mutation cartCreate($input: CartInput!, $country: CountryCode, $language: LanguageCode) 
        @inContext(country: $country, language: $language) {
            result: cartCreate(input: $input) {
                cart {
                    id
                    checkoutUrl
                }
                userErrors {
                    message
                    field
                    code
                }
            }
        }
        '''
        
        payload = {
            'query': query,
            'variables': {
                'input': {
                    'lines': [{
                        'merchandiseId': f'gid://shopify/ProductVariant/{self.product_id}',
                        'quantity': 1,
                    }],
                },
                'country': 'US',
                'language': 'EN',
            }
        }
        
        try:
            url = f"{self.store_url}/api/unstable/graphql.json"
            async with self.session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json()
                
                cart_data = data.get('data', {}).get('result', {}).get('cart', {})
                checkout_url = cart_data.get('checkoutUrl')
                
                if checkout_url:
                    self.checkout_url = checkout_url
                    return True, "Cart created"
                
                errors = data.get('data', {}).get('result', {}).get('userErrors', [])
                if errors:
                    return False, errors[0].get('message', 'Cart creation failed')
                
                return False, "Could not create cart"
                
        except Exception as e:
            return False, f"Cart error: {str(e)}"
    
    async def init_checkout(self) -> Tuple[bool, str]:
        """Initialize checkout session"""
        if not self.checkout_url:
            return False, "No checkout URL"
        
        try:
            headers = self.get_headers({
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
            })
            
            params = {'skip_shop_pay': 'true'}
            
            async with self.session.get(
                self.checkout_url, 
                headers=headers, 
                params=params,
                allow_redirects=True
            ) as resp:
                text = await resp.text()
                
                # Extract session token
                self.session_token = self.extractor.between(
                    text, 
                    'serialized-session-token" content="&quot;', 
                    '&quot'
                )
                
                if not self.session_token:
                    return False, "Could not get session token"
                
                return True, "Checkout initialized"
                
        except Exception as e:
            return False, f"Checkout error: {str(e)}"
    
    async def submit_payment(self, card: Card) -> CheckResult:
        """Submit payment with card"""
        start = time.time()
        
        # Generate buyer info
        first_name, last_name = self.data_gen.full_name()
        email = self.data_gen.email(first_name, last_name)
        address = self.data_gen.address('US')
        
        # Build payment data
        # Note: This is a simplified version - actual implementation depends on gateway
        payment_data = {
            'credit_card': {
                'number': card.number,
                'month': int(card.month),
                'year': int(card.year),
                'verification_value': card.cvv,
                'name': f"{first_name} {last_name}",
            },
            'payment_session_scope': self.store_url,
        }
        
        try:
            # This would be the actual payment submission
            # Implementation varies based on the specific gateway
            elapsed = time.time() - start
            
            return CheckResult(
                status=CardStatus.UNKNOWN,
                message="Payment submission logic depends on specific gateway",
                card=card,
                gateway="Shopify",
                response_time=elapsed
            )
            
        except Exception as e:
            return CheckResult(
                status=CardStatus.ERROR,
                message=str(e),
                card=card,
                response_time=time.time() - start
            )
    
    def parse_shopify_response(self, response_text: str) -> Tuple[CardStatus, str]:
        """Parse Shopify-specific response patterns"""
        text = response_text.lower()
        
        # Shopify-specific patterns
        patterns = {
            CardStatus.LIVE: [
                'thank you', 'order confirmed', 'payment successful',
                'order placed', 'confirmation'
            ],
            CardStatus.DECLINED: [
                'declined', 'card was declined', 'transaction failed',
                'payment could not be processed', 'do_not_honor',
                'generic_decline', 'card_declined'
            ],
            CardStatus.CVV: [
                'cvv', 'cvc', 'security code', 'incorrect_cvc',
                'invalid_cvc', 'security_code_invalid'
            ],
            CardStatus.EXPIRED: [
                'expired', 'card has expired', 'invalid_expiry',
                'expiration date', 'exp_month', 'exp_year'
            ],
            CardStatus.INSUFFICIENT: [
                'insufficient funds', 'insufficient_funds',
                'not enough funds'
            ],
            CardStatus.CCN: [
                'card number', 'invalid card', 'incorrect_number',
                'invalid_number'
            ],
            CardStatus.RATE_LIMITED: [
                'rate limit', 'too many attempts', 'try again later',
                'temporarily blocked'
            ]
        }
        
        for status, keywords in patterns.items():
            for keyword in keywords:
                if keyword in text:
                    return status, keyword
        
        return CardStatus.UNKNOWN, "No matching pattern"
    
    async def check(self, card: Card) -> CheckResult:
        """
        Full card check flow for Shopify.
        
        Args:
            card: Card object to check
            
        Returns:
            CheckResult with status and message
        """
        start = time.time()
        
        # Validate card first
        if not card.is_valid_luhn():
            return CheckResult(
                status=CardStatus.DEAD,
                message="Invalid card number (Luhn check failed)",
                card=card,
                response_time=time.time() - start
            )
        
        # Step 1: Get access token
        success, msg = await self.get_store_token()
        if not success:
            return CheckResult(
                status=CardStatus.ERROR,
                message=f"Token Error: {msg}",
                card=card,
                response_time=time.time() - start
            )
        
        # Step 2: Fetch product
        success, msg = await self.fetch_product()
        if not success:
            return CheckResult(
                status=CardStatus.ERROR,
                message=f"Product Error: {msg}",
                card=card,
                response_time=time.time() - start
            )
        
        # Step 3: Create cart
        success, msg = await self.create_cart()
        if not success:
            return CheckResult(
                status=CardStatus.ERROR,
                message=f"Cart Error: {msg}",
                card=card,
                response_time=time.time() - start
            )
        
        # Step 4: Initialize checkout
        success, msg = await self.init_checkout()
        if not success:
            return CheckResult(
                status=CardStatus.ERROR,
                message=f"Checkout Error: {msg}",
                card=card,
                response_time=time.time() - start
            )
        
        # Step 5: Submit payment
        result = await self.submit_payment(card)
        result.extra_data['product_price'] = self.product_price
        result.extra_data['checkout_url'] = self.checkout_url
        
        return result


class ShopifyBraintreeChecker(ShopifyChecker):
    """
    Shopify checker for stores using Braintree gateway.
    Extends ShopifyChecker with Braintree-specific methods.
    """
    
    async def get_braintree_token(self) -> Optional[str]:
        """Get Braintree client token"""
        # Implementation for Braintree token retrieval
        pass
    
    async def tokenize_braintree(self, card: Card) -> Optional[str]:
        """Tokenize card with Braintree"""
        # Implementation for Braintree card tokenization
        pass


class ShopifyStripeChecker(ShopifyChecker):
    """
    Shopify checker for stores using Stripe gateway.
    Extends ShopifyChecker with Stripe-specific methods.
    """
    
    async def get_stripe_token(self, card: Card) -> Optional[str]:
        """Get Stripe payment method token"""
        # Implementation for Stripe tokenization
        pass


# ==================== UTILITY FUNCTIONS ====================

async def check_shopify_site(url: str) -> Dict[str, Any]:
    """
    Quick check if a site is a valid Shopify store.
    
    Args:
        url: Store URL to check
        
    Returns:
        Dict with store information
    """
    result = {
        'is_shopify': False,
        'has_products': False,
        'product_count': 0,
        'currency': None,
        'error': None
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # Check products.json
            products_url = f"{url.rstrip('/')}/products.json"
            async with session.get(products_url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    products = data.get('products', [])
                    result['is_shopify'] = True
                    result['has_products'] = len(products) > 0
                    result['product_count'] = len(products)
                    
                    # Try to get currency
                    if products:
                        variants = products[0].get('variants', [])
                        if variants:
                            result['currency'] = variants[0].get('currency', 'USD')
                            
    except Exception as e:
        result['error'] = str(e)
    
    return result


# ==================== MAIN ====================

async def main():
    """Example usage"""
    print("Shopify Checker - Built on BaseChecker")
    print("=" * 50)
    
    # Example: Check if a site is Shopify
    test_url = "https://example-store.myshopify.com"  # Replace with actual URL
    
    print(f"\nChecking store: {test_url}")
    # site_info = await check_shopify_site(test_url)
    # print(f"Store info: {site_info}")
    
    # Example: Create checker and check card
    # async with ShopifyChecker(test_url) as checker:
    #     result = await checker.check_str("4111111111111111|12|2025|123")
    #     print(checker.format_result(result))
    
    print("\nTo use:")
    print("  1. Create ShopifyChecker with store URL")
    print("  2. Call check() with Card object or check_str() with card string")
    print("  3. Handle CheckResult")


if __name__ == "__main__":
    asyncio.run(main())
