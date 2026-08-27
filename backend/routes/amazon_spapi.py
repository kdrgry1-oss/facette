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


# ── İlk Faz PII/Restricted guard (Amazon DPP §1) ────────────────────────────
# Restricted Role alınana kadar PII döndüren / RDT gerektiren yollar KAPALI.
# Açmak için: env AMAZON_ALLOW_RESTRICTED=1 (Restricted Role onaylanınca).
RESTRICTED_ALLOWED = os.environ.get("AMAZON_ALLOW_RESTRICTED", "0") == "1"
# PII döndürebilen / RDT gerektiren SP-API yol işaretleri — flag kapalıyken çağrı ENGELLENİR.
_RESTRICTED_PATH_MARKERS = ("/buyerinfo", "buyerinfo", "/address", "shippingaddress",
                            "/tokens", "restricted")
# Yanıtta BEKLENMEDİK şekilde gelirse tamamen SÖKÜLECEK PII container anahtarları
# (defense-in-depth: ilk fazda PII beklenmez; gelirse saklanmadan/loglanmadan atılır).
_PII_KEYS = {
    "buyerinfo", "buyeremail", "buyername", "buyercompanyname",
    "buyertaxinfo", "buyertaxinformation", "shippingaddress", "billingaddress",
    "defaultshipfromlocationaddress", "buyercustomizedinformation",
}


def _assert_restricted_allowed(path: str) -> None:
    """Restricted/PII yol çağrısını flag kapalıyken 403 ile engeller (§1)."""
    if RESTRICTED_ALLOWED:
        return
    low = (path or "").lower()
    if any(m in low for m in _RESTRICTED_PATH_MARKERS):
        raise HTTPException(
            status_code=403,
            detail="Restricted/PII SP-API yolu ilk fazda kapalıdır (AMAZON_ALLOW_RESTRICTED=0).",
        )


def _scrub_pii(obj):
    """Yanıttan beklenmedik PII container'larını özyinelemeli SÖKER (§1). Değer saklanmaz."""
    if isinstance(obj, dict):
        return {k: _scrub_pii(v) for k, v in obj.items() if str(k).lower() not in _PII_KEYS}
    if isinstance(obj, list):
        return [_scrub_pii(x) for x in obj]
    return obj


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


async def _log_spapi_call(action: str, status: int = None, ok: bool = None, actor: str = "") -> None:
    """SP-API çağrı denetim logu (Amazon DPP: SP-API çağrıları merkezi loglanır).
    PII İÇERMEZ — yalnız işlem tipi/path, HTTP durum, zaman, (varsa) admin e-postası.
    İstek parametreleri/gövdesi ve alıcı bilgisi LOGLANMAZ."""
    try:
        await db.spapi_call_logs.insert_one({
            "action": action, "status": status, "ok": ok,
            "actor": actor or "", "at": _now_iso(),
        })
    except Exception:
        pass


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


# İlk faz: Amazon'a YAZMA varsayılan KAPALI (dry-run). Restricted-flag pattern'iyle aynı.
# Açmak için: env AMAZON_ALLOW_WRITE=1 (canlı test SKU'su ile doğrulanınca). Rollback: =0.
ALLOW_WRITE = os.environ.get("AMAZON_ALLOW_WRITE", "0") == "1"


