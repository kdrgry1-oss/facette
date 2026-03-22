"""
Customer account routes - Profile, addresses, orders
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from datetime import datetime, timezone

from .deps import db, logger, get_current_user, require_auth, generate_id

router = APIRouter(tags=["Customer Account"])

@router.get("/my-orders")
async def get_my_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(require_auth)
):
    """Get current user's orders"""
    skip = (page - 1) * limit
    query = {"user_id": current_user.get("id")}
    
    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.orders.count_documents(query)
    
    return {
        "orders": orders,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

@router.put("/users/me")
async def update_my_profile(
    profile_data: dict,
    current_user: dict = Depends(require_auth)
):
    """Update current user's profile"""
    allowed_fields = ["first_name", "last_name", "phone"]
    update_data = {k: v for k, v in profile_data.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.users.update_one(
        {"id": current_user.get("id")},
        {"$set": update_data}
    )
    
    return {"success": True, "message": "Profil güncellendi"}

@router.get("/my-addresses")
async def get_my_addresses(current_user: dict = Depends(require_auth)):
    """Get current user's addresses"""
    addresses = await db.addresses.find(
        {"user_id": current_user.get("id")}, 
        {"_id": 0}
    ).to_list(20)
    
    return {"addresses": addresses}

@router.post("/addresses")
async def create_address(
    address_data: dict,
    current_user: dict = Depends(require_auth)
):
    """Create new address"""
    address = {
        "id": generate_id(),
        "user_id": current_user.get("id"),
        "title": address_data.get("title", ""),
        "first_name": address_data.get("first_name", ""),
        "last_name": address_data.get("last_name", ""),
        "phone": address_data.get("phone", ""),
        "address": address_data.get("address", ""),
        "city": address_data.get("city", ""),
        "district": address_data.get("district", ""),
        "postal_code": address_data.get("postal_code", ""),
        "is_default": address_data.get("is_default", False),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # If setting as default, unset others
    if address["is_default"]:
        await db.addresses.update_many(
            {"user_id": current_user.get("id")},
            {"$set": {"is_default": False}}
        )
    
    await db.addresses.insert_one(address)
    
    return {"success": True, "address_id": address["id"]}

@router.put("/addresses/{address_id}")
async def update_address(
    address_id: str,
    address_data: dict,
    current_user: dict = Depends(require_auth)
):
    """Update address"""
    # Verify ownership
    address = await db.addresses.find_one({
        "id": address_id, 
        "user_id": current_user.get("id")
    })
    
    if not address:
        raise HTTPException(status_code=404, detail="Adres bulunamadı")
    
    # If setting as default, unset others
    if address_data.get("is_default"):
        await db.addresses.update_many(
            {"user_id": current_user.get("id"), "id": {"$ne": address_id}},
            {"$set": {"is_default": False}}
        )
    
    allowed_fields = ["title", "first_name", "last_name", "phone", "address", "city", "district", "postal_code", "is_default"]
    update_data = {k: v for k, v in address_data.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.addresses.update_one({"id": address_id}, {"$set": update_data})
    
    return {"success": True}

@router.delete("/addresses/{address_id}")
async def delete_address(
    address_id: str,
    current_user: dict = Depends(require_auth)
):
    """Delete address"""
    result = await db.addresses.delete_one({
        "id": address_id,
        "user_id": current_user.get("id")
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Adres bulunamadı")
    
    return {"success": True}
