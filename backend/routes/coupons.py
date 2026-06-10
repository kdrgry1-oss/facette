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
        "auto_apply": bool(payload.get("auto_apply", False)),
        # --- nth_discount ("X al Y öde") alanları (önceden create'te kaydedilmiyordu) ---
        "min_quantity": int(payload.get("min_quantity", 0) or 0) or None,
        "buy_quantity": int(payload.get("buy_quantity", 0) or 0) or None,
        "free_quantity": int(payload.get("free_quantity", 1) or 1),
        "get_discount": float(payload.get("get_discount", 0) or 0),
        # --- Madde 4 motor alanları ---
        "priority": int(payload.get("priority", 0) or 0),
        "combinable": bool(payload.get("combinable", False)),
        "stack_group": (payload.get("stack_group") or "").strip() or None,
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
        "start_at", "end_at", "is_active", "first_order_only", "free_shipping", "auto_apply",
        "min_quantity", "buy_quantity", "free_quantity", "get_discount",
        "priority", "combinable", "stack_group",
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

@public_router.post("/available")
async def available_coupons(payload: dict):
    """Trendyol Go benzeri: bu sepet için kullanıcının kullanabileceği aktif kuponları döner.
    Hesaplanmış discount değerlerini de içerir (tıklanınca sepete direkt uygulanır).
    Payload: {cart_total, items, user_id?}
    """
    cart_total = float(payload.get("cart_total") or 0)
    user_id = payload.get("user_id")
    items = payload.get("items") or []
    now_iso = datetime.now(timezone.utc).isoformat()

    q: dict = {"is_active": True}
    # Zaman penceresi (tarih verilmişse)
    q["$and"] = [
        {"$or": [{"start_at": None}, {"start_at": {"$lte": now_iso}}, {"start_at": {"$exists": False}}]},
        {"$or": [{"end_at": None}, {"end_at": {"$gte": now_iso}}, {"end_at": {"$exists": False}}]},
    ]
    coupons = await db.coupons.find(q, {"_id": 0}).sort("value", -1).to_list(length=50)

    out = []
    for c in coupons:
        # Min tutar
        min_total = float(c.get("min_cart_total") or 0)
        if min_total and cart_total < min_total:
            continue
        # İlk siparişte limit
        if user_id and c.get("first_order_only"):
            prior = await db.orders.count_documents({"user_id": user_id, "status": {"$ne": "cancelled"}})
            if prior > 0:
                continue
        # Kullanım limiti
        if c.get("usage_limit"):
            used = await db.coupon_redemptions.count_documents({"coupon_id": c["id"]})
            if used >= c["usage_limit"]:
                continue
        if user_id and c.get("usage_limit_per_user"):
            used_by = await db.coupon_redemptions.count_documents({"coupon_id": c["id"], "user_id": user_id})
            if used_by >= c["usage_limit_per_user"]:
                continue
        # Kategori/ürün filtresi varsa eligible_total hesapla
        allowed_cats = set(c.get("categories") or [])
        allowed_pids = set(c.get("products") or [])
        if allowed_cats or allowed_pids:
            eligible_total = 0.0
            for it in items:
                pid = it.get("product_id")
                cid_ = it.get("category_id")
                if (pid and pid in allowed_pids) or (cid_ and cid_ in allowed_cats):
                    eligible_total += float(it.get("price", 0)) * int(it.get("qty", 0) or 0)
            base = eligible_total
            if base <= 0:
                continue
        else:
            base = cart_total
        # Discount hesapla
        discount = 0.0
        if c.get("type") == "percent":
            discount = base * (c.get("value", 0) / 100.0)
            if c.get("max_discount"):
                discount = min(discount, c["max_discount"])
        else:
            discount = min(c.get("value", 0), base)
        discount = round(discount, 2)
        if discount <= 0 and not c.get("free_shipping"):
            continue
        out.append({
            "id": c["id"], "code": c["code"], "title": c.get("title", ""),
            "type": c.get("type"), "value": c.get("value"),
            "min_cart_total": min_total, "discount": discount,
            "free_shipping": bool(c.get("free_shipping")),
            "end_at": c.get("end_at"),
        })
    # En iyi indirimi yukarı koy
    out.sort(key=lambda x: x["discount"], reverse=True)
    return {"items": out, "total": len(out)}


