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

router = APIRouter(prefix="/orders", tags=["Orders"])

def generate_order_number() -> str:
    return f"FC{int(time.time())}"

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
        "order_number": generate_order_number(),
        "user_id": current_user.get("id") if current_user else None,
        "items": order_data.get("items", []),
        "shipping_address": order_data.get("shipping_address", {}),
        "billing_address": order_data.get("billing_address") or order_data.get("shipping_address", {}),
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

    await db.orders.insert_one(order)
    logger.info(f"Order created: {order['order_number']}")

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
    invoice_type: str = "e-arsiv",
    current_user: dict = Depends(require_admin),
):
    """
    Seçili sipariş için e-Arşiv / e-Fatura keser.

    AKIŞ:
      1) Siparişi ve aktif e-fatura provider config'ini çek.
      2) Provider config'i yoksa hata dön (kullanıcı Ayarlar > E-Fatura
         ekranında provider seçmeli).
      3) Mock: prefix + sayaç ile invoice_number üret, siparişe yaz.
      4) integration_logs'a "invoice_create" olayı yaz.
    """
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    if order.get("invoice_issued"):
        return {"success": True, "message": "Fatura zaten kesilmiş",
                "invoice_number": order.get("invoice_number", "")}

    # Mikro ihracat siparişleri ayrı ETGB beyannamesi ile faturalanır;
    # normal e-arşiv/e-fatura yerine ETGB-placeholder bir belge numarası oluştur.
    if order.get("is_micro_export"):
        count = await db.orders.count_documents({"invoice_type": "etgb"})
        invoice_number = f"ETGB{(count + 1):08d}"
        now = datetime.now(timezone.utc).isoformat()
        await db.orders.update_one(
            {"id": order_id},
            {"$set": {
                "invoice_issued": True,
                "invoice_number": invoice_number,
                "invoice_type": "etgb",
                "invoice_provider": "etgb-micro-export",
                "invoice_issued_at": now,
                "invoice_issued_by": current_user.get("email", ""),
                "updated_at": now,
            }}
        )
        try:
            from .marketplace_hub import log_integration_event
            await log_integration_event(
                marketplace="einvoice:etgb",
                action="invoice_create",
                status="success",
                direction="outbound",
                ref_id=order_id,
                message=f"Mikro İhracat ETGB beyannamesi oluşturuldu: {invoice_number}",
            )
        except Exception:
            pass
        return {
            "success": True,
            "message": "Mikro ihracat ETGB beyannamesi oluşturuldu",
            "invoice_number": invoice_number,
            "invoice_type": "etgb",
            "provider": "etgb-micro-export",
        }

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

    # Prefix
    if dogan_active:
        active = "dogan"
        prefix = (dogan_settings.get("earchive_prefix") if invoice_type == "e-arsiv"
                  else dogan_settings.get("einvoice_prefix")) or "FAC"
    else:
        pcfg = providers[active]
        prefix = (pcfg.get("earchive_prefix") if invoice_type == "e-arsiv"
                  else pcfg.get("einvoice_prefix")) or "FAC"

    # Aynı prefix ile kesilmiş fatura sayısına göre sıra numarası üret (yıllık)
    year_str = datetime.now(timezone.utc).strftime("%Y")
    count = await db.orders.count_documents({
        "invoice_number": {"$regex": f"^{prefix}{year_str}"}
    })
    invoice_number = f"{prefix}{year_str}{(count + 1):09d}"
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
        bill = order.get("billing_address") or {}
        ship_addr = order.get("shipping_address") or {}
        customer_vkn = (bill.get("tax_no") or "").strip().replace(" ", "")
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
                "kdv_rate": 20.0,
            })

        ubl_xml = DoganClient.build_earsiv_ubl_xml(
            invoice_uuid=invoice_uuid,
            invoice_number=invoice_number,
            issue_date=issue_date,
            issue_time=issue_time,
            supplier_vkn=dogan_settings.get("vkn") or "7810816779",
            supplier_name=dogan_settings.get("supplier_name") or "FACETTE DIŞ TİC.A.Ş.",
            supplier_district=dogan_settings.get("supplier_district") or "Küçükçekmece",
            supplier_city=dogan_settings.get("supplier_city") or "İstanbul",
            supplier_street=dogan_settings.get("supplier_street") or "İkitelli OSB Mah.",
            supplier_tax_office=dogan_settings.get("supplier_tax_office") or "Küçükçekmece",
            supplier_phone=dogan_settings.get("supplier_phone") or "",
            supplier_email=dogan_settings.get("supplier_email") or "",
            customer_vkn_or_tckn=customer_vkn,
            customer_name=customer_name,
            customer_district=ship_addr.get("district") or "",
            customer_city=ship_addr.get("city") or "",
            customer_street=ship_addr.get("address") or "",
            customer_phone=ship_addr.get("phone") or "",
            customer_email=ship_addr.get("email") or order.get("user_email") or "",
            currency="TRY",
            kdv_rate=20.0,
            line_items=line_items,
            shipping_cost=float(order.get("shipping_cost") or 0),
            discount=float(order.get("discount") or 0),
            note=f"Sipariş No: {order.get('order_number') or order_id}",
        )

        dogan_client = DoganClient(
            username=dogan_settings["username"],
            password=dogan_settings["password"],
            is_test=dogan_settings.get("is_test", True),
        )
        dogan_result = await run_in_threadpool(dogan_client.send_earsiv_invoice, ubl_xml)

        if not dogan_result.get("success"):
            # Hatayı log'a yaz, mock fallback ile devam etme — gerçek hata bildir
            raise HTTPException(
                status_code=502,
                detail=f"Doğan e-Arşiv hatası: {dogan_result.get('message')}"
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
    public_tracking = gonderi_no_status or barkod
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
            "mng_gonderi_no": gonderi_no_status,           # NZ formatlı (sadece kurumsal havuzlu hesaplar)
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


@router.get("/{order_id}/cargo-label")
async def get_cargo_label(order_id: str, token: str = None):
    """100x150mm yazdırılabilir MNG-stili kargo etiketi (HTML + Code39).
    Üstteki barkod = sipariş numarası | Alttaki barkod = MNG kargo takip no.
    Authorization header yerine ?token=... query parametresi de kabul eder (yeni sekme yazdırma).
    """
    from fastapi.responses import HTMLResponse
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    barkod = order.get("cargo_tracking_number") or ""
    cargo_obj = order.get("cargo") or {}
    mng_siparis_no = cargo_obj.get("mng_siparis_no") or ""
    mng_gonderi_no = cargo_obj.get("mng_gonderi_no") or ""
    # Etikette gösterilecek "asıl" kargo takip — GONDERI_NO varsa o, yoksa MNG_SIPARIS_NO, yoksa current barkod
    real_kargo_takip = mng_gonderi_no or mng_siparis_no or barkod or ""
    siparis_no = str(order.get("order_number") or order_id)
    sender = await _get_sender_info()
    mng = await _get_mng_settings()
    sender_company = mng.get("customer_code") or sender["name"] or "FACETTE"

    ship = order.get("shipping_address") or {}
    receiver_name = f"{ship.get('first_name','')} {ship.get('last_name','')}".strip() or ship.get("name") or "Alıcı"
    receiver_phone = ship.get("phone") or ""
    receiver_addr = f"{ship.get('address','')}".strip()
    receiver_district_city = f"{ship.get('district','')} / {ship.get('city','')}".strip(" /")

    items = order.get("items") or []
    paket_sayisi = "1/1"
    total_adet = sum(int(it.get("quantity") or 1) for it in items)
    desi = "1"

    payment_method = (order.get("payment_method") or "").lower()
    odeme_tipi = "Alıcı Ödemeli" if payment_method in ("cash_on_delivery","kapida") else "Gönderici Ödemeli"
    kargo_tipi = "Alıcı Ödemeli Kargo" if payment_method in ("cash_on_delivery","kapida") else "Gönderici Ödemeli Kargo"

    html = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"><title>Kargo Etiketi - {siparis_no}</title>
<link href="https://fonts.googleapis.com/css2?family=Libre+Barcode+39&family=Libre+Barcode+39+Text&display=swap" rel="stylesheet">
<style>
  @page {{ size: 100mm 150mm; margin: 0; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; width: 100mm; min-height: 150mm; color: #000; }}
  .label {{ padding: 3mm; height: 100%; }}
  .row {{ display: flex; justify-content: space-between; align-items: center; }}
  .small {{ font-size: 7pt; color: #333; }}
  .barcode {{ font-family: 'Libre Barcode 39', monospace; font-size: 38pt; letter-spacing: 0; line-height: 0.9; text-align: center; }}
  .barcode-num {{ text-align:center; font-size: 10pt; letter-spacing: 1.5px; margin-top: -1mm; font-family: 'Courier New', monospace; }}
  .section {{ border-top: 1px solid #000; padding-top: 2mm; margin-top: 2mm; font-size: 9pt; }}
  .section h4 {{ margin: 0 0 1mm 0; font-size: 7pt; color:#444; text-transform: uppercase; letter-spacing: 0.6px; }}
  .strong {{ font-weight: 700; font-size: 10pt; }}
  .top-bar {{ display:flex; justify-content:space-between; align-items:center; padding-bottom:1mm; }}
  .brand {{ font-weight: 800; font-size: 12pt; }}
  .meta {{ display:flex; gap:6mm; font-size: 8pt; }}
  .meta b {{ font-size: 9pt; }}
</style></head><body>
<div class="label">
  <div class="top-bar">
    <div class="brand">MNG <span style="color:#e60012">DHL</span> E-Commerce</div>
    <div class="small">{datetime.now(timezone.utc).strftime('%d.%m.%Y')}</div>
  </div>

  <!-- ÜST: SİPARİŞ NUMARASI BARKODU -->
  <div class="barcode">*{siparis_no}*</div>
  <div class="barcode-num">{siparis_no}</div>

  <div class="section">
    <h4>Gönderici Bilgileri</h4>
    <div class="strong">{sender_company}</div>
    <div class="small">Telefon: {sender['phone']}</div>
    <div class="small">Adres: {sender['address']} {sender['district']}/{sender['city']}</div>
  </div>

  <div class="section">
    <h4>Alıcı Bilgileri</h4>
    <div class="strong">{receiver_name}</div>
    <div class="small">Telefon: {receiver_phone}</div>
    <div class="small">Adres: {receiver_addr}</div>
    <div class="small">{receiver_district_city}</div>
  </div>

  <div class="section">
    <h4>Kargo Bilgileri</h4>
    <div class="meta">
      <div>Ödeme Türü: <b>{odeme_tipi}</b></div>
      <div>Paket Sayısı: <b>{paket_sayisi}</b></div>
      <div>Desi: <b>{desi}</b></div>
    </div>
    <div class="small" style="margin-top:1mm;">Kargo Tipi: {kargo_tipi}</div>
    <div class="small">Sipariş No: {siparis_no}</div>
  </div>

  <!-- ALT: KARGO TAKİP NO BARKODU (varsa GONDERI_NO, yoksa MNG_SIPARIS_NO) -->
  <div style="margin-top: 3mm;">
    <div class="barcode">*{real_kargo_takip or siparis_no}*</div>
    <div class="barcode-num">Takip No: {real_kargo_takip or '— şube işleminden sonra atanacak —'}</div>
    {('<div class="small" style="text-align:center;margin-top:1mm;">Ref: ' + mng_siparis_no + '</div>') if (mng_siparis_no and mng_siparis_no != real_kargo_takip) else ''}
  </div>
</div>
</body></html>"""
    return HTMLResponse(content=html)


# ==================== MNG KARGO AYARLARI ====================
# Bu ayarları integrations.py altındaki generic /{marketplace}/settings de yönetebilir,
# ancak özelleştirilmiş alanlar için ayrı endpoint sağlıyoruz.

@router.get("/cargo/mng-settings")
async def get_mng_settings(current_user: dict = Depends(require_admin)):
    """MNG Kargo ayarlarını döndür (şifre maskelenir)."""
    s = await db.settings.find_one({"id": "mng_kargo"}, {"_id": 0}) or {}
    return {
        "customer_code": s.get("customer_code") or "FACETTE DIŞ TİC.A.Ş.",
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
