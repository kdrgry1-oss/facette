"""
=============================================================================
rooftr_returns.py — Site / iade & kısmi iade SİPARİŞLERİ (İadeler sayfası)
=============================================================================
Ticimax sipariş import'u (integrations.py /ticimax/orders/import) iade ve kısmi
iade durumundaki siparişleri `orders` koleksiyonuna `platform="ticimax"` +
status ∈ {returned, partial_refunded, refunded, return_*} olarak yazıyor.

Bu modül o siparişleri İadeler sayfasında göstermek için listeler — ödeme tipi,
durum ve tüm detayla. Durum değiştirme mevcut `PUT /api/orders/{id}/status`
endpoint'i ile yapılır (bildirim de oradan gider), burada ayrıca tanımlanmaz.

Endpoint'ler (full path):
  GET  /api/admin/rooftr/return-orders     → iade siparişleri listesi + istatistik
=============================================================================
"""
from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional
import re

from .deps import db, logger, require_admin, generate_id, _search_tr_regex
from .orders import _order_vade_farki, _order_is_efatura

router = APIRouter(prefix="/admin/rooftr", tags=["rooftr-returns"])

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
    "ticimax": "Diğer",
}


def _payment_label(method: str, raw: str = "") -> str:
    lbl = PAYMENT_LABELS.get(method or "", "")
    if lbl and lbl != "Diğer":
        return lbl
    # Bilinmeyen ama ham metin varsa onu göster
    return (raw or "").strip() or lbl or "Bilinmiyor"


