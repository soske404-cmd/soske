"""
Shopify GraphQL Checkout API
Converted from working shopify_terminal to api.py style
Uses httpx, function-based approach with real checkout flow
"""

import asyncio
import httpx
import json
import time
import random
import string
import re
from urllib.parse import urlparse


def capture(data, first, last):
    """Extract text between two strings"""
    try:
        start = data.index(first) + len(first)
        end = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None


def get_product_id(response_data):
    """Get cheapest available product from store"""
    try:
        products_data = response_data.get("products", [])
        products = {}
        
        for product in products_data:
            variants = product.get("variants", [])
            for variant in variants:
                product_id = variant.get("id")
                available = variant.get("available", False)
                try:
                    price = variant.get("price", "0")
                    if isinstance(price, str):
                        price = float(price.replace(",", ""))
                    else:
                        price = float(price)
                except (ValueError, TypeError):
                    continue
                    
                if price < 0.1:
                    continue
                if available:
                    products[product_id] = price
                    
        if products:
            min_price_product_id = min(products, key=products.get)
            price = products[min_price_product_id]
            return str(min_price_product_id), price

        return None, None
    except Exception:
        return None, None


def generate_random_name():
    """Generate random first and last name"""
    first_names = ['John', 'James', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph', 'Thomas', 'Charles']
    last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
    return random.choice(first_names), random.choice(last_names)


def generate_email(first_name, last_name):
    """Generate random email"""
    domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com']
    random_num = ''.join(random.choices(string.digits, k=3))
    return f"{first_name.lower()}.{last_name.lower()}{random_num}@{random.choice(domains)}"


def generate_address():
    """Generate random US address"""
    streets = ['123 Main St', '456 Oak Ave', '789 Pine Rd', '321 Elm St', '654 Maple Dr']
    cities = ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix']
    states = ['NY', 'CA', 'IL', 'TX', 'AZ']
    zips = ['10001', '90001', '60601', '77001', '85001']
    phones = ['2125551234', '3235551234', '3125551234', '7135551234', '6025551234']
    
    idx = random.randint(0, 4)
    return {
        'street': random.choice(streets),
        'city': cities[idx],
        'state': states[idx],
        'zip': zips[idx],
        'phone': random.choice(phones)
    }


async def autoshopify(url, card, session):
    """
    Main Shopify GraphQL checkout function
    
    Args:
        url: Shopify store URL (e.g., "https://example.com")
        card: Card details in format "cc|mm|yy|cvv"
        session: httpx.AsyncClient session
        
    Returns:
        dict with Response, Status, Gateway, Price, cc
    """
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
        
        # Clean URL
        url = url.rstrip('/')
        if not url.startswith('http'):
            url = f"https://{url}"
        
        domain = urlparse(url).netloc
        base_url = url
        
        # Generate random buyer info
        firstName, lastName = generate_random_name()
        email = generate_email(firstName, lastName)
        address_data = generate_address()
        
        street = address_data['street']
        city = address_data['city']
        state = address_data['state']
        s_zip = address_data['zip']
        phone = address_data['phone']
        address2 = ""
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Content-Type': 'application/json',
        }
        
        # Step 1: Get products
        try:
            resp = await session.get(f"{base_url}/products.json", headers=headers, timeout=15.0)
            data = resp.json()
            variant_id, price = get_product_id(data)
        except Exception as e:
            output.update({"Response": f"PRODUCTS ERROR: {str(e)}", "Status": False})
            print(json.dumps(output))
            return output
        
        if not variant_id:
            output.update({"Response": "NO PRODUCTS AVAILABLE", "Status": False})
            print(json.dumps(output))
            return output
        
        merch = variant_id
        subtotal = str(price)
        
        # Step 2: Add to cart
        cart_url = f"{base_url}/cart/add.js"
        await session.post(cart_url, json={'id': variant_id}, headers=headers, timeout=15.0)
        
        # Step 3: Go to checkout
        checkout_url = f"{base_url}/checkout/"
        resp = await session.post(checkout_url, headers=headers, follow_redirects=True, timeout=15.0)
        checkout_url = str(resp.url)
        
        if 'login' in checkout_url.lower():
            output.update({"Response": "SITE REQUIRES LOGIN", "Status": False})
            print(json.dumps(output))
            return output
        
        # Get checkout page
        resp = await session.get(checkout_url, headers=headers, timeout=15.0)
        text = resp.text
        
        # Extract session token
        sst = capture(text, 'name="serialized-session-token" content="&quot;', '&q')
        if not sst:
            await asyncio.sleep(2)
            resp = await session.get(checkout_url, headers=headers, timeout=15.0)
            text = resp.text
            sst = capture(text, 'name="serialized-session-token" content="&quot;', '&q')
        
        if not sst:
            output.update({"Response": "NO SESSION TOKEN", "Status": False})
            print(json.dumps(output))
            return output
        
        # Extract other required data
        queueToken = capture(text, 'queueToken&quot;:&quot;', '&q')
        stableId = capture(text, 'stableId&quot;:&quot;', '&q')
        sourceToken = capture(text, 'serialized-source-token" content="&quot;', '&q')
        
        # Get currency
        pattern = r'currencycode\s*[:=]\s*["\']?([^"\']+)["\']?'
        currency_match = re.search(pattern, text.lower())
        currency = currency_match.group(1).upper() if currency_match else 'USD'
        
        # Get payment method info
        payment_name = capture(text, 'paymentMethodName&quot;:&quot;', '&q') or "credit_card"
        gateway = capture(text, 'extensibilityDisplayName&quot;:&quot;', '&q') or "Unknown"
        
        graphql_url = f"https://{domain}/checkouts/unstable/graphql"
        
        # Calculate amounts
        try:
            shipping_amount = "0.00"
            tax_amount = "0.00"
            running_total = str(price)
        except:
            running_total = subtotal
        
        # Get delivery strategy
        delivery_strategy = capture(text, 'handle&quot;:&quot;', '&q') or ""
        
        # GraphQL Headers
        graphql_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': base_url,
            'Referer': checkout_url,
        }
        
        # STEP 1: SHIPPING PROPOSAL
        shipping_json = {
            'query': 'query Proposal($alternativePaymentCurrency:AlternativePaymentCurrencyInput,$delivery:DeliveryTermsInput,$discounts:DiscountTermsInput,$payment:PaymentTermInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$taxes:TaxTermInput,$sessionInput:SessionTokenInput!,$checkpointData:String,$queueToken:String,$reduction:ReductionInput,$availableRedeemables:AvailableRedeemablesInput,$changesetTokens:[String!],$tip:TipTermInput,$note:NoteInput,$localizationExtension:LocalizationExtensionInput,$nonNegotiableTerms:NonNegotiableTermsInput,$scriptFingerprint:ScriptFingerprintInput,$transformerFingerprintV2:String,$optionalDuties:OptionalDutiesInput,$attribution:AttributionInput,$captcha:CaptchaInput,$poNumber:String,$saleAttributions:SaleAttributionsInput){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{alternativePaymentCurrency:$alternativePaymentCurrency,delivery:$delivery,discounts:$discounts,payment:$payment,merchandise:$merchandise,buyerIdentity:$buyerIdentity,taxes:$taxes,reduction:$reduction,availableRedeemables:$availableRedeemables,tip:$tip,note:$note,poNumber:$poNumber,nonNegotiableTerms:$nonNegotiableTerms,localizationExtension:$localizationExtension,scriptFingerprint:$scriptFingerprint,transformerFingerprintV2:$transformerFingerprintV2,optionalDuties:$optionalDuties,attribution:$attribution,captcha:$captcha,saleAttributions:$saleAttributions},checkpointData:$checkpointData,queueToken:$queueToken,changesetTokens:$changesetTokens}){__typename result{...on NegotiationResultAvailable{checkpointData queueToken buyerProposal{...BuyerProposalDetails __typename}sellerProposal{...ProposalDetails __typename}__typename}...on CheckpointDenied{redirectUrl __typename}...on Throttled{pollAfter queueToken pollUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}...on NegotiationResultFailed{__typename}__typename}errors{code localizedMessage nonLocalizedMessage localizedMessageHtml...on RemoveTermViolation{target __typename}...on AcceptNewTermViolation{target __typename}...on ConfirmChangeViolation{from to __typename}...on UnprocessableTermViolation{target __typename}...on UnresolvableTermViolation{target __typename}...on ApplyChangeViolation{target from{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}to{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}__typename}...on GenericError{__typename}...on PendingTermViolation{__typename}__typename}}__typename}}fragment BuyerProposalDetails on Proposal{buyerIdentity{...on FilledBuyerIdentityTerms{email phone customer{...on CustomerProfile{email __typename}...on BusinessCustomerProfile{email __typename}__typename}__typename}__typename}merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}delivery{...ProposalDeliveryFragment __typename}merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}components{...MerchandiseLineComponentWithCapabilities __typename}legacyFee __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}__typename}fragment ProposalDiscountFragment on DiscountTermsV2{__typename...on FilledDiscountTerms{acceptUnexpectedDiscounts lines{...DiscountLineDetailsFragment __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment DiscountLineDetailsFragment on DiscountLine{allocations{...on DiscountAllocatedAllocationSet{__typename allocations{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}target{index targetType stableId __typename}__typename}}__typename}discount{...DiscountDetailsFragment __typename}lineAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}fragment DiscountDetailsFragment on Discount{...on CustomDiscount{title description presentationLevel allocationMethod targetSelection targetType signature signatureUuid type value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on CodeDiscount{title code presentationLevel allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on DiscountCodeTrigger{code __typename}...on AutomaticDiscount{presentationLevel title allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}fragment ProposalDeliveryFragment on DeliveryTerms{__typename...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken deliveryLines{destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType deliveryMethodTypes selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}...on DeliveryStrategyReference{handle __typename}__typename}availableDeliveryStrategies{...on CompleteDeliveryStrategy{title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms brandedPromise{logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName name handle carrierLogoUrl distanceFromSearchLocation{unit value __typename}__typename}__typename}__typename}...on DeliveryStrategyReference{handle __typename}__typename}__typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment FilledMerchandiseLineTargetCollectionFragment on FilledMerchandiseLineTargetCollection{lines{stableId __typename}__typename}fragment SourceProvidedMerchandise on SourceProvidedMerchandise{__typename}fragment ProductVariantMerchandiseDetails on ProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle product{id title untranslatedTitle vendor productType __typename}image{altText url __typename}properties{name value __typename}requiresShipping options{name value __typename}sellingPlan{id name deliveriesPerBillingCycle prepaid digest recurringDeliveries subscriptionDetails{billingInterval billingIntervalCount deliveryInterval deliveryIntervalCount billingMaxCycles __typename}__typename}giftCard sku price{amount currencyCode __typename}deferredAmount{amount currencyCode __typename}taxable taxCode __typename}fragment ContextualizedProductVariantMerchandiseDetails on ContextualizedProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle product{id title untranslatedTitle vendor productType __typename}image{altText url __typename}properties{name value __typename}requiresShipping options{name value __typename}sellingPlan{id name deliveriesPerBillingCycle prepaid digest recurringDeliveries subscriptionDetails{billingInterval billingIntervalCount deliveryInterval deliveryIntervalCount billingMaxCycles __typename}__typename}giftCard sku price{amount currencyCode __typename}deferredAmount{amount currencyCode __typename}taxable taxCode __typename}fragment LineAllocationDetails on LineAllocation{stableId quantity totalAmountBeforeReductions{amount currencyCode __typename}totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}discountAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}__typename}__typename}fragment MerchandiseBundleLineComponent on MerchandiseBundleLineComponent{stableId merchandise{...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails __typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}lineAllocations{...LineAllocationDetails __typename}__typename}fragment MerchandiseLineComponentWithCapabilities on MerchandiseLineComponentWithCapabilities{stableId componentCapabilities componentSource merchandise{...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails __typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}lineAllocations{...LineAllocationDetails __typename}__typename}fragment ProposalDetails on Proposal{delivery{...ProposalDeliveryFragment __typename}payment{...on FilledPaymentTerms{availablePaymentMethods{type methodTypes __typename}billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}paymentLines{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt instruction{...on PaymentInstruction{amount{amount currencyCode __typename}paymentMethodIdentifier paymentMethodTypes __typename}__typename}paymentMethod{...on AnyDirectPaymentMethod{availablePaymentMethodTypes __typename}...on DirectPaymentMethod{paymentMethodIdentifier __typename}...on GiftCardPaymentMethod{code __typename}...on WalletsPlatformConfiguration{name walletParams __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}sessionToken paymentMethodIdentifier __typename}...on PaypalWalletContent{payerId token billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}__typename}...on ApplePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}data signature version __typename}...on GooglePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}signature signedMessage protocolVersion __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}containerData containerId mode __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken creditCard{brand lastDigits __typename}__typename}__typename}__typename}...on LocalPaymentMethod{paymentMethodIdentifier displayName name __typename}...on OffsitePaymentMethod{paymentMethodIdentifier name __typename}...on ManualPaymentMethod{id name paymentInstructions additionalDetails __typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name __typename}...on PaymentOnDeliveryMethod{paymentMethodIdentifier additionalDetails paymentInstructions displayName __typename}...on CustomPaymentMethod{id name paymentInstructions additionalDetails __typename}...on DeferredPaymentMethod{displayName orderingIndex __typename}...on NoopPaymentMethod{__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}paymentFlexibilityPaymentTermsTemplates{id translatedName dueDate dueInDays __typename}checkoutTotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}__typename}buyerIdentity{...on FilledBuyerIdentityTerms{email phone customer{...on CustomerProfile{email id fullName firstName lastName imageUrl acceptsMarketing acceptsSmsMarketing __typename}...on BusinessCustomerProfile{email id fullName firstName lastName imageUrl acceptsMarketing acceptsSmsMarketing ordersCount companyName __typename}__typename}__typename}__typename}taxes{...on FilledTaxTerms{totalTaxAmount{amount currencyCode __typename}totalTaxAndDutyAmount{amount currencyCode __typename}totalDutyAmount{amount currencyCode __typename}totalAmountIncludedInTarget{amount currencyCode __typename}taxLines{amount{amount currencyCode __typename}rate title channelLiable priceIncludesTax __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}__typename}tip{tipLines{amount{amount currencyCode __typename}__typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}note{customAttributes{key value __typename}message __typename}poNumber __typename}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token poNumber orderIdentity{buyerIdentifier id __typename}__typename}...on ProcessingReceipt{id pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}__typename}__typename}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted __typename}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated __typename}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}__typename}__typename}__typename}',
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
                                    'address1': street,
                                    'address2': address2,
                                    'city': city,
                                    'countryCode': 'US',
                                    'postalCode': s_zip,
                                    'firstName': firstName,
                                    'lastName': lastName,
                                    'zoneCode': state,
                                    'phone': phone,
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
                'deliveryExpectations': {
                    'deliveryExpectationLines': [],
                },
                'merchandise': {
                    'merchandiseLines': [
                        {
                            'stableId': stableId,
                            'merchandise': {
                                'productVariantReference': {
                                    'id': f'gid://shopify/ProductVariantMerchandise/{merch}',
                                    'variantId': f'gid://shopify/ProductVariant/{variant_id}',
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
                                    'amount': subtotal,
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
                    'billingAddress': {
                        'streetAddress': {
                            'address1': street,
                            'address2': address2,
                            'city': city,
                            'countryCode': 'US',
                            'postalCode': s_zip,
                            'firstName': firstName,
                            'lastName': lastName,
                            'zoneCode': state,
                            'phone': phone,
                        },
                    },
                },
                'buyerIdentity': {
                    'customer': {
                        'presentmentCurrency': currency,
                        'countryCode': 'US',
                    },
                    'email': email,
                    'emailChanged': False,
                    'phoneCountryCode': 'US',
                    'marketingConsent': [
                        {
                            'email': {
                                'value': email,
                            },
                        },
                    ],
                    'shopPayOptInPhone': {
                        'number': phone,
                        'countryCode': 'US',
                    },
                    'rememberMe': False,
                },
                'tip': {
                    'tipLines': [],
                },
                'taxes': {
                    'proposedAllocations': None,
                    'proposedTotalAmount': None,
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
        
        # Submit shipping proposal
        resp = await session.post(graphql_url, json=shipping_json, headers=graphql_headers, timeout=30.0)
        shipping_resp = resp.json()
        
        # Extract delivery handle and shipping cost
        try:
            delivery_lines = shipping_resp['data']['session']['negotiate']['result']['sellerProposal']['delivery']['deliveryLines']
            if delivery_lines:
                strategies = delivery_lines[0].get('availableDeliveryStrategies', [])
                if strategies:
                    delivery_strategy = strategies[0].get('handle', '')
                    breakdown = strategies[0].get('deliveryStrategyBreakdown', [])
                    if breakdown:
                        shipping_amount = breakdown[0].get('amount', {}).get('value', {}).get('amount', '0.00')
        except:
            pass
        
        # Get updated queue token
        try:
            queueToken = shipping_resp['data']['session']['negotiate']['result'].get('queueToken', queueToken)
        except:
            pass
        
        # Calculate running total
        try:
            running_total = str(float(subtotal) + float(shipping_amount))
        except:
            running_total = subtotal
        
        # STEP 2: TOKENIZE CARD
        vault_headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': 'https://checkout.shopifycs.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        
        # Format card number with spaces (required by Shopify)
        formatted_card = " ".join([cc[i:i+4] for i in range(0, len(cc), 4)])
        
        vault_json = {
            'credit_card': {
                'number': formatted_card,
                'name': f'{firstName} {lastName}',
                'month': mes,
                'year': ano,
                'verification_value': cvv,
            },
            'payment_session_scope': domain,
        }
        
        resp = await session.post('https://deposit.shopifycs.com/sessions', json=vault_json, headers=vault_headers, timeout=15.0)
        
        try:
            vault_resp = resp.json()
            payment_session_id = vault_resp.get('id')
        except:
            payment_session_id = None
        
        if not payment_session_id:
            output.update({"Response": "CARD TOKENIZATION FAILED", "Status": False, "Gateway": gateway})
            print(json.dumps(output))
            return output
        
        # STEP 3: SUBMIT FOR COMPLETION
        completion_json = {
            'query': 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{buyerProposal{...BuyerProposalDetails __typename}sellerProposal{...ProposalDetails __typename}errors{...on NegotiationError{code localizedMessage nonLocalizedMessage localizedMessageHtml...on RemoveTermViolation{message{code localizedDescription __typename}target __typename}...on AcceptNewTermViolation{message{code localizedDescription __typename}target __typename}...on ConfirmChangeViolation{message{code localizedDescription __typename}from to __typename}...on UnprocessableTermViolation{message{code localizedDescription __typename}target __typename}...on UnresolvableTermViolation{message{code localizedDescription __typename}target __typename}...on ApplyChangeViolation{message{code localizedDescription __typename}target from{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}to{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}__typename}...on InputValidationError{field __typename}...on PendingTermViolation{__typename}__typename}__typename}__typename}...on Throttled{pollAfter pollUrl queueToken buyerProposal{...BuyerProposalDetails __typename}__typename}...on CheckpointDenied{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl confirmationPage{url shouldRedirect __typename}orderStatusPageUrl shopPay shopPayInstallments paymentExtensionBrand analytics{checkoutCompletedEventId emitConversionEvent __typename}poNumber orderIdentity{buyerIdentifier id __typename}customerId isFirstOrder eligibleForMarketingOptIn purchaseOrder{...ReceiptPurchaseOrder __typename}orderCreationStatus{__typename}paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway financialPendingReason paymentDescriptor buyerActionInfo{...on MultibancoBuyerActionInfo{entity reference __typename}__typename}__typename}shopAppLinksAndResources{mobileUrl qrCodeUrl canTrackOrderUpdates shopInstallmentsViewSchedules shopInstallmentsMobileUrl installmentsHighlightEligible mobileUrlAttributionPayload shopAppEligible shopAppQrCodeKillswitch shopPayOrder payEscrowMayExist buyerHasShopApp buyerHasShopPay orderUpdateOptions __typename}postPurchasePageUrl postPurchasePageRequested postPurchaseVaultedPaymentMethodStatus paymentFlexibilityPaymentTermsTemplate{__typename dueDate dueInDays id translatedName type}__typename}...on ProcessingReceipt{id purchaseOrder{...ReceiptPurchaseOrder __typename}pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted __typename}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}__typename}__typename}__typename}fragment ReceiptPurchaseOrder on PurchaseOrder{__typename sessionToken totalAmountToPay{amount currencyCode __typename}checkoutCompletionTarget delivery{...on PurchaseOrderDeliveryTerms{splitShippingToggle deliveryLines{__typename availableOn deliveryStrategy{handle title description methodType brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl lightThemeCompactLogoUrl darkThemeCompactLogoUrl name __typename}pickupLocation{...on PickupInStoreLocation{name address{address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}instructions __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}carrierCode carrierName name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyBreakdown{__typename amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice flatRateGroupId targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}...on PurchaseOrderLineComponent{stableId quantity componentCapabilities componentSource merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}lineAmount{amount currencyCode __typename}lineAmountAfterDiscounts{amount currencyCode __typename}destinationAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}__typename}groupType targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}...on PurchaseOrderLineComponent{stableId componentCapabilities componentSource quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}__typename}deliveryExpectations{__typename brandedPromise{name logoUrl handle lightThemeLogoUrl darkThemeLogoUrl __typename}deliveryStrategyHandle deliveryExpectationPresentmentTitle{short long __typename}returnability{returnable __typename}}payment{...on PurchaseOrderPaymentTerms{billingAddress{__typename...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}}paymentLines{amount{amount currencyCode __typename}postPaymentMessage dueAt due{...on PaymentLineDueEvent{event __typename}...on PaymentLineDueTime{time __typename}__typename}paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier vaultingAgreement creditCard{brand lastDigits __typename}billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomerCreditCardPaymentMethod{id brand displayLastDigits token deletable defaultPaymentMethod requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on PurchaseOrderGiftCardPaymentMethod{balance{amount currencyCode __typename}code __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier paymentMethod paymentAttributes __typename}...on PaypalWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token expiresAt __typename}...on ApplePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}data signature version __typename}...on GooglePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}signature signedMessage protocolVersion __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}containerData containerId mode __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken creditCard{brand lastDigits __typename}__typename}__typename}__typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on LocalPaymentMethod{paymentMethodIdentifier name displayName billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on OffsitePaymentMethod{paymentMethodIdentifier name billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on ManualPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on PaypalBillingAgreementPaymentMethod{token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{redemptionPaymentOptionKind billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionId details{redemptionId sourceAmount{amount currencyCode __typename}destinationAmount{amount currencyCode __typename}redemptionType __typename}__typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}__typename}__typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name __typename}__typename}__typename}__typename}__typename}buyerIdentity{...on PurchaseOrderBuyerIdentityTerms{contactMethod{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}marketingConsent{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}__typename}customer{__typename...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}__typename}...on DecodedCustomerProfile{id presentmentCurrency fullName firstName lastName countryCode email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone __typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl email ordersCount phone market{id handle __typename}__typename}}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name __typename}__typename}__typename}merchandise{taxesIncluded merchandiseLines{stableId legacyFee merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}lineComponents{...PurchaseOrderBundleLineComponent __typename}components{...PurchaseOrderLineComponent __typename}quantity{__typename...on PurchaseOrderMerchandiseQuantityByItem{items __typename}}recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}lineAmount{__typename amount currencyCode}__typename}__typename}tax{totalTaxAmountV2{__typename amount currencyCode}totalDutyAmount{amount currencyCode __typename}totalTaxAndDutyAmount{amount currencyCode __typename}totalAmountIncludedInTarget{amount currencyCode __typename}__typename}discounts{lines{...PurchaseOrderDiscountLineFragment __typename}__typename}legacyRepresentProductsAsFees totalSavings{amount currencyCode __typename}subtotalBeforeTaxesAndShipping{amount currencyCode __typename}legacySubtotalBeforeTaxesShippingAndFees{amount currencyCode __typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}dutiesIncluded tip{tipLines{amount{amount currencyCode __typename}__typename}__typename}hasOnlyDeferredShipping note{customAttributes{key value __typename}message __typename}shopPayArtifact{optIn{vaultPhone __typename}__typename}recurringTotals{fixedPrice{amount currencyCode __typename}fixedPriceCount interval intervalCount recurringPrice{amount currencyCode __typename}title __typename}checkoutTotalBeforeTaxesAndShipping{__typename amount currencyCode}checkoutTotal{__typename amount currencyCode}checkoutTotalTaxes{__typename amount currencyCode}subtotalBeforeReductions{__typename amount currencyCode}subtotalAfterMerchandiseDiscounts{__typename amount currencyCode}deferredTotal{amount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}dueAt subtotalAmount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}taxes{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}__typename}metafields{key namespace value valueType:type __typename}}fragment ProductVariantSnapshotMerchandiseDetails on ProductVariantSnapshot{variantId options{name value __typename}productTitle title productUrl untranslatedTitle untranslatedSubtitle sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}deferredAmount{amount currencyCode __typename}digest giftCard image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}price{amount currencyCode __typename}productId productType properties{...MerchandiseProperties __typename}requiresShipping sku taxCode taxable vendor weight{unit value __typename}__typename}fragment MerchandiseProperties on MerchandiseProperty{name value{...on MerchandisePropertyValueString{string:value __typename}...on MerchandisePropertyValueInt{int:value __typename}...on MerchandisePropertyValueFloat{float:value __typename}...on MerchandisePropertyValueBoolean{boolean:value __typename}...on MerchandisePropertyValueJson{json:value __typename}__typename}visible __typename}fragment DiscountDetailsFragment on Discount{...on CustomDiscount{title description presentationLevel allocationMethod targetSelection targetType signature signatureUuid type value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on CodeDiscount{title code presentationLevel allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on DiscountCodeTrigger{code __typename}...on AutomaticDiscount{presentationLevel title allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}fragment PurchaseOrderBundleLineComponent on PurchaseOrderBundleLineComponent{stableId merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}quantity recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}totalAmount{__typename amount currencyCode}__typename}fragment PurchaseOrderLineComponent on PurchaseOrderLineComponent{stableId componentCapabilities componentSource merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}quantity recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}totalAmount{__typename amount currencyCode}__typename}fragment PurchaseOrderDiscountLineFragment on PurchaseOrderDiscountLine{discount{...DiscountDetailsFragment __typename}lineAmount{amount currencyCode __typename}deliveryAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}merchandiseAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}__typename}fragment BuyerProposalDetails on Proposal{__typename}fragment ProposalDetails on Proposal{__typename}',
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
                                        'address1': street,
                                        'address2': address2,
                                        'city': city,
                                        'countryCode': 'US',
                                        'postalCode': s_zip,
                                        'firstName': firstName,
                                        'lastName': lastName,
                                        'zoneCode': state,
                                        'phone': phone,
                                    },
                                },
                                'selectedDeliveryStrategy': {
                                    'deliveryStrategyByHandle': {
                                        'handle': delivery_strategy,
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
                                    'SHIPPING',
                                ],
                                'expectedTotalPrice': {
                                    'value': {
                                        'amount': shipping_amount,
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
                    'deliveryExpectations': {
                        'deliveryExpectationLines': [],
                    },
                    'merchandise': {
                        'merchandiseLines': [
                            {
                                'stableId': stableId,
                                'merchandise': {
                                    'productVariantReference': {
                                        'id': f'gid://shopify/ProductVariantMerchandise/{merch}',
                                        'variantId': f'gid://shopify/ProductVariant/{variant_id}',
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
                                        'amount': subtotal,
                                        'currencyCode': currency,
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
                            'value': {
                                'amount': running_total,
                                'currencyCode': currency,
                            },
                        },
                        'paymentLines': [
                            {
                                'paymentMethod': {
                                    'directPaymentMethod': {
                                        'paymentMethodIdentifier': payment_name,
                                        'sessionId': payment_session_id,
                                        'billingAddress': {
                                            'streetAddress': {
                                                'address1': street,
                                                'address2': address2,
                                                'city': city,
                                                'countryCode': 'US',
                                                'postalCode': s_zip,
                                                'firstName': firstName,
                                                'lastName': lastName,
                                                'zoneCode': state,
                                                'phone': phone,
                                            },
                                        },
                                        'cardSource': None,
                                    },
                                },
                                'amount': {
                                    'value': {
                                        'amount': running_total,
                                        'currencyCode': currency,
                                    },
                                },
                            },
                        ],
                        'billingAddress': {
                            'streetAddress': {
                                'address1': street,
                                'address2': address2,
                                'city': city,
                                'countryCode': 'US',
                                'postalCode': s_zip,
                                'firstName': firstName,
                                'lastName': lastName,
                                'zoneCode': state,
                                'phone': phone,
                            },
                        },
                    },
                    'buyerIdentity': {
                        'customer': {
                            'presentmentCurrency': currency,
                            'countryCode': 'US',
                        },
                        'email': email,
                        'emailChanged': False,
                        'phoneCountryCode': 'US',
                        'marketingConsent': [],
                        'shopPayOptInPhone': {
                            'countryCode': 'US',
                        },
                        'rememberMe': False,
                    },
                    'tip': {
                        'tipLines': [],
                    },
                    'taxes': {
                        'proposedAllocations': None,
                        'proposedTotalAmount': None,
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
                'attemptToken': f'{sourceToken or sst}-attempt1',
                'metafields': [],
                'analytics': None,
            },
            'operationName': 'SubmitForCompletion',
        }
        
        resp = await session.post(graphql_url, json=completion_json, headers=graphql_headers, timeout=30.0)
        completion_resp = resp.json()
        
        # Get receipt ID
        receipt_id = None
        try:
            receipt_id = completion_resp['data']['submitForCompletion']['receipt']['id']
        except:
            pass
        
        # STEP 4: POLL FOR RECEIPT
        if receipt_id:
            poll_json = {
                'query': 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId sessionToken:$sessionToken){...on ProcessedReceipt{id token redirectUrl orderStatusPageUrl __typename}...on ProcessingReceipt{id pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted __typename}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}__typename}__typename}__typename}}',
                'variables': {
                    'receiptId': receipt_id,
                    'sessionToken': sst,
                },
                'operationName': 'PollForReceipt',
            }
            
            for i in range(3):
                resp = await session.post(graphql_url, json=poll_json, headers=graphql_headers, timeout=30.0)
                text = resp.text
                
                if 'WaitingReceipt' not in text:
                    break
                
                await asyncio.sleep(5)
        else:
            text = json.dumps(completion_resp)
        
        # Parse result
        end = time.time()
        
        # Determine response
        if 'actionreq' in text.lower() or 'ActionRequiredReceipt' in text:
            output.update({
                "Response": "3DS_REQUIRED",
                "Status": True,
                "Gateway": gateway,
                "Price": running_total,
                "cc": card
            })
        elif 'processingerror' not in text.lower() and 'ProcessedReceipt' in text:
            output.update({
                "Response": "ORDER_PLACED",
                "Status": True,
                "Gateway": gateway,
                "Price": running_total,
                "cc": card
            })
        else:
            # Extract error code
            code = capture(text, '"code":"', '"')
            if not code:
                try:
                    code = resp.json()['data']['receipt']['processingError']['code']
                except:
                    code = "UNKNOWN"
            
            # Check for specific responses
            text_lower = text.lower()
            if 'insuff' in text_lower or 'funds' in text_lower:
                output.update({
                    "Response": "INSUFFICIENT_FUNDS",
                    "Status": True,
                    "Gateway": gateway,
                    "Price": running_total,
                    "cc": card
                })
            elif 'invalid_cvc' in text_lower or 'incorrect_cvc' in text_lower:
                output.update({
                    "Response": "INCORRECT_CVC",
                    "Status": True,
                    "Gateway": gateway,
                    "Price": running_total,
                    "cc": card
                })
            elif 'incorrect_zip' in text_lower or 'invalid_zip' in text_lower:
                output.update({
                    "Response": "INCORRECT_ZIP",
                    "Status": True,
                    "Gateway": gateway,
                    "Price": running_total,
                    "cc": card
                })
            elif 'card_declined' in text_lower:
                output.update({
                    "Response": "CARD_DECLINED",
                    "Status": True,
                    "Gateway": gateway,
                    "Price": running_total,
                    "cc": card
                })
            elif 'expired' in text_lower:
                output.update({
                    "Response": "EXPIRED_CARD",
                    "Status": True,
                    "Gateway": gateway,
                    "Price": running_total,
                    "cc": card
                })
            elif 'fraud' in text_lower:
                output.update({
                    "Response": "FRAUD_SUSPECTED",
                    "Status": True,
                    "Gateway": gateway,
                    "Price": running_total,
                    "cc": card
                })
            elif 'do_not_honor' in text_lower:
                output.update({
                    "Response": "DO_NOT_HONOR",
                    "Status": True,
                    "Gateway": gateway,
                    "Price": running_total,
                    "cc": card
                })
            elif code:
                output.update({
                    "Response": code.upper(),
                    "Status": True,
                    "Gateway": gateway,
                    "Price": running_total,
                    "cc": card
                })
            else:
                output.update({
                    "Response": "DECLINED",
                    "Status": True,
                    "Gateway": gateway,
                    "Price": running_total,
                    "cc": card
                })
        
    except Exception as e:
        output.update({
            "Response": f"ERROR: {str(e)}",
            "Status": False,
        })
    
    print(json.dumps(output))
    return output


# Example usage:
# async def main():
#     async with httpx.AsyncClient() as session:
#         result = await autoshopify("https://example.com", "4111111111111111|12|25|123", session)
#         print(result)
#
# if __name__ == "__main__":
#     asyncio.run(main())