async def _spapi_send(method: str, path: str, body: dict = None, params: dict = None) -> dict:
    """PATCH/PUT/POST yazma çağrısı. ALLOW_WRITE KAPALIYSA Amazon'a GİTMEZ (dry-run):
    ne gönderileceğini döndürür → SKU/payload'ı canlı yazmadan doğrulayabilirsiniz.
    Açıkken gerçek çağrı yapılır. PII yol koruması (§1) yine geçerli; gövde loglanmaz."""
    _assert_restricted_allowed(path)
    if not ALLOW_WRITE:
        await _log_spapi_call(f"DRYRUN {method} {path}", None, True)
        return {"status": 0, "ok": True, "dry_run": True,
                "would_send": {"method": method, "path": path, "params": params or {}, "body": body}}
    access_token, endpoint, _ = await get_valid_access_token()
    async with httpx.AsyncClient(timeout=25.0) as client:
        r = await client.request(
            method, f"{endpoint}{path}", params=params or {}, json=body,
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
        data = _scrub_pii(data)  # §1: beklenmedik PII saklanmadan sökülür
        _ok = 200 <= r.status_code < 300
        await _log_spapi_call(f"{method} {path}", r.status_code, _ok)  # gövde loglanmaz
        return {"status": r.status_code, "ok": _ok, "data": data}


async def _require_seller_id() -> str:
    cfg = await _get_config()
    seller = (cfg or {}).get("selling_partner_id")
    if not seller:
        raise HTTPException(status_code=400,
                            detail="selling_partner_id yok — önce OAuth ile bağlanın (consent akışı)")
    return seller


async def _spapi_get(path: str, params: dict = None) -> dict:
    # §1: Restricted/PII yol ise (flag kapalı) çağrıyı hiç yapma.
    _assert_restricted_allowed(path)
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
        # §1 defense-in-depth: beklenmedik PII container'ları saklanmadan/loglanmadan SÖKÜLÜR.
        data = _scrub_pii(data)
        _ok = 200 <= r.status_code < 300
        # PII'siz çağrı logu (yalnız path + durum) — parametreler/gövde loglanmaz.
        await _log_spapi_call(f"GET {path}", r.status_code, _ok)
        return {"status": r.status_code, "ok": _ok, "data": data}


# ============================== SİPARİŞ İÇE-AKTARIM (panele düşürme) ==============================
# NOT: Bu yol Amazon siparişlerini Facette paneline (db.orders) YAZAR — Trendyol/Hepsiburada
# ile AYNI pazaryeri deseni. Pazaryeri siparişi ZATEN ödemeyi almış DIŞ sipariştir; panele
# payment_method="marketplace", payment_status="paid", status="confirmed" (Amazon işlem
# durumuna göre) düşer. Müşteri-yönlü iyzico ödeme akışı (CLAUDE.md değişmezleri) bundan
# TAMAMEN AYRIDIR ve burada DEĞİŞMEZ. Alıcı adı/adresi (PII) yalnız Restricted Role onaylı +
# AMAZON_ALLOW_RESTRICTED=1 iken RDT ile çekilir; kapalıyken sipariş kabuğu (PII'siz) düşer.


def _amz_status_of(status_raw: str) -> str:
    """Amazon OrderStatus -> Facette operasyonel durumu.
    Canceled/Unfulfillable=iptal, Shipped=kargoya verildi, diğerleri=onaylandı.
    (Amazon Orders API 'Delivered' döndürmez; teslim ayrı izlenir.)"""
    s = status_raw or ""
    if s in ("Canceled", "Cancelled", "Unfulfillable"):
        return "cancelled"
    if s == "Shipped":
        return "shipped"
    return "confirmed"


async def _get_restricted_data_token(order_id: str) -> Optional[str]:
    """Sipariş PII'si (buyerInfo + shippingAddress) için Restricted Data Token (RDT) alır.
    AMAZON_ALLOW_RESTRICTED=0 iken None döner → PII çekilmez (yalnız sipariş kabuğu).
    Amazon Restricted Role onayı + env flag gerekir."""
    if not RESTRICTED_ALLOWED:
        return None
    try:
        access_token, endpoint, _ = await get_valid_access_token()
        body = {"restrictedResources": [{
            "method": "GET",
            "path": f"/orders/v0/orders/{order_id}",
            "dataElements": ["buyerInfo", "shippingAddress"],
        }]}
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"{endpoint}/tokens/2021-03-01/restrictedDataToken",
                json=body,
                headers={"x-amz-access-token": access_token,
                         "content-type": "application/json", "accept": "application/json"},
            )
        await _log_spapi_call("POST /tokens/restrictedDataToken", r.status_code, 200 <= r.status_code < 300)
        if r.status_code // 100 != 2:
            return None
        return (r.json() or {}).get("restrictedDataToken")
    except Exception:
        return None


