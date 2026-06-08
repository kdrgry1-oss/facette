"""
=============================================================================
payment.py — iyzico Checkout Form (Ödeme Formu) ödeme akışı
=============================================================================

Storefront checkout akışının eksik backend parçası:

  POST /api/payment/initialize  → siparişi iyzico Ödeme Formu'na hazırlar,
                                   paymentPageUrl (hosted) veya
                                   checkoutFormContent (iframe) döndürür.
  POST /api/payment/callback    → iyzico ödeme sonrası token'ı POST eder;
  GET  /api/payment/callback       token ile sonuç sorgulanır (retrieve),
                                   sipariş "ödendi" işaretlenir, kullanıcı
                                   return_url'e (storefront /odeme) yönlendirilir.

Kimlik doğrulama: IYZWSv2 (HMAC-SHA256) — yeni iyzico şeması.
Ayarlar: db.settings (id="iyzico") → api_key, api_secret, mode(live/sandbox).
=============================================================================
"""
import base64
import hashlib
import hmac
import json
import re
import secrets as _secrets
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import RedirectResponse

from .deps import db, logger

router = APIRouter(prefix="/payment", tags=["Payment"])

INIT_PATH = "/payment/iyzipos/checkoutform/initialize/auth/ecom"
RETRIEVE_PATH = "/payment/iyzipos/checkoutform/auth/ecom/detail"
DEFAULT_TCKN = "11111111111"


async def _get_iyzico_settings() -> dict:
    s = await db.settings.find_one({"id": "iyzico"}, {"_id": 0})
    if not s or not s.get("api_key") or not s.get("api_secret"):
        raise HTTPException(status_code=400, detail="iyzico ödeme bilgileri eksik. Lütfen admin panelinden ayarlayın.")
    mode = s.get("mode", "sandbox")
    base = "https://api.iyzipay.com" if mode == "live" else "https://sandbox-api.iyzipay.com"
    return {"api_key": s["api_key"], "api_secret": s["api_secret"], "mode": mode, "base_url": base}


def _v2_headers(api_key: str, secret_key: str, path: str, body_str: str) -> dict:
    """iyzico IYZWSv2 HMAC-SHA256 authorization header (randomKey + path + body imzalanır)."""
    random_key = _secrets.token_hex(16)
    to_sign = f"{random_key}{path}{body_str}"
    sig = hmac.new(secret_key.encode("utf-8"), to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    auth_str = f"apiKey:{api_key}&randomKey:{random_key}&signature:{sig}"
    b64 = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"IYZWSv2 {b64}",
        "x-iyzi-rnd": random_key,
        "Content-Type": "application/json",
    }


def _fmt(v: float) -> str:
    return f"{round(float(v or 0), 2):.2f}"


def _format_gsm(phone: str) -> str:
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if not digits:
        return "+905555555555"
    if digits.startswith("90") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 11:
        return "+90" + digits[1:]
    if len(digits) == 10:
        return "+90" + digits
    return "+" + digits


def _build_initialize_payload(order: dict, callback_url: str) -> dict:
    ship = order.get("shipping_address") or {}
    bill = order.get("billing_address") or ship
    binfo = order.get("billing_info") or {}

    first = (ship.get("first_name") or "").strip() or "Müşteri"
    last = (ship.get("last_name") or "").strip() or "Facette"
    contact = f"{first} {last}".strip()
    _raw_email = (ship.get("email") or order.get("email") or "").strip()
    email = _raw_email if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", _raw_email) else "siparis@facette.com.tr"
    address = (ship.get("address") or "Adres").strip()
    city = (ship.get("city") or "İstanbul").strip()
    zipcode = str(ship.get("postal_code") or ship.get("zip_code") or "34000")
    ip = order.get("customer_ip") or "85.34.78.112"

    # TCKN: kurumsal faturada 11 hane TCKN varsa onu, yoksa varsayılan placeholder
    tn = "".join(ch for ch in str(binfo.get("tax_number") or "") if ch.isdigit())
    identity = tn if len(tn) == 11 else DEFAULT_TCKN

    bill_first = (bill.get("first_name") or first).strip()
    bill_last = (bill.get("last_name") or last).strip()
    bill_contact = f"{bill_first} {bill_last}".strip() or contact
    bill_address = (bill.get("address") or address).strip()
    bill_city = (bill.get("city") or city).strip()
    bill_zip = str(bill.get("postal_code") or bill.get("zip_code") or zipcode)

    # ----- Sepet kalemleri (toplamı price'a eşit olmalı; indirim paidPrice'tan düşülür) -----
    basket_items = []
    items_sum = 0.0
    for it in (order.get("items") or []):
        qty = int(it.get("quantity") or 1)
        line = round(float(it.get("price") or 0) * qty, 2)
        items_sum += line
        basket_items.append({
            "id": str(it.get("product_id") or it.get("id") or "item"),
            "name": (it.get("name") or "Ürün")[:200],
            "category1": (it.get("category") or it.get("category_name") or "Giyim")[:60],
            "itemType": "PHYSICAL",
            "price": _fmt(line),
        })

    shipping_cost = float(order.get("shipping_cost") or 0)
    gift_price = float(order.get("gift_wrap_price") or 0)
    cod_fee = 10.0 if order.get("payment_method") == "cash_on_delivery" else 0.0

    if shipping_cost > 0:
        basket_items.append({"id": "shipping", "name": "Kargo Ücreti", "category1": "Kargo", "itemType": "VIRTUAL", "price": _fmt(shipping_cost)})
    if gift_price > 0:
        basket_items.append({"id": "gift-wrap", "name": "Hediye Paketi", "category1": "Hediye", "itemType": "VIRTUAL", "price": _fmt(gift_price)})
    if cod_fee > 0:
        basket_items.append({"id": "cod-fee", "name": "Kapıda Ödeme Hizmeti", "category1": "Hizmet", "itemType": "VIRTUAL", "price": _fmt(cod_fee)})

    price = round(items_sum + shipping_cost + gift_price + cod_fee, 2)
    paid_price = round(float(order.get("total") or price), 2)
    # paidPrice price'ı geçemez (indirim sadece düşürür)
    if paid_price > price:
        paid_price = price
    if paid_price <= 0:
        paid_price = price

    return {
        "locale": "tr",
        "conversationId": str(order.get("id")),
        "price": _fmt(price),
        "paidPrice": _fmt(paid_price),
        "currency": "TRY",
        "basketId": str(order.get("order_number") or order.get("id")),
        "paymentGroup": "PRODUCT",
        "callbackUrl": callback_url,
        "enabledInstallments": [1, 2, 3, 6, 9],
        "buyer": {
            "id": str(order.get("user_id") or order.get("id")),
            "name": first,
            "surname": last,
            "identityNumber": identity,
            "email": email,
            "gsmNumber": _format_gsm(ship.get("phone")),
            "registrationAddress": address,
            "city": city,
            "country": "Turkey",
            "zipCode": zipcode,
            "ip": ip,
        },
        "shippingAddress": {
            "contactName": contact,
            "city": city,
            "country": "Turkey",
            "address": address,
            "zipCode": zipcode,
        },
        "billingAddress": {
            "contactName": bill_contact,
            "city": bill_city,
            "country": "Turkey",
            "address": bill_address,
            "zipCode": bill_zip,
        },
        "basketItems": basket_items,
    }


