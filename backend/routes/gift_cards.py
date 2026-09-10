"""
Hediye Çeki / Mağaza Kredisi (C2).

- Admin hediye çeki (kind="gift") veya müşteriye bağlı mağaza kredisi (kind="credit")
  oluşturur; bakiye kısmi kullanılabilir, kalan sonraki siparişe devreder.
- Ödemede kod girilir: sunucu bakiyeyi ATOMİK rezerve eder (create_order içinde),
  sipariş toplamı düşer. Tutarın TAMAMI çekle karşılanırsa sipariş sunucu-tarafı
  değer yakalandığı için paid/confirmed açılır (CLAUDE.md'de belgeli ikinci yol).
- Sipariş iptal/otomatik iptal olursa bakiye idempotent şekilde iade edilir
  (orders._restock_order_once içindeki kanca → refund_gift_card_once).

Güvenlik: istemciye asla bakiye yazdırılmaz-güvenilmez; tüm hesap sunucuda.
Kod tahmin edilemez (secrets). Public check ucu rate-limitli.
"""
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request

from .deps import db, logger, require_admin, limiter

router = APIRouter(prefix="/gift-cards", tags=["gift-cards"])

_CODE_ALPHABET = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"


def _gen_code() -> str:
    part = lambda n: "".join(secrets.choice(_CODE_ALPHABET) for _ in range(n))
    return f"HED-{part(4)}-{part(4)}-{part(4)}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _find_active_card(code: str) -> Optional[dict]:
    code = (code or "").strip().upper()
    if not code:
        return None
    card = await db.gift_cards.find_one({"code": code}, {"_id": 0})
    if not card or card.get("status") != "active":
        return None
    exp = card.get("expires_at") or ""
    if exp and exp < _now_iso():
        return None
    return card


