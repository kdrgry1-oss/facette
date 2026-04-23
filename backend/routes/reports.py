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

from .deps import db, require_admin


router = APIRouter(prefix="/admin/reports", tags=["admin-reports"])


def _iso_range(start: Optional[str], end: Optional[str], days_default: int = 30):
    if start and end:
        return start, end
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=days_default)).isoformat(), now.isoformat()


@router.get("/sales")
async def sales(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: str = Query("day", regex="^(day|week|month)$"),
    current_user: dict = Depends(require_admin),
):
    s, e = _iso_range(start_date, end_date)
    fmt = {"day": "%Y-%m-%d", "week": "%Y-%V", "month": "%Y-%m"}[group_by]
    pipeline = [
        {"$match": {"created_at": {"$gte": s, "$lte": e}, "status": {"$ne": "cancelled"}}},
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


@router.get("/products/top")
async def top_products(
    limit: int = Query(20, ge=1, le=100),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    s, e = _iso_range(start_date, end_date, days_default=90)
    pipeline = [
        {"$match": {"created_at": {"$gte": s, "$lte": e}, "status": {"$ne": "cancelled"}}},
        {"$unwind": {"path": "$items", "preserveNullAndEmptyArrays": False}},
        {
            "$group": {
                "_id": {"pid": "$items.product_id", "name": "$items.name"},
                "qty": {"$sum": {"$ifNull": ["$items.quantity", 1]}},
                "revenue": {"$sum": {"$multiply": [{"$ifNull": ["$items.price", 0]}, {"$ifNull": ["$items.quantity", 1]}]}},
                "orders": {"$sum": 1},
            }
        },
        {"$sort": {"revenue": -1}},
        {"$limit": limit},
    ]
    out = []
    async for r in db.orders.aggregate(pipeline):
        out.append({"product_id": r["_id"].get("pid"), "name": r["_id"].get("name"), "qty": r["qty"], "revenue": round(r["revenue"], 2), "orders": r["orders"]})
    return {"items": out}


@router.get("/categories")
async def category_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    s, e = _iso_range(start_date, end_date, days_default=90)
    # Join items -> products -> category
    pipeline = [
        {"$match": {"created_at": {"$gte": s, "$lte": e}, "status": {"$ne": "cancelled"}}},
        {"$unwind": "$items"},
        {"$lookup": {"from": "products", "localField": "items.product_id", "foreignField": "id", "as": "p"}},
        {"$unwind": {"path": "$p", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {"from": "categories", "localField": "p.category_id", "foreignField": "id", "as": "c"}},
        {"$unwind": {"path": "$c", "preserveNullAndEmptyArrays": True}},
        {
            "$group": {
                "_id": {"$ifNull": ["$c.name", "(Kategorisiz)"]},
                "qty": {"$sum": {"$ifNull": ["$items.quantity", 1]}},
                "revenue": {"$sum": {"$multiply": [{"$ifNull": ["$items.price", 0]}, {"$ifNull": ["$items.quantity", 1]}]}},
            }
        },
        {"$sort": {"revenue": -1}},
    ]
    out = []
    async for r in db.orders.aggregate(pipeline):
        out.append({"category": r["_id"], "qty": r["qty"], "revenue": round(r["revenue"], 2)})
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
    current_user: dict = Depends(require_admin),
):
    s, e = _iso_range(start_date, end_date)
    pipeline = [
        {"$match": {"created_at": {"$gte": s, "$lte": e}, "status": {"$ne": "cancelled"}}},
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
            "product_name": {"$first": "$items.name"},
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
            "product_name": {"$first": "$items.name"},
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