@router.post("/initialize")
async def initialize_payment(order_id: str, callback_url: str, return_url: str = ""):
    """Sipariş için iyzico Ödeme Formu başlatır."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    settings = await _get_iyzico_settings()
    payload = _build_initialize_payload(order, callback_url)
    body_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    headers = _v2_headers(settings["api_key"], settings["api_secret"], INIT_PATH, body_str)

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(f"{settings['base_url']}{INIT_PATH}", content=body_str.encode("utf-8"), headers=headers)
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"status": "failure", "errorMessage": resp.text[:300]}
    except Exception as e:
        logger.error(f"iyzico initialize error: {e}")
        raise HTTPException(status_code=502, detail=f"iyzico bağlantı hatası: {e}")

    if data.get("status") != "success":
        logger.warning(f"iyzico initialize failed order={order_id}: {data.get('errorCode')} {data.get('errorMessage')}")
        return {
            "success": False,
            "error": data.get("errorMessage") or "Ödeme başlatılamadı",
            "errorCode": data.get("errorCode"),
        }

    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "iyzico_token": data.get("token"),
            "iyzico_conversation_id": data.get("conversationId"),
            "iyzico_return_url": return_url,
            "payment_provider": "iyzico",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    return {
        "success": True,
        "token": data.get("token"),
        "paymentPageUrl": data.get("paymentPageUrl"),
        "checkoutFormContent": data.get("checkoutFormContent"),
    }


async def _retrieve_and_finalize(token: str) -> dict:
    """token ile iyzico'dan sonucu çeker, siparişi günceller. Döner: {ok, order, return_url}."""
    order = await db.orders.find_one({"iyzico_token": token}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Ödeme token'ı için sipariş bulunamadı")

    settings = await _get_iyzico_settings()
    payload = {"locale": "tr", "conversationId": str(order.get("id")), "token": token}
    body_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    headers = _v2_headers(settings["api_key"], settings["api_secret"], RETRIEVE_PATH, body_str)

    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.post(f"{settings['base_url']}{RETRIEVE_PATH}", content=body_str.encode("utf-8"), headers=headers)
    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"status": "failure"}

    paid = (data.get("status") == "success") and (data.get("paymentStatus") == "SUCCESS")
    update = {
        "iyzico_retrieve_response": {
            "status": data.get("status"),
            "paymentStatus": data.get("paymentStatus"),
            "errorMessage": data.get("errorMessage"),
            "paymentId": data.get("paymentId"),
            "paidPrice": data.get("paidPrice"),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if paid:
        update["payment_status"] = "paid"
        update["payment_id"] = data.get("paymentId")
        update["iyzico_payment_id"] = data.get("paymentId")
        update["paid_at"] = datetime.now(timezone.utc).isoformat()
        update["status"] = "confirmed"
    else:
        update["payment_status"] = "failed"

    await db.orders.update_one({"id": order.get("id")}, {"$set": update})
    logger.info(f"iyzico payment {'PAID' if paid else 'FAILED'} order={order.get('order_number')} pid={data.get('paymentId')}")
    return {"ok": paid, "order": order, "return_url": order.get("iyzico_return_url") or ""}


@router.api_route("/callback", methods=["POST", "GET"])
async def payment_callback(request: Request, token: str = Form(default=None)):
    """iyzico ödeme sonrası buraya yönlendirir; sonucu doğrulayıp storefront'a geri yollar."""
    tok = token
    if not tok:
        tok = request.query_params.get("token")
    if not tok:
        try:
            form = await request.form()
            tok = form.get("token")
        except Exception:
            tok = None

    if not tok:
        raise HTTPException(status_code=400, detail="Ödeme token'ı bulunamadı")

    result = await _retrieve_and_finalize(tok)
    order = result["order"]
    return_base = result["return_url"] or f"{str(request.base_url).rstrip('/')}/odeme"
    sep = "&" if "?" in return_base else "?"
    status = "success" if result["ok"] else "fail"
    redirect = f"{return_base}{sep}status={status}&order={order.get('order_number')}"
    # 303: tarayıcı POST'u GET'e çevirip storefront'a gider
    return RedirectResponse(url=redirect, status_code=303)
