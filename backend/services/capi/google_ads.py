"""
Google Ads Enhanced Conversions adapter (Measurement Protocol for GA4 + Ads).

Two endpoints supported:
  1. GA4 Measurement Protocol (server-side events to GA4 property)
     POST https://www.google-analytics.com/mp/collect?measurement_id={MID}&api_secret={SECRET}
     → Used for GA4 visibility (free).

  2. Google Ads Enhanced Conversions are typically done via the Google Ads API
     (uploadClickConversions / uploadConversionAdjustments). That requires
     OAuth2 + developer token. For MVP we send via GA4 MP which Ads consumes
     via auto-import when the Ads–GA4 link is configured.

Pixel ID format expected: "G-XXXX|api_secret"  (or stored in advanced JSON).
"""
import httpx
from typing import Optional
from datetime import datetime, timezone


GA4_BASE = "https://www.google-analytics.com/mp/collect"

EVENT_MAP = {
    "view_item":        "view_item",
    "view_item_list":   "view_item_list",
    "add_to_cart":      "add_to_cart",
    "remove_from_cart": "remove_from_cart",
    "begin_checkout":   "begin_checkout",
    "add_payment_info": "add_payment_info",
    "add_to_wishlist":  "add_to_wishlist",
    "purchase":         "purchase",
    "refund":           "refund",
    "lead":             "generate_lead",
    "search":           "search",
}


def _items_to_ga4(items: list) -> list:
    out = []
    for it in (items or []):
        out.append({
            "item_id": str(it.get("item_id") or it.get("id") or ""),
            "item_name": it.get("item_name") or it.get("name") or "",
            "item_category": it.get("item_category") or "",
            "item_brand": it.get("item_brand") or "",
            "item_variant": it.get("item_variant") or "",
            "price": float(it.get("price") or 0),
            "quantity": int(it.get("quantity") or 1),
        })
    return out


async def send(
    *,
    pixel_id: str,                # "G-XXXX|api_secret" or just "G-XXXX"
    access_token: str,            # api_secret (GA4 MP) — kept here for compat
    event_name: str,
    event_id: str,
    event_time: Optional[int],
    user_data: dict,
    event_payload: dict,
    event_source_url: Optional[str] = None,
    test_event_code: Optional[str] = None,
    timeout: float = 8.0,
) -> dict:
    # Parse measurement_id + api_secret
    if "|" in pixel_id:
        mid, embedded_secret = pixel_id.split("|", 1)
        api_secret = embedded_secret.strip() or access_token
    else:
        mid = pixel_id
        api_secret = access_token

    if not api_secret:
        return {"ok": False, "status": 0, "response": None,
                "error": "Google Ads/GA4 için api_secret eksik."}

    ga_event = EVENT_MAP.get(event_name, event_name)

    # Build the payload
    params_body = {
        "currency": event_payload.get("currency") or "TRY",
        "value": float(event_payload.get("value") or 0.0),
        "transaction_id": str(event_payload.get("order_id") or event_id),
        "coupon": event_payload.get("coupon") or "",
        "items": _items_to_ga4(event_payload.get("items") or []),
        "engagement_time_msec": 100,
        "session_id": user_data.get("external_id") or event_id,
    }

    payload = {
        "client_id": user_data.get("external_id") or user_data.get("em") or event_id,
        "events": [{"name": ga_event, "params": params_body}],
    }
    # User properties (hashed PII) — Google Ads Enhanced Conversions
    user_props = {}
    if user_data.get("em"): user_props["sha256_email"] = {"value": user_data["em"]}
    if user_data.get("ph"): user_props["sha256_phone"] = {"value": user_data["ph"]}
    if user_props:
        payload["user_properties"] = user_props

    params = {"measurement_id": mid, "api_secret": api_secret}
    if test_event_code:
        params["debug_mode"] = "true"

    url = GA4_BASE + ("/debug" if test_event_code else "")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, params=params, json=payload)
            # MP returns 204 No Content on success
            ok = r.status_code in (200, 204)
            try:
                resp_json = r.json() if r.text else {"status": "no_content"}
            except Exception:
                resp_json = {"text": r.text[:300]}
            return {"ok": ok, "status": r.status_code,
                    "response": resp_json,
                    "error": None if ok else resp_json}
    except Exception as e:
        return {"ok": False, "status": 0, "response": None, "error": str(e)}


async def test_connection(pixel_id: str, access_token: str,
                          test_event_code: Optional[str] = "1") -> dict:
    return await send(
        pixel_id=pixel_id, access_token=access_token,
        event_name="lead", event_id=f"test-{int(datetime.now().timestamp())}",
        event_time=None,
        user_data={"em": "test@example.com"},
        event_payload={"value": 0, "currency": "TRY"},
        test_event_code=test_event_code,
    )
