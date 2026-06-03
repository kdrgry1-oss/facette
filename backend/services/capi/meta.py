"""
Meta (Facebook) Conversions API adapter.
Doc: https://developers.facebook.com/docs/marketing-api/conversions-api

Sends server-side events with PII hashed to: Meta Pixel.
Endpoint:
  POST https://graph.facebook.com/v18.0/{pixel_id}/events?access_token={token}

Required event fields:
  - event_name (e.g. "Purchase", "AddToCart", "InitiateCheckout", "ViewContent")
  - event_time (unix ts)
  - event_id (for dedup with browser pixel)
  - user_data (hashed PII)
  - custom_data (value, currency, content_ids, contents, num_items)
  - action_source ("website")
  - event_source_url (the page URL)
"""
import httpx
from typing import List, Optional
from datetime import datetime, timezone


META_GRAPH_VERSION = "v18.0"
META_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"

# Map of our internal event name → Meta standard event name.
EVENT_MAP = {
    "view_item":        "ViewContent",
    "view_item_list":   "ViewCategory",
    "add_to_cart":      "AddToCart",
    "remove_from_cart": "RemoveFromCart",
    "begin_checkout":   "InitiateCheckout",
    "add_payment_info": "AddPaymentInfo",
    "add_to_wishlist":  "AddToWishlist",
    "purchase":         "Purchase",
    "refund":           "Refund",   # custom event (not native)
    "lead":             "Lead",
    "search":           "Search",
}


def _build_user_data(ud: dict) -> dict:
    """Meta accepts: em, ph, fn, ln, ct, country, zp, external_id, fbp, fbc,
    client_ip_address, client_user_agent."""
    out = {}
    for k in ("em", "ph", "fn", "ln", "ct", "country", "zp", "external_id",
              "fbp", "fbc", "client_ip_address", "client_user_agent"):
        v = ud.get(k)
        if v:
            # Hashed fields go in arrays per Meta spec
            if k in ("em", "ph", "fn", "ln", "ct", "country", "zp", "external_id"):
                out[k] = [v] if not isinstance(v, list) else v
            else:
                out[k] = v
    return out


def _build_custom_data(event: dict) -> dict:
    """Maps GA4 e-commerce items → Meta contents."""
    cd = {
        "currency": event.get("currency") or "TRY",
        "value": float(event.get("value") or 0.0),
    }
    items = event.get("items") or []
    if items:
        contents = []
        ids = []
        for it in items:
            cid = str(it.get("item_id") or it.get("id") or "")
            ids.append(cid)
            contents.append({
                "id": cid,
                "quantity": int(it.get("quantity") or 1),
                "item_price": float(it.get("price") or 0),
            })
        cd["content_ids"] = ids
        cd["contents"] = contents
        cd["num_items"] = sum(int(i.get("quantity") or 1) for i in items)
        cd["content_type"] = "product"
    if event.get("order_id"):
        cd["order_id"] = str(event["order_id"])
    if event.get("coupon"):
        cd["coupon"] = event["coupon"]
    return cd


async def send(
    *,
    pixel_id: str,
    access_token: str,
    event_name: str,                # internal name (mapped to Meta standard)
    event_id: str,                  # for dedup
    event_time: Optional[int],
    user_data: dict,
    event_payload: dict,            # value, currency, items, order_id, ...
    event_source_url: Optional[str] = None,
    test_event_code: Optional[str] = None,
    action_source: str = "website",
    timeout: float = 8.0,
) -> dict:
    """Send a single server-side event to Meta CAPI.

    Returns dict { ok, status, response, error }.
    """
    meta_event = EVENT_MAP.get(event_name, event_name)
    if not event_time:
        event_time = int(datetime.now(timezone.utc).timestamp())

    payload = {
        "data": [{
            "event_name": meta_event,
            "event_time": int(event_time),
            "event_id": event_id,
            "action_source": action_source,
            "event_source_url": event_source_url or "https://www.facette.com.tr",
            "user_data": _build_user_data(user_data),
            "custom_data": _build_custom_data(event_payload),
        }],
    }
    if test_event_code:
        payload["test_event_code"] = test_event_code

    url = f"{META_BASE}/{pixel_id}/events"
    params = {"access_token": access_token}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, params=params, json=payload)
            try:
                resp_json = r.json()
            except Exception:
                resp_json = {"text": r.text[:500]}
            return {
                "ok": 200 <= r.status_code < 300 and "fbtrace_id" in (resp_json or {}),
                "status": r.status_code,
                "response": resp_json,
                "error": None if 200 <= r.status_code < 300 else resp_json,
            }
    except Exception as e:
        return {"ok": False, "status": 0, "response": None, "error": str(e)}


async def test_connection(pixel_id: str, access_token: str,
                          test_event_code: Optional[str] = None) -> dict:
    """Send a PageView ping with test_event_code for connection diagnosis."""
    return await send(
        pixel_id=pixel_id, access_token=access_token,
        event_name="lead", event_id=f"test-{int(datetime.now().timestamp())}",
        event_time=None,
        user_data={"client_ip_address": "8.8.8.8",
                   "client_user_agent": "Mozilla/5.0 FacetteTest"},
        event_payload={"value": 0, "currency": "TRY"},
        test_event_code=test_event_code,
    )
