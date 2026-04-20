"""
Attribution & Funnel Tracking.

- Public: /api/attribution/track-visit  – storefront captures utm_*, referrer,
  landing_page on first visit. Returns a session_id to persist in localStorage.
- Public: /api/attribution/session/{sid} – fetch stored session (debug).
- Admin:  /api/attribution/stats        – breakdown by source/medium/campaign.
- The order create endpoint reads `attribution_session_id` from payload and
  joins the session into the order record at checkout.

Channels auto-detected from utm_source/medium & referrer host:
  instagram, facebook, tiktok, twitter, youtube, google_ads, google_organic,
  bing, email, direct, referral, trendyol, hepsiburada, n11, temu, other.
"""
from fastapi import APIRouter, Request, Depends, Query, HTTPException
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse
import uuid

from .deps import db, require_admin, logger

router = APIRouter(prefix="/attribution", tags=["attribution"])


SEARCH_ENGINES = {"google.com", "google.com.tr", "bing.com", "yandex.com", "duckduckgo.com", "yahoo.com"}
SOCIAL_DOMAINS = {
    "instagram.com": "instagram",
    "l.instagram.com": "instagram",
    "facebook.com": "facebook",
    "m.facebook.com": "facebook",
    "l.facebook.com": "facebook",
    "fb.com": "facebook",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "t.co": "twitter",
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "pinterest.com": "pinterest",
    "linkedin.com": "linkedin",
    "whatsapp.com": "whatsapp",
    "wa.me": "whatsapp",
}
MARKETPLACE_DOMAINS = {
    "trendyol.com": "trendyol",
    "hepsiburada.com": "hepsiburada",
    "n11.com": "n11",
    "temu.com": "temu",
    "amazon.com.tr": "amazon",
    "amazon.com": "amazon",
}


def detect_channel(utm_source: str, utm_medium: str, referrer: str) -> str:
    """Resolve a canonical marketing channel label from UTM + referrer."""
    s = (utm_source or "").lower().strip()
    m = (utm_medium or "").lower().strip()

    # Paid ads
    if m in {"cpc", "ppc", "paidsearch", "paid-search", "paid_search"}:
        if "google" in s:
            return "google_ads"
        if "bing" in s or "microsoft" in s:
            return "bing_ads"
        return "paid_search"
    if m in {"paidsocial", "paid-social", "paid_social", "social-cpc", "social"}:
        if "instagram" in s or "ig" in s:
            return "instagram_ads"
        if "facebook" in s or "fb" in s or "meta" in s:
            return "facebook_ads"
        if "tiktok" in s:
            return "tiktok_ads"
        return "paid_social"
    if m == "display":
        return "display_ads"
    if m in {"email", "e-mail", "newsletter"}:
        return "email"
    if m in {"sms"}:
        return "sms"
    if m in {"affiliate", "partner"}:
        return "affiliate"
    if m in {"influencer"}:
        return "influencer"

    # Direct utm_source signals (organic social, marketplaces)
    if s:
        for d, label in SOCIAL_DOMAINS.items():
            if d.split(".")[0] in s:
                return f"{label}_organic" if m in {"social", "organic", ""} else label
        for d, label in MARKETPLACE_DOMAINS.items():
            if d.split(".")[0] in s:
                return label
        if "google" in s:
            return "google_organic"

    # Fall back to referrer
    if referrer:
        try:
            host = urlparse(referrer).hostname or ""
            host = host.lower().lstrip("www.")
            if host in SEARCH_ENGINES or any(host.endswith("." + se) for se in SEARCH_ENGINES):
                if "google" in host:
                    return "google_organic"
                if "bing" in host:
                    return "bing_organic"
                return "search_organic"
            for d, label in SOCIAL_DOMAINS.items():
                if host == d or host.endswith("." + d):
                    return f"{label}_organic"
            for d, label in MARKETPLACE_DOMAINS.items():
                if host == d or host.endswith("." + d):
                    return label
            return "referral"
        except Exception:
            pass

    return "direct"


