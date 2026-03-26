from fastapi import APIRouter, Depends
from typing import Dict, Any

from .deps import db, require_admin

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.get("")
async def get_settings():
    """Get global settings"""
    settings = await db.settings.find_one({"id": "main"}, {"_id": 0})
    if not settings:
        settings = {
            "id": "main",
            "site_name": "FACETTE",
            "logo_url": "",
            "free_shipping_limit": 500,
            "rotating_texts": [],
            "contact_email": "",
            "contact_phone": "",
            "address": "",
            "payment_methods": {"credit_card": True, "bank_transfer": True, "cash_on_delivery": True},
            "barcode_range_start": "",
            "barcode_range_end": "",
            "default_vat_rate": 10,
            "trendyol_markup": 0
        }
        await db.settings.insert_one(settings.copy())
    return settings

@router.post("")
async def update_settings(
    settings_data: dict,
    current_user: dict = Depends(require_admin)
):
    """Update global settings"""
    settings_data.pop("_id", None)
    existing = await db.settings.find_one({"id": "main"})
    if not existing:
        settings_data["id"] = "main"
        await db.settings.insert_one(settings_data)
    else:
        await db.settings.update_one({"id": "main"}, {"$set": settings_data})
    
    return {"message": "Ayarlar güncellendi"}