def _compute_discount(c: dict, cart_total: float, items: list) -> float:
    """Saf indirim matematigi (dogrulama YOK). Kapsam(scope) + tip(nth/percent/fixed).
    items fiyatlari olceklenmis verilirse (stacking) sonuc kalan tabana gore otomatik cikar."""
    allowed_cats = set(c.get("categories") or [])
    allowed_pids = set(c.get("products") or [])
    if allowed_cats or allowed_pids:
        base = 0.0
        for it in items:
            pid = it.get("product_id"); cid_ = it.get("category_id")
            if (pid and pid in allowed_pids) or (cid_ and cid_ in allowed_cats):
                base += float(it.get("price", 0)) * int(it.get("qty", 0) or 0)
    else:
        base = cart_total
    ctype = c.get("type")
    discount = 0.0
    if ctype == "nth_discount":
        bq = int(c.get("buy_quantity") or 2)
        fq = int(c.get("free_quantity") or 1)
        gd = float(c.get("get_discount") or 0)
        units = []
        for it in items:
            pid = it.get("product_id"); cid_ = it.get("category_id")
            inscope = (not allowed_cats and not allowed_pids) or (pid and pid in allowed_pids) or (cid_ and cid_ in allowed_cats)
            if inscope:
                for _ in range(int(it.get("qty", 0) or 0)):
                    units.append(float(it.get("price", 0) or 0))
        units.sort()  # en ucuz basta
        groups = (len(units) // bq) if bq else 0
        n_disc = groups * fq
        for k in range(min(n_disc, len(units))):
            discount += units[k] * (gd / 100.0)
    elif ctype == "percent":
        discount = base * (c.get("value", 0) / 100.0)
        if c.get("max_discount"):
            discount = min(discount, c["max_discount"])
    else:  # fixed
        discount = min(c.get("value", 0), base)
    return round(discount, 2)


async def _evaluate_single(c: dict, cart_total: float, items: list,
                           user_id=None, email: str = "") -> dict:
    """Tek kuponu dogrular + indirimini hesaplar. apply_coupon VE motor ayni cekirdegi kullanir."""
    if not c.get("is_active"):
        return {"valid": False, "reason": "Kupon pasif", "discount": 0}
    now = datetime.now(timezone.utc)
    if c.get("start_at") and c["start_at"] > now.isoformat():
        return {"valid": False, "reason": "Kupon henüz başlamadı", "discount": 0}
    if c.get("end_at") and c["end_at"] < now.isoformat():
        return {"valid": False, "reason": "Kupon süresi dolmuş", "discount": 0}
    if c.get("min_cart_total", 0) and cart_total < c["min_cart_total"]:
        return {"valid": False, "reason": f"Minimum sepet tutarı ₺{c['min_cart_total']:.2f}", "discount": 0}
    if c.get("usage_limit"):
        used = await db.coupon_redemptions.count_documents({"coupon_id": c["id"]})
        if used >= c["usage_limit"]:
            return {"valid": False, "reason": "Kupon kullanım limiti dolmuş", "discount": 0}
    if user_id and c.get("usage_limit_per_user"):
        used_by_user = await db.coupon_redemptions.count_documents({"coupon_id": c["id"], "user_id": user_id})
        if used_by_user >= c["usage_limit_per_user"]:
            return {"valid": False, "reason": "Bu kupon için kullanım hakkınız kalmadı", "discount": 0}
    if c.get("first_order_only"):
        em = (email or "").strip().lower()
        ors = []
        if user_id:
            ors.append({"user_id": user_id})
        if em:
            ors.append({"customer_email": em})
        if not ors:
            return {"valid": False, "reason": "İlk siparişe özel kupon için giriş yapın", "discount": 0}
        prior = await db.orders.count_documents({"$or": ors, "status": {"$ne": "cancelled"}})
        if prior > 0:
            return {"valid": False, "reason": "Kupon sadece ilk siparişe özeldir", "discount": 0}
    if c.get("min_quantity"):
        total_qty = sum(int(it.get("qty", 0) or 0) for it in items)
        if total_qty < int(c["min_quantity"]):
            return {"valid": False, "reason": f"En az {int(c['min_quantity'])} ürün gerekli", "discount": 0}
    discount = _compute_discount(c, cart_total, items)
    return {
        "valid": True, "coupon_id": c["id"], "code": c["code"],
        "title": c.get("title", ""), "type": c.get("type"), "value": c.get("value"),
        "discount": discount, "free_shipping": bool(c.get("free_shipping")),
    }


@public_router.post("/apply")
async def apply_coupon(payload: dict):
    code = (payload.get("code") or "").strip().upper()
    if not code:
        return {"valid": False, "reason": "Kupon kodu boş", "discount": 0}
    c = await db.coupons.find_one({"code": code}, {"_id": 0})
    if not c:
        return {"valid": False, "reason": "Kupon bulunamadı", "discount": 0}
    cart_total = float(payload.get("cart_total") or 0)
    items = payload.get("items") or []
    email = payload.get("email") or payload.get("customer_email") or ""
    return await _evaluate_single(c, cart_total, items, payload.get("user_id"), email)


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


# ==================== KAMPANYALAR (Campaigns) ====================
# Admin "Kampanyalar" sayfası /api/campaigns çağırır. Kampanya = kupon olduğundan
# bu uçlar db.coupons üzerine eşlenir (tip: percentage<->percent, free_shipping bayrağı).
campaigns_router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _coupon_to_campaign(c: dict) -> dict:
    t = c.get("type", "percent")
    if c.get("free_shipping"):
        ctype = "free_shipping"
    elif t == "percent":
        ctype = "percentage"
    else:
        ctype = t
    return {
        "id": c.get("id"),
        "name": c.get("title") or c.get("code") or "",
        "code": c.get("code", ""),
        "type": ctype,
        "value": c.get("value", 0),
        "min_order_amount": c.get("min_cart_total", 0),
        "usage_limit": c.get("usage_limit") or 0,
        "is_active": c.get("is_active", True),
        "start_date": c.get("start_at"),
        "end_date": c.get("end_at"),
        "redeemed_count": c.get("redeemed_count", 0),
        "auto_apply": c.get("auto_apply", False),
        "first_order_only": c.get("first_order_only", False),
        "usage_limit_per_user": c.get("usage_limit_per_user") or 0,
        "min_quantity": c.get("min_quantity") or 0,
        "buy_quantity": c.get("buy_quantity") or 0,
        "free_quantity": c.get("free_quantity") or 1,
        "get_discount": c.get("get_discount") or 0,
        "max_discount": c.get("max_discount") or 0,
        "priority": c.get("priority", 0),
        "combinable": bool(c.get("combinable", False)),
        "stack_group": c.get("stack_group") or "",
        "categories": c.get("categories") or [],
        "products": c.get("products") or [],
    }


def _campaign_to_coupon_fields(payload: dict) -> dict:
    ctype = payload.get("type") or "percentage"
    if ctype == "fixed":
        type_db = "fixed"
    elif ctype == "nth_discount":
        type_db = "nth_discount"
    else:
        type_db = "percent"  # "percentage" ve "free_shipping" yuzde tabanli calisir
    return {
        "title": payload.get("name") or payload.get("title") or "",
        "type": type_db,
        "value": float(payload.get("value", 0) or 0),
        "min_cart_total": float(payload.get("min_order_amount", payload.get("min_cart_total", 0)) or 0),
        "usage_limit": int(payload.get("usage_limit", 0) or 0) or None,
        # --- Kural alanlari (onceden tasinmiyordu; "ilk uyelik herkese" bug'inin koku) ---
        "usage_limit_per_user": int(payload.get("usage_limit_per_user", 0) or 0) or None,
        "first_order_only": bool(payload.get("first_order_only", False)),
        "min_quantity": int(payload.get("min_quantity", 0) or 0) or None,
        "categories": payload.get("categories") or [],
        "products": payload.get("products") or [],
        "max_discount": (float(payload["max_discount"]) if payload.get("max_discount") else None),
        # --- "X al Y ode / N. urune %Z" icin ---
        "buy_quantity": int(payload.get("buy_quantity", 0) or 0) or None,
        "free_quantity": int(payload.get("free_quantity", 1) or 1),
        "get_discount": float(payload.get("get_discount", 0) or 0),
        "start_at": payload.get("start_date") or payload.get("start_at"),
        "end_at": payload.get("end_date") or payload.get("end_at"),
        "is_active": bool(payload.get("is_active", True)),
        "free_shipping": ctype == "free_shipping",
        "auto_apply": bool(payload.get("auto_apply", False)),
        # --- Madde 4 motor alanları ---
        "priority": int(payload.get("priority", 0) or 0),
        "combinable": bool(payload.get("combinable", False)),
        "stack_group": (payload.get("stack_group") or "").strip() or None,
    }


@campaigns_router.get("")
async def list_campaigns(current_user: dict = Depends(require_admin)):
    """Kampanya listesi — frontend düz dizi bekler (res.data)."""
    items = await db.coupons.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    out = []
    for c in items:
        c["redeemed_count"] = await db.coupon_redemptions.count_documents({"coupon_id": c.get("id")})
        out.append(_coupon_to_campaign(c))
    return out


@campaigns_router.post("")
async def create_campaign(payload: dict, current_user: dict = Depends(require_admin)):
    code = (payload.get("code") or "").strip().upper()
    if not code and payload.get("auto_apply"):
        code = "AUTO-" + uuid.uuid4().hex[:6].upper()
    if not code:
        raise HTTPException(status_code=400, detail="Kampanya kodu gerekli")
    if await db.coupons.find_one({"code": code}):
        raise HTTPException(status_code=409, detail="Bu kod zaten kullanılıyor")
    doc = {
        "id": str(uuid.uuid4()),
        "code": code,
        "categories": [],
        "products": [],
        "max_discount": None,
        "usage_limit_per_user": None,
        "first_order_only": False,
        "created_at": _utcnow(),
        "created_by": current_user.get("email", ""),
    }
    doc.update(_campaign_to_coupon_fields(payload))
    await db.coupons.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "campaign": _coupon_to_campaign(doc)}


