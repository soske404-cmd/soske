"""
Example Checker Implementations
Demonstrates how to extend the BaseChecker for different payment platforms.
"""

import asyncio
import aiohttp
import json
import re
from typing import Optional, Dict, Any

from base_checker import (
    BaseChecker, CardInfo, CheckResponse, CheckResult, 
    Identity, parse_card, run_checker
)
from checker_utils import (
    get_stripe_token, get_braintree_token, 
    validate_card, lookup_bin, ResponseParser
)


# ==================== Stripe Checker Example ====================

class StripeChecker(BaseChecker):
    """
    Example checker for Stripe payment gateway.
    
    Usage:
        checker = StripeChecker(publishable_key="pk_live_...")
        card = CardInfo.from_string("4111111111111111|12|2025|123")
        result = await checker.check(card, amount=100)
    """
    
    def __init__(self, publishable_key: str, secret_key: Optional[str] = None):
        super().__init__("Stripe")
        self.publishable_key = publishable_key
        self.secret_key = secret_key
    
    async def tokenize_card(self, card: CardInfo) -> Optional[str]:
        """Get Stripe token for the card"""
        return await get_stripe_token(
            card.cc, card.month, card.formatted_year, card.cvv,
            self.publishable_key, self.session
        )
    
    async def check(self, card: CardInfo, amount: int = 100, 
                    currency: str = "usd", **kwargs) -> CheckResponse:
        """
        Check a card using Stripe.
        
        Args:
            card: CardInfo object
            amount: Amount in cents (default 100 = $1.00)
            currency: Currency code
        """
        self.start_timer()
        
        # Validate card first
        is_valid, error_msg = validate_card(card.cc, card.month, card.year, card.cvv)
        if not is_valid:
            return self.dead_response(error_msg)
        
        try:
            # Step 1: Tokenize the card
            self.log(f"Tokenizing card {card.bin}xxxx{card.last4}")
            token = await self.tokenize_card(card)
            
            if not token:
                return self.error_response("Failed to tokenize card")
            
            self.log(f"Got token: {token[:20]}...")
            
            # Step 2: If we have secret key, try to create a charge
            if self.secret_key:
                headers = {
                    "Authorization": f"Bearer {self.secret_key}",
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                
                data = {
                    "amount": amount,
                    "currency": currency,
                    "source": token,
                    "description": "Card check"
                }
                
                async with self.session.post(
                    "https://api.stripe.com/v1/charges",
                    data=data, headers=headers
                ) as resp:
                    result = await resp.json()
                    
                    if result.get("paid"):
                        return self.live_response(
                            "Charge successful",
                            charge_id=result.get("id"),
                            amount=f"{amount/100:.2f} {currency.upper()}"
                        )
                    
                    error = result.get("error", {})
                    decline_code = error.get("decline_code", "")
                    message = error.get("message", "Unknown error")
                    
                    if decline_code in ["insufficient_funds", "do_not_honor"]:
                        return self.ccn_response(f"CCN: {message}", decline_code=decline_code)
                    elif decline_code in ["stolen_card", "lost_card", "fraudulent"]:
                        return self.dead_response(f"Dead: {message}", decline_code=decline_code)
                    else:
                        return self.declined_response(message, decline_code=decline_code)
            
            # If no secret key, just tokenization success indicates valid card format
            return self.unknown_response("Token created (no charge attempted)")
            
        except aiohttp.ClientError as e:
            return self.error_response(f"Network error: {str(e)}")
        except Exception as e:
            return self.error_response(f"Error: {str(e)}")


# ==================== Braintree Checker Example ====================

class BraintreeChecker(BaseChecker):
    """
    Example checker for Braintree payment gateway.
    
    Usage:
        checker = BraintreeChecker(authorization="sandbox_...")
        card = CardInfo.from_string("4111111111111111|12|2025|123")
        result = await checker.check(card)
    """
    
    def __init__(self, authorization: str):
        super().__init__("Braintree")
        self.authorization = authorization
    
    async def check(self, card: CardInfo, **kwargs) -> CheckResponse:
        """Check a card using Braintree"""
        self.start_timer()
        
        # Validate card first
        is_valid, error_msg = validate_card(card.cc, card.month, card.year, card.cvv)
        if not is_valid:
            return self.dead_response(error_msg)
        
        try:
            # Tokenize the card
            self.log(f"Tokenizing card {card.bin}xxxx{card.last4}")
            nonce = await get_braintree_token(
                card.cc, card.month, card.year, card.cvv,
                self.authorization, self.session
            )
            
            if nonce:
                return self.ccn_response(
                    "Card tokenized successfully",
                    nonce=nonce[:20] + "..."
                )
            else:
                return self.dead_response("Failed to tokenize card")
                
        except Exception as e:
            return self.error_response(f"Error: {str(e)}")


# ==================== Generic Shopify Checker Example ====================

class ShopifyBaseChecker(BaseChecker):
    """
    Base class for Shopify store checkers.
    Provides common functionality for Shopify-based sites.
    
    Extend this class and implement the payment submission logic.
    """
    
    def __init__(self, store_url: str):
        super().__init__("Shopify")
        self.store_url = store_url.rstrip("/")
        if not self.store_url.startswith("http"):
            self.store_url = f"https://{self.store_url}"
    
    async def fetch_products(self) -> Optional[Dict]:
        """Fetch available products from the store"""
        try:
            async with self.session.get(
                f"{self.store_url}/products.json",
                headers=self.default_headers
            ) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
                products = data.get("products", [])
                
                # Find cheapest available product
                min_price = float('inf')
                best_product = None
                
                for product in products:
                    for variant in product.get("variants", []):
                        if not variant.get("available", False):
                            continue
                        
                        try:
                            price = float(variant.get("price", "0"))
                            if 0 < price < min_price:
                                min_price = price
                                best_product = {
                                    "variant_id": str(variant["id"]),
                                    "price": f"{price:.2f}",
                                    "title": product.get("title", "Product"),
                                    "handle": product.get("handle", "")
                                }
                        except (ValueError, TypeError):
                            continue
                
                return best_product
                
        except Exception:
            return None
    
    async def add_to_cart(self, variant_id: str) -> bool:
        """Add a product variant to cart"""
        try:
            headers = self.json_headers.copy()
            headers["Origin"] = self.store_url
            
            async with self.session.post(
                f"{self.store_url}/cart/add.js",
                json={"id": variant_id, "quantity": 1},
                headers=headers
            ) as resp:
                return resp.status == 200
        except Exception:
            return False
    
    async def get_checkout(self) -> Optional[str]:
        """Create checkout session and return checkout URL"""
        try:
            headers = self.default_headers.copy()
            
            async with self.session.post(
                f"{self.store_url}/checkout",
                headers=headers,
                allow_redirects=True
            ) as resp:
                return str(resp.url)
        except Exception:
            return None
    
    async def extract_checkout_data(self, checkout_url: str) -> Dict[str, str]:
        """Extract necessary tokens from checkout page"""
        try:
            async with self.session.get(checkout_url, headers=self.default_headers) as resp:
                html = await resp.text()
                
                return {
                    "session_token": self.extract_between(html, 'serialized-session-token" content="&quot;', '&quot'),
                    "queue_token": self.extract_between(html, 'queueToken&quot;:&quot;', '&quot'),
                    "stable_id": self.extract_between(html, 'stableId&quot;:&quot;', '&quot'),
                    "payment_method": self.extract_between(html, 'paymentMethodIdentifier&quot;:&quot;', '&quot'),
                    "currency": self.extract_between(html, 'currencyCode&quot;:&quot;', '&quot') or "USD",
                }
        except Exception:
            return {}
    
    async def check(self, card: CardInfo, **kwargs) -> CheckResponse:
        """
        Main check method. Override in subclass for full implementation.
        This provides the basic structure.
        """
        self.start_timer()
        
        try:
            # Step 1: Find a product
            self.log("Fetching products...")
            product = await self.fetch_products()
            if not product:
                return self.error_response("No available products found", site_error=True)
            
            self.log(f"Found product: {product['title']} @ ${product['price']}")
            
            # Step 2: Add to cart
            self.log("Adding to cart...")
            if not await self.add_to_cart(product["variant_id"]):
                return self.error_response("Failed to add to cart")
            
            # Step 3: Get checkout
            self.log("Creating checkout...")
            checkout_url = await self.get_checkout()
            if not checkout_url:
                return self.error_response("Failed to create checkout")
            
            # Step 4: Extract checkout data
            self.log("Extracting checkout tokens...")
            checkout_data = await self.extract_checkout_data(checkout_url)
            if not checkout_data.get("session_token"):
                return self.error_response("Failed to get session token")
            
            # Step 5: Submit payment (implement in subclass)
            return await self.submit_payment(card, checkout_url, checkout_data, product)
            
        except Exception as e:
            return self.error_response(f"Error: {str(e)}")
    
    async def submit_payment(self, card: CardInfo, checkout_url: str, 
                            checkout_data: Dict, product: Dict) -> CheckResponse:
        """
        Submit payment to gateway.
        Override this method in subclasses for specific gateway implementations.
        """
        # Default implementation - just validates setup
        return self.unknown_response(
            "Payment submission not implemented",
            checkout_url=checkout_url,
            product=product["title"]
        )


# ==================== Simple Site Checker Example ====================

class SimpleSiteChecker(BaseChecker):
    """
    Generic checker for simple payment forms.
    Works with sites that have basic card input forms.
    
    Usage:
        checker = SimpleSiteChecker()
        card = CardInfo.from_string("4111111111111111|12|2025|123")
        result = await checker.check(card, url="https://example.com/payment")
    """
    
    def __init__(self):
        super().__init__("SimpleSite")
    
    async def check(self, card: CardInfo, url: str, **kwargs) -> CheckResponse:
        """Check a card on a simple payment form"""
        self.start_timer()
        
        try:
            # Step 1: Get the payment page
            self.log(f"Fetching {url}")
            async with self.session.get(url, headers=self.default_headers) as resp:
                html = await resp.text()
            
            # Step 2: Extract form data
            form_fields = ResponseParser.extract_form_fields(html)
            csrf_token = ResponseParser.extract_csrf_token(html)
            
            if csrf_token:
                form_fields["_token"] = csrf_token
            
            # Step 3: Add card data (field names vary by site)
            card_fields = {
                "card_number": card.cc,
                "cc_number": card.cc,
                "number": card.cc,
                "exp_month": card.month,
                "cc_exp_month": card.month,
                "exp_year": card.year,
                "cc_exp_year": card.year,
                "cvv": card.cvv,
                "cvc": card.cvv,
                "cc_cvv": card.cvv,
            }
            
            form_fields.update(card_fields)
            
            # Step 4: Submit form
            headers = self.default_headers.copy()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            headers["Origin"] = self.get_domain(url)
            headers["Referer"] = url
            
            async with self.session.post(url, data=form_fields, headers=headers) as resp:
                result_html = await resp.text()
            
            # Step 5: Analyze response
            check_result = self.analyze_response(result_html)
            
            response_map = {
                CheckResult.LIVE: self.live_response,
                CheckResult.CCN: self.ccn_response,
                CheckResult.DEAD: self.dead_response,
                CheckResult.DECLINED: self.declined_response,
                CheckResult.RATE_LIMITED: lambda m: self.make_response(CheckResult.RATE_LIMITED, m),
            }
            
            handler = response_map.get(check_result, self.unknown_response)
            return handler(f"Result: {check_result.value}")
            
        except Exception as e:
            return self.error_response(f"Error: {str(e)}")


# ==================== CLI Interface ====================

async def main():
    """Example usage demonstration"""
    print("=" * 60)
    print("Example Checkers - Demo")
    print("=" * 60)
    
    # Test card (Stripe test card)
    test_card = CardInfo.from_string("4242424242424242|12|2025|123")
    print(f"\nTest Card: {test_card.bin}xxxx{test_card.last4}")
    
    # Look up BIN info
    print("\nLooking up BIN info...")
    bin_info = await lookup_bin(test_card.bin)
    print(f"BIN Info: {bin_info}")
    
    # Example with Stripe (test mode)
    print("\n" + "-" * 40)
    print("Stripe Checker Demo (test mode)")
    print("-" * 40)
    
    # Note: Replace with your actual test keys to run
    stripe_checker = StripeChecker(publishable_key="pk_test_your_key_here")
    
    async with stripe_checker:
        result = await stripe_checker.check(test_card, amount=100)
        print(f"Result: {result}")
    
    # Example with Shopify (structure demo)
    print("\n" + "-" * 40)
    print("Shopify Checker Demo (structure)")
    print("-" * 40)
    
    # Note: Replace with actual store URL
    shopify_checker = ShopifyBaseChecker(store_url="https://example-store.myshopify.com")
    
    async with shopify_checker:
        print("Shopify checker initialized")
        print("Methods available:")
        print("  - fetch_products()")
        print("  - add_to_cart(variant_id)")
        print("  - get_checkout()")
        print("  - extract_checkout_data(checkout_url)")
        print("  - check(card)")
    
    print("\n" + "=" * 60)
    print("To create your own checker:")
    print("=" * 60)
    print("""
1. Create a new class extending BaseChecker:

   class MyGatewayChecker(BaseChecker):
       def __init__(self, api_key):
           super().__init__("MyGateway")
           self.api_key = api_key
       
       async def check(self, card: CardInfo, **kwargs) -> CheckResponse:
           self.start_timer()
           # Your implementation here
           return self.live_response("Success!")

2. Use it:

   async def main():
       checker = MyGatewayChecker(api_key="...")
       card = CardInfo.from_string("4111111111111111|12|2025|123")
       
       async with checker:
           result = await checker.check(card)
           print(result)
   
   asyncio.run(main())
""")


if __name__ == "__main__":
    asyncio.run(main())
