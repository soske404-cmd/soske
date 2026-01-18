"""
Shopify Terminal - GraphQL Checkout Implementation
Style inspired by api.py with full GraphQL checkout flow
"""

import asyncio
import httpx
import re
import json
import time
import random
import string
from urllib.parse import urlparse
from typing import Optional, Tuple, Dict, Any

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
ADDRESS_BOOK = {
    "US": {"address1": "123 Main St", "city": "New York", "postalCode": "10001", "zoneCode": "NY", "countryCode": "US", "phone": "2125551234"},
    "CA": {"address1": "88 Queen St", "city": "Toronto", "postalCode": "M5J2J3", "zoneCode": "ON", "countryCode": "CA", "phone": "4165550198"},
    "GB": {"address1": "221B Baker Street", "city": "London", "postalCode": "NW1 6XE", "zoneCode": "LND", "countryCode": "GB", "phone": "2079460123"},
    "IN": {"address1": "221B MG Road", "city": "Mumbai", "postalCode": "400001", "zoneCode": "MH", "countryCode": "IN", "phone": "9876543210"},
    "AE": {"address1": "Burj Tower", "city": "Dubai", "postalCode": "", "zoneCode": "DU", "countryCode": "AE", "phone": "501234567"},
    "HK": {"address1": "Nathan 88", "city": "Kowloon", "postalCode": "", "zoneCode": "KL", "countryCode": "HK", "phone": "55555555"},
    "CN": {"address1": "8 Zhongguancun Street", "city": "Beijing", "postalCode": "100080", "zoneCode": "BJ", "countryCode": "CN", "phone": "1062512345"},
    "CH": {"address1": "Gotthardstrasse 17", "city": "Zurich", "postalCode": "8002", "zoneCode": "ZH", "countryCode": "CH", "phone": "445512345"},
    "AU": {"address1": "1 Martin Place", "city": "Sydney", "postalCode": "2000", "zoneCode": "NSW", "countryCode": "AU", "phone": "291234567"},
    "DE": {"address1": "Alexanderplatz 1", "city": "Berlin", "postalCode": "10178", "zoneCode": "BE", "countryCode": "DE", "phone": "301234567"},
    "DEFAULT": {"address1": "123 Main St", "city": "New York", "postalCode": "10001", "zoneCode": "NY", "countryCode": "US", "phone": "2125551234"},
}

# GraphQL Queries
CART_CREATE_QUERY = 'mutation cartCreate($input:CartInput!$country:CountryCode$language:LanguageCode$withCarrierRates:Boolean=false)@inContext(country:$country language:$language){result:cartCreate(input:$input){...@defer(if:$withCarrierRates){cart{...CartParts}errors:userErrors{...on CartUserError{message field code}}warnings:warnings{...on CartWarning{code}}}}}fragment CartParts on Cart{id checkoutUrl deliveryGroups(first:10 withCarrierRates:$withCarrierRates){edges{node{id groupType selectedDeliveryOption{code title handle deliveryPromise deliveryMethodType estimatedCost{amount currencyCode}}deliveryOptions{code title handle deliveryPromise deliveryMethodType estimatedCost{amount currencyCode}}}}}cost{subtotalAmount{amount currencyCode}totalAmount{amount currencyCode}totalTaxAmount{amount currencyCode}totalDutyAmount{amount currencyCode}}discountAllocations{discountedAmount{amount currencyCode}...on CartCodeDiscountAllocation{code}...on CartAutomaticDiscountAllocation{title}...on CartCustomDiscountAllocation{title}}discountCodes{code applicable}lines(first:10){edges{node{quantity cost{subtotalAmount{amount currencyCode}totalAmount{amount currencyCode}}discountAllocations{discountedAmount{amount currencyCode}...on CartCodeDiscountAllocation{code}...on CartAutomaticDiscountAllocation{title}...on CartCustomDiscountAllocation{title}}merchandise{...on ProductVariant{requiresShipping}}sellingPlanAllocation{priceAdjustments{price{amount currencyCode}}sellingPlan{billingPolicy{...on SellingPlanRecurringBillingPolicy{interval intervalCount}}priceAdjustments{orderCount}recurringDeliveries}}}}}}'

