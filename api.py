from time import sleep
import asyncio
import httpx
import re
import json
import time
from urllib.parse import urlparse

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
    "US": {"address1": "123 Main", "city": "NY", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586"},
    "CA": {"address1": "88 Queen", "city": "Toronto", "postalCode": "M5J2J3", "zoneCode": "ON", "countryCode": "CA", "phone": "4165550198"},
    "GB": {"address1": "221B Baker Street", "city": "London", "postalCode": "NW1 6XE", "zoneCode": "LND", "countryCode": "GB", "phone": "2079460123"},
    "IN": {"address1": "221B MG", "city": "Mumbai", "postalCode": "400001", "zoneCode": "MH", "countryCode": "IN", "phone": "9876543210"},
    "AE": {"address1": "Burj Tower", "city": "Dubai", "postalCode": "", "zoneCode": "DU", "countryCode": "AE", "phone": "501234567"},
    "HK": {"address1": "Nathan 88", "city": "Kowloon", "postalCode": "", "zoneCode": "KL", "countryCode": "HK", "phone": "55555555"},
    "CN": {"address1": "8 Zhongguancun Street", "city": "Beijing", "postalCode": "100080", "zoneCode": "BJ", "countryCode": "CN", "phone": "1062512345"},
    "CH": {"address1": "Gotthardstrasse 17", "city": "Schweiz", "postalCode": "6430", "zoneCode": "SZ", "countryCode": "CH", "phone": "445512345"},
    "AU": {"address1": "1 Martin Place", "city": "Sydney", "postalCode": "2000", "zoneCode": "NSW", "countryCode": "AU", "phone": "291234567"},
    "DEFAULT": {"address1": "123 Main", "city": "New York", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586"},
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
                    price = float(variant.get("price", "0"))
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
    except:
        pass
    return None, None

async def autoshopify(url, card, session):

    output = {
        "Response": "UNKNOWN ERROR",
        "Status": False,
    }
    start = time.time()
    
    try:
        # Fix URL format
        if not url.startswith('http'):
            url = f'https://{url}'
        url = url.rstrip('/')
        domain = urlparse(url).netloc
        
        # Parse card
        parts = card.replace(" ", "").split("|")
        if len(parts) != 4:
            output.update({"Response": "INVALID CARD FORMAT", "Status": False})
            print(json.dumps(output))
            return output
        cc, mes, ano, cvv = map(str.strip, parts)
        
        # Fix year format
        if len(ano) == 2:
            ano = '20' + ano

        # Step 1: Get products
        try:
            request = await session.get(f"{url}/products.json", timeout=15)
            product_id, price = get_product_id(request)
        except Exception as e:
            output.update({"Response": f"SITE ERROR", "Status": False})
            print(json.dumps(output))
            return output

        if not product_id:
            output.update({
                "Response": "PRODUCT EMPTY",
                "Status": False,
            })
            print(json.dumps(output))
            return output

        # Step 2: Get site access token
        try:
            request = await session.get(url, timeout=15)
        except:
            output.update({
                "Response": "SITE DEAD",
                "Status": False,
            })
            print(json.dumps(output))
            return output

        site_key = capture(request.text, '"accessToken":"', '"')
        if not site_key:
            site_key = capture(request.text, 'accessToken":"', '"')

        # Step 3: Create cart
        headers = {
            'accept': 'application/json',
            'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
            'content-type': 'application/json',
            'origin': url,
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
            'x-shopify-storefront-access-token': site_key,
        }

        json_data = {
            'query': 'mutation cartCreate($input:CartInput!$country:CountryCode$language:LanguageCode)@inContext(country:$country language:$language){result:cartCreate(input:$input){cart{id checkoutUrl}}}',
            'variables': {
                'input': {
                    'lines': [
                        {
                            'merchandiseId': f'gid://shopify/ProductVariant/{product_id}',
                            'quantity': 1,
                        },
                    ],
                },
                'country': 'US',
                'language': 'EN',
            },
        }

        try:
            request = await session.post(f'{url}/api/unstable/graphql.json', headers=headers, json=json_data, timeout=15)
            data = request.json()
            checkout_url = data["data"]["result"]["cart"]["checkoutUrl"]
        except Exception as e:
            output.update({"Response": "CART ERROR", "Status": False})
            print(json.dumps(output))
            return output

        # Step 4: Go to checkout
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
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

        request = await session.get(checkout_url, headers=headers, params={'skip_shop_pay': 'true'}, follow_redirects=True, timeout=20)
        checkout_text = request.text

        # Extract checkout session data
        paymentMethodIdentifier = capture(checkout_text, "paymentMethodIdentifier&quot;:&quot;", "&quot")
        stable_id = capture(checkout_text, "stableId&quot;:&quot;", "&quot")
        queue_token = capture(checkout_text, "queueToken&quot;:&quot;", "&quot")
        currencyCode = capture(checkout_text, "currencyCode&quot;:&quot;", "&quot") or "USD"
        countryCode = capture(checkout_text, "countryCode&quot;:&quot;", "&quot") or "US"
        x_checkout_one_session_token = capture(checkout_text, 'serialized-session-token" content="&quot;', '&quot')
        token = capture(checkout_text, 'serialized-source-token" content="&quot;', '&quot')
        web_build = capture(checkout_text, 'sha&quot;:&quot;', '&quot')
        
        gateway = capture(checkout_text, 'extensibilityDisplayName&quot;:&quot;', '&quot')
        if gateway == "Shopify Payments":
            gateway = "Normal"
        elif not gateway:
            gateway = "Unknown"

        if not x_checkout_one_session_token:
            await asyncio.sleep(2)
            request = await session.get(str(request.url), headers=headers, follow_redirects=True, timeout=20)
            checkout_text = request.text
            x_checkout_one_session_token = capture(checkout_text, 'serialized-session-token" content="&quot;', '&quot')
            
        if not x_checkout_one_session_token:
            output.update({"Response": "SESSION ERROR", "Status": False})
            print(json.dumps(output))
            return output

        addr = pick_addr(url, cc=currencyCode, rc=countryCode)
        graphql_url = f'{url}/checkouts/unstable/graphql'

        # Step 5: Submit shipping proposal
        headers = {
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
            'x-checkout-one-session-token': x_checkout_one_session_token,
            'x-checkout-web-build-id': web_build or '',
            'x-checkout-web-deploy-stage': 'production',
            'x-checkout-web-source-id': token or '',
        }

        shipping_json = {
            'query': 'query Proposal($sessionInput:SessionTokenInput!,$queueToken:String,$delivery:DeliveryTermsInput,$discounts:DiscountTermsInput,$payment:PaymentTermInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$taxes:TaxTermInput,$tip:TipTermInput,$note:NoteInput,$scriptFingerprint:ScriptFingerprintInput,$optionalDuties:OptionalDutiesInput){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{delivery:$delivery,discounts:$discounts,payment:$payment,merchandise:$merchandise,buyerIdentity:$buyerIdentity,taxes:$taxes,tip:$tip,note:$note,scriptFingerprint:$scriptFingerprint,optionalDuties:$optionalDuties},queueToken:$queueToken}){result{...on NegotiationResultAvailable{queueToken sellerProposal{delivery{...on FilledDeliveryTerms{deliveryLines{availableDeliveryStrategies{handle amount{value{amount currencyCode}}}}}}runningTotal{value{amount currencyCode}}tax{...on FilledTaxTerms{totalTaxAmount{value{amount currencyCode}}}}payment{...on FilledPaymentTerms{availablePaymentLines{paymentMethod{...on PaymentProvider{paymentMethodIdentifier name}}}}}}}}}}}',
            'variables': {
                'sessionInput': {'sessionToken': x_checkout_one_session_token},
                'queueToken': queue_token,
                'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
                'delivery': {
                    'deliveryLines': [{
                        'destination': {
                            'partialStreetAddress': {
                                'address1': addr["address1"],
                                'city': addr["city"],
                                'countryCode': addr["countryCode"],
                                'postalCode': addr["postalCode"],
                                'firstName': 'Laka',
                                'lastName': 'Lama',
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
                        'deliveryMethodTypes': ['SHIPPING', 'LOCAL'],
                        'expectedTotalPrice': {'any': True},
                        'destinationChanged': True,
                    }],
                    'noDeliveryRequired': [],
                    'useProgressiveRates': False,
                    'supportsSplitShipping': True,
                },
                'merchandise': {
                    'merchandiseLines': [{
                        'stableId': stable_id,
                        'merchandise': {
                            'productVariantReference': {
                                'id': f'gid://shopify/ProductVariantMerchandise/{product_id}',
                                'variantId': f'gid://shopify/ProductVariant/{product_id}',
                                'properties': [],
                            }
                        },
                        'quantity': {'items': {'value': 1}},
                        'expectedTotalPrice': {'value': {'amount': str(price), 'currencyCode': currencyCode}},
                        'lineComponents': [],
                    }],
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
                            'firstName': 'Laka',
                            'lastName': 'Lama',
                            'zoneCode': addr["zoneCode"],
                            'phone': addr["phone"],
                        }
                    },
                },
                'buyerIdentity': {
                    'customer': {'presentmentCurrency': currencyCode, 'countryCode': countryCode},
                    'email': 'testcheck@gmail.com',
                    'emailChanged': False,
                    'marketingConsent': [],
                    'rememberMe': False,
                },
                'tip': {'tipLines': []},
                'taxes': {
                    'proposedTotalAmount': {'value': {'amount': '0', 'currencyCode': currencyCode}},
                    'proposedExemptions': [],
                },
                'note': {'customAttributes': []},
                'scriptFingerprint': {'lineItemScriptChanges': [], 'paymentScriptChanges': [], 'shippingScriptChanges': []},
                'optionalDuties': {'buyerRefusesDuties': False},
            },
            'operationName': 'Proposal',
        }

        # First shipping request
        await session.post(graphql_url, headers=headers, json=shipping_json, timeout=20)
        await asyncio.sleep(2)
        
        # Second shipping request to get rates
        request = await session.post(graphql_url, headers=headers, json=shipping_json, timeout=20)
        
        # Extract shipping data
        try:
            shipping_resp = request.json()
            seller_proposal = shipping_resp['data']['session']['negotiate']['result']['sellerProposal']
            total = seller_proposal.get('runningTotal', {}).get('value', {}).get('amount', str(price))
            
            delivery = seller_proposal.get('delivery', {})
            if delivery and 'deliveryLines' in delivery:
                strategies = delivery['deliveryLines'][0].get('availableDeliveryStrategies', [])
                if strategies:
                    handle = strategies[0].get('handle', '')
                    shipping_amount = strategies[0].get('amount', {}).get('value', {}).get('amount', '0')
                else:
                    handle = ''
                    shipping_amount = '0'
            else:
                handle = ''
                shipping_amount = '0'
                
            tax_data = seller_proposal.get('tax', {})
            if tax_data and 'totalTaxAmount' in tax_data:
                tax_amount = tax_data['totalTaxAmount'].get('value', {}).get('amount', '0')
            else:
                tax_amount = '0'
                
        except Exception as e:
            # Use defaults if parsing fails
            total = str(price)
            handle = ''
            shipping_amount = '0'
            tax_amount = '0'

        # Step 6: Get payment token
        pci_headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': 'https://checkout.shopifycs.com',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36'
        }
        
        json_data = {
            'credit_card': {
                'number': cc,
                'month': mes,
                'year': ano,
                'verification_value': cvv,
                'name': 'Laka Lama',
            },
            'payment_session_scope': domain
        }

        try:
            request = await session.post('https://deposit.shopifycs.com/sessions', headers=pci_headers, json=json_data, timeout=15)
            sessionid = request.json()["id"]
        except Exception as e:
            output.update({"Response": "PAYMENT TOKEN ERROR", "Status": False})
            print(json.dumps(output))
            return output

        # Step 7: Submit for completion
        submit_json = {
            'query': 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!){submitForCompletion(input:$input,attemptToken:$attemptToken){...on SubmitSuccess{receipt{...ReceiptDetails}}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails}}...on SubmitFailed{reason}...on SubmitRejected{errors{code localizedMessage}}...on Throttled{pollAfter queueToken}...on SubmittedForCompletion{receipt{...ReceiptDetails}}}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id}...on ProcessingReceipt{id pollDelay}...on WaitingReceipt{id pollDelay}...on ActionRequiredReceipt{id}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated}}}}',
            'variables': {
                'input': {
                    'sessionInput': {'sessionToken': x_checkout_one_session_token},
                    'queueToken': queue_token,
                    'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
                    'delivery': {
                        'deliveryLines': [{
                            'destination': {
                                'streetAddress': {
                                    'address1': addr["address1"],
                                    'city': addr["city"],
                                    'countryCode': addr["countryCode"],
                                    'postalCode': addr["postalCode"],
                                    'firstName': 'Laka',
                                    'lastName': 'Lama',
                                    'zoneCode': addr["zoneCode"],
                                    'phone': addr["phone"],
                                }
                            },
                            'selectedDeliveryStrategy': {
                                'deliveryStrategyByHandle': {'handle': handle, 'customDeliveryRate': False} if handle else {'deliveryStrategyMatchingConditions': {'estimatedTimeInTransit': {'any': True}, 'shipments': {'any': True}}, 'options': {}},
                                'options': {'phone': addr["phone"]} if handle else {},
                            },
                            'targetMerchandiseLines': {'lines': [{'stableId': stable_id}]} if handle else {'any': True},
                            'deliveryMethodTypes': ['SHIPPING'],
                            'expectedTotalPrice': {'value': {'amount': shipping_amount, 'currencyCode': currencyCode}} if handle else {'any': True},
                            'destinationChanged': False,
                        }],
                        'noDeliveryRequired': [],
                        'useProgressiveRates': False,
                        'supportsSplitShipping': True,
                    },
                    'merchandise': {
                        'merchandiseLines': [{
                            'stableId': stable_id,
                            'merchandise': {
                                'productVariantReference': {
                                    'id': f'gid://shopify/ProductVariantMerchandise/{product_id}',
                                    'variantId': f'gid://shopify/ProductVariant/{product_id}',
                                    'properties': [],
                                }
                            },
                            'quantity': {'items': {'value': 1}},
                            'expectedTotalPrice': {'value': {'amount': str(price), 'currencyCode': currencyCode}},
                            'lineComponents': [],
                        }],
                    },
                    'payment': {
                        'totalAmount': {'any': True},
                        'paymentLines': [{
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
                                            'firstName': 'Laka',
                                            'lastName': 'Lama',
                                            'zoneCode': addr["zoneCode"],
                                            'phone': addr["phone"],
                                        }
                                    },
                                },
                            },
                            'amount': {'value': {'amount': total, 'currencyCode': currencyCode}},
                        }],
                        'billingAddress': {
                            'streetAddress': {
                                'address1': addr["address1"],
                                'city': addr["city"],
                                'countryCode': addr["countryCode"],
                                'postalCode': addr["postalCode"],
                                'firstName': 'Laka',
                                'lastName': 'Lama',
                                'zoneCode': addr["zoneCode"],
                                'phone': addr["phone"],
                            }
                        },
                    },
                    'buyerIdentity': {
                        'customer': {'presentmentCurrency': currencyCode, 'countryCode': countryCode},
                        'email': 'testcheck@gmail.com',
                        'emailChanged': False,
                        'marketingConsent': [],
                        'rememberMe': False,
                    },
                    'tip': {'tipLines': []},
                    'taxes': {
                        'proposedTotalAmount': {'value': {'amount': tax_amount, 'currencyCode': currencyCode}},
                        'proposedExemptions': [],
                    },
                    'note': {'customAttributes': []},
                    'scriptFingerprint': {'lineItemScriptChanges': [], 'paymentScriptChanges': [], 'shippingScriptChanges': []},
                    'optionalDuties': {'buyerRefusesDuties': False},
                },
                'attemptToken': f'{token or x_checkout_one_session_token}-submit',
            },
            'operationName': 'SubmitForCompletion',
        }

        request = await session.post(graphql_url, headers=headers, json=submit_json, timeout=30)
        submit_text = request.text

        # Check for captcha or special errors
        if "CAPTCHA" in submit_text:
            output.update({"Response": "CAPTCHA_REQUIRED", "Status": False, "Gateway": gateway, "Price": total, "cc": card})
            print(json.dumps(output))
            return output

        # Get receipt ID
        receipt_id = None
        try:
            submit_resp = request.json()
            receipt_data = submit_resp.get('data', {}).get('submitForCompletion', {}).get('receipt', {})
            receipt_id = receipt_data.get('id')
        except:
            pass

        if not receipt_id:
            # Retry once
            await asyncio.sleep(3)
            request = await session.post(graphql_url, headers=headers, json=submit_json, timeout=30)
            submit_text = request.text
            try:
                submit_resp = request.json()
                receipt_data = submit_resp.get('data', {}).get('submitForCompletion', {}).get('receipt', {})
                receipt_id = receipt_data.get('id')
            except:
                pass

        if not receipt_id:
            # Check for inline error
            if "CARD_DECLINED" in submit_text:
                output.update({"Response": "CARD_DECLINED", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
            elif "INCORRECT_NUMBER" in submit_text:
                output.update({"Response": "INCORRECT_NUMBER", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
            elif "INVALID_CVC" in submit_text or "INCORRECT_CVC" in submit_text:
                output.update({"Response": "INCORRECT_CVC", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
            else:
                output.update({"Response": "SUBMIT ERROR", "Status": False, "Gateway": gateway, "Price": total, "cc": card})
            print(json.dumps(output))
            return output

        # Step 8: Poll for receipt
        await asyncio.sleep(3)

        poll_json = {
            'query': 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id}...on ProcessingReceipt{id pollDelay}...on WaitingReceipt{id pollDelay}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{url}...on CompletePaymentChallengeV2{challengeType}}}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated}}}}',
            'variables': {
                'receiptId': receipt_id,
                'sessionToken': x_checkout_one_session_token,
            },
            'operationName': 'PollForReceipt',
        }

        final_text = ""
        for i in range(3):
            request = await session.post(graphql_url, headers=headers, json=poll_json, timeout=20)
            final_text = request.text

            if 'WaitingReceipt' not in final_text and 'ProcessingReceipt' not in final_text:
                break
            await asyncio.sleep(4)

        end = time.time()
        timetaken = end - start

        # Parse final result
        result = None
        try:
            res_json = request.json()
            result = res_json.get('data', {}).get('receipt', {}).get('processingError', {}).get('code')
        except:
            pass

        # Determine response
        if "ProcessedReceipt" in final_text and "processingError" not in final_text:
            output.update({"Response": "ORDER_PLACED", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
        elif result == 'CARD_DECLINED':
            output.update({"Response": "CARD_DECLINED", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
        elif result == 'INCORRECT_NUMBER':
            output.update({"Response": "INCORRECT_NUMBER", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
        elif result == 'GENERIC_ERROR':
            output.update({"Response": "GENERIC_ERROR", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
        elif result == 'AUTHENTICATION_FAILED':
            output.update({"Response": "AUTHENTICATION_FAILED", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
        elif "FRAUD_SUSPECTED" in final_text:
            output.update({"Response": "FRAUD_SUSPECTED", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
        elif "INCORRECT_ADDRESS" in final_text:
            output.update({"Response": "INCORRECT_ADDRESS", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
        elif "INCORRECT_ZIP" in final_text:
            output.update({"Response": "INCORRECT_ZIP", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
        elif "INCORRECT_PIN" in final_text:
            output.update({"Response": "INCORRECT_PIN", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
        elif "insufficient_funds" in final_text.lower() or "INSUFFICIENT_FUNDS" in final_text:
            output.update({"Response": "INSUFFICIENT_FUNDS", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
        elif "INVALID_CVC" in final_text or "INCORRECT_CVC" in final_text:
            output.update({"Response": "INCORRECT_CVC", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
        elif "CompletePaymentChallenge" in final_text or "ActionRequiredReceipt" in final_text:
            output.update({"Response": "3DS_REQUIRED", "Status": True, "Gateway": gateway, "Price": total, "cc": card})
        elif result:
            output.update({"Response": result, "Status": True, "Gateway": gateway, "Price": total, "cc": card})
        else:
            output.update({"Response": "UNKNOWN", "Status": True, "Gateway": gateway, "Price": total, "cc": card})

    except Exception as e:
        output.update({"Response": str(e), "Status": False})

    print(json.dumps(output))
    return output
