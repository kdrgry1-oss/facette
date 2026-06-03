"""
CAPI Public Event Endpoint.
React frontend bu endpoint'e (tüm) tracking event'lerini POST eder.
Backend, event'i tüm aktif CAPI provider'larına paralel olarak fan-out eder.

Dedup: Frontend `event_id` (uuid) üretir; aynı id ile browser pixel'i ile
server-side gönderim aynı event olarak sayılır (Meta/TikTok/Pinterest native
support).
"""
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Request, BackgroundTasks
from pydantic import BaseModel, Field

from .deps import db
from services.capi.orchestrator import dispatch_event
from services.capi.hash_utils import build_user_data


router = APIRouter(prefix="/capi", tags=["capi"])


class CapiItem(BaseModel):
    item_id: Optional[str] = None
    item_name: Optional[str] = None
    item_brand: Optional[str] = None
    item_category: Optional[str] = None
    item_variant: Optional[str] = None
    price: Optional[float] = 0.0
    quantity: Optional[int] = 1


class CapiEventReq(BaseModel):
    event_name: str = Field(..., description="view_item|view_item_list|add_to_cart|remove_from_cart|begin_checkout|add_payment_info|purchase|refund|lead|search")
    event_id: Optional[str] = None
    event_time: Optional[int] = None
    # User PII (raw — backend hashes before sending)
    email: Optional[str] = None
    phone: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = "TR"
    zipcode: Optional[str] = None
    external_id: Optional[str] = None        # customer/user id
    # Click IDs (cookies)
    fbp: Optional[str] = None
    fbc: Optional[str] = None
    gclid: Optional[str] = None
    ttclid: Optional[str] = None
    epik: Optional[str] = None
    sc_click_id: Optional[str] = None
    # Event payload (GA4 e-commerce schema)
    currency: Optional[str] = "TRY"
    value: Optional[float] = 0.0
    items: Optional[List[CapiItem]] = None
    order_id: Optional[str] = None
    coupon: Optional[str] = None
    category: Optional[str] = None
    # Context
    event_source_url: Optional[str] = None
    tenant_id: Optional[str] = None
    providers: Optional[List[str]] = None    # restrict to specific providers


@router.post("/event")
async def capi_event(req: CapiEventReq, request: Request,
                     background_tasks: BackgroundTasks):
    """Track event from React. Returns immediately; dispatch runs in background.

    For checkout/purchase flows we want the response to be NON-BLOCKING so the
    user UX is unaffected. We schedule the dispatch via BackgroundTasks.
    """
    client_ip = (request.client.host if request.client else None)
    # If behind proxy / CF, prefer X-Forwarded-For
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        client_ip = fwd.split(",")[0].strip()
    user_agent = request.headers.get("user-agent")

    user_data = build_user_data(
        email=req.email, phone=req.phone,
        first_name=req.first_name, last_name=req.last_name,
        city=req.city, country=req.country, zipcode=req.zipcode,
        external_id=req.external_id,
        client_ip=client_ip, user_agent=user_agent,
        fbp=req.fbp, fbc=req.fbc, gclid=req.gclid,
        ttclid=req.ttclid, epik=req.epik, sc_click_id=req.sc_click_id,
    )

    event_payload = {
        "currency": req.currency,
        "value": req.value,
        "items": [i.dict() for i in (req.items or [])],
        "order_id": req.order_id,
        "coupon": req.coupon,
        "category": req.category,
    }

    event_id = req.event_id  # may be None — orchestrator will gen

    async def _run():
        await dispatch_event(
            db,
            event_name=req.event_name,
            event_id=event_id,
            event_time=req.event_time,
            user_data=user_data,
            event_payload=event_payload,
            event_source_url=req.event_source_url,
            tenant_id=req.tenant_id,
            providers=req.providers,
        )

    background_tasks.add_task(_run)
    # Return acknowledgment immediately
    return {
        "ok": True,
        "event_id": event_id,
        "queued": True,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health")
async def capi_health():
    """Public health check — list providers/pixel count without leaking tokens."""
    active = await db.marketing_pixels.count_documents(
        {"is_active": True, "capi_enabled": True})
    return {"ok": True, "capi_active_pixels": active}
