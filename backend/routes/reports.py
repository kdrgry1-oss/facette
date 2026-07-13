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


def _base_match(s: str, e: str, source: Optional[str] = None) -> dict:
    """Tüm satış raporlarının ortak $match'i: tarih aralığı + iptal/iade hariç + kaynak."""
    m = {"created_at": {"$gte": s, "$lte": e}, "status": {"$nin": _EXCLUDED_STATUSES}}
    sc = _source_cond(source)
    if sc:
        m.update(sc)
    return m


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
        async for p in db.products.find(q, {"_id": 0, "id": 1, "name": 1, "stock": 1, "variants": 1, "barcode": 1}):
            variants = p.get("variants") or []
            stock = sum(int(v.get("stock") or 0) for v in variants) if variants else int(p.get("stock") or 0)
            info = {"id": str(p.get("id")), "name": p.get("name") or "", "stock": stock}
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
            }
        _q = int(r["qty"])
        m["qty"] += _q
        m["revenue"] += float(r["revenue"])
        m["orders"] += int(r["orders"])
        _sz = (r["_id"].get("sz") or "").strip() or "—"
        m["_sizes"][_sz] = m["_sizes"].get(_sz, 0) + _q
        _pl = (r["_id"].get("plat") or "site").strip().lower() or "site"
        m["_plats"][_pl] = m["_plats"].get(_pl, 0) + _q
    out = []
    for m in merged.values():
        _sizes = sorted(m.pop("_sizes").items(), key=lambda x: -x[1])
        _plats = sorted(m.pop("_plats").items(), key=lambda x: -x[1])
        out.append({
            **m,
            "revenue": round(m["revenue"], 2),
            "best_size": _sizes[0][0] if _sizes else "—",
            "size_breakdown": [{"size": k, "qty": v} for k, v in _sizes],
            "top_platform": _plats[0][0] if _plats else "site",
            "platform_breakdown": [{"platform": k, "qty": v} for k, v in _plats],
        })
    out.sort(key=lambda x: -x["revenue"])
    return {"items": out[:limit]}


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
    # Low-stock & out-of-stock
    low = await db.products.find({"stock": {"$gt": 0, "$lte": 5}}, {"_id": 0, "id": 1, "name": 1, "stock_code": 1, "stock": 1}).sort("stock", 1).to_list(100)
    out_of_stock = await db.products.find({"stock": {"$lte": 0}}, {"_id": 0, "id": 1, "name": 1, "stock_code": 1, "stock": 1}).to_list(200)
    total_value_pipeline = [
        {"$group": {"_id": None, "units": {"$sum": {"$ifNull": ["$stock", 0]}}, "value": {"$sum": {"$multiply": [{"$ifNull": ["$stock", 0]}, {"$ifNull": ["$price", 0]}]}}}},
    ]
    tot = None
    async for r in db.products.aggregate(total_value_pipeline):
        tot = r
    return {
        "low_stock": low,
        "out_of_stock": out_of_stock,
        "totals": {"units": tot["units"] if tot else 0, "value": round(tot["value"], 2) if tot else 0},
    }


@router.get("/payments")
async def payment_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = Query(None, description="all|site|trendyol|hepsiburada|temu"),
    current_user: dict = Depends(require_admin),
):
    s, e = _iso_range(start_date, end_date)
    pipeline = [
        {"$match": _base_match(s, e, source)},
        {"$group": {"_id": "$payment_method", "orders": {"$sum": 1}, "revenue": {"$sum": {"$ifNull": ["$total", 0]}}}},
        {"$sort": {"revenue": -1}},
    ]
    out = []
    async for r in db.orders.aggregate(pipeline):
        out.append({"method": r["_id"] or "—", "orders": r["orders"], "revenue": round(r["revenue"], 2)})
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
