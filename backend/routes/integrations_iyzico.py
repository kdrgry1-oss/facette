"""
=============================================================================
integrations_iyzico.py — Iyzico Ödeme Entegrasyonu
=============================================================================

`integrations.py` (3800+ satır) refactoring: Iyzico kısmını ayrı modül olarak
burada tutuyoruz. Mevcut kod tamamen aynı davranışı korur; sadece organize edilir.

Endpoint'ler:
  GET  /api/integrations/payment/status          → ödeme config durumu
  GET  /api/integrations/iyzico/settings         → admin: credential (maskeli)
  POST /api/integrations/iyzico/settings         → admin: credential kaydet
  POST /api/integrations/iyzico/test-connection  → admin: API bağlantı testi
  POST /api/integrations/iyzico/refund           → admin: kısmi iade (kargo kesintili)

Not: Diğer modüllerin (Trendyol, HB, Temu vb.) bu modülün `log_integration_event`
yardımcısına ihtiyacı vardır. İlk aşamada fonksiyon `integrations.py` içinde
kaldığı için oradan import edilir.
=============================================================================
"""
import os
import base64
import hashlib
import random
import json
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, HTTPException, Depends

from .deps import db, logger, require_admin

router = APIRouter(tags=["Integrations-Iyzico"])


# ----- Çevre değişkeni fallback'leri (DB bu değerleri geçersiz kılar) -----
IYZICO_MODE = os.environ.get("IYZICO_MODE", "sandbox")
IYZICO_API_KEY = os.environ.get("IYZICO_API_KEY", "")
IYZICO_SECRET_KEY = os.environ.get("IYZICO_SECRET_KEY", "")
IYZICO_BASE_URL = os.environ.get(
    "IYZICO_BASE_URL",
    "https://api.iyzipay.com" if IYZICO_MODE == "live" else "https://sandbox-api.iyzipay.com",
)


def is_iyzico_configured() -> bool:
    return bool(IYZICO_API_KEY and IYZICO_SECRET_KEY and IYZICO_API_KEY != "sandbox-api-key")


def _iyzico_auth_header(settings: dict, uri: str, body: dict) -> dict:
    """Iyzico v1 auth header builder (PKI string tabanlı — eski format ama iade için çalışır)."""
    api_key = settings.get("api_key", "")
    secret = settings.get("api_secret", "")
    rnd = str(random.randint(10**15, 10**16 - 1))
    payload = api_key + rnd + secret
    h = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    token = base64.b64encode((api_key + ":" + h).encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"IYZWSv2 {token}",
        "x-iyzi-rnd": rnd,
        "Content-Type": "application/json",
    }


@router.get("/payment/status")
async def get_payment_status():
    """DB'de kayıtlı ayar varsa onu kullan, yoksa env fallback."""
    db_settings = await db.settings.find_one({"id": "iyzico"}, {"_id": 0})
    if db_settings and db_settings.get("api_key") and db_settings.get("api_secret"):
        mode = db_settings.get("mode", "sandbox")
        base = "https://api.iyzipay.com" if mode == "live" else "https://sandbox-api.iyzipay.com"
        return {
            "mode": mode,
            "configured": bool(db_settings.get("is_active")),
            "base_url": base,
        }
    return {
        "mode": IYZICO_MODE,
        "configured": is_iyzico_configured(),
        "base_url": IYZICO_BASE_URL,
    }


@router.get("/iyzico/settings")
async def get_iyzico_settings(current_user: dict = Depends(require_admin)):
    settings = await db.settings.find_one({"id": "iyzico"}, {"_id": 0})
    if not settings:
        return {
            "id": "iyzico",
            "api_key": "",
            "api_secret": "",
            "mode": "sandbox",
            "is_active": False,
        }
    if settings.get("api_secret"):
        settings["api_secret"] = "********"
    return settings