async def redeem_gift_card_for_order(code: str, order: dict, payable_total: float) -> dict:
    """create_order içinden çağrılır. Bakiyeyi ATOMİK düşer (yarışa dayanıklı).

    Döner: {"ok": bool, "amount": float, "code": str, "error": str}
    - amount = min(bakiye, payable_total); kart ödemesinde kalan 0<x<1 TL olmasın
      diye gerekirse 1 TL pay bırakılır (iyzico minimum tahsilat).
    """
    card = await _find_active_card(code)
    if not card:
        return {"ok": False, "amount": 0.0, "code": code, "error": "Hediye çeki geçersiz veya süresi dolmuş"}

    # Mağaza kredisi (kind=credit) yalnız sahibinin e-postasıyla kullanılabilir.
    if (card.get("kind") or "gift") == "credit":
        owner = (card.get("customer_email") or "").strip().lower()
        buyer = ((order.get("shipping_address") or {}).get("email") or "").strip().lower()
        if owner and owner != buyer:
            return {"ok": False, "amount": 0.0, "code": code,
                    "error": "Bu mağaza kredisi başka bir hesaba tanımlı"}

    # YÜZDE tipli çek (value_type="percent"): tutar = sepet × yüzde (maks. tutar tavanlı),
    # bakiye yerine kullanım hakkı (uses_left) düşer; iptalde hak geri verilir.
    if (card.get("value_type") or "amount") == "percent":
        pct = float(card.get("percent") or 0)
        cap = float(card.get("max_amount") or 0)
        uses_left = int(card.get("uses_left") if card.get("uses_left") is not None else 1)
        if pct <= 0 or uses_left <= 0:
            return {"ok": False, "amount": 0.0, "code": code, "error": "Hediye çeki kullanım hakkı bitmiş"}
        use = round(max(0.0, payable_total) * pct / 100.0, 2)
        if cap > 0:
            use = min(use, round(cap, 2))
        if use <= 0:
            return {"ok": False, "amount": 0.0, "code": code, "error": "Uygulanacak tutar yok"}
        _pm = (order.get("payment_method") or "").lower()
        _is_card = _pm in ("credit_card", "card", "kredi_karti", "kart", "iyzico", "creditcard")
        remaining = round(payable_total - use, 2)
        if _is_card and 0 < remaining < 1.0:
            use = round(payable_total - 1.0, 2)
            if use <= 0:
                return {"ok": False, "amount": 0.0, "code": code,
                        "error": "Tutar hediye çekiyle uyumsuz — farklı ödeme yöntemi deneyin"}
        res = await db.gift_cards.update_one(
            {"code": card["code"], "status": "active", "uses_left": {"$gte": 1}},
            {"$inc": {"uses_left": -1, "used_total": use},
             "$push": {"transactions": {"type": "redeem", "amount": use, "percent": pct,
                                        "order_id": order.get("id"), "order_number": order.get("order_number"),
                                        "at": _now_iso()}},
             "$set": {"last_used_at": _now_iso()}})
        if not res.modified_count:
            return {"ok": False, "amount": 0.0, "code": code, "error": "Hediye çeki şu an kullanılamadı, tekrar deneyin"}
        await db.gift_cards.update_one({"code": card["code"], "uses_left": {"$lte": 0}}, {"$set": {"status": "used"}})
        logger.info(f"[gift-card] {card['code']} → %{pct} = {use} TL (sipariş {order.get('order_number')})")
        return {"ok": True, "amount": use, "code": card["code"], "error": "", "percent": pct}

    for _attempt in range(2):  # yarış olursa güncel bakiyeyle bir kez daha dene
        balance = round(float(card.get("balance") or 0), 2)
        if balance <= 0:
            return {"ok": False, "amount": 0.0, "code": code, "error": "Hediye çeki bakiyesi tükenmiş"}
        use = round(min(balance, max(0.0, payable_total)), 2)
        if use <= 0:
            return {"ok": False, "amount": 0.0, "code": code, "error": "Uygulanacak tutar yok"}
        # Kartla ödenecek kalan 0 ile 1 TL arasında kalmasın (iyzico min. tahsilat).
        _pm = (order.get("payment_method") or "").lower()
        _is_card = _pm in ("credit_card", "card", "kredi_karti", "kart", "iyzico", "creditcard")
        remaining = round(payable_total - use, 2)
        if _is_card and 0 < remaining < 1.0:
            use = round(payable_total - 1.0, 2)
            if use <= 0:
                return {"ok": False, "amount": 0.0, "code": code,
                        "error": "Tutar hediye çekiyle uyumsuz — farklı ödeme yöntemi deneyin"}
        res = await db.gift_cards.update_one(
            {"code": card["code"], "status": "active", "balance": {"$gte": use}},
            {"$inc": {"balance": -use},
             "$push": {"transactions": {
                 "type": "redeem", "amount": use,
                 "order_id": order.get("id"), "order_number": order.get("order_number"),
                 "at": _now_iso()}},
             "$set": {"last_used_at": _now_iso()}},
        )
        if res.modified_count:
            logger.info(f"[gift-card] {card['code']} → {use} TL rezerve (sipariş {order.get('order_number')})")
            return {"ok": True, "amount": use, "code": card["code"], "error": ""}
        card = await _find_active_card(code)  # yarış: bakiye değişti → tazele
        if not card:
            break
    return {"ok": False, "amount": 0.0, "code": code, "error": "Hediye çeki şu an kullanılamadı, tekrar deneyin"}


async def refund_gift_card_once(order: dict) -> float:
    """Sipariş iptalinde bakiye iadesi — İDEMPOTENT (sipariş bayrağı atomik kilit)."""
    gc = order.get("gift_card") or {}
    amount = round(float(gc.get("amount") or 0), 2)
    code = (gc.get("code") or "").strip().upper()
    if amount <= 0 or not code:
        return 0.0
    lock = await db.orders.update_one(
        {"id": order.get("id"), "gift_card.refunded": {"$ne": True}},
        {"$set": {"gift_card.refunded": True, "gift_card.refunded_at": _now_iso()}},
    )
    if not lock.modified_count:
        return 0.0  # zaten iade edilmiş
    card = await db.gift_cards.find_one({"code": code}, {"_id": 0, "value_type": 1})
    if (card or {}).get("value_type") == "percent":
        # Yüzde çeki: bakiye yok → kullanım hakkı geri verilir, çek yeniden aktif olur.
        await db.gift_cards.update_one(
            {"code": code},
            {"$inc": {"uses_left": 1, "used_total": -amount},
             "$set": {"status": "active"},
             "$push": {"transactions": {"type": "refund", "amount": amount,
                                        "order_id": order.get("id"), "order_number": order.get("order_number"),
                                        "at": _now_iso()}}})
        logger.info(f"[gift-card] {code} ← kullanım hakkı iade (sipariş {order.get('order_number')} iptal)")
        return amount
    await db.gift_cards.update_one(
        {"code": code},
        {"$inc": {"balance": amount},
         "$push": {"transactions": {
             "type": "refund", "amount": amount,
             "order_id": order.get("id"), "order_number": order.get("order_number"),
             "at": _now_iso()}}},
    )
    logger.info(f"[gift-card] {code} ← {amount} TL iade (sipariş {order.get('order_number')} iptal)")
    return amount


