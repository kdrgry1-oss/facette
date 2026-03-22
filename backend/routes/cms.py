"""
CMS routes - Page blocks, homepage content management
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime, timezone

from .deps import db, logger, require_admin, generate_id

router = APIRouter(prefix="/page-blocks", tags=["CMS"])

@router.get("")
async def get_page_blocks(
    page: str = Query("home"),
    is_active: Optional[bool] = None
):
    """Get page blocks for a specific page"""
    query = {"page": page}
    if is_active is not None:
        query["is_active"] = is_active
    
    blocks = await db.page_blocks.find(query, {"_id": 0}).sort("sort_order", 1).to_list(50)
    return blocks

@router.get("/{block_id}")
async def get_page_block(block_id: str):
    """Get single page block"""
    block = await db.page_blocks.find_one({"id": block_id}, {"_id": 0})
    if not block:
        raise HTTPException(status_code=404, detail="Blok bulunamadı")
    return block

@router.post("")
async def create_page_block(
    block_data: dict,
    current_user: dict = Depends(require_admin)
):
    """Create page block (admin only)"""
    block = {
        "id": generate_id(),
        "type": block_data.get("type", "hero_slider"),
        "title": block_data.get("title", ""),
        "images": block_data.get("images", []),
        "links": block_data.get("links", []),
        "settings": block_data.get("settings", {}),
        "page": block_data.get("page", "home"),
        "sort_order": block_data.get("sort_order", 0),
        "is_active": block_data.get("is_active", True),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.page_blocks.insert_one(block)
    return {"id": block["id"], "message": "Blok oluşturuldu"}

@router.put("/{block_id}")
async def update_page_block(
    block_id: str,
    block_data: dict,
    current_user: dict = Depends(require_admin)
):
    """Update page block (admin only)"""
    existing = await db.page_blocks.find_one({"id": block_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Blok bulunamadı")
    
    block_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.page_blocks.update_one({"id": block_id}, {"$set": block_data})
    return {"message": "Blok güncellendi"}

@router.delete("/{block_id}")
async def delete_page_block(
    block_id: str,
    current_user: dict = Depends(require_admin)
):
    """Delete page block (admin only)"""
    result = await db.page_blocks.delete_one({"id": block_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Blok bulunamadı")
    return {"message": "Blok silindi"}
