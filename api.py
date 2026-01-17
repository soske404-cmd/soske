from time import sleep
import asyncio
import httpx
import requests
import re
import base64
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
    "HK": {"address1": "Nathan Road 88", "city": "Kowloon", "postalCode": "", "zoneCode": "KL", "countryCode": "HK", "phone": "55555555"},
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


def get_product_id(response):
    response_data = response.json()
    products_data = response_data.get("products", [])
    products = {}
    
    for product in products_data:
        variants = product.get("variants", [])
        for variant in variants:
            variant_id = variant.get("id")
            available = variant.get("available", False)
            try:
                price = float(variant.get("price", 0))
            except (ValueError, TypeError):
                continue
            if price < 0.1:
                continue
            if available:
                products[variant_id] = price
    
    if products:
        min_price_product_id = min(products, key=products.get)
        price = products[min_price_product_id]
        return min_price_product_id, price

    return None, None


def generate_random_name() -> Tuple[str, str]:
    """Generate random first and last name"""
    first_names = ['John', 'James', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph', 'Thomas', 'Charles']
    last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Wilson', 'Moore']
    return random.choice(first_names), random.choice(last_names)


def generate_email(first_name: str, last_name: str) -> str:
    """Generate random email"""
    domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com']
    random_num = ''.join(random.choices(string.digits, k=4))
    return f"{first_name.lower()}.{last_name.lower()}{random_num}@{random.choice(domains)}"


async def autoshopify(url, card, session):
    output = {
        "Response": "UNKNOWN ERROR",
        "Status": False,
    }
    start = time.time()
    
    try:
        # Parse URL and card
        if not url.startswith("http"):
            url = f"https://{url}"
        url = url.rstrip("/")
        domain = urlparse(url).netloc
        
        cc, mes, ano, cvv = map(str.strip, card.split("|"))
        
        # Format year
        if len(ano) == 2:
            ano = '20' + ano
        
        # Generate random buyer info
        firstName, lastName = generate_random_name()
        email = generate_email(firstName, lastName)
        
        # Get products
        try:
            request = await session.get(f"{url}/products.json", timeout=15)
            product_id, price = get_product_id(request)
        except Exception as e:
            output.update({
                "Response": "SITE_ERROR",
                "Status": False,
            })
            print(json.dumps(output))
            return output
            
        if not product_id:
            output.update({
                "Response": "PRODUCT_EMPTY",
                "Status": False,
            })
            print(json.dumps(output))
            return output

        # Get checkout page
        try:
            request = await session.get(url, timeout=15)
        except:
            output.update({
                "Response": "SITE_DEAD",
                "Status": False,
            })
            print(json.dumps(output))
            return output

        site_key = capture(request.text, '"accessToken":"', '"')
        
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

        # Create cart
        json_data = {
            'query': 'mutation cartCreate($input:CartInput!$country:CountryCode$language:LanguageCode$withCarrierRates:Boolean=false)@inContext(country:$country language:$language){result:cartCreate(input:$input){...@defer(if:$withCarrierRates){cart{...CartParts}errors:userErrors{...on CartUserError{message field code}}warnings:warnings{...on CartWarning{code}}}}}fragment CartParts on Cart{id checkoutUrl deliveryGroups(first:10 withCarrierRates:$withCarrierRates){edges{node{id groupType selectedDeliveryOption{code title handle deliveryPromise deliveryMethodType estimatedCost{amount currencyCode}}deliveryOptions{code title handle deliveryPromise deliveryMethodType estimatedCost{amount currencyCode}}}}}cost{subtotalAmount{amount currencyCode}totalAmount{amount currencyCode}totalTaxAmount{amount currencyCode}totalDutyAmount{amount currencyCode}}discountAllocations{discountedAmount{amount currencyCode}...on CartCodeDiscountAllocation{code}...on CartAutomaticDiscountAllocation{title}...on CartCustomDiscountAllocation{title}}discountCodes{code applicable}lines(first:10){edges{node{quantity cost{subtotalAmount{amount currencyCode}totalAmount{amount currencyCode}}discountAllocations{discountedAmount{amount currencyCode}...on CartCodeDiscountAllocation{code}...on CartAutomaticDiscountAllocation{title}...on CartCustomDiscountAllocation{title}}merchandise{...on ProductVariant{requiresShipping}}sellingPlanAllocation{priceAdjustments{price{amount currencyCode}}sellingPlan{billingPolicy{...on SellingPlanRecurringBillingPolicy{interval intervalCount}}priceAdjustments{orderCount}recurringDeliveries}}}}}}',
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

        request = await session.post(f'{url}/api/unstable/graphql.json', params={'operation_name': 'cartCreate'}, headers=headers, json=json_data)
        data = request.json()
        
        try:
            checkout_url = data["data"]["result"]["cart"]["checkoutUrl"]
        except:
            output.update({
                "Response": "CART_ERROR",
                "Status": False,
            })
            print(json.dumps(output))
            return output

        # Get checkout session
        headers = {
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

        request = await session.get(checkout_url, headers=headers, params={'skip_shop_pay': 'true'}, follow_redirects=True)
        text = request.text
        
        # Extract session data
        paymentMethodIdentifier = capture(text, "paymentMethodIdentifier&quot;:&quot;", "&quot")
        stable_id = capture(text, "stableId&quot;:&quot;", "&quot")
        queue_token = capture(text, "queueToken&quot;:&quot;", "&quot")
        currencyCode = capture(text, "currencyCode&quot;:&quot;", "&quot") or "USD"
        countryCode = capture(text, "countryCode&quot;:&quot;", "&quot") or "US"
        x_checkout_one_session_token = capture(text, 'serialized-session-token" content="&quot;', '&quot')
        token = capture(text, 'serialized-source-token" content="&quot;', '&quot')
        web_build = capture(text, 'serialized-client-bundle-info" content="{&quot;browsers&quot;:&quot;latest&quot;,&quot;format&quot;:&quot;es&quot;,&quot;locale&quot;:&quot;en&quot;,&quot;sha&quot;:&quot;', '&quot')
        tax = capture(text, "totalTaxAndDutyAmount&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;", "&quot") or "0.00"
        gateway = capture(text, 'extensibilityDisplayName&quot;:&quot;', '&quot')
        
        if gateway == "Shopify Payments":
            gateway = "Normal"
        elif gateway:
            gateway = gateway
        else:
            gateway = "Unknown"

        if not x_checkout_one_session_token:
            output.update({
                "Response": "SESSION_ERROR",
                "Status": False,
            })
            print(json.dumps(output))
            return output

        # Get address based on currency/country
        addr = pick_addr(url, cc=currencyCode, rc=countryCode)

        # Get payment token from deposit.shopifycs.com (WORKING METHOD)
        headers = {
            'accept': 'application/json',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://deposit.shopifycs.com',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36'
        }
        
        json_data = {
            'credit_card': {
                'number': cc,
                'month': mes,
                'year': ano,
                'verification_value': cvv,
                'name': f'{firstName} {lastName}',
            },
            'payment_session_scope': domain
        }

        request = await session.post('https://deposit.shopifycs.com/sessions', headers=headers, json=json_data)
        
        try:
            sessionid = request.json()["id"]
        except:
            output.update({
                "Response": "INVALID_CARD_FORMAT",
                "Status": False,
            })
            print(json.dumps(output))
            return output

        await asyncio.sleep(0.2)

        # Shipping Proposal
        headers = {
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
            'x-checkout-one-session-token': x_checkout_one_session_token,
            'x-checkout-web-build-id': web_build or '',
            'x-checkout-web-deploy-stage': 'production',
            'x-checkout-web-server-handling': 'fast',
            'x-checkout-web-server-rendering': 'yes',
            'x-checkout-web-source-id': token or '',
        }

        shipping_query = 'query Proposal($alternativePaymentCurrency:AlternativePaymentCurrencyInput,$delivery:DeliveryTermsInput,$discounts:DiscountTermsInput,$payment:PaymentTermInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$taxes:TaxTermInput,$sessionInput:SessionTokenInput!,$checkpointData:String,$queueToken:String,$reduction:ReductionInput,$availableRedeemables:AvailableRedeemablesInput,$changesetTokens:[String!],$tip:TipTermInput,$note:NoteInput,$localizationExtension:LocalizationExtensionInput,$nonNegotiableTerms:NonNegotiableTermsInput,$scriptFingerprint:ScriptFingerprintInput,$transformerFingerprintV2:String,$optionalDuties:OptionalDutiesInput,$attribution:AttributionInput,$captcha:CaptchaInput,$poNumber:String,$saleAttributions:SaleAttributionsInput){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{alternativePaymentCurrency:$alternativePaymentCurrency,delivery:$delivery,discounts:$discounts,payment:$payment,merchandise:$merchandise,buyerIdentity:$buyerIdentity,taxes:$taxes,reduction:$reduction,availableRedeemables:$availableRedeemables,tip:$tip,note:$note,poNumber:$poNumber,nonNegotiableTerms:$nonNegotiableTerms,localizationExtension:$localizationExtension,scriptFingerprint:$scriptFingerprint,transformerFingerprintV2:$transformerFingerprintV2,optionalDuties:$optionalDuties,attribution:$attribution,captcha:$captcha,saleAttributions:$saleAttributions},checkpointData:$checkpointData,queueToken:$queueToken,changesetTokens:$changesetTokens}){__typename result{...on NegotiationResultAvailable{checkpointData queueToken buyerProposal{...BuyerProposalDetails __typename}sellerProposal{...ProposalDetails __typename}__typename}...on CheckpointDenied{redirectUrl __typename}...on Throttled{pollAfter queueToken pollUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}...on NegotiationResultFailed{__typename}__typename}errors{code localizedMessage nonLocalizedMessage localizedMessageHtml __typename}}__typename}}fragment BuyerProposalDetails on Proposal{buyerIdentity{...on FilledBuyerIdentityTerms{email phone __typename}__typename}delivery{...ProposalDeliveryFragment __typename}merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...on ProductVariantMerchandise{id variantId __typename}...on ContextualizedProductVariantMerchandise{id variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}fragment ProposalDeliveryFragment on DeliveryTerms{__typename...on FilledDeliveryTerms{deliveryLines{destinationAddress{...on StreetAddress{firstName lastName address1 address2 city countryCode zoneCode postalCode phone __typename}...on PartialStreetAddress{firstName lastName address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}groupType selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}__typename}availableDeliveryStrategies{...on CompleteDeliveryStrategy{title handle methodType amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment ProposalDetails on Proposal{delivery{...on FilledDeliveryTerms{deliveryLines{availableDeliveryStrategies{...on CompleteDeliveryStrategy{handle title amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}__typename}payment{...on FilledPaymentTerms{availablePaymentLines{paymentMethod{...on PaymentProvider{paymentMethodIdentifier name __typename}__typename}__typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}tax{...on FilledTaxTerms{totalTaxAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id __typename}...on ProcessingReceipt{id pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id __typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}'

        json_data = {
            'query': shipping_query,
            'variables': {
                'sessionInput': {
                    'sessionToken': x_checkout_one_session_token,
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
                                    'firstName': firstName,
                                    'lastName': lastName,
                                    'zoneCode': addr["zoneCode"],
                                    'phone': addr["phone"],
                                }
                            },
                            'selectedDeliveryStrategy': {
                                'deliveryStrategyMatchingConditions': {
                                    'estimatedTimeInTransit': {'any': True},
                                    'shipments': {'any': True},
                                },
                                'options': {},
                            },
                            'targetMerchandiseLines': {'any': True},
                            'deliveryMethodTypes': ['SHIPPING'],
                            'expectedTotalPrice': {'any': True},
                            'destinationChanged': True,
                        },
                    ],
                    'noDeliveryRequired': [],
                    'useProgressiveRates': False,
                    'prefetchShippingRatesStrategy': None,
                    'supportsSplitShipping': True,
                },
                'deliveryExpectations': {'deliveryExpectationLines': []},
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
                            'quantity': {'items': {'value': 1}},
                            'expectedTotalPrice': {
                                'value': {
                                    'amount': f"{price}",
                                    'currencyCode': currencyCode,
                                },
                            },
                            'lineComponentsSource': None,
                            'lineComponents': [],
                        },
                    ],
                },
                'payment': {
                    'totalAmount': {'any': True},
                    'paymentLines': [],
                    'billingAddress': {
                        'streetAddress': {
                            'address1': addr["address1"],
                            'city': addr["city"],
                            'countryCode': addr["countryCode"],
                            'postalCode': addr["postalCode"],
                            'firstName': firstName,
                            'lastName': lastName,
                            'zoneCode': addr["zoneCode"],
                            'phone': addr["phone"],
                        },
                    },
                },
                'buyerIdentity': {
                    'customer': {
                        'presentmentCurrency': currencyCode,
                        'countryCode': countryCode,
                    },
                    'email': email,
                    'emailChanged': False,
                    'phoneCountryCode': countryCode,
                    'marketingConsent': [],
                    'shopPayOptInPhone': {'countryCode': countryCode},
                    'rememberMe': False,
                },
                'tip': {'tipLines': []},
                'taxes': {
                    'proposedAllocations': None,
                    'proposedTotalAmount': {
                        'value': {
                            'amount': tax,
                            'currencyCode': currencyCode,
                        },
                    },
                    'proposedTotalIncludedAmount': None,
                    'proposedMixedStateTotalAmount': None,
                    'proposedExemptions': [],
                },
                'note': {'message': None, 'customAttributes': []},
                'localizationExtension': {'fields': []},
                'nonNegotiableTerms': None,
                'scriptFingerprint': {
                    'signature': None,
                    'signatureUuid': None,
                    'lineItemScriptChanges': [],
                    'paymentScriptChanges': [],
                    'shippingScriptChanges': [],
                },
                'optionalDuties': {'buyerRefusesDuties': False},
            },
            'operationName': 'Proposal',
        }

        request = await session.post(f'{url}/checkouts/unstable/graphql', params={'operationName': 'Proposal'}, headers=headers, json=json_data)
        shipping_resp = request.json()

        # Extract shipping info
        try:
            seller_proposal = shipping_resp['data']['session']['negotiate']['result']['sellerProposal']
            delivery_data = seller_proposal.get('delivery', {})
            running_total = seller_proposal.get('runningTotal', {}).get('value', {}).get('amount', str(price))
            
            delivery_strategy = ''
            shipping_amount = '0.00'
            
            if delivery_data and delivery_data.get('__typename') != 'PendingTerms':
                delivery_lines = delivery_data.get('deliveryLines', [{}])
                if delivery_lines:
                    strategies = delivery_lines[0].get('availableDeliveryStrategies', [])
                    if strategies:
                        delivery_strategy = strategies[0].get('handle', '')
                        shipping_amount = strategies[0].get('amount', {}).get('value', {}).get('amount', '0.00')
            
            tax_data = seller_proposal.get('tax', {})
            if tax_data and tax_data.get('__typename') != 'PendingTerms':
                ttax = tax_data.get('totalTaxAmount', {}).get('value', {}).get('amount', '0.00')
            else:
                ttax = tax
                
        except Exception as e:
            delivery_strategy = ''
            shipping_amount = '0.00'
            ttax = tax
            running_total = str(price)

        await asyncio.sleep(0.2)

        # Calculate total
        try:
            total = float(price) + float(shipping_amount) + float(ttax)
        except:
            total = float(price)

        # Submit for completion
        submit_query = 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{code localizedMessage nonLocalizedMessage __typename}__typename}...on Throttled{pollAfter queueToken __typename}...on CheckpointDenied{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token orderStatusPageUrl paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway __typename}__typename}...on ProcessingReceipt{id pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}__typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}'

        submit_data = {
            'query': submit_query,
            'variables': {
                'input': {
                    'sessionInput': {'sessionToken': x_checkout_one_session_token},
                    'queueToken': queue_token,
                    'discounts': {
                        'lines': [],
                        'acceptUnexpectedDiscounts': True,
                    },
                    'delivery': {
                        'deliveryLines': [
                            {
                                'destination': {
                                    'streetAddress': {
                                        'address1': addr["address1"],
                                        'city': addr["city"],
                                        'countryCode': addr["countryCode"],
                                        'postalCode': addr["postalCode"],
                                        'firstName': firstName,
                                        'lastName': lastName,
                                        'zoneCode': addr["zoneCode"],
                                        'phone': addr["phone"],
                                    },
                                },
                                'selectedDeliveryStrategy': {
                                    'deliveryStrategyByHandle': {
                                        'handle': delivery_strategy,
                                        'customDeliveryRate': False,
                                    },
                                    'options': {'phone': addr["phone"]},
                                },
                                'targetMerchandiseLines': {
                                    'lines': [{'stableId': stable_id}],
                                },
                                'deliveryMethodTypes': ['SHIPPING'],
                                'expectedTotalPrice': {
                                    'value': {
                                        'amount': shipping_amount,
                                        'currencyCode': currencyCode,
                                    },
                                },
                                'destinationChanged': False,
                            },
                        ],
                        'noDeliveryRequired': [],
                        'useProgressiveRates': True,
                        'prefetchShippingRatesStrategy': None,
                        'supportsSplitShipping': True,
                    },
                    'deliveryExpectations': {'deliveryExpectationLines': []},
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
                                'quantity': {'items': {'value': 1}},
                                'expectedTotalPrice': {
                                    'value': {
                                        'amount': f"{price}",
                                        'currencyCode': currencyCode,
                                    },
                                },
                                'lineComponentsSource': None,
                                'lineComponents': [],
                            },
                        ],
                    },
                    'payment': {
                        'totalAmount': {'any': True},
                        'paymentLines': [
                            {
                                'paymentMethod': {
                                    'directPaymentMethod': {
                                        'paymentMethodIdentifier': paymentMethodIdentifier,
                                        'sessionId': sessionid,
                                        'billingAddress': {
                                            'streetAddress': {
                                                'address1': addr["address1"],
                                                'city': addr["city"],
                                                'countryCode': addr["countryCode"],
                                                'postalCode': addr["postalCode"],
                                                'firstName': firstName,
                                                'lastName': lastName,
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
                                        'amount': running_total,
                                        'currencyCode': currencyCode,
                                    },
                                },
                                'dueAt': None,
                            },
                        ],
                        'billingAddress': {
                            'streetAddress': {
                                'address1': addr["address1"],
                                'city': addr["city"],
                                'countryCode': addr["countryCode"],
                                'postalCode': addr["postalCode"],
                                'firstName': firstName,
                                'lastName': lastName,
                                'zoneCode': addr["zoneCode"],
                                'phone': addr["phone"],
                            },
                        },
                    },
                    'buyerIdentity': {
                        'customer': {
                            'presentmentCurrency': currencyCode,
                            'countryCode': countryCode,
                        },
                        'email': email,
                        'emailChanged': False,
                        'phoneCountryCode': countryCode,
                        'marketingConsent': [],
                        'shopPayOptInPhone': {'countryCode': countryCode},
                        'rememberMe': False,
                    },
                    'tip': {'tipLines': []},
                    'taxes': {
                        'proposedAllocations': None,
                        'proposedTotalAmount': {
                            'value': {
                                'amount': ttax,
                                'currencyCode': currencyCode,
                            },
                        },
                        'proposedTotalIncludedAmount': None,
                        'proposedMixedStateTotalAmount': None,
                        'proposedExemptions': [],
                    },
                    'note': {'message': None, 'customAttributes': []},
                    'localizationExtension': {'fields': []},
                    'nonNegotiableTerms': None,
                    'scriptFingerprint': {
                        'signature': None,
                        'signatureUuid': None,
                        'lineItemScriptChanges': [],
                        'paymentScriptChanges': [],
                        'shippingScriptChanges': [],
                    },
                    'optionalDuties': {'buyerRefusesDuties': False},
                },
                'attemptToken': str(int(time.time() * 1000)),
                'metafields': [],
                'postPurchaseInquiryResult': None,
                'analytics': None,
            },
            'operationName': 'SubmitForCompletion',
        }

        request = await session.post(f'{url}/checkouts/unstable/graphql', params={'operationName': 'SubmitForCompletion'}, headers=headers, json=submit_data)
        res_text = request.text
        
        try:
            res_json = request.json()
        except:
            res_json = {}

        # Check for payment method unavailable
        if "The requested payment method is not available" in res_text:
            output.update({
                "Response": "PAYMENT_METHOD_UNAVAILABLE",
                "Status": False,
                "Gateway": gateway,
                "Price": total,
            })
            print(json.dumps(output))
            return output

        # Extract receipt ID for polling
        receipt_id = None
        try:
            receipt_id = res_json.get('data', {}).get('submitForCompletion', {}).get('receipt', {}).get('id')
        except:
            pass

        # If we need to poll for result
        if receipt_id and ('ProcessingReceipt' in res_text or 'WaitingReceipt' in res_text):
            poll_query = 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token orderStatusPageUrl paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway __typename}__typename}...on ProcessingReceipt{id pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}__typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}'
            
            for _ in range(5):
                await asyncio.sleep(1.5)
                poll_data = {
                    'query': poll_query,
                    'variables': {
                        'receiptId': receipt_id,
                        'sessionToken': x_checkout_one_session_token,
                    },
                    'operationName': 'PollForReceipt',
                }
                
                request = await session.post(f'{url}/checkouts/unstable/graphql', params={'operationName': 'PollForReceipt'}, headers=headers, json=poll_data)
                res_text = request.text
                try:
                    res_json = request.json()
                except:
                    res_json = {}
                
                if 'ProcessedReceipt' in res_text or 'FailedReceipt' in res_text:
                    break

        # Parse the response
        result = None
        
        # Check for error code
        if 'code' in res_text:
            code_match = capture(res_text, '"code":"', '"')
            if code_match:
                result = code_match

        # Determine response based on result
        if "shopify_payments" in str(res_json) or "ProcessedReceipt" in res_text:
            output.update({
                "Response": "ORDER_PLACED",
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
        elif "INVALID_CVC" in res_text or "INCORRECT_CVC" in res_text or "invalid_cvc" in res_text.lower():
            output.update({
                "Response": "INCORRECT_CVC",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "INCORRECT_NUMBER" in res_text or "incorrect_number" in res_text.lower():
            output.update({
                "Response": "INCORRECT_NUMBER",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "CARD_DECLINED" in res_text or "card_declined" in res_text.lower():
            output.update({
                "Response": "CARD_DECLINED",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "GENERIC_ERROR" in res_text or "generic_error" in res_text.lower():
            output.update({
                "Response": "GENERIC_ERROR",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "AUTHENTICATION_FAILED" in res_text or "authentication_failed" in res_text.lower():
            output.update({
                "Response": "AUTHENTICATION_FAILED",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "FRAUD_SUSPECTED" in res_text or "fraud" in res_text.lower():
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
        elif "INCORRECT_ZIP" in res_text or "incorrect_zip" in res_text.lower():
            output.update({
                "Response": "INCORRECT_ZIP",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "INCORRECT_PIN" in res_text:
            output.update({
                "Response": "MISMATCHED_PIN",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "CompletePaymentChallenge" in res_text or "3ds" in res_text.lower():
            output.update({
                "Response": "3DS_REQUIRED",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "EXPIRED_CARD" in res_text or "expired" in res_text.lower():
            output.update({
                "Response": "EXPIRED_CARD",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "DO_NOT_HONOR" in res_text or "do_not_honor" in res_text.lower():
            output.update({
                "Response": "DO_NOT_HONOR",
                "Status": True,
                "Gateway": gateway,
                "Price": total,
                "cc": card
            })
        elif "LOST_CARD" in res_text or "STOLEN_CARD" in res_text:
            output.update({
                "Response": "LOST_OR_STOLEN_CARD",
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
    async with httpx.AsyncClient() as session:
        await autoshopify("https://example.myshopify.com/", "4111111111111111|12|2025|123", session)


if __name__ == "__main__":
    asyncio.run(main())