def detect_device(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "mobile" in ua or "iphone" in ua or "android" in ua:
        return "mobile"
    if "ipad" in ua or "tablet" in ua:
        return "tablet"
    return "desktop"


@router.post("/track-visit")
async def track_visit(payload: dict, request: Request):
    """Storefront calls this on first paint of any page (once per session).
    Payload: { utm_source, utm_medium, utm_campaign, utm_term, utm_content,
               referrer, landing_page, session_id? }
    Returns: { session_id } — the client persists this in localStorage.
    """
    sid = payload.get("session_id") or str(uuid.uuid4())

    # Upsert — if session already exists keep first-touch intact, update last-touch
    existing = await db.attribution_sessions.find_one({"session_id": sid}, {"_id": 0})
    now_iso = datetime.now(timezone.utc).isoformat()

    utm_source = (payload.get("utm_source") or "").strip()
    utm_medium = (payload.get("utm_medium") or "").strip()
    utm_campaign = (payload.get("utm_campaign") or "").strip()
    utm_term = (payload.get("utm_term") or "").strip()
    utm_content = (payload.get("utm_content") or "").strip()
    referrer = (payload.get("referrer") or "").strip()
    landing = (payload.get("landing_page") or "").strip()
    gclid = (payload.get("gclid") or "").strip()
    fbclid = (payload.get("fbclid") or "").strip()
    ua = request.headers.get("user-agent", "")
    ip = request.client.host if request.client else ""
    device = detect_device(ua)
    channel = detect_channel(utm_source, utm_medium, referrer)

    touch = {
        "ts": now_iso,
        "utm_source": utm_source,
        "utm_medium": utm_medium,
        "utm_campaign": utm_campaign,
        "utm_term": utm_term,
        "utm_content": utm_content,
        "gclid": gclid,
        "fbclid": fbclid,
        "referrer": referrer,
        "landing_page": landing,
        "channel": channel,
        "device": device,
    }

    if existing:
        await db.attribution_sessions.update_one(
            {"session_id": sid},
            {
                "$set": {
                    "last_touch": touch,
                    "last_seen_at": now_iso,
                    "visit_count": (existing.get("visit_count") or 1) + 1,
                    "user_agent": ua,
                    "ip": ip,
                },
                "$push": {"touches": {"$each": [touch], "$slice": -20}},
            },
        )
    else:
        await db.attribution_sessions.insert_one(
            {
                "session_id": sid,
                "first_touch": touch,
                "last_touch": touch,
                "touches": [touch],
                "visit_count": 1,
                "user_agent": ua,
                "ip": ip,
                "device": device,
                "created_at": now_iso,
                "last_seen_at": now_iso,
            }
        )

    return {"session_id": sid, "channel": channel, "device": device}


@router.get("/session/{sid}")
async def get_session(sid: str):
    doc = await db.attribution_sessions.find_one({"session_id": sid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Oturum bulunamadı")
    return doc


@router.get("/stats")
async def stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    """Orders grouped by (first_touch) channel/source/campaign within date range."""
    query = {"attribution.channel": {"$exists": True}}
    if start_date or end_date:
        q = {}
        if start_date:
            q["$gte"] = start_date
        if end_date:
            q["$lte"] = end_date
        query["created_at"] = q

    pipeline_channel = [
        {"$match": query},
        {
            "$group": {
                "_id": "$attribution.channel",
                "orders": {"$sum": 1},
                "revenue": {"$sum": {"$ifNull": ["$total", 0]}},
            }
        },
        {"$sort": {"revenue": -1}},
    ]
    by_channel = []
    async for row in db.orders.aggregate(pipeline_channel):
        by_channel.append({"channel": row["_id"] or "direct", "orders": row["orders"], "revenue": round(row["revenue"], 2)})

    pipeline_campaign = [
        {"$match": {**query, "attribution.campaign": {"$nin": [None, ""]}}},
        {
            "$group": {
                "_id": {"campaign": "$attribution.campaign", "source": "$attribution.source"},
                "orders": {"$sum": 1},
                "revenue": {"$sum": {"$ifNull": ["$total", 0]}},
            }
        },
        {"$sort": {"revenue": -1}},
        {"$limit": 30},
    ]
    by_campaign = []
    async for row in db.orders.aggregate(pipeline_campaign):
        by_campaign.append(
            {
                "campaign": row["_id"]["campaign"],
                "source": row["_id"]["source"],
                "orders": row["orders"],
                "revenue": round(row["revenue"], 2),
            }
        )

    # Sessions per channel (traffic)
    pipeline_sessions = [
        {"$group": {"_id": "$first_touch.channel", "sessions": {"$sum": 1}}},
        {"$sort": {"sessions": -1}},
    ]
    traffic = []
    async for row in db.attribution_sessions.aggregate(pipeline_sessions):
        traffic.append({"channel": row["_id"] or "direct", "sessions": row["sessions"]})

    total_orders = sum(c["orders"] for c in by_channel)
    total_revenue = round(sum(c["revenue"] for c in by_channel), 2)

    return {
        "by_channel": by_channel,
        "by_campaign": by_campaign,
        "traffic_by_channel": traffic,
        "totals": {"orders": total_orders, "revenue": total_revenue},
    }


async def resolve_attribution_for_order(session_id: Optional[str], inline_attribution: Optional[dict] = None) -> dict:
    """Build an attribution snapshot to persist on an order.
    Priority: explicit inline attribution → stored session first_touch."""
    if inline_attribution and any(inline_attribution.values()):
        ft = inline_attribution
        return {
            "channel": detect_channel(ft.get("utm_source", ""), ft.get("utm_medium", ""), ft.get("referrer", "")),
            "source": ft.get("utm_source", ""),
            "medium": ft.get("utm_medium", ""),
            "campaign": ft.get("utm_campaign", ""),
            "term": ft.get("utm_term", ""),
            "content": ft.get("utm_content", ""),
            "referrer": ft.get("referrer", ""),
            "landing_page": ft.get("landing_page", ""),
            "session_id": session_id or "",
            "first_touch_at": ft.get("ts", ""),
            "last_touch_at": ft.get("ts", ""),
            "device": ft.get("device", ""),
            "touches_count": 1,
        }

    if not session_id:
        return {
            "channel": "direct",
            "source": "",
            "medium": "",
            "campaign": "",
            "term": "",
            "content": "",
            "referrer": "",
            "landing_page": "",
            "session_id": "",
            "device": "",
            "touches_count": 0,
        }

    sess = await db.attribution_sessions.find_one({"session_id": session_id}, {"_id": 0})
    if not sess:
        return {
            "channel": "direct",
            "source": "",
            "medium": "",
            "campaign": "",
            "term": "",
            "content": "",
            "referrer": "",
            "landing_page": "",
            "session_id": session_id,
            "device": "",
            "touches_count": 0,
        }

    ft = sess.get("first_touch") or {}
    lt = sess.get("last_touch") or ft
    return {
        "channel": ft.get("channel") or detect_channel(ft.get("utm_source", ""), ft.get("utm_medium", ""), ft.get("referrer", "")),
        "source": ft.get("utm_source", ""),
        "medium": ft.get("utm_medium", ""),
        "campaign": ft.get("utm_campaign", ""),
        "term": ft.get("utm_term", ""),
        "content": ft.get("utm_content", ""),
        "referrer": ft.get("referrer", ""),
        "landing_page": ft.get("landing_page", ""),
        "last_touch_channel": lt.get("channel", ""),
        "last_touch_source": lt.get("utm_source", ""),
        "last_touch_campaign": lt.get("utm_campaign", ""),
        "session_id": session_id,
        "first_touch_at": ft.get("ts", ""),
        "last_touch_at": lt.get("ts", ""),
        "device": sess.get("device") or ft.get("device", ""),
        "touches_count": len(sess.get("touches") or []),
    }
