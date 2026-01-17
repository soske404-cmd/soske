import asyncio
import httpx
import re
import json
import time
import random
import string
from urllib.parse import urlparse
from typing import Optional, Tuple

C2C = {
    "USD": "US",
    "CAD": "CA",
    "INR": "IN",
    "AED": "AE",
    "HKD": "HK",
    "GBP": "GB",
    "CHF": "CH",
}

book = {
    "US": {"address1": "123 Main St", "city": "New York", "postalCode": "10001", "zoneCode": "NY", "countryCode": "US", "phone": "2125551234"},
    "CA": {"address1": "88 Queen St", "city": "Toronto", "postalCode": "M5J2J3", "zoneCode": "ON", "countryCode": "CA", "phone": "4165550198"},
    "GB": {"address1": "221B Baker Street", "city": "London", "postalCode": "NW1 6XE", "zoneCode": "LND", "countryCode": "GB", "phone": "2079460123"},
    "IN": {"address1": "221B MG Road", "city": "Mumbai", "postalCode": "400001", "zoneCode": "MH", "countryCode": "IN", "phone": "9876543210"},
    "AE": {"address1": "Burj Tower", "city": "Dubai", "postalCode": "", "zoneCode": "DU", "countryCode": "AE", "phone": "501234567"},
    "HK": {"address1": "Nathan 88", "city": "Kowloon", "postalCode": "", "zoneCode": "KL", "countryCode": "HK", "phone": "55555555"},
    "CN": {"address1": "8 Zhongguancun Street", "city": "Beijing", "postalCode": "100080", "zoneCode": "BJ", "countryCode": "CN", "phone": "1062512345"},
    "CH": {"address1": "Gotthardstrasse 17", "city": "Schweiz", "postalCode": "6430", "zoneCode": "SZ", "countryCode": "CH", "phone": "445512345"},
    "AU": {"address1": "1 Martin Place", "city": "Sydney", "postalCode": "2000", "zoneCode": "NSW", "countryCode": "AU", "phone": "291234567"},
    "DEFAULT": {"address1": "123 Main St", "city": "New York", "postalCode": "10001", "zoneCode": "NY", "countryCode": "US", "phone": "2125551234"},
}


def pick_addr(url, cc=None, rc=None):
    cc = (cc or "").upper()
    rc = (rc or "").upper()
    dom = urlparse(url).netloc
    tcn = dom.split('.')[-1].upper()

    if tcn in book:
        return book[tcn]

    ccn = C2C.get(cc)

    if rc in book and ccn == rc:
        return book[rc]
    elif rc in book:
        return book[rc]
    return book["DEFAULT"]


def capture(data, first, last):
    try:
        start = data.index(first) + len(first)
        end = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None


