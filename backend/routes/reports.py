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