@router.post("/iyzico/settings")
async def save_iyzico_settings(payload: dict, current_user: dict = Depends(require_admin)):
    if payload.get("is_active"):
        existing = await db.settings.find_one({"id": "iyzico"}, {"_id": 0}) or {}
        api_key = payload.get("api_key") or existing.get("api_key")
        api_secret = payload.get("api_secret")
        if api_secret in (None, "", "********"):
            api_secret = existing.get("api_secret")
        if not api_key or not api_secret:
            raise HTTPException(
                status_code=400,
                detail="Iyzico aktifleştirmek için api_key ve api_secret zorunludur",
            )
    update_data = {
        "id": "iyzico",
        "api_key": payload.get("api_key", ""),
        "mode": payload.get("mode", "sandbox"),
        "is_active": payload.get("is_active", False),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if payload.get("api_secret") and payload.get("api_secret") != "********":
        update_data["api_secret"] = payload.get("api_secret")
    await db.settings.update_one({"id": "iyzico"}, {"$set": update_data}, upsert=True)
    return {"success": True, "message": "Iyzico ayarları kaydedildi"}


@router.post("/iyzico/test-connection")
async def test_iyzico_connection(current_user: dict = Depends(require_admin)):
    settings = await db.settings.find_one({"id": "iyzico"}, {"_id": 0})
    if not settings or not settings.get("api_key") or not settings.get("api_secret"):
        return {"success": False, "message": "Iyzico API bilgileri eksik"}
    return {"success": True, "message": "Iyzico API bilgileri kayıtlı. Refund test siparişle yapılabilir."}


@router.post("/iyzico/refund")
async def iyzico_refund(payload: dict, current_user: dict = Depends(require_admin)):
    """
    Iyzico kısmi iade. Kargo bedeli düşülerek iade yapılır.

    Body:
      order_id: str
      amount: float (iadesi yapılacak ürün tutarı, KDV dahil)
      shipping_deduction: float (opsiyonel, müşteriden kesilecek kargo bedeli)
      reason: str (opsiyonel)
    """
    # Geç import — log_integration_event hâlâ integrations.py'de (sonraki refactor'da ortak modüle taşınacak)
    from .integrations import log_integration_event  # noqa

    order_id = payload.get("order_id")
    amount = float(payload.get("amount") or 0)
    shipping_deduction = float(payload.get("shipping_deduction") or 0)
    reason = payload.get("reason", "Kısmi iade")
    if not order_id or amount <= 0:
        raise HTTPException(status_code=400, detail="order_id ve amount zorunlu")

    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    pid = order.get("payment_id") or order.get("iyzico_payment_id")
    if not pid:
        raise HTTPException(status_code=400, detail="Bu sipariş Iyzico ödemesi içermiyor veya payment_id yok")

    net_refund = round(amount - shipping_deduction, 2)
    if net_refund <= 0:
        raise HTTPException(status_code=400, detail="Kargo kesintisi sonrası iade tutarı 0 ya da negatif")

    settings = await db.settings.find_one({"id": "iyzico"}, {"_id": 0})
    if not settings or not settings.get("api_key"):
        raise HTTPException(status_code=400, detail="Iyzico API bilgileri eksik")
    base = (
        "https://api.iyzipay.com"
        if settings.get("mode") == "live"
        else "https://sandbox-api.iyzipay.com"
    )

    body = {
        "locale": "tr",
        "conversationId": f"refund-{order_id}",
        "paymentId": pid,
        "price": f"{net_refund:.2f}",
        "ip": "85.34.78.112",
        "currency": "TRY",
        "reason": reason,
    }
    uri = "/payment/refund"
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            headers = _iyzico_auth_header(settings, uri, body)
            resp = await c.post(f"{base}{uri}", json=body, headers=headers)
            data = (
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else {"raw": resp.text}
            )
        ok = (resp.status_code == 200) and (data.get("status") == "success")
        await log_integration_event(
            "iyzico", "refund", "order", order_id,
            "success" if ok else "error",
            f"Iyzico iade: gross={amount} kargo_kesinti={shipping_deduction} net={net_refund} → {data.get('status','?')}",
            {"response": data, "request": body},
        )
        if ok:
            await db.orders.update_one(
                {"id": order_id},
                {"$push": {"refunds": {
                    "amount": amount,
                    "shipping_deduction": shipping_deduction,
                    "net_refund": net_refund,
                    "reason": reason,
                    "refunded_at": datetime.now(timezone.utc).isoformat(),
                    "refunded_by": current_user.get("email", ""),
                    "provider": "iyzico",
                    "payment_id": pid,
                }}}
            )
        return {
            "success": ok,
            "net_refund": net_refund,
            "message": data.get("errorMessage") or ("Iade başarılı" if ok else "Iade başarısız"),
            "provider_response": data,
        }
    except Exception as e:
        logger.error(f"Iyzico refund error: {e}")
        raise HTTPException(status_code=500, detail=f"Iyzico iade hatası: {e}")
