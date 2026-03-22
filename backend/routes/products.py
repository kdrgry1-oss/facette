"""
Product routes - CRUD, search, filtering
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from datetime import datetime, timezone
import re

from .deps import db, logger, get_current_user, require_admin, generate_id

router = APIRouter(prefix="/products", tags=["Products"])

def generate_slug(name: str) -> str:
    """Generate URL-friendly slug from name"""
    slug = name.lower()
    # Turkish character replacements
    tr_map = {'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c', 'İ': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c'}
    for tr, en in tr_map.items():
        slug = slug.replace(tr, en)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug

@router.get("")
async def get_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = Query("created_at"),
    order: str = Query("desc"),
    is_featured: Optional[bool] = None,
    is_new: Optional[bool] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None
):
    """Get products with filtering and pagination"""
    skip = (page - 1) * limit
    query = {"is_active": True}
    
    if category:
        query["$or"] = [
            {"category_name": {"$regex": category, "$options": "i"}},
            {"category_slug": category}
        ]
    
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"keywords": {"$regex": search, "$options": "i"}},
            {"stock_code": {"$regex": search, "$options": "i"}}
        ]
    
    if is_featured is not None:
        query["is_featured"] = is_featured
    
    if is_new is not None:
        query["is_new"] = is_new
    
    if min_price is not None:
        query["price"] = {"$gte": min_price}
    
    if max_price is not None:
        if "price" in query:
            query["price"]["$lte"] = max_price
        else:
            query["price"] = {"$lte": max_price}
    
    sort_order = -1 if order == "desc" else 1
    
    products = await db.products.find(query, {"_id": 0}).sort(sort, sort_order).skip(skip).limit(limit).to_list(limit)
    total = await db.products.count_documents(query)
    
    return {
        "products": products,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

@router.get("/{product_id}")
async def get_product(product_id: str):
    """Get single product by ID or slug"""
    product = await db.products.find_one(
        {"$or": [{"id": product_id}, {"slug": product_id}]},
        {"_id": 0}
    )
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return product

@router.post("")
async def create_product(
    product_data: dict,
    current_user: dict = Depends(require_admin)
):
    """Create new product (admin only)"""
    product = {
        "id": generate_id(),
        "name": product_data.get("name", ""),
        "slug": product_data.get("slug") or generate_slug(product_data.get("name", "")),
        "description": product_data.get("description", ""),
        "short_description": product_data.get("short_description", ""),
        "price": float(product_data.get("price", 0)),
        "sale_price": product_data.get("sale_price"),
        "category_name": product_data.get("category_name", ""),
        "brand": product_data.get("brand", "FACETTE"),
        "images": product_data.get("images", []),
        "variants": product_data.get("variants", []),
        "stock": int(product_data.get("stock", 0)),
        "stock_code": product_data.get("stock_code", ""),
        "barcode": product_data.get("barcode", ""),
        "sku": product_data.get("sku", ""),
        "is_active": product_data.get("is_active", True),
        "is_featured": product_data.get("is_featured", False),
        "is_new": product_data.get("is_new", False),
        "vat_rate": product_data.get("vat_rate", 20),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.products.insert_one(product)
    logger.info(f"Product created: {product['id']}")
    
    return {"id": product["id"], "message": "Ürün oluşturuldu"}

@router.put("/{product_id}")
async def update_product(
    product_id: str,
    product_data: dict,
    current_user: dict = Depends(require_admin)
):
    """Update product (admin only)"""
    existing = await db.products.find_one({"id": product_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    
    # Update slug if name changed
    if product_data.get("name") and product_data.get("name") != existing.get("name"):
        product_data["slug"] = generate_slug(product_data["name"])
    
    product_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.products.update_one({"id": product_id}, {"$set": product_data})
    
    return {"message": "Ürün güncellendi"}

@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    current_user: dict = Depends(require_admin)
):
    """Delete product (admin only)"""
    result = await db.products.delete_one({"id": product_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    
    return {"message": "Ürün silindi"}

@router.post("/{product_id}/toggle-active")
async def toggle_product_active(
    product_id: str,
    current_user: dict = Depends(require_admin)
):
    """Toggle product active status"""
    product = await db.products.find_one({"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    
    new_status = not product.get("is_active", True)
    await db.products.update_one(
        {"id": product_id},
        {"$set": {"is_active": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"is_active": new_status}

@router.get("/search/popular")
async def get_popular_searches():
    """Get popular search terms"""
    # In production, track and return actual popular searches
    return [
        {"term": "elbise", "count": 150},
        {"term": "bluz", "count": 120},
        {"term": "pantolon", "count": 100},
        {"term": "jean", "count": 90},
        {"term": "kazak", "count": 80},
    ]