@router.get("/return-orders")
async def list_rooftr_return_orders(
    status: Optional[str] = Query(None, description="Tek durum filtresi (örn. partial_refunded). Boş = tüm iade durumları"),
    payment: Optional[str] = Query(None, description="Ödeme tipi filtresi (bank_transfer/credit_card/cash_on_delivery)"),
    search: Optional[str] = Query(None, description="Sipariş no / müşteri adı / telefon araması"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=10000),  # frontend TÜMÜNÜ çeker (client-side sırala+sayfala)
    current_user: dict = Depends(require_admin),
):
    """Ticimax kaynaklı iade / kısmi iade siparişlerini listeler.

    Veri kaynağı: orders koleksiyonu, platform/source = ticimax ve
    status ∈ İade grubu. Her satır ödeme tipi (kod + okunabilir etiket) ve
    durumla döner; durumu değiştirmek için frontend PUT /api/orders/{id}/status
    çağırır.
    """
    # "Web Sitesi" iadeleri = pazaryeri (Trendyol/Hepsiburada) DISI tum siparisler.
    # Eski hali yalnizca platform/source=ticimax idi -> yeni site siparisleri (platform=facette)
    # iade/iptal edilince hicbir sekmede gorunmuyordu. Pazaryeri disi her kaynak (facette + ticimax + bos) dahil.
    # Web Sitesi iadeleri = YALNIZCA pazaryeri (Trendyol/HB) DIŞI siparişler.
    # Pazaryeri siparişleri (elle iade durumuna çekilse bile) BURAYA DÜŞMEZ; kendi
    # pazaryeri sekmesinde (Trendyol/Hepsiburada) listelenir — 'ait olduğu panel' kuralı.
    base_filter = {
        "platform": {"$nin": ["trendyol", "hepsiburada"]},
    }

    # Durum filtresi: tek durum verilmişse onu, yoksa tüm iade grubunu kullan
    if status:
        # Tek veya virgülle ayrılmış çoklu durum (örn. "refunded,partial_refunded" = 5. İade Ödemeleri hanesi)
        _st = [s.strip() for s in status.split(",") if s.strip()]
        base_filter["status"] = {"$in": _st} if len(_st) > 1 else (_st[0] if _st else {"$in": RETURN_STATUSES})
    else:
        base_filter["status"] = {"$in": RETURN_STATUSES}

    if payment:
        _pm = [x.strip() for x in str(payment).split(",") if x.strip()]
        base_filter["payment_method"] = {"$in": _pm} if len(_pm) > 1 else (_pm[0] if _pm else payment)

    if search and search.strip():
        _fields = ["order_number", "order_code",
                   "shipping_address.first_name", "shipping_address.last_name",
                   "shipping_address.full_name", "shipping_address.name",
                   "shipping_address.phone", "shipping_address.email",
                   "customer_name", "full_name"]
        _words = [w for w in search.strip().split() if w]
        if len(_words) <= 1:
            rx = {"$regex": _search_tr_regex(search.strip()), "$options": "i"}
            base_filter["$and"] = [{"$or": [{f: rx} for f in _fields]}]
        else:
            # ÇOK KELİMELİ AD-SOYAD: her kelime herhangi bir alanda geçmeli (sıra önemsiz).
            # 'büşra çe' → 'büşra' first_name'de, 'çe' last_name'de eşleşir → bulunur.
            # (Eskiden tüm ifade tek regex'ti; ad ile soyad AYRI alanlarda olduğundan hiç
            #  eşleşmiyordu → arama bozuluyordu.) Türkçe İ/ı duyarsız (_search_tr_regex).
            base_filter["$and"] = [
                {"$or": [{f: {"$regex": _search_tr_regex(w), "$options": "i"}} for f in _fields]}
                for w in _words
            ]

    total = await db.orders.count_documents(base_filter)

    proj = {
        "_id": 0, "id": 1, "order_number": 1, "order_code": 1, "ticimax_order_id": 1,
        "status": 1, "payment_method": 1, "payment_method_raw": 1, "payment_status": 1,
        "total": 1, "paid_amount": 1, "subtotal": 1, "shipping_cost": 1, "discount": 1,
        "coupon_code": 1, "notes": 1, "shipping_address": 1, "billing_address": 1,
        "customer_name": 1, "full_name": 1, "items": 1,
        "created_at": 1, "updated_at": 1, "channel_source": 1, "invoice_number": 1,
        "return_approved_at": 1, "refund_paid_at": 1, "return_request": 1,
        "cargo_tracking_number": 1, "cargo_tracking_url": 1, "cargo_provider_name": 1,
        "iyzico_retrieve_response": 1, "installment": 1, "admin_notes": 1,
        "invoice_type": 1, "billing_info": 1, "free_shipping_threshold": 1,
    }

    cursor = (
        db.orders.find(base_filter, proj)
        # En güncel iade HAREKETİ en üstte: updated_at (son değişiklik) öncelikli, sonra created_at.
        .sort([("updated_at", -1), ("created_at", -1)])
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
        # Brüt / iskonto order-seviyesinde yoksa kalemlerden türet (unit_price=brüt, price=net).
        _calc_gross = sum(round(float(i.get("unit_price") or i.get("list_price") or i.get("original_price") or i.get("price") or 0), 2) * int(i.get("quantity") or 1) for i in items)
        _calc_net = sum(round(float(i.get("price") or 0), 2) * int(i.get("quantity") or 1) for i in items)
        _calc_idisc = sum(round(float(i.get("discount_amount") or i.get("discount") or 0), 2) * int(i.get("quantity") or 1) for i in items)
        _o_sub = float(o.get("subtotal") or 0)
        _o_disc = float(o.get("discount") or 0)
        _o_total = float(o.get("total") or 0)
        _r_total = _o_total if _o_total > 0 else round(_calc_net, 2)
        _r_subtotal = _o_sub if _o_sub > 0 else round(_calc_gross, 2)
        _r_discount = _o_disc if _o_disc > 0 else (round(_calc_idisc, 2) if _calc_idisc > 0 else round(max(0.0, _r_subtotal - _r_total), 2))
        # KDV-DAHİL TABAN DÜZELTMESİ (Ali Al 398MD4734D): bazı içe-aktarılan siparişlerde
        # item.price KDV-HARİÇ, subtotal KDV-DAHİL → panelde kalem 1159,09 görünüp ara toplam
        # 2550 ile tutmuyordu. Siparişin kendi verisinden faktör: (subtotal−indirim)/Σ(item.price×adet);
        # bir KDV oranına yakınsa (1.06–1.24) kalem fiyatları KDV-dahile ölçeklenir (backend GP
        # calc ile AYNI mantık). Normal siparişler etkilenmez.
        _paid_factor = 1.0
        if _calc_net > 0.5 and _r_subtotal > 0.5:
            _pf = (_r_subtotal - _r_discount) / _calc_net
            if 1.06 <= _pf <= 1.24:
                _paid_factor = _pf
        # Taksitli ödemede iyzico'ya gerçekte tahsil edilen tutar (vade farkı DAHİL) `total`'dan
        # yüksek olabilir — iade onayında baz alınan budur (bkz. orders.py _compute_refund_breakdown).
        # Burada da gösterip admin'in panelde önceden göreceği rakamla onay sırasında hesaplanan
        # rakam tutarlı olsun diye sunuyoruz (Kadir talebi: taksitli siparişte tüm tahsilat iade edilmeli).
        _vf, _charged, _inst = _order_vade_farki(o)
        _charged_total = round(_charged, 2) if _charged > _r_total + 0.01 else _r_total
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
            "total": _r_total,
            "paid_amount": o.get("paid_amount") or 0,
            "charged_total": _charged_total,
            "vade_farki": round(max(0.0, _charged_total - _r_total), 2),
            "installment": int(_inst or 1),
            "subtotal": _r_subtotal,
            "shipping_cost": o.get("shipping_cost") or 0,
            "discount": _r_discount,
            "reason": (o.get("return_request") or {}).get("reason") or "",
            "coupon_code": o.get("coupon_code") or "",
            "notes": o.get("notes") or "",
            # Personel (admin) notlari — siparis ekranindan girilen notlar iade panelinde de gorunsun.
            "staff_notes": [
                {"text": (n or {}).get("text") or "", "by": (n or {}).get("by") or "", "at": (n or {}).get("at") or ""}
                for n in (o.get("admin_notes") or []) if (n or {}).get("text")
            ],
            "item_count": sum(int(i.get("quantity") or 1) for i in items),
            "items": [
                {
                    "name": i.get("product_name") or i.get("name") or "",
                    "qty": i.get("quantity") or 1,
                    "size": i.get("size") or "",
                    "color": i.get("color") or "",
                    "barcode": i.get("barcode") or "",
                    # KDV-dahil faktörüyle ölçekle → panel kalem fiyatları ara toplamla tutar.
                    "price": round(float(i.get("price") or 0) * _paid_factor, 2),
                    "unit_price": round(float(i.get("unit_price") or i.get("list_price") or i.get("price") or 0) * _paid_factor, 2),
                    "discount": round(float(i.get("discount_amount") or i.get("discount") or 0) * _paid_factor, 2),
                }
                for i in items
            ],
            "invoice_number": o.get("invoice_number") or "",
            "is_efatura": _order_is_efatura(o),
            "free_shipping_threshold": o.get("free_shipping_threshold"),
            "created_at": o.get("created_at") or "",
            "updated_at": o.get("updated_at") or "",
            "return_approved_at": o.get("return_approved_at") or "",
            "refund_paid_at": o.get("refund_paid_at") or "",
            "cargo_tracking_number": o.get("cargo_tracking_number") or "",
            "cargo_tracking_url": o.get("cargo_tracking_url") or "",
            "cargo_provider_name": o.get("cargo_provider_name") or "",
        })

    # KALEM BEDENİ: bazı site siparişlerinde item.size boş → barkodu ürün kataloğundaki
    # varyant bedeniyle zenginleştir (kullanıcı isteği: 'bedenleri gelmemiş, getir').
    _need_bc = list({str(it.get("barcode") or "").strip()
                     for r in rows for it in (r.get("items") or [])
                     if str(it.get("barcode") or "").strip() and not str(it.get("size") or "").strip()})
    if _need_bc:
        _bsize = {}
        async for _p in db.products.find({"variants.barcode": {"$in": _need_bc}}, {"_id": 0, "variants": 1}):
            for _v in (_p.get("variants") or []):
                _vbc = str(_v.get("barcode") or "").strip()
                if _vbc and _vbc not in _bsize:
                    _bsize[_vbc] = _v.get("size") or _v.get("beden") or ""
        for r in rows:
            for it in (r.get("items") or []):
                if not str(it.get("size") or "").strip():
                    _sz = _bsize.get(str(it.get("barcode") or "").strip())
                    if _sz:
                        it["size"] = _sz

    # İlgili customer_returns köprü kayıtları (kargo barkodu / iade kodu / reship / ödeme zamanı) — tek sorgu
    _oids = [r["id"] for r in rows if r.get("id")]
    _cr_map = {}
    if _oids:
        async for cr in db.customer_returns.find(
            {"order_id": {"$in": _oids}},
            {"_id": 0, "order_id": 1, "return_code": 1, "barcode_url": 1, "cargo_provider_name": 1,
             "iade_no": 1, "gonderi_no": 1, "mng_ref": 1, "contract_no": 1,
             "reship_code": 1, "reshipped_at": 1, "refund_payment": 1, "reason": 1,
             "has_gider_pusulasi": 1, "gider_pusulasi_no": 1,
             "status": 1, "approval": 1, "approved_item_indexes": 1, "approved_items": 1,
             "refund_breakdown": 1, "items": 1},
        ):
            _cr_map[cr.get("order_id")] = cr
    for r in rows:
        cr = _cr_map.get(r["id"]) or {}
        if cr.get("reason"):
            r["reason"] = cr["reason"]
        r["return_code"] = cr.get("return_code") or ""
        r["iade_no"] = cr.get("iade_no") or cr.get("mng_ref") or ""
        r["gonderi_no"] = cr.get("gonderi_no") or ""
        r["contract_no"] = cr.get("contract_no") or "490059279"
        r["return_barcode_url"] = cr.get("barcode_url") or ""
        r["return_cargo_provider"] = cr.get("cargo_provider_name") or r.get("cargo_provider_name") or ""
        r["reship_code"] = cr.get("reship_code") or ""
        r["reshipped_at"] = cr.get("reshipped_at") or ""
        r["has_gider_pusulasi"] = bool(cr.get("has_gider_pusulasi"))
        r["gider_pusulasi_no"] = cr.get("gider_pusulasi_no") or ""
        # ONAY GEÇMİŞİ: hangi kalemler onaylanmış + kargo mahsubu — approved satırlarda
        # kutucuklar bu seçimle ÖNİŞARETLİ ve READ-ONLY gösterilir (yalnız muhasebe/admin
        # "Düzenle" ile açar). approved_item_indexes yoksa (tam onay) tüm kalemler onaylı sayılır.
        _cr_status = str(cr.get("status") or "")
        _appr = cr.get("approval") or {}
        _is_approved = bool(_appr) or _cr_status in ("approved", "return_approved", "refunded", "partial_refunded") \
            or r.get("status") in ("return_approved", "refunded", "partial_refunded")
        r["return_is_approved"] = _is_approved
        # KRİTİK: panel r["items"] = SİPARİŞİN TÜM kalemleri; customer_returns.items = GERÇEKTE
        # İADE EDİLEN kalemler (alt küme olabilir). "Tam onay" = iadenin TÜM kalemleri, siparişin
        # tümü DEĞİL. W10205: 2 kalemli siparişte yalnız M iade edildi; eski kod range(2) yazıp
        # her ikisini onaylı gösteriyordu. Burada iade kalemlerini sipariş-index'ine eşliyoruz.
        _order_items = r.get("items") or []
        _ret_items = cr.get("items") or []

        def _match_order_idx(ri):
            _bc = str(ri.get("barcode") or ri.get("product_id") or "").strip()
            if _bc:
                for _i, _oi in enumerate(_order_items):
                    if str(_oi.get("barcode") or "").strip() == _bc:
                        return _i
            _nm = str(ri.get("name") or "").strip().lower()
            _sz = str(ri.get("size") or "").strip().lower()
            for _i, _oi in enumerate(_order_items):
                if str(_oi.get("name") or "").strip().lower() == _nm and \
                   str(_oi.get("size") or "").strip().lower() == _sz:
                    return _i
            # beden bilgisi yoksa yalnız ada göre (tek eşleşme varsa)
            _cands = [_i for _i, _oi in enumerate(_order_items)
                      if str(_oi.get("name") or "").strip().lower() == _nm]
            return _cands[0] if len(_cands) == 1 else None

        _ap_idx = cr.get("approved_item_indexes")
        if _is_approved:
            # Onaylanan İADE kalemleri (kısmi onayda alt küme; yoksa iadenin tümü)
            if isinstance(_ap_idx, list) and _ap_idx:
                _appr_ret = [_ret_items[i] for i in _ap_idx if 0 <= i < len(_ret_items)]
            else:
                _appr_ret = _ret_items
            _idxs = []
            for _ri in _appr_ret:
                _mi = _match_order_idx(_ri)
                if _mi is not None and _mi not in _idxs:
                    _idxs.append(_mi)
            r["approved_item_indexes"] = _idxs
            r["approved_full"] = bool(_idxs) and len(_idxs) == len(_order_items)
        else:
            r["approved_item_indexes"] = []
            r["approved_full"] = False
        # Kargo mahsubu onayda uygulandı mı? refund_breakdown.cargo.mode=="deducted"
        _rb_cargo = (cr.get("refund_breakdown") or {}).get("cargo") or {}
        r["approved_cargo_deducted"] = bool(_is_approved and _rb_cargo.get("mode") == "deducted")
        r["approval_by"] = _appr.get("by") or ""
        r["approval_at"] = _appr.get("at") or r.get("return_approved_at") or ""
        r["approval_note"] = _appr.get("note") or ""
        # İade ödeme tarihi: sipariş damgası > köprü ödeme zamanı > (refunded ise) updated_at
        if not r.get("refund_paid_at"):
            _rp = (cr.get("refund_payment") or {}).get("at")
            r["refund_paid_at"] = _rp or (r.get("updated_at") if r.get("status") in ("refunded", "partial_refunded") else "")

    # İstatistik: tüm iade grubunda durum + ödeme dağılımı (mevcut filtreden bağımsız,
    # pazaryeri DISI tum site siparisleri) — sekmedeki rozetler için
    stat_filter = {"platform": {"$nin": ["trendyol", "hepsiburada"]},
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

    # Ücretsiz-kargo siparişlerinde kısmi iade mahsubu için standart kargo ücreti
    # (vitrin/checkout ile AYNI kaynak: settings.cargo_fees[default] → settings.shipping_fee)
    _free_ship_fee = 0.0
    _free_ship_threshold = 0.0
    try:
        _s = await db.settings.find_one(
            {"id": "main"},
            {"_id": 0, "cargo_fees": 1, "default_cargo_company": 1, "shipping_fee": 1,
             "free_shipping_threshold": 1},
        ) or {}
        _cf = _s.get("cargo_fees") or {}
        _dc = _s.get("default_cargo_company") or ""
        if _dc and isinstance(_cf, dict) and _cf.get(_dc) not in (None, ""):
            _free_ship_fee = float(_cf.get(_dc))
        elif _s.get("shipping_fee") not in (None, ""):
            _free_ship_fee = float(_s.get("shipping_fee"))
        if _s.get("free_shipping_threshold") not in (None, ""):
            _free_ship_threshold = float(_s.get("free_shipping_threshold"))
    except Exception:
        _free_ship_fee = 0.0

    return {
        "success": True,
        "orders": rows,
        "free_ship_fee": round(_free_ship_fee or 0, 2),
        "free_shipping_threshold": round(_free_ship_threshold or 0, 2),
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
    # [ticimax-off 2026-06-22] Ticimax SOAP entegrasyonu kapatildi; bu uc devre disi.
    return {"success": False, "message": "Ticimax tarih senkronu kapatildi."}


# ============================================================================
# EXPORT — İade siparişlerini Excel (.xlsx) indir (görseldeki kolon düzeni)
# ============================================================================
@router.get("/return-orders/export")
async def export_rooftr_return_orders(
    status: Optional[str] = Query(None),
    payment: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: dict = Depends(require_admin),
):
    """İade siparişlerini listelemeyle AYNI filtrelerle Excel'e aktarır.
    Kolonlar: Ürün Adı | Tutar | Sipariş Tarihi | Sipariş ID | Sipariş No |
    Ad Soyad | Durum | Kaynak | Ödeme Tipi."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from fastapi.responses import StreamingResponse
    try:
        from order_statuses import ORDER_STATUS_CATALOG
        status_label = {s["key"]: (s.get("label") or s["key"]) for s in ORDER_STATUS_CATALOG}
    except Exception:
        status_label = {}

    base_filter = {"$or": [{"platform": "ticimax"}, {"source": "ticimax"}]}
    if status:
        _st = [s.strip() for s in status.split(",") if s.strip()]
        base_filter["status"] = {"$in": _st} if len(_st) > 1 else (_st[0] if _st else {"$in": RETURN_STATUSES})
    else:
        base_filter["status"] = {"$in": RETURN_STATUSES}
    if payment:
        _pm = [x.strip() for x in str(payment).split(",") if x.strip()]
        base_filter["payment_method"] = {"$in": _pm} if len(_pm) > 1 else (_pm[0] if _pm else payment)
    if search:
        s = re.escape(search.strip())
        rx = {"$regex": s, "$options": "i"}
        base_filter["$and"] = [{
            "$or": [
                {"order_number": rx}, {"order_code": rx},
                {"shipping_address.first_name": rx}, {"shipping_address.last_name": rx},
                {"shipping_address.phone": rx}, {"shipping_address.email": rx},
            ]
        }]

    proj = {
        "_id": 0, "id": 1, "order_number": 1, "ticimax_order_id": 1, "status": 1,
        "payment_method": 1, "payment_method_raw": 1, "total": 1,
        "shipping_address": 1, "billing_address": 1, "customer_name": 1, "full_name": 1,
        "items": 1, "created_at": 1, "channel_source": 1,
    }

    wb = Workbook()
    ws = wb.active
    ws.title = "İade Siparişleri"
    headers = ["Ürün Adı", "Tutar", "Sipariş Tarihi", "Sipariş ID", "Sipariş No",
               "Ad Soyad", "Durum", "Kaynak", "Ödeme Tipi"]
    ws.append(headers)
    hfill = PatternFill("solid", fgColor="FCE4B6")
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = hfill
        c.alignment = Alignment(horizontal="center", vertical="center")

    cursor = db.orders.find(base_filter, proj).sort("created_at", -1)
    async for o in cursor:
        addr = o.get("shipping_address") or {}
        bill = o.get("billing_address") or {}
        name = (" ".join([addr.get("first_name") or "", addr.get("last_name") or ""]).strip()
                or addr.get("full_name") or addr.get("name")
                or o.get("customer_name") or o.get("full_name")
                or " ".join([bill.get("first_name") or "", bill.get("last_name") or ""]).strip()
                or bill.get("name") or "")
        items = o.get("items") or []
        urun = ", ".join([
            (i.get("product_name") or i.get("name") or "").strip()
            for i in items if (i.get("product_name") or i.get("name"))
        ])
        st = o.get("status") or ""
        ws.append([
            urun,
            float(o.get("total") or 0),
            str(o.get("created_at") or "")[:10],
            o.get("id") or "",
            o.get("order_number") or "",
            name,
            status_label.get(st, st),
            o.get("channel_source") or "Ticimax",
            _payment_label(o.get("payment_method") or "", o.get("payment_method_raw") or ""),
        ])

    widths = [42, 12, 14, 16, 14, 24, 18, 12, 16]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = w

    # GÜVENLİK: Excel/CSV formül injection — = + - @ ile başlayan metin hücrelerini kaçışla
    for _ws in wb.worksheets:
        for _row in _ws.iter_rows():
            for _c in _row:
                if isinstance(_c.value, str) and _c.value[:1] in ("=", "+", "-", "@", "\t", "\r"):
                    _c.value = "'" + _c.value
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=iade-siparisleri.xlsx"},
    )


# ============================================================================
# BRIDGE — Ticimax iade siparişini zengin iade akışına (customer_returns) bağlar
# ============================================================================
@router.post("/returns/{order_id}/open")
async def open_rooftr_return(order_id: str, current_user: dict = Depends(require_admin)):
    """Ticimax iade siparişinden, zengin iade akışı (onayla/reddet/gider/öde) için bir
    `customer_returns` köprü kaydı üretir. İDEMPOTENT: zaten varsa mevcut return_id'yi döndürür.
    PARA/İŞLEM YAPMAZ — sadece köprü kaydını oluşturur. Sonraki adımlar mevcut
    /api/orders/returns/{return_id}/{refund-preview,approve,reject,gider-pusulasi,refund-pay}
    endpoint'leriyle yürür (RBAC + bildirim oralarda)."""
    from datetime import datetime, timezone
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    # İdempotent: bu siparişe ait köprü kaydı zaten varsa onu döndür.
    # ONARIM: eski kayıtta items hiç yazılmamışsa (boş) sipariş kalemleriyle doldur —
    # gider pusulası/iade akışları kalemleri bu kayıttan okur, boş kayıt kısmi seçimi bozar.
    existing = await db.customer_returns.find_one(
        {"order_id": order_id, "status": {"$ne": "expired"}},
        {"_id": 0, "id": 1, "status": 1, "items": 1})
    if existing:
        if not (existing.get("items") or []):
            _src = order.get("items") or []
            _fix = [{
                "name": it.get("product_name") or it.get("name") or "Ürün",
                "size": it.get("size", "") or "",
                "color": it.get("color", "") or "",
                "quantity": int(it.get("quantity", 1) or 1),
                "price": float(it.get("price") or it.get("unit_price") or 0),
                "unit_price": float(it.get("unit_price") or it.get("price") or 0),
                "product_id": it.get("barcode") or it.get("product_id") or it.get("sku") or "",
            } for it in _src]
            if _fix:
                await db.customer_returns.update_one(
                    {"id": existing.get("id")}, {"$set": {"items": _fix}})
        return {"success": True, "return_id": existing.get("id"),
                "status": existing.get("status"), "created": False}

    # Sipariş kalemlerini customer_returns şemasına eşle
    src = order.get("items") or []
    items = [{
        "name": it.get("product_name") or it.get("name") or "Ürün",
        "size": it.get("size", "") or "",
        "color": it.get("color", "") or "",
        "quantity": int(it.get("quantity", 1) or 1),
        "price": float(it.get("price") or it.get("unit_price") or 0),
        "unit_price": float(it.get("unit_price") or it.get("price") or 0),
        "product_id": it.get("barcode") or it.get("product_id") or it.get("sku") or "",
    } for it in src]

    # Sipariş durumu → customer_returns durumu
    _map = {
        "return_requested": "created", "return_approved": "approved",
        "return_in_transit": "in_transit", "returned": "received",
        "refunded": "refunded", "partial_refunded": "refunded",
        "return_rejected": "rejected",
    }
    cr_status = _map.get(order.get("status"), "created")

    rid = generate_id()
    rr = order.get("return_request") or {}
    rec = {
        "id": rid, "order_id": order_id, "order_number": order.get("order_number", ""),
        "user_id": order.get("user_id"), "items": items, "reason": "",
        "return_code": rr.get("return_code", "") or "", "mng_ok": False,
        "cargo_provider_name": order.get("cargo_provider_name", "") or "",
        "status": cr_status, "source": "ticimax_bridge",
        "created_at": order.get("created_at") or datetime.now(timezone.utc).isoformat(),
    }
    await db.customer_returns.insert_one({**rec})
    await db.orders.update_one({"id": order_id},
                               {"$set": {"return_request.return_id": rid}})
    return {"success": True, "return_id": rid, "status": cr_status, "created": True}
