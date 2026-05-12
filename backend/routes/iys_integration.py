"""
İYS (İleti Yönetim Sistemi) entegrasyonu — Iter 43.

Türkiye yasal zorunluluğu: B2C ticari ileti (email/SMS/arama) öncesi izin kontrolü.
Bu modül OAuth2 Client Credentials + tek/toplu izin sorgu/ekleme/iptal sağlar.

ENV:
  IYS_API_BASE_URL (default https://api.iys.org.tr)
  IYS_BRAND_CODE
  IYS_API_USERNAME
  IYS_API_PASSWORD

Veritabanı:
  iys_permissions: { recipient, recipient_type, message_type, status, source,
                      consent_date, cached_at, expires_at }
"""
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import List, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .deps import db, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/iys", tags=["iys"])

IYS_BASE = os.environ.get("IYS_API_BASE_URL") or "https://api.iys.org.tr"
IYS_BRAND = os.environ.get("IYS_BRAND_CODE") or ""

RecipientType = Literal["BIREYSEL", "TACIR"]
MessageType = Literal["MESAJ", "EPOSTA", "ARAMA"]


class _TokenCache:
    def __init__(self):
        self.token: Optional[str] = None
        self.expires_at: float = 0
_token = _TokenCache()


async def _get_token() -> Optional[str]:
    """OAuth2 Client Credentials — Secrets Vault'tan veya env'den okur."""
    if _token.token and time.time() < _token.expires_at - 60:
        return _token.token
    # Önce Secrets Vault'tan dene
    try:
        from .secrets_vault import get_secret
        user = await get_secret("IYS_API_USERNAME") or os.environ.get("IYS_API_USERNAME")
        pwd = await get_secret("IYS_API_PASSWORD") or os.environ.get("IYS_API_PASSWORD")
    except Exception:
        user = os.environ.get("IYS_API_USERNAME")
        pwd = os.environ.get("IYS_API_PASSWORD")
    if not user or not pwd:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{IYS_BASE}/oauth/token",
                data={"grant_type": "client_credentials",
                      "username": user, "password": pwd, "scope": "iys-api"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if r.status_code != 200:
                logger.warning(f"IYS token failed: {r.status_code} {r.text[:200]}")
                return None
            d = r.json()
            _token.token = d.get("access_token")
            _token.expires_at = time.time() + int(d.get("expires_in") or 3600)
            return _token.token
    except Exception as e:
        logger.warning(f"IYS token exception: {e}")
        return None


# Local cache helpers ---------------------------------------------------------
async def _cache_get(rec: str, rtype: str, mtype: str) -> Optional[dict]:
    doc = await db.iys_permissions.find_one(
        {"recipient": rec, "recipient_type": rtype, "message_type": mtype, "_id": 0},
        {"_id": 0},
    )
    if doc and doc.get("expires_at", "") > datetime.now(timezone.utc).isoformat():
        return doc
    return None


async def _cache_put(rec: str, rtype: str, mtype: str, status: str, source: str = "", ttl_minutes: int = 60):
    now = datetime.now(timezone.utc)
    await db.iys_permissions.update_one(
        {"recipient": rec, "recipient_type": rtype, "message_type": mtype},
        {"$set": {
            "recipient": rec, "recipient_type": rtype, "message_type": mtype,
            "status": status, "source": source,
            "cached_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=ttl_minutes)).isoformat(),
            "is_compliant": status == "ONAY",
        }},
        upsert=True,
    )


# Models ---------------------------------------------------------------------
class IYSQuery(BaseModel):
    recipient: str
    recipient_type: RecipientType
    message_type: MessageType


class IYSRegister(IYSQuery):
    status: Literal["ONAY", "RET"] = "ONAY"
    source: str = "API"


# Endpoints ------------------------------------------------------------------
@router.get("/status")
async def iys_status(_=Depends(require_admin)):
    """Konfigürasyon ve son token durumu."""
    return {
        "configured": bool(IYS_BRAND and (os.environ.get("IYS_API_USERNAME") or True)),
        "brand_code": IYS_BRAND or "(eksik)",
        "base_url": IYS_BASE,
        "token_valid_seconds": max(0, int(_token.expires_at - time.time())) if _token.token else 0,
    }


@router.post("/query")
async def iys_query(q: IYSQuery, _=Depends(require_admin)):
    """Tek izin sorgula — önce cache, sonra IYS API."""
    cached = await _cache_get(q.recipient, q.recipient_type, q.message_type)
    if cached:
        return {"source": "cache", **cached}

    tok = await _get_token()
    if not tok:
        return {"source": "no_token", "status": "UNKNOWN", "is_compliant": False,
                "message": "IYS API credentials eksik. Secrets Vault → IYS_API_USERNAME/IYS_API_PASSWORD ekleyin"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{IYS_BASE}/v1/consent/show/json",
                headers={"Authorization": f"Bearer {tok}"},
                json={"brandCode": IYS_BRAND, "recipient": q.recipient,
                      "recipientType": q.recipient_type, "type": q.message_type},
            )
            if r.status_code != 200:
                return {"source": "error", "status": "UNKNOWN", "is_compliant": False,
                        "http_status": r.status_code, "detail": r.text[:200]}
            d = r.json()
            consent = (d.get("response") or {}).get("consent") or d
            status = consent.get("status", "UNKNOWN")
            await _cache_put(q.recipient, q.recipient_type, q.message_type, status, consent.get("source", ""))
            return {"source": "api", "status": status, "is_compliant": status == "ONAY",
                    "consent_source": consent.get("source"), "consent_date": consent.get("consentDate")}
    except Exception as e:
        return {"source": "exception", "status": "UNKNOWN", "is_compliant": False, "error": str(e)}


@router.post("/register")
async def iys_register(p: IYSRegister, _=Depends(require_admin)):
    """İzin ekle/güncelle."""
    tok = await _get_token()
    if not tok:
        raise HTTPException(status_code=400, detail="IYS credentials eksik (Secrets Vault)")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{IYS_BASE}/v1/consent/add/json",
                headers={"Authorization": f"Bearer {tok}"},
                json={"brandCode": IYS_BRAND, "permissions": [{
                    "recipient": p.recipient, "recipientType": p.recipient_type,
                    "type": p.message_type, "status": p.status, "source": p.source,
                    "consentDate": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                }]},
            )
            await _cache_put(p.recipient, p.recipient_type, p.message_type, p.status, p.source)
            return {"ok": r.status_code == 200, "status": r.status_code, "body": r.text[:300]}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"IYS error: {e}")


@router.post("/query-batch")
async def iys_query_batch(queries: List[IYSQuery], _=Depends(require_admin)):
    """Toplu sorgulama (max 50). Pazarlama kampanyaları öncesi izin doğrulama."""
    if len(queries) > 50:
        raise HTTPException(status_code=400, detail="Max 50 sorgu")
    import asyncio
    results = await asyncio.gather(*[iys_query(q, _=_) for q in queries], return_exceptions=True)
    out = []
    compliant = 0
    for q, r in zip(queries, results):
        if isinstance(r, Exception):
            out.append({"recipient": q.recipient, "error": str(r), "is_compliant": False})
        else:
            out.append({"recipient": q.recipient, **r})
            if r.get("is_compliant"):
                compliant += 1
    return {"total": len(queries), "compliant": compliant, "items": out}
