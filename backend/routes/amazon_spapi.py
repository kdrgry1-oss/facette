"""
Amazon Selling Partner API (SP-API) entegrasyonu.

ÖNEMLİ: SP-API artık AWS IAM / SigV4 GEREKTİRMİYOR (2 Ekim 2023'ten beri).
Sadece LWA (Login with Amazon) access token yeterli:
  refresh_token -> access_token (https://api.amazon.com/auth/o2/token)
  SP-API çağrılarında header: x-amz-access-token: <access_token>

Kimlik bilgileri (client_secret, refresh_token) AES şifreli vault'ta saklanır.
Config (client_id, marketplace, region) `integration_settings` koleksiyonunda.

Endpoints (hepsi /api prefix + require_admin, public callback hariç):
  GET    /api/amazon/spapi/status         -> bağlantı durumu
  POST   /api/amazon/spapi/config         -> kimlik bilgilerini kaydet
  POST   /api/amazon/spapi/test           -> token üret + marketplaceParticipations ile doğrula
  GET    /api/amazon/spapi/orders         -> son siparişleri çek (örnek)
  GET    /api/amazon/spapi/authorize-url  -> OAuth consent URL (website workflow)
  GET    /api/amazon/spapi/oauth/callback -> spapi_oauth_code -> refresh_token (public)
"""
import os
import time
import secrets as _secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import RedirectResponse

from .deps import db, logger, require_admin

router = APIRouter(prefix="/amazon/spapi", tags=["Amazon SP-API"])

LWA_TOKEN_ENDPOINT = "https://api.amazon.com/auth/o2/token"
CONFIG_KEY = "amazon_spapi"

# Bölge endpoint'leri (SP-API)
SPAPI_REGIONS = {
    "eu": "https://sellingpartnerapi-eu.amazon.com",
    "na": "https://sellingpartnerapi-na.amazon.com",
    "fe": "https://sellingpartnerapi-fe.amazon.com",
}
# Türkiye marketplace -> EU region
DEFAULT_MARKETPLACE_ID = "A33AVAJ2PDY3EV"  # Amazon Türkiye
DEFAULT_REGION = "eu"

# Seller Central consent domain (bölge/ülkeye göre)
SELLERCENTRAL_CONSENT = {
    "eu": "https://sellercentral.amazon.com.tr",
    "na": "https://sellercentral.amazon.com",
    "fe": "https://sellercentral-japan.amazon.com",
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


async def _get_config(include_secrets: bool = False) -> Optional[dict]:
    doc = await db.integration_settings.find_one({"key": CONFIG_KEY}, {"_id": 0})
    if not doc:
        return None
    if include_secrets:
        from security.crypto import decrypt
        doc["client_secret"] = decrypt(doc.get("client_secret_enc")) if doc.get("client_secret_enc") else None
        doc["refresh_token"] = decrypt(doc.get("refresh_token_enc")) if doc.get("refresh_token_enc") else None
    return doc


async def _exchange_refresh_for_access(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """LWA refresh_token -> access_token."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            LWA_TOKEN_ENDPOINT,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = r.json()
        if r.status_code != 200:
            raise HTTPException(status_code=400, detail=f"LWA token hatası: {data.get('error_description') or data}")
        return data


async def _exchange_code_for_refresh(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """LWA authorization_code -> refresh_token (+access_token)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            LWA_TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = r.json()
        if r.status_code != 200:
            raise HTTPException(status_code=400, detail=f"LWA code exchange hatası: {data.get('error_description') or data}")
        return data


async def get_valid_access_token() -> tuple[str, str, str]:
    """Geçerli (gerekirse yenilenmiş) access token döndürür.
    Dönüş: (access_token, endpoint, marketplace_id). Diğer modüller bunu kullanır."""
    cfg = await _get_config(include_secrets=True)
    if not cfg or not cfg.get("refresh_token") or not cfg.get("client_id") or not cfg.get("client_secret"):
        raise HTTPException(status_code=400, detail="Amazon SP-API yapılandırılmamış (refresh token eksik)")

    cached = cfg.get("access_token")
    expires_at = cfg.get("access_expires_at") or 0
    if cached and expires_at > int(time.time()) + 60:
        access_token = cached
    else:
        td = await _exchange_refresh_for_access(cfg["client_id"], cfg["client_secret"], cfg["refresh_token"])
        access_token = td["access_token"]
        expires_at = int(time.time()) + int(td.get("expires_in", 3600))
        await db.integration_settings.update_one(
            {"key": CONFIG_KEY},
            {"$set": {"access_token": access_token, "access_expires_at": expires_at, "updated_at": _now_iso()}},
        )
    region = cfg.get("region") or DEFAULT_REGION
    endpoint = SPAPI_REGIONS.get(region, SPAPI_REGIONS[DEFAULT_REGION])
    return access_token, endpoint, cfg.get("marketplace_id") or DEFAULT_MARKETPLACE_ID


async def _spapi_get(path: str, params: dict = None) -> dict:
    access_token, endpoint, _ = await get_valid_access_token()
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            f"{endpoint}{path}",
            params=params or {},
            headers={
                "x-amz-access-token": access_token,
                "content-type": "application/json",
                "accept": "application/json",
            },
        )
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:500]}
        return {"status": r.status_code, "ok": 200 <= r.status_code < 300, "data": data}


