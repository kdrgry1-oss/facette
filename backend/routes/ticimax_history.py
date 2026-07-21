"""
ticimax_history.py — Ticimax GEÇMİŞ VERİ okuma/kurtarma uçları.

A4 kararıyla tüm Ticimax senkron router'ları kapatıldı (stok/katalog otoritesi
artık kendi sistemimiz). Bu modül YALNIZ geçmişe dönük veri kurtarma içindir:
  - GET  /admin/ticimax-history/orders/probe     — canlı WS şema örneği (admin)
  - POST /admin/ticimax-history/orders/backfill  — geçmiş sipariş aktarımı

Backfill kuralları (kullanıcı şartı — bozma):
  - STOK DÜŞÜMÜ YAPILMAZ, bildirim/mail/push tetiklenmez.
  - Var olan sipariş (order_number / ticimax_order_id) ATLANIR, güncellenmez.
  - Pazaryeri kaynaklı satırlar platform etiketiyle yazılır (raporlar doğru kırılır).
"""
from fastapi import APIRouter, Depends, Body
from datetime import datetime, timezone
from typing import Optional, Dict, List
import asyncio
import sys
import os

_BACKEND_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_PATH not in sys.path:
    sys.path.insert(0, _BACKEND_PATH)

from .deps import db, logger, require_admin, generate_id

router = APIRouter(prefix="/admin/ticimax-history", tags=["admin-ticimax-history"])


def _deep(o, depth=0):
    """Zeep nesnesini JSON'a çevrilebilir yapıya derinlemesine aç."""
    if depth > 8:
        return str(o)
    if o is None or isinstance(o, (str, int, float, bool)):
        return o
    if isinstance(o, (list, tuple)):
        return [_deep(x, depth + 1) for x in o]
    if hasattr(o, "__values__"):
        try:
            return {k: _deep(v, depth + 1) for k, v in dict(o.__values__).items()}
        except Exception:
            return str(o)
    if isinstance(o, dict):
        return {k: _deep(v, depth + 1) for k, v in o.items()}
    try:
        from datetime import datetime as _dt, date as _d
        if isinstance(o, (_dt, _d)):
            return o.isoformat()
    except Exception:
        pass
    try:
        from decimal import Decimal as _Dec
        if isinstance(o, _Dec):
            return float(o)
    except Exception:
        pass
    return str(o)


# Eski mağaza verileri artık bu domainde (facette.com.tr YENİ siteyi gösteriyor;
# Railway'deki TICIMAX_DOMAIN env'i eski günlerden www.facette.com.tr kalmış olabilir —
# history modülü her çağrıda domaini ZORLA doğru adrese çevirir).
HISTORY_DOMAIN_DEFAULT = "facette.ticimaxeticaret.com"


async def _api_key() -> str:
    s = await db.settings.find_one({"id": "ticimax"}) or {}
    return s.get("api_key") or "AKG0M8DTRSEBAIA898JA6HW22EDIU3"


async def _ensure_domain():
    from ticimax_client import set_domain
    s = await db.settings.find_one({"id": "ticimax"}) or {}
    set_domain(s.get("history_domain") or HISTORY_DOMAIN_DEFAULT)


@router.get("/wsdl-probe")
async def ticimax_wsdl_probe(current_user: dict = Depends(require_admin)):
    """SiparisServis WSDL'ine Railway'den erişimi ve harici şema referanslarını teşhis eder."""
    import httpx
    import re as _re
    import ticimax_client as _tc
    await _ensure_domain()
    SIPARIS_WSDL = _tc.SIPARIS_WSDL  # set_domain SONRASI güncel değer
    out = {"wsdl_url": SIPARIS_WSDL}
    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as c:
            r = await c.get(SIPARIS_WSDL)
            body = r.text or ""
            out["status"] = r.status_code
            out["final_url"] = str(r.url)
            out["head"] = body[:300]
            refs = sorted(set(_re.findall(r'(?:schemaLocation|location)="([^"]+)"', body)))
            out["external_refs"] = refs[:20]
            ref_status = {}
            for u in refs[:8]:
                if not u.lower().startswith("http"):
                    continue
                try:
                    rr = await c.get(u)
                    ref_status[u] = {"status": rr.status_code, "head": (rr.text or "")[:120]}
                except Exception as e:
                    ref_status[u] = {"error": str(e)[:150]}
            out["ref_status"] = ref_status
    except Exception as e:
        out["error"] = str(e)[:300]
    return out


@router.get("/orders/probe")
async def ticimax_orders_probe(
    start_date: str, end_date: str, page: int = 1,
    include_marketplace: bool = True,
    current_user: dict = Depends(require_admin),
):
    """Ticimax WS'ten örnek sipariş yapısı — backfill alan eşlemesi doğrulaması."""
    from ticimax_client import get_orders as tc_get_orders, set_live
    key = await _api_key()
    await _ensure_domain()
    set_live(True)
    try:
        orders = await asyncio.to_thread(
            tc_get_orders, page, 5, key, start_date, end_date,
            not include_marketplace, False)
    finally:
        set_live(False)
    return {"count": len(orders), "samples": [_deep(o) for o in orders[:2]]}