PROPOSAL_QUERY = 'query Proposal($alternativePaymentCurrency:AlternativePaymentCurrencyInput,$delivery:DeliveryTermsInput,$discounts:DiscountTermsInput,$payment:PaymentTermInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$taxes:TaxTermInput,$sessionInput:SessionTokenInput!,$checkpointData:String,$queueToken:String,$reduction:ReductionInput,$availableRedeemables:AvailableRedeemablesInput,$changesetTokens:[String!],$tip:TipTermInput,$note:NoteInput,$localizationExtension:LocalizationExtensionInput,$nonNegotiableTerms:NonNegotiableTermsInput,$scriptFingerprint:ScriptFingerprintInput,$transformerFingerprintV2:String,$optionalDuties:OptionalDutiesInput,$attribution:AttributionInput,$captcha:CaptchaInput,$poNumber:String,$saleAttributions:SaleAttributionsInput,$cartMetafields:[CartMetafieldOperationInput!],$memberships:MembershipsInput){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{alternativePaymentCurrency:$alternativePaymentCurrency,delivery:$delivery,discounts:$discounts,payment:$payment,merchandise:$merchandise,buyerIdentity:$buyerIdentity,taxes:$taxes,reduction:$reduction,availableRedeemables:$availableRedeemables,tip:$tip,note:$note,poNumber:$poNumber,nonNegotiableTerms:$nonNegotiableTerms,localizationExtension:$localizationExtension,scriptFingerprint:$scriptFingerprint,transformerFingerprintV2:$transformerFingerprintV2,optionalDuties:$optionalDuties,attribution:$attribution,captcha:$captcha,saleAttributions:$saleAttributions,cartMetafields:$cartMetafields,memberships:$memberships},checkpointData:$checkpointData,queueToken:$queueToken,changesetTokens:$changesetTokens}){__typename result{...on NegotiationResultAvailable{checkpointData queueToken buyerProposal{...BuyerProposalDetails __typename}sellerProposal{...ProposalDetails __typename}__typename}...on CheckpointDenied{redirectUrl __typename}...on Throttled{pollAfter queueToken pollUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}...on NegotiationResultFailed{__typename reportable}__typename}errors{code localizedMessage nonLocalizedMessage localizedMessageHtml...on RemoveTermViolation{target __typename}...on AcceptNewTermViolation{target __typename}...on ConfirmChangeViolation{from to __typename}...on UnprocessableTermViolation{target __typename}...on UnresolvableTermViolation{target __typename}...on ApplyChangeViolation{target from{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}to{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}__typename}...on GenericError{__typename}...on PendingTermViolation{__typename}__typename}}__typename}}fragment BuyerProposalDetails on Proposal{buyerIdentity{...on FilledBuyerIdentityTerms{email phone customer{...on CustomerProfile{email __typename}...on BusinessCustomerProfile{email __typename}__typename}__typename}__typename}merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}delivery{...ProposalDeliveryFragment __typename}merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}legacyFee __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}__typename}fragment ProposalDiscountFragment on DiscountTermsV2{__typename...on FilledDiscountTerms{acceptUnexpectedDiscounts lines{...DiscountLineDetailsFragment __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment DiscountLineDetailsFragment on DiscountLine{allocations{...on DiscountAllocatedAllocationSet{__typename allocations{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}target{index targetType stableId __typename}__typename}}__typename}discount{...DiscountDetailsFragment __typename}lineAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}fragment DiscountDetailsFragment on Discount{...on CustomDiscount{title description presentationLevel allocationMethod targetSelection targetType signature signatureUuid type value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on CodeDiscount{title code presentationLevel allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on DiscountCodeTrigger{code __typename}...on AutomaticDiscount{presentationLevel title allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}fragment ProposalDeliveryFragment on DeliveryTerms{__typename...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken splitShippingToggle deliveryLines{destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode oneTimeUse coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone oneTimeUse coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType deliveryMethodTypes selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}...on DeliveryStrategyReference{handle __typename}__typename}availableDeliveryStrategies{...on CompleteDeliveryStrategy{title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms brandedPromise{logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment FilledMerchandiseLineTargetCollectionFragment on FilledMerchandiseLineTargetCollection{linesV2{...on MerchandiseLine{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on MerchandiseBundleLineComponent{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}fragment DeliveryLineMerchandiseFragment on ProposalMerchandise{...on SourceProvidedMerchandise{__typename requiresShipping}...on ProductVariantMerchandise{__typename requiresShipping}...on ContextualizedProductVariantMerchandise{__typename requiresShipping sellingPlan{id digest name prepaid deliveriesPerBillingCycle subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}}...on MissingProductVariantMerchandise{__typename variantId}__typename}fragment SourceProvidedMerchandise on Merchandise{...on SourceProvidedMerchandise{__typename product{id title productType vendor __typename}productUrl digest variantId optionalIdentifier title untranslatedTitle subtitle untranslatedSubtitle taxable giftCard requiresShipping price{amount currencyCode __typename}deferredAmount{amount currencyCode __typename}image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}options{name value __typename}properties{...MerchandiseProperties __typename}taxCode taxesIncluded weight{value unit __typename}sku}__typename}fragment MerchandiseProperties on MerchandiseProperty{name value{...on MerchandisePropertyValueString{string:value __typename}...on MerchandisePropertyValueInt{int:value __typename}...on MerchandisePropertyValueFloat{float:value __typename}...on MerchandisePropertyValueBoolean{boolean:value __typename}...on MerchandisePropertyValueJson{json:value __typename}__typename}visible __typename}fragment ProductVariantMerchandiseDetails on ProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{id subscriptionDetails{billingInterval __typename}__typename}giftCard __typename}fragment ContextualizedProductVariantMerchandiseDetails on ContextualizedProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle sku price{amount currencyCode __typename}product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}giftCard deferredAmount{amount currencyCode __typename}__typename}fragment LineAllocationDetails on LineAllocation{stableId quantity totalAmountBeforeReductions{amount currencyCode __typename}totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}unitPrice{price{amount currencyCode __typename}measurement{referenceUnit referenceValue __typename}__typename}allocations{...on LineComponentDiscountAllocation{allocation{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}__typename}__typename}__typename}fragment MerchandiseBundleLineComponent on MerchandiseBundleLineComponent{__typename stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}}fragment ProposalDetails on Proposal{merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}deliveryExpectations{...ProposalDeliveryExpectationFragment __typename}memberships{...ProposalMembershipsFragment __typename}availableRedeemables{...on PendingTerms{taskId pollDelay __typename}...on AvailableRedeemables{availableRedeemables{paymentMethod{...RedeemablePaymentMethodFragment __typename}balance{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}availableDeliveryAddresses{name firstName lastName company address1 address2 city countryCode zoneCode postalCode oneTimeUse coordinates{latitude longitude __typename}phone handle label __typename}mustSelectProvidedAddress delivery{...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken splitShippingToggle deliveryLines{id availableOn destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode oneTimeUse coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone oneTimeUse coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}__typename}deliveryMethodTypes availableDeliveryStrategies{...on CompleteDeliveryStrategy{originLocation{id __typename}title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms metafields{key namespace value __typename}brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice flatRateGroupId targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromiseProviderApiClientId deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name distanceFromBuyer{unit value __typename}__typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}deliveryMacros{totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyHandles id title totalTitle __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}__typename}payment{...on FilledPaymentTerms{availablePaymentLines{placements paymentMethod{...on PaymentProvider{paymentMethodIdentifier name brands paymentBrands orderingIndex displayName extensibilityDisplayName availablePresentmentCurrencies paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}checkoutHostedFields alternative supportsNetworkSelection supportsVaulting __typename}...on OffsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex showRedirectionNotice availablePresentmentCurrencies popupEnabled}...on CustomOnsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex availablePresentmentCurrencies popupEnabled paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}}...on AnyRedeemablePaymentMethod{__typename availableRedemptionConfigs{__typename...on CustomRedemptionConfig{paymentMethodIdentifier paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}__typename}}orderingIndex}...on WalletsPlatformConfiguration{name paymentMethodIdentifier configurationParams __typename}...on PaypalWalletConfig{__typename name clientId merchantId venmoEnabled payflow paymentIntent paymentMethodIdentifier orderingIndex clientToken supportsVaulting sandboxTestMode}...on ShopPayWalletConfig{__typename name storefrontUrl paymentMethodIdentifier orderingIndex}...on ShopifyInstallmentsWalletConfig{__typename name availableLoanTypes maxPrice{amount currencyCode __typename}minPrice{amount currencyCode __typename}supportedCountries supportedCurrencies giftCardsNotAllowed subscriptionItemsNotAllowed ineligibleTestModeCheckout ineligibleLineItem paymentMethodIdentifier orderingIndex}...on ApplePayWalletConfig{__typename name supportedNetworks walletAuthenticationToken walletOrderTypeIdentifier walletServiceUrl paymentMethodIdentifier orderingIndex}...on GooglePayWalletConfig{__typename name allowedAuthMethods allowedCardNetworks gateway gatewayMerchantId merchantId authJwt environment paymentMethodIdentifier orderingIndex}...on LocalPaymentMethodConfig{__typename paymentMethodIdentifier name displayName orderingIndex}...on AnyPaymentOnDeliveryMethod{__typename additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex name availablePresentmentCurrencies}...on ManualPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on CustomPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{__typename expired expiryMonth expiryYear name orderingIndex...CustomerCreditCardPaymentMethodFragment}...on PaypalBillingAgreementPaymentMethod{__typename orderingIndex paypalAccountEmail...PaypalBillingAgreementPaymentMethodFragment}__typename}__typename}paymentLines{...PaymentLines __typename}billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}paymentFlexibilityPaymentTermsTemplate{id translatedName dueDate dueInDays type __typename}depositConfiguration{...on DepositPercentage{percentage __typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}poNumber merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}legacyFee __typename}__typename}__typename}note{customAttributes{key value __typename}message __typename}scriptFingerprint{signature signatureUuid lineItemScriptChanges paymentScriptChanges shippingScriptChanges __typename}transformerFingerprintV2 buyerIdentity{...on FilledBuyerIdentityTerms{customer{...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}shippingAddresses{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}...on CustomerProfile{id presentmentCurrency fullName firstName lastName countryCode market{id handle __typename}email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone billingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}shippingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label coordinates{latitude longitude __typename}__typename}__typename}storeCreditAccounts{id balance{amount currencyCode __typename}__typename}__typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl market{id handle __typename}email ordersCount phone __typename}__typename}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name billingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}shippingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}storeCreditAccounts{id balance{amount currencyCode __typename}__typename}__typename}__typename}phone email marketingConsent{...on SMSMarketingConsent{value __typename}...on EmailMarketingConsent{value __typename}__typename}shopPayOptInPhone rememberMe __typename}__typename}checkoutCompletionTarget recurringTotals{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}legacyRepresentProductsAsFees totalSavings{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeReductions{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAfterMerchandiseDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}duty{...on FilledDutyTerms{totalDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAdditionalFeesAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tax{...on FilledTaxTerms{totalTaxAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountIncludedInTarget{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}exemptions{taxExemptionReason targets{...on TargetAllLines{__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tip{tipSuggestions{...on TipSuggestion{__typename percentage amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}}__typename}terms{...on FilledTipTerms{tipLines{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}localizationExtension{...on LocalizationExtension{fields{...on LocalizationExtensionField{key title value __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}dutiesIncluded nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}managedByMarketsPro captcha{...on Captcha{provider challenge sitekey token __typename}...on PendingTerms{taskId pollDelay __typename}__typename}cartCheckoutValidation{...on PendingTerms{taskId pollDelay __typename}__typename}alternativePaymentCurrency{...on AllocatedAlternativePaymentCurrencyTotal{total{amount currencyCode __typename}paymentLineAllocations{amount{amount currencyCode __typename}stableId __typename}__typename}__typename}isShippingRequired __typename}fragment ProposalDeliveryExpectationFragment on DeliveryExpectationTerms{__typename...on FilledDeliveryExpectationTerms{deliveryExpectations{minDeliveryDateTime maxDeliveryDateTime deliveryStrategyHandle brandedPromise{logoUrl darkThemeLogoUrl lightThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name handle __typename}deliveryOptionHandle deliveryExpectationPresentmentTitle{short long __typename}promiseProviderApiClientId signedHandle returnability __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment ProposalMembershipsFragment on MembershipTerms{__typename...on FilledMembershipTerms{memberships{apply handle __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{_singleInstance __typename}}fragment RedeemablePaymentMethodFragment on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionPaymentOptionKind redemptionId destinationAmount{amount currencyCode __typename}sourceAmount{amount currencyCode __typename}details{redemptionId sourceAmount{amount currencyCode __typename}destinationAmount{amount currencyCode __typename}redemptionType __typename}__typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}__typename}__typename}fragment UiExtensionInstallationFragment on UiExtensionInstallation{extension{approvalScopes{handle __typename}capabilities{apiAccess networkAccess blockProgress collectBuyerConsent{smsMarketing customerPrivacy __typename}__typename}apiVersion appId appUrl preloads{target namespace value __typename}appName extensionLocale extensionPoints name registrationUuid scriptUrl translations uuid version __typename}__typename}fragment CustomerCreditCardPaymentMethodFragment on CustomerCreditCardPaymentMethod{id cvvSessionId paymentInstrumentAccessorId paymentMethodIdentifier token displayLastDigits brand defaultPaymentMethod deletable requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaypalBillingAgreementPaymentMethodFragment on PaypalBillingAgreementPaymentMethod{paymentMethodIdentifier token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaymentLines on PaymentLine{stableId specialInstructions amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt due{...on PaymentLineDueEvent{event __typename}...on PaymentLineDueTime{time __typename}__typename}paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier creditCard{...on CreditCard{brand lastDigits name __typename}__typename}paymentAttributes __typename}...on GiftCardPaymentMethod{code balance{amount currencyCode __typename}__typename}...on RedeemablePaymentMethod{...RedeemablePaymentMethodFragment __typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier __typename}...on PaypalWalletContent{paypalBillingAddress:billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token paymentMethodIdentifier acceptedSubscriptionTerms expiresAt merchantId __typename}...on ApplePayWalletContent{data signature version lastDigits paymentMethodIdentifier header{applicationData ephemeralPublicKey publicKeyHash transactionId __typename}__typename}...on GooglePayWalletContent{signature signedMessage protocolVersion paymentMethodIdentifier __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken paymentMethodIdentifier __typename}__typename}__typename}...on LocalPaymentMethod{paymentMethodIdentifier name __typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on OffsitePaymentMethod{paymentMethodIdentifier name __typename}...on CustomPaymentMethod{id name additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name paymentAttributes __typename}...on ManualPaymentMethod{id name paymentMethodIdentifier __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{...CustomerCreditCardPaymentMethodFragment __typename}...on PaypalBillingAgreementPaymentMethod{...PaypalBillingAgreementPaymentMethodFragment __typename}...on NoopPaymentMethod{__typename}__typename}__typename}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl confirmationPage{url shouldRedirect __typename}orderStatusPageUrl shopPay shopPayInstallments paymentExtensionBrand analytics{checkoutCompletedEventId emitConversionEvent __typename}poNumber orderIdentity{buyerIdentifier id __typename}customerId isFirstOrder eligibleForMarketingOptIn purchaseOrder{...ReceiptPurchaseOrder __typename}orderCreationStatus{__typename}paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway financialPendingReason paymentDescriptor buyerActionInfo{...on MultibancoBuyerActionInfo{entity reference __typename}__typename}__typename}shopAppLinksAndResources{mobileUrl qrCodeUrl canTrackOrderUpdates shopInstallmentsViewSchedules shopInstallmentsMobileUrl installmentsHighlightEligible mobileUrlAttributionPayload shopAppEligible shopAppQrCodeKillswitch shopPayOrder payEscrowMayExist buyerHasShopApp buyerHasShopPay orderUpdateOptions __typename}postPurchasePageUrl postPurchasePageRequested postPurchaseVaultedPaymentMethodStatus paymentFlexibilityPaymentTermsTemplate{__typename dueDate dueInDays id translatedName type}__typename}...on ProcessingReceipt{id purchaseOrder{...ReceiptPurchaseOrder __typename}pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted __typename}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}__typename}__typename}__typename}fragment ReceiptPurchaseOrder on PurchaseOrder{__typename sessionToken totalAmountToPay{amount currencyCode __typename}checkoutCompletionTarget}'

