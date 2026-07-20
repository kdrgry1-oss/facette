"""
Reports module — aggregated analytics for admin dashboard.

Endpoints (all admin-protected):
  GET /api/admin/reports/sales?start_date=&end_date=&group_by=day|week|month
  GET /api/admin/reports/products/top?limit=20
  GET /api/admin/reports/categories
  GET /api/admin/reports/members
  GET /api/admin/reports/stock
  GET /api/admin/reports/cargo
  GET /api/admin/reports/payments
"""
from fastapi import APIRouter, Depends, Query
from datetime import datetime, timezone, timedelta
from typing import Optional

from .deps import db, require_admin, tr_range_to_utc


router = APIRouter(prefix="/admin/reports", tags=["admin-reports"])


def _iso_range(start: Optional[str], end: Optional[str], days_default: int = 30):
    # Seçilen tarihler TÜRKİYE yerel günü kabul edilir (00:00–23:59:59.999 +03:00) ve UTC ISO
    # sınırına çevrilir → bitiş günü tam dahil olur, saat-dilimi kayması OLMAZ. (deps.tr_range_to_utc)
    if start and end:
        return tr_range_to_utc(start, end)
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=days_default)).isoformat(), now.isoformat()


# Pazaryeri kaynakları — Site dışı her şey. (platform VEYA marketplace alanında durabilir;
# örn. Temu siparişleri yalnız marketplace="temu" taşır, platform boş olabilir.)
_MARKETPLACES = ["trendyol", "hepsiburada", "temu"]

# Ciro/sipariş tutarlarına DAHİL EDİLMEYECEK durumlar: iptal + iade grubu.
# return_rejected (iade reddedildi) HARİÇ — satış geçerli sayıldığı için ciroda kalır.
_EXCLUDED_STATUSES = [
    "cancelled",
    "return_requested", "return_approved", "return_in_transit",
    "returned", "refunded", "partial_refunded",
]


def _source_cond(source: Optional[str]) -> dict:
    """Rapor kaynak filtresi → Mongo koşulu.
    'all'/boş = toplu (filtre yok). 'site' = pazaryeri olmayan tüm siparişler.
    'trendyol'/'hepsiburada'/'temu' = ilgili pazaryeri (platform VEYA marketplace).
    """
    s = (source or "all").strip().lower()
    if s in ("", "all", "toplu", "hepsi", "tum", "tümü"):
        return {}
    if s in ("site", "facette", "web", "kendi"):
        # Site = pazaryeri olmayan: platform da marketplace da pazaryeri listesinde DEĞİL
        # (alan hiç yoksa $nin yine eşleşir → boş platform site sayılır).
        return {"platform": {"$nin": _MARKETPLACES}, "marketplace": {"$nin": _MARKETPLACES}}
    if s in ("trendyol", "ty"):
        return {"$or": [{"platform": "trendyol"}, {"marketplace": "trendyol"}]}
    if s in ("hepsiburada", "hb"):
        return {"$or": [{"platform": "hepsiburada"}, {"marketplace": "hepsiburada"}]}
    if s == "temu":
        return {"$or": [{"platform": "temu"}, {"marketplace": "temu"}]}
    return {}  # bilinmeyen kaynak → toplu


def _collection_from_code(*codes) -> str:
    """Stok kodu ön ekinden koleksiyon türetir: 'fcfw…' → FcFw (Sonbahar/Kış),
    'fcss…' → FCss (İlkbahar/Yaz). Büyük/küçük harf duyarsız; ilk eşleşen kod kazanır."""
    for c in codes:
        cc = (str(c) if c is not None else "").strip().lower()
        if cc.startswith("fcfw"):
            return "FcFw"
        if cc.startswith("fcss"):
            return "FCss"
    return ""


def _base_match(s: str, e: str, source: Optional[str] = None) -> dict:
    """Tüm satış raporlarının ortak $match'i: tarih aralığı + iptal/iade hariç + kaynak."""
    m = {"created_at": {"$gte": s, "$lte": e}, "status": {"$nin": _EXCLUDED_STATUSES}}
    sc = _source_cond(source)
    if sc:
        m.update(sc)
    return m


@router.get("/sales-summary")
async def sales_summary(current_user: dict = Depends(require_admin)):
    """Genel Satış Özeti (anlık dashboard bloğu) — TR yerel güne göre:
    bugünkü ciro (iptal+iade DAHİL brüt), dünle karşılaştırma, hafta/ay/yıl cirosu,
    bugünkü sipariş adedi, satılan ürün adedi (adet toplamı), ortalama sepet,
    sipariş başına ürün adedi, iade tutarı, iptal tutarı, net satış (iptal+iade hariç)."""
    _tr = timedelta(hours=3)
    now_tr = datetime.now(timezone.utc) + _tr
    day0 = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)

    def _u(dt_tr):  # TR yerel → UTC ISO (orders.created_at UTC saklanır)
        return (dt_tr - _tr).isoformat()

    _RETURN_ST = ["return_requested", "return_approved", "return_in_transit",
                  "returned", "refunded", "partial_refunded"]
    _CANCEL_ST = ["cancelled", "cancel_refunded"]

    async def _agg(s_iso: str, e_iso: str) -> dict:
        pipe = [
            {"$match": {"created_at": {"$gte": s_iso, "$lt": e_iso}}},
            {"$group": {
                "_id": None,
                "revenue_all": {"$sum": {"$ifNull": ["$total", 0]}},
                "cancel_total": {"$sum": {"$cond": [{"$in": ["$status", _CANCEL_ST]}, {"$ifNull": ["$total", 0]}, 0]}},
                "return_total": {"$sum": {"$cond": [{"$in": ["$status", _RETURN_ST]}, {"$ifNull": ["$total", 0]}, 0]}},
                "net_revenue": {"$sum": {"$cond": [{"$in": ["$status", _CANCEL_ST + _RETURN_ST]}, 0, {"$ifNull": ["$total", 0]}]}},
                "net_orders": {"$sum": {"$cond": [{"$in": ["$status", _CANCEL_ST + _RETURN_ST]}, 0, 1]}},
                "items_sold": {"$sum": {"$cond": [
                    {"$in": ["$status", _CANCEL_ST + _RETURN_ST]}, 0,
                    {"$sum": {"$map": {"input": {"$ifNull": ["$items", []]}, "as": "it",
                                       "in": {"$ifNull": ["$$it.quantity", 1]}}}}]}},
            }},
        ]
        r = await db.orders.aggregate(pipe).to_list(1)
        d = r[0] if r else {}
        return {
            "revenue": round(float(d.get("revenue_all") or 0), 2),
            "net": round(float(d.get("net_revenue") or 0), 2),
            "cancels": round(float(d.get("cancel_total") or 0), 2),
            "returns": round(float(d.get("return_total") or 0), 2),
            "orders": int(d.get("net_orders") or 0),
            "items": int(d.get("items_sold") or 0),
        }

    now_iso = _u(now_tr)
    today = await _agg(_u(day0), now_iso)
    yesterday = await _agg(_u(day0 - timedelta(days=1)), _u(day0))
    week = await _agg(_u(day0 - timedelta(days=day0.weekday())), now_iso)
    month = await _agg(_u(day0.replace(day=1)), now_iso)
    year = await _agg(_u(day0.replace(month=1, day=1)), now_iso)

    _cmp = None
    if yesterday["revenue"] > 0:
        _cmp = round((today["revenue"] - yesterday["revenue"]) / yesterday["revenue"] * 100, 1)
    return {
        "today": {
            **today,
            "aov": round(today["net"] / today["orders"], 2) if today["orders"] else 0,
            "items_per_order": round(today["items"] / today["orders"], 2) if today["orders"] else 0,
        },
        "yesterday": yesterday,
        "vs_yesterday_pct": _cmp,
        "week_revenue": week["revenue"],
        "month_revenue": month["revenue"],
        "year_revenue": year["revenue"],
        "as_of": now_iso,
    }


@router.get("/sales-by-hour")
async def sales_by_hour(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = Query(None),
    current_user: dict = Depends(require_admin),
):
    """Saat Analizi (00-24, TR saati): hangi saatlerde satış geliyor — sipariş + ciro.
    Reklam planlaması için zirve saat aralığı da döner."""
    s, e = _iso_range(start_date, end_date)
    pipeline = [
        {"$match": _base_match(s, e, source)},
        {"$addFields": {"_d": {"$dateFromString": {"dateString": "$created_at", "onError": None}}}},
        {"$match": {"_d": {"$ne": None}}},
        {"$group": {"_id": {"$hour": {"date": "$_d", "timezone": "+03:00"}},
                    "orders": {"$sum": 1},
                    "revenue": {"$sum": {"$ifNull": ["$total", 0]}}}},
        {"$sort": {"_id": 1}},
    ]
    by = {int(r["_id"]): r async for r in db.orders.aggregate(pipeline)}
    rows = [{"hour": h, "label": f"{h:02d}:00",
             "orders": int(by.get(h, {}).get("orders", 0)),
             "revenue": round(float(by.get(h, {}).get("revenue", 0)), 2)} for h in range(24)]
    peak = max(rows, key=lambda r: r["orders"]) if any(r["orders"] for r in rows) else None
    return {"rows": rows,
            "peak": ({"range": f"{peak['hour']:02d}:00-{(peak['hour'] + 1) % 24:02d}:00",
                      "orders": peak["orders"]} if peak else None)}