@campaigns_router.put("/{cid}")
async def update_campaign(cid: str, payload: dict, current_user: dict = Depends(require_admin)):
    update = _campaign_to_coupon_fields(payload)
    update["updated_at"] = _utcnow()
    res = await db.coupons.update_one({"id": cid}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı")
    return {"success": True}


@campaigns_router.delete("/{cid}")
async def delete_campaign(cid: str, current_user: dict = Depends(require_admin)):
    res = await db.coupons.delete_one({"id": cid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı")
    return {"success": True}


# ============================================================================
# Madde 4 — Kampanya Motoru (P3)
# Kilitli kurallar: priority sirali; combinable=False MUNHASIR; combinable=True
# stack_group basina bir, KALAN tabana ARDISIK (once %20 sonra %10); GLOBAL TAVAN.
# ============================================================================

async def _promo_cap_pct() -> float:
    s = await db.settings.find_one({"id": "main"}, {"_id": 0, "promo_max_discount_pct": 1}) or {}
    try:
        v = float(s.get("promo_max_discount_pct", 70) or 70)
    except Exception:
        v = 70.0
    return v if v > 0 else 70.0


async def evaluate_cart_promotions(cart_total: float, items: list,
                                   user_id=None, email: str = "", entered_code: str = "") -> dict:
    """Otomatik kampanyalar + (varsa) girilen kodu birlikte degerlendirir. Saf orkestrasyon."""
    entered = (entered_code or "").strip().upper()

    # 1) Adaylar: aktif auto_apply kampanyalar + girilen kod
    candidates = {}
    async for c in db.coupons.find({"is_active": True, "auto_apply": True}, {"_id": 0}):
        candidates[c["id"]] = c
    entered_id = None
    if entered:
        ec = await db.coupons.find_one({"code": entered}, {"_id": 0})
        if ec:
            candidates[ec["id"]] = ec
            entered_id = ec["id"]

    # 2) Tekil degerlendirme
    valid, rejected = [], []
    for cid, c in candidates.items():
        ev = await _evaluate_single(c, cart_total, items, user_id, email)
        if ev.get("valid") and (ev.get("discount", 0) > 0 or ev.get("free_shipping")):
            valid.append({
                "c": c, "discount": ev["discount"], "free_shipping": ev.get("free_shipping", False),
                "priority": int(c.get("priority", 0) or 0),
                "combinable": bool(c.get("combinable", False)),
                "stack_group": c.get("stack_group") or "",
                "is_entered": cid == entered_id,
            })
        elif cid == entered_id:
            rejected.append({"code": entered, "reason": ev.get("reason", "Uygulanamadı")})

    # 3) Sirala: priority -> discount -> girilen kod (esitlikte one)
    valid.sort(key=lambda x: (x["priority"], x["discount"], x["is_entered"]), reverse=True)

    # 4) Stack uygula (combinable kapisi + stack_group + kalan tabana ardisik)
    applied = []
    running = cart_total
    used_groups = set()
    for cand in valid:
        if applied:
            if not cand["combinable"] or not all(a["combinable"] for a in applied):
                continue
            if cand["stack_group"] and cand["stack_group"] in used_groups:
                continue
        scale = (running / cart_total) if cart_total > 0 else 0.0
        scaled_items = [{**it, "price": float(it.get("price", 0)) * scale} for it in items]
        d = _compute_discount(cand["c"], running, scaled_items)
        fs = cand["free_shipping"]
        if d <= 0 and not fs:
            continue
        applied.append({**cand, "applied_discount": round(d, 2)})
        running = round(running - d, 2)
        if cand["stack_group"]:
            used_groups.add(cand["stack_group"])

    total = round(sum(a["applied_discount"] for a in applied), 2)

    # 5) Global tavan
    cap_pct = await _promo_cap_pct()
    cap_amount = round(cart_total * cap_pct / 100.0, 2)
    capped = False
    if total > cap_amount and total > 0:
        factor = cap_amount / total
        for a in applied:
            a["applied_discount"] = round(a["applied_discount"] * factor, 2)
        total = round(sum(a["applied_discount"] for a in applied), 2)
        capped = True

    return {
        "applied": [{
            "coupon_id": a["c"]["id"], "code": a["c"].get("code", ""),
            "title": a["c"].get("title", ""), "type": a["c"].get("type"),
            "discount": a["applied_discount"], "free_shipping": a["free_shipping"],
            "priority": a["priority"], "combinable": a["combinable"], "stack_group": a["stack_group"],
        } for a in applied],
        "total_discount": total,
        "free_shipping": any(a["free_shipping"] for a in applied),
        "capped": capped,
        "cap_pct": cap_pct,
        "rejected": rejected,
    }


@public_router.post("/evaluate")
async def evaluate_promotions_endpoint(payload: dict):
    """Checkout/sepet motoru ucu. Onizleme ve siparis-kaydi AYNI motoru cagirir."""
    return await evaluate_cart_promotions(
        cart_total=float(payload.get("cart_total") or 0),
        items=payload.get("items") or [],
        user_id=payload.get("user_id"),
        email=payload.get("email") or payload.get("customer_email") or "",
        entered_code=payload.get("code") or "",
    )
