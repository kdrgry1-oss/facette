"""
=============================================================================
notifications.py — Admin bildirim ayarları ve şablon CRUD
=============================================================================
Endpoints:
  GET  /api/notifications/providers           → mevcut config
  POST /api/notifications/providers           → kaydet (sms_active, whatsapp_active, email_active, providers{})
  GET  /api/notifications/providers/catalog   → kanal+sağlayıcı listesi (UI için)

  GET  /api/notifications/templates           → tüm event×channel şablonları
  POST /api/notifications/templates           → tek şablonu kaydet (upsert)
  POST /api/notifications/templates/seed      → default şablonları oluştur (boş değilse dokunmaz)

  POST /api/notifications/test                → test gönderimi
  GET  /api/notifications/logs                → son N log
=============================================================================
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .deps import db, require_admin
from notification_service import (
    SMS_PROVIDERS,
    DEFAULT_EVENTS,
    CHANNELS,
    send_notification,
    test_provider,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


class ProviderConfigReq(BaseModel):
    sms_active: Optional[str] = None
    whatsapp_active: bool = False
    email_active: bool = True
    providers: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class TemplateReq(BaseModel):
    event: str
    channel: str  # sms|email|whatsapp
    enabled: bool = True
    subject: Optional[str] = ""
    body: str = ""
    meta_template_name: Optional[str] = None
    meta_template_lang: Optional[str] = "tr"
    meta_template_params: Optional[List[str]] = None


class TestReq(BaseModel):
    channel: str
    provider_key: Optional[str] = None
    to: str
    message: str = "Facette test bildirimi ✓"


@router.get("/providers/catalog")
async def get_catalog(current_user: dict = Depends(require_admin)):
    return {
        "sms_providers": SMS_PROVIDERS,
        "channels": CHANNELS,
        "events": DEFAULT_EVENTS,
    }


@router.get("/providers")
async def get_providers(current_user: dict = Depends(require_admin)):
    cfg = await db.settings.find_one({"id": "notification_providers"}, {"_id": 0})
    if not cfg:
        cfg = {
            "id": "notification_providers",
            "sms_active": None,
            "whatsapp_active": False,
            "email_active": True,
            "providers": {},
        }
    # Secret alanları maskele (ekranda görünsün ama ham şekilde değil)
    SECRET_FIELDS = {"password", "auth_token", "api_hash", "api_key", "access_token", "api_secret"}
    masked = dict(cfg)
    prov = {}
    for pkey, fields in (cfg.get("providers") or {}).items():
        prov[pkey] = {}
        for f, v in (fields or {}).items():
            if f in SECRET_FIELDS and v:
                s = str(v)
                prov[pkey][f] = (s[:2] + "****" + s[-2:]) if len(s) > 6 else "****"
                prov[pkey][f"__has_{f}"] = True
            else:
                prov[pkey][f] = v
    masked["providers"] = prov
    return masked


@router.post("/providers")
async def save_providers(req: ProviderConfigReq, current_user: dict = Depends(require_admin)):
    # Mevcut config (gizli alanlar için). Eğer UI maskeli bir değeri aynen geri gönderdiyse
    # orijinal değeri koru (yani "xx****yy" gönderilmişse değiştirmiyor sayılır).
    existing = await db.settings.find_one({"id": "notification_providers"}, {"_id": 0}) or {}
    existing_provs = existing.get("providers", {})
    SECRET_FIELDS = {"password", "auth_token", "api_hash", "api_key", "access_token", "api_secret"}
    merged_provs: Dict[str, Dict[str, Any]] = {}
    for pkey, fields in req.providers.items():
        merged = dict(fields or {})
        old = existing_provs.get(pkey, {}) or {}
        for f in list(merged.keys()):
            if f in SECRET_FIELDS:
                val = merged[f]
                # UI'den maskeli/boş geldi → eski değeri koru
                if not val or (isinstance(val, str) and "****" in val):
                    if old.get(f):
                        merged[f] = old[f]
        # __has_ bayraklarını DB'ye yazma
        merged = {k: v for k, v in merged.items() if not k.startswith("__has_")}
        merged_provs[pkey] = merged

    data = {
        "id": "notification_providers",
        "sms_active": req.sms_active,
        "whatsapp_active": req.whatsapp_active,
        "email_active": req.email_active,
        "providers": merged_provs,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": current_user.get("email", ""),
    }
    await db.settings.update_one({"id": "notification_providers"}, {"$set": data}, upsert=True)
    return {"success": True, "message": "Bildirim sağlayıcı ayarları kaydedildi"}


@router.get("/templates")
async def list_templates(current_user: dict = Depends(require_admin)):
    rows = await db.notification_templates.find({}, {"_id": 0}).to_list(length=None)
    return {"templates": rows}


@router.post("/templates")
async def upsert_template(req: TemplateReq, current_user: dict = Depends(require_admin)):
    if req.channel not in CHANNELS:
        raise HTTPException(status_code=400, detail="Geçersiz kanal")
    data = req.model_dump()
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["updated_by"] = current_user.get("email", "")
    await db.notification_templates.update_one(
        {"event": req.event, "channel": req.channel},
        {"$set": data},
        upsert=True,
    )
    return {"success": True}


_DEFAULT_TEMPLATES = {
    # (event, channel) → payload
    ("order_confirmed", "sms"):
        "Merhaba {customer_name}, {order_number} numarali siparisiniz onaylandi. Facette",
    ("order_shipped", "sms"):
        "Siparisiniz kargoya verildi. Kargo takip: {tracking_number}. Facette",
    ("order_delivered", "sms"):
        "Siparisiniz teslim edildi. Facette'i tercih ettiginiz icin tesekkurler.",
    ("order_undelivered", "sms"):
        "Kargonuz teslim edilemedi, subede bekliyor. Takip: {tracking_number}. Facette",
    ("order_cancelled", "sms"):
        "{order_number} numarali siparisiniz iptal edildi. Bilgi: destek@facette.com",
    ("password_reset_otp", "sms"):
        "Facette dogrulama kodunuz: {otp_code} (5 dk gecerli).",
    ("abandoned_cart", "sms"):
        "Sepetinizde urunler kaldi! Siparis tamamlama baglantisi: {cart_url}",
}


@router.post("/templates/seed")
async def seed_templates(current_user: dict = Depends(require_admin)):
    """Default şablonları oluştur. Var olanlara dokunmaz."""
    created = 0
    for ev in DEFAULT_EVENTS:
        ev_key = ev["key"]
        for ch in CHANNELS:
            existing = await db.notification_templates.find_one({"event": ev_key, "channel": ch}, {"_id": 1})
            if existing:
                continue
            body = _DEFAULT_TEMPLATES.get((ev_key, ch), "")
            subj = ev["name"] if ch == "email" else ""
            if ch == "email" and not body:
                body = f"<p>Merhaba {{customer_name}},</p><p>{ev['name']} bildirimi.</p>"
            await db.notification_templates.insert_one({
                "event": ev_key,
                "channel": ch,
                "enabled": bool(body),
                "subject": subj,
                "body": body,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            created += 1
    return {"success": True, "created": created}


@router.post("/test")
async def send_test(req: TestReq, current_user: dict = Depends(require_admin)):
    res = await test_provider(db, req.channel, req.provider_key, req.to, req.message)
    return res


@router.get("/logs")
async def list_logs(limit: int = Query(50, ge=1, le=500), current_user: dict = Depends(require_admin)):
    rows = (
        await db.notification_logs.find({}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(length=limit)
    )
    return {"logs": rows}
