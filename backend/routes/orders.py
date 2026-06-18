"""
Order routes - CRUD, checkout, tracking
"""
from fastapi import APIRouter, HTTPException, Query, Depends, Response, Request, UploadFile, File, Form, Body
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import time
import uuid

from .deps import db, logger, get_current_user, require_admin, require_permission, generate_id
from .attribution import resolve_attribution_for_order
from pymongo import ReturnDocument

router = APIRouter(prefix="/orders", tags=["Orders"])

def _platform_display(order) -> str:
    p = (str(order.get("platform") or order.get("marketplace") or "")).strip().lower()
    return {"trendyol": "Trendyol", "hepsiburada": "Hepsiburada"}.get(
        p, "Site" if p in ("", "facette", "site") else p.title())


async def _log_order_event(order_id: str, event_type: str, description: str,
                           current_user: dict = None, meta: dict = None,
                           order_number: str = None):
    """Sipariş işlem geçmişi (audit log) kaydı → db.order_events.

    Her sipariş aksiyonunda (durum, ödeme, kargo, not, fatura, iade) bir iz
    bırakır. Tasarım gereği HİÇBİR ZAMAN isteği bozmaz; hata olursa sadece
    uyarı loglar. `stock_movements` deseninin birebir kardeşidir.
    """
    try:
        if order_number is None:
            _o = await db.orders.find_one({"id": order_id}, {"_id": 0, "order_number": 1})
            order_number = (_o or {}).get("order_number", "")
        await db.order_events.insert_one({
            "id": str(uuid.uuid4()),
            "order_id": order_id,
            "order_number": order_number or "",
            "event_type": event_type,
            "description": description,
            "actor": (current_user or {}).get("email", "") if current_user else "",
            "meta": meta or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as _e:  # pragma: no cover - log asla isteği bozmaz
        logger.warning(f"order_event log failed for {order_id}: {_e}")


async def _enrich_items_with_products(items):
    """Sipariş kalemlerini barkodla products'tan zenginleştir: Marka + KDV oranı.

    Stored veriyi DEĞİŞTİRMEZ; sadece okuma anında (detay) ekler. Tek bir $in
    sorgusuyla hem ürün hem varyant barkodunu eşler. Hata olursa items'ı olduğu
    gibi döndürür. (Desi/ağırlık ürün şemasında yok — eklenmez.)
    """
    try:
        if not items:
            return items
        bset = list({str(it.get("barcode") or "").strip() for it in items if (it.get("barcode") or "").strip()})
        if not bset:
            return items
        bmap = {}
        cursor = db.products.find(
            {"$or": [{"barcode": {"$in": bset}}, {"variants.barcode": {"$in": bset}}]},
            {"_id": 0, "barcode": 1, "brand": 1, "vat_rate": 1, "variants.barcode": 1},
        )
        async for p in cursor:
            meta = {"brand": p.get("brand") or "", "vat_rate": p.get("vat_rate")}
            pb = str(p.get("barcode") or "").strip()
            if pb:
                bmap[pb] = meta
            for v in (p.get("variants") or []):
                vb = str(v.get("barcode") or "").strip()
                if vb:
                    bmap[vb] = meta
        for it in items:
            m = bmap.get(str(it.get("barcode") or "").strip())
            if not m:
                continue
            if not it.get("brand") and m.get("brand"):
                it["brand"] = m["brand"]
            if it.get("vat_rate") in (None, "") and m.get("vat_rate") is not None:
                it["vat_rate"] = m["vat_rate"]
        return items
    except Exception as _e:  # pragma: no cover
        logger.warning(f"item enrich failed: {_e}")
        return items


async def _order_notify_vars(order: dict, **extra) -> dict:
    """Bir sipariş dokümanından TÜM bildirim değişkenlerini (email + SMS şablonlarının
    kullandığı her placeholder) tek elden üretir. Amaç: hiçbir ma/sms'te {order_date},
    {items_html}, {subtotal}, {shipping_*}, {tracking_*} gibi alanlar BOŞ/ham kalmasın.
    Her order-bildirim çağrısı bunu kullanır → değişken↔veri köprüsü her yerde aynı.
    **extra ile event'e özel değerler (return_code, refund_amount, reason...) eklenir/üzerine yazılır.
    """
    import os as _os
    ship = order.get("shipping_address") or {}
    full_name = (f"{ship.get('first_name','')} {ship.get('last_name','')}".strip()
                 or ship.get("full_name") or ship.get("name") or "Müşterimiz")

    # Kalemler tablosu (items_html) — sipariş onay mailindeki ürün listesi
    items_rows = ""
    for it in (order.get("items") or []):
        name = it.get("name") or it.get("product_name") or "Ürün"
        qty = int(it.get("quantity") or 1)
        price = float(it.get("price") or 0)
        size = (it.get("size") or it.get("variant_size") or "")
        color = (it.get("color") or it.get("variant_color") or "")
        img = (it.get("image") or it.get("image_url") or it.get("thumbnail")
               or (it.get("images") or [""])[0] if it.get("images") else
               (it.get("image") or it.get("image_url") or it.get("thumbnail") or ""))
        meta = " · ".join([x for x in [f"Beden: {size}" if size else "",
                                       f"Renk: {color}" if color else "",
                                       f"Adet: {qty}"] if x])
        items_rows += (
            f'<tr><td style="padding:12px 0;border-bottom:1px solid #f0f0f0;width:80px;">'
            f'<img src="{img}" alt="" style="width:64px;height:80px;object-fit:cover;background:#fafafa;"/></td>'
            f'<td style="padding:12px 12px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#111;">{name}'
            f'<div style="color:#999;font-size:11px;margin-top:4px;">{meta}</div></td>'
            f'<td style="padding:12px 0;border-bottom:1px solid #f0f0f0;text-align:right;font-size:13px;color:#111;white-space:nowrap;">{(price*qty):.2f} TL</td></tr>'
        )
    items_html = ('<div style="padding:0 24px 16px;"><table cellpadding="0" cellspacing="0" border="0" '
                  f'style="width:100%;">{items_rows}</table></div>') if items_rows else ""

    base_url = (_os.environ.get("FRONTEND_PUBLIC_URL") or _os.environ.get("REACT_APP_BACKEND_URL")
                or _os.environ.get("SITE_URL") or "https://facette.com.tr").rstrip("/")
    onum = order.get("order_number") or order.get("id") or ""
    order_link = f"{base_url}/order-success/{onum}" if base_url else "#"
    order_date = str(order.get("created_at") or "")[:10]

    subtotal = float(order.get("subtotal") or 0)
    shipping_cost = float(order.get("shipping_cost") or 0)
    discount = float(order.get("discount") or order.get("discount_amount") or 0)
    total = float(order.get("total") or 0)

    cargo = order.get("cargo") or {}
    real_tn = (order.get("cargo_tracking_number") or cargo.get("tracking_number") or "")
    track_link = (order.get("cargo_tracking_link") or cargo.get("tracking_link")
                  or (f"https://kargotakip.dhlecommerce.com.tr/?takipNo={real_tn}" if real_tn
                      else "https://www.dhlecommerce.com.tr/gonderitakip"))
    cargo_provider = (order.get("cargo_provider_name") or cargo.get("provider_name") or "MNG Kargo")

    try:
        from order_statuses import customer_label_for as _clf
        status_label = _clf(order.get("status") or "")
    except Exception:
        status_label = ""

    # Havale/EFT → banka bilgileri (ödeme bekleyen siparişlerde mailde gösterilir)
    bank = {}
    if (order.get("status") == "awaiting_payment"
            or (order.get("payment_method") or "").lower() in
            ("bank_transfer", "havale", "eft", "havale_eft", "banka_havale", "havale/eft")):
        try:
            _pay = await db.settings.find_one({"id": "payment"}, {"_id": 0}) or {}
            _banks = _pay.get("bank_accounts") or []
            bank = next((b for b in _banks if b.get("is_default")), None) or (_banks[0] if _banks else {})
        except Exception:
            bank = {}

    v = {
        "customer_name": full_name,
        "first_name": ship.get("first_name", "") or (full_name.split(" ")[0] if full_name else ""),
        "name": full_name,
        "order_number": onum,
        "order_date": order_date,
        "amount": f"{total:.2f} TL",
        "subtotal": f"{subtotal:.2f}",
        "shipping_cost": f"{shipping_cost:.2f}",
        "discount": f"{discount:.2f}",
        "total": f"{total:.2f}",
        "items_html": items_html,
        "shipping_full_name": full_name,
        "shipping_address": ship.get("address", ""),
        "shipping_city": ship.get("city", ""),
        "shipping_district": ship.get("district", ""),
        "shipping_phone": ship.get("phone", ""),
        "tracking_number": real_tn,
        "tracking_link": track_link,
        "tracking_url": track_link,
        "cargo_provider": cargo_provider,
        "cargo_company": cargo_provider,
        "status_label": status_label,
        "order_link": order_link,
        "site_url": base_url,
        "cart_url": f"{base_url}/sepet",
        "bank_name": (bank or {}).get("bank_name", ""),
        "bank_branch": (bank or {}).get("branch", ""),
        "bank_iban": (bank or {}).get("iban", ""),
        "bank_account_holder": (bank or {}).get("account_holder", ""),
        "payment_url": (f"{base_url}/odeme-bildirimi/{onum}" if base_url else order_link),
    }
    if extra:
        v.update({k: val for k, val in extra.items() if val is not None})
    return v


async def _product_vat_map(order: dict) -> dict:
    """Sipariş kalemlerinin ürünlerinden product_id → vat_rate (KDV) haritası.
    Fatura kesiminde, kalemde vat_rate yoksa ürünün KDV oranı kullanılır (DİNAMİK)."""
    pids = list({it.get("product_id") for it in (order.get("items") or []) if it.get("product_id")})
    m = {}
    if pids:
        try:
            async for p in db.products.find({"id": {"$in": pids}}, {"_id": 0, "id": 1, "vat_rate": 1}):
                if p.get("vat_rate") not in (None, ""):
                    m[p["id"]] = float(p["vat_rate"])
        except Exception:
            pass
    return m


def _item_kdv(it: dict, vat_map: dict, default: float = 20.0) -> float:
    """Kalem KDV oranı: önce kalemin vat_rate/kdv_rate'i, sonra ürünün vat_rate'i, en son default.
    Eskiden sabit 10.0'a düşüyordu; artık ürün içindeki gerçek KDV alanına köprüleniyor."""
    for cand in (it.get("vat_rate"), it.get("kdv_rate"), vat_map.get(it.get("product_id"))):
        if cand not in (None, ""):
            try:
                return float(cand)
            except Exception:
                pass
    return float(default)


def generate_order_number() -> str:
    import secrets
    return f"FC{int(time.time())}{secrets.token_hex(2).upper()}"

async def next_order_number() -> str:
    """Kısa, sıralı site sipariş numarası: W10001, W10002, ...
    Atomik sayaç (db.counters) ile çakışma imkânsız. Sayaç başarısız olursa
    kısa, W ön ekli bir fallback üretir; sipariş oluşturma asla kırılmaz."""
    try:
        doc = await db.counters.find_one_and_update(
            {"_id": "order_seq"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return f"W{10000 + int(doc['seq'])}"
    except Exception as e:
        logger.warning(f"order_seq sayaci basarisiz, fallback kullaniliyor: {e}")
        import secrets
        return f"W{int(time.time()) % 1000000}{secrets.token_hex(1).upper()}"

# Sipariş listesi sayım (count) önbelleği — büyük koleksiyonda count_documents her
# istekte koleksiyonu tarıyor (özellikle valid/hide_closed gibi $nor/$nin filtrelerinde
# pahalı). Aynı filtre için kısa süre cache'leyip sayfalama/yenilemede tekrar taramayı
# önleriz. Filtre imzası skip/limit içermez → tüm sayfalar aynı toplamı paylaşır.
_ORDERS_COUNT_CACHE = {}   # sig -> (count, monotonic_ts)
_ORDERS_COUNT_TTL = 60.0   # sn

@router.get("")
async def get_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=1000),
    status: Optional[str] = None,
    search: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    order_number: Optional[str] = None,
    cargo_tracking: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    payment_method: Optional[str] = None,
    platform: Optional[str] = None,
    invoice_number: Optional[str] = None,
    payment_status: Optional[str] = None,
    channel: Optional[str] = None,
    source: Optional[str] = None,
    coupon_code: Optional[str] = None,
    influencer: Optional[str] = None,
    is_corporate: Optional[str] = None,
    payment_view: Optional[str] = "all",
    hide_closed: Optional[str] = None,
    current_user: dict = Depends(require_admin)
):
    """Get orders with pagination (admin only)"""
    skip = (page - 1) * limit
    query = {}
    
    if status:
        _st = [x.strip() for x in str(status).split(",") if x.strip()]
        query["status"] = _st[0] if len(_st) == 1 else {"$in": _st}
    elif str(hide_closed).lower() in ("0", "false"):
        # Açıkça "kapalı durumları da göster" istendi → durum filtresi uygulanmaz.
        pass
    else:
        # VARSAYILAN: ana "Tüm Siparişler" görünümünde iptal/iade/iade-bedeli kapalı
        # durumları GİZLE. Böylece iptal edilen sipariş ana listede KALMAZ; yalnızca
        # İptaller / İade Edilenler sayfalarında (status= ile) listelenir.
        # return_approved = iade onaylandı, "İade Bedeli Öde" aşamasında → buradan da çıkar.
        query["status"] = {"$nin": ["cancelled", "returned", "refunded", "return_approved"]}
    if phone:
        query["shipping_address.phone"] = {"$regex": phone, "$options": "i"}
    if email:
        query["shipping_address.email"] = {"$regex": email, "$options": "i"}
    if order_number:
        query["order_number"] = {"$regex": order_number, "$options": "i"}
    if cargo_tracking:
        query["cargo_tracking"] = {"$regex": cargo_tracking, "$options": "i"}
    if payment_method:
        _pm = [x.strip() for x in str(payment_method).split(",") if x.strip()]
        query["payment_method"] = {"$in": _pm} if len(_pm) > 1 else (_pm[0] if _pm else payment_method)
    if platform:
        _pf = [x.strip() for x in str(platform).split(",") if x.strip()]
        query["platform"] = {"$in": _pf} if len(_pf) > 1 else (_pf[0] if _pf else platform)
    if invoice_number:
        query["invoice_number"] = {"$regex": invoice_number, "$options": "i"}
    if payment_status:
        _ps = [x.strip() for x in str(payment_status).split(",") if x.strip()]
        query["payment_status"] = {"$in": _ps} if len(_ps) > 1 else (_ps[0] if _ps else payment_status)
    if channel:
        # Çoklu seçim: virgülle gelen değerler regex alternation'a çevrilir (organic,ads|paid → organic|ads|paid)
        _ch = str(channel).replace(",", "|").strip("|")
        query["attribution.channel"] = {"$regex": _ch, "$options": "i"}
    if source:
        query["attribution.source"] = {"$regex": source, "$options": "i"}
    if coupon_code:
        query["coupon_code"] = {"$regex": coupon_code, "$options": "i"}
    if influencer and str(influencer).lower() not in ("0", "false", ""):
        query["influencer_id"] = {"$exists": True, "$ne": None}
    if is_corporate and str(is_corporate).lower() not in ("0", "false", ""):
        query["billing_info.is_corporate"] = True
        
    date_query = {}
    if start_date:
        date_query["$gte"] = start_date
    if end_date:
        date_query["$lte"] = end_date
    if date_query:
        query["created_at"] = date_query
    
    if search:
        query["$or"] = [
            {"order_number": {"$regex": search, "$options": "i"}},
            {"invoice_number": {"$regex": search, "$options": "i"}},
            {"cargo_tracking": {"$regex": search, "$options": "i"}},
            {"shipping_address.first_name": {"$regex": search, "$options": "i"}},
            {"shipping_address.last_name": {"$regex": search, "$options": "i"}},
            {"shipping_address.phone": {"$regex": search, "$options": "i"}},
            {"shipping_address.email": {"$regex": search, "$options": "i"}}
        ]
    
    # Ödeme kaydı bulunmayan (web kart denemesi, hiç ödenmemiş) ayrımı
    _web_cond = {"$or": [{"platform": "facette"}, {"platform": {"$in": [None, ""]}}, {"platform": {"$exists": False}}]}
    _settled_pay = ["paid", "completed", "success", "succeeded", "captured"]
    _offline_pm = ["bank_transfer", "cash_on_delivery"]
    _fulfilled_status = ["confirmed", "processing", "preparing", "shipped", "delivered", "completed", "undelivered", "cancelled"]
    _junk_cond = {"$and": [
        _web_cond,
        {"payment_status": {"$nin": _settled_pay}},
        {"payment_method": {"$nin": _offline_pm}},
        {"status": {"$nin": _fulfilled_status}},
    ]}
    if payment_view == "unpaid":
        query.setdefault("$and", []).append(_junk_cond)
    elif payment_view == "valid":
        query.setdefault("$and", []).append({"$nor": [_junk_cond]})

    # PERF: find ve count'u paralel çalıştır (ardışık değil) + count'u kısa süre
    # önbellekle. Önceden find→count ardışıktı ve karmaşık filtrede toplam ~8 sn
    # sürüyordu; soğuk önbellekte paralel + cache çok daha hızlı.
    import asyncio as _aio
    import json as _json
    _sig = _json.dumps(query, sort_keys=True, default=str)
    _now = time.monotonic()
    _cached = _ORDERS_COUNT_CACHE.get(_sig)

    async def _do_find():
        # created_at KARIŞIK TİPTE olabilir: bazı eski/migrasyon kayıtları BSON Date,
        # çoğu ISO string. MongoDB karışık tipte önce TİP'e göre sıralar → tüm Date tipli
        # kayıtlar (ör. Ticimax'tan taşınanlar) string tarihlerin üstüne çıkar ve liste
        # gerçek tarih sırasını kaybeder. Bu yüzden created_at'i $convert ile Date'e
        # normalize edip ona göre sıralarız (EN YENİ EN ÜSTTE), tip ne olursa olsun.
        _pipe = [
            {"$match": query},
            {"$addFields": {"_sort_dt": {"$convert": {
                "input": "$created_at", "to": "date", "onError": None, "onNull": None
            }}}},
            {"$sort": {"_sort_dt": -1, "created_at": -1, "_id": -1}},
            {"$skip": skip},
            {"$limit": limit},
            {"$project": {"_id": 0, "_sort_dt": 0}},
        ]
        return await db.orders.aggregate(_pipe, allowDiskUse=True).to_list(limit)

    if _cached and (_now - _cached[1] < _ORDERS_COUNT_TTL):
        orders = await _do_find()
        total = _cached[0]
    else:
        orders, total = await _aio.gather(_do_find(), db.orders.count_documents(query))
        _ORDERS_COUNT_CACHE[_sig] = (total, _now)
        # cache'i sınırla (sınırsız büyümesin)
        if len(_ORDERS_COUNT_CACHE) > 200:
            _oldest = min(_ORDERS_COUNT_CACHE.items(), key=lambda kv: kv[1][1])[0]
            _ORDERS_COUNT_CACHE.pop(_oldest, None)

    # Pazaryeri (Trendyol vb.) kalemlerinde görsel yoksa barkodla yerel üründen eşle.
    # Barkodlar Trendyol ile aynı olduğundan doğrudan eşleşir; mevcut siparişler için
    # re-sync gerekmez (okuma anında zenginleştirilir).
    try:
        _need = set()
        for _o in orders:
            for _it in (_o.get("items") or []) + (_o.get("lines") or []):
                if not _it.get("image"):
                    _bc = str(_it.get("barcode") or "").strip()
                    if _bc:
                        _need.add(_bc)
        if _need:
            _need_list = list(_need)
            _prods = await db.products.find(
                {"$or": [{"barcode": {"$in": _need_list}}, {"variants.barcode": {"$in": _need_list}}]},
                {"_id": 0, "barcode": 1, "image": 1, "images": 1, "thumbnail": 1, "variants": 1},
            ).to_list(1000)

            def _first_img(pr):
                for im in (pr.get("images") or []):
                    if isinstance(im, str) and im:
                        return im
                    if isinstance(im, dict):
                        u = im.get("url") or im.get("src") or im.get("image")
                        if u:
                            return u
                return pr.get("image") or pr.get("thumbnail") or ""

            _img_by_bc = {}
            for _pr in _prods:
                _img = _first_img(_pr)
                if not _img:
                    continue
                _pb = str(_pr.get("barcode") or "").strip()
                if _pb:
                    _img_by_bc.setdefault(_pb, _img)
                for _v in (_pr.get("variants") or []):
                    _vb = str(_v.get("barcode") or "").strip()
                    if _vb:
                        _img_by_bc.setdefault(_vb, _img)

            if _img_by_bc:
                for _o in orders:
                    for _it in (_o.get("items") or []) + (_o.get("lines") or []):
                        if not _it.get("image"):
                            _bc = str(_it.get("barcode") or "").strip()
                            if _bc and _img_by_bc.get(_bc):
                                _it["image"] = _img_by_bc[_bc]
    except Exception as _e:
        logger.warning(f"order image enrich skipped: {_e}")

    return {
        "orders": orders,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

@router.get("/by-number/{order_number}")
async def get_order_by_number(order_number: str):
    """Sipariş numarasıyla siparişi getir (public — ödeme sonrası başarı sayfası için).
    PII maskelenir (telefon/email son kısımları gizlenir, adres detayı sınırlanır)."""
    order = await db.orders.find_one(
        {"order_number": order_number},
        {"_id": 0, "admin_notes": 0, "payment_id": 0, "user_id": 0, "customer_ip": 0, "user_agent": 0,
         "billing_address": 0, "attribution": 0}
    )
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    def _mask_email(e: str) -> str:
        if not e or "@" not in e:
            return ""
        local, _, domain = e.partition("@")
        return (local[:2] + "***@" + domain) if len(local) > 2 else "***@" + domain

    def _mask_phone(p: str) -> str:
        digits = "".join(c for c in str(p or "") if c.isdigit())
        return (digits[:3] + "****" + digits[-2:]) if len(digits) >= 6 else ""

    ship = order.get("shipping_address") or {}
    if ship:
        order["shipping_address"] = {
            "first_name": ship.get("first_name", ""),
            "last_name": ship.get("last_name", ""),
            "phone": _mask_phone(ship.get("phone", "")),
            "email": _mask_email(ship.get("email", "")),
            "address": (ship.get("address") or "")[:40] + ("..." if len(ship.get("address") or "") > 40 else ""),
            "city": ship.get("city", ""),
            "district": ship.get("district", ""),
        }
    return order


@router.get("/deleted")
async def list_deleted_orders(
    page: int = 1,
    limit: int = 50,
    search: str = "",
    current_user: dict = Depends(require_admin),
):
    """Silinen (arşivlenen) siparişler — orders_deleted koleksiyonundan, en yeni üstte."""
    q = {}
    if search:
        q["$or"] = [
            {"order_number": {"$regex": search, "$options": "i"}},
            {"shipping_address.phone": {"$regex": search, "$options": "i"}},
            {"shipping_address.email": {"$regex": search, "$options": "i"}},
        ]
    try:
        limit = max(1, min(int(limit), 200))
        page = max(1, int(page))
    except Exception:
        limit, page = 50, 1
    skip = (page - 1) * limit
    total = await db.orders_deleted.count_documents(q)
    items = await db.orders_deleted.find(q, {"_id": 0}).sort("deleted_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"orders": items, "total": total, "page": page, "limit": limit}


@router.get("/{order_id}")
async def get_order(
    order_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get single order"""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    # Check access - admin can see all, users can see only their own
    if current_user and not current_user.get("is_admin"):
        if order.get("user_id") != current_user.get("id"):
            raise HTTPException(status_code=403, detail="Bu siparişi görüntüleme yetkiniz yok")
    
    order["items"] = await _enrich_items_with_products(order.get("items") or [])
    return order


@router.get("/{order_id}/events")
async def get_order_events(
    order_id: str,
    current_user: dict = Depends(require_admin),
):
    """Sipariş işlem geçmişi (Log) — en yeni en üstte."""
    events = await db.order_events.find(
        {"order_id": order_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return {"events": events, "count": len(events)}


@router.post("")
async def create_order(
    order_data: dict,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Create new order"""
    # FAZ 6 — Kullanıcı IP'sini kayda al (X-Forwarded-For → gerçek IP)
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")

    # FAZ 6 — Blok kontrolü: kullanıcı veya IP bloklu mu?
    uid = (current_user.get("id") if current_user else None)
    block_query = []
    if uid:
        block_query.append({"user_id": uid})
    if client_ip:
        block_query.append({"ip": client_ip})
    if block_query:
        bl = await db.blocked_customers.find_one({"$or": block_query, "active": True}, {"_id": 0})
        if bl:
            logger.warning(f"Blocked order attempt: user={uid} ip={client_ip} reason={bl.get('reason')}")
            raise HTTPException(status_code=403, detail="Hesabınız sipariş veremez. Lütfen destek ile iletişime geçin.")

    order = {
        "id": generate_id(),
        "order_number": await next_order_number(),
        "user_id": current_user.get("id") if current_user else None,
        "items": order_data.get("items", []),
        "shipping_address": order_data.get("shipping_address", {}),
        "billing_address": order_data.get("billing_address") or order_data.get("shipping_address", {}),
        # Kurumsal fatura bilgileri (B2B müşteriler için)
        "billing_info": {
            "is_corporate": bool((order_data.get("billing_info") or {}).get("is_corporate", False)),
            "company_name": ((order_data.get("billing_info") or {}).get("company_name") or "").strip(),
            "tax_office": ((order_data.get("billing_info") or {}).get("tax_office") or "").strip(),
            "tax_number": ((order_data.get("billing_info") or {}).get("tax_number") or "").strip(),
            "e_invoice_user": bool((order_data.get("billing_info") or {}).get("e_invoice_user", False)),
        } if order_data.get("billing_info") else {"is_corporate": False},
        "subtotal": float(order_data.get("subtotal", 0)),
        "shipping_cost": float(order_data.get("shipping_cost", 0)),
        "discount": float(order_data.get("discount", 0)),
        "total": float(order_data.get("total", 0)),
        "payment_method": order_data.get("payment_method", "credit_card"),
        "payment_status": "pending",
        "status": "pending",
        "notes": order_data.get("notes", ""),
        "platform": order_data.get("platform", "facette"),
        # FAZ 4 — hediye seçenekleri
        "gift_note": (order_data.get("gift_note") or "")[:500],
        "gift_wrap": bool(order_data.get("gift_wrap", False)),
        "gift_wrap_price": float(order_data.get("gift_wrap_price", 0) or 0),
        "coupon_code": (order_data.get("coupon_code") or "").upper(),
        "applied_promotions": order_data.get("applied_promotions") or [],
        # FAZ 6 — müşteri izleri
        "customer_ip": client_ip,
        "user_agent": request.headers.get("user-agent", "")[:300],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    # Attribution snapshot (source of the sale)
    try:
        sid = order_data.get("attribution_session_id") or order_data.get("session_id")
        inline = order_data.get("attribution") if isinstance(order_data.get("attribution"), dict) else None
        order["attribution"] = await resolve_attribution_for_order(sid, inline)
    except Exception as att_err:
        logger.warning(f"Attribution resolve failed: {att_err}")
        order["attribution"] = {"channel": "direct", "source": "", "medium": "", "campaign": "", "session_id": ""}

    # Influencer linking — aff_id (çerez) önce, kupon fallback override
    try:
        from .influencers import resolve_influencer_for_order
        aff_id = (order.get("attribution") or {}).get("aff_id") or order_data.get("aff_id")
        link = await resolve_influencer_for_order(aff_id, order.get("coupon_code"))
        if link:
            order["influencer_id"] = link["influencer_id"]
            order["influencer_via"] = link["via"]
    except Exception as inf_err:
        logger.warning(f"Influencer link failed: {inf_err}")

    # Havale/EFT siparisleri: "Siparisiniz Alindi · Odeme Bekleniyor" durumunda baslar
    _pm0 = (order.get("payment_method") or "").lower()
    if _pm0 in ("bank_transfer", "havale", "eft", "havale_eft", "banka_havale"):
        order["status"] = "awaiting_payment"

    # Guvenlik: kapida odeme admin tarafindan KAPALIYSA, eski istemci veya dogrudan
    # API cagrisi ile gelen kapida odeme siparislerini sunucu tarafinda da reddet.
    if _pm0 in ("cash_on_delivery", "kapida"):
        _scfg = await db.settings.find_one({"id": "main"}, {"_id": 0, "payment_methods": 1}) or {}
        _cod_on = ((_scfg.get("payment_methods") or {}).get("cash_on_delivery")) is True
        if not _cod_on:
            raise HTTPException(status_code=400, detail="Kapıda ödeme şu anda kullanılamıyor. Lütfen başka bir ödeme yöntemi seçin.")

    # Madde 4 — SUNUCU-OTORITER GUVENLI KELEPCE (tek yonlu). Sunucu indirimi odeme yontemiyle
    # birlikte yeniden hesaplar; istemcinin gonderdigi indirim sunucununkini ASAMAZ. Mesru
    # siparis degismez (iki deger esit). Sismis/sahte indirim (orn. havale indirimini kapip
    # kartla odeme) kirpilir; karta yansiyan tutar INSERT'ten ONCE duzeltilir (cunku
    # /payment/card/pay siparisin kayitli total'ini ceker). Hata olsa bile siparis bozulmaz.
    try:
        from .coupons import evaluate_cart_promotions as _eval_promos
        _eng_items = [{
            "product_id": it.get("product_id"),
            "category_id": it.get("category_id"),
            "qty": it.get("quantity", it.get("qty", 1)),
            "price": it.get("price", 0),
        } for it in (order.get("items") or [])]
        _ev = await _eval_promos(
            cart_total=float(order.get("subtotal", 0) or 0),
            items=_eng_items,
            user_id=order.get("user_id"),
            email=(order.get("shipping_address") or {}).get("email", ""),
            entered_code=order.get("coupon_code", ""),
            payment_method=order.get("payment_method", ""),
        )
        _srv = round(float(_ev.get("total_discount", 0) or 0), 2)
        _cli = round(float(order.get("discount", 0) or 0), 2)
        if _cli - _srv > 0.01:  # istemci fazla indirim iddia etmis -> sunucu degerine kirp
            _delta = round(_cli - _srv, 2)
            order["discount"] = _srv
            order["total"] = round(float(order.get("total", 0) or 0) + _delta, 2)
            order["applied_promotions"] = _ev.get("applied") or []
            order["promo_clamped"] = {"client": _cli, "server": _srv, "delta": _delta,
                                      "payment_method": order.get("payment_method")}
            logger.warning(f"[PROMO KELEPCE] siparis={order['order_number']} istemci={_cli} "
                           f"sunucu={_srv} -> indirim {_srv}'e kirpildi, total +{_delta} "
                           f"(odeme={order.get('payment_method')})")
    except Exception as _clamp_err:
        logger.warning(f"Promo kelepce hatasi (siparis etkilenmedi): {_clamp_err}")

    await db.orders.insert_one(order)
    logger.info(f"Order created: {order['order_number']}")

    # Madde 4 — Promosyon kullanım kaydı (usage_limit / usage_limit_per_user'ın ÇALIŞMASI için).
    # FIYATA DOKUNMAZ; sadece coupon_redemptions'a yazar. Hata olsa bile sipariş bozulmaz.
    try:
        _email = (order.get("shipping_address") or {}).get("email", "")
        _redeem_ids = []
        _applied = order.get("applied_promotions") or []
        if _applied:
            for _a in _applied:
                _cid = _a.get("coupon_id")
                if _cid:
                    _redeem_ids.append((_cid, float(_a.get("discount", 0) or 0)))
        elif order.get("coupon_code"):
            _c = await db.coupons.find_one({"code": order["coupon_code"]}, {"_id": 0, "id": 1})
            if _c:
                _redeem_ids.append((_c["id"], float(order.get("discount", 0) or 0)))
        for _cid, _disc in _redeem_ids:
            _exists = await db.coupon_redemptions.find_one({"coupon_id": _cid, "order_id": order["id"]})
            if not _exists:
                await db.coupon_redemptions.insert_one({
                    "coupon_id": _cid,
                    "order_id": order["id"],
                    "user_id": order.get("user_id"),
                    "customer_email": _email,
                    "discount": _disc,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
    except Exception as _redeem_err:
        logger.warning(f"Promosyon kullanım kaydı başarısız (sipariş etkilenmedi): {_redeem_err}")

    # NOT: Sunucu-otoriter promosyon yeniden-hesabi artik INSERT'ten ONCE "guvenli kelepce"
    # blogunda yapiliyor (yukari bkz). Bu yuzden eski post-insert [PROMO SHADOW] gozlem blogu
    # kaldirildi — motor siparis basina yalnizca bir kez calisir.


    # FAZ — Sipariş onayı bildirimi (SMS + Email + WhatsApp) — fire-and-forget
    import asyncio as _asyncio
    async def _notify_order_created():
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from notification_service import send_notification

            ship = order.get("shipping_address") or {}
            full_name = (
                f"{ship.get('first_name','')} {ship.get('last_name','')}".strip()
                or ship.get("full_name") or ship.get("name") or "Müşterimiz"
            )
            # Sipariş kalemlerini email için HTML satırlarına çevir
            items = order.get("items") or []
            items_rows = ""
            for it in items[:20]:
                img = it.get("image") or ""
                name = it.get("name") or it.get("product_name") or "Ürün"
                qty = it.get("quantity", 1)
                price = it.get("price", 0)
                size = it.get("size", "")
                color = it.get("color", "")
                meta = " · ".join([f"Beden: {size}" if size else "", f"Renk: {color}" if color else "", f"Adet: {qty}"]).strip(" · ")
                items_rows += (
                    f'<tr><td style="padding:12px 0;border-bottom:1px solid #f0f0f0;width:80px;">'
                    f'<img src="{img}" alt="" style="width:64px;height:80px;object-fit:cover;background:#fafafa;"/></td>'
                    f'<td style="padding:12px 12px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#111;">{name}'
                    f'<div style="color:#999;font-size:11px;margin-top:4px;">{meta}</div></td>'
                    f'<td style="padding:12px 0;border-bottom:1px solid #f0f0f0;text-align:right;font-size:13px;color:#111;white-space:nowrap;">{(price*qty):.2f} TL</td></tr>'
                )
            items_html = (
                '<div style="padding:0 24px 16px;"><table cellpadding="0" cellspacing="0" border="0" style="width:100%;">'
                f'{items_rows}</table></div>'
            ) if items_rows else ""

            base_url = os.environ.get("FRONTEND_PUBLIC_URL") or os.environ.get("REACT_APP_BACKEND_URL") or ""
            order_link = f"{base_url}/order-success/{order['order_number']}" if base_url else "#"
            order_date = order["created_at"][:10]
            _hv_bank = {}
            if order.get("status") == "awaiting_payment":
                _pay = await db.settings.find_one({"id": "payment"}, {"_id": 0}) or {}
                _banks = _pay.get("bank_accounts") or []
                _hv_bank = next((b for b in _banks if b.get("is_default")), None) or (_banks[0] if _banks else {})

            variables = await _order_notify_vars(order)
            if order.get("status") == "awaiting_payment":
                from order_statuses import get_status_config
                _cfg = await get_status_config(db)
                _nz = (_cfg.get("notify") or {}).get("awaiting_payment") or {}
                _channels = [c for c in ("sms", "email") if _nz.get(c)]
                # Havale/EFT siparişinde "Siparişiniz Alındı · Ödeme Bekleniyor"
                # bildirimi HER ZAMAN gitmeli — config boş bırakılmış olsa bile
                # müşteri en azından e-posta (varsa SMS) ile bilgilendirilir.
                if not _channels:
                    _channels = ["email"]
                    if (ship.get("phone") or order.get("phone")):
                        _channels.append("sms")
                await send_notification(
                    db, "order_awaiting_payment",
                    to_phone=ship.get("phone") or order.get("phone"),
                    to_email=ship.get("email") or order.get("email"),
                    variables=variables,
                    channels=_channels,
                )
            else:
                await send_notification(
                    db, "order_confirmed",
                    to_phone=ship.get("phone") or order.get("phone"),
                    to_email=ship.get("email") or order.get("email"),
                    variables=variables,
                )
        except Exception as e:
            logger.warning(f"order_confirmed notification dispatch failed: {e}")

    _asyncio.create_task(_notify_order_created())

    # FAZ 1 - C1: otomatik stok düşümü
    try:
        moves = await _stock_delta_for_order(order, -1)
        if moves:
            await db.stock_movements.insert_one({
                "id": str(uuid.uuid4()),
                "type": "order_created",
                "order_id": order["id"],
                "order_number": order["order_number"],
                "items": moves,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as stock_err:
        logger.error(f"Stock decrement on order create failed: {stock_err}")

    return {
        "order_id": order["id"],
        "order_number": order["order_number"],
        "message": "Sipariş oluşturuldu"
    }

@router.put("/{order_id}")
async def update_order(
    order_id: str,
    order_data: dict,
    current_user: dict = Depends(require_admin)
):
    """Update order (admin only)"""
    existing = await db.orders.find_one({"id": order_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    order_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.orders.update_one({"id": order_id}, {"$set": order_data})
    
    return {"message": "Sipariş güncellendi"}

@router.put("/{order_id}/status")
async def update_order_status(
    order_id: str,
    status: str = Query(...),
    current_user: dict = Depends(require_admin)
):
    """Update order status"""
    from order_statuses import get_status_config, valid_keys
    _cfg0 = await get_status_config(db)
    valid_statuses = valid_keys(_cfg0)
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Geçersiz durum. Geçerli değerler: {sorted(valid_statuses)}")
    
    _now = datetime.now(timezone.utc).isoformat()
    _set = {"status": status, "updated_at": _now}
    if status == "return_approved":
        _set["return_approved_at"] = _now
    if status in ("refunded", "partial_refunded"):
        _set["refund_paid_at"] = _now

    # "Sipariş Onaylandı" (confirmed) → havale/EFT siparişinde ödeme bildirimini de
    # OTOMATİK onayla: payment_status=paid. Sipariş içine girmeden listeden onaylayınca
    # içerideki ödeme onayı tetiklenir, fatura/kargo kilidi açılır. Kapıda ödeme HARİÇ
    # (teslimde ödenir), kredi kartı zaten 'paid' olduğundan etkilenmez.
    _confirm_paid = False
    _od_pre = None
    if status == "confirmed":
        _od_pre = await db.orders.find_one(
            {"id": order_id},
            {"_id": 0, "payment_method": 1, "payment_status": 1, "order_number": 1},
        )
        if _od_pre:
            _pm = (_od_pre.get("payment_method") or "").lower()
            if _pm in _HAVALE_PMS and _od_pre.get("payment_status") != "paid":
                _set["payment_status"] = "paid"
                _set["paid_at"] = _now
                _set["paid_by"] = current_user.get("email", "")
                _set["payment_approved_via"] = "status_confirm"
                _confirm_paid = True

    result = await db.orders.update_one(
        {"id": order_id},
        {"$set": _set}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    await _log_order_event(order_id, "status", f"Durum güncellendi: {status}", current_user, {"status": status})
    if _confirm_paid:
        await _log_order_event(
            order_id, "payment",
            "Ödeme onaylandı (sipariş onayı ile otomatik · havale/EFT)",
            current_user, {"payment_status": "paid", "via": "status_confirm"},
            order_number=(_od_pre or {}).get("order_number", ""),
        )

    # ---- FATURA İPTALİ (Doğan e-Arşiv) ----------------------------------------
    # Sipariş iptal edildiyse ve Doğan'dan e-Arşiv fatura kesilmişse, faturayı da
    # Doğan üzerinden iptal etmeyi dener. Best-effort: durum güncellemesini ASLA
    # bloklamaz/bozmaz. e-Fatura iptali farklı bir süreç (alıcı onayı / iptal
    # faturası) olduğundan otomatik iptal edilmez, manuel olarak işaretlenir.
    if status == "cancelled":
        try:
            _od = await db.orders.find_one({"id": order_id}, {"_id": 0})
            if (_od and _od.get("invoice_issued") and (_od.get("invoice_provider") == "dogan")
                    and not _od.get("invoice_cancelled")):
                _itype = str(_od.get("invoice_type") or "").lower()
                if _itype in ("e-arsiv", "earsiv", "e-arşiv"):
                    _ds = await db.settings.find_one({"id": "dogan_edonusum"}, {"_id": 0}) or {}
                    if _ds.get("enabled") and _ds.get("username"):
                        from dogan_client import DoganClient as _DC
                        from fastapi.concurrency import run_in_threadpool as _rtp
                        _cli = _DC(username=_ds["username"], password=_ds["password"],
                                   is_test=_ds.get("is_test", True))
                        _cancel = await _rtp(
                            _cli.cancel_earsiv_invoice,
                            invoice_uuid=_od.get("invoice_uuid", "") or "",
                            invoice_id=_od.get("invoice_dogan_id", "") or "",
                            reason=f"Sipariş iptal edildi ({_od.get('order_number') or order_id})",
                        )
                        try:
                            await _rtp(_cli.logout)
                        except Exception:
                            pass
                        await db.orders.update_one({"id": order_id}, {"$set": {
                            "invoice_cancelled": bool(_cancel.get("success")),
                            "invoice_cancel_result": _cancel,
                            "invoice_cancel_attempted_at": _now,
                        }})
                        await _log_order_event(
                            order_id, "invoice",
                            ("Doğan e-Arşiv fatura iptal edildi"
                             if _cancel.get("success")
                             else f"Doğan fatura iptali başarısız: {_cancel.get('message') or _cancel.get('error') or ''}"),
                            current_user, {"cancel": _cancel})
                else:
                    await db.orders.update_one({"id": order_id}, {"$set": {
                        "invoice_cancel_needs_manual": True,
                        "invoice_cancel_attempted_at": _now,
                    }})
                    await _log_order_event(
                        order_id, "invoice",
                        "e-Fatura iptali manuel yapılmalı (Doğan portalı / iptal faturası).",
                        current_user, {})
        except Exception as _ic:
            logger.error(f"[dogan invoice cancel {order_id}] {_ic}")

    # Bildirim tetikleme: status → event eşlemesi
    # NOT: Provider'lara gidiş yavaş olabilir — fire-and-forget task ile UI yanıtını
    # bloklamadan arka planda tetikliyoruz.
    import asyncio as _asyncio
    async def _dispatch_notif():
        try:
            order_doc = await db.orders.find_one({"id": order_id}, {"_id": 0})
            if not order_doc:
                return
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from notification_service import send_notification
            from order_statuses import event_for_cfg, get_status_config, customer_label_for_cfg
            _cfg = await get_status_config(db)
            ev = event_for_cfg(status, _cfg)
            if not ev:
                return
            _nz = (_cfg.get("notify") or {}).get(status) or {}
            _channels = [c for c in ("sms", "email") if _nz.get(c)]
            if not _channels:
                return  # bu durum icin bildirim kapali (Ayarlar > Siparis Durumlari)
            addr = order_doc.get("shipping_address") or {}
            _bank = {}
            if status == "awaiting_payment":
                _pay = await db.settings.find_one({"id": "payment"}, {"_id": 0}) or {}
                _banks = _pay.get("bank_accounts") or []
                _bank = next((b for b in _banks if b.get("is_default")), None) or (_banks[0] if _banks else {})
            _base = os.environ.get("FRONTEND_PUBLIC_URL") or os.environ.get("REACT_APP_BACKEND_URL") or ""
            # Kargo takip linki — gerçek deep-link önceliği (cargo_tracking_link),
            # yoksa eski alanlara düş. {tracking_link} ve {tracking_url} ikisi de bunu alır.
            _track_link = (order_doc.get("cargo_tracking_link")
                           or order_doc.get("cargo_tracking_url")
                           or order_doc.get("tracking_url") or "")
            variables = await _order_notify_vars(order_doc, status_label=customer_label_for_cfg(status, _cfg))
            await send_notification(
                db, ev,
                to_phone=addr.get("phone") or order_doc.get("phone"),
                to_email=addr.get("email") or order_doc.get("email"),
                variables=variables,
                channels=_channels,
            )
        except Exception as _notif_err:
            logger.warning(f"notification dispatch failed for order {order_id}: {_notif_err}")

    _asyncio.create_task(_dispatch_notif())

    # ---- CAPI Server-Side Tracking Hooks ----
    # Status değişimleri reklam platformlarına da bildirilir.
    async def _dispatch_capi():
        try:
            order_doc = await db.orders.find_one({"id": order_id}, {"_id": 0})
            if not order_doc:
                return
            # Map status → CAPI event_name
            capi_event = None
            value_multiplier = 1.0
            if status == "confirmed" and order_doc.get("payment_status") == "paid":
                capi_event = "purchase"
            elif status == "cancelled" and order_doc.get("payment_status") == "paid":
                capi_event = "refund"
                value_multiplier = -1.0
            if not capi_event:
                return
            from services.capi.orchestrator import dispatch_event
            addr = order_doc.get("shipping_address") or {}
            user_data_kwargs = {
                "email": addr.get("email") or order_doc.get("email"),
                "phone": addr.get("phone") or order_doc.get("phone"),
                "first_name": addr.get("first_name") or (addr.get("full_name") or "").split(" ")[0],
                "last_name": addr.get("last_name") or " ".join((addr.get("full_name") or "").split(" ")[1:]),
                "city": addr.get("city"),
                "state": addr.get("district") or addr.get("state"),
                "country": addr.get("country") or "TR",
                "zipcode": addr.get("zipcode") or addr.get("postal_code"),
                "street": addr.get("address") or addr.get("address_line1"),
                "date_of_birth": (order_doc.get("customer") or {}).get("date_of_birth"),
                "gender": (order_doc.get("customer") or {}).get("gender"),
                "external_id": order_doc.get("customer_id") or order_doc.get("user_id"),
            }
            from services.capi.hash_utils import build_user_data
            user_data = build_user_data(**user_data_kwargs)
            items_payload = []
            for it in (order_doc.get("items") or []):
                items_payload.append({
                    "item_id": str(it.get("product_id") or it.get("sku") or ""),
                    "item_name": it.get("name") or "",
                    "item_brand": it.get("brand") or "",
                    "item_variant": f"{it.get('size','')} {it.get('color','')}".strip(),
                    "price": float(it.get("unit_price") or it.get("price") or 0),
                    "quantity": int(it.get("quantity") or 1),
                })
            await dispatch_event(
                db,
                event_name=capi_event,
                event_id=f"{order_id}-{capi_event}",   # dedup by order
                user_data=user_data,
                event_payload={
                    "currency": order_doc.get("currency") or "TRY",
                    "value": float(order_doc.get("total") or 0) * value_multiplier,
                    "items": items_payload,
                    "order_id": order_doc.get("order_number") or order_id,
                    "coupon": order_doc.get("coupon_code"),
                },
                event_source_url="https://www.facette.com.tr",
            )
        except Exception as _capi_err:
            logger.warning(f"CAPI dispatch failed for order {order_id}: {_capi_err}")

    _asyncio.create_task(_dispatch_capi())

    # FAZ 1 - C1: Status değişikliğinde stok düzenlemesi
    try:
        order_doc = await db.orders.find_one({"id": order_id}, {"_id": 0})
        prev_status = None  # we don't have a before-value; rely on status flip idempotence
        if status == "cancelled":
            # Only increment once – guard with stock_movements presence
            already = await db.stock_movements.find_one({"order_id": order_id, "type": "order_cancelled"}, {"_id": 1})
            if not already:
                moves = await _stock_delta_for_order(order_doc, +1)
                if moves:
                    await db.stock_movements.insert_one({
                        "id": str(uuid.uuid4()),
                        "type": "order_cancelled",
                        "order_id": order_id,
                        "order_number": order_doc.get("order_number", ""),
                        "items": moves,
                        "created_by": current_user.get("email", ""),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
    except Exception as stock_err:
        logger.error(f"Stock restore on cancel failed: {stock_err}")

    return {"message": f"Sipariş durumu '{status}' olarak güncellendi"}

@router.put("/{order_id}/mark-paid")
async def mark_order_paid(
    order_id: str,
    current_user: dict = Depends(require_admin)
):
    """Havale/EFT ödemesi manuel onaylama.
    payment_status='paid' yapar ve CAPI'ye offline 'purchase' event'i gönderir.
    """
    order_doc = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order_doc:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    if order_doc.get("payment_status") == "paid":
        return {"message": "Sipariş zaten ödenmiş olarak işaretli.",
                "order_id": order_id, "already_paid": True}

    now_iso = datetime.now(timezone.utc).isoformat()
    _set = {
        "payment_status": "paid",
        "paid_at": now_iso,
        "paid_by": current_user.get("email", ""),
        "updated_at": now_iso,
    }
    _flip_confirmed = order_doc.get("status") in ("awaiting_payment", "payment_notified", "pending")
    if _flip_confirmed:
        _set["status"] = "confirmed"
    await db.orders.update_one({"id": order_id}, {"$set": _set})

    await _log_order_event(order_id, "payment", "Ödeme onaylandı (manuel/havale)", current_user,
                           {"payment_status": "paid", "status_flipped": _flip_confirmed},
                           order_number=order_doc.get("order_number", ""))

    # Havale onayinda "Onaylandi" bildirimi (Siparis Durumlari ayarina gore)
    if _flip_confirmed:
        import asyncio as _aio2
        async def _notify_confirmed():
            try:
                import sys, os
                sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
                from notification_service import send_notification
                from order_statuses import get_status_config, customer_label_for
                cfg = await get_status_config(db)
                nz = (cfg.get("notify") or {}).get("confirmed") or {}
                ch = [c for c in ("sms", "email") if nz.get(c)]
                if not ch:
                    return
                addr = order_doc.get("shipping_address") or {}
                _base = os.environ.get("FRONTEND_PUBLIC_URL") or os.environ.get("REACT_APP_BACKEND_URL") or ""
                await send_notification(
                    db, "order_confirmed",
                    to_phone=addr.get("phone") or order_doc.get("phone"),
                    to_email=addr.get("email") or order_doc.get("email"),
                    variables=await _order_notify_vars(order_doc, status_label=customer_label_for("confirmed")),
                    channels=ch,
                )
            except Exception as e:
                logger.warning(f"confirmed notif failed: {e}")
        _aio2.create_task(_notify_confirmed())

    # CAPI offline conversion (purchase event) — fire-and-forget
    import asyncio as _asyncio
    async def _capi_offline_purchase():
        try:
            from services.capi.orchestrator import dispatch_event
            from services.capi.hash_utils import build_user_data
            addr = order_doc.get("shipping_address") or {}
            user_data = build_user_data(
                email=addr.get("email") or order_doc.get("email"),
                phone=addr.get("phone") or order_doc.get("phone"),
                first_name=addr.get("first_name") or (addr.get("full_name") or "").split(" ")[0],
                last_name=addr.get("last_name") or " ".join((addr.get("full_name") or "").split(" ")[1:]),
                city=addr.get("city"),
                state=addr.get("district") or addr.get("state"),
                country=addr.get("country") or "TR",
                zipcode=addr.get("zipcode") or addr.get("postal_code"),
                street=addr.get("address") or addr.get("address_line1"),
                date_of_birth=(order_doc.get("customer") or {}).get("date_of_birth"),
                gender=(order_doc.get("customer") or {}).get("gender"),
                external_id=order_doc.get("customer_id") or order_doc.get("user_id"),
            )
            items_payload = []
            for it in (order_doc.get("items") or []):
                items_payload.append({
                    "item_id": str(it.get("product_id") or it.get("sku") or ""),
                    "item_name": it.get("name") or "",
                    "item_variant": f"{it.get('size','')} {it.get('color','')}".strip(),
                    "price": float(it.get("unit_price") or it.get("price") or 0),
                    "quantity": int(it.get("quantity") or 1),
                })
            await dispatch_event(
                db,
                event_name="purchase",
                event_id=f"{order_id}-offline-purchase",
                user_data=user_data,
                event_payload={
                    "currency": order_doc.get("currency") or "TRY",
                    "value": float(order_doc.get("total") or 0),
                    "items": items_payload,
                    "order_id": order_doc.get("order_number") or order_id,
                    "coupon": order_doc.get("coupon_code"),
                },
                event_source_url="https://www.facette.com.tr",
            )
        except Exception as e:
            logger.warning(f"CAPI offline-purchase failed: {e}")

    _asyncio.create_task(_capi_offline_purchase())

    return {"message": "Ödeme onaylandı, CAPI offline conversion tetiklendi.",
            "order_id": order_id, "payment_status": "paid"}


@router.delete("/{order_id}")
async def delete_order(
    order_id: str,
    current_user: dict = Depends(require_admin)
):
    """Siparişi sil — fiziksel silmeden ÖNCE orders_deleted arşivine taşı.
    Böylece 'Silinen Siparişler' sayfasından görülüp geri alınabilir; ana orders
    sorguları/raporları/dashboard hiç etkilenmez."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    order["deleted_at"] = datetime.now(timezone.utc).isoformat()
    order["deleted_by"] = current_user.get("email", "")
    try:
        await db.orders_deleted.replace_one({"id": order_id}, order, upsert=True)
    except Exception as _e:
        logger.warning(f"archive deleted order failed {order_id}: {_e}")
    await db.orders.delete_one({"id": order_id})
    await _log_order_event(order_id, "delete", "Sipariş silindi (arşive taşındı)", current_user, {},
                           order_number=order.get("order_number", ""))
    return {"message": "Sipariş silindi", "archived": True}


@router.post("/{order_id}/restore")
async def restore_deleted_order(
    order_id: str,
    current_user: dict = Depends(require_admin)
):
    """Arşivlenen (silinen) siparişi orders'a geri taşır."""
    arch = await db.orders_deleted.find_one({"id": order_id}, {"_id": 0})
    if not arch:
        raise HTTPException(status_code=404, detail="Silinen sipariş bulunamadı")
    arch.pop("deleted_at", None)
    arch.pop("deleted_by", None)
    now_iso = datetime.now(timezone.utc).isoformat()
    arch["updated_at"] = now_iso
    arch["restored_at"] = now_iso
    arch["restored_by"] = current_user.get("email", "")
    await db.orders.replace_one({"id": order_id}, arch, upsert=True)
    await db.orders_deleted.delete_one({"id": order_id})
    await _log_order_event(order_id, "status", "Sipariş geri alındı (arşivden)", current_user, {},
                           order_number=arch.get("order_number", ""))
    return {"message": "Sipariş geri alındı", "restored": True}


# ==================== FAZ 1: STOCK AUTO-FLOW + AUTO-CANCEL + NOTES ====================

async def _stock_delta_for_order(order: dict, delta: int) -> list:
    """Apply stock delta (+1 or -1 per unit) for every order item. Returns movement list."""
    movements = []
    items = order.get("items") or order.get("lines") or []
    for it in items:
        barcode = it.get("barcode") or it.get("sku") or ""
        qty = int(it.get("quantity", 1) or 1)
        if not barcode:
            continue
        # Try variant match first
        prod = await db.products.find_one({"variants.barcode": barcode}, {"_id": 0, "id": 1, "variants": 1})
        if prod:
            for v in (prod.get("variants") or []):
                if v.get("barcode") == barcode:
                    v["stock"] = max(0, int(v.get("stock", 0) or 0) + (delta * qty))
                    break
            new_total = sum(int(v.get("stock", 0) or 0) for v in prod.get("variants", []))
            await db.products.update_one(
                {"id": prod["id"]},
                {"$set": {"variants": prod["variants"], "stock": new_total, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            movements.append({"barcode": barcode, "delta": delta * qty, "product_id": prod["id"]})
        else:
            # Fallback product-level barcode
            p2 = await db.products.find_one({"barcode": barcode}, {"_id": 0, "id": 1})
            if p2:
                await db.products.update_one(
                    {"id": p2["id"]},
                    {"$inc": {"stock": delta * qty}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
                )
                movements.append({"barcode": barcode, "delta": delta * qty, "product_id": p2["id"]})
    return movements


@router.post("/{order_id}/apply-stock")
async def apply_stock_for_order(
    order_id: str,
    action: str = Query(..., description="'decrement' (new order) or 'increment' (cancel/refund)"),
    current_user: dict = Depends(require_admin)
):
    """Manually trigger stock adjustment for an order (use for reconciliation)."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    delta = -1 if action == "decrement" else 1
    moves = await _stock_delta_for_order(order, delta)
    await db.stock_movements.insert_one({
        "id": str(uuid.uuid4()),
        "type": f"manual_{action}",
        "order_id": order_id,
        "order_number": order.get("order_number", ""),
        "items": moves,
        "created_by": current_user.get("email", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"success": True, "items_affected": len(moves)}


@router.post("/reconcile-stock")
async def reconcile_stock_backfill(
    platform: str = Query("trendyol"),
    start_date: str = Query(...),
    action: str = Query("decrement"),
    skip_status: str = Query("cancelled,returned,refunded"),
    current_user: dict = Depends(require_admin)
):
    """İdempotent stok mutabakatı: platform + start_date sonrası siparişlerden HENÜZ
    stok-düşümü yapılmamış olanlara delta uygular. Daha önce düşüm hareketi olan siparişi
    atlar (manual_decrement / order_imported / backfill_decrement). Tekrar çalıştırılabilir.
    Ticimax stok senkronu ile ALAKASI YOKTUR — sadece sipariş bazlı stok düşer/ekler."""
    skips = set(s.strip() for s in (skip_status or "").split(",") if s.strip())
    delta = -1 if action == "decrement" else 1
    guard_types = ["manual_decrement", "order_imported", "backfill_decrement"]
    q = {"platform": platform, "created_at": {"$gte": start_date}}
    total = 0
    applied = 0
    skipped_status = 0
    skipped_done = 0
    zero_affected = []
    cursor = db.orders.find(q, {"_id": 0, "id": 1, "order_number": 1, "status": 1, "items": 1})
    async for o in cursor:
        total += 1
        if (o.get("status") or "") in skips:
            skipped_status += 1
            continue
        oid = o.get("id")
        already = await db.stock_movements.find_one(
            {"order_id": oid, "type": {"$in": guard_types}}, {"_id": 1}
        )
        if already:
            skipped_done += 1
            continue
        moves = await _stock_delta_for_order(o, delta)
        await db.stock_movements.insert_one({
            "id": str(uuid.uuid4()),
            "type": "backfill_decrement" if delta < 0 else "backfill_increment",
            "order_id": oid,
            "order_number": o.get("order_number", ""),
            "items": moves,
            "created_by": current_user.get("email", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        if moves:
            applied += 1
        else:
            zero_affected.append(o.get("order_number", ""))
    return {
        "success": True,
        "total_scanned": total,
        "applied": applied,
        "skipped_status": skipped_status,
        "skipped_already_done": skipped_done,
        "zero_affected_count": len(zero_affected),
        "zero_affected": zero_affected[:50],
    }


@router.post("/auto-cancel-expired")
async def auto_cancel_expired_orders(
    hours: int = Query(48, ge=1),
    current_user: dict = Depends(require_admin)
):
    """Cancel orders that have been unpaid for more than N hours and restock."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    # Only cancel pending/unpaid orders
    query = {
        "payment_status": "pending",
        "status": {"$in": ["pending", "confirmed"]},
        "created_at": {"$lt": cutoff},
    }
    cancelled = 0
    async for order in db.orders.find(query, {"_id": 0}):
        moves = await _stock_delta_for_order(order, +1)
        await db.orders.update_one(
            {"id": order["id"]},
            {"$set": {
                "status": "cancelled",
                "payment_status": "expired",
                "cancel_reason": f"Ödeme {hours} saat içinde tamamlanmadı",
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        await db.stock_movements.insert_one({
            "id": str(uuid.uuid4()),
            "type": "auto_cancel_expired",
            "order_id": order["id"],
            "order_number": order.get("order_number", ""),
            "items": moves,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        cancelled += 1
    return {"success": True, "cancelled": cancelled, "hours": hours}


@router.post("/{order_id}/note")
async def add_order_note(
    order_id: str,
    payload: dict,
    current_user: dict = Depends(require_admin)
):
    """Add/update admin note on order (e.g. havale takip)."""
    note = (payload or {}).get("note", "").strip()
    existing = await db.orders.find_one({"id": order_id}, {"_id": 0, "id": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    notes_list = (await db.orders.find_one({"id": order_id}, {"_id": 0, "admin_notes": 1})).get("admin_notes") or []
    notes_list.append({
        "id": str(uuid.uuid4()),
        "text": note,
        "by": current_user.get("email", ""),
        "at": datetime.now(timezone.utc).isoformat(),
    })
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"admin_notes": notes_list, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    await _log_order_event(order_id, "note", "Sipariş notu eklendi", current_user, {"note": note[:200]})
    return {"success": True, "notes": notes_list}


# =============================================================================
# FAZ 5 — Kargo durum güncellemeleri (ship / undeliver / deliver)
# =============================================================================
VALID_CARGO_COMPANIES = {
    "MNG", "DHL", "Yurtici", "Aras", "PTT", "UPS", "HepsiJet", "Trendyol", "Other"
}


@router.post("/{order_id}/ship")
async def ship_order(
    order_id: str,
    cargo_company: str = Query(..., description="Kargo firması kodu"),
    tracking_number: str = Query(..., min_length=3, description="Kargo takip numarası"),
    current_user: dict = Depends(require_admin)
):
    """Siparişi kargoya ver: status=shipped + cargo_company + cargo_tracking_number.
    Bildirim hook'u (order_shipped) otomatik tetiklenir.
    """
    if cargo_company not in VALID_CARGO_COMPANIES:
        raise HTTPException(status_code=400, detail=f"Geçersiz kargo firması. Geçerli: {sorted(VALID_CARGO_COMPANIES)}")

    existing = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "status": "shipped",
            "cargo_company": cargo_company,
            "cargo_tracking_number": tracking_number.strip(),
            "shipped_at": now_iso,
            "updated_at": now_iso,
        }},
    )

    await _log_order_event(order_id, "cargo", f"Kargoya verildi: {cargo_company} ({tracking_number.strip()})", current_user,
                           {"cargo_company": cargo_company, "tracking_number": tracking_number.strip()},
                           order_number=existing.get("order_number", ""))

    # Bildirim — fire-and-forget
    import asyncio as _asyncio
    async def _notify_ship():
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from notification_service import send_notification
            addr = existing.get("shipping_address") or {}
            await send_notification(
                db, "order_shipped",
                to_phone=addr.get("phone") or existing.get("phone"),
                to_email=addr.get("email") or existing.get("email"),
                variables=await _order_notify_vars(existing, tracking_number=tracking_number.strip(), cargo_company=cargo_company, cargo_provider=cargo_company),
            )
        except Exception as _e:
            logger.warning(f"order_shipped notification failed: {_e}")
    _asyncio.create_task(_notify_ship())

    return {
        "success": True,
        "message": f"Sipariş {cargo_company} kargosuna verildi ({tracking_number})",
        "tracking_number": tracking_number,
    }


@router.post("/{order_id}/undeliver")
async def mark_order_undelivered(
    order_id: str,
    reason: str = Query("Kargo teslim edilemedi", description="Teslim edilememe nedeni"),
    branch_info: str = Query("", description="Şube bilgisi / nerede bekliyor"),
    current_user: dict = Depends(require_admin)
):
    """Kargo teslim edilemedi (şubede bekliyor) durumunu işaretler ve müşteriye bildirim atar."""
    existing = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "status": "undelivered",
            "undelivered_reason": reason,
            "undelivered_branch": branch_info,
            "undelivered_at": now_iso,
            "updated_at": now_iso,
        }},
    )

    import asyncio as _asyncio
    async def _notify_undeliver():
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from notification_service import send_notification
            addr = existing.get("shipping_address") or {}
            await send_notification(
                db, "order_undelivered",
                to_phone=addr.get("phone") or existing.get("phone"),
                to_email=addr.get("email") or existing.get("email"),
                variables=await _order_notify_vars(existing, reason=reason, branch_info=branch_info),
            )
        except Exception as _e:
            logger.warning(f"order_undelivered notification failed: {_e}")
    _asyncio.create_task(_notify_undeliver())

    return {"success": True, "message": "Teslim edilemedi olarak işaretlendi"}


@router.post("/{order_id}/mark-invoiced")
async def mark_order_invoiced(
    order_id: str,
    payload: dict,
    current_user: dict = Depends(require_admin)
):
    """Mark order as invoiced – locks edits, flips status to 'confirmed' if pending."""
    invoice_number = (payload or {}).get("invoice_number", "")
    existing = await db.orders.find_one({"id": order_id}, {"_id": 0, "status": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    update = {
        "invoice_issued": True,
        "invoice_number": invoice_number,
        "invoice_issued_at": datetime.now(timezone.utc).isoformat(),
        "invoice_issued_by": current_user.get("email", ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing.get("status") == "pending":
        update["status"] = "confirmed"
    await db.orders.update_one({"id": order_id}, {"$set": update})
    await _log_order_event(order_id, "invoice", f"Fatura işlendi: {invoice_number}".strip(), current_user, {"invoice_number": invoice_number})
    return {"success": True, "invoice_issued": True}



# ---------------------------------------------------------------------------
# E-Fatura oluşturma — aktif e-fatura entegratörünü kullanarak fatura keser.
# Aktif provider `providers_config` kolleksiyonundan okunur. Canlıda her
# provider için ayrı SDK çağrısı olacak; şu an mock başarı döner ama doğru
# provider adı + üretilmiş invoice_number ile kayıt altına alınır.
#
# FRONTEND: Orders.jsx handleGenerateInvoice + handleBulkGenerateInvoice.
# ---------------------------------------------------------------------------
@router.post("/{order_id}/reset-invoice")
async def reset_invoice_for_order(order_id: str, current_user: dict = Depends(require_admin)):
    """Sipariş fatura kaydını panelde sıfırlar (yeniden kesilebilsin diye).
    Doğan'daki gerçek faturayı İPTAL ETMEZ; yalnız paneldeki fatura işaretini/numarasını temizler."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    prev = order.get("invoice_number") or ""
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"invoice_issued": False},
         "$unset": {
             "invoice_number": "", "invoice_uuid": "", "invoice_type": "",
             "invoice_provider": "", "invoice_provider_response": "",
             "invoice_intl_txn_id": "", "invoice_dogan_id": "", "invoice_pdf_url": "",
             "invoice_issued_at": "", "invoice_issued_by": "",
         }},
    )
    return {"success": True, "message": f"Fatura kaydı sıfırlandı ({prev or 'kayıt'} silindi), yeniden kesebilirsiniz"}


# Havale/EFT siparişlerinde fatura, ödeme (havale) onaylanmadan KESİLMEZ.
_HAVALE_PMS = ("bank_transfer", "havale", "eft", "havale_eft", "banka_havale", "havale/eft")
_SETTLED_PAY = ("paid", "completed", "success", "succeeded", "captured")


def _havale_invoice_block(order: dict):
    """Havale/EFT siparişi ödemesi onaylanmamışsa fatura engelinin sebebini döndürür;
    onaylıysa (payment_status ödenmiş) None döner."""
    pm = (order.get("payment_method") or "").lower()
    pstat = (order.get("payment_status") or "").lower()
    if pm in _HAVALE_PMS and pstat not in _SETTLED_PAY:
        return ("Havale onaylanmadığı için bu siparişe fatura kesilemedi. "
                "Önce siparişin ödemesini 'Ödendi' olarak işaretleyin (havale onayı), "
                "sonra faturayı kesin.")
    return None


@router.post("/{order_id}/create-invoice")
async def create_invoice_for_order(
    order_id: str,
    invoice_type: str = "auto",
    current_user: dict = Depends(require_admin),
):
    """
    Seçili sipariş için e-Arşiv / e-Fatura keser.

    invoice_type:
      - "auto" (default): Müşterinin VKN/TCKN'sini Doğan'da CheckUser ile sorgular,
        e-Fatura mükellefi ise e-Fatura, değilse veya VKN/TC boşsa e-Arşiv keser.
      - "e-arsiv": Zorla e-Arşiv (bireysel TCKN dolu/boş hepsi)
      - "e-fatura": Zorla e-Fatura (10 haneli VKN şart)
    """
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    if order.get("invoice_issued"):
        return {"success": True, "message": "Fatura zaten kesilmiş",
                "invoice_number": order.get("invoice_number", "")}

    # Havale/EFT siparişi onaylanmadan fatura KESİLMEZ — buton basılsa bile engelle.
    _hblk = _havale_invoice_block(order)
    if _hblk:
        raise HTTPException(status_code=400, detail=_hblk)

    # Mikro ihracat: gerçek e-Arşiv İSTİSNA faturası (InvoiceTypeCode=ISTISNA, KDV %0,
    # istisna 301 "11/1-a Mal ihracatı"). ETGB placeholder yerine normal e-Arşiv akışı;
    # build aşamasında export builder seçilir.
    if order.get("is_micro_export"):
        invoice_type = "e-arsiv"
    cfg = await db.providers_config.find_one({"kind": "einvoice"}, {"_id": 0})
    active = (cfg or {}).get("active_provider")
    providers = (cfg or {}).get("providers") or {}

    # Yeni: Doğan ayarları settings.id=dogan_edonusum altında saklanıyor
    dogan_settings = await db.settings.find_one({"id": "dogan_edonusum"}, {"_id": 0}) or {}
    dogan_active = dogan_settings.get("enabled") and dogan_settings.get("username")

    if not (active and providers.get(active)) and not dogan_active:
        raise HTTPException(
            status_code=400,
            detail="Aktif e-fatura entegratörü yapılandırılmamış. Ayarlar > E-Arşiv / E-Fatura ekranından seçin."
        )

    # Prefix — e-Arşiv: FCT, e-Fatura: FCE (kullanıcı belirleyebilir; default Doğan standardı)
    if dogan_active:
        active = "dogan"
    else:
        pcfg = providers[active]

    # ─── AKILLI HİBRİT MOD ─────────────────────────────────────────────
    # invoice_type="auto" (default): VKN/TCKN dolu ise Doğan CheckUser ile
    # mükellef sorgula → mükellef ise e-Fatura, değilse e-Arşiv. Boşsa e-Arşiv.
    bill = dict(order.get("billing_address") or {})
    ship_addr = order.get("shipping_address") or {}
    # Site (facette) KURUMSAL fatura talebi bilgileri billing_address'te DEĞİL, billing_info'da
    # tutulur (is_corporate/company_name/tax_office/tax_number). Marketplace'te billing_address dolu gelir.
    # billing_address boşsa billing_info'dan tamamla → kurumsal site siparişinde VKN bulunup CheckUser
    # ile e-Fatura'ya yükseltilebilsin. (Aksi halde VKN boş kalıp yanlışlıkla e-Arşiv kesiliyordu.)
    _binfo = order.get("billing_info") or {}
    for _bk in ("tax_number", "tax_office", "company_name"):
        if not bill.get(_bk) and _binfo.get(_bk):
            bill[_bk] = _binfo.get(_bk)
    customer_vkn_raw = (bill.get("tax_number") or bill.get("tax_no") or bill.get("vkn") or "").strip().replace(" ", "")
    if not customer_vkn_raw:
        # Bireysel müşteri: Trendyol TCKN'i identityNumber alanında gelir
        customer_vkn_raw = (str(order.get("trendyol_identity_number") or "")).strip().replace(" ", "")
    receiver_alias = ""

    # Alıcı e-fatura mükellefi ise e-arşiv DÜZENLENEMEZ (Doğan 10013). Bu nedenle
    # mikro ihracat DIŞINDAKİ e-arşiv taleplerini de mükellef sorgusundan geçir:
    # mükellef → e-fatura'ya yükselt; değilse / VKN yoksa e-arşiv kalır.
    if invoice_type in ("auto", "e-arsiv") and not order.get("is_micro_export") and dogan_active:
        if customer_vkn_raw and len(customer_vkn_raw) in (10, 11):
            # Doğan'a sor
            try:
                from dogan_client import DoganClient as _DC
                from fastapi.concurrency import run_in_threadpool as _rtp
                _tmp = _DC(
                    username=dogan_settings["username"],
                    password=dogan_settings["password"],
                    is_test=dogan_settings.get("is_test", True),
                )
                chk = await _rtp(_tmp.check_user, customer_vkn_raw)
                # Mükellef ise e-Fatura'ya yükselt — VKN (10) VEYA e-Fatura mükellefi
                # TCKN'li şahıs firması (11). Builder TCKN/VKN şemasını otomatik kurar.
                if chk.get("is_efatura"):
                    invoice_type = "e-fatura"
                    receiver_alias = chk.get("invoice_alias") or ""
                else:
                    invoice_type = "e-arsiv"
            except Exception as _e:
                logger.warning(f"CheckUser fallback to e-arsiv: {_e}")
                invoice_type = "e-arsiv"
        else:
            # VKN/TCKN boş → bireysel e-arşiv
            invoice_type = "e-arsiv"

    if dogan_active:
        prefix = (dogan_settings.get("earchive_prefix") if invoice_type == "e-arsiv"
                  else dogan_settings.get("einvoice_prefix"))
        if not prefix:
            prefix = "FCT" if invoice_type == "e-arsiv" else "FCE"
    else:
        prefix = (pcfg.get("earchive_prefix") if invoice_type == "e-arsiv"
                  else pcfg.get("einvoice_prefix"))
        if not prefix:
            prefix = "FCT" if invoice_type == "e-arsiv" else "FCE"

    # ─── ATOMİK KİLİT (çift tıklama / eşzamanlı istek koruması) ──────────
    # Sayaç artırma + Doğan'a gönderim geri döndürülemez. Aynı sipariş için
    # ikinci eşzamanlı isteği atomik olarak engelle. 2 dk'dan eski kilit
    # "stale" sayılır (önceki deneme çökmüşse otomatik yeniden denenebilir).
    _lock_now = datetime.now(timezone.utc)
    _stale_iso = (_lock_now - timedelta(minutes=2)).isoformat()
    _claim = await db.orders.find_one_and_update(
        {"id": order_id, "invoice_issued": {"$ne": True},
         "$or": [{"invoice_in_progress": {"$ne": True}},
                 {"invoice_in_progress_at": {"$lt": _stale_iso}}]},
        {"$set": {"invoice_in_progress": True,
                  "invoice_in_progress_at": _lock_now.isoformat()}},
    )
    if _claim is None:
        _fresh = await db.orders.find_one({"id": order_id}, {"_id": 0}) or {}
        if _fresh.get("invoice_issued"):
            return {"success": True, "message": "Fatura zaten kesilmiş",
                    "invoice_number": _fresh.get("invoice_number", "")}
        raise HTTPException(status_code=409,
            detail="Bu sipariş için fatura işlemi şu anda sürüyor. Lütfen birkaç saniye bekleyip tekrar deneyin.")

    # Sıra numarası: atomik sayaç (db.counters) — başarısız denemede bile ilerler,
    # aynı numara BİR DAHA üretilmez (Doğan 10009 "duplicate" önlenir).
    # Taban: panelde en son kesilen no'nun DEVAMI — dogan_edonusum.earchive_start_number
    # (yıl bazlı: earchive_start_year ilgili yıla eşitse uygulanır).
    year_str = datetime.now(timezone.utc).strftime("%Y")
    seq_key = f"invoice_seq_{prefix}{year_str}"
    base_start = 0
    try:
        if invoice_type == "e-arsiv":
            if str((dogan_settings or {}).get("earchive_start_year") or "") == year_str:
                base_start = int((dogan_settings or {}).get("earchive_start_number") or 0)
        else:
            if str((dogan_settings or {}).get("einvoice_start_year") or "") == year_str:
                base_start = int((dogan_settings or {}).get("einvoice_start_number") or 0)
    except Exception:
        base_start = 0
    _existing_ctr = await db.counters.find_one({"_id": seq_key})
    if _existing_ctr is None and base_start > 0:
        await db.counters.update_one(
            {"_id": seq_key}, {"$setOnInsert": {"seq": base_start - 1}}, upsert=True
        )
    await db.counters.update_one({"_id": seq_key}, {"$inc": {"seq": 1}}, upsert=True)
    _seq_doc = await db.counters.find_one({"_id": seq_key}) or {}
    seq = int(_seq_doc.get("seq", 1))
    invoice_number = f"{prefix}{year_str}{seq:09d}"
    invoice_uuid = generate_id()  # UUID-like

    now = datetime.now(timezone.utc)
    issue_date = now.strftime("%Y-%m-%d")
    issue_time = now.strftime("%H:%M:%S")

    # Gerçek Doğan e-Arşiv kesimi
    dogan_result = None
    if dogan_active and invoice_type == "e-arsiv":
        from dogan_client import DoganClient
        from fastapi.concurrency import run_in_threadpool

        # Müşteri VKN/TCKN — order'dan al, yoksa default 11111111111 (TCKN bilinmiyor)
        customer_vkn = customer_vkn_raw
        customer_name = (bill.get("company_name") or bill.get("name") or
                         f"{ship_addr.get('first_name','')} {ship_addr.get('last_name','')}".strip() or
                         "Bireysel Müşteri")
        if not customer_vkn:
            # TCKN yoksa Doğan kabul etmez — bireysel için varsayılan TCKN dön (test'te)
            customer_vkn = "11111111111"
        if order.get("is_micro_export"):
            # Mikro ihracat (İSTİSNA): yabancı alıcının TR VKN'i yok →
            # Trendyol gerçek VKN verdiyse (10/11 hane) onu, yoksa 2222222222.
            _mx_vkn = (bill.get("tax_number") or bill.get("tax_no") or "").strip().replace(" ", "")
            customer_vkn = _mx_vkn if len(_mx_vkn) in (10, 11) else "2222222222"

        # Site sipariş kalemlerinde barkod boş olabilir → ürün varyantından tamamla
        # (fatura "Barkod" sütunu için). Marketplace kalemlerinde barkod zaten dolu gelir.
        # NOT: kalemin product_id'si ürünün id'sine DEĞİL kart id'sine (urun_karti_id /
        # csv_card_id) denk gelebilir → ürün bulunamayıp barkod boş kalırdı. Artık üç
        # anahtarla da eşleştiriliyor, ayrıca SKU/beden/tek-varyant fallback'leri var.
        _bc_keys = list({str(it.get("product_id")) for it in (order.get("items") or [])
                         if it.get("product_id") and not it.get("barcode")})
        _bc_pmap = {}
        if _bc_keys:
            async for _p in db.products.find(
                {"$or": [{"id": {"$in": _bc_keys}},
                         {"urun_karti_id": {"$in": _bc_keys}},
                         {"csv_card_id": {"$in": _bc_keys}}]},
                {"_id": 0, "id": 1, "urun_karti_id": 1, "csv_card_id": 1,
                 "variants": 1, "barcode": 1}):
                for _k in (_p.get("id"), _p.get("urun_karti_id"), _p.get("csv_card_id")):
                    if _k:
                        _bc_pmap[str(_k)] = _p

        def _item_barcode(it):
            if it.get("barcode"):
                return it["barcode"]
            _p = _bc_pmap.get(str(it.get("product_id"))) or {}
            _vs = _p.get("variants") or []
            _sz = (it.get("size") or "").strip().lower()
            _cl = (it.get("color") or "").strip().lower()
            _sku = (it.get("sku") or it.get("product_code") or "").strip().lower()
            # 1) SKU eşleşmesi
            if _sku:
                for _v in _vs:
                    if str(_v.get("sku") or "").strip().lower() == _sku and _v.get("barcode"):
                        return _v["barcode"]
            # 2) beden + renk
            for _v in _vs:
                if (str(_v.get("size") or "").strip().lower() == _sz
                        and (not _cl or str(_v.get("color") or "").strip().lower() == _cl)
                        and _v.get("barcode")):
                    return _v["barcode"]
            # 3) sadece beden
            if _sz:
                for _v in _vs:
                    if str(_v.get("size") or "").strip().lower() == _sz and _v.get("barcode"):
                        return _v["barcode"]
            # 4) tek barkodlu varyant → onu kullan
            _withbc = [_v for _v in _vs if _v.get("barcode")]
            if len(_withbc) == 1:
                return _withbc[0]["barcode"]
            # 5) ürün-seviye barkod
            return _p.get("barcode") or ""

        _vat_map = await _product_vat_map(order)
        line_items = []
        for it in (order.get("items") or []):
            _bc = _item_barcode(it)
            line_items.append({
                "name": it.get("product_name") or it.get("name") or "Ürün",
                "qty": int(it.get("quantity") or 1),
                "unit_price": float(it.get("price") or 0),
                "kdv_rate": _item_kdv(it, _vat_map),
                "sku": it.get("sku") or it.get("product_code") or "",
                "barcode": _bc,
                # Doğan şablonu Barkod/Renk/Beden sütunlarını satır notundan parse eder:
                # Renk='Renk:'..';' arası, Beden='Beden:'..':' arası, Barkod=substring-after('Barcode:').
                # Açıklamaya (Item/Name) stok/beden YAZILMAZ; sütunlar bu nottan dolar.
                "note": ((
                    f"Renk:{(it.get('color') or '').strip()};"
                    f"Beden:{(it.get('size') or '').strip()}:"
                    f"Barcode:{_bc}"
                ) if (it.get('color') or it.get('size') or _bc) else ""),
            })

        # Kupon/indirim faturaya yansısın: fatura brütü (kalemler + kargo) ile müşterinin
        # ödediği tutar (order.total) farkı = indirim. order.discount yedek olarak kullanılır.
        # Marketplace siparişinde fiyatlar zaten net geldiği için fark ~0 → indirim uygulanmaz.
        _items_gross = sum(float(i.get("price") or 0) * int(i.get("quantity") or 1)
                           for i in (order.get("items") or []))
        _inv_gross = _items_gross + float(order.get("shipping_cost") or 0)
        _paid_total = float(order.get("total") or _inv_gross)
        _inv_discount = round(_inv_gross - _paid_total, 2)
        if _inv_discount < 0.01:
            _inv_discount = round(float(order.get("discount") or 0), 2)
        if _inv_discount < 0:
            _inv_discount = 0.0

        # İndirimi ÜRÜN satırlarının birim fiyatına orantılı dağıt (kargo hariç).
        # Böylece her satırın KDV matrahı indirimli tutardan hesaplanır; satır toplamları
        # ve KDV tutarlı kalır → GİB/Doğan geçerli. (Builder'ın belge-seviyesi indirimi
        # LineExtension/matrah uyuşmazlığı yarattığı için kullanılmıyor.) Son satır kalanı alır.
        if _inv_discount > 0 and line_items:
            _prod_gross = sum((li["unit_price"] or 0) * (li["qty"] or 1) for li in line_items)
            if _prod_gross > 0:
                _disc = min(_inv_discount, round(_prod_gross, 2))
                _alloc = 0.0
                for _k, li in enumerate(line_items):
                    _g = (li["unit_price"] or 0) * (li["qty"] or 1)
                    if _k < len(line_items) - 1:
                        _d = round(_disc * _g / _prod_gross, 2)
                    else:
                        _d = round(_disc - _alloc, 2)  # yuvarlama kalanı son satıra
                    _alloc += _d
                    _new_gross = _g - _d
                    _q = li["qty"] or 1
                    li["unit_price"] = round(_new_gross / _q, 4) if _q else _new_gross

        # Taşıyan (kargo firması) — siparişin Trendyol'da beyan edilen kargosundan DİNAMİK.
        # Bilinen firmalar için ad+VKN; bilinmeyende Trendyol'un beyan adı, VKN boş (UBL'de atlanır).
        _cpn = (order.get("cargo_provider_name") or "")
        _cpl = _cpn.lower()
        if "trendyol" in _cpl:
            _carrier_name, _carrier_vkn, _carrier_city = "Trendyol Lojistik A.Ş.", "8590921777", "İstanbul"
        elif "mng" in _cpl:
            _carrier_name, _carrier_vkn, _carrier_city = "MNG KARGO YURTİÇİ VE YURTDIŞI TAŞIMACILIK A.Ş.", "6080712084", "İstanbul"
        elif ("yurtiçi" in _cpl) or ("yurtici" in _cpl):
            _carrier_name, _carrier_vkn, _carrier_city = "YURTİÇİ KARGO SERVİSİ A.Ş.", "9860008925", "İstanbul"
        elif "aras" in _cpl:
            _carrier_name, _carrier_vkn, _carrier_city = "ARAS KARGO YURT İÇİ YURT DIŞI TAŞIMACILIK A.Ş.", "0720039666", "İstanbul"
        elif "dhl" in _cpl:
            # Trendyol "DHL eCommerce" yurtiçinde MNG tarafından taşınır
            _carrier_name, _carrier_vkn, _carrier_city = "MNG KARGO YURTİÇİ VE YURTDIŞI TAŞIMACILIK A.Ş.", "6080712084", "İstanbul"
        elif _cpn.strip():
            # Bilinmeyen taşıyıcı: adı koru ama VKN boş kalmasın (Doğan CarrierParty'de VKN zorunlu)
            _carrier_name, _carrier_vkn, _carrier_city = _cpn.replace("Marketplace", "").strip(" -"), "6080712084", "İstanbul"
        else:
            _carrier_name, _carrier_vkn, _carrier_city = "MNG KARGO YURTİÇİ VE YURTDIŞI TAŞIMACILIK A.Ş.", "6080712084", "İstanbul"

        _earsiv_kwargs = dict(
            invoice_uuid=invoice_uuid,
            invoice_number=invoice_number,
            issue_date=issue_date,
            issue_time=issue_time,
            supplier_vkn=dogan_settings.get("vkn") or "7810816779",
            supplier_name=dogan_settings.get("supplier_name") or "FACETTE DIŞ TİC. A.Ş.",
            supplier_district=dogan_settings.get("supplier_district") or "KÜÇÜKÇEKMECE",
            supplier_city=dogan_settings.get("supplier_city") or "İstanbul",
            supplier_street=dogan_settings.get("supplier_street") or "İkitelli O.S.B. İmsan San. Sit. D BLOK NO:3",
            supplier_tax_office=dogan_settings.get("supplier_tax_office") or "HALKALI VERGİ DAİRESİ BAŞKANLIĞI",
            supplier_phone=dogan_settings.get("supplier_phone") or "",
            supplier_email=dogan_settings.get("supplier_email") or "",
            supplier_website=dogan_settings.get("supplier_website") or "facette.com.tr",
            customer_vkn_or_tckn=customer_vkn,
            customer_name=customer_name,
            customer_district=ship_addr.get("district") or "",
            customer_city=ship_addr.get("city") or "",
            customer_street=ship_addr.get("address") or "",
            customer_postal_zone=ship_addr.get("postal_code") or ship_addr.get("zip") or ship_addr.get("postal_zone") or "",
            customer_phone=ship_addr.get("phone") or "",
            customer_email=ship_addr.get("email") or order.get("user_email") or "",
            customer_tax_office=bill.get("tax_office") or "",
            currency="TRY",
            kdv_rate=10.0,
            line_items=line_items,
            shipping_cost=float(order.get("shipping_cost") or 0),
            discount=0.0,
            order_number=order.get("order_number") or order_id,
            payment_method=order.get("payment_method") or "DIGER",
            cargo_tracking=str(order.get("cargo_tracking_number") or order.get("cargo_tracking") or order.get("tracking_number") or ""),
            order_ext_id=str(order.get("marketplace_order_id") or order.get("platform_order_id") or order.get("order_number") or ""),
            store_name=order.get("store_name") or order.get("marketplace") or "",
            platform_label=_platform_display(order),
            payment_amount=float(order.get("total") or order.get("total_amount") or order.get("grand_total") or 0),
            carrier_name=_carrier_name,
            carrier_vkn=_carrier_vkn,
            carrier_city=_carrier_city,
            note="",
        )
        # Mikro ihracat İSTİSNA: faturada alıcı = yabancı alıcı (billing_address), kargocu değil.
        if order.get("is_micro_export"):
            _buyer_name = f"{bill.get('first_name','')} {bill.get('last_name','')}".strip()
            if _buyer_name:
                _earsiv_kwargs["customer_name"] = _buyer_name
            _earsiv_kwargs["customer_district"] = bill.get("district") or ""
            _earsiv_kwargs["customer_city"] = bill.get("city") or ""
            _earsiv_kwargs["customer_street"] = bill.get("address") or ""
            _earsiv_kwargs["customer_postal_zone"] = bill.get("postal_code") or bill.get("zip") or bill.get("postal_zone") or ""
            _earsiv_kwargs["customer_phone"] = bill.get("phone") or ""
            if bill.get("country"):
                _earsiv_kwargs["customer_country"] = bill.get("country")
        _earsiv_builder = (DoganClient.build_earsiv_export_ubl_xml
                           if order.get("is_micro_export")
                           else DoganClient.build_earsiv_ubl_xml)
        ubl_xml = _earsiv_builder(**_earsiv_kwargs)

        dogan_client = DoganClient(
            username=dogan_settings["username"],
            password=dogan_settings["password"],
            is_test=dogan_settings.get("is_test", True),
        )
        # Müşteri e-postasına PDF gönder
        cust_email = (ship_addr.get("email") or order.get("user_email") or "").strip()
        archive_note = f"Sipariş No: {order.get('order_number') or order_id}"
        dogan_result = await run_in_threadpool(
            dogan_client.send_earsiv_invoice,
            ubl_xml, invoice_uuid, cust_email, archive_note,
        )
        # Cift-numara korumasi: Dogan "zaten kayitli/mukerrer/10009" -> siradaki no
        _ex_tries = 0
        while (not dogan_result.get("success")) and _ex_tries < 5 and any(_t in str(dogan_result.get("message","")).lower() for _t in ("zaten","mükerrer","mukerrer","duplicate","already","10009","kayıtlı","kayitli","mevcut")):
            _ex_tries += 1
            await db.counters.update_one({"_id": seq_key}, {"$inc": {"seq": 1}}, upsert=True)
            _sd = await db.counters.find_one({"_id": seq_key}) or {}
            seq = int(_sd.get("seq", 1))
            invoice_number = f"{prefix}{year_str}{seq:09d}"
            invoice_uuid = generate_id()
            _earsiv_kwargs["invoice_number"] = invoice_number
            _earsiv_kwargs["invoice_uuid"] = invoice_uuid
            logger.warning(f"e-Arsiv numara cakismasi -> siradaki: {invoice_number} (deneme {_ex_tries})")
            ubl_xml = _earsiv_builder(**_earsiv_kwargs)
            dogan_result = await run_in_threadpool(
                dogan_client.send_earsiv_invoice,
                ubl_xml, invoice_uuid, cust_email, archive_note,
            )

        if not dogan_result.get("success"):
            logger.error(f"DOGAN_RET earsiv: {dogan_result}")
            # Hatayı log'a yaz, mock fallback ile devam etme — gerçek hata bildir
            await db.orders.update_one({"id": order_id}, {"$set": {"invoice_in_progress": False}})
            raise HTTPException(
                status_code=502,
                detail=f"Doğan e-Arşiv hatası: {dogan_result.get('message')}"
            )

    # ─── Doğan e-Fatura (TEMELFATURA) kesimi ─────────────────────────
    if dogan_active and invoice_type == "e-fatura":
        from dogan_client import DoganClient
        from fastapi.concurrency import run_in_threadpool

        customer_vkn = customer_vkn_raw
        if not customer_vkn or len(customer_vkn) not in (10, 11):
            raise HTTPException(
                status_code=400,
                detail="e-Fatura için 10 (VKN) veya 11 (TCKN) haneli kimlik gerekli, müşteride yok."
            )
        _ef_scheme = "TCKN" if len(customer_vkn) == 11 else "VKN"
        customer_name = (bill.get("company_name") or bill.get("name") or
                         f"{ship_addr.get('first_name','')} {ship_addr.get('last_name','')}".strip() or
                         "Müşteri")
        # Birey (TCKN) için Ad/Soyad — Person bloğu builder'da bundan kurulur.
        # Tüzel (VKN) için Person YOK; PartyName = firma unvanı kullanılır.
        _ef_first = ""
        _ef_family = ""
        if _ef_scheme == "TCKN":
            _ef_first = (ship_addr.get("first_name") or "").strip()
            _ef_family = (ship_addr.get("last_name") or "").strip()
            if not (_ef_first or _ef_family):
                _np = (customer_name or "").split()
                _ef_first = " ".join(_np[:-1]) if len(_np) > 1 else (customer_name or "")
                _ef_family = _np[-1] if len(_np) > 1 else ""

        # receiver_alias auto-mode'da çekildi; explicit invoice_type=e-fatura
        # çağrısında alias yoksa CheckUser ile tamamla
        if not receiver_alias:
            try:
                _tmp_cli = DoganClient(
                    username=dogan_settings["username"],
                    password=dogan_settings["password"],
                    is_test=dogan_settings.get("is_test", True),
                )
                chk = await run_in_threadpool(_tmp_cli.check_user, customer_vkn)
                receiver_alias = chk.get("invoice_alias") or ""
            except Exception:
                pass
        if not receiver_alias:
            raise HTTPException(
                status_code=400,
                detail=f"Müşteri ({customer_vkn}) e-Fatura mükellefi değil veya alias bulunamadı."
            )

        _vat_map = await _product_vat_map(order)
        line_items = []
        for it in (order.get("items") or []):
            line_items.append({
                "name": it.get("product_name") or it.get("name") or "Ürün",
                "qty": int(it.get("quantity") or 1),
                "unit_price": float(it.get("price") or 0),
                "kdv_rate": _item_kdv(it, _vat_map),
                "sku": it.get("sku") or it.get("product_code") or "",
                "buyer_sku": it.get("sku") or it.get("product_code") or "",
                "barcode": (it.get("barcode") or "").strip(),
                "color": (it.get("color") or "").strip(),
                "size": (it.get("size") or "").strip(),
                # Barkod/Renk/Beden/Stok Kodu satır notuna DEĞİL, builder'da header Note[0]'a
                # yazılır (gerçek çalışan e-Faturadaki format FCE...016). Satır notu boş kalır.
                "note": "",
            })

        # Taşıyan (kargo firması) — Trendyol'da beyan edilen kargodan DİNAMİK (e-Arşiv ile aynı eşleme)
        _cpn = (order.get("cargo_provider_name") or "")
        _cpl = _cpn.lower()
        if "trendyol" in _cpl:
            _carrier_name, _carrier_vkn = "Trendyol Lojistik A.Ş.", "8590921777"
        elif "mng" in _cpl:
            _carrier_name, _carrier_vkn = "MNG KARGO YURTİÇİ VE YURTDIŞI TAŞIMACILIK A.Ş.", "6080712084"
        elif ("yurtiçi" in _cpl) or ("yurtici" in _cpl):
            _carrier_name, _carrier_vkn = "YURTİÇİ KARGO SERVİSİ A.Ş.", "9860008925"
        elif "aras" in _cpl:
            _carrier_name, _carrier_vkn = "ARAS KARGO YURT İÇİ YURT DIŞI TAŞIMACILIK A.Ş.", "0720039666"
        elif "dhl" in _cpl:
            _carrier_name, _carrier_vkn = "MNG KARGO YURTİÇİ VE YURTDIŞI TAŞIMACILIK A.Ş.", "6080712084"
        elif _cpn.strip():
            _carrier_name, _carrier_vkn = _cpn.replace("Marketplace", "").strip(" -"), ""
        else:
            _carrier_name, _carrier_vkn = "", ""

        _efatura_kwargs = dict(
            invoice_uuid=invoice_uuid,
            invoice_number=invoice_number,
            issue_date=issue_date,
            issue_time=issue_time,
            supplier_vkn=dogan_settings.get("vkn") or "7810816779",
            supplier_name=dogan_settings.get("supplier_name") or "FACETTE DIŞ TİC. A.Ş.",
            supplier_district=dogan_settings.get("supplier_district") or "KÜÇÜKÇEKMECE",
            supplier_city=dogan_settings.get("supplier_city") or "İstanbul",
            supplier_street=dogan_settings.get("supplier_street") or "İkitelli O.S.B. İmsan San. Sit. D BLOK NO:3",
            supplier_tax_office=dogan_settings.get("supplier_tax_office") or "HALKALI VERGİ DAİRESİ BAŞKANLIĞI",
            supplier_website=dogan_settings.get("supplier_website") or "facette.com.tr",
            customer_vkn=customer_vkn,
            customer_id_scheme=_ef_scheme,
            customer_tax_office=bill.get("tax_office") or "",
            customer_first_name=(_ef_first if _ef_scheme == "TCKN" else ""),
            customer_family_name=(_ef_family if _ef_scheme == "TCKN" else ""),
            customer_name=customer_name,
            customer_street=ship_addr.get("address") or "",
            customer_district=ship_addr.get("district") or "",
            customer_city=ship_addr.get("city") or "İstanbul",
            customer_postal_zone=ship_addr.get("postal_code") or "34000",
            customer_email=ship_addr.get("email") or order.get("user_email") or "",
            currency="TRY",
            kdv_rate=10.0,
            line_items=line_items,
            shipping_cost=float(order.get("shipping_cost") or 0),
            discount=0.0,
            order_number=order.get("order_number") or order_id,
            order_date=(order.get("created_at") or now.isoformat())[:10],
            order_ext_id=str(order.get("marketplace_order_id") or order.get("platform_order_id") or order.get("order_number") or ""),
            cargo_tracking=str(order.get("cargo_tracking_number") or order.get("cargo_tracking") or order.get("tracking_number") or ""),
            carrier_name=_carrier_name,
            carrier_vkn=_carrier_vkn,
            carrier_type="Tüzel",
            store_name=order.get("store_name") or order.get("marketplace") or "",
            platform_label=_platform_display(order),
            payment_method=order.get("payment_method") or "",
            payment_amount=float(order.get("total") or order.get("total_amount") or order.get("grand_total") or 0),
            dispatch_date=str(order.get("shipped_at") or order.get("dispatch_date") or issue_date)[:10],
            # Senaryo: Ticari Fatura (alıcı 8 gün içinde kabul/red edebilir). Ayardan
            # değiştirilebilir (dogan_settings.einvoice_profile); varsayılan TİCARİ.
            profile_id=(dogan_settings.get("einvoice_profile") or "TICARIFATURA"),
        )
        ubl_xml = DoganClient.build_efatura_ubl_xml(**_efatura_kwargs)

        dogan_client = DoganClient(
            username=dogan_settings["username"],
            password=dogan_settings["password"],
            is_test=dogan_settings.get("is_test", True),
        )
        cust_email = (ship_addr.get("email") or order.get("user_email") or "").strip()
        sender_alias = (dogan_settings.get("sender_alias") or "").strip()
        if not sender_alias:
            # GÖNDERİCİ = GÖNDERİCİ BİRİM (GB) etiketi olmalıdır; POSTA KUTUSU (PK) DEĞİL.
            # Doğan'da iki ayrı etiket vardır:
            #   • Posta Etiketi (PK)  = urn:mail:defaultpk@facette.com  → ALICI posta kutusu
            #   • Birim Etiketi (GB)  = urn:mail:defaultgb@facette.com  → GÖNDERİCİ birim
            # CheckUser invoice_alias PK (defaultpk) döndürür; onu gönderici verince Doğan
            # "Kullanıcının Gönderici ... işlem yetkisi yoktur!" hatası verir. Bu yüzden
            # gönderici birim etiketini (GB) kullanırız. Ticimax+Doğan ayar ekranındaki değer:
            #   E-Fatura Birim Etiketi: urn:mail:defaultgb@facette.com
            sender_alias = (dogan_settings.get("sender_unit_alias")
                            or "urn:mail:defaultgb@facette.com")
        logger.info(f"e-Fatura gönderim: receiver_alias={'dolu' if receiver_alias else 'BOŞ'}, sender_alias={'dolu' if sender_alias else 'BOŞ'}")
        dogan_result = await run_in_threadpool(
            dogan_client.send_efatura_invoice,
            ubl_xml, invoice_uuid, invoice_number,
            customer_vkn, receiver_alias, sender_alias, cust_email,
        )
        _ef_tries = 0
        while (not dogan_result.get("success")) and _ef_tries < 5 and any(_t in str(dogan_result.get("message","")).lower() for _t in ("zaten","mükerrer","mukerrer","duplicate","already","10009","kayıtlı","kayitli","mevcut")):
            _ef_tries += 1
            await db.counters.update_one({"_id": seq_key}, {"$inc": {"seq": 1}}, upsert=True)
            _sd = await db.counters.find_one({"_id": seq_key}) or {}
            seq = int(_sd.get("seq", 1))
            invoice_number = f"{prefix}{year_str}{seq:09d}"
            invoice_uuid = generate_id()
            _efatura_kwargs["invoice_number"] = invoice_number
            _efatura_kwargs["invoice_uuid"] = invoice_uuid
            logger.warning(f"e-Fatura numara cakismasi -> siradaki: {invoice_number} (deneme {_ef_tries})")
            ubl_xml = DoganClient.build_efatura_ubl_xml(**_efatura_kwargs)
            dogan_result = await run_in_threadpool(
                dogan_client.send_efatura_invoice,
                ubl_xml, invoice_uuid, invoice_number,
                customer_vkn, receiver_alias, sender_alias, cust_email,
            )

        if not dogan_result.get("success"):
            logger.error(f"DOGAN_RET efatura: {dogan_result}")
            await db.orders.update_one({"id": order_id}, {"$set": {"invoice_in_progress": False}})
            raise HTTPException(
                status_code=502,
                detail=f"Doğan e-Fatura hatası: {dogan_result.get('message')}"
            )

    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "invoice_issued": True,
            "invoice_in_progress": False,
            "invoice_number": invoice_number,
            "invoice_uuid": invoice_uuid,
            "invoice_type": invoice_type,
            "invoice_provider": active,
            "invoice_provider_response": dogan_result,
            "invoice_intl_txn_id": (dogan_result or {}).get("intl_txn_id", ""),
            "invoice_dogan_id": (dogan_result or {}).get("invoice_id", ""),
            "invoice_pdf_url": (dogan_result or {}).get("web_key", ""),
            "invoice_issued_at": now.isoformat(),
            "invoice_issued_by": current_user.get("email", ""),
            "updated_at": now.isoformat(),
        }}
    )

    # Log — integration_logs'a ekle
    try:
        from .marketplace_hub import log_integration_event
        await log_integration_event(
            marketplace=f"einvoice:{active}",
            action="invoice_create",
            status="success",
            direction="outbound",
            ref_id=order_id,
            message=f"{invoice_type} fatura oluşturuldu: {invoice_number} (Doğan: {dogan_result.get('message') if dogan_result else 'mock'})",
        )
    except Exception:
        pass

    # ─── Trendyol: fatura kesilir kesilmez ANINDA Trendyol'a yükle ──────────
    # Tüm fatura tipleri için (e-arşiv, e-fatura, mikro ihracat) — hiçbirini
    # atlamaz. Hata olsa bile fatura kesimi başarılı sayılır (sadece loglanır),
    # böylece toplu fatura akışı kesintisiz devam eder. Bu sayede manuel "linki
    # yapıştır" adımına gerek kalmaz; geç/hiç gitmeme sorunu ortadan kalkar.
    trendyol_upload = None
    try:
        if (order.get("platform") == "trendyol") and order.get("trendyol_package_id"):
            _web = ((dogan_result or {}).get("web_key") or order.get("invoice_pdf_url") or "").strip()
            _tmpl = (dogan_settings.get("earsiv_link_template") or "").strip()
            if _web.startswith("http"):
                _inv_link = _web
            elif _tmpl and _web:
                _inv_link = _tmpl.replace("{web_key}", _web)
            else:
                _inv_link = ""
            if _inv_link:
                from .integrations import upload_invoice_to_trendyol
                try:
                    await upload_invoice_to_trendyol(
                        order.get("order_number"),
                        {"invoice_link": _inv_link, "invoice_number": invoice_number},
                        current_user,
                    )
                    trendyol_upload = {"ok": True, "link": _inv_link}
                    await db.orders.update_one(
                        {"id": order_id},
                        {"$set": {"trendyol_invoice_uploaded": True, "trendyol_invoice_error": ""}},
                    )
                except HTTPException as _he:
                    _err = str(_he.detail)
                    trendyol_upload = {"ok": False, "error": _err}
                    await db.orders.update_one(
                        {"id": order_id},
                        {"$set": {"trendyol_invoice_uploaded": False, "trendyol_invoice_error": _err[:1000]}},
                    )
                    logger.error(f"[trendyol invoice auto-upload] {order.get('order_number')}: {_err}")
            else:
                _err = ("Gecerli fatura linki uretilemedi: Dogan web_key bir URL degil ve "
                        "earsiv_link_template ayarli degil (Ayarlar > E-Arsiv / E-Fatura).")
                trendyol_upload = {"ok": False, "error": _err}
                await db.orders.update_one(
                    {"id": order_id},
                    {"$set": {"trendyol_invoice_uploaded": False, "trendyol_invoice_error": _err}},
                )
                logger.warning(f"[trendyol invoice] {order.get('order_number')}: {_err}")
    except Exception as _te:
        trendyol_upload = {"ok": False, "error": str(_te)}
        logger.error(f"[trendyol invoice auto-upload] {order.get('order_number')}: {_te}")

    return {
        "success": True,
        "message": "Fatura oluşturuldu",
        "invoice_number": invoice_number,
        "invoice_type": invoice_type,
        "provider": active,
        "trendyol_upload": trendyol_upload,
    }


# ---------------------------------------------------------------------------
# FATURA YAZDIR (HTML) — Orders.jsx handleBulkPrintInvoices iframe src olarak
# bu endpoint'i kullanır. Basit bir A4 fatura HTML'i döner; gerçek XSL-UBL
# dönüşümü canlıda provider'dan gelen PDF URL'siyle değiştirilir.
# ---------------------------------------------------------------------------
@router.get("/{order_id}/invoice/print")
async def print_invoice_html(order_id: str, token: str = None):
    """Basit fatura HTML çıktısı (yazdırılabilir). Bulk print için iframe."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    addr = order.get("shipping_address") or {}
    items = order.get("items") or []
    total = order.get("total") or order.get("total_amount") or 0

    rows = "".join(
        f"<tr><td>{i.get('product_name') or i.get('name') or ''}</td>"
        f"<td style='text-align:center'>{i.get('quantity',1)}</td>"
        f"<td style='text-align:right'>{(i.get('price') or 0):.2f} ₺</td>"
        f"<td style='text-align:right'>{((i.get('price') or 0)*(i.get('quantity') or 1)):.2f} ₺</td></tr>"
        for i in items
    )

    from fastapi.responses import HTMLResponse
    html = f"""
<!doctype html><html lang="tr"><head><meta charset="utf-8"/>
<title>Fatura — {order.get('invoice_number') or order.get('order_number','')}</title>
<style>
  @page {{ size: A4; margin: 15mm; }}
  body {{ font-family: -apple-system, Arial, sans-serif; color:#111; margin:0; }}
  .header {{ display:flex; justify-content:space-between; border-bottom:2px solid #111; padding-bottom:10px; margin-bottom:16px; }}
  .brand {{ font-size:20px; font-weight:800; letter-spacing:.1em; }}
  h1 {{ font-size:18px; margin:0 0 8px; }}
  table {{ width:100%; border-collapse:collapse; margin-top:12px; font-size:12px; }}
  th, td {{ padding:6px 8px; border-bottom:1px solid #eee; }}
  th {{ background:#f9fafb; text-align:left; }}
  .totals {{ margin-top:12px; text-align:right; }}
  .grand {{ font-size:16px; font-weight:800; margin-top:4px; }}
  .meta {{ font-size:11px; color:#555; }}
</style></head><body>
<div class="header">
  <div>
    <div class="brand">FACETTE</div>
    <div class="meta">Facette E-Ticaret · facette.com.tr</div>
  </div>
  <div style="text-align:right">
    <h1>{'E-ARŞİV FATURA' if order.get('invoice_type')=='e-arsiv' else 'E-FATURA'}</h1>
    <div class="meta">No: <strong>{order.get('invoice_number') or '-'}</strong></div>
    <div class="meta">Tarih: {(order.get('invoice_issued_at') or order.get('created_at') or '')[:10]}</div>
    <div class="meta">Sipariş: {order.get('order_number','')}</div>
  </div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:12px;">
  <div>
    <div class="meta" style="font-weight:700">Alıcı:</div>
    <div>{addr.get('full_name','')}</div>
    <div class="meta">{addr.get('address','')}</div>
    <div class="meta">{addr.get('district','')} / {addr.get('city','')}</div>
    <div class="meta">Tel: {addr.get('phone','')}</div>
  </div>
  <div>
    <div class="meta" style="font-weight:700">Sipariş Kanalı:</div>
    <div>{order.get('channel') or 'web'}</div>
    <div class="meta">Ödeme: {order.get('payment_method','-')}</div>
  </div>
</div>
<table>
  <thead><tr><th>Ürün</th><th style="text-align:center">Adet</th><th style="text-align:right">Birim</th><th style="text-align:right">Tutar</th></tr></thead>
  <tbody>{rows or '<tr><td colspan=4 style="text-align:center">Kalem yok</td></tr>'}</tbody>
</table>
<div class="totals">
  <div class="grand">Toplam: {float(total):.2f} ₺</div>
</div>
<p class="meta" style="margin-top:24px;border-top:1px solid #eee;padding-top:10px;">
  Bu belge e-Arşiv fatura olup, aktif entegratör
  <strong>{order.get('invoice_provider') or '-'}</strong> üzerinden üretilmiştir.
</p>
</body></html>
"""
    return HTMLResponse(content=html)



# ==================== KARGO BARKOD / MNG SHIPMENT ====================

def _normalize_phone(p: str) -> str:
    if not p:
        return ""
    digits = "".join(ch for ch in str(p) if ch.isdigit())
    # Türkiye: 90XXXXXXXXXX (12) → 5XXXXXXXXX (10) format, MNG cep formatı tercih eder
    if digits.startswith("90") and len(digits) == 12:
        return digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        return digits[1:]
    return digits


async def _get_mng_settings() -> dict:
    """MNG Kargo ayarlarını DB'den çeker, yoksa kullanıcı tarafından verilen default'u döndürür."""
    s = await db.settings.find_one({"id": "mng_kargo"}, {"_id": 0}) or {}
    return {
        "username": s.get("username") or "490059279",
        "password": s.get("password") or "Face.0024E",
        "customer_code": s.get("customer_code") or "FACETTE DIŞ TİC.A.Ş.",
        "tax_no": s.get("tax_no") or "6080712084",
        "is_active": s.get("is_active", True),
    }


async def _get_sender_info() -> dict:
    """Mağaza/Gönderici bilgilerini DB'den çeker (settings.id=store_info veya mng_kargo)."""
    store = await db.settings.find_one({"id": "store_info"}, {"_id": 0}) or {}
    return {
        "name": store.get("sender_name") or "FACETTE",
        "phone": _normalize_phone(store.get("sender_phone") or "5550000000"),
        "address": store.get("sender_address") or "",
        "city": store.get("sender_city") or "İstanbul",
        "district": store.get("sender_district") or "",
    }


@router.post("/{order_id}/cargo-barcode")
async def create_cargo_barcode(
    order_id: str,
    cargo_company: str = Query("MNG"),
    current_user: dict = Depends(require_admin)
):
    """Aktif kargo firmasında barkod / takip numarası oluşturur ve sipariş üzerine yazar.
    Şu an MNG Kargo entegrasyonu canlı; diğer firmalar için manuel takip no input'u gerekir.
    """
    company = (cargo_company or "MNG").upper()
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    # Havale/EFT siparişi ödeme onaylanmadan kargo barkodu OLUŞTURULMAZ (fatura ile aynı kural).
    _bc_pm = (order.get("payment_method") or "").lower()
    _bc_ps = (order.get("payment_status") or "").lower()
    if _bc_pm in _HAVALE_PMS and _bc_ps not in _SETTLED_PAY:
        raise HTTPException(status_code=400, detail=(
            "Havale onaylanmadığı için bu siparişe kargo barkodu oluşturulamadı. "
            "Önce siparişin ödemesini 'Ödendi' olarak işaretleyin (havale onayı), sonra barkod alın."
        ))

    # Eğer mevcut barkod/takip no varsa direkt dön — yoksa tekrar MNG'ye gidip
    # "duplicate siparis_no" hatası alınır (502 → "barkod oluşmuyor" görünümü).
    # cargo_barcode_number = bizim Self Barkodumuz (her zaman dolu); cargo_tracking_number = gerçek takip no (boş olabilir).
    _existing_tn = (order.get("cargo_tracking_number") or order.get("cargo_barcode_number")
                    or (order.get("cargo") or {}).get("mng_siparis_no")
                    or (order.get("cargo") or {}).get("tracking_number"))
    if _existing_tn:
        return {
            "success": True,
            "tracking_number": _existing_tn,
            "cargo_provider_name": order.get("cargo_provider_name") or company,
            "message": "Sipariş zaten kargo barkoduna sahip",
        }

    if company != "MNG":
        # Diğer firmalar için sahte/placeholder takip no üret (henüz canlı entegrasyon yok)
        import random
        tracking = f"{company}-{int(time.time())}{random.randint(100,999)}"
        await db.orders.update_one(
            {"id": order_id},
            {"$set": {
                "cargo_tracking_number": tracking,
                "cargo_provider_name": company,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        return {
            "success": True,
            "tracking_number": tracking,
            "cargo_provider_name": company,
            "message": f"{company} için manuel takip no atandı (canlı API entegrasyonu yok)",
        }

    # ===== MNG KARGO CANLI =====
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from mng_kargo_client import create_shipment as mng_create

    settings = await _get_mng_settings()
    if not settings["is_active"]:
        raise HTTPException(status_code=400, detail="MNG Kargo entegrasyonu pasif. Lütfen Ayarlar > Kargo bölümünden aktif edin.")

    # Sipariş üzerinden teslim adresini al
    ship = order.get("shipping_address") or {}
    full_name = (
        f"{ship.get('first_name','')} {ship.get('last_name','')}".strip()
        or ship.get("name")
        or "Alıcı"
    )
    phone = _normalize_phone(ship.get("phone"))
    if not phone:
        raise HTTPException(status_code=400, detail="Alıcı telefonu eksik. MNG barkodu oluşturulamaz.")
    il = (ship.get("city") or "").strip()
    ilce = (ship.get("district") or "").strip()
    adres = (ship.get("address") or "").strip()
    if not (il and adres):
        raise HTTPException(status_code=400, detail="Alıcı il ve adresi eksik. MNG barkodu oluşturulamaz.")

    # İçerik: ürün isimleri (ilk 250 karakter)
    items = order.get("items") or []
    icerik = "; ".join([f"{it.get('quantity',1)}x {it.get('product_name','')}".strip() for it in items])[:250] or "Ürün"
    kiymet = float(order.get("total") or order.get("subtotal") or 0)

    # Sipariş numarası (MNG için unique olmalı, varsa siparişin order_number'ı)
    siparis_no = str(order.get("order_number") or order.get("id") or order_id)

    # Kapıda ödeme?
    payment_method = (order.get("payment_method") or "").lower()
    kapida = 1 if payment_method in ("cash_on_delivery", "kapida") else 0
    odeme_sekli = "U" if kapida else "P"  # P=Peşin (Gönderici Öder), U=Ücretli (Alıcı Öder)

    # Senkron SOAP çağrısı event loop'u BLOKE etmesin diye thread'e taşı (aksi halde
    # MNG WSDL yavaşlığı/erişilemezliği Railway worker'ını kilitleyip 503'e yol açar).
    import asyncio as _aio_cargo
    try:
        res = await _aio_cargo.to_thread(
            mng_create,
            username=settings["username"],
            password=settings["password"],
            siparis_no=siparis_no,
            irsaliye_no=str(order.get("invoice_number") or "")[:20],
            kiymet=kiymet,
            icerik=icerik,
            hizmet_sekli="NORMAL",  # NORMAL | ONCELIKLI | GUNICI | AKSAM_TESLIMAT
            teslim_sekli=1,
            al_sms=0,
            gn_sms=1 if phone else 0,
            # MNG format: "Kg:Desi:En:Boy:Yukseklik:;" (her paket ; ile ayrılır)
            # Varsayılan: 1 paket, 1kg, 1 desi, 20x30x15cm
            parca_list="1:1:20:30:15:;",
            alici_ad=full_name,
            odeme_sekli=odeme_sekli,
            adres_farkli="0",
            il=il,
            ilce=ilce,
            adres=adres,
            tel_cep=phone,
            email=ship.get("email") or order.get("user_email") or "",
            kapida_odeme=kapida,
            platform_adi="",  # Pazaryeri değil — boş geç (N11/GG/TRND aksi takdirde)
            platform_kodu="",
        )
    except Exception as _mng_exc:
        # MNG bağlantı/SOAP exception'ı: 503 (Railway) yerine okunabilir 502 + gerçek sebep döndür.
        logger.error(f"MNG create_shipment exception (order={order_id}): {_mng_exc}")
        try:
            await db.cargo_logs.insert_one({
                "id": generate_id(), "order_id": order_id, "provider": "MNG",
                "action": "create_shipment", "status": "exception",
                "request_summary": {"siparis_no": siparis_no, "il": il, "ilce": ilce},
                "error": str(_mng_exc)[:1000],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=f"MNG Kargo bağlantı hatası: {str(_mng_exc)[:300]}")

    if not res.get("ok"):
        _hata = str(res.get("hata") or "")
        # E005: MNG'de bu sipariş_no'ya ait kayıt ZATEN VAR (önceki denemede oluştu ama
        # yanıt bize dönmeden timeout/503 olduğu için DB'ye yazılamadı). Bu bir HATA değil —
        # mevcut kaydı FaturaSiparisListesi'nden çekip kurtarıyoruz (yeni kayıt oluşturmadan).
        _recovered = False
        if ("ZATEN VAR" in _hata.upper()) or ("E005" in _hata.upper()):
            # Kayıt MNG'de KESİN var. Gerçek MNG gönderi no'yu çekmeyi dene (FaturaSiparisListesi);
            # ama günlük sorgu limiti ("GUNLUK SORGULAMA SINIRI") veya boş dönse BİLE sipariş_no'yu
            # barkod kabul edip kurtar — etiket barkodu zaten sipariş no'yu kodluyor, gerçek gönderi no
            # sonradan scheduler/backfill ile dolar. Amaç: etiket HEMEN oluşsun.
            _existing_barkod = ""
            _existing_gonderi = ""
            try:
                from mng_kargo_client import get_mng_shipment_status as _gss_recover
                _rec = await _aio_cargo.to_thread(
                    _gss_recover,
                    username=settings["username"], password=settings["password"], siparis_no=siparis_no
                )
                if _rec.get("ok"):
                    _existing_barkod = (_rec.get("mng_siparis_no") or "").strip()
                    _existing_gonderi = (_rec.get("gonderi_no") or "").strip()
                else:
                    logger.warning(f"E005 FaturaSiparisListesi başarısız (siparis_no={siparis_no}): {_rec.get('error')}")
            except Exception as _re:
                logger.warning(f"E005 kurtarma sorgusu hata (siparis_no={siparis_no}): {_re}")
            res = {
                "ok": True,
                "barkod": _existing_barkod or siparis_no,   # gerçek MNG no varsa o; yoksa sipariş no (etiket için yeterli)
                "gonderi_no": _existing_gonderi,
                "raw": "recovered_from_E005",
            }
            _recovered = True
            logger.info(f"E005 kurtarma (siparis_no={siparis_no}): barkod={res['barkod']}, gonderi={_existing_gonderi or '(sonra dolacak)'}")

        if not _recovered:
            # MNG hatasını cargo_logs'a yaz
            await db.cargo_logs.insert_one({
                "id": generate_id(),
                "order_id": order_id,
                "provider": "MNG",
                "action": "create_shipment",
                "status": "error",
                "request_summary": {"siparis_no": siparis_no, "alici_ad": full_name, "il": il, "ilce": ilce},
                "error": res.get("hata"),
                "raw": str(res.get("raw"))[:1000] if res.get("raw") else None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            raise HTTPException(status_code=502, detail=f"MNG Kargo hatası: {res.get('hata') or 'Bilinmeyen hata'}")

    barkod = res["barkod"]  # MNG_SIPARIS_NO (MNG Self Barkod) — gerçek kargo takip kodu
    
    # MNGGonderiBarkod denemesi → NZ-formatlı kargo barkodu (kurumsal hesaplarda anında dolar).
    # Yetki hatası alırsa graceful fallback: MNG_SIPARIS_NO kullanılır.
    nz_barkod = ""
    nz_gonderi_no = ""
    try:
        from mng_kargo_client import get_mng_barcode_immediately
        kapida = (order.get("payment_method") or "").lower() in ("cash_on_delivery", "kapida")
        nz_res = await _aio_cargo.to_thread(
            get_mng_barcode_immediately,
            username=settings["username"], password=settings["password"],
            siparis_no=siparis_no,
            irsaliye_no=str(order.get("invoice_number") or "")[:20],
            urun_bedeli=kiymet,
            kapida_tahsilat=kapida,
        )
        if nz_res.get("ok"):
            nz_barkod = nz_res.get("barkod", "")
            nz_gonderi_no = nz_res.get("gonderi_no", "")
            logger.info(f"MNG NZ barkod alındı: {nz_barkod} (gonderi_no={nz_gonderi_no})")
        else:
            logger.info(f"MNGGonderiBarkod denenemedi/başarısız (graceful fallback): {nz_res.get('hata')}")
    except Exception as nz_err:
        logger.warning(f"MNGGonderiBarkod exception (fallback to siparis_no): {nz_err}")

    # FaturaSiparisListesi'nden ek kargo durumu çek (şube, kargo statu, varsa GONDERI_NO)
    from mng_kargo_client import get_mng_shipment_status
    try:
        status_info = await _aio_cargo.to_thread(
            get_mng_shipment_status,
            username=settings["username"], password=settings["password"], siparis_no=siparis_no
        )
    except Exception as _st_exc:
        logger.warning(f"get_mng_shipment_status exception (graceful fallback): {_st_exc}")
        status_info = {"ok": False}
    gonderi_no_status = (status_info.get("gonderi_no") or "") if status_info.get("ok") else ""
    kargo_takip_url = (status_info.get("kargo_takip_url") or "") if status_info.get("ok") else ""
    kargo_statu = (status_info.get("kargo_statu") or "0") if status_info.get("ok") else "0"
    kargo_statu_aciklama = (status_info.get("kargo_statu_aciklama") or "") if status_info.get("ok") else ""

    # Self Barkod hesapları için: MNG_SIPARIS_NO zaten gerçek kargo takip kodudur
    # NZ-formatlı havuz tahsis edilen kurumsal hesaplarda GONDERI_NO field'ında ayrı bir kod gelir
    # Öncelik: NZ (anında MNGGonderiBarkod) → GONDERI_NO (FaturaSiparisListesi sonradan dolu) → MNG_SIPARIS_NO
    # Gerçek kargo takip no SADECE kargo firması gönderi numarası üretince dolar (NZ barkod / NZ gönderi / GONDERI_NO).
    # MNG Self Barkod (barkod = MNG_SIPARIS_NO) = bizim oluşturduğumuz barkod → kargoya verildiği/kargoda olduğu
    # anlamına GELMEZ, bu yüzden takip no olarak YAZILMAZ. Gerçek no scheduler/backfill ile sonradan yakalanır.
    real_tracking = nz_barkod or nz_gonderi_no or gonderi_no_status or ""
    public_tracking = real_tracking or barkod  # bildirim metni / geriye dönük fallback
    # MNG->DHL devri: kargotakip.dhlecommerce.com.tr/?takipNo={no} dogru deep-link (no ile direkt takip,
    # form/CAPTCHA gerektirmez). Gerçek no yoksa manuel takip sayfasina dusulur.
    track_link = (f"https://kargotakip.dhlecommerce.com.tr/?takipNo={real_tracking}" if real_tracking else "https://www.dhlecommerce.com.tr/gonderitakip")
    update_doc = {
        "cargo_tracking_number": real_tracking,    # SADECE gerçek takip no; yoksa boş (scheduler/backfill doldurur)
        "cargo_barcode_number": barkod,            # MNG Self Barkod — bizim barkodumuz (takip no DEĞİL)
        "cargo_tracking_link": track_link,
        "cargo_provider_name": "MNG Kargo",
        "cargo_provider_code": "MNG",
        "cargo": {
            "provider": "MNG",
            "provider_name": "MNG Kargo",
            "tracking_number": public_tracking,   # etiket/yazdırma butonu için DOLU (gerçek no yoksa barkod). Gerçek takip no order.cargo_tracking_number'da; kargo sütunu barkodu gerçek saymaz (ctn==barcodeNo).
            "tracking_link": track_link,
            "label_format": "10x15cm",
            "mng_siparis_no": barkod,                      # MNG Self Barkod (her zaman dolu)
            "mng_gonderi_no": gonderi_no_status,           # NZ formatlı (FaturaSiparisListesi sonrası)
            "mng_nz_barkod": nz_barkod,                    # NZ formatlı (MNGGonderiBarkod anında, varsa)
            "mng_nz_gonderi_no": nz_gonderi_no,
            "mng_kargo_statu": kargo_statu,
            "mng_kargo_statu_aciklama": kargo_statu_aciklama,
            "cikis_subesi": status_info.get("cikis_subesi"),
            "teslim_subesi": status_info.get("teslim_subesi"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "status": "shipped" if order.get("status") in ("pending", "confirmed", "processing") else order.get("status"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.orders.update_one({"id": order_id}, {"$set": update_doc})

    # Otomatik müşteri bildirimi (SMS + WhatsApp + Email) — kargoya verildi
    try:
        from notification_service import send_notification
        ship_addr = order.get("shipping_address") or {}
        full_name = (
            f"{ship_addr.get('first_name','')} {ship_addr.get('last_name','')}".strip()
            or ship_addr.get("name") or ""
        )
        # Gercek MNG/DHL gonderi no (siparis no DEGIL). E005 kurtarmasinda barkod=siparis_no
        # oldugu icin SMS'te yanlislikla siparis no gozukuyordu; gercek no yoksa bos birak.
        _real_tn = (nz_barkod or nz_gonderi_no or gonderi_no_status or "").strip()
        await send_notification(
            db,
            event="order_shipped",
            to_phone=ship_addr.get("phone") or order.get("customer_phone"),
            to_email=ship_addr.get("email") or order.get("customer_email") or order.get("user_email"),
            variables=await _order_notify_vars(order, order_number=order.get("order_number") or order_id, tracking_number=_real_tn, tracking_link=track_link, tracking_url=track_link, cargo_provider="MNG Kargo"),
        )
    except Exception as ne:
        logger.warning(f"Kargo bildirimi gönderilemedi (order={order_id}): {ne}")
    await db.cargo_logs.insert_one({
        "id": generate_id(),
        "order_id": order_id,
        "provider": "MNG",
        "action": "create_shipment",
        "status": "success",
        "tracking_number": barkod,
        "request_summary": {"siparis_no": siparis_no, "alici_ad": full_name, "il": il, "ilce": ilce},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "success": True,
        "tracking_number": public_tracking,
        "tracking_link": track_link,
        "mng_siparis_no": barkod,
        "mng_gonderi_no": gonderi_no_status,
        "mng_kargo_statu": kargo_statu,
        "cargo_provider_name": "MNG Kargo",
        "message": f"✅ MNG kargo barkodu oluşturuldu: {public_tracking}",
    }


@router.post("/{order_id}/cargo-refresh")
async def refresh_cargo_tracking(order_id: str, current_user: dict = Depends(require_admin)):
    """Kargo takip durumunu yeniler — anlaşılır mesajla.

    - Pazaryeri (Trendyol/Hepsiburada) siparişi → takip no pazaryeri senkronundan gelir,
      MNG'de SORGULANMAZ (yanlış 'bulunamadı' hatası önlenir).
    - Site siparişi → MNG FaturaSiparisListesi'nden gönderi no/durum çekilir.
    Hiçbir durumda kuru 'yenilenemedi' dönmez: MNG'de kayıt yok / gönderi no henüz atanmadı /
    yetki-IP whitelist hatası ayrı ayrı, ne yapılacağını söyleyen mesajla döner.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from mng_kargo_client import get_mng_shipment_status

    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    cargo = order.get("cargo") or {}
    siparis_no = str(order.get("order_number") or order_id)

    # ── Pazaryeri siparişi: MNG'de aranmaz (takip no pazaryerinden gelir) ──
    _platform = str(order.get("platform") or order.get("marketplace") or "").lower()
    _is_marketplace = (_platform in ("trendyol", "hepsiburada")
                       or (order.get("payment_method") == "marketplace"))
    if _is_marketplace:
        _tn = order.get("cargo_tracking_number") or cargo.get("tracking_number") or ""
        _label = ("Trendyol" if "trendyol" in _platform else
                  "Hepsiburada" if "hepsi" in _platform else "Pazaryeri")
        return {
            "success": True,
            "tracking_number": _tn,
            "message": (
                f"{_label} siparişi — kargo takip no pazaryeri senkronuyla güncellenir, MNG sorgusu yapılmaz. "
                + (f"Mevcut takip: {_tn}" if _tn else "Takip no pazaryeri tarafından atandığında senkronla gelecek.")
            ),
        }

    # ── Site siparişi: MNG'den durum çek (hata yutulmaz, kategorize edilir) ──
    settings = await _get_mng_settings()
    try:
        info = get_mng_shipment_status(
            username=settings["username"], password=settings["password"], siparis_no=siparis_no
        )
    except Exception as _e:
        logger.error(f"cargo-refresh MNG exception {siparis_no}: {_e}")
        info = {"ok": False, "error": str(_e)}

    if not info.get("ok"):
        _err = str(info.get("error") or "").lower()
        # MNG'de kayıt yok → genelde MNG kargo barkodu hiç oluşturulmamış (site siparişi elle "Kargoya Verildi")
        if (not _err) or any(t in _err for t in ("bulunamad", "kayıt", "kayit", "not found", "no record")):
            return {
                "success": False,
                "tracking_number": order.get("cargo_tracking_number") or "",
                "message": (
                    f"Bu sipariş ({siparis_no}) MNG'de bulunamadı. Site siparişi MNG ile gönderilmediyse "
                    "önce 📦 (MNG kargo barkodu) butonuyla oluşturun; barkod oluşunca takip no burada görünür."
                ),
            }
        # Yetki / IP whitelist / bağlantı → gerçek sistem hatası (kırmızı uyarı)
        raise HTTPException(
            status_code=502,
            detail=(f"MNG durumu alınamadı: {info.get('error')}. "
                    "Yetki/IP whitelist veya bağlantı sorunu olabilir — MNG paneli > API IP izinlerini kontrol edin."),
        )

    gonderi_no = info.get("gonderi_no") or ""   # GERÇEK kargo takip no (boş olabilir)
    mng_siparis_no = info.get("mng_siparis_no") or cargo.get("mng_siparis_no") or ""
    # ÖNEMLİ: iç sipariş no'yu (mng_siparis_no) ASLA takip no diye yazma. Sadece gerçek gönderi no.
    track_link = (f"https://kargotakip.dhlecommerce.com.tr/?takipNo={gonderi_no}"
                  if gonderi_no else "https://www.dhlecommerce.com.tr/gonderitakip")

    # Durum alanlarını her zaman güncelle; takip no'yu yalnız GERÇEK gönderi no doluysa yaz.
    update = {
        "cargo.mng_siparis_no": mng_siparis_no,
        "cargo.mng_gonderi_no": gonderi_no,
        "cargo.mng_kargo_statu": info.get("kargo_statu"),
        "cargo.mng_kargo_statu_aciklama": info.get("kargo_statu_aciklama"),
        "cargo.cikis_subesi": info.get("cikis_subesi"),
        "cargo.teslim_subesi": info.get("teslim_subesi"),
        "cargo.teslim_tarihi": info.get("teslim_tarihi"),
        "cargo_status_text": info.get("kargo_statu_aciklama") or "",
        "cargo_query_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if gonderi_no:
        update["cargo_gonderi_no"] = gonderi_no
        update["cargo_tracking_number"] = gonderi_no
        update["cargo_tracking_link"] = track_link
        update["cargo.tracking_number"] = gonderi_no
        update["cargo.tracking_link"] = track_link
    else:
        # Gerçek no yok → daha önce YANLIŞLIKLA yazılmış (iç no = takip no) değeri TEMİZLE,
        # böylece sipariş listesinde yanlış numara yerine "takip bekleniyor" görünür.
        _wrong = (order.get("cargo_tracking_number") or "")
        if _wrong and _wrong == mng_siparis_no:
            update["cargo_tracking_number"] = ""
            update["cargo_gonderi_no"] = ""
            update["cargo.tracking_number"] = ""
    await db.orders.update_one({"id": order_id}, {"$set": update})

    if gonderi_no:
        _msg = f"📦 Gönderi No: {gonderi_no}" + (f" · {info.get('kargo_statu_aciklama')}" if info.get("kargo_statu_aciklama") else "")
    else:
        # Gerçek gönderi no yok = kargo henüz teslim alıp işleme almamış.
        _aci = (info.get("kargo_statu_aciklama") or "").strip()
        _msg = ("Bu sipariş henüz kargoya verilmedi / kargo firması gönderi no atamadı"
                + (f" ({_aci})" if _aci else "")
                + ". Kargo şubede işleme alınınca gönderi no OTOMATİK çekilecek.")
    return {
        "success": True,
        "tracking_number": gonderi_no,   # gerçek no yoksa boş
        "mng_siparis_no": mng_siparis_no,
        "mng_gonderi_no": gonderi_no,
        "kargo_statu": info.get("kargo_statu"),
        "kargo_statu_aciklama": info.get("kargo_statu_aciklama"),
        "tracking_link": track_link,
        "message": _msg,
    }


@router.post("/cargo/backfill-tracking")
async def backfill_cargo_tracking(
    since: str = "",
    force: bool = False,
    all_statuses: bool = False,
    site_only: bool = False,
    current_user: dict = Depends(require_admin),
):
    """Kargoya verilmiş siparişlerin MNG (DHL eCommerce) takip numaralarını TOPLU çeker.

    - since boş → TÜM ZAMANLAR (tarih sınırı yok). Tarih verilirse (YYYY-MM-DD) o tarihten sonrası.
    - force=False → yalnız takip no'su EKSİK olanları sorgular (verimli); force=True → hepsini yeniden.
    - all_statuses=True → durum filtresi uygulamaz (varsayılan: yalnız kargo durumundaki siparişler).
    - site_only=True → pazaryeri (TY/HB önekli) siparişleri ATLAR; yalnız site siparişlerini sorgular
      (MNG/DHL'de zaten pazaryeri siparişi yok → boşuna sorgu/yanlış 'bulunamadı' önlenir).
    - get_mng_shipment_status (SALT OKUMA) → yeni kargo OLUŞTURMAZ, bildirim göndermez.
    - MNG sorgusu thread'de (event loop bloklanmaz); sıralı → MNG'yi hammer'lamaz.

    ÖNEMLİ: Gerçek takip no'yu MNG 'FaturaSiparisListesi' üretir — MNG kargoyu okutunca dolar
    ve bu sorgu MNG tarafında IP whitelist ister. DHL'in bir 'günlük sorgu limiti' YOKTUR.
    Dönüşteki 'diagnosis' her siparişin GERÇEK nedenini sayar (atanmadı / yetki / hata).
    """
    import asyncio
    from mng_kargo_client import get_mng_shipment_status

    settings = await _get_mng_settings()
    q = {}
    if since:
        q["created_at"] = {"$gte": since}
    if not all_statuses:
        q["status"] = {"$in": [
            "shipped", "in_transit", "out_for_delivery", "delivered",
            "return_requested", "return_approved", "return_in_transit",
            "returned", "undelivered",
        ]}
    cur = db.orders.find(
        q,
        {"_id": 0, "id": 1, "order_number": 1, "cargo_tracking_number": 1, "cargo": 1, "status": 1},
    ).sort("created_at", -1)
    orders = await cur.to_list(length=20000)

    updated, skipped, failed = [], [], []
    # Gerçek neden sayaçları — kullanıcı "limit mi?" diye soruyor; net görünsün.
    diagnosis = {
        "guncellendi": 0,
        "zaten_takip_no_vardi": 0,
        "mngde_kayit_var_takip_no_yok": 0,  # MNG kaydı oluşmuş, GONDERI_NO atanmamış (kargo henüz okutulmadı)
        "mngde_kayit_yok_veya_yetki": 0,    # hiç satır dönmedi → bulunamadı VEYA IP whitelist/yetki eksik
        "sorgu_hatasi": 0,                  # exception / SOAP hatası
        "gunluk_limit": 0,                  # MNG/DHL günlük sorgu limiti mesajı
    }
    limit_hit = False
    site_taranan = 0
    for o in orders:
        on = str(o.get("order_number") or "")
        _is_site = bool(on and (on.startswith("W") or on.startswith("IW")))
        if site_only and not _is_site:
            continue  # SADECE site siparişleri (W / IW); TY/HB ve diğerleri atlanır
        if _is_site:
            site_taranan += 1
        existing = o.get("cargo_tracking_number") or (o.get("cargo") or {}).get("tracking_number")
        _internal_no = (o.get("cargo") or {}).get("mng_siparis_no") or ""
        # Daha önce YANLIŞLIKLA iç sipariş no'su takip no diye yazılmışsa, "zaten var" sayma —
        # yeniden sorgula ki ya gerçek no ile düzelt ya da temizle.
        _existing_wrong = bool(existing) and existing == _internal_no
        if existing and not _existing_wrong and not force:
            skipped.append(on)
            diagnosis["zaten_takip_no_vardi"] += 1
            continue
        siparis_no = on or str(o.get("id"))
        try:
            info = await asyncio.to_thread(
                get_mng_shipment_status,
                username=settings["username"], password=settings["password"], siparis_no=siparis_no,
            )
        except Exception as e:
            failed.append({"no": siparis_no, "reason": "sorgu_hatasi", "err": str(e)[:160]})
            diagnosis["sorgu_hatasi"] += 1
            continue
        if not info.get("ok"):
            _err_txt = (info.get("error") or "")
            if any(k in _err_txt.lower() for k in ("sorgulama sınır", "sorgulama sinir",
                                                   "günlük sorgu", "gunluk sorgu", "sorgu limit",
                                                   "limit aşıl", "limit asil")):
                diagnosis["gunluk_limit"] += 1
                limit_hit = True
                failed.append({"no": siparis_no, "reason": "gunluk_limit", "err": _err_txt[:160]})
                break  # limiti uzatmamak için taramayı durdur
            failed.append({"no": siparis_no, "reason": "sorgu_hatasi", "err": _err_txt[:160]})
            diagnosis["sorgu_hatasi"] += 1
            continue
        gonderi = (info.get("gonderi_no") or "").strip()  # SADECE gerçek GONDERI_NO; iç no'ya düşme
        if not gonderi:
            has_record = bool((info.get("mng_siparis_no") or "").strip())
            reason = "mngde_kayit_var_takip_no_yok" if has_record else "mngde_kayit_yok_veya_yetki"
            diagnosis[reason] += 1
            # Yanlış (iç no) yazılmış takip no varsa TEMİZLE → listede "takip bekleniyor" görünsün.
            if _existing_wrong:
                await db.orders.update_one(
                    {"id": o["id"]},
                    {"$set": {"cargo_tracking_number": "", "cargo_gonderi_no": "",
                              "cargo.tracking_number": "",
                              "cargo_status_text": info.get("kargo_statu_aciklama") or "",
                              "updated_at": datetime.now(timezone.utc).isoformat()}},
                )
            failed.append({
                "no": siparis_no, "reason": reason,
                "kargo_statu": info.get("kargo_statu"),
                "kargo_statu_aciklama": info.get("kargo_statu_aciklama"),
                "mng_siparis_no": info.get("mng_siparis_no"),
            })
            continue
        await db.orders.update_one(
            {"id": o["id"]},
            {"$set": {
                "cargo_tracking_number": gonderi,
                "cargo_tracking_link": f"https://kargotakip.dhlecommerce.com.tr/?takipNo={gonderi}",
                "cargo.tracking_number": gonderi,
                "cargo.tracking_link": f"https://kargotakip.dhlecommerce.com.tr/?takipNo={gonderi}",
                "cargo.mng_gonderi_no": gonderi,
                "cargo.mng_kargo_statu": info.get("kargo_statu"),
                "cargo.mng_kargo_statu_aciklama": info.get("kargo_statu_aciklama"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        updated.append({"no": siparis_no, "gonderi_no": gonderi})
        diagnosis["guncellendi"] += 1

    # Günlük limite takıldıysak scheduler poll de bugün geri çekilsin diye bayrağı kaydet.
    if limit_hit:
        try:
            await db.settings.update_one(
                {"id": "mng_kargo"},
                {"$set": {"daily_limit_hit_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
        except Exception:
            pass

    return {
        "since": since or "(tüm zamanlar)", "force": force, "all_statuses": all_statuses,
        "site_only": site_only, "limit_hit": limit_hit,
        "scanned": len(orders), "site_taranan": site_taranan,
        "updated": len(updated), "skipped": len(skipped), "failed": len(failed),
        "diagnosis": diagnosis,
        "aciklama": (
            ("⚠️ MNG/DHL GÜNLÜK SORGU LİMİTİNE takıldı — tarama durduruldu, bugün için yeterli sorgu yapıldı; "
             "yarın otomatik devam eder. Bu limit DHL/MNG tarafındadır, bizim kodumuzda limit yoktur. "
             if limit_hit else
             "Bu limit (varsa) DHL/MNG tarafındadır; bizim kodumuzda günlük limit yoktur. ")
            + "Takip no MNG 'FaturaSiparisListesi'nden gelir; MNG kargoyu okutunca dolar (IP whitelist gerektirir). "
            "'mngde_kayit_var_takip_no_yok' = MNG kaydı oluşmuş ama numara henüz atanmamış. "
            "'mngde_kayit_yok_veya_yetki' = MNG'den satır dönmedi (bulunamadı VEYA whitelist/yetki eksik)."
        ),
        "updatedList": updated[:200], "failedList": failed[:80],
    }


@router.post("/returns/bulk-mark-refunded-silent")
async def bulk_mark_refunded_silent(payload: dict, current_user: dict = Depends(require_admin)):
    """Verilen sipariş ID'lerini 'İade Bedeli Ödendi' (refunded) durumuna alır.

    BİLDİRİMSİZ: db.orders doğrudan güncellenir, send_notification çağrılmaz →
    bu siparişler için müşteriye SMS/e-posta GİTMEZ. (Tek seferlik toplu işlem.)
    """
    order_ids = payload.get("order_ids") or []
    if not isinstance(order_ids, list) or not order_ids:
        raise HTTPException(status_code=400, detail="order_ids (liste) gerekli")
    now = datetime.now(timezone.utc).isoformat()
    done, missing = [], []
    for oid in order_ids:
        res = await db.orders.update_one(
            {"id": oid},
            {"$set": {
                "status": "refunded",
                "refund_paid_at": now,
                "return_approved_at": now,
                "updated_at": now,
                "refund_silent_bulk": True,
            }},
        )
        (done if res.matched_count else missing).append(oid)
    return {"requested": len(order_ids), "updated": len(done), "updatedIds": done, "missingIds": missing}


@router.post("/cargo/relink-dhl")
async def relink_cargo_dhl(current_user: dict = Depends(require_admin)):
    """Eski/yanlis kargo takip linklerini DHL deep-link formatina cevirir:
    kargotakip.dhlecommerce.com.tr/?takipNo={no} (no ile direkt takip, form/CAPTCHA yok).
    Sadece MNG/DHL linki olan siparisleri etkiler (Trendyol/HB kendi linkine dokunulmaz).
    No bos olan kayitlarda manuel takip sayfasina dusulur. Bildirimsiz; MNG API cagirmaz."""
    now = datetime.now(timezone.utc).isoformat()
    DEEP = "https://kargotakip.dhlecommerce.com.tr/?takipNo="
    FALLBACK = "https://www.dhlecommerce.com.tr/gonderitakip"
    rx = {"$regex": "mngkargo|dhlecommerce|gonderitakip|BarkodNo", "$options": "i"}
    q = {"cargo_tracking_link": rx}
    matched = await db.orders.count_documents(q)
    link_expr = {
        "$cond": [
            {"$gt": [{"$strLenCP": {"$ifNull": ["$cargo_tracking_number", ""]}}, 0]},
            {"$concat": [DEEP, "$cargo_tracking_number"]},
            FALLBACK,
        ]
    }
    r = await db.orders.update_many(q, [{"$set": {
        "cargo_tracking_link": link_expr,
        "cargo.tracking_link": link_expr,
        "updated_at": now,
    }}])
    return {"matched": matched, "modified": r.modified_count}


@router.post("/{order_id}/create-mng-shipment")
async def create_mng_shipment(order_id: str, current_user: dict = Depends(require_admin)):
    """MNG Kargo'ya sipariş gönder ve barkod al (kısayol)."""
    return await create_cargo_barcode(order_id=order_id, cargo_company="MNG", current_user=current_user)


@router.get("/cargo/mng-test")
async def mng_connection_test(siparis_no: str = None, current_user: dict = Depends(require_admin)):
    """TEŞHİS: MNG/DHL SOAP servisine (service.mngkargo.com.tr) sunucudan erişim testi.
    Barkod OLUŞTURMAZ — sadece Baglanti_Test() ping atar. 200 + JSON döner (CORS güvenli).
    ok=true → erişim var; ok=false → error alanında gerçek sebep (timeout/whitelist/DNS).
    """
    import asyncio as _aio_t, time as _t
    from mng_kargo_client import baglanti_test
    t0 = _t.time()
    try:
        res = await _aio_t.to_thread(baglanti_test)
        out = {"ok": bool(res.get("ok")), "result": str(res.get("result"))[:300],
               "error": str(res.get("error"))[:500] if res.get("error") else None,
               "ms": int((_t.time() - t0) * 1000)}
    except Exception as e:
        out = {"ok": False, "error": str(e)[:500], "ms": int((_t.time() - t0) * 1000)}
    # MNG ayar özeti (şifre maskeli) — credential dolu mu kontrolü
    try:
        s = await _get_mng_settings()
        out["settings"] = {
            "username": (s.get("username") or "")[:4] + "***" if s.get("username") else "(boş)",
            "has_password": bool(s.get("password")),
            "customer_code": s.get("customer_code") or "(boş)",
            "enabled": s.get("enabled", True),
        }
    except Exception as se:
        out["settings_error"] = str(se)[:200]
    # siparis_no verilirse FaturaSiparisListesi'nden mevcut kaydı da test et (E005 kurtarma kaynağı)
    if siparis_no:
        try:
            from mng_kargo_client import get_mng_shipment_status as _gss_t
            _s2 = await _get_mng_settings()
            _ss = await _aio_t.to_thread(
                _gss_t, username=_s2["username"], password=_s2["password"], siparis_no=siparis_no
            )
            # Ham yanıtı okunur bir önizlemeye indir (JSON şişmesin, panelde görünür).
            if isinstance(_ss, dict) and "raw" in _ss:
                _ss["raw_preview"] = str(_ss.pop("raw"))[:2000]
            out["shipment_status"] = _ss
        except Exception as _e2:
            out["shipment_status_error"] = str(_e2)[:300]
    return out


@router.get("/cargo/logs")
async def get_cargo_logs_diag(limit: int = 10, current_user: dict = Depends(require_admin)):
    """TEŞHİS: Son kargo işlem logları (create_shipment hataları/exception'ları dahil).
    create-mng-shipment 503/502 verdiğinde gerçek MNG hatası buraya yazılır."""
    try:
        logs = await db.cargo_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(
            length=min(int(limit or 10), 50))
        return {"ok": True, "count": len(logs), "logs": logs}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@router.post("/bulk/cargo-barcode")
async def bulk_create_cargo_barcode(
    order_ids: List[str],
    cargo_company: str = Query("MNG"),
    current_user: dict = Depends(require_admin)
):
    """Birden çok sipariş için topluca kargo barkodu oluştur."""
    success = []
    errors = []
    for oid in order_ids or []:
        try:
            r = await create_cargo_barcode(order_id=oid, cargo_company=cargo_company, current_user=current_user)
            success.append({"order_id": oid, "tracking_number": r.get("tracking_number")})
        except HTTPException as he:
            errors.append({"order_id": oid, "error": he.detail})
        except Exception as e:
            errors.append({"order_id": oid, "error": str(e)})
    return {
        "success": True,
        "success_count": len(success),
        "error_count": len(errors),
        "successes": success,
        "errors": errors,
    }


@router.post("/bulk-create-invoice")
async def bulk_create_invoice(
    order_ids: List[str],
    invoice_type: str = Query("auto"),
    current_user: dict = Depends(require_admin)
):
    """Toplu fatura kesimi — invoice_type=auto ile her sipariş için VKN/TC kontrolü
    yapılır, mükellefse e-Fatura, değilse e-Arşiv kesilir.
    """
    success = []
    errors = []
    for oid in order_ids or []:
        try:
            # Daha önce kesilmişse atla
            o = await db.orders.find_one({"id": oid}, {"_id": 0, "invoice_issued": 1, "order_number": 1})
            if not o:
                errors.append({"order_id": oid, "error": "Sipariş bulunamadı"})
                continue
            if o.get("invoice_issued"):
                errors.append({"order_id": oid, "error": "Fatura zaten kesilmiş", "skipped": True})
                continue
            r = await create_invoice_for_order(
                order_id=oid, invoice_type=invoice_type, current_user=current_user
            )
            success.append({
                "order_id": oid,
                "invoice_number": r.get("invoice_number"),
                "invoice_type": r.get("invoice_type"),
                "invoice_pdf_url": r.get("invoice_pdf_url"),
                "trendyol_upload": r.get("trendyol_upload"),
            })
        except HTTPException as he:
            errors.append({"order_id": oid, "error": str(he.detail)})
        except Exception as e:
            errors.append({"order_id": oid, "error": str(e)})
    return {
        "success": True,
        "success_count": len(success),
        "error_count": len(errors),
        "successes": success,
        "errors": errors,
    }


# ═══════════════════ MNG KARGO WEBHOOK ═══════════════════════════════
@router.post("/cargo/mng-webhook")
async def mng_cargo_webhook(payload: dict):
    """MNG Kargo'dan gelen kargo durum güncelleme webhook'u.

    MNG Kargo, gönderi durumu değiştikçe önceden tanımlanmış URL'e bu yapıda
    POST atar:
      {"BARKOD": "NZ123", "ISLEM_KODU": "300", "ISLEM_ADI": "Dağıtımda",
       "TARIH": "2026-05-06T12:30:00", "REFERANS_NO": "FC123ABCD"}

    İşlem kodları (MNG standardı):
      - 100: Şubeye girdi
      - 200: Transfere alındı
      - 300: Dağıtıma çıktı
      - 400: Teslim edildi
      - 500: İade
    """
    barkod = (payload.get("BARKOD") or payload.get("barcode") or "").strip()
    islem_kodu = str(payload.get("ISLEM_KODU") or payload.get("status_code") or "")
    islem_adi = (payload.get("ISLEM_ADI") or payload.get("status_text") or "").strip()
    tarih = (payload.get("TARIH") or payload.get("event_time") or
             datetime.now(timezone.utc).isoformat())
    referans_no = (payload.get("REFERANS_NO") or payload.get("reference_no") or "").strip()

    if not barkod and not referans_no:
        raise HTTPException(status_code=400, detail="BARKOD veya REFERANS_NO zorunlu")

    # Siparişi barkod veya referans_no ile bul
    query_or = []
    if barkod:
        query_or.extend([
            {"cargo_tracking_number": barkod},
            {"cargo.mng_nz_barkod": barkod},
            {"cargo.mng_gonderi_no": barkod},
            {"cargo.mng_siparis_no": barkod},
        ])
    if referans_no:
        query_or.append({"order_number": referans_no})

    order = await db.orders.find_one({"$or": query_or}, {"_id": 0, "id": 1, "order_number": 1, "cargo_status_history": 1})
    if not order:
        # Sessizce 200 dön — MNG retry yapmasın, sadece logla
        await db.integration_logs.insert_one({
            "id": generate_id(),
            "service": "mng_kargo",
            "event": "webhook_unknown_order",
            "barkod": barkod,
            "referans_no": referans_no,
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"success": True, "matched": False}

    # Sipariş durumu mapping
    status_map = {
        "100": ("preparing", "Şubeye Girdi"),
        "200": ("shipped", "Transfere Alındı"),
        "300": ("shipped", "Dağıtımda"),
        "400": ("delivered", "Teslim Edildi"),
        "500": ("returned", "İade"),
    }
    new_status, _ = status_map.get(islem_kodu, (None, None))

    update_set = {
        "cargo_last_status_code": islem_kodu,
        "cargo_last_status_text": islem_adi,
        "cargo_last_event_at": tarih,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if new_status:
        update_set["status"] = new_status
        if new_status == "delivered":
            update_set["delivered_at"] = tarih

    history_entry = {
        "code": islem_kodu, "text": islem_adi, "at": tarih,
        "barkod": barkod, "raw": payload,
    }

    await db.orders.update_one(
        {"id": order["id"]},
        {
            "$set": update_set,
            "$push": {"cargo_status_history": history_entry},
        },
    )

    # Log'a yaz
    await db.integration_logs.insert_one({
        "id": generate_id(),
        "service": "mng_kargo",
        "event": "webhook_update",
        "order_id": order["id"],
        "order_number": order.get("order_number"),
        "barkod": barkod,
        "code": islem_kodu,
        "text": islem_adi,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "success": True,
        "matched": True,
        "order_id": order["id"],
        "order_number": order.get("order_number"),
        "new_status": new_status,
    }


@router.get("/{order_id}/cargo-label")
async def get_cargo_label(order_id: str, token: str = None):
    """100x150mm yazdırılabilir kargo etiketi (HTML + Code39).
    Tek barkod: kargo takip no varsa onu, yoksa sipariş numarasını kullanır.
    Tasarım: LOGO + ORIGIN ID + FROM/TO/REF + ORDER/ITEM/SHIP DATE/DIMENSIONS/WEIGHT
    + REMARKS + tek barkod sağ altta + sağ kenarda handling icon'ları.
    """
    from fastapi.responses import HTMLResponse
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    barkod = order.get("cargo_tracking_number") or ""
    cargo_obj = order.get("cargo") or {}
    mng_siparis_no = cargo_obj.get("mng_siparis_no") or ""
    mng_gonderi_no = cargo_obj.get("mng_gonderi_no") or ""
    mng_nz_barkod = cargo_obj.get("mng_nz_barkod") or ""
    # Tek barkod: NZ > GONDERI_NO > MNG_SIPARIS_NO > tracking > sipariş_no
    real_kargo_takip = mng_nz_barkod or mng_gonderi_no or mng_siparis_no or barkod or ""
    siparis_no = str(order.get("order_number") or order_id)
    # ✅ Barkod ÇUBUKLARI = SİPARİŞ NO (W10047). Depo/operasyon barkodu okutunca siparişi
    # bulabilsin diye. Önceden çubuklar kargo takip no'yu (örn. 170553284) kodluyordu ama
    # alttaki yazı sipariş no idi → okutunca sipariş no yerine takip no çıkıyordu.
    main_barcode = siparis_no
    # Kargo Takip yazısı etiket/barkod altından KALDIRILDI (kullanıcı talebi).
    # Barkod çubukları + altındaki sipariş no zaten yeterli; ayrıca "Kargo Takip: ..." satırı basılmaz.
    tracking_line = ""
    sender = await _get_sender_info()
    mng = await _get_mng_settings()
    sender_company = mng.get("customer_code") or sender["name"] or "FACETTE"
    sender_addr_line = f"{sender['address']}, {sender['district']}/{sender['city']}".strip(" ,/")

    ship = order.get("shipping_address") or {}
    receiver_name = f"{ship.get('first_name','')} {ship.get('last_name','')}".strip() or ship.get("name") or "Alıcı"
    receiver_phone = ship.get("phone") or ""
    receiver_addr = (ship.get("address") or "").strip()
    receiver_district_city = f"{ship.get('district','')} / {ship.get('city','')}".strip(" /")
    receiver_full_addr = ", ".join([x for x in [receiver_addr, receiver_district_city] if x])

    items = order.get("items") or []
    total_qty = sum(int(it.get("quantity") or 1) for it in items)
    # İlk ürünün stock_code/sku/barcode/name'i ITEM NO; çoklu ürün varsa "+N more"
    first_item = items[0] if items else {}
    item_no = (first_item.get("stock_code") or first_item.get("sku")
               or first_item.get("barcode") or first_item.get("name") or "-")
    # Çok uzun ürün ismini kısalt
    item_no = (item_no[:32] + "…") if len(str(item_no)) > 33 else item_no
    if len(items) > 1:
        item_no = f"{item_no} (+{len(items)-1})"

    ship_date = order.get("ship_date") or order.get("created_at") or datetime.now(timezone.utc).isoformat()
    try:
        ship_date_str = datetime.fromisoformat(ship_date.replace("Z", "+00:00")).strftime("%d %b %Y").upper()
    except Exception:
        ship_date_str = datetime.now(timezone.utc).strftime("%d %b %Y").upper()

    # Dimensions / Weight — items'dan toplama
    total_weight = sum(float(it.get("weight") or 0) for it in items)
    if total_weight <= 0:
        total_weight = 0.5 * total_qty  # makul varsayılan
    dimensions = order.get("package_dimensions") or "30x20x15 cm"
    weight_str = f"{total_weight:.1f} KG"

    payment_method = (order.get("payment_method") or "").lower()
    remarks = order.get("cargo_remarks") or order.get("note") or ""
    if not remarks:
        remarks = "Alıcı Ödemeli" if payment_method in ("cash_on_delivery", "kapida") else "Gönderici Ödemeli"

    # Kargo bilgileri (paylaşılan referans şablonuna göre)
    cargo_company_display = "DHL E-Commerce"  # MNG ibaresi kaldırıldı
    payment_method = (order.get("payment_method") or "").lower()
    is_kapida = payment_method in ("cash_on_delivery", "kapida")
    odeme_turu = "Kapıda Ödemeli" if is_kapida else "Peşin Ödemeli"
    kargo_tipi = f"{odeme_turu} Kargo"

    # Telefon formatı: 5435955290 → 543 595 52 90
    def _fmt_phone(p: str) -> str:
        if not p:
            return ""
        digits = "".join(c for c in str(p) if c.isdigit())
        # Başında 90 ülke kodu varsa atla, 0 ile başlıyorsa atla
        if digits.startswith("90") and len(digits) == 12:
            digits = digits[2:]
        elif digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        if len(digits) == 10:
            return f"{digits[0:3]} {digits[3:6]} {digits[6:8]} {digits[8:10]}"
        return str(p)

    # Brand logo (PNG → base64) — paylaşılan FACETTE wordmark
    import base64, pathlib
    logo_b64 = ""
    try:
        logo_path = pathlib.Path(__file__).parent.parent / "static" / "brand" / "facette-logo.png"
        if logo_path.exists():
            logo_b64 = base64.b64encode(logo_path.read_bytes()).decode()
    except Exception:
        logo_b64 = ""
    logo_src = f"data:image/png;base64,{logo_b64}" if logo_b64 else ""

    # Sender (gönderici) için telefon
    sender_phone = _fmt_phone(sender.get("phone", "") or "")
    receiver_phone_fmt = _fmt_phone(receiver_phone)

    html = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="UTF-8"><title>Kargo Etiketi - {siparis_no}</title>
<link href="https://fonts.googleapis.com/css2?family=Mulish:wght@400;500;600;700;800;900&family=Libre+Barcode+39+Extended&display=swap" rel="stylesheet">
<style>
  @page {{ size: 100mm 120mm; margin: 0; }}
  * {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  body {{ margin: 0; font-family: 'Mulish','Helvetica Neue',Arial,sans-serif; width: 100mm; height: 120mm; color: #000; background:#fff; }}
  .label {{ width: 100mm; height: 120mm; padding: 2mm; }}
  .main {{ width: 100%; height: 100%; border: 1.8pt solid #000; border-radius: 1.5mm; padding: 2.5mm; display:flex; flex-direction:column; }}

  /* LOGO bandı */
  .logo-band {{ display:flex; align-items:center; justify-content:center; padding: 0.5mm 0 1.8mm 0; border-bottom: 1.4pt solid #000; }}
  .logo-band img {{ height: 7mm; width: auto; max-width: 78mm; }}
  .logo-fallback {{ font-family:'Mulish',sans-serif; font-weight: 900; font-size: 18pt; letter-spacing: 5pt; }}

  /* Bölüm başlığı (Gönderici / Alıcı / Kargo Bilgileri) */
  .section-title {{ text-align: center; font-family:'Mulish',sans-serif; font-weight: 800; font-size: 9pt; letter-spacing: 0.5pt; padding: 1.2mm 0; border-bottom: 1pt solid #000; background: #f0f0f0; }}

  /* Tablo satırları (label / value) */
  .info-table {{ border-bottom: 1pt solid #000; }}
  .info-row {{ display:flex; border-bottom: 0.6pt solid #000; min-height: 5mm; }}
  .info-row:last-child {{ border-bottom: 0; }}
  .info-row .lbl {{ width: 22mm; padding: 1mm 1.5mm; font-family:'Mulish',sans-serif; font-weight: 700; font-size: 7.8pt; border-right: 0.6pt solid #000; display:flex; align-items:center; }}
  .info-row .val {{ flex: 1; padding: 1mm 1.5mm; font-family:'Mulish',sans-serif; font-weight: 700; font-size: 8.4pt; display:flex; align-items:center; line-height: 1.25; word-break: break-word; }}
  .info-row .val.addr {{ font-weight: 600; font-size: 7.6pt; line-height: 1.3; }}

  /* Barkod */
  .barcode-band {{ margin-top: auto; padding-top: 1.5mm; text-align:center; }}
  /* Libre Barcode 39 Extended → Code 39 (alfanumerik desteklenir). 30pt → her char ~5mm,
     12 karakter ≈ 60mm < 88mm kullanılabilir alan. */
  .barcode {{ font-family: 'Libre Barcode 39 Extended', 'Libre Barcode 39', monospace; font-size: 30pt; letter-spacing: 0; line-height: 0.95; color:#000; white-space: nowrap; display: block; }}
  .barcode-num {{ font-size: 9pt; letter-spacing: 1.4pt; font-family: 'Courier New', monospace; font-weight: 800; margin-top: 0.3mm; }}
</style></head><body>
<div class="label">
  <div class="main">

    <!-- LOGO BANDI -->
    <div class="logo-band">
      {('<img src="'+logo_src+'" alt="FACETTE"/>') if logo_src else '<div class="logo-fallback">FACETTE</div>'}
    </div>

    <!-- GÖNDERİCİ BİLGİLERİ -->
    <div class="section-title">Gönderici Bilgileri</div>
    <div class="info-table">
      <div class="info-row"><span class="lbl">Firma</span><span class="val">{sender_company}</span></div>
      <div class="info-row"><span class="lbl">Telefon</span><span class="val">{sender_phone}</span></div>
      <div class="info-row"><span class="lbl">Adres</span><span class="val addr">{sender_addr_line}</span></div>
    </div>

    <!-- ALICI BİLGİLERİ -->
    <div class="section-title">Alıcı Bilgileri</div>
    <div class="info-table">
      <div class="info-row"><span class="lbl">İsim</span><span class="val">{receiver_name}</span></div>
      <div class="info-row"><span class="lbl">Telefon</span><span class="val">{receiver_phone_fmt}</span></div>
      <div class="info-row"><span class="lbl">Adres</span><span class="val addr">{receiver_full_addr}</span></div>
    </div>

    <!-- KARGO BİLGİLERİ -->
    <div class="section-title">Kargo Bilgileri</div>
    <div class="info-table">
      <div class="info-row"><span class="lbl">Kargo Firması</span><span class="val">{cargo_company_display}</span></div>
      <div class="info-row"><span class="lbl">Ödeme Türü</span><span class="val">{odeme_turu}</span></div>
      <div class="info-row"><span class="lbl">Kargo Tipi</span><span class="val">{kargo_tipi}</span></div>
    </div>

    <!-- BARKOD (alt) -->
    <div class="barcode-band">
      <div class="barcode">*{main_barcode}*</div>
      <div class="barcode-num">{siparis_no}</div>
      {tracking_line}
    </div>

  </div>
</div>
<script>
  // Barkodu çerçeveye sığdır — fontlar yüklendikten SONRA çalış
  async function fitBarcode() {{
    if (document.fonts && document.fonts.ready) {{
      try {{ await document.fonts.ready; }} catch(e) {{}}
    }}
    // Ekstra güvenlik: fontların gerçekten render olması için bir frame bekle
    await new Promise(r => requestAnimationFrame(() => r()));
    const el = document.querySelector('.barcode');
    if (!el) return;
    // Container genişliği — .main padding'i çıkarılarak hesaplanır
    const main = document.querySelector('.main');
    const maxW = (main ? main.clientWidth : 340) - 12;
    // 36pt'tan başla, sığana kadar küçült (min 18pt)
    let size = 36;
    el.style.fontSize = size + 'pt';
    let safety = 24;
    while (el.scrollWidth > maxW && size > 18 && safety-- > 0) {{
      size -= 1;
      el.style.fontSize = size + 'pt';
    }}
  }}
  window.addEventListener('load', () => {{
    fitBarcode().then(() => {{
      if (window.location.search.includes('print=1')) {{
        setTimeout(() => window.print(), 200);
      }}
    }});
  }});
</script>
</body></html>"""
    return HTMLResponse(content=html, headers={"Content-Type": "text/html; charset=utf-8"})


# ==================== MNG KARGO AYARLARI ====================
# Bu ayarları integrations.py altındaki generic /{marketplace}/settings de yönetebilir,
# ancak özelleştirilmiş alanlar için ayrı endpoint sağlıyoruz.

@router.get("/cargo/mng-settings")
async def get_mng_settings(current_user: dict = Depends(require_admin)):
    """MNG Kargo ayarlarını döndür (şifre maskelenir)."""
    s = await db.settings.find_one({"id": "mng_kargo"}, {"_id": 0}) or {}
    return {
        "customer_code": s.get("customer_code") or "FACETTE DIS TIC.A.S.",
        "username": s.get("username") or "490059279",
        "password": "********" if s.get("password") else "",
        "tax_no": s.get("tax_no") or "6080712084",
        "is_active": s.get("is_active", True),
        "barkod_cikti_turu": s.get("barkod_cikti_turu") or "Standart",
        "musteri_kodu_goster": s.get("musteri_kodu_goster", False),
    }


@router.post("/cargo/mng-settings")
async def save_mng_settings(payload: dict, current_user: dict = Depends(require_admin)):
    """MNG Kargo ayarlarını kaydet."""
    update = {
        "customer_code": payload.get("customer_code", "FACETTE DIŞ TİC.A.Ş."),
        "username": payload.get("username", ""),
        "tax_no": payload.get("tax_no", ""),
        "is_active": bool(payload.get("is_active", True)),
        "barkod_cikti_turu": payload.get("barkod_cikti_turu", "Standart"),
        "musteri_kodu_goster": bool(payload.get("musteri_kodu_goster", False)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if payload.get("password") and payload.get("password") != "********":
        update["password"] = payload.get("password")
    await db.settings.update_one({"id": "mng_kargo"}, {"$set": update}, upsert=True)
    return {"success": True, "message": "MNG Kargo ayarları kaydedildi"}


@router.post("/cargo/mng-test")
async def test_mng_connection(current_user: dict = Depends(require_admin)):
    """MNG Kargo bağlantı testi (Baglanti_Test)."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from mng_kargo_client import baglanti_test
    return baglanti_test()


# =============================================================================
# Faz 2 — Havale dekont bildirimi (storefront yukleme + admin goruntuleme)
# =============================================================================
@router.post("/by-number/{order_number}/payment-notification")
async def submit_payment_notification(
    order_number: str,
    file: UploadFile = File(...),
    note: str = Form(""),
):
    """Musteri: ilgili siparis icin dekont (PDF/gorsel) yukler.
    Auth gerekmez; siparis numarasi yetkilendirme anahtaridir."""
    order = await db.orders.find_one({"order_number": order_number}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Dosya 8MB'tan büyük olamaz")
    ctype = file.content_type or "application/octet-stream"
    if not (ctype.startswith("image/") or ctype == "application/pdf"):
        raise HTTPException(status_code=400, detail="Sadece PDF veya görsel yükleyebilirsiniz")
    import base64 as _b64
    now_iso = datetime.now(timezone.utc).isoformat()
    receipt = {
        "filename": (file.filename or "dekont")[:120],
        "content_type": ctype,
        "size": len(data),
        "data_b64": _b64.b64encode(data).decode("ascii"),
        "note": (note or "")[:500],
        "uploaded_at": now_iso,
    }
    upd = {
        "payment_receipt": receipt,
        "payment_notified": True,
        "payment_notified_at": now_iso,
        "updated_at": now_iso,
    }
    if order.get("status") in ("awaiting_payment", "pending"):
        upd["status"] = "payment_notified"
    await db.orders.update_one({"id": order["id"]}, {"$set": upd})

    import asyncio as _aio
    async def _notif():
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from notification_service import send_notification
            from order_statuses import get_status_config
            cfg = await get_status_config(db)
            nz = (cfg.get("notify") or {}).get("payment_notified") or {}
            ch = [c for c in ("sms", "email") if nz.get(c)]
            if not ch:
                return
            addr = order.get("shipping_address") or {}
            await send_notification(
                db, "order_payment_notified",
                to_phone=addr.get("phone") or order.get("phone"),
                to_email=addr.get("email") or order.get("email"),
                variables=await _order_notify_vars(order, order_number=order_number),
                channels=ch,
            )
        except Exception as e:
            logger.warning(f"payment_notified notif failed: {e}")
    _aio.create_task(_notif())
    return {"success": True, "message": "Ödeme bildiriminiz alındı, en kısa sürede kontrol edilecek."}


@router.get("/{order_id}/payment-receipt")
async def get_payment_receipt(order_id: str, current_user: dict = Depends(require_admin)):
    """Admin: yuklenen dekontu goruntule/indir."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0, "payment_receipt": 1})
    r = (order or {}).get("payment_receipt")
    if not r:
        raise HTTPException(status_code=404, detail="Dekont bulunamadı")
    import base64 as _b64
    raw = _b64.b64decode(r["data_b64"])
    return Response(
        content=raw,
        media_type=r.get("content_type", "application/octet-stream"),
        headers={"Content-Disposition": f'inline; filename="{r.get("filename","dekont")}"'},
    )


@router.post("/cargo/poll-now")
async def cargo_poll_now(current_user: dict = Depends(require_admin)):
    """Admin: DHL/MNG kargo durum taramasini hemen calistir (5 dk'lik job'in manuel tetigi)."""
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from scheduler import _dhl_cargo_poll_tick
        await _dhl_cargo_poll_tick()
        return {"success": True, "message": "DHL/MNG kargo taraması çalıştırıldı."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tarama hatası: {e}")


@router.get("/cargo/poll-health")
async def cargo_poll_health(current_user: dict = Depends(require_admin)):
    """Admin: DHL/MNG kargo durum taraması sağlık/izleme bilgisi.

    Ayarlar > Kargo sayfasındaki izleme paneli bu veriyi gösterir: son çalışma
    zamanı, sonuç (running/ok/skipped/error), sorgulanan/değişen sipariş sayıları,
    son hata mesajı, ortalama süre ve MNG/DHL ayarlarının aktif olup olmadığı.
    Senkron hiç çalışmadıysa status='unknown' döner (panel bunu uyarı olarak gösterir).
    """
    h = await db.settings.find_one({"id": "dhl_poll_health"}, {"_id": 0}) or {}
    mng = await _get_mng_settings()
    # Günlük limit bayrağı mng_kargo ayar dokümanında saklanır (poll + backfill ortak kullanır).
    _mng_lim = await db.settings.find_one({"id": "mng_kargo"}, {"_id": 0, "daily_limit_hit_at": 1}) or {}
    _lim_at = _mng_lim.get("daily_limit_hit_at") or ""
    _lim_today = False
    if _lim_at:
        try:
            _lim_today = datetime.fromisoformat(_lim_at).date() == datetime.now(timezone.utc).date()
        except Exception:
            _lim_today = False
    hist = list(reversed(h.get("history") or []))[:20]  # yeni → eski
    return {
        "ok": True,
        "interval_min": h.get("interval_min", 5),
        "status": h.get("status") or "unknown",
        "last_run_at": h.get("last_run_at"),
        "last_finish_at": h.get("last_finish_at"),
        "updated_at": h.get("updated_at"),
        "processed": h.get("processed", 0),
        "matched": h.get("matched", 0),
        "last_note": h.get("last_note", ""),
        "shipped": h.get("shipped", 0),
        "delivered": h.get("delivered", 0),
        "updated": h.get("updated", 0),
        "errors": h.get("errors", 0),
        "duration_ms": h.get("duration_ms", 0),
        "last_error": h.get("last_error", ""),
        "skipped_reason": h.get("skipped_reason", ""),
        "daily_limit": bool(h.get("daily_limit")) or _lim_today,
        "daily_limit_hit_at": _lim_at,
        "mng_active": bool(mng.get("is_active")),
        "mng_user_set": bool(mng.get("username")),
        "history": hist,
    }


# =============================================================================
# Faz 4 — Müşteri iadesi (14 gün) + DHL/MNG iade barkodu (3 gün geçerli)
# Veri: db.customer_returns + order.return_request (özet)
# =============================================================================
def _render_return_barcode_png_b64(code: str) -> str:
    """İade kodunu Code128 PNG (base64) barkoda çevirir (e-posta + ekran için)."""
    try:
        import io as _io, base64 as _b64
        import barcode as _bc
        from barcode.writer import ImageWriter as _IW
        c = (code or "").strip() or "IADE"
        buf = _io.BytesIO()
        _bc.get("code128", c, writer=_IW()).write(
            buf, options={"module_height": 12.0, "module_width": 0.3,
                          "font_size": 10, "text_distance": 3.5, "quiet_zone": 2.0}
        )
        return _b64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        logger.warning(f"return barcode render failed: {e}")
        return ""


def _public_return(rec: dict) -> dict:
    png = rec.get("barcode_png_b64") or ""
    return {
        "id": rec.get("id"),
        "order_number": rec.get("order_number"),
        "return_code": rec.get("return_code"),
        "status": rec.get("status"),
        "valid_until": rec.get("valid_until"),
        "cargo_provider_name": rec.get("cargo_provider_name"),
        "mng_ok": rec.get("mng_ok", False),
        "items": rec.get("items") or [],
        "reason": rec.get("reason", ""),
        "created_at": rec.get("created_at"),
        "barcode_data_url": (f"data:image/png;base64,{png}" if png else ""),
    }


async def _ensure_return_email_template():
    """İade e-posta şablonunu markalı tasarım (logo · kod · barkod · footer) ile garanti eder."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from email_layout import email_shell, info_row
    SENTINEL = "<!--facette-email-v2-->"
    body = SENTINEL + email_shell(
        icon="↩", eyebrow="İADE", title="İade talebin oluşturuldu",
        intro_html=("Merhaba {customer_name}, {order_number} numaralı siparişin için iade talebin oluşturuldu. "
                    "Ürünü en yakın DHL / MNG şubesine aşağıdaki kodu veya barkodu göstererek teslim edebilirsin."),
        body_html=(info_row("İade Kargo Kodu", "{return_code}")
                   + '<div style="text-align:center;margin-top:18px;">{return_barcode_img}</div>'),
        note_title="Bu kod 3 gün geçerlidir.",
        note_html="Son geçerlilik: {valid_until}",
        preheader="İade kargo kodun: {return_code}",
    )
    try:
        tpl = await db.notification_templates.find_one(
            {"event": "order_return_requested", "channel": "email"}, {"_id": 0}
        )
        cur = (tpl or {}).get("body") or ""
        # Eski tasarımı (veya barkodsuz/markasız olanı) yeni markalı tasarıma yükselt;
        # admin manuel düzenlediyse dokunma.
        needs_update = (not tpl) or (SENTINEL not in cur) or ("{return_barcode_img}" not in cur)
        if needs_update and not (tpl or {}).get("manually_edited"):
            await db.notification_templates.update_one(
                {"event": "order_return_requested", "channel": "email"},
                {"$set": {"event": "order_return_requested", "channel": "email", "enabled": True,
                          "subject": "İade talebin oluşturuldu · {order_number}", "body": body,
                          "updated_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
    except Exception as e:
        logger.warning(f"ensure return email tpl failed: {e}")


async def _notify_return(order: dict, code: str, valid_until: str, barcode_img: str):
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from notification_service import send_notification
        from order_statuses import get_status_config
        await _ensure_return_email_template()
        cfg = await get_status_config(db)
        nz = (cfg.get("notify") or {}).get("return_requested") or {}
        ch = [c for c in ("sms", "email") if nz.get(c)]
        if not ch:
            return
        addr = order.get("shipping_address") or {}
        try:
            vu = datetime.fromisoformat(valid_until).strftime("%d.%m.%Y %H:%M")
        except Exception:
            vu = valid_until
        await send_notification(
            db, "order_return_requested",
            to_phone=addr.get("phone") or order.get("phone"),
            to_email=addr.get("email") or order.get("email"),
            variables=await _order_notify_vars(order, return_code=code, valid_until=vu, return_barcode_img=barcode_img),
            channels=ch,
        )
    except Exception as e:
        logger.warning(f"return notif failed: {e}")


@router.post("/{order_id}/return-request")
async def create_return_request(order_id: str, payload: dict, current_user: dict = Depends(get_current_user)):
    """Müşteri: teslimden itibaren 14 gün içinde iade talebi oluşturur (sipariş + ürün seçer).
    3 gün geçerli DHL/MNG iade kargo kodu + barkod üretir, kaydeder ve bildirir."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmanız gerekiyor")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        order = await db.orders.find_one({"order_number": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    if order.get("user_id") and current_user.get("id") and order["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Bu sipariş size ait değil")

    # --- 14 gün penceresi (teslim anından itibaren, 1 sn bile geçse engelle) ---
    delivered_at = order.get("delivered_at")
    if not delivered_at:
        raise HTTPException(status_code=400, detail="Sipariş henüz teslim edilmedi; iade başlatılamaz.")
    try:
        d = datetime.fromisoformat(str(delivered_at).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
    except Exception:
        raise HTTPException(status_code=400, detail="Teslim tarihi okunamadı.")
    now = datetime.now(timezone.utc)
    if now > (d + timedelta(days=14)):
        raise HTTPException(status_code=400, detail="İade süresi (teslimden itibaren 14 gün) dolmuştur.")

    # Zaten aktif iade var mı?
    existing = await db.customer_returns.find_one(
        {"order_id": order["id"], "status": {"$in": ["created", "in_transit"]}}, {"_id": 0}
    )
    if existing:
        return {"success": True, "already": True, "return": _public_return(existing)}

    # Seçilen kalemler (index listesi) — boşsa tüm sipariş
    src_items = order.get("items") or []
    sel = payload.get("items")
    chosen = []
    if isinstance(sel, list) and sel:
        for idx in sel:
            try:
                it = src_items[int(idx)]
            except Exception:
                continue
            chosen.append(it)
    if not chosen:
        chosen = src_items
    items = [{
        "name": it.get("name") or it.get("product_name") or "Ürün",
        "size": it.get("size", ""), "color": it.get("color", ""),
        "quantity": int(it.get("quantity", 1) or 1),
        "price": float(it.get("price") or it.get("unit_price") or 0),
        "product_id": it.get("product_id") or it.get("sku") or "",
    } for it in chosen]
    reason = (payload.get("reason") or "").strip()[:500]

    rid = generate_id()
    ref = f"IADE{order.get('order_number', '')}{rid[:6]}".replace(" ", "")

    # --- İade kodu + MNG iade gönderisi (alıcı = depo/mağaza) — best-effort ---
    # Varsayılan iade kodu = anlaşmalı MNG sözleşme/müşteri no (settings.username, varsayılan 490059279).
    # Müşteri HER ZAMAN bu kodla anlaşmalı kargoya teslim edebilir. MNG API per-gönderi barkod
    # üretirse return_code bununla DEĞİŞTİRİLİR → her müşterinin iadesi ayrı barkodla takip edilir.
    return_code = "490059279"
    mng_ok = False
    cargo_name = "DHL E-Commerce"
    try:
        import sys, os, asyncio as _aio
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from mng_kargo_client import create_shipment as mng_create
        s = await _get_mng_settings()
        return_code = (str(s.get("username") or "").strip() or "490059279")
        snd = await _get_sender_info()
        if s.get("is_active") and snd.get("address") and snd.get("city"):
            res = await _aio.to_thread(
                mng_create,
                username=s["username"], password=s["password"],
                siparis_no=ref, kiymet=float(order.get("total") or 0),
                icerik=("IADE - " + "; ".join(f"{i['quantity']}x {i['name']}" for i in items))[:200],
                hizmet_sekli="NORMAL", teslim_sekli=1, al_sms=0, gn_sms=0,
                parca_list="1:1:20:30:15:;",
                alici_ad=snd["name"], odeme_sekli="GO", adres_farkli="0",
                il=snd["city"], ilce=snd.get("district", ""), adres=snd["address"],
                tel_cep=snd["phone"], email="", kapida_odeme=0,
                platform_adi="", platform_kodu="",
            )
            if res.get("ok") and res.get("barkod"):
                return_code = str(res["barkod"]).strip()
                mng_ok = True
    except Exception as e:
        logger.warning(f"return MNG create failed: {e}")

    png_b64 = _render_return_barcode_png_b64(return_code)
    now_iso = now.isoformat()
    valid_until = (now + timedelta(days=3)).isoformat()
    rec = {
        "id": rid, "order_id": order["id"], "order_number": order.get("order_number", ""),
        "user_id": order.get("user_id"), "items": items, "reason": reason,
        "return_code": return_code, "mng_ref": ref, "mng_ok": mng_ok, "cargo_provider_name": cargo_name,
        "barcode_png_b64": png_b64, "status": "created",
        "created_at": now_iso, "valid_until": valid_until,
    }
    await db.customer_returns.insert_one({**rec})
    await _log_order_event(order["id"], "return", "İade talebi oluşturuldu", current_user,
                           {"return_id": rid, "return_code": return_code},
                           order_number=order.get("order_number", ""))
    await db.orders.update_one({"id": order["id"]}, {"$set": {
        "return_request": {
            "return_id": rid, "return_code": return_code, "valid_until": valid_until,
            "created_at": now_iso, "status": "created", "items_count": len(items),
        },
        "status": "return_requested", "updated_at": now_iso,
    }})

    import os as _os, asyncio as _aio2
    base = _os.environ.get("FRONTEND_PUBLIC_URL") or _os.environ.get("REACT_APP_BACKEND_URL") or ""
    barcode_img = (
        f'<div style="margin:14px 0"><img src="{base}/api/orders/returns/{rid}/barcode.png" '
        f'alt="{return_code}" style="height:90px"/></div>' if base else ""
    )
    _aio2.create_task(_notify_return(order, return_code, valid_until, barcode_img))
    return {"success": True, "return": _public_return(rec)}


@router.post("/{order_id}/admin-return")
async def admin_manual_return(order_id: str, payload: dict = Body(default={}),
                              current_user: dict = Depends(require_admin)):
    """Admin: sipariş panelinden MANUEL (kısmi) iade.
    - payload.item_indexes: iade edilecek kalem index'leri (boşsa TÜM sipariş).
    - Seçili kalemler customer_returns'e yazılır (gider pusulası bu kayıttan üretilir → kısmi olur).
    - TÜM kalemler seçildiyse sipariş target_status'e (returned/refunded) taşınır.
    - KISMİ ise sipariş AÇIK kalır; kalem bazında iade kaydı order.partial_returns'e işlenir
      ve order.has_partial_return=True olur (eski kayıtlarda 'bir kalem iade edildi' görünür)."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        order = await db.orders.find_one({"order_number": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    src_items = order.get("items") or []
    sel = payload.get("item_indexes")
    target_status = (payload.get("target_status") or "returned").strip()
    if target_status not in ("returned", "refunded", "return_requested", "return_in_transit"):
        target_status = "returned"

    chosen, chosen_idx = [], []
    if isinstance(sel, list) and sel:
        for idx in sel:
            try:
                i = int(idx)
                chosen.append(src_items[i]); chosen_idx.append(i)
            except Exception:
                continue
    if not chosen:
        chosen = list(src_items); chosen_idx = list(range(len(src_items)))

    items = [{
        "name": it.get("name") or it.get("product_name") or "Ürün",
        "size": it.get("size", ""), "color": it.get("color", ""),
        "quantity": int(it.get("quantity", 1) or 1),
        "price": float(it.get("price") or it.get("unit_price") or 0),
        "unit_price": float(it.get("unit_price") or it.get("price") or 0),
        "discount_amount": float(it.get("discount_amount") or it.get("discount") or 0),
        "product_id": it.get("product_id") or it.get("sku") or it.get("barcode") or "",
    } for it in chosen]
    reason = (payload.get("reason") or "").strip()[:500]
    is_full = (len(src_items) > 0 and len(chosen_idx) >= len(src_items))

    rid = generate_id()
    now = datetime.now(timezone.utc); now_iso = now.isoformat()
    rec = {
        "id": rid, "order_id": order["id"], "order_number": order.get("order_number", ""),
        "user_id": order.get("user_id"), "items": items, "reason": reason,
        "return_code": f"MAN{order.get('order_number','')}{rid[:6]}".replace(" ", ""),
        "cargo_provider_name": order.get("cargo_provider_name", ""),
        "status": "returned" if target_status in ("returned", "refunded") else "created",
        "source": "admin_manual", "is_partial": (not is_full), "item_indexes": chosen_idx,
        "created_at": now_iso, "updated_at": now_iso,
    }
    await db.customer_returns.insert_one({**rec})

    if is_full:
        # Tüm kalemler iade → siparişi iade alanına taşı
        await db.orders.update_one({"id": order["id"]}, {"$set": {
            "status": target_status, "updated_at": now_iso,
            "return_request": {"return_id": rid, "status": "returned",
                               "items_count": len(items), "created_at": now_iso, "partial": False},
        }})
    else:
        # Kısmi iade → sipariş AÇIK kalır; kalem bazında iade kaydını işle
        prev = order.get("partial_returns") or []
        prev.append({"return_id": rid, "item_indexes": chosen_idx,
                     "items_count": len(items), "created_at": now_iso, "reason": reason})
        await db.orders.update_one({"id": order["id"]}, {"$set": {
            "has_partial_return": True, "partial_returns": prev, "updated_at": now_iso,
        }})

    await _log_order_event(order["id"], "return",
                           ("Tüm sipariş iade alındı (manuel)" if is_full else f"Kısmi iade (manuel): {len(items)} kalem"),
                           current_user, {"return_id": rid, "item_indexes": chosen_idx, "partial": (not is_full)},
                           order_number=order.get("order_number", ""))
    return {"success": True, "return_id": rid, "partial": (not is_full), "items_count": len(items), "is_full": is_full}


@router.get("/{order_id}/return")
async def get_return_info(order_id: str, current_user: dict = Depends(get_current_user)):
    """Müşteri: bir siparişin iade kaydını getir (ekranda barkod/kod göstermek için)."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmanız gerekiyor")
    oid = order_id
    o = await db.orders.find_one({"$or": [{"id": order_id}, {"order_number": order_id}]}, {"_id": 0, "id": 1, "user_id": 1})
    if o:
        oid = o.get("id", order_id)
        if o.get("user_id") and current_user.get("id") and o["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Bu sipariş size ait değil")
    rec = await db.customer_returns.find_one({"order_id": oid}, {"_id": 0}, sort=[("created_at", -1)])
    if not rec:
        raise HTTPException(status_code=404, detail="İade kaydı bulunamadı")
    return {"return": _public_return(rec)}


@router.get("/returns/{return_id}/barcode.png")
async def return_barcode_png(return_id: str):
    """İade barkodu PNG (e-posta <img> ve ekran için; opak return_id yetki anahtarı)."""
    rec = await db.customer_returns.find_one({"id": return_id}, {"_id": 0, "barcode_png_b64": 1})
    if not rec or not rec.get("barcode_png_b64"):
        raise HTTPException(status_code=404, detail="Barkod bulunamadı")
    import base64 as _b64
    raw = _b64.b64decode(rec["barcode_png_b64"])
    return Response(content=raw, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


# --- Admin: site iade taleplerini listele / durum güncelle ---
_RETURN_STATUS_MAP = {
    "created":     (None,                None),
    # approved/rejected bildirimleri ozel endpoint'lerde (sebep/tutar/barkod
    # degiskenleriyle) gonderilir; generic durum-degistirici burada event ATMAZ.
    "approved":    ("return_approved",   None),
    "in_transit":  ("return_in_transit", "order_return_in_transit"),
    "received":    ("returned",          "order_returned"),
    "returned":    ("returned",          "order_returned"),
    "refunded":    ("refunded",          "order_refunded"),
    "partial_refunded": ("partial_refunded", "order_partial_refunded"),
    "rejected":    ("return_rejected",   None),
    "cancelled":   ("delivered",         None),
}


@router.get("/returns/admin/list")
async def list_returns_admin(
    status: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(require_admin),
):
    q = {}
    if status:
        q["status"] = status
    rows = await db.customer_returns.find(q, {"_id": 0, "barcode_png_b64": 0}).sort("created_at", -1).to_list(length=limit)
    out = []
    for r in rows:
        o = await db.orders.find_one({"id": r.get("order_id")}, {"_id": 0, "shipping_address": 1, "status": 1}) or {}
        addr = o.get("shipping_address") or {}
        out.append({
            **r,
            "customer_name": addr.get("full_name") or f"{addr.get('first_name','')} {addr.get('last_name','')}".strip(),
            "customer_email": addr.get("email", ""),
            "customer_phone": addr.get("phone", ""),
            "order_status": o.get("status", ""),
            "barcode_url": f"/api/orders/returns/{r.get('id')}/barcode.png",
        })
    return {"returns": out}


@router.post("/returns/{return_id}/status")
async def update_return_status(return_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    rec = await db.customer_returns.find_one({"id": return_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="İade bulunamadı")
    new = (payload.get("status") or "").strip()
    if new not in _RETURN_STATUS_MAP:
        raise HTTPException(status_code=400, detail=f"Geçersiz durum. Geçerli: {list(_RETURN_STATUS_MAP)}")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.customer_returns.update_one({"id": return_id}, {"$set": {"status": new, "updated_at": now_iso}})
    order_status, event = _RETURN_STATUS_MAP[new]
    if order_status:
        _oset = {"status": order_status, "return_request.status": new, "updated_at": now_iso}
        if order_status == "return_approved":
            _oset["return_approved_at"] = now_iso
        if order_status in ("refunded", "partial_refunded"):
            _oset["refund_paid_at"] = now_iso
        await db.orders.update_one({"id": rec["order_id"]}, {"$set": _oset})
    else:
        await db.orders.update_one({"id": rec["order_id"]},
            {"$set": {"return_request.status": new, "updated_at": now_iso}})

    if event and order_status:
        import asyncio as _aio
        async def _n():
            try:
                import sys, os
                sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
                from notification_service import send_notification
                from order_statuses import get_status_config, customer_label_for
                cfg = await get_status_config(db)
                nz = (cfg.get("notify") or {}).get(order_status) or {}
                ch = [c for c in ("sms", "email") if nz.get(c)]
                if not ch:
                    return
                o = await db.orders.find_one({"id": rec["order_id"]}, {"_id": 0})
                addr = (o or {}).get("shipping_address") or {}
                await send_notification(
                    db, event,
                    to_phone=addr.get("phone") or (o or {}).get("phone"),
                    to_email=addr.get("email") or (o or {}).get("email"),
                    variables=await _order_notify_vars(o or {}, order_number=rec.get("order_number", ""), return_code=rec.get("return_code", ""), status_label=customer_label_for(order_status)),
                    channels=ch,
                )
            except Exception as e:
                logger.warning(f"return status notif failed: {e}")
        _aio.create_task(_n())
    return {"success": True, "status": new}


# ============================================================================
# Madde 3 — İade tutarı hesabı + Onay endpoint'i (P3)
# ============================================================================

async def _resolve_shipping_cost(cart_total: float):
    """db.shipping_rules'tan verilen sepet tutarına uygulanacak kargo bedelini döndürür.
    free_shipping kuralı -> 0.0 ; eşleşen kural yoksa None (bilgi yok)."""
    try:
        rules = await db.shipping_rules.find({"is_active": True}, {"_id": 0}).sort("min_cart", -1).to_list(100)
    except Exception:
        return None
    for r in rules:
        mn = r.get("min_cart", 0) or 0
        mx = r.get("max_cart") or None
        if cart_total >= mn and (not mx or cart_total <= mx):
            return 0.0 if r.get("free_shipping") else float(r.get("shipping_cost", 0) or 0)
    return None


def _round2(x):
    try:
        return round(float(x or 0) + 1e-9, 2)
    except Exception:
        return 0.0


async def _storefront_free_shipping():
    """Vitrinin kullandığı ücretsiz-kargo EŞİĞİ ve kargo ÜCRETİNİ döndürür.
    /api/settings (settings.py) ile BİREBİR aynı kaynak — böylece iade hesabı
    müşterinin checkout'ta gördüğü kargo mantığıyla tutarlı olur:
      - eşik = aktif 'otomatik' free_shipping kuponlarının en düşük min_cart_total'ı
      - ücret = default kargo firması bedeli (yoksa settings.shipping_fee)
    Değerler panelden değişebilir; sabit yazılmaz. (threshold, fee) döner."""
    s = await db.settings.find_one({"id": "main"}, {"_id": 0}) or {}
    cargo_fees = s.get("cargo_fees") or {}
    default_company = s.get("default_cargo_company") or ""
    fee = None
    if default_company and isinstance(cargo_fees, dict) and cargo_fees.get(default_company) not in (None, ""):
        try:
            fee = float(cargo_fees.get(default_company))
        except Exception:
            fee = None
    if fee is None:
        try:
            fee = float(s.get("shipping_fee"))
        except Exception:
            fee = 0.0
    fee = _round2(fee or 0.0)
    threshold = None
    try:
        async for _c in db.coupons.find(
            {"is_active": True, "free_shipping": True, "auto_apply": True},
            {"_id": 0, "min_cart_total": 1},
        ):
            mc = _c.get("min_cart_total")
            if mc in (None, ""):
                continue
            mc = float(mc)
            if threshold is None or mc < threshold:
                threshold = mc
    except Exception:
        threshold = None
    return threshold, fee


async def _compute_refund_breakdown(rec: dict, order: dict, fault: str,
                                    return_cargo_fee_override=None, returned_net_override=None):
    """İade tutarını otomatik hesaplar, şeffaf bir döküm döndürür (Karar #2 + #3).

    fault: 'customer' (müşteri kusuru -> kargo bedeli müşteriden tahsil / iadeden düşülür)
           'store'    (mağaza kusuru  -> kargo bedeli mağazadan; HİÇBİR kargo düşülmez)
    returned_net_override: kısmi iadede (panelde seçili kalemler) iade edilen net tutar.
    """
    fault = (fault or "store").lower()
    items = rec.get("items") or []
    if returned_net_override not in (None, ""):
        returned_net = _round2(returned_net_override)
    else:
        returned_net = _round2(sum(_round2(it.get("price", 0)) * int(it.get("quantity", 1) or 1) for it in items))

    orig_cart = _round2(order.get("subtotal") or order.get("total") or 0)
    kept_cart = _round2(max(0.0, orig_cart - returned_net))
    is_partial = kept_cart > 0.01  # tam iadede (kalan 0) kargo mahsubu uygulanmaz

    # --- Ücretsiz-kargo iptali (Karar #2): kısmi iade sonrası KALAN sepet, vitrindeki
    #     ücretsiz-kargo eşiğinin altına düşerse — ve SADECE müşteri kusurunda —
    #     vitrindeki kargo ücreti müşteriden tahsil edilir (iadeden düşülür).
    #     Eşik + ücret vitrinle aynı kaynaktan (settings) okunur, sabit değildir. ---
    campaign_deduction = 0.0
    campaign_note = ""
    free_threshold, ship_fee = await _storefront_free_shipping()
    if (fault == "customer" and is_partial and free_threshold is not None
            and ship_fee > 0 and orig_cart >= free_threshold and kept_cart < free_threshold):
        campaign_deduction = _round2(ship_fee)
        campaign_note = (
            f"İade sonrası kalan tutar ({kept_cart:.2f} TL) ücretsiz kargo eşiğinin "
            f"({free_threshold:.0f} TL) altına düştü; kargo bedeli ({campaign_deduction:.2f} TL) "
            f"müşteriden tahsil edildi (iadeden düşüldü)."
        )

    # --- İade kargo bedeli (Karar #3 = kusur seçimine bağlı) ---
    if return_cargo_fee_override is not None:
        return_cargo_fee = _round2(return_cargo_fee_override)
    elif fault == "customer":
        sugg = order.get("shipping_cost")
        if not sugg:
            sugg = await _resolve_shipping_cost(orig_cart) or 0
        return_cargo_fee = _round2(sugg)
    else:
        return_cargo_fee = 0.0

    # Çifte kargo tahsilatını önle: ücretsiz-kargo iptali zaten kargo bedelini
    # düşüyorsa, ayrıca iade kargo bedeli EKLEME (ikisi de aynı kargo ücretidir).
    if campaign_deduction > 0 and return_cargo_fee > 0:
        return_cargo_fee = 0.0

    auto_refund = _round2(max(0.0, returned_net - campaign_deduction - return_cargo_fee))

    return {
        "returned_net": returned_net,
        "orig_cart": orig_cart,
        "kept_cart": kept_cart,
        "is_partial": is_partial,
        "fault": fault,
        "free_shipping_threshold": free_threshold,
        "shipping_fee": ship_fee,
        "campaign_deduction": campaign_deduction,
        "campaign_note": campaign_note,
        "return_cargo_fee": return_cargo_fee,
        "auto_refund": auto_refund,
    }


@router.get("/returns/{return_id}/refund-preview")
async def refund_preview(return_id: str, fault: str = "store",
                         returned_net: Optional[float] = None,
                         current_user: dict = Depends(require_permission("returns.approve"))):
    """Onaydan ÖNCE iade tutarı dökümünü hesaplar (kaydetmez). Frontend bunu gösterir.
    returned_net: panelde seçili kalemlerin net toplamı (kısmi iade); verilmezse tüm iade."""
    rec = await db.customer_returns.find_one({"id": return_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="İade bulunamadı")
    order = await db.orders.find_one({"id": rec.get("order_id")}, {"_id": 0}) or {}
    bd = await _compute_refund_breakdown(rec, order, fault, returned_net_override=returned_net)
    return {"breakdown": bd}


@router.post("/returns/{return_id}/approve")
async def approve_return(return_id: str, payload: dict,
                         current_user: dict = Depends(require_permission("returns.approve"))):
    """İadeyi onaylar: tutarı hesaplar (kusur seçimine göre), kaydeder, durumu 'approved'
    yapar ve müşteriye bildirim gönderir. Tutar elle override edilebilir (loglanır)."""
    rec = await db.customer_returns.find_one({"id": return_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="İade bulunamadı")
    if rec.get("status") in ("refunded", "cancelled"):
        raise HTTPException(status_code=400, detail="Bu iade kapanmış; onaylanamaz.")
    order = await db.orders.find_one({"id": rec.get("order_id")}, {"_id": 0}) or {}

    fault = (payload.get("fault") or "store").lower()
    if fault not in ("customer", "store"):
        raise HTTPException(status_code=400, detail="Geçersiz kusur (customer|store).")

    cargo_override = payload.get("return_cargo_fee")
    cargo_override = None if cargo_override in (None, "") else cargo_override
    returned_net_in = payload.get("returned_net")
    returned_net_in = None if returned_net_in in (None, "") else returned_net_in
    bd = await _compute_refund_breakdown(rec, order, fault, return_cargo_fee_override=cargo_override,
                                         returned_net_override=returned_net_in)

    # Elle tutar override (Karar #5: otomatik hesap + elle düzeltme, loglanır)
    final_amount = bd["auto_refund"]
    manual_override = False
    if payload.get("refund_amount") not in (None, ""):
        try:
            final_amount = _round2(payload.get("refund_amount"))
        except Exception:
            raise HTTPException(status_code=400, detail="Geçersiz iade tutarı.")
        manual_override = abs(final_amount - bd["auto_refund"]) > 0.01

    now_iso = datetime.now(timezone.utc).isoformat()
    approval = {
        "by": current_user.get("email") or current_user.get("id"),
        "at": now_iso,
        "fault": fault,
        "auto_refund": bd["auto_refund"],
        "final_refund": final_amount,
        "manual_override": manual_override,
        "note": (payload.get("note") or "")[:500],
    }
    await db.customer_returns.update_one({"id": return_id}, {"$set": {
        "status": "approved", "fault": fault,
        "refund_breakdown": bd, "refund_amount": final_amount,
        "approval": approval, "updated_at": now_iso,
    }})
    await db.orders.update_one({"id": rec.get("order_id")}, {"$set": {
        "status": "return_approved", "return_request.status": "approved", "updated_at": now_iso,
        "return_approved_at": now_iso,
    }})

    # Bildirim: "İade Onaylandı" + tutar (kanal ayarı panelden yönetilir)
    import asyncio as _aio
    async def _n():
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from notification_service import send_notification
            from order_statuses import get_status_config, customer_label_for
            cfg = await get_status_config(db)
            nz = (cfg.get("notify") or {}).get("return_approved") or {}
            ch = [c for c in ("sms", "email") if nz.get(c)]
            if not ch:
                return
            addr = (order or {}).get("shipping_address") or {}
            await send_notification(
                db, "order_return_approved",
                to_phone=addr.get("phone") or order.get("phone"),
                to_email=addr.get("email") or order.get("email"),
                variables=await _order_notify_vars(order, order_number=rec.get("order_number", ""), return_code=rec.get("return_code", ""), refund_amount=f"{final_amount:.2f}", status_label=customer_label_for("return_approved")),
                channels=ch,
            )
        except Exception as e:
            logger.warning(f"return approve notif failed: {e}")
    _aio.create_task(_n())

    await _log_order_event(rec.get("order_id"), "return", f"İade onaylandı (₺{final_amount})", current_user,
                           {"return_id": return_id, "refund_amount": final_amount, "fault": fault},
                           order_number=rec.get("order_number", ""))
    return {"success": True, "status": "approved", "refund_amount": final_amount,
            "manual_override": manual_override, "breakdown": bd}


# ============================================================================
# Madde 3 — Ret (sebep + bildirim) + Barkod yeniden üretimi (P4)
# ============================================================================

async def _create_return_shipment(ref: str, kiymet: float, icerik: str, recipient: dict):
    """Parametrik MNG iade gönderisi (best-effort). recipient={name,phone,city,district,address}.
    MNG kapalı/eksikse veya hata olursa ref'i kod olarak döndürür (mng_ok=False)."""
    code = ref
    mng_ok = False
    try:
        import sys, os, asyncio as _aio
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from mng_kargo_client import create_shipment as mng_create
        s = await _get_mng_settings()
        if s.get("is_active") and recipient.get("address") and recipient.get("city"):
            res = await _aio.to_thread(
                mng_create,
                username=s["username"], password=s["password"],
                siparis_no=ref, kiymet=float(kiymet or 0),
                icerik=(icerik or "IADE")[:200],
                hizmet_sekli="NORMAL", teslim_sekli=1, al_sms=0, gn_sms=0,
                parca_list="1:1:20:30:15:;",
                alici_ad=recipient.get("name", ""), odeme_sekli="GO", adres_farkli="0",
                il=recipient["city"], ilce=recipient.get("district", ""), adres=recipient["address"],
                tel_cep=recipient.get("phone", ""), email="", kapida_odeme=0,
                platform_adi="", platform_kodu="",
            )
            if res.get("ok") and res.get("barkod"):
                code = str(res["barkod"]).strip()
                mng_ok = True
    except Exception as e:
        logger.warning(f"return shipment create failed: {e}")
    return code, mng_ok


async def _within_return_window(order: dict) -> bool:
    """Sipariş teslim tarihinden itibaren 14 gün içinde mi? (barkod yeniden üretimi için)"""
    delivered_at = order.get("delivered_at")
    if not delivered_at:
        return False
    try:
        d = datetime.fromisoformat(str(delivered_at).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
    except Exception:
        return False
    return datetime.now(timezone.utc) <= (d + timedelta(days=14))


@router.post("/returns/{return_id}/reissue-barcode")
async def reissue_return_barcode(return_id: str,
                                 current_user: dict = Depends(require_permission("returns.cargo_rebook"))):
    """Karar #1: barkod 3 gün geçerli; 14 gün içinde YENİDEN üretilebilir.
    Depoya iade gönderisi için yeni 3 günlük barkod üretir, kayda yazar, müşteriye bildirir."""
    rec = await db.customer_returns.find_one({"id": return_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="İade bulunamadı")
    if rec.get("status") in ("refunded", "cancelled", "rejected"):
        raise HTTPException(status_code=400, detail="Bu iade kapanmış; yeni barkod üretilemez.")
    order = await db.orders.find_one({"id": rec.get("order_id")}, {"_id": 0}) or {}
    if not await _within_return_window(order):
        raise HTTPException(status_code=400, detail="İade süresi (teslimden 14 gün) dolmuş; barkod üretilemez.")

    items = rec.get("items") or []
    ref = f"IADE{rec.get('order_number','')}{generate_id()[:6]}".replace(" ", "")
    icerik = "IADE - " + "; ".join(f"{i.get('quantity',1)}x {i.get('name','Ürün')}" for i in items)
    warehouse = await _get_sender_info()
    code, mng_ok = await _create_return_shipment(ref, order.get("total") or 0, icerik, warehouse)
    png_b64 = _render_return_barcode_png_b64(code)
    now = datetime.now(timezone.utc)
    valid_until = (now + timedelta(days=3)).isoformat()
    await db.customer_returns.update_one({"id": return_id}, {"$set": {
        "return_code": code, "mng_ref": ref, "mng_ok": mng_ok, "barcode_png_b64": png_b64,
        "valid_until": valid_until, "updated_at": now.isoformat(),
        "status": "created" if rec.get("status") in (None, "created", "in_transit") else rec.get("status"),
    }})
    await db.orders.update_one({"id": rec.get("order_id")},
        {"$set": {"return_request.return_code": code, "return_request.valid_until": valid_until,
                  "updated_at": now.isoformat()}})

    # Bildirim: yeni barkod (oluşturma şablonu ile)
    import os as _os, asyncio as _aio
    _base = _os.environ.get("FRONTEND_PUBLIC_URL") or _os.environ.get("REACT_APP_BACKEND_URL") or ""
    barcode_img = (f'<div style="margin:14px 0"><img src="{_base}/api/orders/returns/{return_id}/barcode.png" '
                   f'alt="{code}" style="height:90px"/></div>' if _base else "")
    _aio.create_task(_notify_return(order, code, valid_until, barcode_img))

    return {"success": True, "return_code": code, "mng_ok": mng_ok, "valid_until": valid_until}


@router.post("/returns/{return_id}/reject")
async def reject_return(return_id: str, payload: dict,
                        current_user: dict = Depends(require_permission("returns.reject"))):
    """İadeyi reddeder: sebep zorunlu, durum 'rejected', müşteriye SEBEP'le bildirim.
    İsteğe bağlı (reship=true): ürünü müşteriye geri göndermek için yeni kargo barkodu üretir."""
    rec = await db.customer_returns.find_one({"id": return_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="İade bulunamadı")
    if rec.get("status") in ("refunded", "cancelled"):
        raise HTTPException(status_code=400, detail="Bu iade kapanmış; reddedilemez.")
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Ret sebebi zorunludur.")
    order = await db.orders.find_one({"id": rec.get("order_id")}, {"_id": 0}) or {}
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # İsteğe bağlı: ürünü müşteriye geri gönder (yeni barkod, alıcı = müşteri)
    reship_code = ""
    if payload.get("reship"):
        addr = order.get("shipping_address") or {}
        recipient = {
            "name": addr.get("full_name") or f"{addr.get('first_name','')} {addr.get('last_name','')}".strip() or "Müşteri",
            "phone": addr.get("phone", ""), "city": addr.get("city", ""),
            "district": addr.get("district", ""), "address": addr.get("address", ""),
        }
        ref = f"RET{rec.get('order_number','')}{generate_id()[:6]}".replace(" ", "")
        reship_code, _mng = await _create_return_shipment(ref, order.get("total") or 0, "IADE RED - geri gonderim", recipient)

    rejection = {
        "by": current_user.get("email") or current_user.get("id"),
        "at": now_iso, "reason": reason, "reship_code": reship_code,
    }
    await db.customer_returns.update_one({"id": return_id}, {"$set": {
        "status": "rejected", "reject_reason": reason, "rejection": rejection,
        "reship_code": reship_code, "updated_at": now_iso,
    }})
    await db.orders.update_one({"id": rec.get("order_id")}, {"$set": {
        "status": "return_rejected", "return_request.status": "rejected", "updated_at": now_iso,
    }})

    # Bildirim: reddedildi + SEBEP (+ varsa geri-gönderim takip kodu)
    import asyncio as _aio
    async def _n():
        try:
            import sys, os as _os
            sys.path.insert(0, _os.path.dirname(_os.path.dirname(__file__)))
            from notification_service import send_notification
            from order_statuses import get_status_config, customer_label_for
            cfg = await get_status_config(db)
            nz = (cfg.get("notify") or {}).get("return_rejected") or {}
            ch = [c for c in ("sms", "email") if nz.get(c)]
            if not ch:
                return
            addr = (order or {}).get("shipping_address") or {}
            await send_notification(
                db, "order_return_rejected",
                to_phone=addr.get("phone") or order.get("phone"),
                to_email=addr.get("email") or order.get("email"),
                variables=await _order_notify_vars(order, order_number=rec.get("order_number", ""), return_code=rec.get("return_code", ""), reason=reason, reship_code=reship_code, status_label=customer_label_for("return_rejected")),
                channels=ch,
            )
        except Exception as e:
            logger.warning(f"return reject notif failed: {e}")
    _aio.create_task(_n())

    await _log_order_event(rec.get("order_id"), "return", f"İade reddedildi: {reason}", current_user,
                           {"return_id": return_id, "reason": reason},
                           order_number=rec.get("order_number", ""))
    return {"success": True, "status": "rejected", "reason": reason, "reship_code": reship_code}


# ============================================================================
# Madde 3 — Gider Pusulası (site iadeleri) (P5)
# ============================================================================

@router.post("/returns/{return_id}/gider-pusulasi")
async def site_return_gider_pusulasi(return_id: str, payload: Optional[dict] = Body(default=None),
                                     current_user: dict = Depends(require_permission("returns.expense_note"))):
    """Site iadesi için gider pusulası verisi üretir. Trendyol tarafıyla AYNI koleksiyonu
    (db.gider_pusulasi) ve AYNI numara serisini kullanır (numaralar sürekli)."""
    rec = await db.customer_returns.find_one({"id": return_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="İade bulunamadı")
    order = await db.orders.find_one({"id": rec.get("order_id")}, {"_id": 0}) or {}
    settings = await db.settings.find_one({"id": "main"}, {"_id": 0}) or {}
    company = settings.get("company_info", {}) if settings else {}

    ship = order.get("shipping_address", {}) or {}
    cust_name = (f"{ship.get('first_name','')} {ship.get('last_name','')}".strip()
                 or ship.get("full_name", "") or "Müşteri")

    items = rec.get("items", []) or []
    # Kısmi gider pusulası: yalnızca seçili kalemler (item_indexes verilirse SADECE onlar hesaplanır)
    _sel_idx = (payload or {}).get("item_indexes")
    if isinstance(_sel_idx, list) and _sel_idx:
        _filtered = []
        for _i in _sel_idx:
            try:
                _filtered.append(items[int(_i)])
            except Exception:
                continue
        if _filtered:
            items = _filtered
    total_net = _round2(sum(_round2(it.get("price", 0)) * int(it.get("quantity", 1) or 1) for it in items))
    total_gross = _round2(sum(_round2(it.get("unit_price", it.get("price", 0))) * int(it.get("quantity", 1) or 1) for it in items))
    total_discount = _round2(max(0.0, total_gross - total_net))
    vat_rate = settings.get("default_vat_rate", 10) if settings else 10
    vat_amount = round(total_net * vat_rate / (100 + vat_rate), 2)
    net_without_vat = round(total_net - vat_amount, 2)

    # ORTAK numara serisi (Trendyol + site)
    last_gp = await db.gider_pusulasi.find_one({}, sort=[("number", -1)])
    gp_number = (last_gp.get("number", 0) + 1) if last_gp else 1
    tracking_no = str((payload or {}).get("tracking_no") or "").strip()
    display_number = tracking_no if tracking_no else f"GP-{gp_number:06d}"

    gp_items = [{
        "name": it.get("name", ""),
        "barcode": it.get("product_id", "") or it.get("barcode", ""),
        "size": it.get("size", ""),
        "quantity": it.get("quantity", 1),
        "unit_price": it.get("unit_price", it.get("price", 0)),
        "discount": it.get("discount_amount", 0),
        "net_price": it.get("price", 0),
        "reason": rec.get("reason", ""),
    } for it in items]

    gider_pusulasi = {
        "number": gp_number,
        "display_number": display_number,
        "return_id": return_id,
        "source": "site",
        "order_number": rec.get("order_number", ""),
        "date": datetime.now(timezone.utc).isoformat(),
        "company": company,
        "customer": {
            "name": cust_name,
            "address": ship.get("address", ""),
            "district": ship.get("district", ""),
            "city": ship.get("city", ""),
            "country": ship.get("country", "") or "Türkiye",
        },
        "sales_invoice_no": order.get("invoice_number", ""),
        "cargo_company": rec.get("cargo_provider_name", ""),
        "sales_rep": "",
        "items": gp_items,
        "totals": {
            "gross": total_gross,
            "discount": total_discount,
            "net": total_net,
            "vat_rate": vat_rate,
            "vat_amount": vat_amount,
            "net_without_vat": net_without_vat,
        },
        "claim_reason": rec.get("reason", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.gider_pusulasi.update_one({"return_id": return_id}, {"$set": gider_pusulasi}, upsert=True)
    await db.customer_returns.update_one({"id": return_id},
        {"$set": {"has_gider_pusulasi": True, "gider_pusulasi_no": display_number}})

    return {"success": True, "gider_pusulasi": gider_pusulasi}


# ============================================================================
# Madde 3 — İade Ödemesi (refunded) — SADECE returns.refund_pay yetkisi (P6)
# ============================================================================

@router.post("/returns/{return_id}/refund-pay")
async def refund_pay_return(return_id: str, payload: Optional[dict] = Body(default=None),
                            current_user: dict = Depends(require_permission("returns.refund_pay"))):
    """İade bedelinin ödendiğini işaretler. Sadece 'returns.refund_pay' yetkisi (örn. merve).
    Durumu 'refunded' yapar, kim/ne zaman/yöntem loglanır, müşteriye bildirim gönderir."""
    rec = await db.customer_returns.find_one({"id": return_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="İade bulunamadı")
    if rec.get("status") == "refunded":
        return {"success": True, "status": "refunded", "already": True}
    if rec.get("status") in ("cancelled", "rejected"):
        raise HTTPException(status_code=400, detail="Bu iade kapanmış; ödeme yapılamaz.")
    order = await db.orders.find_one({"id": rec.get("order_id")}, {"_id": 0}) or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    method = (payload or {}).get("method") or ""  # havale | iyzico | nakit ...
    amount = rec.get("refund_amount")
    if (payload or {}).get("amount") not in (None, ""):
        try:
            amount = _round2((payload or {}).get("amount"))
        except Exception:
            raise HTTPException(status_code=400, detail="Geçersiz tutar.")
    payment = {
        "by": current_user.get("email") or current_user.get("id"),
        "at": now_iso, "method": method, "amount": amount,
        "reference": str((payload or {}).get("reference") or "").strip(),
    }
    await db.customer_returns.update_one({"id": return_id}, {"$set": {
        "status": "refunded", "refund_payment": payment,
        "refund_amount": amount if amount is not None else rec.get("refund_amount"),
        "updated_at": now_iso,
    }})
    await db.orders.update_one({"id": rec.get("order_id")}, {"$set": {
        "status": "refunded", "return_request.status": "refunded", "updated_at": now_iso,
        "refund_paid_at": now_iso,
    }})

    import asyncio as _aio
    async def _n():
        try:
            import sys, os as _os
            sys.path.insert(0, _os.path.dirname(_os.path.dirname(__file__)))
            from notification_service import send_notification
            from order_statuses import get_status_config, customer_label_for
            cfg = await get_status_config(db)
            nz = (cfg.get("notify") or {}).get("refunded") or {}
            ch = [c for c in ("sms", "email") if nz.get(c)]
            if not ch:
                return
            addr = (order or {}).get("shipping_address") or {}
            await send_notification(
                db, "order_refunded",
                to_phone=addr.get("phone") or order.get("phone"),
                to_email=addr.get("email") or order.get("email"),
                variables=await _order_notify_vars(order, order_number=rec.get("order_number", ""), return_code=rec.get("return_code", ""), refund_amount=f"{(amount or 0):.2f}", status_label=customer_label_for("refunded")),
                channels=ch,
            )
        except Exception as e:
            logger.warning(f"refund-pay notif failed: {e}")
    _aio.create_task(_n())

    return {"success": True, "status": "refunded", "amount": amount}


# ============================================================================
# Aşama 6 — Reddedilen iadeyi müşteriye GERİ gönder (reship)
# ============================================================================

@router.post("/returns/{return_id}/reship")
async def reship_return(return_id: str, payload: Optional[dict] = Body(default=None),
                        current_user: dict = Depends(require_permission("returns.cargo_rebook"))):
    """Aşama 6: Reddedilen iadede ürünü müşteriye GERİ gönderir (yeni kargo barkodu, alıcı = müşteri).
    Reddetme anında reship yapılmadıysa ya da tekrar gönderim gerekiyorsa kullanılır."""
    rec = await db.customer_returns.find_one({"id": return_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="İade bulunamadı")
    if rec.get("status") != "rejected":
        raise HTTPException(status_code=400, detail="Yalnızca reddedilmiş iadeler geri gönderilebilir.")
    order = await db.orders.find_one({"id": rec.get("order_id")}, {"_id": 0}) or {}
    addr = order.get("shipping_address") or {}
    recipient = {
        "name": addr.get("full_name") or f"{addr.get('first_name','')} {addr.get('last_name','')}".strip() or "Müşteri",
        "phone": addr.get("phone", ""), "city": addr.get("city", ""),
        "district": addr.get("district", ""), "address": addr.get("address", ""),
    }
    ref = f"RET{rec.get('order_number','')}{generate_id()[:6]}".replace(" ", "")
    reship_code, _mng = await _create_return_shipment(ref, order.get("total") or 0, "IADE RED - geri gonderim", recipient)
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.customer_returns.update_one({"id": return_id}, {"$set": {
        "reship_code": reship_code, "reshipped_at": now_iso,
        "reshipped_by": current_user.get("email") or current_user.get("id"),
        "updated_at": now_iso,
    }})
    await _log_order_event(rec.get("order_id"), "return", f"Reddedilen iade geri gönderildi: {reship_code}", current_user,
                           {"return_id": return_id, "reship_code": reship_code},
                           order_number=rec.get("order_number", ""))
    return {"success": True, "reship_code": reship_code}