# ============================== ENDPOINTS ==============================

@router.get("/status")
async def spapi_status(current_user: dict = Depends(require_admin)):
    cfg = await _get_config()
    if not cfg:
        return {"configured": False, "connected": False}
    return {
        "configured": True,
        "connected": bool(cfg.get("refresh_token_enc")),
        "has_client_secret": bool(cfg.get("client_secret_enc")),
        "client_id": cfg.get("client_id"),
        "marketplace_id": cfg.get("marketplace_id") or DEFAULT_MARKETPLACE_ID,
        "region": cfg.get("region") or DEFAULT_REGION,
        "app_id": cfg.get("app_id"),
        "last_test": cfg.get("last_test"),
        "updated_at": cfg.get("updated_at"),
    }


@router.post("/config")
async def spapi_save_config(payload: dict, current_user: dict = Depends(require_admin)):
    """Kimlik bilgilerini kaydeder. Secret'lar AES vault formatında şifrelenir.
    payload: { client_id, client_secret?, refresh_token?, app_id?, marketplace_id?, region? }
    """
    from security.crypto import encrypt
    existing = await _get_config() or {}
    update = {
        "key": CONFIG_KEY,
        "client_id": (payload.get("client_id") or existing.get("client_id") or "").strip(),
        "app_id": (payload.get("app_id") or existing.get("app_id") or "").strip(),
        "marketplace_id": (payload.get("marketplace_id") or existing.get("marketplace_id") or DEFAULT_MARKETPLACE_ID).strip(),
        "region": (payload.get("region") or existing.get("region") or DEFAULT_REGION).strip(),
        "updated_at": _now_iso(),
        "updated_by": current_user.get("email"),
    }
    if payload.get("client_secret"):
        update["client_secret_enc"] = encrypt(payload["client_secret"].strip())
    if payload.get("refresh_token"):
        update["refresh_token_enc"] = encrypt(payload["refresh_token"].strip())
        # token değişti -> cache temizle
        update["access_token"] = None
        update["access_expires_at"] = 0
    await db.integration_settings.update_one(
        {"key": CONFIG_KEY},
        {"$set": update, "$setOnInsert": {"created_at": _now_iso()}},
        upsert=True,
    )
    return {"success": True}


@router.post("/test")
async def spapi_test(current_user: dict = Depends(require_admin)):
    """Token üretip getMarketplaceParticipations ile bağlantıyı doğrular."""
    res = await _spapi_get("/sellers/v1/marketplaceParticipations")
    ok = res["ok"]
    marketplaces = []
    if ok:
        for p in (res["data"].get("payload") or []):
            mp = p.get("marketplace") or {}
            marketplaces.append({
                "id": mp.get("id"),
                "name": mp.get("name"),
                "country": mp.get("countryCode"),
                "currency": mp.get("defaultCurrencyCode"),
            })
    await db.integration_settings.update_one(
        {"key": CONFIG_KEY},
        {"$set": {"last_test": {"ok": ok, "at": _now_iso(), "status": res["status"]}}},
    )
    if not ok:
        return {"success": False, "status": res["status"], "error": res["data"]}
    return {"success": True, "marketplaces": marketplaces}