# ── Public: kod doğrulama (ödeme sayfası) ────────────────────────────────────
@router.post("/check")
@(limiter.limit("15/minute") if limiter else (lambda f: f))
async def check_gift_card(request: Request, payload: dict):
    code = (payload or {}).get("code") or ""
    card = await _find_active_card(code)
    if not card:
        # Sık karışıklık: kullanıcı indirim/kampanya KODUNU (ör. HOSGELDIN10) hediye çeki
        # alanına giriyor → "geçersiz" mesajı yanıltıyor. Kod bir kupon/kampanya ise net söyle
        # ve kampanyaların her zaman birleşmeyebileceğini uyar (kullanıcı isteği).
        # Harf + Türkçe-I duyarsız: 'HOSGELDİN', 'hosgeldin', 'hosgeldın' hepsi 'HOSGELDIN' say.
        _norm = str(code or "").strip().replace("İ", "I").replace("ı", "I").upper()
        if _norm:
            import re as _re_cpn
            try:
                _cpn = await db.coupons.find_one(
                    {"code": {"$regex": f"^{_re_cpn.escape(_norm)}$", "$options": "i"}},
                    {"_id": 0, "id": 1, "code": 1})
            except Exception:
                _cpn = None
            if _cpn:
                # is_coupon + coupon_code: frontend bu kodu OTOMATİK "Promosyon kodu" olarak
                # uygular (kullanıcı ayrı alana tekrar girmek zorunda kalmaz).
                return {"valid": False, "is_coupon": True, "coupon_code": _cpn.get("code") or _norm,
                        "error": "Bu bir indirim/kampanya kodu — promosyon olarak uygulanıyor…"}
        return {"valid": False, "error": "Hediye çeki geçersiz veya süresi dolmuş"}
    if (card.get("kind") or "gift") == "credit":
        owner = (card.get("customer_email") or "").strip().lower()
        buyer = ((payload or {}).get("email") or "").strip().lower()
        if owner and owner != buyer:
            return {"valid": False, "error": "Bu mağaza kredisi başka bir hesaba tanımlı"}
    if (card.get("value_type") or "amount") == "percent":
        if int(card.get("uses_left") if card.get("uses_left") is not None else 1) <= 0:
            return {"valid": False, "error": "Hediye çeki kullanım hakkı bitmiş"}
        return {"valid": True, "value_type": "percent", "percent": float(card.get("percent") or 0),
                "max_amount": float(card.get("max_amount") or 0), "balance": 0,
                "kind": card.get("kind") or "gift"}
    return {"valid": True, "value_type": "amount", "balance": round(float(card.get("balance") or 0), 2),
            "kind": card.get("kind") or "gift"}


# ── Admin ────────────────────────────────────────────────────────────────────
admin_router = APIRouter(prefix="/admin/gift-cards", tags=["gift-cards-admin"])