async def _fetch_amazon_order_full(order_id: str) -> dict:
    """Tek siparişi çeker. RDT alınabildiyse (Restricted açık) yanıt alıcı adı/adresini
    İÇERİR ve KORUNUR; RDT yoksa Amazon PII döndürmez → defense-in-depth scrub uygulanır.
    Döner: Orders API 'payload' (tek sipariş objesi) veya {}."""
    access_token, endpoint, _ = await get_valid_access_token()
    rdt = await _get_restricted_data_token(order_id)
    token = rdt or access_token
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                f"{endpoint}/orders/v0/orders/{order_id}",
                headers={"x-amz-access-token": token, "accept": "application/json"},
            )
        _ok = 200 <= r.status_code < 300
        await _log_spapi_call(f"GET /orders/v0/orders/{order_id}", r.status_code, _ok)
        try:
            payload = (r.json() or {}).get("payload") or {}
        except Exception:
            payload = {}
        if not rdt:
            # RDT yoksa beklenmedik PII saklanmadan/loglanmadan SÖKÜLÜR (§1).
            payload = _scrub_pii(payload)
        return payload
    except Exception:
        return {}


async def _fetch_amazon_order_items(order_id: str) -> list:
    """Sipariş kalemleri (SellerSKU/ASIN/adet/fiyat). PII'siz — RDT gerekmez."""
    items, next_token = [], None
    for _ in range(10):
        params = {"NextToken": next_token} if next_token else {}
        res = await _spapi_get(f"/orders/v0/orders/{order_id}/orderItems", params)
        if not res["ok"]:
            break
        payload = res["data"].get("payload") or {}
        items.extend(payload.get("OrderItems") or [])
        next_token = payload.get("NextToken")
        if not next_token:
            break
    return items


def _amz_addr(node: dict, fallback_name: str, email: str) -> dict:
    """Amazon ShippingAddress -> Facette adres bloğu. Ad 'Name' tek alandır → ilk/soyad ayrılır."""
    node = node or {}
    full_name = (node.get("Name") or fallback_name or "").strip()
    parts = full_name.split(" ", 1) if full_name else []
    first = (parts[0] if parts else "") or "Amazon"
    last = (parts[1] if len(parts) > 1 else "") or "Müşterisi"
    addr_line = " ".join([x for x in [node.get("AddressLine1"), node.get("AddressLine2"),
                                      node.get("AddressLine3")] if x]).strip()
    return {
        "first_name": first,
        "last_name": last,
        "phone": node.get("Phone", "") or "",
        "email": email or "",
        "address": addr_line,
        "city": node.get("City", "") or "",
        "district": node.get("County") or node.get("District") or node.get("StateOrRegion", "") or "",
        "country": node.get("CountryCode", "") or "",
        "postal_code": node.get("PostalCode", "") or "",
    }


