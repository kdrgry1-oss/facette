"""
Admin routes - Dashboard, stats, settings
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from datetime import datetime, timezone, timedelta

from .deps import db, logger, require_admin

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/dashboard-stats")
async def get_dashboard_stats(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_admin)
):
    """Get dashboard statistics for admin"""
    try:
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        prev_start = start_date - timedelta(days=days)
        
        # Get totals
        total_orders = await db.orders.count_documents({})
        total_products = await db.products.count_documents({"is_active": True})
        total_customers = await db.users.count_documents({"is_admin": {"$ne": True}})
        
        # Get orders in date range
        orders_in_range = await db.orders.find({
            "created_at": {"$gte": start_date.isoformat()}
        }, {"_id": 0}).to_list(1000)
        
        # Calculate revenue
        total_revenue = sum(o.get("total", 0) for o in orders_in_range)
        
        # Previous period for comparison
        prev_orders = await db.orders.find({
            "created_at": {
                "$gte": prev_start.isoformat(),
                "$lt": start_date.isoformat()
            }
        }, {"_id": 0}).to_list(1000)
        prev_revenue = sum(o.get("total", 0) for o in prev_orders)
        
        # Growth calculations
        growth_orders = ((len(orders_in_range) - len(prev_orders)) / max(len(prev_orders), 1)) * 100 if prev_orders else 0
        growth_revenue = ((total_revenue - prev_revenue) / max(prev_revenue, 1)) * 100 if prev_revenue else 0
        
        # Today's stats
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        orders_today = [o for o in orders_in_range if o.get("created_at", "") >= today_start.isoformat()]
        revenue_today = sum(o.get("total", 0) for o in orders_today)
        
        # Order status breakdown
        status_breakdown = {}
        for order in orders_in_range:
            status = order.get("status", "pending")
            status_breakdown[status] = status_breakdown.get(status, 0) + 1
        
        # Pending and shipped counts
        pending_orders = await db.orders.count_documents({"status": "pending"})
        shipped_orders = await db.orders.count_documents({"status": "shipped"})
        
        # Recent orders
        recent_orders = await db.orders.find(
            {}, {"_id": 0, "id": 1, "order_number": 1, "total": 1, "status": 1, "created_at": 1}
        ).sort("created_at", -1).limit(5).to_list(5)
        
        # Top selling products
        pipeline = [
            {"$unwind": "$items"},
            {"$group": {
                "_id": "$items.name",
                "sold": {"$sum": "$items.quantity"},
                "revenue": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}}
            }},
            {"$sort": {"sold": -1}},
            {"$limit": 5}
        ]
        top_products_cursor = db.orders.aggregate(pipeline)
        top_products = []
        async for p in top_products_cursor:
            top_products.append({
                "name": p["_id"],
                "sold": p["sold"],
                "revenue": p["revenue"]
            })
        
        return {
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "total_products": total_products,
            "total_customers": total_customers,
            "pending_orders": pending_orders,
            "shipped_orders": shipped_orders,
            "orders_today": len(orders_today),
            "revenue_today": revenue_today,
            "growth_orders": round(growth_orders, 1),
            "growth_revenue": round(growth_revenue, 1),
            "recent_orders": recent_orders,
            "top_products": top_products,
            "order_status_breakdown": status_breakdown
        }
        
    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users")
async def get_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    current_user: dict = Depends(require_admin)
):
    """Get users list (admin only)"""
    skip = (page - 1) * limit
    query = {}
    
    if search:
        query["$or"] = [
            {"email": {"$regex": search, "$options": "i"}},
            {"first_name": {"$regex": search, "$options": "i"}},
            {"last_name": {"$regex": search, "$options": "i"}}
        ]
    
    users = await db.users.find(query, {"_id": 0, "password": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.users.count_documents(query)
    
    return {
        "users": users,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }
