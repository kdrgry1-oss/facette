"""
=============================================================================
ticimax_returns.py — Ticimax iade / kısmi iade SİPARİŞLERİ (İadeler sayfası)
=============================================================================
Ticimax sipariş import'u (integrations.py /ticimax/orders/import) iade ve kısmi
iade durumundaki siparişleri `orders` koleksiyonuna `platform="ticimax"` +
status ∈ {returned, partial_refunded, refunded, return_*} olarak yazıyor.

Bu modül o siparişleri İadeler sayfasında göstermek için listeler — ödeme tipi,
durum ve tüm detayla. Durum değiştirme mevcut `PUT /api/orders/{id}/status`
endpoint'i ile yapılır (bildirim de oradan gider), burada ayrıca tanımlanmaz.

Endpoint'ler (full path):
  GET  /api/admin/ticimax/return-orders     → iade siparişleri listesi + istatistik
=============================================================================
"""
from fastapi import APIRouter, Query, Depends
from typing import Optional
import re

from .deps import db, logger, require_admin

router = APIRouter(prefix="/admin/ticimax", tags=["ticimax-returns"])

# İade sürecindeki tüm sipariş durumları (order_statuses.py "İade" grubu)
RETURN_STATUSES = [
    "return_requested", "return_approved", "return_rejected",
    "return_in_transit", "returned", "refunded", "partial_refunded",
]

# Ödeme tipi kodu → okunabilir Türkçe etiket
PAYMENT_LABELS = {
    "bank_transfer": "Havale / EFT",
    "credit_card": "Kredi Kartı",
    "cash_on_delivery": "Kapıda Ödeme",
    "cod_card": "Kapıda Kredi Kartı",
    "ticimax": "Diğer (Ticimax)",
}


def _payment_label(method: str, raw: str = "") -> str:
    lbl = PAYMENT_LABELS.get(method or "", "")
    if lbl and lbl != "Diğer (Ticimax)":
        return lbl
    # Bilinmeyen ama ham metin varsa onu göster
    return (raw or "").strip() or lbl or "Bilinmiyor"


