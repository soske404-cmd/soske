from time import sleep
import asyncio
import httpx
import re
import json
import time
import random
import string
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
    "AUD": "AU",
    "EUR": "DE",
}

# Address book for different countries
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
    "DE": {"address1": "Friedrichstraße 123", "city": "Berlin", "postalCode": "10117", "zoneCode": "BE", "countryCode": "DE", "phone": "301234567"},
    "DEFAULT": {"address1": "123 Main", "city": "New York", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586"},
}

def pick_addr(url, cc=None, rc=None):
    """Pick address based on currency/country code"""
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
    """Extract text between two strings"""
    try:
        start = data.index(first) + len(first)
        end = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None

def generate_random_email():
    """Generate random email address"""
    first_names = ['john', 'james', 'robert', 'michael', 'william', 'david', 'richard', 'joseph']
    last_names = ['smith', 'johnson', 'williams', 'brown', 'jones', 'garcia', 'miller', 'davis']
    domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com']
    random_num = ''.join(random.choices(string.digits, k=3))
    return f"{random.choice(first_names)}.{random.choice(last_names)}{random_num}@{random.choice(domains)}"

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

# GraphQL Queries
PROPOSAL_QUERY = 'query Proposal($alternativePaymentCurrency:AlternativePaymentCurrencyInput,$delivery:DeliveryTermsInput,$discounts:DiscountTermsInput,$payment:PaymentTermInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$taxes:TaxTermInput,$sessionInput:SessionTokenInput!,$checkpointData:String,$queueToken:String,$reduction:ReductionInput,$availableRedeemables:AvailableRedeemablesInput,$changesetTokens:[String!],$tip:TipTermInput,$note:NoteInput,$localizationExtension:LocalizationExtensionInput,$nonNegotiableTerms:NonNegotiableTermsInput,$scriptFingerprint:ScriptFingerprintInput,$transformerFingerprintV2:String,$optionalDuties:OptionalDutiesInput,$attribution:AttributionInput,$captcha:CaptchaInput,$poNumber:String,$saleAttributions:SaleAttributionsInput,$cartMetafields:[CartMetafieldOperationInput!],$memberships:MembershipsInput){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{alternativePaymentCurrency:$alternativePaymentCurrency,delivery:$delivery,discounts:$discounts,payment:$payment,merchandise:$merchandise,buyerIdentity:$buyerIdentity,taxes:$taxes,reduction:$reduction,availableRedeemables:$availableRedeemables,tip:$tip,note:$note,poNumber:$poNumber,nonNegotiableTerms:$nonNegotiableTerms,localizationExtension:$localizationExtension,scriptFingerprint:$scriptFingerprint,transformerFingerprintV2:$transformerFingerprintV2,optionalDuties:$optionalDuties,attribution:$attribution,captcha:$captcha,saleAttributions:$saleAttributions,cartMetafields:$cartMetafields,memberships:$memberships},checkpointData:$checkpointData,queueToken:$queueToken,changesetTokens:$changesetTokens}){__typename result{...on NegotiationResultAvailable{checkpointData queueToken buyerProposal{...BuyerProposalDetails __typename}sellerProposal{...ProposalDetails __typename}__typename}...on CheckpointDenied{redirectUrl __typename}...on Throttled{pollAfter queueToken pollUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}...on NegotiationResultFailed{__typename reportable}__typename}errors{code localizedMessage nonLocalizedMessage localizedMessageHtml...on RemoveTermViolation{target __typename}...on AcceptNewTermViolation{target __typename}...on ConfirmChangeViolation{from to __typename}...on UnprocessableTermViolation{target __typename}...on UnresolvableTermViolation{target __typename}...on ApplyChangeViolation{target from{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}to{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}__typename}...on GenericError{__typename}...on PendingTermViolation{__typename}__typename}}__typename}}fragment BuyerProposalDetails on Proposal{buyerIdentity{...on FilledBuyerIdentityTerms{email phone customer{...on CustomerProfile{email __typename}...on BusinessCustomerProfile{email __typename}__typename}__typename}__typename}merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}delivery{...ProposalDeliveryFragment __typename}merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}legacyFee __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}__typename}fragment ProposalDiscountFragment on DiscountTermsV2{__typename...on FilledDiscountTerms{acceptUnexpectedDiscounts lines{...DiscountLineDetailsFragment __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment DiscountLineDetailsFragment on DiscountLine{allocations{...on DiscountAllocatedAllocationSet{__typename allocations{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}target{index targetType stableId __typename}__typename}}__typename}discount{...DiscountDetailsFragment __typename}lineAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}fragment DiscountDetailsFragment on Discount{...on CustomDiscount{title description presentationLevel allocationMethod targetSelection targetType signature signatureUuid type value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on CodeDiscount{title code presentationLevel allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on DiscountCodeTrigger{code __typename}...on AutomaticDiscount{presentationLevel title allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}fragment ProposalDeliveryFragment on DeliveryTerms{__typename...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken splitShippingToggle deliveryLines{destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode oneTimeUse coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone oneTimeUse coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType deliveryMethodTypes selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}...on DeliveryStrategyReference{handle __typename}__typename}availableDeliveryStrategies{...on CompleteDeliveryStrategy{title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms brandedPromise{logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment FilledMerchandiseLineTargetCollectionFragment on FilledMerchandiseLineTargetCollection{linesV2{...on MerchandiseLine{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on MerchandiseBundleLineComponent{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}fragment DeliveryLineMerchandiseFragment on ProposalMerchandise{...on SourceProvidedMerchandise{__typename requiresShipping}...on ProductVariantMerchandise{__typename requiresShipping}...on ContextualizedProductVariantMerchandise{__typename requiresShipping sellingPlan{id digest name prepaid deliveriesPerBillingCycle subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}}...on MissingProductVariantMerchandise{__typename variantId}__typename}fragment SourceProvidedMerchandise on Merchandise{...on SourceProvidedMerchandise{__typename product{id title productType vendor __typename}productUrl digest variantId optionalIdentifier title untranslatedTitle subtitle untranslatedSubtitle taxable giftCard requiresShipping price{amount currencyCode __typename}deferredAmount{amount currencyCode __typename}image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}options{name value __typename}properties{...MerchandiseProperties __typename}taxCode taxesIncluded weight{value unit __typename}sku}__typename}fragment MerchandiseProperties on MerchandiseProperty{name value{...on MerchandisePropertyValueString{string:value __typename}...on MerchandisePropertyValueInt{int:value __typename}...on MerchandisePropertyValueFloat{float:value __typename}...on MerchandisePropertyValueBoolean{boolean:value __typename}...on MerchandisePropertyValueJson{json:value __typename}__typename}visible __typename}fragment ProductVariantMerchandiseDetails on ProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{id subscriptionDetails{billingInterval __typename}__typename}giftCard __typename}fragment ContextualizedProductVariantMerchandiseDetails on ContextualizedProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle sku price{amount currencyCode __typename}product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}giftCard deferredAmount{amount currencyCode __typename}__typename}fragment LineAllocationDetails on LineAllocation{stableId quantity totalAmountBeforeReductions{amount currencyCode __typename}totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}unitPrice{price{amount currencyCode __typename}measurement{referenceUnit referenceValue __typename}__typename}allocations{...on LineComponentDiscountAllocation{allocation{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}__typename}__typename}__typename}fragment MerchandiseBundleLineComponent on MerchandiseBundleLineComponent{__typename stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}}fragment ProposalDetails on Proposal{merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}deliveryExpectations{...ProposalDeliveryExpectationFragment __typename}memberships{...ProposalMembershipsFragment __typename}availableRedeemables{...on PendingTerms{taskId pollDelay __typename}...on AvailableRedeemables{availableRedeemables{paymentMethod{...RedeemablePaymentMethodFragment __typename}balance{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}availableDeliveryAddresses{name firstName lastName company address1 address2 city countryCode zoneCode postalCode oneTimeUse coordinates{latitude longitude __typename}phone handle label __typename}mustSelectProvidedAddress delivery{...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken splitShippingToggle deliveryLines{id availableOn destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode oneTimeUse coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone oneTimeUse coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}__typename}deliveryMethodTypes availableDeliveryStrategies{...on CompleteDeliveryStrategy{originLocation{id __typename}title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms metafields{key namespace value __typename}brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice flatRateGroupId targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromiseProviderApiClientId deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name distanceFromBuyer{unit value __typename}__typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}deliveryMacros{totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyHandles id title totalTitle __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}__typename}payment{...on FilledPaymentTerms{availablePaymentLines{placements paymentMethod{...on PaymentProvider{paymentMethodIdentifier name brands paymentBrands orderingIndex displayName extensibilityDisplayName availablePresentmentCurrencies paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}checkoutHostedFields alternative supportsNetworkSelection supportsVaulting __typename}...on OffsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex showRedirectionNotice availablePresentmentCurrencies popupEnabled}...on CustomOnsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex availablePresentmentCurrencies popupEnabled paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}}...on AnyRedeemablePaymentMethod{__typename availableRedemptionConfigs{__typename...on CustomRedemptionConfig{paymentMethodIdentifier paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}__typename}}orderingIndex}...on WalletsPlatformConfiguration{name paymentMethodIdentifier configurationParams __typename}...on PaypalWalletConfig{__typename name clientId merchantId venmoEnabled payflow paymentIntent paymentMethodIdentifier orderingIndex clientToken supportsVaulting sandboxTestMode}...on ShopPayWalletConfig{__typename name storefrontUrl paymentMethodIdentifier orderingIndex}...on ShopifyInstallmentsWalletConfig{__typename name availableLoanTypes maxPrice{amount currencyCode __typename}minPrice{amount currencyCode __typename}supportedCountries supportedCurrencies giftCardsNotAllowed subscriptionItemsNotAllowed ineligibleTestModeCheckout ineligibleLineItem paymentMethodIdentifier orderingIndex}...on ApplePayWalletConfig{__typename name supportedNetworks walletAuthenticationToken walletOrderTypeIdentifier walletServiceUrl paymentMethodIdentifier orderingIndex}...on GooglePayWalletConfig{__typename name allowedAuthMethods allowedCardNetworks gateway gatewayMerchantId merchantId authJwt environment paymentMethodIdentifier orderingIndex}...on LocalPaymentMethodConfig{__typename paymentMethodIdentifier name displayName orderingIndex}...on AnyPaymentOnDeliveryMethod{__typename additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex name availablePresentmentCurrencies}...on ManualPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on CustomPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{__typename expired expiryMonth expiryYear name orderingIndex...CustomerCreditCardPaymentMethodFragment}...on PaypalBillingAgreementPaymentMethod{__typename orderingIndex paypalAccountEmail...PaypalBillingAgreementPaymentMethodFragment}__typename}__typename}paymentLines{...PaymentLines __typename}billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}paymentFlexibilityPaymentTermsTemplate{id translatedName dueDate dueInDays type __typename}depositConfiguration{...on DepositPercentage{percentage __typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}poNumber merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}legacyFee __typename}__typename}__typename}note{customAttributes{key value __typename}message __typename}scriptFingerprint{signature signatureUuid lineItemScriptChanges paymentScriptChanges shippingScriptChanges __typename}transformerFingerprintV2 buyerIdentity{...on FilledBuyerIdentityTerms{customer{...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}shippingAddresses{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}...on CustomerProfile{id presentmentCurrency fullName firstName lastName countryCode market{id handle __typename}email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone billingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}shippingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label coordinates{latitude longitude __typename}__typename}__typename}storeCreditAccounts{id balance{amount currencyCode __typename}__typename}__typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl market{id handle __typename}email ordersCount phone __typename}__typename}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name billingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}shippingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}storeCreditAccounts{id balance{amount currencyCode __typename}__typename}__typename}__typename}phone email marketingConsent{...on SMSMarketingConsent{value __typename}...on EmailMarketingConsent{value __typename}__typename}shopPayOptInPhone rememberMe __typename}__typename}checkoutCompletionTarget recurringTotals{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}legacyRepresentProductsAsFees totalSavings{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeReductions{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAfterMerchandiseDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}duty{...on FilledDutyTerms{totalDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAdditionalFeesAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tax{...on FilledTaxTerms{totalTaxAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountIncludedInTarget{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}exemptions{taxExemptionReason targets{...on TargetAllLines{__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tip{tipSuggestions{...on TipSuggestion{__typename percentage amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}}__typename}terms{...on FilledTipTerms{tipLines{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}localizationExtension{...on LocalizationExtension{fields{...on LocalizationExtensionField{key title value __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}dutiesIncluded nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}managedByMarketsPro captcha{...on Captcha{provider challenge sitekey token __typename}...on PendingTerms{taskId pollDelay __typename}__typename}cartCheckoutValidation{...on PendingTerms{taskId pollDelay __typename}__typename}alternativePaymentCurrency{...on AllocatedAlternativePaymentCurrencyTotal{total{amount currencyCode __typename}paymentLineAllocations{amount{amount currencyCode __typename}stableId __typename}__typename}__typename}isShippingRequired __typename}fragment ProposalDeliveryExpectationFragment on DeliveryExpectationTerms{__typename...on FilledDeliveryExpectationTerms{deliveryExpectations{minDeliveryDateTime maxDeliveryDateTime deliveryStrategyHandle brandedPromise{logoUrl darkThemeLogoUrl lightThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name handle __typename}deliveryOptionHandle deliveryExpectationPresentmentTitle{short long __typename}promiseProviderApiClientId signedHandle returnability __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment ProposalMembershipsFragment on MembershipTerms{__typename...on FilledMembershipTerms{memberships{apply handle __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{_singleInstance __typename}}fragment RedeemablePaymentMethodFragment on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionPaymentOptionKind redemptionId destinationAmount{amount currencyCode __typename}sourceAmount{amount currencyCode __typename}details{redemptionId sourceAmount{amount currencyCode __typename}destinationAmount{amount currencyCode __typename}redemptionType __typename}__typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}__typename}__typename}fragment UiExtensionInstallationFragment on UiExtensionInstallation{extension{approvalScopes{handle __typename}capabilities{apiAccess networkAccess blockProgress collectBuyerConsent{smsMarketing customerPrivacy __typename}__typename}apiVersion appId appUrl preloads{target namespace value __typename}appName extensionLocale extensionPoints name registrationUuid scriptUrl translations uuid version __typename}__typename}fragment CustomerCreditCardPaymentMethodFragment on CustomerCreditCardPaymentMethod{id cvvSessionId paymentInstrumentAccessorId paymentMethodIdentifier token displayLastDigits brand defaultPaymentMethod deletable requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaypalBillingAgreementPaymentMethodFragment on PaypalBillingAgreementPaymentMethod{paymentMethodIdentifier token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaymentLines on PaymentLine{stableId specialInstructions amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt due{...on PaymentLineDueEvent{event __typename}...on PaymentLineDueTime{time __typename}__typename}paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier creditCard{...on CreditCard{brand lastDigits name __typename}__typename}paymentAttributes __typename}...on GiftCardPaymentMethod{code balance{amount currencyCode __typename}__typename}...on RedeemablePaymentMethod{...RedeemablePaymentMethodFragment __typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier __typename}...on PaypalWalletContent{paypalBillingAddress:billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token paymentMethodIdentifier acceptedSubscriptionTerms expiresAt merchantId __typename}...on ApplePayWalletContent{data signature version lastDigits paymentMethodIdentifier header{applicationData ephemeralPublicKey publicKeyHash transactionId __typename}__typename}...on GooglePayWalletContent{signature signedMessage protocolVersion paymentMethodIdentifier __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken paymentMethodIdentifier __typename}__typename}__typename}...on LocalPaymentMethod{paymentMethodIdentifier name __typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on OffsitePaymentMethod{paymentMethodIdentifier name __typename}...on CustomPaymentMethod{id name additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name paymentAttributes __typename}...on ManualPaymentMethod{id name paymentMethodIdentifier __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{...CustomerCreditCardPaymentMethodFragment __typename}...on PaypalBillingAgreementPaymentMethod{...PaypalBillingAgreementPaymentMethodFragment __typename}...on NoopPaymentMethod{__typename}__typename}__typename}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl confirmationPage{url shouldRedirect __typename}orderStatusPageUrl shopPay shopPayInstallments paymentExtensionBrand analytics{checkoutCompletedEventId emitConversionEvent __typename}poNumber orderIdentity{buyerIdentifier id __typename}customerId isFirstOrder eligibleForMarketingOptIn purchaseOrder{...ReceiptPurchaseOrder __typename}orderCreationStatus{__typename}paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway financialPendingReason paymentDescriptor buyerActionInfo{...on MultibancoBuyerActionInfo{entity reference __typename}__typename}__typename}shopAppLinksAndResources{mobileUrl qrCodeUrl canTrackOrderUpdates shopInstallmentsViewSchedules shopInstallmentsMobileUrl installmentsHighlightEligible mobileUrlAttributionPayload shopAppEligible shopAppQrCodeKillswitch shopPayOrder payEscrowMayExist buyerHasShopApp buyerHasShopPay orderUpdateOptions __typename}postPurchasePageUrl postPurchasePageRequested postPurchaseVaultedPaymentMethodStatus paymentFlexibilityPaymentTermsTemplate{__typename dueDate dueInDays id translatedName type}__typename}...on ProcessingReceipt{id purchaseOrder{...ReceiptPurchaseOrder __typename}pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted __typename}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}__typename}__typename}__typename}fragment ReceiptPurchaseOrder on PurchaseOrder{__typename sessionToken totalAmountToPay{amount currencyCode __typename}checkoutCompletionTarget}' 

