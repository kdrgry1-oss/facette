"""
Order routes - CRUD, checkout, tracking
"""
from fastapi import APIRouter, HTTPException, Query, Depends, Response
from typing import List, Optional
from datetime import datetime, timezone
import time

from .deps import db, logger, get_current_user, require_admin, generate_id

router = APIRouter(prefix="/orders", tags=["Orders"])

def generate_order_number() -> str:
    return f"FC{int(time.time())}"

@router.get("")
async def get_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
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
    current_user: dict = Depends(require_admin)
):
    """Get orders with pagination (admin only)"""
    skip = (page - 1) * limit
    query = {}
    
    if status:
        query["status"] = status
    if phone:
        query["shipping_address.phone"] = {"$regex": phone, "$options": "i"}
    if email:
        query["shipping_address.email"] = {"$regex": email, "$options": "i"}
    if order_number:
        query["order_number"] = {"$regex": order_number, "$options": "i"}
    if cargo_tracking:
        query["cargo_tracking"] = {"$regex": cargo_tracking, "$options": "i"}
    if payment_method:
        query["payment_method"] = payment_method
    if platform:
        query["platform"] = platform
        
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
            {"shipping_address.first_name": {"$regex": search, "$options": "i"}},
            {"shipping_address.last_name": {"$regex": search, "$options": "i"}},
            {"shipping_address.phone": {"$regex": search, "$options": "i"}},
            {"shipping_address.email": {"$regex": search, "$options": "i"}}
        ]
    
    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.orders.count_documents(query)
    
    return {
        "orders": orders,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

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
    
    return order

@router.post("")
async def create_order(
    order_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Create new order"""
    order = {
        "id": generate_id(),
        "order_number": generate_order_number(),
        "user_id": current_user.get("id") if current_user else None,
        "items": order_data.get("items", []),
        "shipping_address": order_data.get("shipping_address", {}),
        "billing_address": order_data.get("billing_address") or order_data.get("shipping_address", {}),
        "subtotal": float(order_data.get("subtotal", 0)),
        "shipping_cost": float(order_data.get("shipping_cost", 0)),
        "discount": float(order_data.get("discount", 0)),
        "total": float(order_data.get("total", 0)),
        "payment_method": order_data.get("payment_method", "credit_card"),
        "payment_status": "pending",
        "status": "pending",
        "notes": order_data.get("notes", ""),
        "platform": order_data.get("platform", "facette"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.orders.insert_one(order)
    logger.info(f"Order created: {order['order_number']}")
    
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
    valid_statuses = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Geçersiz durum. Geçerli değerler: {valid_statuses}")
    
    result = await db.orders.update_one(
        {"id": order_id},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    return {"message": f"Sipariş durumu '{status}' olarak güncellendi"}

@router.delete("/{order_id}")
async def delete_order(
    order_id: str,
    current_user: dict = Depends(require_admin)
):
    """Delete order (admin only)"""
    result = await db.orders.delete_one({"id": order_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    return {"message": "Sipariş silindi"}