@router.get("/sales-by-weekday")
async def sales_by_weekday(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = Query(None),
    current_user: dict = Depends(require_admin),
):
    """Gün Analizi: haftanın hangi günü daha çok satıyor (TR saati) — sipariş + ciro."""
    s, e = _iso_range(start_date, end_date)
    pipeline = [
        {"$match": _base_match(s, e, source)},
        {"$addFields": {"_d": {"$dateFromString": {"dateString": "$created_at", "onError": None}}}},
        {"$match": {"_d": {"$ne": None}}},
        {"$group": {"_id": {"$isoDayOfWeek": {"date": "$_d", "timezone": "+03:00"}},
                    "orders": {"$sum": 1},
                    "revenue": {"$sum": {"$ifNull": ["$total", 0]}}}},
        {"$sort": {"_id": 1}},
    ]
    _DAYS = {1: "Pazartesi", 2: "Salı", 3: "Çarşamba", 4: "Perşembe",
             5: "Cuma", 6: "Cumartesi", 7: "Pazar"}
    by = {int(r["_id"]): r async for r in db.orders.aggregate(pipeline)}
    rows = [{"day": d, "label": _DAYS[d],
             "orders": int(by.get(d, {}).get("orders", 0)),
             "revenue": round(float(by.get(d, {}).get("revenue", 0)), 2)} for d in range(1, 8)]
    peak = max(rows, key=lambda r: r["orders"]) if any(r["orders"] for r in rows) else None
    return {"rows": rows, "peak": (peak["label"] if peak else None)}


@router.get("/day-orders")
async def day_orders(
    date: str = Query(..., description="YYYY-MM-DD (TR günü)"),
    source: Optional[str] = Query(None),
    current_user: dict = Depends(require_admin),
):
    """Gün Detayı: seçilen TR gününde NE sipariş edilmiş — ürün/beden bazında adet + ciro."""
    try:
        d0 = datetime.fromisoformat(date).replace(tzinfo=timezone.utc) - timedelta(hours=3)
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz tarih (YYYY-MM-DD)")
    s, e = d0.isoformat(), (d0 + timedelta(days=1)).isoformat()
    m = {"created_at": {"$gte": s, "$lt": e}, "status": {"$nin": _EXCLUDED_STATUSES}}
    sc = _source_cond(source)
    if sc:
        m.update(sc)
    pipeline = [
        {"$match": m},
        {"$unwind": {"path": "$items", "preserveNullAndEmptyArrays": False}},
        {"$group": {
            "_id": {"name": {"$ifNull": ["$items.product_name", {"$ifNull": ["$items.name", "Ürün"]}]},
                    "size": {"$ifNull": ["$items.size", ""]}},
            "qty": {"$sum": {"$ifNull": ["$items.quantity", 1]}},
            "revenue": {"$sum": {"$multiply": [
                {"$ifNull": ["$items.quantity", 1]},
                {"$ifNull": ["$items.unit_price", {"$ifNull": ["$items.price", 0]}]}]}},
        }},
        {"$sort": {"qty": -1}},
        {"$limit": 300},
    ]
    rows = []
    async for r in db.orders.aggregate(pipeline):
        rows.append({"name": r["_id"]["name"], "size": r["_id"]["size"],
                     "qty": int(r["qty"]), "revenue": round(float(r["revenue"]), 2)})
    order_count = await db.orders.count_documents(m)
    return {"date": date, "order_count": order_count,
            "total_qty": sum(r["qty"] for r in rows), "rows": rows}