@router.get("/return-orders")
async def list_ticimax_return_orders(
    status: Optional[str] = Query(None, description="Tek durum filtresi (örn. partial_refunded). Boş = tüm iade durumları"),
    payment: Optional[str] = Query(None, description="Ödeme tipi filtresi (bank_transfer/credit_card/cash_on_delivery)"),
    search: Optional[str] = Query(None, description="Sipariş no / müşteri adı / telefon araması"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_admin),
):
    """Ticimax kaynaklı iade / kısmi iade siparişlerini listeler.

    Veri kaynağı: orders koleksiyonu, platform/source = ticimax ve
    status ∈ İade grubu. Her satır ödeme tipi (kod + okunabilir etiket) ve
    durumla döner; durumu değiştirmek için frontend PUT /api/orders/{id}/status
    çağırır.
    """
    base_filter = {
        "$or": [{"platform": "ticimax"}, {"source": "ticimax"}],
    }

    # Durum filtresi: tek durum verilmişse onu, yoksa tüm iade grubunu kullan
    if status:
        # Artık herhangi bir sipariş durumuyla filtrelenebilir (yalnız iade grubuyla sınırlı değil)
        base_filter["status"] = status
    else:
        base_filter["status"] = {"$in": RETURN_STATUSES}

    if payment:
        base_filter["payment_method"] = payment

    if search:
        s = re.escape(search.strip())
        rx = {"$regex": s, "$options": "i"}
        base_filter["$and"] = [{
            "$or": [
                {"order_number": rx},
                {"order_code": rx},
                {"shipping_address.first_name": rx},
                {"shipping_address.last_name": rx},
                {"shipping_address.phone": rx},
                {"shipping_address.email": rx},
            ]
        }]

    total = await db.orders.count_documents(base_filter)

    proj = {
        "_id": 0, "id": 1, "order_number": 1, "order_code": 1, "ticimax_order_id": 1,
        "status": 1, "payment_method": 1, "payment_method_raw": 1, "payment_status": 1,
        "total": 1, "paid_amount": 1, "subtotal": 1, "shipping_cost": 1, "discount": 1,
        "coupon_code": 1, "notes": 1, "shipping_address": 1, "billing_address": 1,
        "customer_name": 1, "full_name": 1, "items": 1,
        "created_at": 1, "updated_at": 1, "channel_source": 1, "invoice_number": 1,
    }

    cursor = (
        db.orders.find(base_filter, proj)
        .sort("created_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )

    rows = []
    async for o in cursor:
        addr = o.get("shipping_address") or {}
        bill = o.get("billing_address") or {}
        name = (" ".join([addr.get("first_name") or "", addr.get("last_name") or ""]).strip()
                or addr.get("full_name") or addr.get("name")
                or o.get("customer_name") or o.get("full_name")
                or " ".join([bill.get("first_name") or "", bill.get("last_name") or ""]).strip()
                or bill.get("name") or "—")
        items = o.get("items") or []
        rows.append({
            "id": o.get("id"),
            "order_number": o.get("order_number"),
            "ticimax_order_id": o.get("ticimax_order_id"),
            "customer_name": name,
            "phone": addr.get("phone") or "",
            "email": addr.get("email") or "",
            "address": addr.get("address") or "",
            "city": addr.get("city") or "",
            "district": addr.get("district") or "",
            "status": o.get("status"),
            "payment_method": o.get("payment_method") or "",
            "payment_label": _payment_label(o.get("payment_method") or "", o.get("payment_method_raw") or ""),
            "payment_method_raw": o.get("payment_method_raw") or "",
            "payment_status": o.get("payment_status") or "",
            "total": o.get("total") or 0,
            "paid_amount": o.get("paid_amount") or 0,
            "subtotal": o.get("subtotal") or 0,
            "shipping_cost": o.get("shipping_cost") or 0,
            "discount": o.get("discount") or 0,
            "coupon_code": o.get("coupon_code") or "",
            "notes": o.get("notes") or "",
            "item_count": sum(int(i.get("quantity") or 1) for i in items),
            "items": [
                {
                    "name": i.get("product_name") or "",
                    "qty": i.get("quantity") or 1,
                    "size": i.get("size") or "",
                    "color": i.get("color") or "",
                    "barcode": i.get("barcode") or "",
                    "price": i.get("price") or 0,
                }
                for i in items
            ],
            "invoice_number": o.get("invoice_number") or "",
            "created_at": o.get("created_at") or "",
            "updated_at": o.get("updated_at") or "",
        })

    # İstatistik: tüm iade grubunda durum + ödeme dağılımı (mevcut filtreden bağımsız,
    # sadece ticimax kaynağına bağlı) — sekmedeki rozetler için
    stat_filter = {"$or": [{"platform": "ticimax"}, {"source": "ticimax"}],
                   "status": {"$in": RETURN_STATUSES}}
    status_counts = {}
    payment_counts = {}
    try:
        async for grp in db.orders.aggregate([
            {"$match": stat_filter},
            {"$group": {"_id": "$status", "n": {"$sum": 1}}},
        ]):
            status_counts[grp["_id"]] = grp["n"]
        async for grp in db.orders.aggregate([
            {"$match": stat_filter},
            {"$group": {"_id": "$payment_method", "n": {"$sum": 1}}},
        ]):
            payment_counts[grp["_id"] or "bilinmiyor"] = grp["n"]
    except Exception as e:
        logger.warning(f"[ticimax-returns] stats hatası: {e}")

    return {
        "success": True,
        "orders": rows,
        "total": total,
        "page": page,
        "limit": limit,
        "status_counts": status_counts,
        "payment_counts": payment_counts,
        "total_returns": sum(status_counts.values()),
    }


@router.post("/orders/refresh-dates")
async def refresh_order_dates(
    page: int = Query(1, ge=1),
    per_pages: int = Query(5, ge=1, le=15),
    current_user: dict = Depends(require_admin),
):
    """Siparişlerin created_at'ini Ticimax'taki gerçek SiparisTarihi'ne çeker.

    Zaman aşımına takılmamak için her çağrıda `per_pages` sayfa (100'er kayıt)
    işler. Frontend, has_more=False dönene kadar page'i artırarak döngüyle çağırır.
    """
    import asyncio
    from datetime import datetime, timezone
    try:
        from ticimax_client import get_orders as tc_get_orders
    except Exception as e:
        return {"success": False, "message": f"Ticimax client yüklenemedi: {e}"}

    fixed = 0
    scanned = 0
    reached_end = False
    for i in range(per_pages):
        pno = page + i
        try:
            batch = tc_get_orders(page=pno, page_size=100,
                                  exclude_marketplace=False, only_with_phone=False)
        except Exception as e:
            logger.warning(f"[refresh-dates] sayfa {pno} çekilemedi: {e}")
            batch = []
        if not batch:
            reached_end = True
            break
        for o in batch:
            if not o:
                continue
            scanned += 1
            tid = o.get("SiparisID") or o.get("ID")
            d = o.get("SiparisTarihi") or o.get("SiparisTarih") or o.get("Tarih")
            if not tid or not d:
                continue
            try:
                iso = d.isoformat() if hasattr(d, "isoformat") else str(d)
                tid_int = int(tid)
            except Exception:
                continue
            try:
                r = await db.orders.update_one(
                    {"ticimax_order_id": tid_int},
                    {"$set": {"created_at": iso,
                              "updated_at": datetime.now(timezone.utc).isoformat()}},
                )
                if r.modified_count:
                    fixed += 1
            except Exception as ie:
                logger.warning(f"[refresh-dates] update hata {tid_int}: {ie}")
        await asyncio.sleep(0.4)

    return {
        "success": True,
        "fixed": fixed,
        "scanned": scanned,
        "next_page": page + per_pages,
        "has_more": (not reached_end),
    }
