"""
Snapchat Conversions API adapter.
Doc: https://developers.snap.com/api/marketing-api/Conversions-API/

Endpoint:
  POST https://tr.snapchat.com/v3/conversion?access_token={token}
"""
import httpx
from typing import Optional
from datetime import datetime, timezone


SNAP_BASE = "https://tr.snapchat.com/v3/conversion"

EVENT_MAP = {
    "view_item":        "VIEW_CONTENT",
    "view_item_list":   "LIST_VIEW",
    "add_to_cart":      "ADD_CART",
    "remove_from_cart": "ADD_CART",
    "begin_checkout":   "START_CHECKOUT",
    "add_payment_info": "ADD_BILLING",
    "add_to_wishlist":  "ADD_TO_WISHLIST",
    "purchase":         "PURCHASE",
    "refund":           "PURCHASE",  # negative value
    "lead":             "SIGN_UP",
    "search":           "SEARCH",
}


def _build_user(ud: dict) -> dict:
    out = {}
    if ud.get("em"): out["em"] = ud["em"]
    if ud.get("ph"): out["ph"] = ud["ph"]
    if ud.get("external_id"): out["uuid_c1"] = ud["external_id"]
    if ud.get("sc_click_id"): out["sc_click_id"] = ud["sc_click_id"]
    if ud.get("client_ip_address"): out["client_ip_address"] = ud["client_ip_address"]
    if ud.get("client_user_agent"): out["client_user_agent"] = ud["client_user_agent"]
    return out


def _build_custom(event: dict) -> dict:
    items = event.get("items") or []
    ids = [str(it.get("item_id") or it.get("id") or "") for it in items]
    return {
        "currency": event.get("currency") or "TRY",
        "price": float(event.get("value") or 0.0),
        "transaction_id": str(event.get("order_id") or ""),
        "item_ids": ids,
        "number_items": sum(int(it.get("quantity") or 1) for it in items),
        "item_category": event.get("category") or "",
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
    snap_event = EVENT_MAP.get(event_name, event_name.upper())
    if not event_time:
        event_time = int(datetime.now(timezone.utc).timestamp() * 1000)  # ms

    payload = {
        "pixel_id": pixel_id,
        "event_type": snap_event,
        "event_conversion_type": "WEB",
        "event_tag": event_name,
        "timestamp": int(event_time),
        "event_id": event_id,
        "page_url": event_source_url or "https://www.facette.com.tr",
        **_build_user(user_data),
        **_build_custom(event_payload),
    }

    params = {"access_token": access_token}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(SNAP_BASE, params=params, json=payload)
            try:
                resp_json = r.json()
            except Exception:
                resp_json = {"text": r.text[:300]}
            ok = 200 <= r.status_code < 300
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
        user_data={"em": "abc",
                   "client_ip_address": "8.8.8.8",
                   "client_user_agent": "Mozilla/5.0 FacetteTest"},
        event_payload={"value": 0, "currency": "TRY"},
    )
