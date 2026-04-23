"""
Order routes - CRUD, checkout, tracking
"""
from fastapi import APIRouter, HTTPException, Query, Depends, Response
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
    current_user: dict = Depends(get_current_user)
):
    """Create new order"""
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
    valid_statuses = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"]
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
    if not active or not providers.get(active):
        raise HTTPException(
            status_code=400,
            detail="Aktif e-fatura entegratörü yapılandırılmamış. Ayarlar > E-Arşiv / E-Fatura ekranından seçin."
        )

    pcfg = providers[active]
    prefix = (pcfg.get("earchive_prefix") if invoice_type == "e-arsiv"
              else pcfg.get("einvoice_prefix")) or "FAC"

    # Aynı prefix ile kesilmiş fatura sayısına göre sıra numarası üret
    count = await db.orders.count_documents({
        "invoice_number": {"$regex": f"^{prefix}"}
    })
    invoice_number = f"{prefix}{(count + 1):08d}"

    now = datetime.now(timezone.utc).isoformat()
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "invoice_issued": True,
            "invoice_number": invoice_number,
            "invoice_type": invoice_type,
            "invoice_provider": active,
            "invoice_issued_at": now,
            "invoice_issued_by": current_user.get("email", ""),
            "updated_at": now,
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
            message=f"{invoice_type} fatura oluşturuldu: {invoice_number}",
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
