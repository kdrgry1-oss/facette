"""Shipping eligibility is based on merchandise after discounts, never charges.

Gift cards/store credit are payment instruments, not merchandise discounts.
The threshold is supplied by settings/campaigns; no tenant amount is hardcoded.
"""
from decimal import Decimal, ROUND_HALF_UP


def shipping_quote(subtotal, discounts, threshold, fee, free_shipping_promotion=False):
    money = lambda value: Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    basis = max(Decimal(0), money(subtotal) - sum((money(d) for d in discounts), Decimal(0)))
    # A promotion flag must not bypass a configured minimum after payment/points discounts.
    free = basis >= money(threshold) if threshold is not None else bool(free_shipping_promotion)
    return {"basis": float(basis), "free": free, "cost": 0.0 if free else float(money(fee))}