@router.get("/orders")
async def spapi_orders(
    days: int = Query(7, ge=1, le=90),
    current_user: dict = Depends(require_admin),
):
    """Son N gün siparişlerini Amazon Orders API'den çeker (örnek/önizleme)."""
    _, _, marketplace_id = await get_valid_access_token()
    created_after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res = await _spapi_get("/orders/v0/orders", {
        "MarketplaceIds": marketplace_id,
        "CreatedAfter": created_after,
    })
    if not res["ok"]:
        return {"success": False, "status": res["status"], "error": res["data"]}
    payload = res["data"].get("payload") or {}
    orders = payload.get("Orders") or []
    return {
        "success": True,
        "count": len(orders),
        "orders": [{
            "amazon_order_id": o.get("AmazonOrderId"),
            "status": o.get("OrderStatus"),
            "purchase_date": o.get("PurchaseDate"),
            "total": (o.get("OrderTotal") or {}).get("Amount"),
            "currency": (o.get("OrderTotal") or {}).get("CurrencyCode"),
            "items_shipped": o.get("NumberOfItemsShipped"),
            "fulfillment": o.get("FulfillmentChannel"),
        } for o in orders],
    }


def _public_base() -> str:
    return (os.environ.get("PUBLIC_BASE_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")


@router.get("/authorize-url")
async def spapi_authorize_url(current_user: dict = Depends(require_admin)):
    """OAuth consent URL (website workflow). App ID (solution id) gerektirir."""
    cfg = await _get_config()
    if not cfg or not cfg.get("app_id"):
        raise HTTPException(status_code=400, detail="App ID (Solution ID, amzn1.sp.solution.xxx) kaydedilmemiş")
    if not cfg.get("client_secret_enc"):
        raise HTTPException(status_code=400, detail="Önce Client Secret kaydedin")
    region = cfg.get("region") or DEFAULT_REGION
    base = SELLERCENTRAL_CONSENT.get(region, SELLERCENTRAL_CONSENT["eu"])
    redirect_uri = f"{_public_base()}/api/amazon/spapi/oauth/callback"
    state = _secrets.token_urlsafe(24)
    await db.integration_settings.update_one(
        {"key": CONFIG_KEY}, {"$set": {"oauth_state": state, "oauth_redirect": redirect_uri}}
    )
    url = (f"{base}/apps/authorize/consent?application_id={cfg['app_id']}"
           f"&state={state}&redirect_uri={redirect_uri}&version=beta")
    return {"url": url, "redirect_uri": redirect_uri}


@router.get("/oauth/callback")
async def spapi_oauth_callback(request: Request, spapi_oauth_code: str = None,
                               state: str = None, selling_partner_id: str = None):
    """Amazon OAuth dönüşü — spapi_oauth_code -> refresh_token (vault'a kaydedilir)."""
    from security.crypto import encrypt
    cfg = await _get_config(include_secrets=True)
    frontend = _public_base()
    if not spapi_oauth_code or not cfg:
        return RedirectResponse(url=f"{frontend}/admin/amazon?status=error")
    if cfg.get("oauth_state") and state and state != cfg.get("oauth_state"):
        return RedirectResponse(url=f"{frontend}/admin/amazon?status=state_mismatch")
    redirect_uri = cfg.get("oauth_redirect") or f"{_public_base()}/api/amazon/spapi/oauth/callback"
    try:
        td = await _exchange_code_for_refresh(cfg["client_id"], cfg["client_secret"], spapi_oauth_code, redirect_uri)
    except HTTPException:
        return RedirectResponse(url=f"{frontend}/admin/amazon?status=exchange_failed")
    refresh_token = td.get("refresh_token")
    if not refresh_token:
        return RedirectResponse(url=f"{frontend}/admin/amazon?status=no_refresh_token")
    await db.integration_settings.update_one(
        {"key": CONFIG_KEY},
        {"$set": {
            "refresh_token_enc": encrypt(refresh_token),
            "selling_partner_id": selling_partner_id,
            "access_token": None, "access_expires_at": 0,
            "updated_at": _now_iso(),
        }},
    )
    return RedirectResponse(url=f"{frontend}/admin/amazon?status=connected")