@router.get("/sales")
async def sales(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: str = Query("day", regex="^(day|week|month)$"),
    source: Optional[str] = Query(None, description="all|site|trendyol|hepsiburada|temu"),
    current_user: dict = Depends(require_admin),
):
    s, e = _iso_range(start_date, end_date)
    fmt = {"day": "%Y-%m-%d", "week": "%Y-%V", "month": "%Y-%m"}[group_by]
    pipeline = [
        {"$match": _base_match(s, e, source)},
        {
            "$group": {
                "_id": {"$dateToString": {"format": fmt, "date": {"$dateFromString": {"dateString": "$created_at"}}}},
                "orders": {"$sum": 1},
                "revenue": {"$sum": {"$ifNull": ["$total", 0]}},
                "items": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    rows = []
    async for r in db.orders.aggregate(pipeline):
        rows.append({"period": r["_id"], "orders": r["orders"], "revenue": round(r["revenue"], 2), "items": r["items"]})

    total_orders = sum(r["orders"] for r in rows)
    total_revenue = round(sum(r["revenue"] for r in rows), 2)
    aov = round(total_revenue / total_orders, 2) if total_orders else 0
    return {"rows": rows, "totals": {"orders": total_orders, "revenue": total_revenue, "aov": aov}}


@router.get("/sales-breakdown")
async def sales_breakdown(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = Query(None, description="all|site|trendyol|hepsiburada|temu"),
    current_user: dict = Depends(require_admin),
):
    """Ciro kırılımı — 4 kademe:
      ① included = İptal + İade DAHİL toplam ciro (net + iptal + iade)
      ② cancels  = sadece iptal edilen siparişlerin tutarı (kaybedilen)
      ③ returns  = sadece iade edilen siparişlerin tutarı (kaybedilen)
      ④ net      = iptal & iade HARİÇ net ciro (elimizde kalan)
    Tutar = order.total toplamı. Tarih aralığı TR yerel gün, kaynak filtreli."""
    s, e = _iso_range(start_date, end_date)
    base = {"created_at": {"$gte": s, "$lte": e}}
    sc = _source_cond(source)
    if sc:
        base.update(sc)
    _CANCEL = ["cancelled"]
    # İade grubu (return_rejected HARİÇ — satış geçerli sayılır, ciroda kalır)
    _RETURN = ["return_requested", "return_approved", "return_in_transit",
               "returned", "refunded", "partial_refunded"]

    async def _sum(status_cond):
        m = dict(base)
        if status_cond is not None:
            m["status"] = status_cond
        pipe = [{"$match": m}, {"$group": {"_id": None,
                "revenue": {"$sum": {"$ifNull": ["$total", 0]}}, "orders": {"$sum": 1}}}]
        async for r in db.orders.aggregate(pipe):
            return {"revenue": round(float(r["revenue"]), 2), "orders": int(r["orders"])}
        return {"revenue": 0.0, "orders": 0}

    cancels = await _sum({"$in": _CANCEL})
    returns = await _sum({"$in": _RETURN})
    net = await _sum({"$nin": _EXCLUDED_STATUSES})
    # DAHİL = net + iptal + iade (içsel tutarlı: pending/ödeme-bekleyen gürültüsü katılmaz)
    included = {
        "revenue": round(net["revenue"] + cancels["revenue"] + returns["revenue"], 2),
        "orders": net["orders"] + cancels["orders"] + returns["orders"],
    }
    return {"included": included, "cancels": cancels, "returns": returns, "net": net}


@router.get("/products/export-xlsx")
async def products_export_xlsx(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = Query(None),
    current_user: dict = Depends(require_admin),
):
    """Ürün raporunun Excel çıktısı — ekrandaki listeyle aynı veri (tüm ürünler,
    iptal/iade kolonları dahil). Kolon sıralamayı Excel içinde yapabilirsiniz."""
    import openpyxl
    from io import BytesIO as _BytesIO
    from fastapi.responses import Response as _Response
    data = await top_products(limit=5000, start_date=start_date, end_date=end_date,
                              source=source, current_user=current_user)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ürün Raporu"
    ws.append(["Ürün", "Koleksiyon", "Satış Adedi", "Ciro (TL)", "Sipariş", "Güncel Stok",
               "En Çok Satan Beden", "En Çok Satan Platform", "Haftalık Hız",
               "İptal Adet", "İade Adet", "Platform İptal/İade Detay"])
    for r in data.get("items", []):
        _crd = "; ".join(f"{x['platform']}: iptal {x['cancel']} / iade {x['return']}"
                         for x in (r.get("cancel_return_by_platform") or []))
        ws.append([r.get("name"), r.get("collection") or "", r.get("qty"), r.get("revenue"),
                   r.get("orders"), r.get("current_stock"), r.get("best_size"),
                   r.get("top_platform"), (r.get("velocity") or {}).get("weekly_rate"),
                   r.get("cancel_qty", 0), r.get("return_qty", 0), _crd])
    for col, w in zip("ABCDEFGHIJKL", [42, 10, 12, 14, 10, 12, 16, 18, 12, 10, 10, 40]):
        ws.column_dimensions[col].width = w
    buf = _BytesIO()
    wb.save(buf)
    return _Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=urun-raporu.xlsx"})


@router.get("/products/top")
async def top_products(
    limit: int = Query(1000, ge=1, le=5000),   # varsayılan TÜM ürünler (yüksek tavan)
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = Query(None, description="all|site|trendyol|hepsiburada|temu"),
    current_user: dict = Depends(require_admin),
):
    """ÜRÜN bazında satış raporu. Aynı ürünün farklı beden/renk kalemleri TEK satırda
    birleşir (mükerrer yok). Her ürün için: toplam adet + ciro + sipariş, güncel stok,
    EN ÇOK SATAN BEDEN ve PLATFORM DAĞILIMI döner. Frontend cirodan yükseğe sıralar/filtreler."""
    s, e = _iso_range(start_date, end_date, days_default=90)
    pipeline = [
        {"$match": _base_match(s, e, source)},
        # Sipariş platformu: platform > marketplace > 'site'
        {"$addFields": {"_plat": {"$toLower": {"$ifNull": ["$platform", {"$ifNull": ["$marketplace", "site"]}]}}}},
        {"$unwind": {"path": "$items", "preserveNullAndEmptyArrays": False}},
        {"$addFields": {
            "_nm": {"$ifNull": ["$items.name",
                     {"$ifNull": ["$items.product_name",
                       {"$ifNull": ["$items.productName", ""]}]}]},
            "_bc": {"$toString": {"$ifNull": ["$items.barcode", ""]}},
            "_pid": {"$toString": {"$ifNull": ["$items.product_id", ""]}},
            "_sz": {"$toString": {"$ifNull": ["$items.size", ""]}},
        }},
        # Kalem anahtarı: barkod > product_id > ad. Beden ve platform gruplamaya dahil edilir
        # ki EN ÇOK SATAN BEDEN + platform dağılımı çıkarılabilsin (parent birleştirme Python'da).
        {"$addFields": {"_key": {"$switch": {"branches": [
            {"case": {"$ne": ["$_bc", ""]}, "then": {"$concat": ["bc:", "$_bc"]}},
            {"case": {"$ne": ["$_pid", ""]}, "then": {"$concat": ["pid:", "$_pid"]}},
        ], "default": {"$concat": ["nm:", "$_nm"]}}}}},
        {"$group": {
            "_id": {"k": "$_key", "sz": "$_sz", "plat": "$_plat"},
            "name": {"$first": "$_nm"},
            "barcode": {"$first": "$_bc"},
            "pid": {"$first": "$_pid"},
            "qty": {"$sum": {"$ifNull": ["$items.quantity", 1]}},
            "revenue": {"$sum": {"$multiply": [{"$ifNull": ["$items.price", 0]}, {"$ifNull": ["$items.quantity", 1]}]}},
            "orders": {"$sum": 1},
        }},
    ]
    raw = []
    async for r in db.orders.aggregate(pipeline):
        raw.append(r)
    # Ürün eşleştirme: barkod/pid -> PARENT ürün (id, ad, stok). Birleştirme parent id ile yapılır.
    pids = [r.get("pid") for r in raw if r.get("pid")]
    bcs = [r.get("barcode") for r in raw if r.get("barcode")]
    by_id, by_bc = {}, {}
    if pids or bcs:
        q = {"$or": []}
        if pids:
            q["$or"].append({"id": {"$in": pids}})
        if bcs:
            q["$or"] += [{"barcode": {"$in": bcs}}, {"variants.barcode": {"$in": bcs}}]
        async for p in db.products.find(q, {"_id": 0, "id": 1, "name": 1, "stock": 1, "variants": 1,
                                             "barcode": 1, "collection": 1, "created_at": 1, "stock_code": 1}):
            variants = p.get("variants") or []
            stock = sum(int(v.get("stock") or 0) for v in variants) if variants else int(p.get("stock") or 0)
            info = {"id": str(p.get("id")), "name": p.get("name") or "", "stock": stock,
                    "collection": (p.get("collection") or "").strip(),
                    "created_at": p.get("created_at") or None,
                    "stock_code": (p.get("stock_code") or "").strip()}
            by_id[str(p.get("id"))] = info
            if p.get("barcode"):
                by_bc[str(p["barcode"])] = info
            for v in variants:
                if v.get("barcode"):
                    by_bc[str(v["barcode"])] = info
    # PARENT ürün bazında birleştir → mükerrer beden/renk satırları tek ürün olur.
    merged = {}
    for r in raw:
        pm = by_bc.get(r.get("barcode") or "") or by_id.get(r.get("pid") or "") or {}
        name = pm.get("name") or r.get("name") or "(isimsiz ürün)"
        # Grup anahtarı: çözülen parent id > pid > ad (isim NFC normalize edilerek NFD mükerreri de birleşsin)
        import unicodedata as _ud
        _nkey = _ud.normalize("NFC", name).strip().lower()
        gkey = pm.get("id") or (r.get("pid") or None) or f"nm:{_nkey}"
        m = merged.get(gkey)
        if not m:
            m = merged[gkey] = {
                "product_id": pm.get("id") or r.get("pid"), "name": name,
                "qty": 0, "revenue": 0.0, "orders": 0,
                "current_stock": pm.get("stock", None), "_sizes": {}, "_plats": {},
                # Koleksiyon: stok kodu ön ekinden (fcfw/fcss) — filtre değerleri tek tip (FcFw/FCss)
                # kalsın diye önce kod ön eki; kod yoksa serbest metin collection alanına düşer.
                "collection": _collection_from_code(pm.get("stock_code"), r.get("barcode"), r.get("pid"))
                              or (pm.get("collection") or "").strip(),
                "created_at": pm.get("created_at"),
                "stock_code": pm.get("stock_code") or "",
            }
        _q = int(r["qty"])
        m["qty"] += _q
        m["revenue"] += float(r["revenue"])
        m["orders"] += int(r["orders"])
        _sz = (r["_id"].get("sz") or "").strip() or "—"
        m["_sizes"][_sz] = m["_sizes"].get(_sz, 0) + _q
        _pl = (r["_id"].get("plat") or "site").strip().lower() or "site"
        m["_plats"][_pl] = m["_plats"].get(_pl, 0) + _q
    # D4 — Satış hızı (velocity) renk kodu. Seçili tarih aralığının hafta sayısına göre
    # HAFTALIK ortalama satış hesaplanır: yeşil ≥5/hafta, sarı 1-4/hafta, kırmızı <1/hafta (~ayda 0-2).
    try:
        _sd = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        _ed = datetime.fromisoformat(str(e).replace("Z", "+00:00"))
        _range_days = max(1.0, (_ed - _sd).total_seconds() / 86400.0)
    except Exception:
        _range_days = float(90)
    _weeks = max(1.0, _range_days / 7.0)

    def _velocity(qty: int):
        wr = qty / _weeks
        if wr >= 5:
            code, label = "green", "Hızlı (haftada 5+)"
        elif wr >= 1:
            code, label = "yellow", "Orta (haftada 1-4)"
        else:
            code, label = "red", "Yavaş (ayda 0-2)"
        return {"weekly_rate": round(wr, 1), "code": code, "label": label}

    # SATIŞI OLMAYAN ürünler de listelensin ("143 ürün" yalnız satışı olanlardı) —
    # aktif katalogda olup raporda görünmeyenler qty=0 satırıyla eklenir.
    _seen_ids = {m.get("product_id") for m in merged.values() if m.get("product_id")}
    async for p in db.products.find(
            {"is_active": True, "is_deleted": {"$ne": True}},
            {"_id": 0, "id": 1, "name": 1, "stock": 1, "variants": 1, "collection": 1,
             "created_at": 1, "stock_code": 1}):
        if str(p.get("id")) in _seen_ids:
            continue
        variants = p.get("variants") or []
        stock = sum(int(v.get("stock") or 0) for v in variants) if variants else int(p.get("stock") or 0)
        merged[f"zero:{p.get('id')}"] = {
            "product_id": str(p.get("id")), "name": p.get("name") or "",
            "qty": 0, "revenue": 0.0, "orders": 0, "current_stock": stock,
            "_sizes": {}, "_plats": {},
            "collection": _collection_from_code(p.get("stock_code")) or (p.get("collection") or "").strip(),
            "created_at": p.get("created_at"), "stock_code": (p.get("stock_code") or "").strip(),
        }

    # İPTAL & İADE — ürün bazında, platform kırılımlı (aynı kalem-anahtar çözümüyle)
    _CR_CANCEL = ["cancelled", "cancel_refunded"]
    _CR_RETURN = ["return_requested", "return_approved", "return_in_transit",
                  "returned", "refunded", "partial_refunded"]
    _cr_pipe = [
        {"$match": {"created_at": {"$gte": s, "$lte": e}, "status": {"$in": _CR_CANCEL + _CR_RETURN}}},
        {"$addFields": {"_plat": {"$toLower": {"$ifNull": ["$platform", {"$ifNull": ["$marketplace", "site"]}]}},
                        "_kind": {"$cond": [{"$in": ["$status", _CR_CANCEL]}, "cancel", "return"]}}},
        {"$unwind": {"path": "$items", "preserveNullAndEmptyArrays": False}},
        {"$group": {"_id": {"bc": {"$toString": {"$ifNull": ["$items.barcode", ""]}},
                            "pid": {"$toString": {"$ifNull": ["$items.product_id", ""]}},
                            "nm": {"$ifNull": ["$items.name", {"$ifNull": ["$items.product_name", ""]}]},
                            "kind": "$_kind", "plat": "$_plat"},
                    "qty": {"$sum": {"$ifNull": ["$items.quantity", 1]}}}},
    ]
    import unicodedata as _ud3
    cr_map: dict = {}
    async for r in db.orders.aggregate(_cr_pipe):
        i = r["_id"]
        pm = by_bc.get(i.get("bc") or "") or by_id.get(i.get("pid") or "") or {}
        _cname = pm.get("name") or i.get("nm") or "(isimsiz ürün)"
        gk = pm.get("id") or (i.get("pid") or None) or f"nm:{_ud3.normalize('NFC', _cname).strip().lower()}"
        d = cr_map.setdefault(gk, {"cancel": 0, "return": 0, "by_plat": {}})
        d[i["kind"]] += int(r["qty"])
        bp = d["by_plat"].setdefault((i.get("plat") or "site"), {"cancel": 0, "return": 0})
        bp[i["kind"]] += int(r["qty"])

    out = []
    for gkey, m in merged.items():
        _sizes = sorted(m.pop("_sizes").items(), key=lambda x: -x[1])
        _plats = sorted(m.pop("_plats").items(), key=lambda x: -x[1])
        _cr = cr_map.get(m.get("product_id") or gkey) or cr_map.get(gkey) or {}
        out.append({
            **m,
            "revenue": round(m["revenue"], 2),
            "best_size": _sizes[0][0] if _sizes else "—",
            "size_breakdown": [{"size": k, "qty": v} for k, v in _sizes],
            "top_platform": _plats[0][0] if _plats else "site",
            "platform_breakdown": [{"platform": k, "qty": v} for k, v in _plats],
            "velocity": _velocity(int(m["qty"])),
            "cancel_qty": int(_cr.get("cancel", 0)),
            "return_qty": int(_cr.get("return", 0)),
            "cancel_return_by_platform": [
                {"platform": k, "cancel": v["cancel"], "return": v["return"]}
                for k, v in sorted((_cr.get("by_plat") or {}).items())],
        })
    out.sort(key=lambda x: -x["revenue"])
    return {"items": out[:limit], "range_days": round(_range_days, 1), "weeks": round(_weeks, 1)}


# ============================================================================
# KÂRLILIK ANALİZİ (Melontik-tarzı) — kategori × pazaryeri NET kâr
# Gider kalemleri: COGS + komisyon + kargo + hizmet bedeli + reklam + KDV + kurumlar vergisi.
# Oranlar db.settings id="profitability_config" tan; yoksa TR gerçeğine göre varsayılan.
# ============================================================================
_PROFIT_DEFAULTS = {
    # Pazaryeri komisyonu (%) — kategori bazında değişir; buradan pazaryeri-geneli ayarlanır.
    "commission_pct": {"trendyol": 18.0, "hepsiburada": 17.0, "temu": 5.0,
                       "n11": 12.0, "amazon": 15.0, "site": 3.0, "manual": 0.0},
    # Hizmet/işlem bedeli (%) — Trendyol hizmet bedeli vb. (varsayılan 0, kullanıcı girer)
    "service_fee_pct": {"trendyol": 0.0, "hepsiburada": 0.0, "temu": 0.0, "site": 0.0},
    # Dönem TOPLAM reklam gideri (TL) — kanal bazında; ciro payına göre kategorilere dağıtılır.
    "ad_spend": {"trendyol": 0.0, "hepsiburada": 0.0, "site": 0.0},
    # AYLIK reklam bütçesi (TL) — kanal bazında; seçili tarih aralığına OTOMATİK orantılanır
    # (Trendyol reklam verisi API'de olmadığından: aylık gir, rapor gün sayısına göre böler).
    # Bir kanalda ad_spend_monthly>0 ise o kanalda ad_spend yerine bu (orantılı) kullanılır.
    "ad_spend_monthly": {"trendyol": 0.0, "hepsiburada": 0.0, "site": 0.0},
    "packaging_per_order": 0.0,   # sipariş başı paketleme/operasyon (TL)
    "vat_rate": 10.0,             # KDV (%)
    "corporate_tax_pct": 25.0,    # Kurumlar vergisi (2025 TR)
    "cog_fallback_ratio": 0.5,    # maliyet bilinmiyorsa satış fiyatının %'si
}


async def _profitability_config() -> dict:
    doc = await db.settings.find_one({"id": "profitability_config"}, {"_id": 0}) or {}
    cfg = {**_PROFIT_DEFAULTS}
    for k, v in doc.items():
        if k == "id":
            continue
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k] = {**cfg[k], **v}
        else:
            cfg[k] = v
    return cfg


@router.get("/profitability-config")
async def get_profitability_config(current_user: dict = Depends(require_admin)):
    """Kârlılık analizi gider oran/varsayımları (komisyon, reklam, hizmet bedeli, KDV, kurumlar vergisi)."""
    return {"config": await _profitability_config(), "defaults": _PROFIT_DEFAULTS}


@router.put("/profitability-config")
async def set_profitability_config(payload: dict, current_user: dict = Depends(require_admin)):
    """Kârlılık gider varsayımlarını günceller (yalnız gönderilen alanlar birleşir)."""
    payload = {k: v for k, v in (payload or {}).items() if k in _PROFIT_DEFAULTS}
    await db.settings.update_one({"id": "profitability_config"}, {"$set": {"id": "profitability_config", **payload}}, upsert=True)
    return {"success": True, "config": await _profitability_config()}


@router.get("/profitability")
async def profitability(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = Query(None, description="all|site|trendyol|hepsiburada|temu"),
    current_user: dict = Depends(require_admin),
):
    """KÂRLILIK ANALİZİ — kategori bazında (kaynak filtreli) tüm giderler düşülerek NET kâr.
    Kalemler: Ciro − COGS − Komisyon − Kargo − Hizmet Bedeli − Reklam − İade − KDV − Kurumlar Vergisi.
    Oranlar profitability-config'ten; maliyet ürün purchase_price/product_costs'tan (yoksa oranla tahmin)."""
    s, e = _iso_range(start_date, end_date, days_default=30)
    cfg = await _profitability_config()
    # Tarih aralığı gün sayısı — aylık reklam bütçesini orantılamak için.
    try:
        _d0 = datetime.fromisoformat(s.replace("Z", "+00:00"))
        _d1 = datetime.fromisoformat(e.replace("Z", "+00:00"))
        _days_range = max(1, (_d1 - _d0).days + 1)
    except Exception:
        _days_range = 30
    _CH_ALIAS = {"facette": "site", "": "site", "web": "site", "admin_manual": "manual", "admin": "manual"}
    from collections import defaultdict as _dd

    # Ana kırılım: (kategori, kanal) → ciro, maliyet, adet, sipariş. Maliyet: purchase_price köprüsü.
    pipeline = [
        {"$match": _base_match(s, e, source)},
        {"$addFields": {"_ch": {"$toLower": {"$ifNull": ["$platform", {"$ifNull": ["$marketplace", "site"]}]}}}},
        {"$unwind": "$items"},
        {"$addFields": {"_bc": {"$toString": {"$ifNull": ["$items.barcode", ""]}}}},
        {"$lookup": {
            "from": "products",
            "let": {"pid": "$items.product_id", "bc": "$_bc"},
            "pipeline": [
                {"$match": {"$expr": {"$or": [
                    {"$eq": ["$id", "$$pid"]},
                    {"$and": [{"$ne": ["$$bc", ""]}, {"$eq": [{"$toString": "$barcode"}, "$$bc"]}]},
                    {"$and": [{"$ne": ["$$bc", ""]}, {"$in": ["$$bc", {"$map": {"input": {"$ifNull": ["$variants", []]}, "as": "v", "in": {"$toString": "$$v.barcode"}}}]}]},
                ]}}},
                {"$limit": 1},
                {"$project": {"_id": 0, "category_name": 1, "purchase_price": 1}},
            ],
            "as": "p",
        }},
        {"$unwind": {"path": "$p", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": {"cat": {"$ifNull": ["$p.category_name",
                        {"$ifNull": ["$items.category_name", {"$ifNull": ["$items.category", "(Kategorisiz)"]}]}]},
                    "ch": "$_ch"},
            "qty": {"$sum": {"$ifNull": ["$items.quantity", 1]}},
            "revenue": {"$sum": {"$multiply": [{"$ifNull": ["$items.price", 0]}, {"$ifNull": ["$items.quantity", 1]}]}},
            "cogs": {"$sum": {"$multiply": [{"$ifNull": ["$p.purchase_price", 0]}, {"$ifNull": ["$items.quantity", 1]}]}},
            "revenue_nocost": {"$sum": {"$cond": [{"$gt": [{"$ifNull": ["$p.purchase_price", 0]}, 0]}, 0,
                                {"$multiply": [{"$ifNull": ["$items.price", 0]}, {"$ifNull": ["$items.quantity", 1]}]}]}},
        }},
    ]
    # Kanal başına toplam kargo (ciro payına göre kategorilere dağıtılır)
    cargo_by_ch = _dd(float)
    async for r in db.orders.aggregate([
        {"$match": _base_match(s, e, source)},
        {"$addFields": {"_ch": {"$toLower": {"$ifNull": ["$platform", {"$ifNull": ["$marketplace", "site"]}]}}}},
        {"$group": {"_id": "$_ch", "shipping": {"$sum": {"$ifNull": ["$shipping_cost", 0]}}, "orders": {"$sum": 1}}},
    ]):
        cargo_by_ch[_CH_ALIAS.get((r["_id"] or "site"), r["_id"] or "site")] = {"shipping": float(r["shipping"] or 0), "orders": int(r["orders"])}

    # Kategori-kanal satırlarını topla
    rows = []
    rev_by_ch = _dd(float)
    async for r in db.orders.aggregate(pipeline):
        ch = _CH_ALIAS.get((r["_id"].get("ch") or "site"), r["_id"].get("ch") or "site")
        rev = float(r["revenue"] or 0)
        cogs = float(r["cogs"] or 0)
        # Maliyeti bilinmeyen kalemler için oranla tahmin ekle
        cogs += float(r.get("revenue_nocost") or 0) * float(cfg["cog_fallback_ratio"])
        rows.append({"category": r["_id"].get("cat") or "(Kategorisiz)", "channel": ch,
                     "qty": int(r["qty"]), "revenue": rev, "cogs": round(cogs, 2)})
        rev_by_ch[ch] += rev
    total_rev = sum(rev_by_ch.values()) or 1.0

    vat = float(cfg["vat_rate"])
    corp = float(cfg["corporate_tax_pct"])
    out = []
    for row in rows:
        ch = row["channel"]
        rev = row["revenue"]
        cogs = row["cogs"]
        commission = rev * float(cfg["commission_pct"].get(ch, 5.0)) / 100.0
        service_fee = rev * float(cfg["service_fee_pct"].get(ch, 0.0)) / 100.0
        # Kargo: kanal toplam kargosunu bu satırın ciro payına göre dağıt
        ch_cargo = (cargo_by_ch.get(ch) or {}).get("shipping", 0.0)
        cargo = ch_cargo * (rev / rev_by_ch[ch]) if rev_by_ch.get(ch) else 0.0
        # Reklam: AYLIK bütçe girildiyse tarih aralığına orantıla (aylık × gün/30), yoksa dönem toplamı.
        _monthly = float((cfg.get("ad_spend_monthly") or {}).get(ch, 0.0))
        ad_total = round(_monthly * _days_range / 30.0, 2) if _monthly > 0 else float(cfg["ad_spend"].get(ch, 0.0))
        ad_alloc = ad_total * (rev / rev_by_ch[ch]) if rev_by_ch.get(ch) else 0.0
        operating = rev - cogs - commission - service_fee - cargo - ad_alloc
        # KDV (net ödenecek — katma değer üzerinden): (ciro - maliyet) içindeki KDV
        vat_payable = max(0.0, (rev - cogs)) * vat / (100.0 + vat)
        pre_tax = operating - vat_payable
        corporate_tax = max(0.0, pre_tax) * corp / 100.0
        net = pre_tax - corporate_tax
        out.append({
            "category": row["category"], "channel": ch, "qty": row["qty"],
            "revenue": round(rev, 2), "cogs": round(cogs, 2),
            "commission": round(commission, 2), "service_fee": round(service_fee, 2),
            "cargo": round(cargo, 2), "ad_spend": round(ad_alloc, 2),
            "vat_payable": round(vat_payable, 2), "corporate_tax": round(corporate_tax, 2),
            "net_profit": round(net, 2),
            "margin_pct": round(net / rev * 100.0, 1) if rev else 0.0,
        })
    out.sort(key=lambda x: -x["net_profit"])
    # Toplamlar
    def _sum(k):
        return round(sum(x[k] for x in out), 2)
    totals = {k: _sum(k) for k in ("revenue", "cogs", "commission", "service_fee", "cargo",
                                    "ad_spend", "vat_payable", "corporate_tax", "net_profit")}
    totals["qty"] = sum(x["qty"] for x in out)
    totals["margin_pct"] = round(totals["net_profit"] / totals["revenue"] * 100.0, 1) if totals["revenue"] else 0.0
    return {"items": out, "totals": totals, "config": cfg}


@router.get("/categories")
async def category_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = Query(None, description="all|site|trendyol|hepsiburada|temu"),
    current_user: dict = Depends(require_admin),
):
    s, e = _iso_range(start_date, end_date, days_default=90)
    # items -> product: product_id VEYA barkod (üst/varyant) ile eşleştir (pazaryeri kalemleri
    # productCode taşır, Facette id'siyle eşleşmez → barkod köprüsü şart). Kategori adı: kategori
    # dokümanı > ürünün category_name'i > kalemin kendi category'si > (Kategorisiz).
    pipeline = [
        {"$match": _base_match(s, e, source)},
        {"$unwind": "$items"},
        {"$addFields": {"_bc": {"$toString": {"$ifNull": ["$items.barcode", ""]}}}},
        {"$lookup": {
            "from": "products",
            "let": {"pid": "$items.product_id", "bc": "$_bc"},
            "pipeline": [
                {"$match": {"$expr": {"$or": [
                    {"$eq": ["$id", "$$pid"]},
                    {"$and": [{"$ne": ["$$bc", ""]}, {"$eq": [{"$toString": "$barcode"}, "$$bc"]}]},
                    {"$and": [{"$ne": ["$$bc", ""]}, {"$in": ["$$bc", {"$map": {"input": {"$ifNull": ["$variants", []]}, "as": "v", "in": {"$toString": "$$v.barcode"}}}]}]},
                ]}}},
                {"$limit": 1},
                {"$project": {"_id": 0, "category_id": 1, "category_name": 1}},
            ],
            "as": "p",
        }},
        {"$unwind": {"path": "$p", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {"from": "categories", "localField": "p.category_id", "foreignField": "id", "as": "c"}},
        {"$unwind": {"path": "$c", "preserveNullAndEmptyArrays": True}},
        {
            "$group": {
                "_id": {"$ifNull": ["$c.name",
                         {"$ifNull": ["$p.category_name",
                           {"$ifNull": ["$items.category_name",
                             {"$ifNull": ["$items.category", "(Kategorisiz)"]}]}]}]},
                "qty": {"$sum": {"$ifNull": ["$items.quantity", 1]}},
                "revenue": {"$sum": {"$multiply": [{"$ifNull": ["$items.price", 0]}, {"$ifNull": ["$items.quantity", 1]}]}},
            }
        },
        {"$sort": {"revenue": -1}},
    ]
    out = []
    async for r in db.orders.aggregate(pipeline):
        out.append({"category": r["_id"] or "(Kategorisiz)", "qty": r["qty"], "revenue": round(r["revenue"], 2)})
    return {"items": out}


@router.get("/stock")
async def stock_report(current_user: dict = Depends(require_admin)):
    # DENETİM FIX: stok varyantlı üründe top-level 'stock'ta DEĞİL variants[].stock'ta tutulur.
    # Eski rapor yalnız top-level 'stock'a bakıyordu → varyantlı ürünler yanlışlıkla 'tükendi'
    # sayılıyor, toplam adet/değer ve kritik/tükenen listeleri hatalı çıkıyordu. Efektif stok:
    # varyant varsa varyant toplamı, yoksa top-level stock.
    _eff = {"$cond": [{"$gt": [{"$size": {"$ifNull": ["$variants", []]}}, 0]},
                      {"$sum": {"$map": {"input": "$variants", "as": "v",
                                         "in": {"$convert": {"input": "$$v.stock", "to": "int", "onError": 0, "onNull": 0}}}}},
                      {"$convert": {"input": "$stock", "to": "int", "onError": 0, "onNull": 0}}]}
    low, out_of_stock = [], []
    units = 0
    value = 0.0
    async for r in db.products.aggregate([
        {"$project": {"_id": 0, "id": 1, "name": 1, "stock_code": 1, "price": 1, "eff": _eff}}
    ]):
        s = int(r.get("eff") or 0)
        units += s
        try:
            value += s * float(r.get("price") or 0)
        except Exception:
            pass
        row = {"id": r.get("id"), "name": r.get("name"), "stock_code": r.get("stock_code"), "stock": s}
        if s <= 0:
            out_of_stock.append(row)
        elif s <= 5:
            low.append(row)
    low.sort(key=lambda x: x["stock"])
    return {
        "low_stock": low[:100],
        "out_of_stock": out_of_stock[:200],
        "totals": {"units": units, "value": round(value, 2)},
    }


@router.get("/payments")
async def payment_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = Query(None, description="all|site|trendyol|hepsiburada|temu"),
    current_user: dict = Depends(require_admin),
):
    s, e = _iso_range(start_date, end_date)
    # Pazaryeri siparişleri "marketplace" olarak tek kalemde toplanıyordu — artık
    # platforma göre Trendyol / Hepsiburada / Temu olarak AYRI gösterilir.
    _plat = {"$toLower": {"$ifNull": ["$platform", {"$ifNull": ["$marketplace", ""]}]}}
    pipeline = [
        {"$match": _base_match(s, e, source)},
        {"$group": {"_id": {"$cond": [
            {"$in": [_plat, ["trendyol", "hepsiburada", "temu"]]},
            _plat,
            {"$ifNull": ["$payment_method", "—"]}]},
            "orders": {"$sum": 1}, "revenue": {"$sum": {"$ifNull": ["$total", 0]}}}},
        {"$sort": {"revenue": -1}},
    ]
    _LABELS = {
        "trendyol": "Trendyol", "hepsiburada": "Hepsiburada", "temu": "Temu",
        "credit_card": "Kredi Kartı", "card": "Kredi Kartı", "iyzico": "Kredi Kartı",
        "bank_transfer": "Havale/EFT", "havale": "Havale/EFT", "eft": "Havale/EFT",
        "havale_eft": "Havale/EFT", "banka_havale": "Havale/EFT",
        "cash_on_delivery": "Kapıda Ödeme", "kapida": "Kapıda Ödeme", "cod": "Kapıda Ödeme",
        "gift_card": "Hediye Çeki", "marketplace": "Pazaryeri (diğer)",
    }
    merged: dict = {}
    async for r in db.orders.aggregate(pipeline):
        key = str(r["_id"] or "—").lower()
        label = _LABELS.get(key, r["_id"] or "—")
        m = merged.setdefault(label, {"orders": 0, "revenue": 0.0})
        m["orders"] += r["orders"]
        m["revenue"] += float(r["revenue"] or 0)
    out = [{"method": k, "orders": v["orders"], "revenue": round(v["revenue"], 2)}
           for k, v in sorted(merged.items(), key=lambda kv: -kv[1]["revenue"])]
    return {"items": out}


