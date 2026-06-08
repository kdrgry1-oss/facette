"""
Order routes - CRUD, checkout, tracking
"""
from fastapi import APIRouter, HTTPException, Query, Depends, Response, Request
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import time
import uuid

from .deps import db, logger, get_current_user, require_admin, generate_id
from .attribution import resolve_attribution_for_order
from pymongo import ReturnDocument

router = APIRouter(prefix="/orders", tags=["Orders"])

def generate_order_number() -> str:
    import secrets
    return f"FC{int(time.time())}{secrets.token_hex(2).upper()}"

async def next_order_number() -> str:
    """Kısa, sıralı site sipariş numarası: W10001, W10002, ...
    Atomik sayaç (db.counters) ile çakışma imkânsız. Sayaç başarısız olursa
    kısa, W ön ekli bir fallback üretir; sipariş oluşturma asla kırılmaz."""
    try:
        doc = await db.counters.find_one_and_update(
            {"_id": "order_seq"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return f"W{10000 + int(doc['seq'])}"
    except Exception as e:
        logger.warning(f"order_seq sayaci basarisiz, fallback kullaniliyor: {e}")
        import secrets
        return f"W{int(time.time()) % 1000000}{secrets.token_hex(1).upper()}"

@router.get("")
async def get_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    order_number: Optional[str] = None,
    cargo_tracking: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    payment_method: Optional[str] = None,
    platform: Optional[str] = None,
    current_user: dict = Depends(require_admin)
):
    """Get orders with pagination (admin only)"""
    skip = (page - 1) * limit
    query = {}
    
    if status:
        query["status"] = status
    if phone:
        query["shipping_address.phone"] = {"$regex": phone, "$options": "i"}
    if email:
        query["shipping_address.email"] = {"$regex": email, "$options": "i"}
    if order_number:
        query["order_number"] = {"$regex": order_number, "$options": "i"}
    if cargo_tracking:
        query["cargo_tracking"] = {"$regex": cargo_tracking, "$options": "i"}
    if payment_method:
        query["payment_method"] = payment_method
    if platform:
        query["platform"] = platform
        
    date_query = {}
    if start_date:
        date_query["$gte"] = start_date
    if end_date:
        date_query["$lte"] = end_date
    if date_query:
        query["created_at"] = date_query
    
    if search:
        query["$or"] = [
            {"order_number": {"$regex": search, "$options": "i"}},
            {"shipping_address.first_name": {"$regex": search, "$options": "i"}},
            {"shipping_address.last_name": {"$regex": search, "$options": "i"}},
            {"shipping_address.phone": {"$regex": search, "$options": "i"}},
            {"shipping_address.email": {"$regex": search, "$options": "i"}}
        ]
    
    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.orders.count_documents(query)
    
    return {
        "orders": orders,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

@router.get("/by-number/{order_number}")
async def get_order_by_number(order_number: str):
    """Sipariş numarasıyla siparişi getir (public — ödeme sonrası başarı sayfası için).
    PII maskelenir (telefon/email son kısımları gizlenir, adres detayı sınırlanır)."""
    order = await db.orders.find_one(
        {"order_number": order_number},
        {"_id": 0, "admin_notes": 0, "payment_id": 0, "user_id": 0, "customer_ip": 0, "user_agent": 0,
         "billing_address": 0, "attribution": 0}
    )
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    def _mask_email(e: str) -> str:
        if not e or "@" not in e:
            return ""
        local, _, domain = e.partition("@")
        return (local[:2] + "***@" + domain) if len(local) > 2 else "***@" + domain

    def _mask_phone(p: str) -> str:
        digits = "".join(c for c in str(p or "") if c.isdigit())
        return (digits[:3] + "****" + digits[-2:]) if len(digits) >= 6 else ""

    ship = order.get("shipping_address") or {}
    if ship:
        order["shipping_address"] = {
            "first_name": ship.get("first_name", ""),
            "last_name": ship.get("last_name", ""),
            "phone": _mask_phone(ship.get("phone", "")),
            "email": _mask_email(ship.get("email", "")),
            "address": (ship.get("address") or "")[:40] + ("..." if len(ship.get("address") or "") > 40 else ""),
            "city": ship.get("city", ""),
            "district": ship.get("district", ""),
        }
    return order


@router.get("/{order_id}")
async def get_order(
    order_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get single order"""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    # Check access - admin can see all, users can see only their own
    if current_user and not current_user.get("is_admin"):
        if order.get("user_id") != current_user.get("id"):
            raise HTTPException(status_code=403, detail="Bu siparişi görüntüleme yetkiniz yok")
    
    return order

@router.post("")
async def create_order(
    order_data: dict,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Create new order"""
    # FAZ 6 — Kullanıcı IP'sini kayda al (X-Forwarded-For → gerçek IP)
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")

    # FAZ 6 — Blok kontrolü: kullanıcı veya IP bloklu mu?
    uid = (current_user.get("id") if current_user else None)
    block_query = []
    if uid:
        block_query.append({"user_id": uid})
    if client_ip:
        block_query.append({"ip": client_ip})
    if block_query:
        bl = await db.blocked_customers.find_one({"$or": block_query, "active": True}, {"_id": 0})
        if bl:
            logger.warning(f"Blocked order attempt: user={uid} ip={client_ip} reason={bl.get('reason')}")
            raise HTTPException(status_code=403, detail="Hesabınız sipariş veremez. Lütfen destek ile iletişime geçin.")

    order = {
        "id": generate_id(),
        "order_number": await next_order_number(),
        "user_id": current_user.get("id") if current_user else None,
        "items": order_data.get("items", []),
        "shipping_address": order_data.get("shipping_address", {}),
        "billing_address": order_data.get("billing_address") or order_data.get("shipping_address", {}),
        # Kurumsal fatura bilgileri (B2B müşteriler için)
        "billing_info": {
            "is_corporate": bool((order_data.get("billing_info") or {}).get("is_corporate", False)),
            "company_name": ((order_data.get("billing_info") or {}).get("company_name") or "").strip(),
            "tax_office": ((order_data.get("billing_info") or {}).get("tax_office") or "").strip(),
            "tax_number": ((order_data.get("billing_info") or {}).get("tax_number") or "").strip(),
            "e_invoice_user": bool((order_data.get("billing_info") or {}).get("e_invoice_user", False)),
        } if order_data.get("billing_info") else {"is_corporate": False},
        "subtotal": float(order_data.get("subtotal", 0)),
        "shipping_cost": float(order_data.get("shipping_cost", 0)),
        "discount": float(order_data.get("discount", 0)),
        "total": float(order_data.get("total", 0)),
        "payment_method": order_data.get("payment_method", "credit_card"),
        "payment_status": "pending",
        "status": "pending",
        "notes": order_data.get("notes", ""),
        "platform": order_data.get("platform", "facette"),
        # FAZ 4 — hediye seçenekleri
        "gift_note": (order_data.get("gift_note") or "")[:500],
        "gift_wrap": bool(order_data.get("gift_wrap", False)),
        "gift_wrap_price": float(order_data.get("gift_wrap_price", 0) or 0),
        "coupon_code": (order_data.get("coupon_code") or "").upper(),
        # FAZ 6 — müşteri izleri
        "customer_ip": client_ip,
        "user_agent": request.headers.get("user-agent", "")[:300],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    # Attribution snapshot (source of the sale)
    try:
        sid = order_data.get("attribution_session_id") or order_data.get("session_id")
        inline = order_data.get("attribution") if isinstance(order_data.get("attribution"), dict) else None
        order["attribution"] = await resolve_attribution_for_order(sid, inline)
    except Exception as att_err:
        logger.warning(f"Attribution resolve failed: {att_err}")
        order["attribution"] = {"channel": "direct", "source": "", "medium": "", "campaign": "", "session_id": ""}

    # Influencer linking — aff_id (çerez) önce, kupon fallback override
    try:
        from .influencers import resolve_influencer_for_order
        aff_id = (order.get("attribution") or {}).get("aff_id") or order_data.get("aff_id")
        link = await resolve_influencer_for_order(aff_id, order.get("coupon_code"))
        if link:
            order["influencer_id"] = link["influencer_id"]
            order["influencer_via"] = link["via"]
    except Exception as inf_err:
        logger.warning(f"Influencer link failed: {inf_err}")

    await db.orders.insert_one(order)
    logger.info(f"Order created: {order['order_number']}")

    # FAZ — Sipariş onayı bildirimi (SMS + Email + WhatsApp) — fire-and-forget
    import asyncio as _asyncio
    async def _notify_order_created():
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from notification_service import send_notification

            ship = order.get("shipping_address") or {}
            full_name = (
                f"{ship.get('first_name','')} {ship.get('last_name','')}".strip()
                or ship.get("full_name") or ship.get("name") or "Müşterimiz"
            )
            # Sipariş kalemlerini email için HTML satırlarına çevir
            items = order.get("items") or []
            items_rows = ""
            for it in items[:20]:
                img = it.get("image") or ""
                name = it.get("name") or it.get("product_name") or "Ürün"
                qty = it.get("quantity", 1)
                price = it.get("price", 0)
                size = it.get("size", "")
                color = it.get("color", "")
                meta = " · ".join([f"Beden: {size}" if size else "", f"Renk: {color}" if color else "", f"Adet: {qty}"]).strip(" · ")
                items_rows += (
                    f'<tr><td style="padding:12px 0;border-bottom:1px solid #f0f0f0;width:80px;">'
                    f'<img src="{img}" alt="" style="width:64px;height:80px;object-fit:cover;background:#fafafa;"/></td>'
                    f'<td style="padding:12px 12px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#111;">{name}'
                    f'<div style="color:#999;font-size:11px;margin-top:4px;">{meta}</div></td>'
                    f'<td style="padding:12px 0;border-bottom:1px solid #f0f0f0;text-align:right;font-size:13px;color:#111;white-space:nowrap;">{(price*qty):.2f} TL</td></tr>'
                )
            items_html = (
                '<div style="padding:0 24px 16px;"><table cellpadding="0" cellspacing="0" border="0" style="width:100%;">'
                f'{items_rows}</table></div>'
            ) if items_rows else ""

            base_url = os.environ.get("FRONTEND_PUBLIC_URL") or os.environ.get("REACT_APP_BACKEND_URL") or ""
            order_link = f"{base_url}/order-success/{order['order_number']}" if base_url else "#"
            order_date = order["created_at"][:10]

            variables = {
                "customer_name": full_name,
                "first_name": ship.get("first_name", "") or full_name.split(" ")[0],
                "order_number": order["order_number"],
                "order_date": order_date,
                "amount": f"{order['total']:.2f} TL",
                "subtotal": f"{order['subtotal']:.2f}",
                "shipping_cost": f"{order['shipping_cost']:.2f}",
                "discount": f"{order['discount']:.2f}",
                "total": f"{order['total']:.2f}",
                "items_html": items_html,
                "shipping_full_name": full_name,
                "shipping_address": ship.get("address", ""),
                "shipping_city": ship.get("city", ""),
                "shipping_district": ship.get("district", ""),
                "shipping_phone": ship.get("phone", ""),
                "order_link": order_link,
            }
            await send_notification(
                db, "order_confirmed",
                to_phone=ship.get("phone") or order.get("phone"),
                to_email=ship.get("email") or order.get("email"),
                variables=variables,
            )
        except Exception as e:
            logger.warning(f"order_confirmed notification dispatch failed: {e}")

    _asyncio.create_task(_notify_order_created())

    # FAZ 1 - C1: otomatik stok düşümü
    try:
        moves = await _stock_delta_for_order(order, -1)
        if moves:
            await db.stock_movements.insert_one({
                "id": str(uuid.uuid4()),
                "type": "order_created",
                "order_id": order["id"],
                "order_number": order["order_number"],
                "items": moves,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as stock_err:
        logger.error(f"Stock decrement on order create failed: {stock_err}")

    return {
        "order_id": order["id"],
        "order_number": order["order_number"],
        "message": "Sipariş oluşturuldu"
    }

@router.put("/{order_id}")
async def update_order(
    order_id: str,
    order_data: dict,
    current_user: dict = Depends(require_admin)
):
    """Update order (admin only)"""
    existing = await db.orders.find_one({"id": order_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    order_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.orders.update_one({"id": order_id}, {"$set": order_data})
    
    return {"message": "Sipariş güncellendi"}

@router.put("/{order_id}/status")
async def update_order_status(
    order_id: str,
    status: str = Query(...),
    current_user: dict = Depends(require_admin)
):
    """Update order status"""
    valid_statuses = ["pending", "confirmed", "processing", "shipped", "delivered", "undelivered", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Geçersiz durum. Geçerli değerler: {valid_statuses}")
    
    result = await db.orders.update_one(
        {"id": order_id},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    # Bildirim tetikleme: status → event eşlemesi
    # NOT: Provider'lara gidiş yavaş olabilir — fire-and-forget task ile UI yanıtını
    # bloklamadan arka planda tetikliyoruz.
    import asyncio as _asyncio
    async def _dispatch_notif():
        try:
            order_doc = await db.orders.find_one({"id": order_id}, {"_id": 0})
            if not order_doc:
                return
            status_to_event = {
                "confirmed": "order_confirmed",
                "processing": "order_packed",
                "shipped": "order_shipped",
                "delivered": "order_delivered",
                "undelivered": "order_undelivered",
                "cancelled": "order_cancelled",
            }
            ev = status_to_event.get(status)
            if not ev:
                return
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from notification_service import send_notification
            addr = order_doc.get("shipping_address") or {}
            variables = {
                "customer_name": addr.get("full_name") or addr.get("first_name") or "Müşterimiz",
                "order_number": order_doc.get("order_number", ""),
                "amount": f"{order_doc.get('total', 0):.2f} TL",
                "tracking_number": order_doc.get("cargo_tracking_number", ""),
                "status_label": status,
            }
            await send_notification(
                db, ev,
                to_phone=addr.get("phone") or order_doc.get("phone"),
                to_email=addr.get("email") or order_doc.get("email"),
                variables=variables,
            )
        except Exception as _notif_err:
            logger.warning(f"notification dispatch failed for order {order_id}: {_notif_err}")

    _asyncio.create_task(_dispatch_notif())

    # ---- CAPI Server-Side Tracking Hooks ----
    # Status değişimleri reklam platformlarına da bildirilir.
    async def _dispatch_capi():
        try:
            order_doc = await db.orders.find_one({"id": order_id}, {"_id": 0})
            if not order_doc:
                return
            # Map status → CAPI event_name
            capi_event = None
            value_multiplier = 1.0
            if status == "confirmed" and order_doc.get("payment_status") == "paid":
                capi_event = "purchase"
            elif status == "cancelled" and order_doc.get("payment_status") == "paid":
                capi_event = "refund"
                value_multiplier = -1.0
            if not capi_event:
                return
            from services.capi.orchestrator import dispatch_event
            addr = order_doc.get("shipping_address") or {}
            user_data_kwargs = {
                "email": addr.get("email") or order_doc.get("email"),
                "phone": addr.get("phone") or order_doc.get("phone"),
                "first_name": addr.get("first_name") or (addr.get("full_name") or "").split(" ")[0],
                "last_name": addr.get("last_name") or " ".join((addr.get("full_name") or "").split(" ")[1:]),
                "city": addr.get("city"),
                "state": addr.get("district") or addr.get("state"),
                "country": addr.get("country") or "TR",
                "zipcode": addr.get("zipcode") or addr.get("postal_code"),
                "street": addr.get("address") or addr.get("address_line1"),
                "date_of_birth": (order_doc.get("customer") or {}).get("date_of_birth"),
                "gender": (order_doc.get("customer") or {}).get("gender"),
                "external_id": order_doc.get("customer_id") or order_doc.get("user_id"),
            }
            from services.capi.hash_utils import build_user_data
            user_data = build_user_data(**user_data_kwargs)
            items_payload = []
            for it in (order_doc.get("items") or []):
                items_payload.append({
                    "item_id": str(it.get("product_id") or it.get("sku") or ""),
                    "item_name": it.get("name") or "",
                    "item_brand": it.get("brand") or "",
                    "item_variant": f"{it.get('size','')} {it.get('color','')}".strip(),
                    "price": float(it.get("unit_price") or it.get("price") or 0),
                    "quantity": int(it.get("quantity") or 1),
                })
            await dispatch_event(
                db,
                event_name=capi_event,
                event_id=f"{order_id}-{capi_event}",   # dedup by order
                user_data=user_data,
                event_payload={
                    "currency": order_doc.get("currency") or "TRY",
                    "value": float(order_doc.get("total") or 0) * value_multiplier,
                    "items": items_payload,
                    "order_id": order_doc.get("order_number") or order_id,
                    "coupon": order_doc.get("coupon_code"),
                },
                event_source_url="https://www.facette.com.tr",
            )
        except Exception as _capi_err:
            logger.warning(f"CAPI dispatch failed for order {order_id}: {_capi_err}")

    _asyncio.create_task(_dispatch_capi())

    # FAZ 1 - C1: Status değişikliğinde stok düzenlemesi
    try:
        order_doc = await db.orders.find_one({"id": order_id}, {"_id": 0})
        prev_status = None  # we don't have a before-value; rely on status flip idempotence
        if status == "cancelled":
            # Only increment once – guard with stock_movements presence
            already = await db.stock_movements.find_one({"order_id": order_id, "type": "order_cancelled"}, {"_id": 1})
            if not already:
                moves = await _stock_delta_for_order(order_doc, +1)
                if moves:
                    await db.stock_movements.insert_one({
                        "id": str(uuid.uuid4()),
                        "type": "order_cancelled",
                        "order_id": order_id,
                        "order_number": order_doc.get("order_number", ""),
                        "items": moves,
                        "created_by": current_user.get("email", ""),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
    except Exception as stock_err:
        logger.error(f"Stock restore on cancel failed: {stock_err}")

    return {"message": f"Sipariş durumu '{status}' olarak güncellendi"}

@router.put("/{order_id}/mark-paid")
async def mark_order_paid(
    order_id: str,
    current_user: dict = Depends(require_admin)
):
    """Havale/EFT ödemesi manuel onaylama.
    payment_status='paid' yapar ve CAPI'ye offline 'purchase' event'i gönderir.
    """
    order_doc = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order_doc:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    if order_doc.get("payment_status") == "paid":
        return {"message": "Sipariş zaten ödenmiş olarak işaretli.",
                "order_id": order_id, "already_paid": True}

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "payment_status": "paid",
            "paid_at": now_iso,
            "paid_by": current_user.get("email", ""),
            "updated_at": now_iso,
        }},
    )

    # CAPI offline conversion (purchase event) — fire-and-forget
    import asyncio as _asyncio
    async def _capi_offline_purchase():
        try:
            from services.capi.orchestrator import dispatch_event
            from services.capi.hash_utils import build_user_data
            addr = order_doc.get("shipping_address") or {}
            user_data = build_user_data(
                email=addr.get("email") or order_doc.get("email"),
                phone=addr.get("phone") or order_doc.get("phone"),
                first_name=addr.get("first_name") or (addr.get("full_name") or "").split(" ")[0],
                last_name=addr.get("last_name") or " ".join((addr.get("full_name") or "").split(" ")[1:]),
                city=addr.get("city"),
                state=addr.get("district") or addr.get("state"),
                country=addr.get("country") or "TR",
                zipcode=addr.get("zipcode") or addr.get("postal_code"),
                street=addr.get("address") or addr.get("address_line1"),
                date_of_birth=(order_doc.get("customer") or {}).get("date_of_birth"),
                gender=(order_doc.get("customer") or {}).get("gender"),
                external_id=order_doc.get("customer_id") or order_doc.get("user_id"),
            )
            items_payload = []
            for it in (order_doc.get("items") or []):
                items_payload.append({
                    "item_id": str(it.get("product_id") or it.get("sku") or ""),
                    "item_name": it.get("name") or "",
                    "item_variant": f"{it.get('size','')} {it.get('color','')}".strip(),
                    "price": float(it.get("unit_price") or it.get("price") or 0),
                    "quantity": int(it.get("quantity") or 1),
                })
            await dispatch_event(
                db,
                event_name="purchase",
                event_id=f"{order_id}-offline-purchase",
                user_data=user_data,
                event_payload={
                    "currency": order_doc.get("currency") or "TRY",
                    "value": float(order_doc.get("total") or 0),
                    "items": items_payload,
                    "order_id": order_doc.get("order_number") or order_id,
                    "coupon": order_doc.get("coupon_code"),
                },
                event_source_url="https://www.facette.com.tr",
            )
        except Exception as e:
            logger.warning(f"CAPI offline-purchase failed: {e}")

    _asyncio.create_task(_capi_offline_purchase())

    return {"message": "Ödeme onaylandı, CAPI offline conversion tetiklendi.",
            "order_id": order_id, "payment_status": "paid"}


@router.delete("/{order_id}")
async def delete_order(
    order_id: str,
    current_user: dict = Depends(require_admin)
):
    """Delete order (admin only)"""
    result = await db.orders.delete_one({"id": order_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    return {"message": "Sipariş silindi"}


# ==================== FAZ 1: STOCK AUTO-FLOW + AUTO-CANCEL + NOTES ====================

async def _stock_delta_for_order(order: dict, delta: int) -> list:
    """Apply stock delta (+1 or -1 per unit) for every order item. Returns movement list."""
    movements = []
    items = order.get("items") or order.get("lines") or []
    for it in items:
        barcode = it.get("barcode") or it.get("sku") or ""
        qty = int(it.get("quantity", 1) or 1)
        if not barcode:
            continue
        # Try variant match first
        prod = await db.products.find_one({"variants.barcode": barcode}, {"_id": 0, "id": 1, "variants": 1})
        if prod:
            for v in (prod.get("variants") or []):
                if v.get("barcode") == barcode:
                    v["stock"] = max(0, int(v.get("stock", 0) or 0) + (delta * qty))
                    break
            new_total = sum(int(v.get("stock", 0) or 0) for v in prod.get("variants", []))
            await db.products.update_one(
                {"id": prod["id"]},
                {"$set": {"variants": prod["variants"], "stock": new_total, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            movements.append({"barcode": barcode, "delta": delta * qty, "product_id": prod["id"]})
        else:
            # Fallback product-level barcode
            p2 = await db.products.find_one({"barcode": barcode}, {"_id": 0, "id": 1})
            if p2:
                await db.products.update_one(
                    {"id": p2["id"]},
                    {"$inc": {"stock": delta * qty}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
                )
                movements.append({"barcode": barcode, "delta": delta * qty, "product_id": p2["id"]})
    return movements


@router.post("/{order_id}/apply-stock")
async def apply_stock_for_order(
    order_id: str,
    action: str = Query(..., description="'decrement' (new order) or 'increment' (cancel/refund)"),
    current_user: dict = Depends(require_admin)
):
    """Manually trigger stock adjustment for an order (use for reconciliation)."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    delta = -1 if action == "decrement" else 1
    moves = await _stock_delta_for_order(order, delta)
    await db.stock_movements.insert_one({
        "id": str(uuid.uuid4()),
        "type": f"manual_{action}",
        "order_id": order_id,
        "order_number": order.get("order_number", ""),
        "items": moves,
        "created_by": current_user.get("email", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"success": True, "items_affected": len(moves)}


@router.post("/auto-cancel-expired")
async def auto_cancel_expired_orders(
    hours: int = Query(48, ge=1),
    current_user: dict = Depends(require_admin)
):
    """Cancel orders that have been unpaid for more than N hours and restock."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    # Only cancel pending/unpaid orders
    query = {
        "payment_status": "pending",
        "status": {"$in": ["pending", "confirmed"]},
        "created_at": {"$lt": cutoff},
    }
    cancelled = 0
    async for order in db.orders.find(query, {"_id": 0}):
        moves = await _stock_delta_for_order(order, +1)
        await db.orders.update_one(
            {"id": order["id"]},
            {"$set": {
                "status": "cancelled",
                "payment_status": "expired",
                "cancel_reason": f"Ödeme {hours} saat içinde tamamlanmadı",
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        await db.stock_movements.insert_one({
            "id": str(uuid.uuid4()),
            "type": "auto_cancel_expired",
            "order_id": order["id"],
            "order_number": order.get("order_number", ""),
            "items": moves,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        cancelled += 1
    return {"success": True, "cancelled": cancelled, "hours": hours}


@router.post("/{order_id}/note")
async def add_order_note(
    order_id: str,
    payload: dict,
    current_user: dict = Depends(require_admin)
):
    """Add/update admin note on order (e.g. havale takip)."""
    note = (payload or {}).get("note", "").strip()
    existing = await db.orders.find_one({"id": order_id}, {"_id": 0, "id": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    notes_list = (await db.orders.find_one({"id": order_id}, {"_id": 0, "admin_notes": 1})).get("admin_notes") or []
    notes_list.append({
        "id": str(uuid.uuid4()),
        "text": note,
        "by": current_user.get("email", ""),
        "at": datetime.now(timezone.utc).isoformat(),
    })
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"admin_notes": notes_list, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "notes": notes_list}


# =============================================================================
# FAZ 5 — Kargo durum güncellemeleri (ship / undeliver / deliver)
# =============================================================================
VALID_CARGO_COMPANIES = {
    "MNG", "DHL", "Yurtici", "Aras", "PTT", "UPS", "HepsiJet", "Trendyol", "Other"
}


@router.post("/{order_id}/ship")
async def ship_order(
    order_id: str,
    cargo_company: str = Query(..., description="Kargo firması kodu"),
    tracking_number: str = Query(..., min_length=3, description="Kargo takip numarası"),
    current_user: dict = Depends(require_admin)
):
    """Siparişi kargoya ver: status=shipped + cargo_company + cargo_tracking_number.
    Bildirim hook'u (order_shipped) otomatik tetiklenir.
    """
    if cargo_company not in VALID_CARGO_COMPANIES:
        raise HTTPException(status_code=400, detail=f"Geçersiz kargo firması. Geçerli: {sorted(VALID_CARGO_COMPANIES)}")

    existing = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "status": "shipped",
            "cargo_company": cargo_company,
            "cargo_tracking_number": tracking_number.strip(),
            "shipped_at": now_iso,
            "updated_at": now_iso,
        }},
    )

    # Bildirim — fire-and-forget
    import asyncio as _asyncio
    async def _notify_ship():
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from notification_service import send_notification
            addr = existing.get("shipping_address") or {}
            await send_notification(
                db, "order_shipped",
                to_phone=addr.get("phone") or existing.get("phone"),
                to_email=addr.get("email") or existing.get("email"),
                variables={
                    "customer_name": addr.get("full_name") or addr.get("first_name") or "Müşterimiz",
                    "order_number": existing.get("order_number", ""),
                    "tracking_number": tracking_number.strip(),
                    "cargo_company": cargo_company,
                },
            )
        except Exception as _e:
            logger.warning(f"order_shipped notification failed: {_e}")
    _asyncio.create_task(_notify_ship())

    return {
        "success": True,
        "message": f"Sipariş {cargo_company} kargosuna verildi ({tracking_number})",
        "tracking_number": tracking_number,
    }


@router.post("/{order_id}/undeliver")
async def mark_order_undelivered(
    order_id: str,
    reason: str = Query("Kargo teslim edilemedi", description="Teslim edilememe nedeni"),
    branch_info: str = Query("", description="Şube bilgisi / nerede bekliyor"),
    current_user: dict = Depends(require_admin)
):
    """Kargo teslim edilemedi (şubede bekliyor) durumunu işaretler ve müşteriye bildirim atar."""
    existing = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "status": "undelivered",
            "undelivered_reason": reason,
            "undelivered_branch": branch_info,
            "undelivered_at": now_iso,
            "updated_at": now_iso,
        }},
    )

    import asyncio as _asyncio
    async def _notify_undeliver():
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from notification_service import send_notification
            addr = existing.get("shipping_address") or {}
            await send_notification(
                db, "order_undelivered",
                to_phone=addr.get("phone") or existing.get("phone"),
                to_email=addr.get("email") or existing.get("email"),
                variables={
                    "customer_name": addr.get("full_name") or addr.get("first_name") or "Müşterimiz",
                    "order_number": existing.get("order_number", ""),
                    "tracking_number": existing.get("cargo_tracking_number", ""),
                    "reason": reason,
                    "branch_info": branch_info,
                },
            )
        except Exception as _e:
            logger.warning(f"order_undelivered notification failed: {_e}")
    _asyncio.create_task(_notify_undeliver())

    return {"success": True, "message": "Teslim edilemedi olarak işaretlendi"}


@router.post("/{order_id}/mark-invoiced")
async def mark_order_invoiced(
    order_id: str,
    payload: dict,
    current_user: dict = Depends(require_admin)
):
    """Mark order as invoiced – locks edits, flips status to 'confirmed' if pending."""
    invoice_number = (payload or {}).get("invoice_number", "")
    existing = await db.orders.find_one({"id": order_id}, {"_id": 0, "status": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    update = {
        "invoice_issued": True,
        "invoice_number": invoice_number,
        "invoice_issued_at": datetime.now(timezone.utc).isoformat(),
        "invoice_issued_by": current_user.get("email", ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing.get("status") == "pending":
        update["status"] = "confirmed"
    await db.orders.update_one({"id": order_id}, {"$set": update})
    return {"success": True, "invoice_issued": True}



# ---------------------------------------------------------------------------
# E-Fatura oluşturma — aktif e-fatura entegratörünü kullanarak fatura keser.
# Aktif provider `providers_config` kolleksiyonundan okunur. Canlıda her
# provider için ayrı SDK çağrısı olacak; şu an mock başarı döner ama doğru
# provider adı + üretilmiş invoice_number ile kayıt altına alınır.
#
# FRONTEND: Orders.jsx handleGenerateInvoice + handleBulkGenerateInvoice.
# ---------------------------------------------------------------------------
@router.post("/{order_id}/create-invoice")
async def create_invoice_for_order(
    order_id: str,
    invoice_type: str = "auto",
    current_user: dict = Depends(require_admin),
):
    """
    Seçili sipariş için e-Arşiv / e-Fatura keser.

    invoice_type:
      - "auto" (default): Müşterinin VKN/TCKN'sini Doğan'da CheckUser ile sorgular,
        e-Fatura mükellefi ise e-Fatura, değilse veya VKN/TC boşsa e-Arşiv keser.
      - "e-arsiv": Zorla e-Arşiv (bireysel TCKN dolu/boş hepsi)
      - "e-fatura": Zorla e-Fatura (10 haneli VKN şart)
    """
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    if order.get("invoice_issued"):
        return {"success": True, "message": "Fatura zaten kesilmiş",
                "invoice_number": order.get("invoice_number", "")}

    # Mikro ihracat: gerçek e-Arşiv İSTİSNA faturası (InvoiceTypeCode=ISTISNA, KDV %0,
    # istisna 301 "11/1-a Mal ihracatı"). ETGB placeholder yerine normal e-Arşiv akışı;
    # build aşamasında export builder seçilir.
    if order.get("is_micro_export"):
        invoice_type = "e-arsiv"
    cfg = await db.providers_config.find_one({"kind": "einvoice"}, {"_id": 0})
    active = (cfg or {}).get("active_provider")
    providers = (cfg or {}).get("providers") or {}

    # Yeni: Doğan ayarları settings.id=dogan_edonusum altında saklanıyor
    dogan_settings = await db.settings.find_one({"id": "dogan_edonusum"}, {"_id": 0}) or {}
    dogan_active = dogan_settings.get("enabled") and dogan_settings.get("username")

    if not (active and providers.get(active)) and not dogan_active:
        raise HTTPException(
            status_code=400,
            detail="Aktif e-fatura entegratörü yapılandırılmamış. Ayarlar > E-Arşiv / E-Fatura ekranından seçin."
        )

    # Prefix — e-Arşiv: FCT, e-Fatura: EFC (kullanıcı belirleyebilir; default Doğan standardı)
    if dogan_active:
        active = "dogan"
    else:
        pcfg = providers[active]

    # ─── AKILLI HİBRİT MOD ─────────────────────────────────────────────
    # invoice_type="auto" (default): VKN/TCKN dolu ise Doğan CheckUser ile
    # mükellef sorgula → mükellef ise e-Fatura, değilse e-Arşiv. Boşsa e-Arşiv.
    bill = order.get("billing_address") or {}
    ship_addr = order.get("shipping_address") or {}
    customer_vkn_raw = (bill.get("tax_no") or "").strip().replace(" ", "")
    receiver_alias = ""

    if invoice_type == "auto" and dogan_active:
        if customer_vkn_raw and len(customer_vkn_raw) in (10, 11):
            # Doğan'a sor
            try:
                from dogan_client import DoganClient as _DC
                from fastapi.concurrency import run_in_threadpool as _rtp
                _tmp = _DC(
                    username=dogan_settings["username"],
                    password=dogan_settings["password"],
                    is_test=dogan_settings.get("is_test", True),
                )
                chk = await _rtp(_tmp.check_user, customer_vkn_raw)
                if chk.get("is_efatura") and len(customer_vkn_raw) == 10:
                    invoice_type = "e-fatura"
                    receiver_alias = chk.get("invoice_alias") or ""
                else:
                    invoice_type = "e-arsiv"
            except Exception as _e:
                logger.warning(f"CheckUser fallback to e-arsiv: {_e}")
                invoice_type = "e-arsiv"
        else:
            # VKN/TCKN boş → bireysel e-arşiv
            invoice_type = "e-arsiv"

    if dogan_active:
        prefix = (dogan_settings.get("earchive_prefix") if invoice_type == "e-arsiv"
                  else dogan_settings.get("einvoice_prefix"))
        if not prefix:
            prefix = "FCT" if invoice_type == "e-arsiv" else "EFC"
    else:
        prefix = (pcfg.get("earchive_prefix") if invoice_type == "e-arsiv"
                  else pcfg.get("einvoice_prefix"))
        if not prefix:
            prefix = "FCT" if invoice_type == "e-arsiv" else "EFC"

    # Sıra numarası: atomik sayaç (db.counters) — başarısız denemede bile ilerler,
    # aynı numara BİR DAHA üretilmez (Doğan 10009 "duplicate" önlenir).
    # Taban: panelde en son kesilen no'nun DEVAMI — dogan_edonusum.earchive_start_number
    # (yıl bazlı: earchive_start_year ilgili yıla eşitse uygulanır).
    year_str = datetime.now(timezone.utc).strftime("%Y")
    seq_key = f"invoice_seq_{prefix}{year_str}"
    base_start = 0
    try:
        if invoice_type == "e-arsiv":
            if str((dogan_settings or {}).get("earchive_start_year") or "") == year_str:
                base_start = int((dogan_settings or {}).get("earchive_start_number") or 0)
        else:
            if str((dogan_settings or {}).get("einvoice_start_year") or "") == year_str:
                base_start = int((dogan_settings or {}).get("einvoice_start_number") or 0)
    except Exception:
        base_start = 0
    _existing_ctr = await db.counters.find_one({"_id": seq_key})
    if _existing_ctr is None and base_start > 0:
        await db.counters.update_one(
            {"_id": seq_key}, {"$setOnInsert": {"seq": base_start - 1}}, upsert=True
        )
    await db.counters.update_one({"_id": seq_key}, {"$inc": {"seq": 1}}, upsert=True)
    _seq_doc = await db.counters.find_one({"_id": seq_key}) or {}
    seq = int(_seq_doc.get("seq", 1))
    invoice_number = f"{prefix}{year_str}{seq:09d}"
    invoice_uuid = generate_id()  # UUID-like

    now = datetime.now(timezone.utc)
    issue_date = now.strftime("%Y-%m-%d")
    issue_time = now.strftime("%H:%M:%S")

    # Gerçek Doğan e-Arşiv kesimi
    dogan_result = None
    if dogan_active and invoice_type == "e-arsiv":
        from dogan_client import DoganClient
        from fastapi.concurrency import run_in_threadpool

        # Müşteri VKN/TCKN — order'dan al, yoksa default 11111111111 (TCKN bilinmiyor)
        customer_vkn = customer_vkn_raw
        customer_name = (bill.get("name") or
                         f"{ship_addr.get('first_name','')} {ship_addr.get('last_name','')}".strip() or
                         "Bireysel Müşteri")
        if not customer_vkn:
            # TCKN yoksa Doğan kabul etmez — bireysel için varsayılan TCKN dön (test'te)
            customer_vkn = "11111111111"

        line_items = []
        for it in (order.get("items") or []):
            line_items.append({
                "name": it.get("product_name") or "Ürün",
                "qty": int(it.get("quantity") or 1),
                "unit_price": float(it.get("price") or 0),
                "kdv_rate": float(it.get("kdv_rate") or 10.0),
                "sku": it.get("sku") or it.get("product_code") or "",
                "barcode": it.get("barcode") or "",
                "note": (f"Renk:{it.get('color') or ''}; Beden:{it.get('size') or ''}: Barcode:{it.get('barcode') or ''}"
                         if (it.get('color') or it.get('size') or it.get('barcode'))
                         else ""),
            })

        # Taşıyan (kargo firması) — siparişin Trendyol'da beyan edilen kargosundan DİNAMİK.
        # Bilinen firmalar için ad+VKN; bilinmeyende Trendyol'un beyan adı, VKN boş (UBL'de atlanır).
        _cpn = (order.get("cargo_provider_name") or "")
        _cpl = _cpn.lower()
        if "trendyol" in _cpl:
            _carrier_name, _carrier_vkn, _carrier_city = "Trendyol Lojistik A.Ş.", "8590921777", "İstanbul"
        elif "mng" in _cpl:
            _carrier_name, _carrier_vkn, _carrier_city = "MNG KARGO YURTİÇİ VE YURTDIŞI TAŞIMACILIK A.Ş.", "6080712084", "İstanbul"
        elif ("yurtiçi" in _cpl) or ("yurtici" in _cpl):
            _carrier_name, _carrier_vkn, _carrier_city = "YURTİÇİ KARGO SERVİSİ A.Ş.", "9860008925", "İstanbul"
        elif "aras" in _cpl:
            _carrier_name, _carrier_vkn, _carrier_city = "ARAS KARGO YURT İÇİ YURT DIŞI TAŞIMACILIK A.Ş.", "0720039666", "İstanbul"
        elif _cpn.strip():
            _carrier_name, _carrier_vkn, _carrier_city = _cpn.replace("Marketplace", "").strip(" -"), "", "İstanbul"
        else:
            _carrier_name, _carrier_vkn, _carrier_city = "MNG KARGO YURTİÇİ VE YURTDIŞI TAŞIMACILIK A.Ş.", "6080712084", "İstanbul"

        _earsiv_kwargs = dict(
            invoice_uuid=invoice_uuid,
            invoice_number=invoice_number,
            issue_date=issue_date,
            issue_time=issue_time,
            supplier_vkn=dogan_settings.get("vkn") or "7810816779",
            supplier_name=dogan_settings.get("supplier_name") or "FACETTE DIŞ. TİC.A.Ş",
            supplier_district=dogan_settings.get("supplier_district") or "KÜÇÜKÇEKMECE",
            supplier_city=dogan_settings.get("supplier_city") or "İstanbul",
            supplier_street=dogan_settings.get("supplier_street") or "",
            supplier_tax_office=dogan_settings.get("supplier_tax_office") or "HALKALI VERGİ DAİRESİ BAŞKANLIĞI",
            supplier_phone=dogan_settings.get("supplier_phone") or "",
            supplier_email=dogan_settings.get("supplier_email") or "",
            supplier_website=dogan_settings.get("supplier_website") or "facette.com.tr",
            customer_vkn_or_tckn=customer_vkn,
            customer_name=customer_name,
            customer_district=ship_addr.get("district") or "",
            customer_city=ship_addr.get("city") or "",
            customer_street=ship_addr.get("address") or "",
            customer_postal_zone=ship_addr.get("postal_code") or ship_addr.get("zip") or ship_addr.get("postal_zone") or "",
            customer_phone=ship_addr.get("phone") or "",
            customer_email=ship_addr.get("email") or order.get("user_email") or "",
            customer_tax_office=bill.get("tax_office") or "",
            currency="TRY",
            kdv_rate=10.0,
            line_items=line_items,
            shipping_cost=float(order.get("shipping_cost") or 0),
            discount=0.0,
            order_number=order.get("order_number") or order_id,
            payment_method=order.get("payment_method") or "DIGER",
            cargo_tracking=str(order.get("cargo_tracking_number") or order.get("cargo_tracking") or order.get("tracking_number") or ""),
            order_ext_id=str(order.get("marketplace_order_id") or order.get("platform_order_id") or order.get("order_number") or ""),
            store_name=order.get("store_name") or order.get("marketplace") or "",
            payment_amount=float(order.get("total") or order.get("total_amount") or order.get("grand_total") or 0),
            carrier_name=_carrier_name,
            carrier_vkn=_carrier_vkn,
            carrier_city=_carrier_city,
            note="",
        )
        _earsiv_builder = (DoganClient.build_earsiv_export_ubl_xml
                           if order.get("is_micro_export")
                           else DoganClient.build_earsiv_ubl_xml)
        ubl_xml = _earsiv_builder(**_earsiv_kwargs)

        dogan_client = DoganClient(
            username=dogan_settings["username"],
            password=dogan_settings["password"],
            is_test=dogan_settings.get("is_test", True),
        )
        # Müşteri e-postasına PDF gönder
        cust_email = (ship_addr.get("email") or order.get("user_email") or "").strip()
        archive_note = f"Sipariş No: {order.get('order_number') or order_id}"
        dogan_result = await run_in_threadpool(
            dogan_client.send_earsiv_invoice,
            ubl_xml, invoice_uuid, cust_email, archive_note,
        )
        # Cift-numara korumasi: Dogan "zaten kayitli/mukerrer/10009" -> siradaki no
        _ex_tries = 0
        while (not dogan_result.get("success")) and _ex_tries < 5 and any(_t in str(dogan_result.get("message","")).lower() for _t in ("zaten","mükerrer","mukerrer","duplicate","already","10009","kayıtlı","kayitli","mevcut")):
            _ex_tries += 1
            await db.counters.update_one({"_id": seq_key}, {"$inc": {"seq": 1}}, upsert=True)
            _sd = await db.counters.find_one({"_id": seq_key}) or {}
            seq = int(_sd.get("seq", 1))
            invoice_number = f"{prefix}{year_str}{seq:09d}"
            invoice_uuid = generate_id()
            _earsiv_kwargs["invoice_number"] = invoice_number
            _earsiv_kwargs["invoice_uuid"] = invoice_uuid
            logger.warning(f"e-Arsiv numara cakismasi -> siradaki: {invoice_number} (deneme {_ex_tries})")
            ubl_xml = _earsiv_builder(**_earsiv_kwargs)
            dogan_result = await run_in_threadpool(
                dogan_client.send_earsiv_invoice,
                ubl_xml, invoice_uuid, cust_email, archive_note,
            )

        if not dogan_result.get("success"):
            logger.error(f"DOGAN_RET earsiv: {dogan_result}")
            # Hatayı log'a yaz, mock fallback ile devam etme — gerçek hata bildir
            raise HTTPException(
                status_code=502,
                detail=f"Doğan e-Arşiv hatası: {dogan_result.get('message')}"
            )

    # ─── Doğan e-Fatura (TEMELFATURA) kesimi ─────────────────────────
    if dogan_active and invoice_type == "e-fatura":
        from dogan_client import DoganClient
        from fastapi.concurrency import run_in_threadpool

        customer_vkn = customer_vkn_raw
        if not customer_vkn or len(customer_vkn) != 10:
            raise HTTPException(
                status_code=400,
                detail="e-Fatura için 10 haneli VKN gerekli, müşteride yok."
            )
        customer_name = (bill.get("name") or
                         f"{ship_addr.get('first_name','')} {ship_addr.get('last_name','')}".strip() or
                         "Müşteri")

        # receiver_alias auto-mode'da çekildi; explicit invoice_type=e-fatura
        # çağrısında alias yoksa CheckUser ile tamamla
        if not receiver_alias:
            try:
                _tmp_cli = DoganClient(
                    username=dogan_settings["username"],
                    password=dogan_settings["password"],
                    is_test=dogan_settings.get("is_test", True),
                )
                chk = await run_in_threadpool(_tmp_cli.check_user, customer_vkn)
                receiver_alias = chk.get("invoice_alias") or ""
            except Exception:
                pass
        if not receiver_alias:
            raise HTTPException(
                status_code=400,
                detail=f"Müşteri ({customer_vkn}) e-Fatura mükellefi değil veya alias bulunamadı."
            )

        line_items = []
        for it in (order.get("items") or []):
            line_items.append({
                "name": it.get("product_name") or "Ürün",
                "qty": int(it.get("quantity") or 1),
                "unit_price": float(it.get("price") or 0),
                "kdv_rate": float(it.get("kdv_rate") or 10.0),
                "sku": it.get("sku") or it.get("product_code") or "",
                "buyer_sku": it.get("sku") or it.get("product_code") or "",
                "barcode": it.get("barcode") or "",
                "note": (f"{it.get('product_name', '')}, Renk:{it.get('color') or ''}, Beden:{it.get('size') or ''}"
                         if (it.get('color') or it.get('size'))
                         else ""),
            })

        _efatura_kwargs = dict(
            invoice_uuid=invoice_uuid,
            invoice_number=invoice_number,
            issue_date=issue_date,
            issue_time=issue_time,
            supplier_vkn=dogan_settings.get("vkn") or "7810816779",
            supplier_name=dogan_settings.get("supplier_name") or "FACETTE DIŞ. TİC.A.Ş",
            supplier_district=dogan_settings.get("supplier_district") or "KÜÇÜKÇEKMECE",
            supplier_city=dogan_settings.get("supplier_city") or "İstanbul",
            supplier_tax_office=dogan_settings.get("supplier_tax_office") or "HALKALI VERGİ DAİRESİ BAŞKANLIĞI",
            supplier_website=dogan_settings.get("supplier_website") or "facette.com.tr",
            customer_vkn=customer_vkn,
            customer_name=customer_name,
            customer_street=ship_addr.get("address") or "",
            customer_district=ship_addr.get("district") or "",
            customer_city=ship_addr.get("city") or "İstanbul",
            customer_postal_zone=ship_addr.get("postal_code") or "34000",
            customer_email=ship_addr.get("email") or order.get("user_email") or "",
            currency="TRY",
            kdv_rate=10.0,
            line_items=line_items,
            shipping_cost=float(order.get("shipping_cost") or 0),
            discount=0.0,
            order_number=order.get("order_number") or order_id,
            order_date=(order.get("created_at") or now.isoformat())[:10],
        )
        ubl_xml = DoganClient.build_efatura_ubl_xml(**_efatura_kwargs)

        dogan_client = DoganClient(
            username=dogan_settings["username"],
            password=dogan_settings["password"],
            is_test=dogan_settings.get("is_test", True),
        )
        cust_email = (ship_addr.get("email") or order.get("user_email") or "").strip()
        sender_alias = dogan_settings.get("sender_alias") or ""
        dogan_result = await run_in_threadpool(
            dogan_client.send_efatura_invoice,
            ubl_xml, invoice_uuid, invoice_number,
            customer_vkn, receiver_alias, sender_alias, cust_email,
        )
        _ef_tries = 0
        while (not dogan_result.get("success")) and _ef_tries < 5 and any(_t in str(dogan_result.get("message","")).lower() for _t in ("zaten","mükerrer","mukerrer","duplicate","already","10009","kayıtlı","kayitli","mevcut")):
            _ef_tries += 1
            await db.counters.update_one({"_id": seq_key}, {"$inc": {"seq": 1}}, upsert=True)
            _sd = await db.counters.find_one({"_id": seq_key}) or {}
            seq = int(_sd.get("seq", 1))
            invoice_number = f"{prefix}{year_str}{seq:09d}"
            invoice_uuid = generate_id()
            _efatura_kwargs["invoice_number"] = invoice_number
            _efatura_kwargs["invoice_uuid"] = invoice_uuid
            logger.warning(f"e-Fatura numara cakismasi -> siradaki: {invoice_number} (deneme {_ef_tries})")
            ubl_xml = DoganClient.build_efatura_ubl_xml(**_efatura_kwargs)
            dogan_result = await run_in_threadpool(
                dogan_client.send_efatura_invoice,
                ubl_xml, invoice_uuid, invoice_number,
                customer_vkn, receiver_alias, sender_alias, cust_email,
            )

        if not dogan_result.get("success"):
            logger.error(f"DOGAN_RET efatura: {dogan_result}")
            raise HTTPException(
                status_code=502,
                detail=f"Doğan e-Fatura hatası: {dogan_result.get('message')}"
            )

    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "invoice_issued": True,
            "invoice_number": invoice_number,
            "invoice_uuid": invoice_uuid,
            "invoice_type": invoice_type,
            "invoice_provider": active,
            "invoice_provider_response": dogan_result,
            "invoice_intl_txn_id": (dogan_result or {}).get("intl_txn_id", ""),
            "invoice_dogan_id": (dogan_result or {}).get("invoice_id", ""),
            "invoice_pdf_url": (dogan_result or {}).get("web_key", ""),
            "invoice_issued_at": now.isoformat(),
            "invoice_issued_by": current_user.get("email", ""),
            "updated_at": now.isoformat(),
        }}
    )

    # Log — integration_logs'a ekle
    try:
        from .marketplace_hub import log_integration_event
        await log_integration_event(
            marketplace=f"einvoice:{active}",
            action="invoice_create",
            status="success",
            direction="outbound",
            ref_id=order_id,
            message=f"{invoice_type} fatura oluşturuldu: {invoice_number} (Doğan: {dogan_result.get('message') if dogan_result else 'mock'})",
        )
    except Exception:
        pass

    return {
        "success": True,
        "message": "Fatura oluşturuldu",
        "invoice_number": invoice_number,
        "invoice_type": invoice_type,
        "provider": active,
    }


# ---------------------------------------------------------------------------
# FATURA YAZDIR (HTML) — Orders.jsx handleBulkPrintInvoices iframe src olarak
# bu endpoint'i kullanır. Basit bir A4 fatura HTML'i döner; gerçek XSL-UBL
# dönüşümü canlıda provider'dan gelen PDF URL'siyle değiştirilir.
# ---------------------------------------------------------------------------
@router.get("/{order_id}/invoice/print")
async def print_invoice_html(order_id: str, token: str = None):
    """Basit fatura HTML çıktısı (yazdırılabilir). Bulk print için iframe."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    addr = order.get("shipping_address") or {}
    items = order.get("items") or []
    total = order.get("total") or order.get("total_amount") or 0

    rows = "".join(
        f"<tr><td>{i.get('product_name','')}</td>"
        f"<td style='text-align:center'>{i.get('quantity',1)}</td>"
        f"<td style='text-align:right'>{(i.get('price') or 0):.2f} ₺</td>"
        f"<td style='text-align:right'>{((i.get('price') or 0)*(i.get('quantity') or 1)):.2f} ₺</td></tr>"
        for i in items
    )

    from fastapi.responses import HTMLResponse
    html = f"""
<!doctype html><html lang="tr"><head><meta charset="utf-8"/>
<title>Fatura — {order.get('invoice_number') or order.get('order_number','')}</title>
<style>
  @page {{ size: A4; margin: 15mm; }}
  body {{ font-family: -apple-system, Arial, sans-serif; color:#111; margin:0; }}
  .header {{ display:flex; justify-content:space-between; border-bottom:2px solid #111; padding-bottom:10px; margin-bottom:16px; }}
  .brand {{ font-size:20px; font-weight:800; letter-spacing:.1em; }}
  h1 {{ font-size:18px; margin:0 0 8px; }}
  table {{ width:100%; border-collapse:collapse; margin-top:12px; font-size:12px; }}
  th, td {{ padding:6px 8px; border-bottom:1px solid #eee; }}
  th {{ background:#f9fafb; text-align:left; }}
  .totals {{ margin-top:12px; text-align:right; }}
  .grand {{ font-size:16px; font-weight:800; margin-top:4px; }}
  .meta {{ font-size:11px; color:#555; }}
</style></head><body>
<div class="header">
  <div>
    <div class="brand">FACETTE</div>
    <div class="meta">Facette E-Ticaret · facette.com.tr</div>
  </div>
  <div style="text-align:right">
    <h1>{'E-ARŞİV FATURA' if order.get('invoice_type')=='e-arsiv' else 'E-FATURA'}</h1>
    <div class="meta">No: <strong>{order.get('invoice_number') or '-'}</strong></div>
    <div class="meta">Tarih: {(order.get('invoice_issued_at') or order.get('created_at') or '')[:10]}</div>
    <div class="meta">Sipariş: {order.get('order_number','')}</div>
  </div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:12px;">
  <div>
    <div class="meta" style="font-weight:700">Alıcı:</div>
    <div>{addr.get('full_name','')}</div>
    <div class="meta">{addr.get('address','')}</div>
    <div class="meta">{addr.get('district','')} / {addr.get('city','')}</div>
    <div class="meta">Tel: {addr.get('phone','')}</div>
  </div>
  <div>
    <div class="meta" style="font-weight:700">Sipariş Kanalı:</div>
    <div>{order.get('channel') or 'web'}</div>
    <div class="meta">Ödeme: {order.get('payment_method','-')}</div>
  </div>
</div>
<table>
  <thead><tr><th>Ürün</th><th style="text-align:center">Adet</th><th style="text-align:right">Birim</th><th style="text-align:right">Tutar</th></tr></thead>
  <tbody>{rows or '<tr><td colspan=4 style="text-align:center">Kalem yok</td></tr>'}</tbody>
</table>
<div class="totals">
  <div class="grand">Toplam: {float(total):.2f} ₺</div>
</div>
<p class="meta" style="margin-top:24px;border-top:1px solid #eee;padding-top:10px;">
  Bu belge e-Arşiv fatura olup, aktif entegratör
  <strong>{order.get('invoice_provider') or '-'}</strong> üzerinden üretilmiştir.
</p>
</body></html>
"""
    return HTMLResponse(content=html)



# ==================== KARGO BARKOD / MNG SHIPMENT ====================

def _normalize_phone(p: str) -> str:
    if not p:
        return ""
    digits = "".join(ch for ch in str(p) if ch.isdigit())
    # Türkiye: 90XXXXXXXXXX (12) → 5XXXXXXXXX (10) format, MNG cep formatı tercih eder
    if digits.startswith("90") and len(digits) == 12:
        return digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        return digits[1:]
    return digits


async def _get_mng_settings() -> dict:
    """MNG Kargo ayarlarını DB'den çeker, yoksa kullanıcı tarafından verilen default'u döndürür."""
    s = await db.settings.find_one({"id": "mng_kargo"}, {"_id": 0}) or {}
    return {
        "username": s.get("username") or "490059279",
        "password": s.get("password") or "Face.0024E",
        "customer_code": s.get("customer_code") or "FACETTE DIŞ TİC.A.Ş.",
        "tax_no": s.get("tax_no") or "6080712084",
        "is_active": s.get("is_active", True),
    }


async def _get_sender_info() -> dict:
    """Mağaza/Gönderici bilgilerini DB'den çeker (settings.id=store_info veya mng_kargo)."""
    store = await db.settings.find_one({"id": "store_info"}, {"_id": 0}) or {}
    return {
        "name": store.get("sender_name") or "FACETTE",
        "phone": _normalize_phone(store.get("sender_phone") or "5550000000"),
        "address": store.get("sender_address") or "",
        "city": store.get("sender_city") or "İstanbul",
        "district": store.get("sender_district") or "",
    }


@router.post("/{order_id}/cargo-barcode")
async def create_cargo_barcode(
    order_id: str,
    cargo_company: str = Query("MNG"),
    current_user: dict = Depends(require_admin)
):
    """Aktif kargo firmasında barkod / takip numarası oluşturur ve sipariş üzerine yazar.
    Şu an MNG Kargo entegrasyonu canlı; diğer firmalar için manuel takip no input'u gerekir.
    """
    company = (cargo_company or "MNG").upper()
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    # Eğer mevcut barkod varsa direkt dön
    if order.get("cargo_tracking_number"):
        return {
            "success": True,
            "tracking_number": order["cargo_tracking_number"],
            "cargo_provider_name": order.get("cargo_provider_name") or company,
            "message": "Sipariş zaten kargo barkoduna sahip",
        }

    if company != "MNG":
        # Diğer firmalar için sahte/placeholder takip no üret (henüz canlı entegrasyon yok)
        import random
        tracking = f"{company}-{int(time.time())}{random.randint(100,999)}"
        await db.orders.update_one(
            {"id": order_id},
            {"$set": {
                "cargo_tracking_number": tracking,
                "cargo_provider_name": company,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        return {
            "success": True,
            "tracking_number": tracking,
            "cargo_provider_name": company,
            "message": f"{company} için manuel takip no atandı (canlı API entegrasyonu yok)",
        }

    # ===== MNG KARGO CANLI =====
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from mng_kargo_client import create_shipment as mng_create

    settings = await _get_mng_settings()
    if not settings["is_active"]:
        raise HTTPException(status_code=400, detail="MNG Kargo entegrasyonu pasif. Lütfen Ayarlar > Kargo bölümünden aktif edin.")

    # Sipariş üzerinden teslim adresini al
    ship = order.get("shipping_address") or {}
    full_name = (
        f"{ship.get('first_name','')} {ship.get('last_name','')}".strip()
        or ship.get("name")
        or "Alıcı"
    )
    phone = _normalize_phone(ship.get("phone"))
    if not phone:
        raise HTTPException(status_code=400, detail="Alıcı telefonu eksik. MNG barkodu oluşturulamaz.")
    il = (ship.get("city") or "").strip()
    ilce = (ship.get("district") or "").strip()
    adres = (ship.get("address") or "").strip()
    if not (il and adres):
        raise HTTPException(status_code=400, detail="Alıcı il ve adresi eksik. MNG barkodu oluşturulamaz.")

    # İçerik: ürün isimleri (ilk 250 karakter)
    items = order.get("items") or []
    icerik = "; ".join([f"{it.get('quantity',1)}x {it.get('product_name','')}".strip() for it in items])[:250] or "Ürün"
    kiymet = float(order.get("total") or order.get("subtotal") or 0)

    # Sipariş numarası (MNG için unique olmalı, varsa siparişin order_number'ı)
    siparis_no = str(order.get("order_number") or order.get("id") or order_id)

    # Kapıda ödeme?
    payment_method = (order.get("payment_method") or "").lower()
    kapida = 1 if payment_method in ("cash_on_delivery", "kapida") else 0
    odeme_sekli = "U" if kapida else "P"  # P=Peşin (Gönderici Öder), U=Ücretli (Alıcı Öder)

    res = mng_create(
        username=settings["username"],
        password=settings["password"],
        siparis_no=siparis_no,
        irsaliye_no=str(order.get("invoice_number") or "")[:20],
        kiymet=kiymet,
        icerik=icerik,
        hizmet_sekli="NORMAL",  # NORMAL | ONCELIKLI | GUNICI | AKSAM_TESLIMAT
        teslim_sekli=1,
        al_sms=0,
        gn_sms=1 if phone else 0,
        # MNG format: "Kg:Desi:En:Boy:Yukseklik:;" (her paket ; ile ayrılır)
        # Varsayılan: 1 paket, 1kg, 1 desi, 20x30x15cm
        parca_list="1:1:20:30:15:;",
        alici_ad=full_name,
        odeme_sekli=odeme_sekli,
        adres_farkli="0",
        il=il,
        ilce=ilce,
        adres=adres,
        tel_cep=phone,
        email=ship.get("email") or order.get("user_email") or "",
        kapida_odeme=kapida,
        platform_adi="",  # Pazaryeri değil — boş geç (N11/GG/TRND aksi takdirde)
        platform_kodu="",
    )

    if not res.get("ok"):
        # MNG hatasını orderhist log et
        await db.cargo_logs.insert_one({
            "id": generate_id(),
            "order_id": order_id,
            "provider": "MNG",
            "action": "create_shipment",
            "status": "error",
            "request_summary": {"siparis_no": siparis_no, "alici_ad": full_name, "il": il, "ilce": ilce},
            "error": res.get("hata"),
            "raw": str(res.get("raw"))[:1000] if res.get("raw") else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        raise HTTPException(status_code=502, detail=f"MNG Kargo hatası: {res.get('hata') or 'Bilinmeyen hata'}")

    barkod = res["barkod"]  # MNG_SIPARIS_NO (MNG Self Barkod) — gerçek kargo takip kodu
    
    # MNGGonderiBarkod denemesi → NZ-formatlı kargo barkodu (kurumsal hesaplarda anında dolar).
    # Yetki hatası alırsa graceful fallback: MNG_SIPARIS_NO kullanılır.
    nz_barkod = ""
    nz_gonderi_no = ""
    try:
        from mng_kargo_client import get_mng_barcode_immediately
        kapida = (order.get("payment_method") or "").lower() in ("cash_on_delivery", "kapida")
        nz_res = get_mng_barcode_immediately(
            username=settings["username"], password=settings["password"],
            siparis_no=siparis_no,
            irsaliye_no=str(order.get("invoice_number") or "")[:20],
            urun_bedeli=kiymet,
            kapida_tahsilat=kapida,
        )
        if nz_res.get("ok"):
            nz_barkod = nz_res.get("barkod", "")
            nz_gonderi_no = nz_res.get("gonderi_no", "")
            logger.info(f"MNG NZ barkod alındı: {nz_barkod} (gonderi_no={nz_gonderi_no})")
        else:
            logger.info(f"MNGGonderiBarkod denenemedi/başarısız (graceful fallback): {nz_res.get('hata')}")
    except Exception as nz_err:
        logger.warning(f"MNGGonderiBarkod exception (fallback to siparis_no): {nz_err}")

    # FaturaSiparisListesi'nden ek kargo durumu çek (şube, kargo statu, varsa GONDERI_NO)
    from mng_kargo_client import get_mng_shipment_status
    status_info = get_mng_shipment_status(
        username=settings["username"], password=settings["password"], siparis_no=siparis_no
    )
    gonderi_no_status = (status_info.get("gonderi_no") or "") if status_info.get("ok") else ""
    kargo_takip_url = (status_info.get("kargo_takip_url") or "") if status_info.get("ok") else ""
    kargo_statu = (status_info.get("kargo_statu") or "0") if status_info.get("ok") else "0"
    kargo_statu_aciklama = (status_info.get("kargo_statu_aciklama") or "") if status_info.get("ok") else ""

    # Self Barkod hesapları için: MNG_SIPARIS_NO zaten gerçek kargo takip kodudur
    # NZ-formatlı havuz tahsis edilen kurumsal hesaplarda GONDERI_NO field'ında ayrı bir kod gelir
    # Öncelik: NZ (anında MNGGonderiBarkod) → GONDERI_NO (FaturaSiparisListesi sonradan dolu) → MNG_SIPARIS_NO
    public_tracking = nz_barkod or nz_gonderi_no or gonderi_no_status or barkod
    track_link = kargo_takip_url or (f"https://kargotakip.mngkargo.com.tr/?BarkodNo={public_tracking}" if public_tracking else "")
    update_doc = {
        "cargo_tracking_number": public_tracking,
        "cargo_tracking_link": track_link,
        "cargo_provider_name": "MNG Kargo",
        "cargo_provider_code": "MNG",
        "cargo": {
            "provider": "MNG",
            "provider_name": "MNG Kargo",
            "tracking_number": public_tracking,
            "tracking_link": track_link,
            "label_format": "10x15cm",
            "mng_siparis_no": barkod,                      # MNG Self Barkod (her zaman dolu)
            "mng_gonderi_no": gonderi_no_status,           # NZ formatlı (FaturaSiparisListesi sonrası)
            "mng_nz_barkod": nz_barkod,                    # NZ formatlı (MNGGonderiBarkod anında, varsa)
            "mng_nz_gonderi_no": nz_gonderi_no,
            "mng_kargo_statu": kargo_statu,
            "mng_kargo_statu_aciklama": kargo_statu_aciklama,
            "cikis_subesi": status_info.get("cikis_subesi"),
            "teslim_subesi": status_info.get("teslim_subesi"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "status": "shipped" if order.get("status") in ("pending", "confirmed", "processing") else order.get("status"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.orders.update_one({"id": order_id}, {"$set": update_doc})

    # Otomatik müşteri bildirimi (SMS + WhatsApp + Email) — kargoya verildi
    try:
        from notification_service import send_notification
        ship_addr = order.get("shipping_address") or {}
        full_name = (
            f"{ship_addr.get('first_name','')} {ship_addr.get('last_name','')}".strip()
            or ship_addr.get("name") or ""
        )
        await send_notification(
            db,
            event="order_shipped",
            to_phone=ship_addr.get("phone") or order.get("customer_phone"),
            to_email=ship_addr.get("email") or order.get("customer_email") or order.get("user_email"),
            variables={
                "name": full_name,
                "first_name": ship_addr.get("first_name", ""),
                "order_number": order.get("order_number") or order_id,
                "tracking_number": barkod,
                "tracking_link": track_link,
                "cargo_provider": "MNG Kargo",
                "total": float(order.get("total") or 0),
            },
        )
    except Exception as ne:
        logger.warning(f"Kargo bildirimi gönderilemedi (order={order_id}): {ne}")
    await db.cargo_logs.insert_one({
        "id": generate_id(),
        "order_id": order_id,
        "provider": "MNG",
        "action": "create_shipment",
        "status": "success",
        "tracking_number": barkod,
        "request_summary": {"siparis_no": siparis_no, "alici_ad": full_name, "il": il, "ilce": ilce},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "success": True,
        "tracking_number": public_tracking,
        "tracking_link": track_link,
        "mng_siparis_no": barkod,
        "mng_gonderi_no": gonderi_no_status,
        "mng_kargo_statu": kargo_statu,
        "cargo_provider_name": "MNG Kargo",
        "message": f"✅ MNG kargo barkodu oluşturuldu: {public_tracking}",
    }


@router.post("/{order_id}/cargo-refresh")
async def refresh_cargo_tracking(order_id: str, current_user: dict = Depends(require_admin)):
    """MNG'den güncel kargo durumunu çek ve order'ı güncelle.
    
    Sıra: (1) MNGGonderiBarkod (anında NZ barkod) → (2) FaturaSiparisListesi (durum/şube)
    UI'dan "Yenile" butonu ile çağrılabilir.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from mng_kargo_client import get_mng_shipment_status

    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    cargo = order.get("cargo") or {}
    siparis_no = str(order.get("order_number") or order_id)
    settings = await _get_mng_settings()

    info = get_mng_shipment_status(
        username=settings["username"], password=settings["password"], siparis_no=siparis_no
    )
    if not info.get("ok"):
        raise HTTPException(status_code=502, detail=info.get("error") or "MNG durumu alınamadı")

    gonderi_no = info.get("gonderi_no") or ""
    mng_siparis_no = info.get("mng_siparis_no") or cargo.get("mng_siparis_no") or ""
    public_tracking = gonderi_no or mng_siparis_no
    track_link = info.get("kargo_takip_url") or (f"https://kargotakip.mngkargo.com.tr/?BarkodNo={public_tracking}" if public_tracking else "")

    update = {
        "cargo_tracking_number": public_tracking,
        "cargo_tracking_link": track_link,
        "cargo.tracking_number": public_tracking,
        "cargo.tracking_link": track_link,
        "cargo.mng_siparis_no": mng_siparis_no,
        "cargo.mng_gonderi_no": gonderi_no,
        "cargo.mng_kargo_statu": info.get("kargo_statu"),
        "cargo.mng_kargo_statu_aciklama": info.get("kargo_statu_aciklama"),
        "cargo.cikis_subesi": info.get("cikis_subesi"),
        "cargo.teslim_subesi": info.get("teslim_subesi"),
        "cargo.teslim_tarihi": info.get("teslim_tarihi"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.orders.update_one({"id": order_id}, {"$set": update})
    return {
        "success": True,
        "tracking_number": public_tracking,
        "mng_siparis_no": mng_siparis_no,
        "mng_gonderi_no": gonderi_no,
        "kargo_statu": info.get("kargo_statu"),
        "kargo_statu_aciklama": info.get("kargo_statu_aciklama"),
        "tracking_link": track_link,
        "message": (
            f"📦 Gönderi No: {gonderi_no}" if gonderi_no else
            f"✅ Güncel takip: {public_tracking} ({info.get('kargo_statu_aciklama') or 'durum güncellendi'})"
        ),
    }


@router.post("/{order_id}/create-mng-shipment")
async def create_mng_shipment(order_id: str, current_user: dict = Depends(require_admin)):
    """MNG Kargo'ya sipariş gönder ve barkod al (kısayol)."""
    return await create_cargo_barcode(order_id=order_id, cargo_company="MNG", current_user=current_user)


@router.post("/bulk/cargo-barcode")
async def bulk_create_cargo_barcode(
    order_ids: List[str],
    cargo_company: str = Query("MNG"),
    current_user: dict = Depends(require_admin)
):
    """Birden çok sipariş için topluca kargo barkodu oluştur."""
    success = []
    errors = []
    for oid in order_ids or []:
        try:
            r = await create_cargo_barcode(order_id=oid, cargo_company=cargo_company, current_user=current_user)
            success.append({"order_id": oid, "tracking_number": r.get("tracking_number")})
        except HTTPException as he:
            errors.append({"order_id": oid, "error": he.detail})
        except Exception as e:
            errors.append({"order_id": oid, "error": str(e)})
    return {
        "success": True,
        "success_count": len(success),
        "error_count": len(errors),
        "successes": success,
        "errors": errors,
    }


@router.post("/bulk/create-invoice")
async def bulk_create_invoice(
    order_ids: List[str],
    invoice_type: str = Query("auto"),
    current_user: dict = Depends(require_admin)
):
    """Toplu fatura kesimi — invoice_type=auto ile her sipariş için VKN/TC kontrolü
    yapılır, mükellefse e-Fatura, değilse e-Arşiv kesilir.
    """
    success = []
    errors = []
    for oid in order_ids or []:
        try:
            # Daha önce kesilmişse atla
            o = await db.orders.find_one({"id": oid}, {"_id": 0, "invoice_issued": 1, "order_number": 1})
            if not o:
                errors.append({"order_id": oid, "error": "Sipariş bulunamadı"})
                continue
            if o.get("invoice_issued"):
                errors.append({"order_id": oid, "error": "Fatura zaten kesilmiş", "skipped": True})
                continue
            r = await create_invoice_for_order(
                order_id=oid, invoice_type=invoice_type, current_user=current_user
            )
            success.append({
                "order_id": oid,
                "invoice_number": r.get("invoice_number"),
                "invoice_type": r.get("invoice_type"),
                "invoice_pdf_url": r.get("invoice_pdf_url"),
            })
        except HTTPException as he:
            errors.append({"order_id": oid, "error": str(he.detail)})
        except Exception as e:
            errors.append({"order_id": oid, "error": str(e)})
    return {
        "success": True,
        "success_count": len(success),
        "error_count": len(errors),
        "successes": success,
        "errors": errors,
    }


# ═══════════════════ MNG KARGO WEBHOOK ═══════════════════════════════
@router.post("/cargo/mng-webhook")
async def mng_cargo_webhook(payload: dict):
    """MNG Kargo'dan gelen kargo durum güncelleme webhook'u.

    MNG Kargo, gönderi durumu değiştikçe önceden tanımlanmış URL'e bu yapıda
    POST atar:
      {"BARKOD": "NZ123", "ISLEM_KODU": "300", "ISLEM_ADI": "Dağıtımda",
       "TARIH": "2026-05-06T12:30:00", "REFERANS_NO": "FC123ABCD"}

    İşlem kodları (MNG standardı):
      - 100: Şubeye girdi
      - 200: Transfere alındı
      - 300: Dağıtıma çıktı
      - 400: Teslim edildi
      - 500: İade
    """
    barkod = (payload.get("BARKOD") or payload.get("barcode") or "").strip()
    islem_kodu = str(payload.get("ISLEM_KODU") or payload.get("status_code") or "")
    islem_adi = (payload.get("ISLEM_ADI") or payload.get("status_text") or "").strip()
    tarih = (payload.get("TARIH") or payload.get("event_time") or
             datetime.now(timezone.utc).isoformat())
    referans_no = (payload.get("REFERANS_NO") or payload.get("reference_no") or "").strip()

    if not barkod and not referans_no:
        raise HTTPException(status_code=400, detail="BARKOD veya REFERANS_NO zorunlu")

    # Siparişi barkod veya referans_no ile bul
    query_or = []
    if barkod:
        query_or.extend([
            {"cargo_tracking_number": barkod},
            {"cargo.mng_nz_barkod": barkod},
            {"cargo.mng_gonderi_no": barkod},
            {"cargo.mng_siparis_no": barkod},
        ])
    if referans_no:
        query_or.append({"order_number": referans_no})

    order = await db.orders.find_one({"$or": query_or}, {"_id": 0, "id": 1, "order_number": 1, "cargo_status_history": 1})
    if not order:
        # Sessizce 200 dön — MNG retry yapmasın, sadece logla
        await db.integration_logs.insert_one({
            "id": generate_id(),
            "service": "mng_kargo",
            "event": "webhook_unknown_order",
            "barkod": barkod,
            "referans_no": referans_no,
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"success": True, "matched": False}

    # Sipariş durumu mapping
    status_map = {
        "100": ("preparing", "Şubeye Girdi"),
        "200": ("shipped", "Transfere Alındı"),
        "300": ("shipped", "Dağıtımda"),
        "400": ("delivered", "Teslim Edildi"),
        "500": ("returned", "İade"),
    }
    new_status, _ = status_map.get(islem_kodu, (None, None))

    update_set = {
        "cargo_last_status_code": islem_kodu,
        "cargo_last_status_text": islem_adi,
        "cargo_last_event_at": tarih,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if new_status:
        update_set["status"] = new_status
        if new_status == "delivered":
            update_set["delivered_at"] = tarih

    history_entry = {
        "code": islem_kodu, "text": islem_adi, "at": tarih,
        "barkod": barkod, "raw": payload,
    }

    await db.orders.update_one(
        {"id": order["id"]},
        {
            "$set": update_set,
            "$push": {"cargo_status_history": history_entry},
        },
    )

    # Log'a yaz
    await db.integration_logs.insert_one({
        "id": generate_id(),
        "service": "mng_kargo",
        "event": "webhook_update",
        "order_id": order["id"],
        "order_number": order.get("order_number"),
        "barkod": barkod,
        "code": islem_kodu,
        "text": islem_adi,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "success": True,
        "matched": True,
        "order_id": order["id"],
        "order_number": order.get("order_number"),
        "new_status": new_status,
    }


@router.get("/{order_id}/cargo-label")
async def get_cargo_label(order_id: str, token: str = None):
    """100x150mm yazdırılabilir kargo etiketi (HTML + Code39).
    Tek barkod: kargo takip no varsa onu, yoksa sipariş numarasını kullanır.
    Tasarım: LOGO + ORIGIN ID + FROM/TO/REF + ORDER/ITEM/SHIP DATE/DIMENSIONS/WEIGHT
    + REMARKS + tek barkod sağ altta + sağ kenarda handling icon'ları.
    """
    from fastapi.responses import HTMLResponse
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    barkod = order.get("cargo_tracking_number") or ""
    cargo_obj = order.get("cargo") or {}
    mng_siparis_no = cargo_obj.get("mng_siparis_no") or ""
    mng_gonderi_no = cargo_obj.get("mng_gonderi_no") or ""
    mng_nz_barkod = cargo_obj.get("mng_nz_barkod") or ""
    # Tek barkod: NZ > GONDERI_NO > MNG_SIPARIS_NO > tracking > sipariş_no
    real_kargo_takip = mng_nz_barkod or mng_gonderi_no or mng_siparis_no or barkod or ""
    siparis_no = str(order.get("order_number") or order_id)
    main_barcode = real_kargo_takip or siparis_no  # ✅ TEK barkod — etiketin merkezi
    sender = await _get_sender_info()
    mng = await _get_mng_settings()
    sender_company = mng.get("customer_code") or sender["name"] or "FACETTE"
    sender_addr_line = f"{sender['address']}, {sender['district']}/{sender['city']}".strip(" ,/")

    ship = order.get("shipping_address") or {}
    receiver_name = f"{ship.get('first_name','')} {ship.get('last_name','')}".strip() or ship.get("name") or "Alıcı"
    receiver_phone = ship.get("phone") or ""
    receiver_addr = (ship.get("address") or "").strip()
    receiver_district_city = f"{ship.get('district','')} / {ship.get('city','')}".strip(" /")
    receiver_full_addr = ", ".join([x for x in [receiver_addr, receiver_district_city] if x])

    items = order.get("items") or []
    total_qty = sum(int(it.get("quantity") or 1) for it in items)
    # İlk ürünün stock_code/sku/barcode/name'i ITEM NO; çoklu ürün varsa "+N more"
    first_item = items[0] if items else {}
    item_no = (first_item.get("stock_code") or first_item.get("sku")
               or first_item.get("barcode") or first_item.get("name") or "-")
    # Çok uzun ürün ismini kısalt
    item_no = (item_no[:32] + "…") if len(str(item_no)) > 33 else item_no
    if len(items) > 1:
        item_no = f"{item_no} (+{len(items)-1})"

    ship_date = order.get("ship_date") or order.get("created_at") or datetime.now(timezone.utc).isoformat()
    try:
        ship_date_str = datetime.fromisoformat(ship_date.replace("Z", "+00:00")).strftime("%d %b %Y").upper()
    except Exception:
        ship_date_str = datetime.now(timezone.utc).strftime("%d %b %Y").upper()

    # Dimensions / Weight — items'dan toplama
    total_weight = sum(float(it.get("weight") or 0) for it in items)
    if total_weight <= 0:
        total_weight = 0.5 * total_qty  # makul varsayılan
    dimensions = order.get("package_dimensions") or "30x20x15 cm"
    weight_str = f"{total_weight:.1f} KG"

    payment_method = (order.get("payment_method") or "").lower()
    remarks = order.get("cargo_remarks") or order.get("note") or ""
    if not remarks:
        remarks = "Alıcı Ödemeli" if payment_method in ("cash_on_delivery", "kapida") else "Gönderici Ödemeli"

    # Kargo bilgileri (paylaşılan referans şablonuna göre)
    cargo_company_display = "DHL E-Commerce"  # MNG ibaresi kaldırıldı
    payment_method = (order.get("payment_method") or "").lower()
    is_kapida = payment_method in ("cash_on_delivery", "kapida")
    odeme_turu = "Kapıda Ödemeli" if is_kapida else "Peşin Ödemeli"
    kargo_tipi = f"{odeme_turu} Kargo"

    # Telefon formatı: 5435955290 → 543 595 52 90
    def _fmt_phone(p: str) -> str:
        if not p:
            return ""
        digits = "".join(c for c in str(p) if c.isdigit())
        # Başında 90 ülke kodu varsa atla, 0 ile başlıyorsa atla
        if digits.startswith("90") and len(digits) == 12:
            digits = digits[2:]
        elif digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        if len(digits) == 10:
            return f"{digits[0:3]} {digits[3:6]} {digits[6:8]} {digits[8:10]}"
        return str(p)

    # Brand logo (PNG → base64) — paylaşılan FACETTE wordmark
    import base64, pathlib
    logo_b64 = ""
    try:
        logo_path = pathlib.Path(__file__).parent.parent / "static" / "brand" / "facette-logo.png"
        if logo_path.exists():
            logo_b64 = base64.b64encode(logo_path.read_bytes()).decode()
    except Exception:
        logo_b64 = ""
    logo_src = f"data:image/png;base64,{logo_b64}" if logo_b64 else ""

    # Sender (gönderici) için telefon
    sender_phone = _fmt_phone(sender.get("phone", "") or "")
    receiver_phone_fmt = _fmt_phone(receiver_phone)

    html = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="UTF-8"><title>Kargo Etiketi - {siparis_no}</title>
<link href="https://fonts.googleapis.com/css2?family=Mulish:wght@400;500;600;700;800;900&family=Libre+Barcode+39+Extended&display=swap" rel="stylesheet">
<style>
  @page {{ size: 100mm 120mm; margin: 0; }}
  * {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  body {{ margin: 0; font-family: 'Mulish','Helvetica Neue',Arial,sans-serif; width: 100mm; height: 120mm; color: #000; background:#fff; }}
  .label {{ width: 100mm; height: 120mm; padding: 2mm; }}
  .main {{ width: 100%; height: 100%; border: 1.8pt solid #000; border-radius: 1.5mm; padding: 2.5mm; display:flex; flex-direction:column; }}

  /* LOGO bandı */
  .logo-band {{ display:flex; align-items:center; justify-content:center; padding: 0.5mm 0 1.8mm 0; border-bottom: 1.4pt solid #000; }}
  .logo-band img {{ height: 7mm; width: auto; max-width: 78mm; }}
  .logo-fallback {{ font-family:'Mulish',sans-serif; font-weight: 900; font-size: 18pt; letter-spacing: 5pt; }}

  /* Bölüm başlığı (Gönderici / Alıcı / Kargo Bilgileri) */
  .section-title {{ text-align: center; font-family:'Mulish',sans-serif; font-weight: 800; font-size: 9pt; letter-spacing: 0.5pt; padding: 1.2mm 0; border-bottom: 1pt solid #000; background: #f0f0f0; }}

  /* Tablo satırları (label / value) */
  .info-table {{ border-bottom: 1pt solid #000; }}
  .info-row {{ display:flex; border-bottom: 0.6pt solid #000; min-height: 5mm; }}
  .info-row:last-child {{ border-bottom: 0; }}
  .info-row .lbl {{ width: 22mm; padding: 1mm 1.5mm; font-family:'Mulish',sans-serif; font-weight: 700; font-size: 7.8pt; border-right: 0.6pt solid #000; display:flex; align-items:center; }}
  .info-row .val {{ flex: 1; padding: 1mm 1.5mm; font-family:'Mulish',sans-serif; font-weight: 700; font-size: 8.4pt; display:flex; align-items:center; line-height: 1.25; word-break: break-word; }}
  .info-row .val.addr {{ font-weight: 600; font-size: 7.6pt; line-height: 1.3; }}

  /* Barkod */
  .barcode-band {{ margin-top: auto; padding-top: 1.5mm; text-align:center; }}
  /* Libre Barcode 39 Extended → Code 39 (alfanumerik desteklenir). 30pt → her char ~5mm,
     12 karakter ≈ 60mm < 88mm kullanılabilir alan. */
  .barcode {{ font-family: 'Libre Barcode 39 Extended', 'Libre Barcode 39', monospace; font-size: 30pt; letter-spacing: 0; line-height: 0.95; color:#000; white-space: nowrap; display: block; }}
  .barcode-num {{ font-size: 9pt; letter-spacing: 1.4pt; font-family: 'Courier New', monospace; font-weight: 800; margin-top: 0.3mm; }}
</style></head><body>
<div class="label">
  <div class="main">

    <!-- LOGO BANDI -->
    <div class="logo-band">
      {('<img src="'+logo_src+'" alt="FACETTE"/>') if logo_src else '<div class="logo-fallback">FACETTE</div>'}
    </div>

    <!-- GÖNDERİCİ BİLGİLERİ -->
    <div class="section-title">Gönderici Bilgileri</div>
    <div class="info-table">
      <div class="info-row"><span class="lbl">Firma</span><span class="val">{sender_company}</span></div>
      <div class="info-row"><span class="lbl">Telefon</span><span class="val">{sender_phone}</span></div>
      <div class="info-row"><span class="lbl">Adres</span><span class="val addr">{sender_addr_line}</span></div>
    </div>

    <!-- ALICI BİLGİLERİ -->
    <div class="section-title">Alıcı Bilgileri</div>
    <div class="info-table">
      <div class="info-row"><span class="lbl">İsim</span><span class="val">{receiver_name}</span></div>
      <div class="info-row"><span class="lbl">Telefon</span><span class="val">{receiver_phone_fmt}</span></div>
      <div class="info-row"><span class="lbl">Adres</span><span class="val addr">{receiver_full_addr}</span></div>
    </div>

    <!-- KARGO BİLGİLERİ -->
    <div class="section-title">Kargo Bilgileri</div>
    <div class="info-table">
      <div class="info-row"><span class="lbl">Kargo Firması</span><span class="val">{cargo_company_display}</span></div>
      <div class="info-row"><span class="lbl">Ödeme Türü</span><span class="val">{odeme_turu}</span></div>
      <div class="info-row"><span class="lbl">Kargo Tipi</span><span class="val">{kargo_tipi}</span></div>
    </div>

    <!-- BARKOD (alt) -->
    <div class="barcode-band">
      <div class="barcode">*{main_barcode}*</div>
      <div class="barcode-num">{siparis_no}</div>
    </div>

  </div>
</div>
<script>
  // Barkodu çerçeveye sığdır — fontlar yüklendikten SONRA çalış
  async function fitBarcode() {{
    if (document.fonts && document.fonts.ready) {{
      try {{ await document.fonts.ready; }} catch(e) {{}}
    }}
    // Ekstra güvenlik: fontların gerçekten render olması için bir frame bekle
    await new Promise(r => requestAnimationFrame(() => r()));
    const el = document.querySelector('.barcode');
    if (!el) return;
    // Container genişliği — .main padding'i çıkarılarak hesaplanır
    const main = document.querySelector('.main');
    const maxW = (main ? main.clientWidth : 340) - 12;
    // 36pt'tan başla, sığana kadar küçült (min 18pt)
    let size = 36;
    el.style.fontSize = size + 'pt';
    let safety = 24;
    while (el.scrollWidth > maxW && size > 18 && safety-- > 0) {{
      size -= 1;
      el.style.fontSize = size + 'pt';
    }}
  }}
  window.addEventListener('load', () => {{
    fitBarcode().then(() => {{
      if (window.location.search.includes('print=1')) {{
        setTimeout(() => window.print(), 200);
      }}
    }});
  }});
</script>
</body></html>"""
    return HTMLResponse(content=html, headers={"Content-Type": "text/html; charset=utf-8"})


# ==================== MNG KARGO AYARLARI ====================
# Bu ayarları integrations.py altındaki generic /{marketplace}/settings de yönetebilir,
# ancak özelleştirilmiş alanlar için ayrı endpoint sağlıyoruz.

@router.get("/cargo/mng-settings")
async def get_mng_settings(current_user: dict = Depends(require_admin)):
    """MNG Kargo ayarlarını döndür (şifre maskelenir)."""
    s = await db.settings.find_one({"id": "mng_kargo"}, {"_id": 0}) or {}
    return {
        "customer_code": s.get("customer_code") or "FACETTE DIS TIC.A.S.",
        "username": s.get("username") or "490059279",
        "password": "********" if s.get("password") else "",
        "tax_no": s.get("tax_no") or "6080712084",
        "is_active": s.get("is_active", True),
        "barkod_cikti_turu": s.get("barkod_cikti_turu") or "Standart",
        "musteri_kodu_goster": s.get("musteri_kodu_goster", False),
    }


@router.post("/cargo/mng-settings")
async def save_mng_settings(payload: dict, current_user: dict = Depends(require_admin)):
    """MNG Kargo ayarlarını kaydet."""
    update = {
        "customer_code": payload.get("customer_code", "FACETTE DIŞ TİC.A.Ş."),
        "username": payload.get("username", ""),
        "tax_no": payload.get("tax_no", ""),
        "is_active": bool(payload.get("is_active", True)),
        "barkod_cikti_turu": payload.get("barkod_cikti_turu", "Standart"),
        "musteri_kodu_goster": bool(payload.get("musteri_kodu_goster", False)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if payload.get("password") and payload.get("password") != "********":
        update["password"] = payload.get("password")
    await db.settings.update_one({"id": "mng_kargo"}, {"$set": update}, upsert=True)
    return {"success": True, "message": "MNG Kargo ayarları kaydedildi"}


@router.post("/cargo/mng-test")
async def test_mng_connection(current_user: dict = Depends(require_admin)):
    """MNG Kargo bağlantı testi (Baglanti_Test)."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from mng_kargo_client import baglanti_test
    return baglanti_test()