SUBMIT_QUERY = 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{buyerProposal{...BuyerProposalDetails __typename}sellerProposal{...ProposalDetails __typename}errors{...on NegotiationError{code localizedMessage nonLocalizedMessage localizedMessageHtml...on RemoveTermViolation{message{code localizedDescription __typename}target __typename}...on AcceptNewTermViolation{message{code localizedDescription __typename}target __typename}...on ConfirmChangeViolation{message{code localizedDescription __typename}from to __typename}...on UnprocessableTermViolation{message{code localizedDescription __typename}target __typename}...on UnresolvableTermViolation{message{code localizedDescription __typename}target __typename}...on ApplyChangeViolation{message{code localizedDescription __typename}target from{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}to{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}__typename}...on InputValidationError{field __typename}...on PendingTermViolation{__typename}__typename}__typename}__typename}...on Throttled{pollAfter pollUrl queueToken buyerProposal{...BuyerProposalDetails __typename}__typename}...on CheckpointDenied{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token}...on ProcessingReceipt{id pollDelay}...on WaitingReceipt{id pollDelay}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url}...on CompletePaymentChallengeV2{challengeType challengeData}}timeout{millisecondsRemaining}}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated}}}}'

POLL_RECEIPT_QUERY = 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl orderStatusPageUrl shopPay shopPayInstallments analytics{checkoutCompletedEventId emitConversionEvent}poNumber orderIdentity{buyerIdentifier id}customerId isFirstOrder eligibleForMarketingOptIn orderCreationStatus{__typename}paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode}paymentGateway financialPendingReason paymentDescriptor}}...on ProcessingReceipt{id pollDelay}...on WaitingReceipt{id pollDelay}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url}...on CompletePaymentChallengeV2{challengeType challengeData}}timeout{millisecondsRemaining}}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}}}}'