@admin_router.post("")
async def create_gift_card(payload: dict, current_user: dict = Depends(require_admin)):
    value_type = (payload or {}).get("value_type") or "amount"
    if value_type not in ("amount", "percent"):
        value_type = "amount"
    amount = 0.0
    percent = 0.0
    max_amount = 0.0
    usage_limit = 1
    if value_type == "percent":
        percent = round(float((payload or {}).get("percent") or 0), 2)
        if percent <= 0 or percent > 100:
            raise HTTPException(status_code=400, detail="Yüzde 1-100 arasında olmalı")
        max_amount = round(float((payload or {}).get("max_amount") or 0), 2)
        usage_limit = max(1, min(int((payload or {}).get("usage_limit") or 1), 100000))
    else:
        amount = round(float((payload or {}).get("amount") or 0), 2)
        if amount <= 0 or amount > 100000:
            raise HTTPException(status_code=400, detail="Tutar 0'dan büyük olmalı")
    kind = (payload.get("kind") or "gift").lower()
    if kind not in ("gift", "credit"):
        kind = "gift"
    email = (payload.get("customer_email") or "").strip().lower()
    if kind == "credit" and not email:
        raise HTTPException(status_code=400, detail="Mağaza kredisi için müşteri e-postası zorunlu")
    expires_days = int(payload.get("expires_days") or 0)
    # KOD: admin kendi belirleyebilir (ör. YILBASI20); boşsa otomatik üretilir.
    import re as _re
    custom = str(payload.get("code") or "").strip().upper().replace("İ", "I").replace("ı", "I")
    if custom:
        custom = _re.sub(r"\s+", "", custom)
        if not _re.fullmatch(r"[A-Z0-9][A-Z0-9\-_]{2,31}", custom):
            raise HTTPException(status_code=400, detail="Kod 3-32 karakter olmalı; harf, rakam, - ve _ kullanılabilir")
        if await db.gift_cards.find_one({"code": custom}, {"_id": 1}):
            raise HTTPException(status_code=400, detail="Bu kod zaten bir hediye çekinde kullanılıyor")
        if await db.coupons.find_one({"code": {"$regex": f"^{_re.escape(custom)}$", "$options": "i"}}, {"_id": 1}):
            raise HTTPException(status_code=400, detail="Bu kod bir kupon/kampanya kodu — hediye çeki kodu farklı olmalı")
        code = custom
    else:
        code = _gen_code()
        while await db.gift_cards.find_one({"code": code}, {"_id": 1}):
            code = _gen_code()
    doc = {
        "id": secrets.token_hex(8),
        "code": code,
        "kind": kind,
        "value_type": value_type,
        "initial_amount": amount,
        "balance": amount,
        # Yüzde çeki alanları (value_type="percent"): yüzde, maks. indirim tutarı, kullanım hakkı
        "percent": percent,
        "max_amount": max_amount,
        "usage_limit": usage_limit,
        "uses_left": usage_limit if value_type == "percent" else None,
        "used_total": 0.0,
        "currency": "TRY",
        "status": "active",
        "customer_email": email,
        "note": str(payload.get("note") or "")[:300],
        "created_by": current_user.get("email", ""),
        "created_at": _now_iso(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat() if expires_days > 0 else "",
        "transactions": [],
    }
    await db.gift_cards.insert_one({**doc})
    return doc


@admin_router.get("")
async def list_gift_cards(q: str = "", status: str = "", limit: int = 200,
                          current_user: dict = Depends(require_admin)):
    query: dict = {}
    if q:
        import re as _re
        rx = {"$regex": _re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"code": rx}, {"customer_email": rx}, {"note": rx}]
    if status:
        query["status"] = status
    rows = await db.gift_cards.find(query, {"_id": 0}).sort("created_at", -1).to_list(max(1, min(limit, 1000)))
    return {"items": rows, "count": len(rows)}


@admin_router.put("/{card_id}")
async def update_gift_card(card_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    upd: dict = {}
    if "status" in (payload or {}):
        st = str(payload["status"]).lower()
        if st not in ("active", "disabled"):
            raise HTTPException(status_code=400, detail="Durum active/disabled olabilir")
        upd["status"] = st
    if "note" in (payload or {}):
        upd["note"] = str(payload.get("note") or "")[:300]
    if payload.get("add_balance") is not None:
        delta = round(float(payload["add_balance"]), 2)
        if delta:
            await db.gift_cards.update_one(
                {"id": card_id},
                {"$inc": {"balance": delta},
                 "$push": {"transactions": {"type": "adjust", "amount": delta,
                                            "by": current_user.get("email", ""), "at": _now_iso()}}})
    if upd:
        await db.gift_cards.update_one({"id": card_id}, {"$set": upd})
    card = await db.gift_cards.find_one({"id": card_id}, {"_id": 0})
    if not card:
        raise HTTPException(status_code=404, detail="Hediye çeki bulunamadı")
    return card