SUBMIT_QUERY = 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{code localizedMessage nonLocalizedMessage __typename}__typename}...on Throttled{pollAfter pollUrl queueToken __typename}...on CheckpointDenied{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id __typename}...on ProcessingReceipt{id pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id __typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}'

POLL_QUERY = 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id __typename}...on ProcessingReceipt{id pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}__typename}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted __typename}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}__typename}__typename}__typename}'

async def autoshopify(url, card, session):
    """
    Main Shopify checkout function
    Args:
        url: Shopify store URL (e.g., https://example.com)
        card: Card details in format cc|mm|yy|cvv
        session: httpx AsyncClient session
    Returns:
        dict with Response, Status, Gateway, Price, cc
    """
    output = {
        "Response": "UNKNOWN_ERROR",
        "Status": False,
    }
    
    start = time.time()
    
    try:
        # Parse URL and card
        if not url.startswith('http'):
            url = f'https://{url}'
        url = url.rstrip('/')
        domain = urlparse(url).netloc
        
        # Parse card
        parts = card.replace(' ', '').split('|')
        if len(parts) != 4:
            output["Response"] = "INVALID_CARD_FORMAT"
            return output
        cc, mes, ano, cvv = map(str.strip, parts)
        
        # Format year
        if len(ano) == 2:
            ano = '20' + ano
            
        email = generate_random_email()
        
        # Step 1: Get products
        try:
            request = await session.get(f"{url}/products.json", timeout=15)
            product_id, price = get_product_id(request)
        except Exception as e:
            output["Response"] = "SITE_ERROR"
            return output
            
        if not product_id:
            output["Response"] = "NO_PRODUCTS"
            return output

        # Step 2: Get site key and create checkout
        try:
            request = await session.get(url, timeout=15)
        except:
            output["Response"] = "SITE_DEAD"
            return output

        site_key = capture(request.text, '"accessToken":"', '"')
        if not site_key:
            site_key = capture(request.text, 'accessToken":"', '"')

        # Create cart
        headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': url,
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
            'x-shopify-storefront-access-token': site_key,
        }

        cart_json = {
            'query': 'mutation cartCreate($input:CartInput!$country:CountryCode$language:LanguageCode)@inContext(country:$country language:$language){result:cartCreate(input:$input){cart{id checkoutUrl}}}',
            'variables': {
                'input': {
                    'lines': [{'merchandiseId': f'gid://shopify/ProductVariant/{product_id}', 'quantity': 1}],
                },
                'country': 'US',
                'language': 'EN',
            },
        }

        request = await session.post(f'{url}/api/unstable/graphql.json', headers=headers, json=cart_json)
        data = request.json()
        
        try:
            checkout_url = data["data"]["result"]["cart"]["checkoutUrl"]
        except:
            output["Response"] = "CART_ERROR"
            return output

        # Step 3: Go to checkout
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36'
        }

        request = await session.get(checkout_url, headers=headers, params={'skip_shop_pay': 'true'}, follow_redirects=True)
        checkout_text = request.text
        
        # Extract session data
        session_token = capture(checkout_text, 'serialized-session-token" content="&quot;', '&quot')
        source_token = capture(checkout_text, 'serialized-source-token" content="&quot;', '&quot')
        web_build = capture(checkout_text, 'sha&quot;:&quot;', '&quot')
        queue_token = capture(checkout_text, 'queueToken&quot;:&quot;', '&quot')
        stable_id = capture(checkout_text, 'stableId&quot;:&quot;', '&quot')
        payment_method_id = capture(checkout_text, 'paymentMethodIdentifier&quot;:&quot;', '&quot')
        currency_code = capture(checkout_text, 'currencyCode&quot;:&quot;', '&quot') or 'USD'
        country_code = capture(checkout_text, 'countryCode&quot;:&quot;', '&quot') or 'US'
        
        # Get gateway name
        gateway = capture(checkout_text, 'extensibilityDisplayName&quot;:&quot;', '&quot')
        if gateway == "Shopify Payments":
            gateway = "Normal"
        elif not gateway:
            gateway = "Unknown"

        if not session_token:
            await asyncio.sleep(2)
            request = await session.get(str(request.url), headers=headers, follow_redirects=True)
            checkout_text = request.text
            session_token = capture(checkout_text, 'serialized-session-token" content="&quot;', '&quot')
            
        if not session_token:
            output["Response"] = "SESSION_ERROR"
            return output

        # Get address based on currency/country
        addr = pick_addr(url, cc=currency_code, rc=country_code)
        graphql_url = f'{url}/checkouts/unstable/graphql'
        
        # Headers for GraphQL requests
        gql_headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': url,
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
            'shopify-checkout-client': 'checkout-web/1.0',
            'x-checkout-one-session-token': session_token,
            'x-checkout-web-build-id': web_build or '',
            'x-checkout-web-deploy-stage': 'production',
            'x-checkout-web-source-id': source_token or '',
        }

        # Step 4: First proposal - shipping
        proposal_vars = {
            'sessionInput': {'sessionToken': session_token},
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
                            'oneTimeUse': False,
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
                    'expectedTotalPrice': {'value': {'amount': str(price), 'currencyCode': currency_code}},
                    'lineComponents': [],
                }],
            },
            'memberships': {'memberships': []},
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
                'customer': {'presentmentCurrency': currency_code, 'countryCode': country_code},
                'email': email,
                'emailChanged': False,
                'marketingConsent': [],
                'rememberMe': False,
            },
            'tip': {'tipLines': []},
            'taxes': {
                'proposedTotalAmount': {'value': {'amount': '0', 'currencyCode': currency_code}},
                'proposedExemptions': [],
            },
            'note': {'customAttributes': []},
            'scriptFingerprint': {'lineItemScriptChanges': [], 'paymentScriptChanges': [], 'shippingScriptChanges': []},
            'optionalDuties': {'buyerRefusesDuties': False},
            'cartMetafields': [],
        }

        request = await session.post(graphql_url, headers=gql_headers, json={'query': PROPOSAL_QUERY, 'variables': proposal_vars})
        await asyncio.sleep(1)
        request = await session.post(graphql_url, headers=gql_headers, json={'query': PROPOSAL_QUERY, 'variables': proposal_vars})
        
        proposal_resp = request.json()
        
        # Extract shipping data
        try:
            seller_proposal = proposal_resp['data']['session']['negotiate']['result']['sellerProposal']
            total = seller_proposal.get('runningTotal', {}).get('value', {}).get('amount', str(price))
            
            delivery = seller_proposal.get('delivery', {})
            if delivery.get('__typename') == 'FilledDeliveryTerms':
                delivery_lines = delivery.get('deliveryLines', [{}])
                if delivery_lines:
                    strategies = delivery_lines[0].get('availableDeliveryStrategies', [])
                    handle = strategies[0]['handle'] if strategies else ''
                    shipping_amount = strategies[0].get('amount', {}).get('value', {}).get('amount', '0') if strategies else '0'
                else:
                    handle = ''
                    shipping_amount = '0'
            else:
                handle = ''
                shipping_amount = '0'
                
            tax_data = seller_proposal.get('tax', {})
            tax_amount = '0'
            if tax_data.get('__typename') == 'FilledTaxTerms':
                tax_amount = tax_data.get('totalTaxAmount', {}).get('value', {}).get('amount', '0')
                
        except Exception as e:
            output["Response"] = f"PROPOSAL_ERROR"
            return output

        # Step 5: Get payment token
        pci_headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': 'https://checkout.shopifycs.com',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36'
        }
        
        payment_json = {
            'credit_card': {
                'number': cc,
                'month': mes,
                'year': ano,
                'verification_value': cvv,
                'name': 'Laka Lama',
            },
            'payment_session_scope': domain
        }

        request = await session.post('https://deposit.shopifycs.com/sessions', headers=pci_headers, json=payment_json)
        
        try:
            payment_token = request.json()["id"]
        except:
            output["Response"] = "PAYMENT_TOKEN_ERROR"
            return output

        # Step 6: Submit for completion
        submit_vars = {
            'input': {
                'sessionInput': {'sessionToken': session_token},
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
                                'oneTimeUse': False,
                            }
                        },
                        'selectedDeliveryStrategy': {
                            'deliveryStrategyByHandle': {'handle': handle, 'customDeliveryRate': False},
                            'options': {'phone': addr["phone"]},
                        },
                        'targetMerchandiseLines': {'lines': [{'stableId': stable_id}]},
                        'deliveryMethodTypes': ['SHIPPING'],
                        'expectedTotalPrice': {'value': {'amount': shipping_amount, 'currencyCode': currency_code}},
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
                        'expectedTotalPrice': {'value': {'amount': str(price), 'currencyCode': currency_code}},
                        'lineComponents': [],
                    }],
                },
                'payment': {
                    'totalAmount': {'any': True},
                    'paymentLines': [{
                        'paymentMethod': {
                            'directPaymentMethod': {
                                'paymentMethodIdentifier': payment_method_id,
                                'sessionId': payment_token,
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
                        'amount': {'value': {'amount': total, 'currencyCode': currency_code}},
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
                    'customer': {'presentmentCurrency': currency_code, 'countryCode': country_code},
                    'email': email,
                    'emailChanged': False,
                    'marketingConsent': [],
                    'rememberMe': False,
                },
                'tip': {'tipLines': []},
                'taxes': {
                    'proposedTotalAmount': {'value': {'amount': tax_amount, 'currencyCode': currency_code}},
                    'proposedExemptions': [],
                },
                'note': {'customAttributes': []},
                'scriptFingerprint': {'lineItemScriptChanges': [], 'paymentScriptChanges': [], 'shippingScriptChanges': []},
                'optionalDuties': {'buyerRefusesDuties': False},
                'cartMetafields': [],
            },
            'attemptToken': f'{source_token or session_token}-submit',
            'metafields': [],
            'analytics': {'requestUrl': checkout_url},
        }

        request = await session.post(graphql_url, headers=gql_headers, json={'query': SUBMIT_QUERY, 'variables': submit_vars})
        submit_text = request.text
        
        # Handle special errors
        if "CAPTCHA" in submit_text:
            output.update({"Response": "CAPTCHA_REQUIRED", "Status": False, "Gateway": gateway, "Price": total, "cc": card})
            return output
            
        if "Your order total has changed" in submit_text:
            output.update({"Response": "TOTAL_CHANGED", "Status": False, "Gateway": gateway, "Price": total, "cc": card})
            return output

        # Get receipt ID
        try:
            submit_resp = request.json()
            receipt_id = submit_resp['data']['submitForCompletion']['receipt']['id']
        except:
            # Try retry
            await asyncio.sleep(3)
            request = await session.post(graphql_url, headers=gql_headers, json={'query': SUBMIT_QUERY, 'variables': submit_vars})
            try:
                submit_resp = request.json()
                receipt_id = submit_resp['data']['submitForCompletion']['receipt']['id']
            except:
                output.update({"Response": "SUBMIT_ERROR", "Status": False, "Gateway": gateway, "Price": total, "cc": card})
                return output

        # Step 7: Poll for receipt
        await asyncio.sleep(3)
        
        poll_vars = {'receiptId': receipt_id, 'sessionToken': session_token}
        
        final_text = ""
        for i in range(3):
            request = await session.post(graphql_url, headers=gql_headers, json={'query': POLL_QUERY, 'variables': poll_vars})
            final_text = request.text
            
            if 'WaitingReceipt' not in final_text:
                break
            await asyncio.sleep(3)

        end = time.time()
        
        # Parse final result
        final_resp = request.json()
        result = None
        try:
            result = final_resp.get('data', {}).get('receipt', {}).get('processingError', {}).get('code')
        except:
            pass

        # Determine response
        if "shopify_payments" in final_text.lower() or "ProcessedReceipt" in final_text:
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
            output.update({"Response": "UNKNOWN_RESPONSE", "Status": True, "Gateway": gateway, "Price": total, "cc": card})

    except Exception as e:
        output.update({"Response": str(e), "Status": False})

    print(json.dumps(output))
    return output


async def main():
    """Test function"""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as session:
        # Example usage - replace with actual test
        result = await autoshopify("https://example.myshopify.com", "4111111111111111|12|25|123", session)
        print(result)

if __name__ == "__main__":
    asyncio.run(main())