def capture(data: str, first: str, last: str) -> Optional[str]:
    """Extract text between two strings"""
    try:
        start = data.index(first) + len(first)
        end = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None


def get_product_id(response_data: dict) -> Optional[Tuple[str, float]]:
    """Get cheapest available product from products.json response"""
    try:
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
                if available and product_id:
                    products[product_id] = price
        
        if products:
            min_price_product_id = min(products, key=products.get)
            price = products[min_price_product_id]
            return str(min_price_product_id), price
        
        return None
    except Exception:
        return None


def pick_addr(url: str, cc: str = None, rc: str = None) -> dict:
    """Pick appropriate address based on currency/country"""
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


def generate_email() -> str:
    """Generate random email"""
    first_names = ['john', 'james', 'robert', 'michael', 'william', 'david', 'richard', 'joseph']
    last_names = ['smith', 'johnson', 'williams', 'brown', 'jones', 'garcia', 'miller', 'davis']
    domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com']
    
    first = random.choice(first_names)
    last = random.choice(last_names)
    num = ''.join(random.choices(string.digits, k=3))
    domain = random.choice(domains)
    
    return f"{first}.{last}{num}@{domain}"


def get_headers(domain: str, url: str, session_token: str = None, web_build: str = None, source_token: str = None) -> dict:
    """Generate standard headers for Shopify requests"""
    headers = {
        'accept': 'application/json',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json',
        'origin': url,
        'referer': url,
        'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
    }
    
    if session_token:
        headers['x-checkout-one-session-token'] = session_token
        headers['shopify-checkout-client'] = 'checkout-web/1.0'
    
    if web_build:
        headers['x-checkout-web-build-id'] = web_build
        headers['x-checkout-web-deploy-stage'] = 'production'
        headers['x-checkout-web-server-handling'] = 'fast'
        headers['x-checkout-web-server-rendering'] = 'yes'
    
    if source_token:
        headers['x-checkout-web-source-id'] = source_token
    
    return headers


