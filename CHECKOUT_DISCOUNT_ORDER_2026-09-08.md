# Checkout discount order and authoritative breakdown

User-approved order: automatic product campaign, welcome/entered coupon, bank-transfer
discount. No brand/code/percentage constants introduced. Existing campaign priorities
remain effective within each calculation stage; manual coupon preference still wins
non-combinable selection. First-order eligibility, redemption, stock and payment-status
code is unchanged. The same evaluate_cart_promotions function serves previews and orders.

The lower checkout summary now renders the engine's applied promotions, in returned
order, instead of reconstructing product/coupon shares from a cached campaign badge.
Only the embedded sale-price difference is shown separately. Scope restrictions,
excluded promotions and caps therefore use the same amounts in both summaries.

Regression coverage: 3790 -> launch 758 -> welcome 303.20 -> bank 136.44 -> shipping
99 -> total 2691.36; non-combinable coupons, one-sided combinability, stack groups,
exclusions, free-shipping threshold, scoped products, caps, manual sale-price display.

No real order, payment, customer, redemption or admin campaign configuration is created
or changed as part of verification. The repository's real-card-order smoke is deliberately
not run: customer payment/stock mutations are outside this test authorization.
