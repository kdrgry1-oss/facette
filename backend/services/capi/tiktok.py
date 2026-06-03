"""
TikTok Events API adapter.
Doc: https://business-api.tiktok.com/portal/docs?id=1771101303285761

Endpoint:
  POST https://business-api.tiktok.com/open_api/v1.3/event/track/

Header:
  Access-Token: <ACCESS_TOKEN>
"""
import httpx
from typing import Optional
from datetime import datetime, timezone


TIKTOK_BASE = "https://business-api.tiktok.com/open_api/v1.3/event/track/"

EVENT_MAP = {
    "view_item":        "ViewContent",
    "view_item_list":   "ViewContent",
    "add_to_cart":      "AddToCart",
    "remove_from_cart": "RemoveFromCart",
    "begin_checkout":   "InitiateCheckout",
    "add_payment_info": "AddPaymentInfo",
    "add_to_wishlist":  "AddToWishlist",
    "purchase":         "CompletePayment",
    "refund":           "PlaceAnOrder",   # closest fallback
    "lead":             "SubmitForm",
    "search":           "Search",
}


def _build_user(ud: dict) -> dict:
    out = {}
    if ud.get("em"):       out["email"] = ud["em"]
    if ud.get("ph"):       out["phone"] = ud["ph"]
    if ud.get("external_id"): out["external_id"] = ud["external_id"]
    if ud.get("ttclid"):   out["ttclid"] = ud["ttclid"]
    if ud.get("client_ip_address"): out["ip"] = ud["client_ip_address"]
    if ud.get("client_user_agent"): out["user_agent"] = ud["client_user_agent"]
    return out


def _build_properties(event: dict) -> dict:
    contents = []
    for it in (event.get("items") or []):
        contents.append({
            "content_id": str(it.get("item_id") or it.get("id") or ""),
            "content_name": it.get("item_name") or it.get("name") or "",
            "content_type": "product",
            "quantity": int(it.get("quantity") or 1),
            "price": float(it.get("price") or 0),
        })
    return {
        "currency": event.get("currency") or "TRY",
        "value": float(event.get("value") or 0.0),
        "contents": contents,
        "content_type": "product",
        "order_id": str(event.get("order_id") or ""),
    }


async def send(
    *,
    pixel_id: str,
    access_token: str,
    event_name: str,
    event_id: str,
    event_time: Optional[int],
    user_data: dict,
    event_payload: dict,
    event_source_url: Optional[str] = None,
    test_event_code: Optional[str] = None,
    timeout: float = 8.0,
) -> dict:
    tt_event = EVENT_MAP.get(event_name, event_name)
    if not event_time:
        event_time = int(datetime.now(timezone.utc).timestamp())

    payload = {
        "event_source": "web",
        "event_source_id": pixel_id,
        "data": [{
            "event": tt_event,
            "event_time": int(event_time),
            "event_id": event_id,
            "user": _build_user(user_data),
            "properties": _build_properties(event_payload),
            "page": {"url": event_source_url or "https://www.facette.com.tr"},
        }],
    }
    if test_event_code:
        payload["test_event_code"] = test_event_code

    headers = {"Access-Token": access_token, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(TIKTOK_BASE, json=payload, headers=headers)
            try:
                resp_json = r.json()
            except Exception:
                resp_json = {"text": r.text[:500]}
            ok = (r.status_code == 200 and (resp_json or {}).get("code") == 0)
            return {"ok": ok, "status": r.status_code,
                    "response": resp_json,
                    "error": None if ok else resp_json}
    except Exception as e:
        return {"ok": False, "status": 0, "response": None, "error": str(e)}


async def test_connection(pixel_id: str, access_token: str,
                          test_event_code: Optional[str] = None) -> dict:
    return await send(
        pixel_id=pixel_id, access_token=access_token,
        event_name="lead", event_id=f"test-{int(datetime.now().timestamp())}",
        event_time=None,
        user_data={"client_ip_address": "8.8.8.8",
                   "client_user_agent": "Mozilla/5.0 FacetteTest"},
        event_payload={"value": 0, "currency": "TRY"},
        test_event_code=test_event_code,
    )
