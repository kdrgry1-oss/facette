"""
Coupons (Kupon) module — code-based discount coupons.

Supports:
- Type: percent or fixed amount (TRY)
- Min cart total, applicable categories/products, usage limits (total + per user)
- Start/end dates, active flag
- Usage tracking via `coupon_redemptions` collection

Storefront: POST /api/coupons/apply {code, cart_total, items:[{product_id, category_id, qty, price}]}
  Returns {valid: bool, discount: float, reason?: str}
Admin:  /api/admin/coupons  CRUD + stats
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone
from typing import Optional, List
import uuid

from .deps import db, require_admin, logger


admin_router = APIRouter(prefix="/admin/coupons", tags=["admin-coupons"])
public_router = APIRouter(prefix="/coupons", tags=["coupons"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@admin_router.get("")
async def list_coupons(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
    active_only: bool = False,
    current_user: dict = Depends(require_admin),
):
    q: dict = {}
    if search:
        q["$or"] = [{"code": {"$regex": search, "$options": "i"}}, {"title": {"$regex": search, "$options": "i"}}]
    if active_only:
        q["is_active"] = True
    total = await db.coupons.count_documents(q)
    skip = (page - 1) * limit
    items = await db.coupons.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    # Annotate redemption counts
    for c in items:
        c["redeemed_count"] = await db.coupon_redemptions.count_documents({"coupon_id": c["id"]})
    return {"items": items, "total": total, "page": page, "pages": (total + limit - 1) // limit}


@admin_router.post("")
async def create_coupon(payload: dict, current_user: dict = Depends(require_admin)):
    code = (payload.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Kupon kodu gerekli")
    if await db.coupons.find_one({"code": code}):
        raise HTTPException(status_code=409, detail="Bu kupon kodu zaten kullanılıyor")
    doc = {
        "id": str(uuid.uuid4()),
        "code": code,
        "title": payload.get("title", ""),
        "type": payload.get("type", "percent"),  # percent | fixed
        "value": float(payload.get("value", 0) or 0),
        "min_cart_total": float(payload.get("min_cart_total", 0) or 0),
        "max_discount": float(payload.get("max_discount", 0) or 0) or None,  # cap for percent
        "categories": payload.get("categories", []),
        "products": payload.get("products", []),
        "usage_limit": int(payload.get("usage_limit", 0) or 0) or None,
        "usage_limit_per_user": int(payload.get("usage_limit_per_user", 0) or 0) or None,
        "start_at": payload.get("start_at"),
        "end_at": payload.get("end_at"),
        "is_active": bool(payload.get("is_active", True)),
        "first_order_only": bool(payload.get("first_order_only", False)),
        "free_shipping": bool(payload.get("free_shipping", False)),
        "created_at": _utcnow(),
        "created_by": current_user.get("email", ""),
    }
    await db.coupons.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "coupon": doc}


@admin_router.put("/{cid}")
async def update_coupon(cid: str, payload: dict, current_user: dict = Depends(require_admin)):
    allowed = (
        "title", "type", "value", "min_cart_total", "max_discount",
        "categories", "products", "usage_limit", "usage_limit_per_user",
        "start_at", "end_at", "is_active", "first_order_only", "free_shipping",
    )
    update = {k: v for k, v in payload.items() if k in allowed}
    update["updated_at"] = _utcnow()
    res = await db.coupons.update_one({"id": cid}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kupon bulunamadı")
    return {"success": True}


@admin_router.delete("/{cid}")
async def delete_coupon(cid: str, current_user: dict = Depends(require_admin)):
    res = await db.coupons.delete_one({"id": cid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kupon bulunamadı")
    return {"success": True}


@admin_router.get("/{cid}/redemptions")
async def coupon_redemptions(cid: str, current_user: dict = Depends(require_admin)):
    rows = await db.coupon_redemptions.find({"coupon_id": cid}, {"_id": 0}).sort("redeemed_at", -1).to_list(500)
    return {"items": rows, "total": len(rows)}


# ---------------- Public: apply a coupon at checkout ----------------

@public_router.post("/apply")
async def apply_coupon(payload: dict):
    code = (payload.get("code") or "").strip().upper()
    if not code:
        return {"valid": False, "reason": "Kupon kodu boş", "discount": 0}

    c = await db.coupons.find_one({"code": code}, {"_id": 0})
    if not c:
        return {"valid": False, "reason": "Kupon bulunamadı", "discount": 0}
    if not c.get("is_active"):
        return {"valid": False, "reason": "Kupon pasif", "discount": 0}

    now = datetime.now(timezone.utc)
    if c.get("start_at") and c["start_at"] > now.isoformat():
        return {"valid": False, "reason": "Kupon henüz başlamadı", "discount": 0}
    if c.get("end_at") and c["end_at"] < now.isoformat():
        return {"valid": False, "reason": "Kupon süresi dolmuş", "discount": 0}

    cart_total = float(payload.get("cart_total") or 0)
    if c.get("min_cart_total", 0) and cart_total < c["min_cart_total"]:
        return {"valid": False, "reason": f"Minimum sepet tutarı ₺{c['min_cart_total']:.2f}", "discount": 0}

    # Usage limits
    if c.get("usage_limit"):
        used = await db.coupon_redemptions.count_documents({"coupon_id": c["id"]})
        if used >= c["usage_limit"]:
            return {"valid": False, "reason": "Kupon kullanım limiti dolmuş", "discount": 0}

    user_id = payload.get("user_id")
    if user_id and c.get("usage_limit_per_user"):
        used_by_user = await db.coupon_redemptions.count_documents({"coupon_id": c["id"], "user_id": user_id})
        if used_by_user >= c["usage_limit_per_user"]:
            return {"valid": False, "reason": "Bu kupon için kullanım hakkınız kalmadı", "discount": 0}

    # First-order only guard
    if user_id and c.get("first_order_only"):
        prior = await db.orders.count_documents({"user_id": user_id, "status": {"$ne": "cancelled"}})
        if prior > 0:
            return {"valid": False, "reason": "Kupon sadece ilk siparişe özeldir", "discount": 0}

    # Category/product filter — applies discount only on matching items
    allowed_cats = set(c.get("categories") or [])
    allowed_pids = set(c.get("products") or [])
    items = payload.get("items") or []

    if allowed_cats or allowed_pids:
        eligible_total = 0.0
        for it in items:
            pid = it.get("product_id")
            cid_ = it.get("category_id")
            if (pid and pid in allowed_pids) or (cid_ and cid_ in allowed_cats):
                eligible_total += float(it.get("price", 0)) * int(it.get("qty", 0) or 0)
        base = eligible_total
    else:
        base = cart_total

    discount = 0.0
    if c.get("type") == "percent":
        discount = base * (c.get("value", 0) / 100.0)
        if c.get("max_discount"):
            discount = min(discount, c["max_discount"])
    else:  # fixed
        discount = min(c.get("value", 0), base)

    discount = round(discount, 2)
    return {
        "valid": True,
        "coupon_id": c["id"],
        "code": c["code"],
        "title": c.get("title", ""),
        "type": c.get("type"),
        "value": c.get("value"),
        "discount": discount,
        "free_shipping": bool(c.get("free_shipping")),
    }


@public_router.post("/redeem")
async def redeem_coupon(payload: dict):
    """Record a redemption. Called by orders.create after successful save."""
    cid = payload.get("coupon_id")
    if not cid:
        return {"recorded": False}
    await db.coupon_redemptions.insert_one({
        "id": str(uuid.uuid4()),
        "coupon_id": cid,
        "order_id": payload.get("order_id"),
        "user_id": payload.get("user_id"),
        "discount": float(payload.get("discount", 0)),
        "redeemed_at": _utcnow(),
    })
    return {"recorded": True}
