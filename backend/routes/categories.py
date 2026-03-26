"""
Category routes - CRUD
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime, timezone
import re

from .deps import db, logger, require_admin, generate_id, generate_short_id

router = APIRouter(prefix="/categories", tags=["Categories"])

def generate_slug(name: str) -> str:
    slug = name.lower()
    tr_map = {'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c'}
    for tr, en in tr_map.items():
        slug = slug.replace(tr, en)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug).strip('-')
    return slug

@router.get("")
async def get_categories(
    parent_id: Optional[str] = None,
    is_active: Optional[bool] = None
):
    """Get categories"""
    query = {}
    if parent_id is not None:
        query["parent_id"] = parent_id
    if is_active is not None:
        query["is_active"] = is_active
    
    categories = await db.categories.find(query, {"_id": 0}).to_list(500)
    
    # Build hierarchical full_name
    cat_dict = {c["id"]: c for c in categories}
    for c in categories:
        path = []
        curr = c
        while curr:
            path.append(curr.get("name", ""))
            parent_id = curr.get("parent_id")
            if parent_id and parent_id in cat_dict and parent_id != curr.get("id"):
                curr = cat_dict[parent_id]
            else:
                curr = None
        c["full_name"] = " > ".join(reversed(path))

    # Sort: by sort_order if available, else by full_name
    categories.sort(key=lambda c: (c.get("sort_order") or 999, c.get("full_name", "")))
    return categories

@router.get("/{category_id}")
async def get_category(category_id: str):
    """Get single category"""
    category = await db.categories.find_one(
        {"$or": [{"id": category_id}, {"slug": category_id}]},
        {"_id": 0}
    )
    if not category:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı")
    return category

@router.post("")
async def create_category(
    category_data: dict,
    current_user: dict = Depends(require_admin)
):
    """Create category (admin only)"""
    category = {
        "id": await generate_short_id("categories"),
        "name": category_data.get("name", ""),
        "slug": category_data.get("slug") or generate_slug(category_data.get("name", "")),
        "description": category_data.get("description", ""),
        "image": category_data.get("image", ""),
        "image_url": category_data.get("image_url", ""),
        "parent_id": category_data.get("parent_id"),
        "trendyol_category_id": category_data.get("trendyol_category_id"),
        "hepsiburada_category_id": category_data.get("hepsiburada_category_id"),
        "amazon_category_id": category_data.get("amazon_category_id"),
        "attribute_mapping": category_data.get("attribute_mapping", {}),
        "sort_order": category_data.get("sort_order", 0),
        "is_active": category_data.get("is_active", True),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.categories.insert_one(category)
    return {"id": category["id"], "message": "Kategori oluşturuldu"}

@router.put("/{category_id}")
async def update_category(
    category_id: str,
    category_data: dict,
    current_user: dict = Depends(require_admin)
):
    """Update category (admin only)"""
    existing = await db.categories.find_one({"id": category_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı")
    
    if category_data.get("name"):
        category_data["slug"] = generate_slug(category_data["name"])
    
    category_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.categories.update_one({"id": category_id}, {"$set": category_data})
    return {"message": "Kategori güncellendi"}

@router.delete("/{category_id}")
async def delete_category(
    category_id: str,
    current_user: dict = Depends(require_admin)
):
    """Delete category (admin only)"""
    result = await db.categories.delete_one({"id": category_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı")
    return {"message": "Kategori silindi"}