@router.get("/cancel-return-by-source")
async def cancel_return_by_source(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    """Pazaryerlerine göre iade ve iptal durumları: Site / Trendyol / Hepsiburada / Temu
    başına iptal + iade sipariş sayısı ve tutarı."""
    s, e = _iso_range(start_date, end_date)
    _RETURN_ST = ["return_requested", "return_approved", "return_in_transit",
                  "returned", "refunded", "partial_refunded"]
    _CANCEL_ST = ["cancelled", "cancel_refunded"]
    _plat = {"$toLower": {"$ifNull": ["$platform", {"$ifNull": ["$marketplace", ""]}]}}
    pipeline = [
        {"$match": {"created_at": {"$gte": s, "$lte": e},
                    "status": {"$in": _RETURN_ST + _CANCEL_ST}}},
        {"$group": {
            "_id": {"src": {"$cond": [{"$in": [_plat, ["trendyol", "hepsiburada", "temu"]]}, _plat, "site"]},
                    "kind": {"$cond": [{"$in": ["$status", _CANCEL_ST]}, "cancel", "return"]}},
            "orders": {"$sum": 1},
            "total": {"$sum": {"$ifNull": ["$total", 0]}}}},
    ]
    _SRC = {"site": "Site", "trendyol": "Trendyol", "hepsiburada": "Hepsiburada", "temu": "Temu"}
    rows: dict = {}
    async for r in db.orders.aggregate(pipeline):
        src = _SRC.get(r["_id"]["src"], r["_id"]["src"])
        d = rows.setdefault(src, {"source": src, "cancel_orders": 0, "cancel_total": 0.0,
                                  "return_orders": 0, "return_total": 0.0})
        if r["_id"]["kind"] == "cancel":
            d["cancel_orders"] += r["orders"]
            d["cancel_total"] += float(r["total"] or 0)
        else:
            d["return_orders"] += r["orders"]
            d["return_total"] += float(r["total"] or 0)
    out = sorted(rows.values(), key=lambda x: -(x["cancel_total"] + x["return_total"]))
    for d in out:
        d["cancel_total"] = round(d["cancel_total"], 2)
        d["return_total"] = round(d["return_total"], 2)
    return {"items": out}


@router.get("/cargo")
async def cargo_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    s, e = _iso_range(start_date, end_date)
    pipeline = [
        {"$match": {"created_at": {"$gte": s, "$lte": e}}},
        {"$group": {"_id": {"$ifNull": ["$cargo_provider_name", "$cargo.company"]}, "orders": {"$sum": 1}, "revenue": {"$sum": {"$ifNull": ["$shipping_cost", 0]}}}},
        {"$sort": {"orders": -1}},
    ]
    out = []
    async for r in db.orders.aggregate(pipeline):
        out.append({"provider": r["_id"] or "Belirtilmemiş", "orders": r["orders"], "shipping_revenue": round(r["revenue"], 2)})
    return {"items": out}


@router.get("/members")
async def members_report(current_user: dict = Depends(require_admin)):
    # Top 20 members by spend
    pipeline = [
        {"$match": {"user_id": {"$ne": None}, "status": {"$ne": "cancelled"}}},
        {"$group": {"_id": "$user_id", "orders": {"$sum": 1}, "revenue": {"$sum": {"$ifNull": ["$total", 0]}}, "last_order": {"$max": "$created_at"}}},
        {"$sort": {"revenue": -1}},
        {"$limit": 20},
        {"$lookup": {"from": "users", "localField": "_id", "foreignField": "id", "as": "u"}},
        {"$unwind": {"path": "$u", "preserveNullAndEmptyArrays": True}},
    ]
    out = []
    async for r in db.orders.aggregate(pipeline):
        u = r.get("u") or {}
        out.append({
            "user_id": r["_id"],
            "name": f"{u.get('first_name','')} {u.get('last_name','')}".strip() or u.get("email", "—"),
            "email": u.get("email", "—"),
            "orders": r["orders"],
            "revenue": round(r["revenue"], 2),
            "last_order_at": r["last_order"],
        })
    return {"top_members": out}



# =============================================================================
# FAZ 8 — İade analizleri + hızlı satış dedektörü
# =============================================================================

@router.get("/returns/by-size")
async def returns_by_size(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    """En çok iade edilen bedenleri döner (returns koleksiyonu)."""
    start, end = _iso_range(start_date, end_date, 180)
    pipeline = [
        {"$match": {"created_at": {"$gte": start, "$lte": end}, "status": {"$ne": "rejected"}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": {"size": {"$ifNull": ["$items.size", "—"]}},
            "count": {"$sum": {"$ifNull": ["$items.quantity", 1]}},
            "orders": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 30},
    ]
    out = []
    async for r in db.returns.aggregate(pipeline):
        out.append({"size": r["_id"]["size"], "count": r["count"], "order_count": r["orders"]})
    return {"by_size": out, "start": start, "end": end}


@router.get("/returns/by-product")
async def returns_by_product(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_admin),
):
    """En çok iade edilen ürünler + iade oranları (aynı dönem satışa göre)."""
    start, end = _iso_range(start_date, end_date, 180)
    ret_pipe = [
        {"$match": {"created_at": {"$gte": start, "$lte": end}, "status": {"$ne": "rejected"}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.product_id",
            "returned": {"$sum": {"$ifNull": ["$items.quantity", 1]}},
            "product_name": {"$first": {"$ifNull": ["$items.name", "$items.product_name"]}},
        }},
        {"$sort": {"returned": -1}},
        {"$limit": limit},
    ]
    returns_map = {}
    async for r in db.returns.aggregate(ret_pipe):
        returns_map[r["_id"]] = r

    product_ids = list(returns_map.keys())
    sales_map = {}
    if product_ids:
        sales_pipe = [
            {"$match": {"created_at": {"$gte": start, "$lte": end}, "status": {"$nin": ["cancelled", "pending"]}}},
            {"$unwind": "$items"},
            {"$match": {"items.product_id": {"$in": product_ids}}},
            {"$group": {
                "_id": "$items.product_id",
                "sold": {"$sum": {"$ifNull": ["$items.quantity", 1]}},
            }},
        ]
        async for r in db.orders.aggregate(sales_pipe):
            sales_map[r["_id"]] = r["sold"]

    out = []
    for pid, r in returns_map.items():
        sold = sales_map.get(pid, 0)
        rate = (r["returned"] / sold * 100) if sold else None
        out.append({
            "product_id": pid,
            "product_name": r.get("product_name") or "—",
            "returned": r["returned"],
            "sold": sold,
            "return_rate_pct": round(rate, 1) if rate is not None else None,
        })
    return {"items": out, "start": start, "end": end}


@router.get("/returns/reasons")
async def returns_by_reason(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    """İade sebeplerine göre dağılım."""
    start, end = _iso_range(start_date, end_date, 180)
    pipeline = [
        {"$match": {"created_at": {"$gte": start, "$lte": end}, "status": {"$ne": "rejected"}}},
        {"$group": {"_id": {"$ifNull": ["$reason", "Belirtilmemiş"]}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    out = []
    async for r in db.returns.aggregate(pipeline):
        out.append({"reason": r["_id"], "count": r["count"]})
    return {"reasons": out, "start": start, "end": end}


@router.get("/fast-selling")
async def fast_selling_products(
    window_days: int = Query(14, ge=1, le=90),
    min_sold: int = Query(10, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_admin),
):
    """Hızlı satış dedektörü: son N gün içinde ≥ min_sold adet satan ürünler.
    recommend_ads = true → ilk 60 gün içindeki yeni ürün + min sold'u geçti → reklam önerisi.
    """
    now = datetime.now(timezone.utc)
    start_ts = (now - timedelta(days=window_days)).isoformat()
    pipeline = [
        {"$match": {"created_at": {"$gte": start_ts}, "status": {"$nin": ["cancelled", "pending"]}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.product_id",
            "sold": {"$sum": {"$ifNull": ["$items.quantity", 1]}},
            "product_name": {"$first": {"$ifNull": ["$items.name", "$items.product_name"]}},
            "revenue": {"$sum": {"$multiply": [{"$ifNull": ["$items.price", 0]}, {"$ifNull": ["$items.quantity", 1]}]}},
        }},
        {"$match": {"sold": {"$gte": min_sold}}},
        {"$sort": {"sold": -1}},
        {"$limit": limit},
    ]
    out = []
    async for r in db.orders.aggregate(pipeline):
        pid = r["_id"]
        product = await db.products.find_one({"id": pid}, {"_id": 0, "created_at": 1, "name": 1, "sale_price": 1, "images": 1, "stock": 1})
        product_age_days = None
        if product and product.get("created_at"):
            try:
                c = datetime.fromisoformat(product["created_at"])
                product_age_days = (now - c).days
            except Exception:
                pass
        age = product_age_days if product_age_days is not None else 999
        recommend_ads = age <= 60 and r["sold"] >= min_sold
        out.append({
            "product_id": pid,
            "product_name": (product or {}).get("name") or r.get("product_name") or "—",
            "sold_in_window": r["sold"],
            "revenue": round(r["revenue"], 2),
            "product_age_days": product_age_days,
            "window_days": window_days,
            "stock": (product or {}).get("stock"),
            "image": ((product or {}).get("images") or [None])[0] if (product or {}).get("images") else None,
            "recommend_ads": recommend_ads,
        })
    return {"items": out, "window_days": window_days, "min_sold": min_sold}


# =============================================================================
# Üretici performans (FAZ 7 potansiyel iyileştirme)
# =============================================================================

@router.get("/manufacturer-performance")
async def manufacturer_performance(current_user: dict = Depends(require_admin)):
    """Üretici bazında ortalama gecikme, sipariş adedi ve +/-% fark.
    Skor: 100 başlangıç, her gün gecikme -3, |qty_diff| -0.5.
    """
    pipeline = [
        {"$match": {"manufacturer_id": {"$ne": None, "$exists": True}}},
        {"$group": {
            "_id": "$manufacturer_id",
            "name": {"$first": "$manufacturer_name"},
            "rows": {"$sum": 1},
            "avg_delay": {"$avg": "$delay_days"},
            "max_delay": {"$max": "$delay_days"},
            "avg_qty_diff": {"$avg": "$qty_diff_pct"},
            "delivered_count": {"$sum": {"$cond": [{"$ne": ["$delivered_qty", 0]}, 1, 0]}},
        }},
        {"$sort": {"avg_delay": 1}},
    ]
    out = []
    async for r in db.production_plan.aggregate(pipeline):
        avg_delay = r.get("avg_delay")
        avg_qty = r.get("avg_qty_diff")
        score = 100
        if avg_delay is not None:
            score -= max(0, avg_delay) * 3
        if avg_qty is not None:
            score -= abs(avg_qty) * 0.5
        score = max(0, round(score, 1))
        out.append({
            "manufacturer_id": r["_id"],
            "name": r.get("name") or "—",
            "rows": r["rows"],
            "delivered": r.get("delivered_count", 0),
            "avg_delay_days": round(avg_delay, 1) if avg_delay is not None else None,
            "max_delay_days": r.get("max_delay"),
            "avg_qty_diff_pct": round(avg_qty, 1) if avg_qty is not None else None,
            "score": score,
        })
    out.sort(key=lambda x: -x["score"])
    return {"items": out}


# ============================================================================
# EK RAPORLAR — İl/İlçe, Kaynak (Instagram/Google/Pazaryeri), Uzun süredir satılmayan
# ============================================================================

@router.get("/by-location")
async def sales_by_location(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group: str = Query("city", regex="^(city|district)$"),
    source: Optional[str] = Query(None, description="all|site|trendyol|hepsiburada|temu"),
    limit: int = Query(100, ge=1, le=1000),
    current_user: dict = Depends(require_admin),
):
    """Satışları İL (city) veya İLÇE (district) bazında gruplar. Tarih + kaynak filtresi."""
    s, e = _iso_range(start_date, end_date)
    field = "$shipping_address.city" if group == "city" else "$shipping_address.district"
    gid = {"loc": field}
    if group == "district":
        gid["city"] = "$shipping_address.city"
    pipeline = [
        {"$match": _base_match(s, e, source)},
        {"$group": {
            "_id": gid,
            "orders": {"$sum": 1},
            "revenue": {"$sum": {"$ifNull": ["$total", 0]}},
            "items": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": limit},
    ]
    rows = []
    async for r in db.orders.aggregate(pipeline):
        loc = (r["_id"].get("loc") or "").strip() or "Bilinmiyor"
        row = {"location": loc, "orders": r["orders"], "revenue": round(r["revenue"], 2), "items": r["items"]}
        if group == "district":
            row["city"] = (r["_id"].get("city") or "").strip()
        rows.append(row)
    return {
        "group": group,
        "rows": rows,
        "totals": {
            "orders": sum(x["orders"] for x in rows),
            "revenue": round(sum(x["revenue"] for x in rows), 2),
        },
    }


# Kaynak kısaltmaları → tek kanal. ig=instagram, fb=meta, gads=google… (aynı kanal ayrı satır
# olmasın diye). TAM değer eşleşmesiyle uygulanır (substring değil — "ig" pek çok kelimede geçer).
_CHANNEL_ALIASES = {
    "ig": "instagram", "insta": "instagram", "instagram": "instagram", "instagramshop": "instagram",
    "ig_shopping": "instagram", "instagram_shop": "instagram", "instagram-feed": "instagram", "igshopping": "instagram",
    "fb": "meta", "facebook": "meta", "meta": "meta", "fb_ig": "meta",
    "gl": "google", "google": "google", "gads": "google", "adwords": "google", "googleads": "google",
    "google_ads": "google", "google-ads": "google", "cpc": "google",
    "tt": "tiktok", "tiktok": "tiktok",
    "yt": "youtube", "youtube": "youtube",
    "pin": "pinterest", "pinterest": "pinterest",
    "eposta": "email", "e-posta": "email", "email": "email", "mail": "email", "sms": "sms",
    "referral": "referral", "direct": "direct", "organic": "organic",
}


def _channel_label(idv: dict) -> str:
    """Bir siparişin satış kanalını tek etikete indirger: pazaryeri > sosyal kaynak > direct.
    'ig'/'insta' gibi kısaltmalar 'instagram'a, 'fb' 'meta'ya vb. normalize edilir → aynı kanal
    tek satırda toplanır."""
    pf = (idv.get("platform") or "").strip().lower()
    mk = (idv.get("marketplace") or "").strip().lower()
    for m in _MARKETPLACES:
        if pf == m or mk == m:
            return m
    src = (idv.get("src") or "").strip().lower()
    ch = (idv.get("channel") or "").strip().lower()
    # 1) TAM değer alias'ı (ig=instagram gibi kısaltmalar) — hem src hem channel denenir.
    for v in (src, ch):
        if v in _CHANNEL_ALIASES:
            return _CHANNEL_ALIASES[v]
    # 2) İçerik taraması: tam kanal adı metnin içinde geçiyorsa (utm_source=instagram_stories vb.)
    blob = f"{src} {ch}"
    for k in ("instagram", "google", "facebook", "tiktok", "meta", "youtube", "pinterest", "email", "sms"):
        if k in blob:
            return "meta" if k in ("facebook", "meta") else k
    if src or ch:
        return src or ch
    return "direct"


@router.get("/by-source")
async def sales_by_source(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    """Satışları KANAL bazında gruplar: pazaryerleri (Trendyol/HB/Temu) + site trafiği kaynağı
    (Instagram/Google/Meta/direct) — attribution.source/channel'dan türetilir."""
    s, e = _iso_range(start_date, end_date)
    pipeline = [
        {"$match": {"created_at": {"$gte": s, "$lte": e}, "status": {"$nin": _EXCLUDED_STATUSES}}},
        {"$group": {
            "_id": {
                "platform": {"$ifNull": ["$platform", ""]},
                "marketplace": {"$ifNull": ["$marketplace", ""]},
                "src": {"$ifNull": ["$attribution.source", ""]},
                "channel": {"$ifNull": ["$attribution.channel", ""]},
            },
            "orders": {"$sum": 1},
            "revenue": {"$sum": {"$ifNull": ["$total", 0]}},
        }},
    ]
    agg: dict = {}
    async for r in db.orders.aggregate(pipeline):
        label = _channel_label(r["_id"])
        a = agg.setdefault(label, {"orders": 0, "revenue": 0.0})
        a["orders"] += r["orders"]
        a["revenue"] += r["revenue"] or 0
    rows = [{"channel": k, "orders": v["orders"], "revenue": round(v["revenue"], 2)} for k, v in agg.items()]
    rows.sort(key=lambda x: -x["revenue"])
    return {
        "rows": rows,
        "totals": {
            "orders": sum(x["orders"] for x in rows),
            "revenue": round(sum(x["revenue"] for x in rows), 2),
        },
    }


@router.get("/never-sold")
async def never_sold(
    days: int = Query(90, ge=1, le=3650),
    limit: int = Query(500, ge=1, le=5000),
    current_user: dict = Depends(require_admin),
):
    """Son N günde HİÇ satılmayan aktif ürünler (uzun süredir satış yok). Stok değerine göre sıralı."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    sold = set()
    pipeline = [
        {"$match": {"created_at": {"$gte": cutoff}, "status": {"$nin": _EXCLUDED_STATUSES}}},
        {"$unwind": {"path": "$items", "preserveNullAndEmptyArrays": False}},
        {"$group": {"_id": {"$ifNull": ["$items.product_id", "$items.id"]}}},
    ]
    async for r in db.orders.aggregate(pipeline):
        if r.get("_id"):
            sold.add(str(r["_id"]))
    rows = []
    async for p in db.products.find(
        {"is_active": True, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "stock": 1, "price": 1, "sale_price": 1,
         "created_at": 1, "stock_code": 1, "images": 1, "variants": 1},
    ):
        if str(p.get("id")) in sold:
            continue
        variants = p.get("variants") or []
        # Stok: varyant varsa varyant stoklarının TOPLAMI (top-level 'stock' varyantlıda 0 olabilir).
        v_stock = sum(int(v.get("stock") or 0) for v in variants)
        stock = v_stock if variants else int(p.get("stock") or 0)
        if not variants and stock == 0:
            stock = int(p.get("stock") or 0)
        price = float(p.get("sale_price") or p.get("price") or 0)
        # Bedenler: stok bilgisiyle birlikte (S:3, M:0, L:5 gibi)
        sizes = []
        for v in variants:
            sz = (v.get("size") or "").strip()
            if sz:
                sizes.append(f"{sz}:{int(v.get('stock') or 0)}")
        img = ""
        try:
            im0 = (p.get("images") or [None])[0]
            img = im0.get("url") if isinstance(im0, dict) else (im0 or "")
        except Exception:
            img = ""
        rows.append({
            "product_id": p.get("id"),
            "name": p.get("name") or "(isimsiz ürün)",
            "stock_code": p.get("stock_code") or "",
            "stock": stock,
            "sizes": ", ".join(sizes) if sizes else "—",
            "variant_count": len(variants),
            "price": price,
            "stock_value": round(stock * price, 2),
            "created_at": p.get("created_at") or "",
            "image": img,
        })
    rows.sort(key=lambda x: -x["stock_value"])
    total_value = round(sum(x["stock_value"] for x in rows), 2)
    return {"days": days, "count": len(rows), "total_stock_value": total_value, "items": rows[:limit]}


# ============================================================================
# EK RAPORLAR 2 — Saatlik, Ödeme Tipi, Kupon Performansı, Yeni/Tekrar Eden Müşteri
# ============================================================================

@router.get("/by-hour")
async def sales_by_hour(
    start_date: Optional[str] = None, end_date: Optional[str] = None,
    source: Optional[str] = None, current_user: dict = Depends(require_admin),
):
    """Günün SAATLERİNE göre satış dağılımı (TR saati, +03:00). En yoğun saatler."""
    s, e = _iso_range(start_date, end_date)
    pipeline = [
        {"$match": _base_match(s, e, source)},
        {"$group": {
            "_id": {"$dateToString": {"format": "%H", "date": {"$dateFromString": {"dateString": "$created_at"}}, "timezone": "+03:00"}},
            "orders": {"$sum": 1},
            "revenue": {"$sum": {"$ifNull": ["$total", 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    by = {f"{h:02d}": {"orders": 0, "revenue": 0.0} for h in range(24)}
    async for r in db.orders.aggregate(pipeline):
        by[r["_id"]] = {"orders": r["orders"], "revenue": round(r["revenue"], 2)}
    rows = [{"hour": h, "orders": v["orders"], "revenue": v["revenue"]} for h, v in sorted(by.items())]
    return {"rows": rows, "totals": {"orders": sum(x["orders"] for x in rows), "revenue": round(sum(x["revenue"] for x in rows), 2)}}


_PM_LABELS = {
    "transfer": "Havale/EFT", "havale": "Havale/EFT", "bank_transfer": "Havale/EFT",
    "eft": "Havale/EFT", "havale_eft": "Havale/EFT", "banka_havale": "Havale/EFT",
    "card": "Kredi/Banka Kartı", "credit_card": "Kredi/Banka Kartı", "iyzico": "Kredi/Banka Kartı",
    "iyzipay": "Kredi/Banka Kartı", "cod": "Kapıda Ödeme", "kapida": "Kapıda Ödeme",
}


@router.get("/by-payment")
async def sales_by_payment(
    start_date: Optional[str] = None, end_date: Optional[str] = None,
    source: Optional[str] = None, current_user: dict = Depends(require_admin),
):
    """Ödeme tipine göre satış (Havale / Kart / Kapıda vb.)."""
    s, e = _iso_range(start_date, end_date)
    pipeline = [
        {"$match": _base_match(s, e, source)},
        {"$group": {"_id": {"$ifNull": ["$payment_method", ""]}, "orders": {"$sum": 1}, "revenue": {"$sum": {"$ifNull": ["$total", 0]}}}},
    ]
    agg = {}
    async for r in db.orders.aggregate(pipeline):
        label = _PM_LABELS.get(str(r["_id"]).strip().lower(), (str(r["_id"]).strip() or "Belirtilmemiş"))
        a = agg.setdefault(label, {"orders": 0, "revenue": 0.0})
        a["orders"] += r["orders"]; a["revenue"] += r["revenue"] or 0
    rows = [{"method": k, "orders": v["orders"], "revenue": round(v["revenue"], 2)} for k, v in agg.items()]
    rows.sort(key=lambda x: -x["revenue"])
    return {"rows": rows, "totals": {"orders": sum(x["orders"] for x in rows), "revenue": round(sum(x["revenue"] for x in rows), 2)}}


@router.get("/coupon-performance")
async def coupon_performance(
    start_date: Optional[str] = None, end_date: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    """Kupon performansı: her kupon kaç siparişte kullanıldı, ne kadar indirim + ciro getirdi."""
    s, e = _iso_range(start_date, end_date)
    pipeline = [
        {"$match": {"created_at": {"$gte": s, "$lte": e}, "status": {"$nin": _EXCLUDED_STATUSES},
                    "coupon_code": {"$nin": [None, ""]}}},
        {"$group": {
            "_id": "$coupon_code",
            "orders": {"$sum": 1},
            "revenue": {"$sum": {"$ifNull": ["$total", 0]}},
            "discount": {"$sum": {"$ifNull": ["$discount", {"$ifNull": ["$discount_amount", 0]}]}},
        }},
        {"$sort": {"orders": -1}},
    ]
    rows = []
    async for r in db.orders.aggregate(pipeline):
        rows.append({"coupon": r["_id"], "orders": r["orders"], "revenue": round(r["revenue"], 2), "discount": round(r.get("discount") or 0, 2)})
    return {"rows": rows, "totals": {
        "orders": sum(x["orders"] for x in rows),
        "revenue": round(sum(x["revenue"] for x in rows), 2),
        "discount": round(sum(x["discount"] for x in rows), 2),
    }}


@router.get("/customer-type")
async def customer_type(
    start_date: Optional[str] = None, end_date: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    """Bu aralıkta sipariş veren müşteriler: YENİ (ilk siparişi bu aralıkta) vs TEKRAR EDEN
    (daha önce de sipariş vermiş). Müşteri anahtarı: e-posta."""
    s, e = _iso_range(start_date, end_date)
    key = {"$toLower": {"$ifNull": ["$email", {"$ifNull": ["$shipping_address.email", "$user_id"]}]}}
    pipeline = [
        {"$match": {"status": {"$nin": _EXCLUDED_STATUSES}}},
        {"$group": {
            "_id": key,
            "firstOrder": {"$min": "$created_at"},
            "ordersInRange": {"$sum": {"$cond": [{"$and": [{"$gte": ["$created_at", s]}, {"$lte": ["$created_at", e]}]}, 1, 0]}},
            "revInRange": {"$sum": {"$cond": [{"$and": [{"$gte": ["$created_at", s]}, {"$lte": ["$created_at", e]}]}, {"$ifNull": ["$total", 0]}, 0]}},
        }},
        {"$match": {"ordersInRange": {"$gt": 0}}},
    ]
    new_c = ret_c = 0
    new_rev = ret_rev = 0.0
    new_ord = ret_ord = 0
    async for r in db.orders.aggregate(pipeline):
        is_new = (r.get("firstOrder") or "") >= s
        if is_new:
            new_c += 1; new_rev += r.get("revInRange") or 0; new_ord += r.get("ordersInRange") or 0
        else:
            ret_c += 1; ret_rev += r.get("revInRange") or 0; ret_ord += r.get("ordersInRange") or 0
    total_c = new_c + ret_c
    return {
        "new": {"customers": new_c, "orders": new_ord, "revenue": round(new_rev, 2)},
        "returning": {"customers": ret_c, "orders": ret_ord, "revenue": round(ret_rev, 2)},
        "repeat_rate": round((ret_c / total_c) * 100, 1) if total_c else 0,
    }
