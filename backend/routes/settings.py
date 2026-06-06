from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from datetime import datetime, timezone
import re

from .deps import db, require_admin

router = APIRouter(prefix="/settings", tags=["Settings"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

@router.post("/maintenance/notify")
async def maintenance_notify_subscribe(payload: dict):
    """Public: bakım modu sırasında 'açılınca haber ver' e-posta toplama."""
    email = (payload.get("email") or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Geçerli bir e-posta adresi giriniz.")
    existing = await db.maintenance_subscribers.find_one({"email": email})
    if existing:
        return {"message": "E-posta adresiniz zaten kayıtlı. Açılınca size haber vereceğiz."}
    await db.maintenance_subscribers.insert_one({
        "email": email,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notified": False,
    })
    return {"message": "Teşekkürler! Site açılır açılmaz size haber vereceğiz."}

@router.get("/maintenance/subscribers")
async def maintenance_subscribers_list(current_user: dict = Depends(require_admin)):
    """Admin: bakım modu e-posta aboneleri."""
    items = await db.maintenance_subscribers.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return {"total": len(items), "subscribers": items}

@router.get("/maintenance")
async def get_maintenance_status():
    """Public, lightweight maintenance-mode status used by the storefront gate."""
    settings = await db.settings.find_one(
        {"id": "main"},
        {"_id": 0, "maintenance_mode": 1, "maintenance_title": 1, "maintenance_message": 1, "logo_url": 1, "site_name": 1},
    ) or {}
    return {
        "maintenance_mode": bool(settings.get("maintenance_mode", False)),
        "maintenance_title": settings.get("maintenance_title") or "Sitemiz sizin için yenileniyor",
        "maintenance_message": settings.get("maintenance_message") or "Çok yakında, daha iyi bir alışveriş deneyimiyle buradayız. Anlayışınız için teşekkür ederiz.",
        "logo_url": settings.get("logo_url") or "",
        "site_name": settings.get("site_name") or "FACETTE",
    }

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
            "trendyol_markup": 0,
            "company_info": {
                "company_name": "",
                "tax_office": "",
                "tax_number": "",
                "address": "",
                "city": "",
                "website": "",
                "phone": "",
                "email": ""
            }
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