async def shopify_checkout(url: str, card: str, session: httpx.AsyncClient) -> Dict[str, Any]:
    """
    Complete Shopify GraphQL checkout flow
    
    Args:
        url: Shopify store URL (e.g., https://example.myshopify.com)
        card: Card string in format CC|MM|YYYY|CVV
        session: httpx AsyncClient session
        
    Returns:
        Dict with Response, Status, Gateway, Price, and card info
    """
    output = {
        "Response": "UNKNOWN_ERROR",
        "Status": False,
        "Gateway": "Unknown",
        "Price": "0.00",
        "cc": card
    }
    
    start_time = time.time()
    
    try:
        # Parse URL and card
        if not url.startswith('http'):
            url = f"https://{url}"
        url = url.rstrip('/')
        domain = urlparse(url).netloc
        
        cc, mes, ano, cvv = map(str.strip, card.split("|"))
        email = generate_email()
        
        # Step 1: Fetch products
        response = await session.get(f"{url}/products.json", timeout=15)
        if response.status_code != 200:
            output["Response"] = "SITE_ERROR"
            return output
            
        product_result = get_product_id(response.json())
        if not product_result:
            output["Response"] = "NO_PRODUCTS"
            return output
            
        product_id, price = product_result
        
        # Step 2: Get site key and create cart
        response = await session.get(url, timeout=15)
        site_key = capture(response.text, '"accessToken":"', '"')
        
        if not site_key:
            output["Response"] = "SITE_KEY_ERROR"
            return output
        
        # Create cart via GraphQL
        cart_headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': url,
            'x-shopify-storefront-access-token': site_key,
            'x-sdk-variant': 'portable-wallets',
            'x-start-wallet-checkout': 'true',
            'x-wallet-name': 'MoreOptions',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
        }
        
        cart_data = {
            'query': CART_CREATE_QUERY,
            'variables': {
                'input': {
                    'lines': [{
                        'merchandiseId': f'gid://shopify/ProductVariant/{product_id}',
                        'quantity': 1,
                        'attributes': [],
                    }],
                    'discountCodes': [],
                },
                'country': 'US',
                'language': 'EN',
            },
        }
        
        response = await session.post(
            f'{url}/api/unstable/graphql.json',
            params={'operation_name': 'cartCreate'},
            headers=cart_headers,
            json=cart_data
        )
        
        data = response.json()
        checkout_url = data.get("data", {}).get("result", {}).get("cart", {}).get("checkoutUrl")
        
        if not checkout_url:
            output["Response"] = "CART_ERROR"
            return output
        
        # Step 3: Go to checkout and extract session data
        response = await session.get(
            checkout_url,
            params={'skip_shop_pay': 'true'},
            follow_redirects=True
        )
        
        checkout_text = response.text
        
        # Extract checkout data
        payment_method_id = capture(checkout_text, "paymentMethodIdentifier&quot;:&quot;", "&quot")
        stable_id = capture(checkout_text, "stableId&quot;:&quot;", "&quot")
        queue_token = capture(checkout_text, "queueToken&quot;:&quot;", "&quot")
        currency_code = capture(checkout_text, "currencyCode&quot;:&quot;", "&quot") or "USD"
        country_code = capture(checkout_text, "countryCode&quot;:&quot;", "&quot") or "US"
        session_token = capture(checkout_text, 'serialized-session-token" content="&quot;', '&quot')
        source_token = capture(checkout_text, 'serialized-source-token" content="&quot;', '&quot')
        web_build = capture(checkout_text, 'serialized-client-bundle-info" content="{&quot;browsers&quot;:&quot;latest&quot;,&quot;format&quot;:&quot;es&quot;,&quot;locale&quot;:&quot;en&quot;,&quot;sha&quot;:&quot;', '&quot')
        tax = capture(checkout_text, "totalTaxAndDutyAmount&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;", "&quot") or "0.0"
        
        # Get gateway info
        gateway = capture(checkout_text, 'extensibilityDisplayName&quot;:&quot;', '&quot')
        if gateway == "Shopify Payments":
            gateway = "Normal"
        elif not gateway:
            gateway = "Unknown"
        
        if not session_token:
            output["Response"] = "SESSION_ERROR"
            return output
        
        # Get address based on currency/country
        addr = pick_addr(url, cc=currency_code, rc=country_code)
        
        # Step 4: Create payment session
        payment_session_data = {
            'credit_card': {
                'number': cc,
                'month': mes,
                'year': ano,
                'verification_value': cvv,
                'start_month': None,
                'start_year': None,
                'issue_number': '',
                'name': 'Checkout User',
            },
            'payment_session_scope': domain
        }
        
        response = await session.post(
            'https://checkout.pci.shopifyinc.com/sessions',
            headers={
                'accept': 'application/json',
                'content-type': 'application/json',
                'origin': 'https://checkout.pci.shopifyinc.com',
                'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
            },
            json=payment_session_data
        )
        
        session_id = response.json().get("id")
        if not session_id:
            output["Response"] = "PAYMENT_SESSION_ERROR"
            return output
        
        await asyncio.sleep(0.1)
        
        # Step 5: First proposal (shipping)
        checkout_headers = get_headers(domain, url, session_token, web_build, source_token)
        
        shipping_variables = {
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
                            'firstName': 'Checkout',
                            'lastName': 'User',
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
                    'deliveryMethodTypes': ['SHIPPING'],
                    'expectedTotalPrice': {'any': True},
                    'destinationChanged': False,
                }],
                'noDeliveryRequired': [],
                'useProgressiveRates': False,
                'prefetchShippingRatesStrategy': None,
                'supportsSplitShipping': True,
            },
            'deliveryExpectations': {'deliveryExpectationLines': []},
            'merchandise': {
                'merchandiseLines': [{
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
                        'value': {'amount': f"{price}", 'currencyCode': currency_code}
                    },
                    'lineComponentsSource': None,
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
                        'firstName': 'Checkout',
                        'lastName': 'User',
                        'zoneCode': addr["zoneCode"],
                        'phone': addr["phone"],
                    },
                },
            },
            'buyerIdentity': {
                'customer': {
                    'presentmentCurrency': currency_code,
                    'countryCode': country_code,
                },
                'email': email,
                'emailChanged': False,
                'phoneCountryCode': country_code,
                'marketingConsent': [],
                'shopPayOptInPhone': {'countryCode': country_code},
                'rememberMe': False,
            },
            'tip': {'tipLines': []},
            'taxes': {
                'proposedAllocations': None,
                'proposedTotalAmount': {
                    'value': {'amount': f"{tax}", 'currencyCode': currency_code}
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
            'cartMetafields': [],
        }
        
        response = await session.post(
            f'{url}/checkouts/unstable/graphql',
            params={'operationName': 'Proposal'},
            headers=checkout_headers,
            json={'query': PROPOSAL_QUERY, 'variables': shipping_variables, 'operationName': 'Proposal'}
        )
        
        # Extract tax and handle from response
        resp_text = response.text
        
        match = re.search(r'"totalTaxAndDutyAmount"\s*:\s*{[^}]*"value"\s*:\s*{[^}]*"amount"\s*:\s*"([\d.]+)"', resp_text)
        if not match:
            match = re.search(r'"totalAmountIncludedInTarget"\s*:\s*{[^}]*"value"\s*:\s*{[^}]*"amount"\s*:\s*"([\d.]+)"', resp_text)
        
        ttax = float(match.group(1)) if match else 0.0
        
        # Get delivery handle
        handle_match = re.search(r'"handle"\s*:\s*"([^"]+)"', resp_text)
        handle = handle_match.group(1) if handle_match else ""
        
        # Get shipping amount
        shipping_match = re.search(r'"deliveryLines".*?"amount".*?"value".*?"amount"\s*:\s*"([\d.]+)"', resp_text)
        shipping_amount = float(shipping_match.group(1)) if shipping_match else 0.0
        
        # Calculate total
        total = price + ttax + shipping_amount
        
        await asyncio.sleep(0.1)
        
        # Step 6: Second proposal with selected shipping
        shipping_variables['delivery']['deliveryLines'][0]['selectedDeliveryStrategy'] = {
            'deliveryStrategyByHandle': {
                'handle': handle,
                'customDeliveryRate': False,
            },
            'options': {},
        }
        shipping_variables['delivery']['deliveryLines'][0]['deliveryMethodTypes'] = ['SHIPPING', 'LOCAL']
        
        response = await session.post(
            f'{url}/checkouts/unstable/graphql',
            params={'operationName': 'Proposal'},
            headers=checkout_headers,
            json={'query': PROPOSAL_QUERY, 'variables': shipping_variables, 'operationName': 'Proposal'}
        )
        
        await asyncio.sleep(0.1)
        
        # Step 7: Submit for completion
        submit_variables = {
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
                                'firstName': 'Checkout',
                                'lastName': 'User',
                                'zoneCode': addr["zoneCode"],
                                'phone': addr["phone"],
                                'oneTimeUse': False,
                            },
                        },
                        'selectedDeliveryStrategy': {
                            'deliveryStrategyByHandle': {
                                'handle': handle,
                                'customDeliveryRate': False,
                            },
                            'options': {'phone': addr["phone"]},
                        },
                        'targetMerchandiseLines': {
                            'lines': [{'stableId': stable_id}],
                        },
                        'deliveryMethodTypes': ['SHIPPING'],
                        'expectedTotalPrice': {
                            'value': {'amount': f'{shipping_amount}', 'currencyCode': currency_code}
                        },
                        'destinationChanged': False,
                    }],
                    'noDeliveryRequired': [],
                    'useProgressiveRates': False,
                    'prefetchShippingRatesStrategy': None,
                    'supportsSplitShipping': True,
                },
                'deliveryExpectations': {'deliveryExpectationLines': []},
                'merchandise': {
                    'merchandiseLines': [{
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
                            'value': {'amount': f'{price}', 'currencyCode': currency_code}
                        },
                        'lineComponentsSource': None,
                        'lineComponents': [],
                    }],
                },
                'memberships': {'memberships': []},
                'payment': {
                    'totalAmount': {'any': True},
                    'paymentLines': [{
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
                                        'firstName': 'Checkout',
                                        'lastName': 'User',
                                        'zoneCode': addr["zoneCode"],
                                        'phone': addr["phone"],
                                    },
                                },
                            },
                        },
                        'amount': {
                            'value': {'amount': f'{total}', 'currencyCode': currency_code}
                        },
                    }],
                    'billingAddress': {
                        'streetAddress': {
                            'address1': addr["address1"],
                            'city': addr["city"],
                            'countryCode': addr["countryCode"],
                            'postalCode': addr["postalCode"],
                            'firstName': 'Checkout',
                            'lastName': 'User',
                            'zoneCode': addr["zoneCode"],
                            'phone': addr["phone"],
                        },
                    },
                },
                'buyerIdentity': {
                    'customer': {
                        'presentmentCurrency': currency_code,
                        'countryCode': country_code,
                    },
                    'email': email,
                    'emailChanged': False,
                    'phoneCountryCode': country_code,
                    'marketingConsent': [],
                    'shopPayOptInPhone': {'countryCode': country_code},
                    'rememberMe': False,
                },
                'tip': {'tipLines': []},
                'taxes': {
                    'proposedAllocations': None,
                    'proposedTotalAmount': {
                        'value': {'amount': f'{ttax}', 'currencyCode': currency_code}
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
                'cartMetafields': [],
            },
            'attemptToken': f'{source_token}-checkout',
            'metafields': [],
            'analytics': {
                'requestUrl': checkout_url,
                'pageId': '0cde623b-7B13-4911-E150-61A3736179ED',
            },
        }
        
        response = await session.post(
            f'{url}/checkouts/unstable/graphql',
            params={'operationName': 'SubmitForCompletion'},
            headers=checkout_headers,
            json={'query': SUBMIT_QUERY, 'variables': submit_variables, 'operationName': 'SubmitForCompletion'}
        )
        
        resp_text = response.text
        
        # Extract receipt ID
        receipt_id = capture(resp_text, '"receiptId":"', '"') or capture(resp_text, '"id":"', '"')
        
        if not receipt_id:
            # Check for direct error
            if 'processingError' in resp_text:
                error_code = capture(resp_text, '"code":"', '"')
                if error_code:
                    output["Response"] = error_code
                    output["Status"] = True
                    output["Gateway"] = gateway
                    output["Price"] = f"{total:.2f}"
                    return output
        
        await asyncio.sleep(0.5)
        
        # Step 8: Poll for receipt
        poll_data = {
            'query': POLL_RECEIPT_QUERY,
            'variables': {
                'receiptId': receipt_id,
                'sessionToken': session_token,
            },
            'operationName': 'PollForReceipt',
        }
        
        # Poll up to 3 times
        for _ in range(3):
            response = await session.post(
                f'{url}/checkouts/unstable/graphql',
                params={'operationName': 'PollForReceipt'},
                headers=checkout_headers,
                json=poll_data
            )
            
            resp_text = response.text
            
            if 'WaitingReceipt' not in resp_text and 'ProcessingReceipt' not in resp_text:
                break
            
            await asyncio.sleep(3)
        
        # Parse final response
        resp_json = response.json()
        result = resp_json.get('data', {}).get('receipt', {}).get('processingError', {}).get('code')
        
        elapsed = time.time() - start_time
        
        output["Gateway"] = gateway
        output["Price"] = f"{total:.2f}"
        output["Status"] = True
        
        # Determine response
        if "shopify_payments" in resp_text.lower() and "processingerror" not in resp_text.lower():
            output["Response"] = "ORDER_PLACED"
        elif result == 'CARD_DECLINED':
            output["Response"] = "CARD_DECLINED"
        elif result == 'INCORRECT_NUMBER':
            output["Response"] = "INCORRECT_NUMBER"
        elif result == 'GENERIC_ERROR':
            output["Response"] = "GENERIC_ERROR"
        elif result == 'AUTHENTICATION_FAILED':
            output["Response"] = "AUTHENTICATION_FAILED"
        elif "FRAUD_SUSPECTED" in resp_text:
            output["Response"] = "FRAUD_SUSPECTED"
        elif "INCORRECT_ADDRESS" in resp_text:
            output["Response"] = "INCORRECT_ADDRESS"
        elif "INCORRECT_ZIP" in resp_text:
            output["Response"] = "INCORRECT_ZIP"
        elif "INCORRECT_PIN" in resp_text:
            output["Response"] = "INCORRECT_PIN"
        elif "insufficient_funds" in resp_text.lower() or "INSUFFICIENT_FUNDS" in resp_text:
            output["Response"] = "INSUFFICIENT_FUNDS"
        elif "INVALID_CVC" in resp_text or "INCORRECT_CVC" in resp_text:
            output["Response"] = "INCORRECT_CVC"
        elif "CompletePaymentChallenge" in resp_text:
            output["Response"] = "3DS_REQUIRED"
        elif result:
            output["Response"] = result
        else:
            output["Response"] = "PROCESSED"
        
        return output
        
    except httpx.TimeoutException:
        output["Response"] = "TIMEOUT"
        return output
    except Exception as e:
        output["Response"] = f"ERROR: {str(e)[:50]}"
        return output


async def main():
    """Main entry point for terminal usage"""
    print("=" * 60)
    print("SHOPIFY GRAPHQL CHECKOUT".center(60))
    print("=" * 60)
    
    # Get website
    website = input("\n[?] Enter Shopify website (e.g., example.myshopify.com): ").strip()
    if not website:
        print("[!] No website provided")
        return
    
    # Get card
    card = input("[?] Enter card (CC|MM|YYYY|CVV): ").strip()
    if not card or card.count('|') != 3:
        print("[!] Invalid card format")
        return
    
    print(f"\n[*] Processing checkout on {website}...")
    
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as session:
        result = await shopify_checkout(website, card, session)
    
    print("\n" + "=" * 60)
    print("RESULT".center(60))
    print("=" * 60)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