def map_amazon_order(o: dict, items: list) -> dict:
    """Amazon Orders API sipariş + kalemlerini Facette db.orders şemasına eşler
    (map_trendyol_order deseniyle hizalı)."""
    from datetime import datetime, timezone
    order_id = o.get("AmazonOrderId")
    total_node = o.get("OrderTotal") or {}
    buyer = o.get("BuyerInfo") or {}
    ship = o.get("ShippingAddress") or {}
    buyer_email = buyer.get("BuyerEmail", "") or ""
    buyer_name = buyer.get("BuyerName", "") or ""

    mapped_items, subtotal = [], 0.0
    for it in (items or []):
        try:
            qty = int(it.get("QuantityOrdered") or 1) or 1
        except Exception:
            qty = 1
        try:
            line_amt = float((it.get("ItemPrice") or {}).get("Amount") or 0)
        except Exception:
            line_amt = 0.0
        unit = round(line_amt / qty, 2) if qty else line_amt
        sku = it.get("SellerSKU") or ""
        mapped_items.append({
            "product_id": sku,
            "product_name": it.get("Title", "") or "",
            "quantity": qty,
            "unit_price": unit,
            "discount_amount": 0,
            "price": unit,
            "size": "",
            "color": "",
            "barcode": sku,   # Facette stok eşlemesi variants.barcode ile yapılır
            "sku": sku,
            "asin": it.get("ASIN", "") or "",
            "currency": (it.get("ItemPrice") or {}).get("CurrencyCode") or "TRY",
        })
        subtotal += line_amt

    try:
        total_amt = float(total_node.get("Amount") or 0) or round(subtotal, 2)
    except Exception:
        total_amt = round(subtotal, 2)

    # Teslimat adı = kargo adresindeki ALICI adı (ShippingAddress.Name). Fatura adı = SİPARİŞ
    # VEREN (BuyerInfo.BuyerName) — ikisi farklı olabilir (hediye/başkası adına gönderim).
    ship_addr = _amz_addr(ship, buyer_name, buyer_email)
    bill_addr = dict(ship_addr)
    if buyer_name:
        _bp = buyer_name.split(" ", 1)
        bill_addr["first_name"] = _bp[0] or bill_addr.get("first_name")
        bill_addr["last_name"] = (_bp[1] if len(_bp) > 1 else "")
    if buyer_email:
        bill_addr["email"] = buyer_email
    status_raw = o.get("OrderStatus") or ""

    return {
        "order_number": str(order_id),
        "platform": "amazon",
        "amazon_order_id": order_id,
        "user_id": None,
        "items": mapped_items,
        "shipping_address": ship_addr,
        "billing_address": {**bill_addr, "company_name": "", "tax_number": "",
                            "tax_office": "", "is_corporate": False},
        "billing_info": {"is_corporate": False, "company_name": "", "tax_number": "",
                         "tax_office": "", "e_invoice_user": False},
        "subtotal": round(subtotal, 2) if subtotal else total_amt,
        "shipping_cost": 0,
        "discount_amount": 0,
        "total": total_amt,
        "payment_method": "marketplace",
        "payment_status": "paid",
        "status": _amz_status_of(status_raw),
        "marketplace_status": status_raw,
        "fulfillment_channel": o.get("FulfillmentChannel", "") or "",  # AFN=FBA(Amazon kargolar) / MFN=satıcı
        "is_prime": bool(o.get("IsPrime")),
        "is_business_order": bool(o.get("IsBusinessOrder")),
        "sales_channel": o.get("SalesChannel", "") or "",
        "amazon_currency": total_node.get("CurrencyCode", "") or "",
        "marketplace_order_date": o.get("PurchaseDate", "") or "",
        "marketplace_last_modified": o.get("LastUpdateDate", "") or "",
        "cargo_tracking_number": "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _amazon_push_stock_price(sku: str, quantity: int, price=None, currency: str = "TRY") -> dict:
    """Tek Amazon SKU'su için stok (+opsiyonel fiyat) PATCH'ler — Listings Items 2021-08-01,
    tek çağrıda fulfillment_availability + purchasable_offer. AMAZON_ALLOW_WRITE=0 iken dry-run
    (Amazon'a GİTMEZ, would_send döner). Stok/fiyat senkron job'ı bunu kullanır."""
    seller = await _require_seller_id()
    _, _, mp = await get_valid_access_token()
    try:
        qty = max(0, int(quantity))
    except Exception:
        qty = 0
    patches = [{
        "op": "replace",
        "path": "/attributes/fulfillment_availability",
        "value": [{"fulfillment_channel_code": "DEFAULT", "quantity": qty}],
    }]
    try:
        _pr = round(float(price), 2) if price is not None else 0
    except Exception:
        _pr = 0
    if _pr > 0:
        patches.append({
            "op": "replace",
            "path": "/attributes/purchasable_offer",
            "value": [{"marketplace_id": mp, "currency": (currency or "TRY").upper(),
                       "our_price": [{"schedule": [{"value_with_tax": _pr}]}]}],
        })
    body = {"productType": "PRODUCT", "patches": patches}
    return await _spapi_send("PATCH", f"/listings/2021-08-01/items/{seller}/{sku}",
                             body=body, params={"marketplaceIds": mp})


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
    # Denetim: kimlik bilgisi değişikliği loglanır (secret DEĞERİ loglanmaz).
    await _log_spapi_call(
        "config_save", ok=True, actor=current_user.get("email", ""),
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


@router.post("/orders/pull")
async def spapi_pull_orders_now(
    days: int = Query(3, ge=1, le=30),
    current_user: dict = Depends(require_admin),
):
    """Amazon siparişlerini ŞİMDİ panele çeker (manuel tetik). Otomatik cron ile AYNI
    mantığı kullanır: son `days` gün LastUpdatedAfter penceresi → yeni sipariş insert +
    iptal/kargo durum güncelle. Yeni siparişte (MFN) stok düşülür, FBA'da düşülmez."""
    from scheduler import _run_amazon_auto_orders_pull  # yerel import — döngü önleme
    res = await _run_amazon_auto_orders_pull(lookback_days=days)
    return {"success": True, **(res or {})}


@router.get("/orders/{order_number}/diagnose")
async def spapi_diagnose_order(order_number: str, current_user: dict = Depends(require_admin)):
    """TEŞHİS — tek Amazon siparişini uçtan uca açar: (1) config bayrakları, (2) panelde kayıtlı
    sipariş (isim/kalem/eşleşme/resim), (3) Amazon'un DÖNDÜRDÜĞÜ ham isim + SellerSKU/ASIN,
    (4) her SellerSKU için Facette ürün eşleşme denemesi (neden resim/stok gelmiyor GÖRÜLÜR).
    'Trendyol'da nasıl oluyorsa' problemini kesin teşhis için."""
    from .integrations_common import _facette_match_for_codes, _facette_product_image

    out = {
        "order_number": order_number,
        "flags": {
            "restricted_allowed": RESTRICTED_ALLOWED,
            "allow_write": ALLOW_WRITE,
        },
    }

    # (2) Panelde kayıtlı sipariş
    stored = await db.orders.find_one({"order_number": order_number, "platform": "amazon"}, {"_id": 0})
    if stored:
        sa = stored.get("shipping_address") or {}
        ba = stored.get("billing_address") or {}
        out["stored"] = {
            "found": True,
            "status": stored.get("status"),
            "shipping_name": f"{sa.get('first_name','')} {sa.get('last_name','')}".strip(),
            "billing_name": f"{ba.get('first_name','')} {ba.get('last_name','')}".strip(),
            "shipping_city": sa.get("city", ""),
            "needs_pii_refresh": stored.get("needs_pii_refresh"),
            "pii_attempts": stored.get("pii_attempts"),
            "items_enriched": stored.get("items_enriched"),
            "items": [{
                "product_name": it.get("product_name"),
                "sku": it.get("sku") or it.get("marketplace_sku"),
                "barcode": it.get("barcode"),
                "product_id": it.get("product_id"),
                "matched": it.get("matched"),
                "has_image": bool(it.get("image")),
                "quantity": it.get("quantity"),
            } for it in (stored.get("items") or [])],
        }
    else:
        out["stored"] = {"found": False}

    # (3)+(4) Amazon'dan canlı çek + eşleşme denemesi
    try:
        full = await _fetch_amazon_order_full(order_number)
        items = await _fetch_amazon_order_items(order_number)
        buyer = (full or {}).get("BuyerInfo") or {}
        ship = (full or {}).get("ShippingAddress") or {}
        out["amazon_live"] = {
            "order_status": (full or {}).get("OrderStatus"),
            "fulfillment_channel": (full or {}).get("FulfillmentChannel"),
            "buyer_name_raw": buyer.get("BuyerName", ""),
            "buyer_email_present": bool(buyer.get("BuyerEmail")),
            "ship_name_raw": ship.get("Name", ""),
            "ship_city": ship.get("City", ""),
            "pii_returned": bool(ship or buyer),  # RDT gerçekten PII getirdi mi?
            "items": [{
                "SellerSKU": it.get("SellerSKU"),
                "ASIN": it.get("ASIN"),
                "Title": it.get("Title"),
                "QuantityOrdered": it.get("QuantityOrdered"),
            } for it in (items or [])],
        }
        # Her SellerSKU için Facette eşleşme denemesi (import ile AYNI aday kodlar)
        match_report = []
        for it in (items or []):
            sku = it.get("SellerSKU") or ""
            m = await _facette_match_for_codes([sku])
            if m:
                prod, code, how = m
                match_report.append({
                    "SellerSKU": sku, "matched": True, "method": how,
                    "facette_product_id": prod.get("id"),
                    "facette_name": prod.get("name"),
                    "has_image": bool(_facette_product_image(prod)),
                })
            else:
                # Eşleşmedi → Facette'te bu koda benzer ne var? (ilk 3 örnek barkod/stok_kodu)
                sample = []
                async for p in db.products.find(
                    {"is_active": True}, {"_id": 0, "name": 1, "variants.barcode": 1, "variants.stock_code": 1}
                ).limit(3):
                    for v in (p.get("variants") or [])[:2]:
                        sample.append({"barcode": v.get("barcode"), "stock_code": v.get("stock_code")})
                match_report.append({
                    "SellerSKU": sku, "matched": False,
                    "hint": "Bu SellerSKU Facette variants.barcode/stock_code/sku/urun_id ile eşleşmedi.",
                    "facette_ornek_kodlar": sample[:4],
                })
        out["match_report"] = match_report
    except Exception as e:
        out["amazon_live_error"] = str(e)

    return out


# ============================== STOK / FİYAT / LISTING (yazma) ==============================
# Hepsi Listings Items API 2021-08-01 (PATCH) — Product Listing rolü yeterli.
# Fiyatı YAZMAK için Pricing rolü GEREKMEZ (Pricing rolü sadece rakip/Buy Box fiyatı OKUMAK için).
# İlk fazda ALLOW_WRITE=0 → dry-run; canlı yazma env ile açılır.

@router.get("/write-status")
async def spapi_write_status(current_user: dict = Depends(require_admin)):
    """Yazma modu açık mı (canlı) yoksa dry-run mu — panelde göstermek için."""
    return {"allow_write": ALLOW_WRITE, "mode": "live" if ALLOW_WRITE else "dry_run"}


@router.post("/inventory/{sku}")
async def spapi_set_inventory(sku: str, payload: dict, current_user: dict = Depends(require_admin)):
    """Stok gönder: Listings Items PATCH fulfillment_availability.
    Body: { quantity:int, product_type?:str, fulfillment_channel_code?:str }"""
    try:
        qty = max(0, int((payload or {}).get("quantity")))
    except Exception:
        raise HTTPException(status_code=400, detail="quantity (tam sayı) gerekli")
    seller = await _require_seller_id()
    _, _, mp = await get_valid_access_token()
    body = {
        "productType": (payload or {}).get("product_type") or "PRODUCT",
        "patches": [{
            "op": "replace",
            "path": "/attributes/fulfillment_availability",
            "value": [{
                "fulfillment_channel_code": (payload or {}).get("fulfillment_channel_code") or "DEFAULT",
                "quantity": qty,
            }],
        }],
    }
    res = await _spapi_send("PATCH", f"/listings/2021-08-01/items/{seller}/{sku}",
                            body=body, params={"marketplaceIds": mp})
    return {"success": res.get("ok"), "sku": sku, "quantity": qty, **res}


@router.post("/price/{sku}")
async def spapi_set_price(sku: str, payload: dict, current_user: dict = Depends(require_admin)):
    """Fiyat gönder (KENDİ fiyatımız): Listings Items PATCH purchasable_offer.
    Body: { price:float, currency?:str=TRY, product_type?:str }"""
    try:
        price = round(float((payload or {}).get("price")), 2)
        if price <= 0:
            raise ValueError()
    except Exception:
        raise HTTPException(status_code=400, detail="price (>0) gerekli")
    currency = ((payload or {}).get("currency") or "TRY").upper()
    seller = await _require_seller_id()
    _, _, mp = await get_valid_access_token()
    body = {
        "productType": (payload or {}).get("product_type") or "PRODUCT",
        "patches": [{
            "op": "replace",
            "path": "/attributes/purchasable_offer",
            "value": [{
                "marketplace_id": mp,
                "currency": currency,
                "our_price": [{"schedule": [{"value_with_tax": price}]}],
            }],
        }],
    }
    res = await _spapi_send("PATCH", f"/listings/2021-08-01/items/{seller}/{sku}",
                            body=body, params={"marketplaceIds": mp})
    return {"success": res.get("ok"), "sku": sku, "price": price, "currency": currency, **res}


@router.patch("/listing/{sku}")
async def spapi_patch_listing(sku: str, payload: dict, current_user: dict = Depends(require_admin)):
    """Genel listing güncelle: çağıran JSON-patch listesi verir.
    Body: { patches:[{op,path,value}], product_type?:str }. Yeni SKU için PUT gerekiyorsa
    ayrı ele alınır — ilk faz mevcut SKU güncelleme odaklı."""
    patches = (payload or {}).get("patches")
    if not isinstance(patches, list) or not patches:
        raise HTTPException(status_code=400, detail="patches (liste) gerekli")
    seller = await _require_seller_id()
    _, _, mp = await get_valid_access_token()
    body = {"productType": (payload or {}).get("product_type") or "PRODUCT", "patches": patches}
    res = await _spapi_send("PATCH", f"/listings/2021-08-01/items/{seller}/{sku}",
                            body=body, params={"marketplaceIds": mp})
    return {"success": res.get("ok"), "sku": sku, **res}


# ============================== FİNANS + FİYAT OKUMA (read) ==============================

@router.get("/finances")
async def spapi_finances(days: int = Query(30, ge=1, le=180),
                         current_user: dict = Depends(require_admin)):
    """Finansal olaylar (Finances API v0) — PII'siz (tutar/komisyon/ücret; alıcı bilgisi YOK).
    Finance and Accounting rolü gerekir."""
    posted_after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res = await _spapi_get("/finances/v0/financialEvents",
                           {"PostedAfter": posted_after, "MaxResultsPerPage": 100})
    if not res["ok"]:
        return {"success": False, "status": res["status"], "error": res["data"]}
    groups = (res["data"].get("payload") or {}).get("FinancialEvents") or {}
    # PII'siz özet: yalnız event tipleri + adet (ham finansal detay Amazon'da; burada özet).
    summary = {k: len(v) for k, v in groups.items() if isinstance(v, list)}
    return {"success": True, "event_types": summary, "raw_keys": list(groups.keys())}


@router.get("/pricing/{sku}")
async def spapi_read_pricing(sku: str, current_user: dict = Depends(require_admin)):
    """Amazon fiyatı / offer OKUMA (Product Pricing API v0). Pricing rolü gerekir.
    NOT: Kendi fiyatımızı YAZMAK için bu rol GEREKMEZ; bu yalnız OKUMA içindir."""
    _, _, mp = await get_valid_access_token()
    res = await _spapi_get("/products/pricing/v0/price",
                           {"MarketplaceId": mp, "ItemType": "Sku", "Skus": sku})
    return {"success": res["ok"], "status": res["status"], "data": res.get("data")}


@router.get("/offers/{sku}")
async def spapi_read_offers(sku: str, condition: str = Query("New"),
                            current_user: dict = Depends(require_admin)):
    """Offer / Buy Box OKUMA (getListingOffers). Pricing rolü gerekir. PII'siz."""
    _, _, mp = await get_valid_access_token()
    res = await _spapi_get(f"/products/pricing/v0/listings/{sku}/offers",
                           {"MarketplaceId": mp, "ItemCondition": condition})
    return {"success": res["ok"], "status": res["status"], "data": res.get("data")}


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
    # GÜVENLİK (CSRF): oauth_state tanımlıysa, gelen state MUTLAKA verilmeli VE eşleşmeli.
    # Eskiden `and state` kısa devresi yüzünden state="" gönderilince kontrol ATLANIYORDU.
    _expected_state = cfg.get("oauth_state")
    if _expected_state and (not state or state != _expected_state):
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
