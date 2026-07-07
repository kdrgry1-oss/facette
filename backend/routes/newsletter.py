"""
=============================================================================
newsletter.py — "Facette Kulübü" bülten aboneliği
=============================================================================
Footer üstündeki bülten bloğu ve genel e-posta abonelikleri için basit,
tekilleştirilmiş kayıt. İzin (İYS/EPOSTA) NetGSM entegratörü üzerinden
best-effort bildirilir.

ENDPOINTS:
  POST /api/newsletter/subscribe          — Public (e-posta ile abone ol)
  GET  /api/admin/newsletter/subscribers  — Admin (abone listesi)
=============================================================================
"""
import re
from fastapi import APIRouter, Depends, Request, HTTPException
from datetime import datetime, timezone

from .deps import db, require_admin, generate_id

public_router = APIRouter(prefix="/newsletter", tags=["newsletter-public"])
admin_router = APIRouter(prefix="/admin/newsletter", tags=["newsletter-admin"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@public_router.post("/subscribe")
async def subscribe(payload: dict, request: Request):
    """Bülten aboneliği. E-postayı tekilleştirerek kaydeder; İYS iznini
    NetGSM üzerinden bildirir (best-effort — hata aboneliği engellemez)."""
    email = (payload or {}).get("email", "")
    email = email.strip().lower() if isinstance(email, str) else ""
    if not email or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Geçerli bir e-posta adresi girin.")
    if len(email) > 254:
        raise HTTPException(status_code=400, detail="E-posta adresi çok uzun.")

    now = datetime.now(timezone.utc).isoformat()
    ip = request.client.host if request and request.client else ""
    source = (payload or {}).get("source") or "footer"

    existing = await db.newsletter_subscribers.find_one({"email": email})
    if existing:
        # Zaten kayıtlı — sessizce başarı döndür (kullanıcıya "zaten abonesiniz").
        return {"success": True, "already": True,
                "message": "Zaten Facette Kulübü üyesisiniz."}

    await db.newsletter_subscribers.insert_one({
        "id": generate_id(),
        "email": email,
        "source": source,
        "ip": ip,
        "active": True,
        "created_at": now,
    })

    # İYS/EPOSTA iznini NetGSM entegratörüne bildir (best-effort).
    try:
        from .iys import record_consent
        await record_consent(
            recipient_email=email, recipient_phone="",
            channels=["EPOSTA"], status="ONAY",
            source="HS_WEB", ip=ip,
        )
    except Exception:
        pass

    return {"success": True, "already": False,
            "message": "Facette Kulübü'ne hoş geldiniz!"}


@admin_router.get("/subscribers")
async def list_subscribers(limit: int = 500, current_user: dict = Depends(require_admin)):
    """Bülten abonelerini listeler (en yeni önce)."""
    limit = max(1, min(limit, 5000))
    rows = await db.newsletter_subscribers.find(
        {}, {"_id": 0}).sort("created_at", -1).to_list(length=limit)
    total = await db.newsletter_subscribers.count_documents({})
    return {"total": total, "subscribers": rows}