def generate_random_name():
    """Generate random first and last name"""
    first_names = ['John', 'James', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph']
    last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis']
    return random.choice(first_names), random.choice(last_names)


def generate_email(first_name: str, last_name: str) -> str:
    """Generate random email"""
    domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com']
    random_num = ''.join(random.choices(string.digits, k=3))
    return f"{first_name.lower()}.{last_name.lower()}{random_num}@{random.choice(domains)}"


async def fetch_products(session, base_url: str):
    """Fetch cheapest product from Shopify store"""
    try:
        url = f"{base_url}/products.json"
        resp = await session.get(url, timeout=15)
        
        if resp.status_code != 200:
            return None, None, "Site Error - Cannot access products"
        
        text = resp.text
        if "shopify" not in text.lower() and "products" not in text.lower():
            return None, None, "Not a Shopify site"
        
        data = resp.json()
        products = data.get('products', [])
        
        if not products:
            return None, None, "No products found"
        
        min_price = float('inf')
        min_product = None
        
        for product in products:
            if not product.get('variants'):
                continue
            
            for variant in product['variants']:
                if not variant.get('available', False):
                    continue
                
                try:
                    price = variant.get('price', '0')
                    if isinstance(price, str):
                        price = float(price.replace(',', ''))
                    else:
                        price = float(price)
                    
                    if price < min_price and price > 0:
                        min_price = price
                        min_product = {
                            'price': f"{price:.2f}",
                            'variant_id': str(variant['id']),
                            'handle': product['handle']
                        }
                except (ValueError, TypeError, KeyError):
                    continue
        
        if min_product:
            return min_product['variant_id'], min_product['price'], None
        else:
            return None, None, "No valid products found"
            
    except Exception as e:
        return None, None, f"Error: {str(e)}"


async def autoshopify(url, card, session):
    output = {
        "Response": "UNKNOWN ERROR",
        "Status": False,
    }
    start = time.time()
    
    try:
        # Parse card
        cc, mes, ano, cvv = map(str.strip, card.split("|"))
        
        # Format year
        if len(ano) == 2:
            ano = '20' + ano
        
        # Normalize URL
        if not url.startswith('http'):
            url = f"https://{url}"
        url = url.rstrip('/')
        
        domain = urlparse(url).netloc
        
        # Generate random user info
        firstName, lastName = generate_random_name()
        email = generate_email(firstName, lastName)
        
        # Fetch products
        product_id, price, error = await fetch_products(session, url)
        
        if not product_id:
            output.update({
                "Response": error or "PRODUCT EMPTY",
                "Status": False,
            })
            print(json.dumps(output))
            return output
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Content-Type': 'application/json',
        }
        
        # Step 1: Add to cart
        cart_url = f"{url}/cart/add.js"
        await session.post(cart_url, json={'id': product_id}, headers=headers)
        
        # Step 2: Go to checkout
        checkout_url = f"{url}/checkout/"
        resp = await session.post(checkout_url, headers=headers, follow_redirects=True)
        checkout_url = str(resp.url)
        
        if 'login' in checkout_url.lower():
            output.update({
                "Response": "SITE REQUIRES LOGIN",
                "Status": False,
            })
            print(json.dumps(output))
            return output
        
        # Get session token
        resp = await session.get(checkout_url, headers=headers, follow_redirects=True)
        text = resp.text
        
        sst = capture(text, 'name="serialized-session-token" content="&quot;', '&q')
        if not sst:
            await asyncio.sleep(2)
            resp = await session.get(checkout_url, headers=headers, follow_redirects=True)
            text = resp.text
            sst = capture(text, 'name="serialized-session-token" content="&quot;', '&q')
        
        if not sst:
            output.update({
                "Response": "FAILED TO GET SESSION TOKEN",
                "Status": False,
            })
            print(json.dumps(output))
            return output
        
        # Extract other required data
        queueToken = capture(text, 'queueToken&quot;:&quot;', '&q')
        stableId = capture(text, 'stableId&quot;:&quot;', '&q')
        subtotal = capture(text, 'totalAmount&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;', '&q')
        paymentMethodIdentifier = capture(text, "paymentMethodIdentifier&quot;:&quot;", "&quot")
        token = capture(text, 'serialized-source-token" content="&quot;', '&quot')
        web_build = capture(text, 'serialized-client-bundle-info" content="{&quot;browsers&quot;:&quot;latest&quot;,&quot;format&quot;:&quot;es&quot;,&quot;locale&quot;:&quot;en&quot;,&quot;sha&quot;:&quot;', '&quot')
        
        pattern = r'currencycode\s*[:=]\s*["\']?([^"\']+)["\']?'
        currency_match = re.search(pattern, text.lower())
        currency = currency_match.group(1).upper() if currency_match else 'USD'
        
        countryCode_match = re.search(r'countryCode&quot;:&quot;([A-Z]{2})&quot', text)
        countryCode = countryCode_match.group(1) if countryCode_match else 'US'
        
        gateway = capture(text, 'extensibilityDisplayName&quot;:&quot;', '&quot')
        if gateway == "Shopify Payments":
            gateway = "Normal"
        elif not gateway:
            gateway = "Unknown"
        
        DMT = capture(text, 'deliveryMethodTypes&quot;:[&quot;', '&quot;],&quot;')
        if not DMT:
            DMT = "SHIPPING"
        
        # Get address based on currency/country
        addr = pick_addr(url, cc=currency, rc=countryCode)
        
        graphql_url = f"https://{domain}/checkouts/unstable/graphql"
        
        # Get payment session ID
        pci_headers = {
            'authority': 'checkout.pci.shopifyinc.com',
            'accept': 'application/json',
            'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
            'content-type': 'application/json',
            'origin': 'https://checkout.pci.shopifyinc.com',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36'
        }
        
        pci_json = {
            'credit_card': {
                'number': cc,
                'month': mes,
                'year': ano,
                'verification_value': cvv,
                'start_month': None,
                'start_year': None,
                'issue_number': '',
                'name': f'{firstName} {lastName}',
            },
            'payment_session_scope': domain
        }
        
        resp = await session.post('https://checkout.pci.shopifyinc.com/sessions', headers=pci_headers, json=pci_json)
        
        try:
            payment_token = resp.json()["id"]
        except:
            output.update({
                "Response": "FAILED TO GET PAYMENT TOKEN",
                "Status": False,
            })
            print(json.dumps(output))
            return output
        
        await asyncio.sleep(0.1)
        
        # GraphQL headers
        gql_headers = {
            'authority': domain,
            'accept': 'application/json',
            'accept-language': 'en-IN',
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
            'x-checkout-one-session-token': sst,
            'x-checkout-web-deploy-stage': 'production',
            'x-checkout-web-server-handling': 'fast',
            'x-checkout-web-server-rendering': 'yes',
        }
        
        if web_build:
            gql_headers['x-checkout-web-build-id'] = web_build
        if token:
            gql_headers['x-checkout-web-source-id'] = token
        
        # STEP 1: SHIPPING PROPOSAL
        shipping_json = {
            'query': 'query Proposal($alternativePaymentCurrency:AlternativePaymentCurrencyInput,$delivery:DeliveryTermsInput,$discounts:DiscountTermsInput,$payment:PaymentTermInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$taxes:TaxTermInput,$sessionInput:SessionTokenInput!,$checkpointData:String,$queueToken:String,$reduction:ReductionInput,$availableRedeemables:AvailableRedeemablesInput,$changesetTokens:[String!],$tip:TipTermInput,$note:NoteInput,$localizationExtension:LocalizationExtensionInput,$nonNegotiableTerms:NonNegotiableTermsInput,$scriptFingerprint:ScriptFingerprintInput,$transformerFingerprintV2:String,$optionalDuties:OptionalDutiesInput,$attribution:AttributionInput,$captcha:CaptchaInput,$poNumber:String,$saleAttributions:SaleAttributionsInput){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{alternativePaymentCurrency:$alternativePaymentCurrency,delivery:$delivery,discounts:$discounts,payment:$payment,merchandise:$merchandise,buyerIdentity:$buyerIdentity,taxes:$taxes,reduction:$reduction,availableRedeemables:$availableRedeemables,tip:$tip,note:$note,poNumber:$poNumber,nonNegotiableTerms:$nonNegotiableTerms,localizationExtension:$localizationExtension,scriptFingerprint:$scriptFingerprint,transformerFingerprintV2:$transformerFingerprintV2,optionalDuties:$optionalDuties,attribution:$attribution,captcha:$captcha,saleAttributions:$saleAttributions},checkpointData:$checkpointData,queueToken:$queueToken,changesetTokens:$changesetTokens}){__typename result{...on NegotiationResultAvailable{queueToken sellerProposal{delivery{...on FilledDeliveryTerms{deliveryLines{availableDeliveryStrategies{...on CompleteDeliveryStrategy{handle title amount{...on MoneyValueConstraint{value{amount currencyCode}}}}}}}}runningTotal{...on MoneyValueConstraint{value{amount currencyCode}}}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode}}}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode}}}}}}errors{code localizedMessage}}}}',
            'variables': {
                'sessionInput': {
                    'sessionToken': sst,
                },
                'queueToken': queueToken,
                'discounts': {
                    'lines': [],
                    'acceptUnexpectedDiscounts': True,
                },
                'delivery': {
                    'deliveryLines': [
                        {
                            'destination': {
                                'partialStreetAddress': {
                                    'address1': addr['address1'],
                                    'address2': '',
                                    'city': addr['city'],
                                    'countryCode': addr['countryCode'],
                                    'postalCode': addr['postalCode'],
                                    'firstName': firstName,
                                    'lastName': lastName,
                                    'zoneCode': addr['zoneCode'],
                                    'phone': addr['phone'],
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
                            ],
                            'expectedTotalPrice': {
                                'any': True,
                            },
                            'destinationChanged': True,
                        },
                    ],
                    'noDeliveryRequired': [],
                    'useProgressiveRates': False,
                    'prefetchShippingRatesStrategy': None,
                    'supportsSplitShipping': True,
                },
                'merchandise': {
                    'merchandiseLines': [
                        {
                            'stableId': stableId,
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
                                    'amount': subtotal or price,
                                    'currencyCode': currency,
                                },
                            },
                            'lineComponentsSource': None,
                            'lineComponents': [],
                        },
                    ],
                },
                'payment': {
                    'totalAmount': {
                        'any': True,
                    },
                    'paymentLines': [],
                    'billingAddress': None,
                },
                'buyerIdentity': {
                    'customer': {
                        'presentmentCurrency': currency,
                        'countryCode': addr['countryCode'],
                    },
                    'email': email,
                    'emailChanged': True,
                },
            },
            'operationName': 'Proposal',
        }
        
        resp = await session.post(graphql_url, json=shipping_json, headers=gql_headers, params={'operationName': 'Proposal'})
        ship_text = resp.text
        
        # Extract shipping info
        handle = capture(ship_text, '"handle":"', '"')
        running_total = capture(ship_text, '"runningTotal":{"__typename":"MoneyValueConstraint","value":{"amount":"', '"')
        tax_amount = capture(ship_text, '"checkoutTotalTaxes":{"__typename":"MoneyValueConstraint","value":{"amount":"', '"')
        
        if not handle:
            handle = capture(ship_text, 'handle&quot;:&quot;', '&quot')
        if not running_total:
            running_total = subtotal or price
        if not tax_amount:
            tax_amount = "0.00"
        
        total = running_total or subtotal or price
        
        # STEP 2: PAYMENT PROPOSAL
        payment_json = {
            'query': 'query Proposal($alternativePaymentCurrency:AlternativePaymentCurrencyInput,$delivery:DeliveryTermsInput,$discounts:DiscountTermsInput,$payment:PaymentTermInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$taxes:TaxTermInput,$sessionInput:SessionTokenInput!,$checkpointData:String,$queueToken:String,$reduction:ReductionInput,$availableRedeemables:AvailableRedeemablesInput,$changesetTokens:[String!],$tip:TipTermInput,$note:NoteInput,$localizationExtension:LocalizationExtensionInput,$nonNegotiableTerms:NonNegotiableTermsInput,$scriptFingerprint:ScriptFingerprintInput,$transformerFingerprintV2:String,$optionalDuties:OptionalDutiesInput,$attribution:AttributionInput,$captcha:CaptchaInput,$poNumber:String,$saleAttributions:SaleAttributionsInput){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{alternativePaymentCurrency:$alternativePaymentCurrency,delivery:$delivery,discounts:$discounts,payment:$payment,merchandise:$merchandise,buyerIdentity:$buyerIdentity,taxes:$taxes,reduction:$reduction,availableRedeemables:$availableRedeemables,tip:$tip,note:$note,poNumber:$poNumber,nonNegotiableTerms:$nonNegotiableTerms,localizationExtension:$localizationExtension,scriptFingerprint:$scriptFingerprint,transformerFingerprintV2:$transformerFingerprintV2,optionalDuties:$optionalDuties,attribution:$attribution,captcha:$captcha,saleAttributions:$saleAttributions},checkpointData:$checkpointData,queueToken:$queueToken,changesetTokens:$changesetTokens}){__typename result{...on NegotiationResultAvailable{queueToken sellerProposal{checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode}}}}}errors{code localizedMessage}}}}',
            'variables': {
                'sessionInput': {
                    'sessionToken': sst,
                },
                'queueToken': queueToken,
                'discounts': {
                    'lines': [],
                    'acceptUnexpectedDiscounts': True,
                },
                'delivery': {
                    'deliveryLines': [
                        {
                            'destination': {
                                'streetAddress': {
                                    'address1': addr['address1'],
                                    'address2': '',
                                    'city': addr['city'],
                                    'countryCode': addr['countryCode'],
                                    'postalCode': addr['postalCode'],
                                    'firstName': firstName,
                                    'lastName': lastName,
                                    'zoneCode': addr['zoneCode'],
                                    'phone': addr['phone'],
                                },
                            },
                            'selectedDeliveryStrategy': {
                                'deliveryStrategyByHandle': {
                                    'handle': handle or 'shopify-pickup-in-store-0',
                                    'customDeliveryRate': False,
                                },
                                'options': {},
                            },
                            'targetMerchandiseLines': {
                                'lines': [
                                    {
                                        'stableId': stableId,
                                    },
                                ],
                            },
                            'deliveryMethodTypes': [
                                DMT,
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
                'merchandise': {
                    'merchandiseLines': [
                        {
                            'stableId': stableId,
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
                                    'amount': subtotal or price,
                                    'currencyCode': currency,
                                },
                            },
                            'lineComponentsSource': None,
                            'lineComponents': [],
                        },
                    ],
                },
                'payment': {
                    'totalAmount': {
                        'any': True,
                    },
                    'paymentLines': [
                        {
                            'paymentMethod': {
                                'directPaymentMethod': {
                                    'paymentMethodIdentifier': paymentMethodIdentifier or 'https://elb.deposit.shopifycs.com/sessions',
                                    'sessionId': payment_token,
                                    'billingAddress': {
                                        'streetAddress': {
                                            'address1': addr['address1'],
                                            'address2': '',
                                            'city': addr['city'],
                                            'countryCode': addr['countryCode'],
                                            'postalCode': addr['postalCode'],
                                            'firstName': firstName,
                                            'lastName': lastName,
                                            'zoneCode': addr['zoneCode'],
                                            'phone': addr['phone'],
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
                                    'amount': total,
                                    'currencyCode': currency
                                },
                            },
                            'dueAt': None,
                        },
                    ],
                    'billingAddress': {
                        'streetAddress': {
                            'address1': addr['address1'],
                            'address2': '',
                            'city': addr['city'],
                            'countryCode': addr['countryCode'],
                            'postalCode': addr['postalCode'],
                            'firstName': firstName,
                            'lastName': lastName,
                            'zoneCode': addr['zoneCode'],
                            'phone': addr['phone'],
                        },
                    },
                },
                'buyerIdentity': {
                    'customer': {
                        'presentmentCurrency': currency,
                        'countryCode': addr['countryCode'],
                    },
                    'email': email,
                    'emailChanged': False,
                    'phoneCountryCode': addr['countryCode'],
                    'marketingConsent': [
                        {
                            'email': {
                                'value': email,
                            },
                        },
                    ],
                    'shopPayOptInPhone': {
                        'number': addr['phone'],
                        'countryCode': addr['countryCode'],
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
                            'amount': tax_amount,
                            'currencyCode': currency,
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
            },
            'operationName': 'Proposal',
        }
        
        resp = await session.post(graphql_url, json=payment_json, headers=gql_headers, params={'operationName': 'Proposal'})
        pay_text = resp.text
        
        # Update queueToken if available
        new_queue_token = capture(pay_text, '"queueToken":"', '"')
        if new_queue_token:
            queueToken = new_queue_token
        
        await asyncio.sleep(0.5)
        
        # STEP 3: SUBMIT FOR COMPLETION
        attempt_token = checkout_url.split('/')[-1] if '/' in checkout_url else token
        
        completion_json = {
            'query': 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails}}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails}}...on SubmitFailed{reason}...on SubmitRejected{errors{code localizedMessage}}...on Throttled{pollAfter queueToken}...on CheckpointDenied{redirectUrl}...on SubmittedForCompletion{receipt{...ReceiptDetails}}}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token}...on ProcessingReceipt{id pollDelay}...on WaitingReceipt{id pollDelay}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{url}...on CompletePaymentChallengeV2{challengeType challengeData}}}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated}}}}',
            'variables': {
                'input': {
                    'sessionInput': {
                        'sessionToken': sst,
                    },
                    'queueToken': queueToken,
                    'discounts': {
                        'lines': [],
                        'acceptUnexpectedDiscounts': True,
                    },
                    'delivery': {
                        'deliveryLines': [
                            {
                                'destination': {
                                    'streetAddress': {
                                        'address1': addr['address1'],
                                        'address2': '',
                                        'city': addr['city'],
                                        'countryCode': addr['countryCode'],
                                        'postalCode': addr['postalCode'],
                                        'firstName': firstName,
                                        'lastName': lastName,
                                        'zoneCode': addr['zoneCode'],
                                        'phone': addr['phone'],
                                        'oneTimeUse': False,
                                    },
                                },
                                'selectedDeliveryStrategy': {
                                    'deliveryStrategyByHandle': {
                                        'handle': handle or 'shopify-pickup-in-store-0',
                                        'customDeliveryRate': False,
                                    },
                                    'options': {
                                        'phone': addr['phone'],
                                    },
                                },
                                'targetMerchandiseLines': {
                                    'lines': [
                                        {
                                            'stableId': stableId,
                                        },
                                    ],
                                },
                                'deliveryMethodTypes': [
                                    DMT,
                                ],
                                'expectedTotalPrice': {
                                    'value': {
                                        'amount': total,
                                        'currencyCode': currency,
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
                    'merchandise': {
                        'merchandiseLines': [
                            {
                                'stableId': stableId,
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
                                        'amount': subtotal or price,
                                        'currencyCode': currency,
                                    },
                                },
                                'lineComponentsSource': None,
                                'lineComponents': [],
                            },
                        ],
                    },
                    'payment': {
                        'totalAmount': {
                            'any': True,
                        },
                        'paymentLines': [
                            {
                                'paymentMethod': {
                                    'directPaymentMethod': {
                                        'paymentMethodIdentifier': paymentMethodIdentifier or 'https://elb.deposit.shopifycs.com/sessions',
                                        'sessionId': payment_token,
                                        'billingAddress': {
                                            'streetAddress': {
                                                'address1': addr['address1'],
                                                'address2': '',
                                                'city': addr['city'],
                                                'countryCode': addr['countryCode'],
                                                'postalCode': addr['postalCode'],
                                                'firstName': firstName,
                                                'lastName': lastName,
                                                'zoneCode': addr['zoneCode'],
                                                'phone': addr['phone'],
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
                                        'amount': total,
                                        'currencyCode': currency
                                    },
                                },
                                'dueAt': None,
                            },
                        ],
                        'billingAddress': {
                            'streetAddress': {
                                'address1': addr['address1'],
                                'address2': '',
                                'city': addr['city'],
                                'countryCode': addr['countryCode'],
                                'postalCode': addr['postalCode'],
                                'firstName': firstName,
                                'lastName': lastName,
                                'zoneCode': addr['zoneCode'],
                                'phone': addr['phone'],
                            },
                        },
                    },
                    'buyerIdentity': {
                        'customer': {
                            'presentmentCurrency': currency,
                            'countryCode': addr['countryCode'],
                        },
                        'email': email,
                        'emailChanged': False,
                        'phoneCountryCode': addr['countryCode'],
                        'marketingConsent': [
                            {
                                'email': {
                                    'value': email,
                                },
                            },
                        ],
                        'shopPayOptInPhone': {
                            'number': addr['phone'],
                            'countryCode': addr['countryCode'],
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
                                'amount': tax_amount,
                                'currencyCode': currency,
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
                },
                'attemptToken': attempt_token,
                'metafields': [],
                'analytics': {
                    'requestUrl': checkout_url,
                },
            },
            'operationName': 'SubmitForCompletion',
        }
        
        resp = await session.post(graphql_url, json=completion_json, headers=gql_headers, params={'operationName': 'SubmitForCompletion'})
        result_text = resp.text
        
        if "Your order total has changed." in result_text:
            output.update({
                "Response": "SITE_NOT_SUPPORTED",
                "Status": False,
            })
            print(json.dumps(output))
            return output
        
        if "The requested payment method is not available." in result_text:
            output.update({
                "Response": "PAYMENT_METHOD_NOT_AVAILABLE",
                "Status": False,
            })
            print(json.dumps(output))
            return output
        
        # Try to get receipt ID
        receipt_id = capture(result_text, '"id":"', '"')
        
        if not receipt_id and 'CAPTCHA_METADATA_MISSING' in result_text:
            output.update({
                "Response": "CAPTCHA_REQUIRED",
                "Status": False,
            })
            print(json.dumps(output))
            return output
        
        if not receipt_id:
            await asyncio.sleep(3)
            resp = await session.post(graphql_url, json=completion_json, headers=gql_headers, params={'operationName': 'SubmitForCompletion'})
            result_text = resp.text
            receipt_id = capture(result_text, '"id":"', '"')
        
        if not receipt_id:
            if 'PAYMENTS_CREDIT_CARD_VERIFICATION_VALUE_INVALID_FOR_CARD_TYPE' in result_text:
                output.update({
                    "Response": "INVALID_CVV",
                    "Status": True,
                    "Gateway": gateway,
                    "Price": total,
                    "cc": card
                })
                print(json.dumps(output))
                return output
            output.update({
                "Response": "ERROR_PROCESSING_CARD",
                "Status": False,
            })
            print(json.dumps(output))
            return output
        
        # STEP 4: POLL FOR RECEIPT
        await asyncio.sleep(3)
        
        poll_json = {
            'query': 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token}...on ProcessingReceipt{id pollDelay}...on WaitingReceipt{id pollDelay}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{url}...on CompletePaymentChallengeV2{challengeType challengeData}}}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated}}}}',
            'variables': {
                'receiptId': receipt_id,
                'sessionToken': sst,
            },
            'operationName': 'PollForReceipt',
        }
        
        for i in range(3):
            resp = await session.post(graphql_url, json=poll_json, headers=gql_headers, params={'operationName': 'PollForReceipt'})
            poll_text = resp.text
            
            if 'WaitingReceipt' not in poll_text and 'ProcessingReceipt' not in poll_text:
                break
            
            await asyncio.sleep(3)
        
        res_json = poll_text
        
        # Parse result
        result = capture(res_json, '"code":"', '"')
        
        if "shopify_payments" in res_json.lower() or "ProcessedReceipt" in res_json:
            if "processingError" not in res_json.lower():
                output.update({
                    "Response": "ORDER_PLACED",
                    "Status": True,
                    "Gateway": gateway,
                    "Price": total,
                    "cc": card
                })
        elif "ActionRequiredReceipt" in res_json or "CompletePaymentChallenge" in res_json:
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
        elif "FRAUD_SUSPECTED" in res_json:
            output.update({
                "Response": "FRAUD_SUSPECTED",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "INCORRECT_ADDRESS" in res_json:
            output.update({
                "Response": "INCORRECT_ADDRESS",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "INCORRECT_ZIP" in res_json:
            output.update({
                "Response": "INCORRECT_ZIP",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "INCORRECT_PIN" in res_json:
            output.update({
                "Response": "MISMATCHED_PIN",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "insufficient_funds" in res_json.lower():
            output.update({
                "Response": "INSUFFICIENT_FUNDS",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "INVALID_CVC" in res_json or "INCORRECT_CVC" in res_json:
            output.update({
                "Response": "INCORRECT_CVC",
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
            "Response": str(e),
            "Status": False,
        })

    print(json.dumps(output))
    return output


async def main():
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as session:
        await autoshopify("https://example.myshopify.com/", "4111111111111111|12|2028|123", session)


if __name__ == "__main__":
    asyncio.run(main())
