from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
from typing import Dict, Any
from routes.deps import logger, db
import traceback

router = APIRouter(tags=["Webhooks"])

@router.post("/webhooks/trendyol")
async def trendyol_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Trendyol Event Notification Webhook
    Gelen bildirimleri asenkron olarak işler.
    """
    try:
        payload = await request.json()
    except:
        payload = {}

    if not payload:
        return {"status": "ok"}
        
    logger.info(f"Received Trendyol Webhook: {payload.get('eventType')} - {payload.get('orderNumber')}")

    # Process in background
    background_tasks.add_task(process_trendyol_event, payload)
    
    return {"status": "ok", "message": "Event received"}

async def process_trendyol_event(payload: dict):
    """Background task to process the event"""
    try:
        event_type = payload.get("eventType")
        
        if event_type in ["OrderCancelled", "ClaimApproved"]:
            await handle_stock_restoration(payload)
            
        elif event_type == "OrderStatusChanged":
            await handle_order_status_change(payload)
            
    except Exception as e:
        logger.error(f"Error processing Trendyol webhook: {str(e)}\n{traceback.format_exc()}")


async def handle_stock_restoration(payload: dict):
    """
    Sipariş iptal edildiğinde veya iade onaylandığında ilgili stokları geri yükle.
    Trendyol 'ClaimApproved' ve 'OrderCancelled' eventlarında orderLineItem listesi atar.
    """
    lines = payload.get("orderLines", [])
    if not lines:
        return
        
    for line in lines:
        barcode = line.get("barcode", "")
        qty = int(line.get("quantity", 0))
        
        if barcode and qty > 0:
            # Find the product/variant with this barcode
            product = await db.products.find_one({"variants.barcode": barcode})
            if product:
                # Update variant stock
                await db.products.update_one(
                    {"_id": product["_id"], "variants.barcode": barcode},
                    {"$inc": {"variants.$.stock": qty}}
                )
                logger.info(f"Trendyol Webhook: Restored {qty} stock for barcode {barcode}")


async def handle_order_status_change(payload: dict):
    """
    Trendyol'da sipariş kargoya verildi veya teslim edildi statüsüne geçtiyse 
    bizim paneldeki 'status' alanını da güncelleyebiliriz.
    """
    order_number = payload.get("orderNumber")
    new_status = payload.get("status")
    
    if order_number and new_status:
        # Trendyol status mapping
        status_map = {
            "Shipped": "shipped",
            "Delivered": "delivered",
            "Cancelled": "cancelled",
            "UnDelivered": "returned"
        }
        mapped_status = status_map.get(new_status)
        if mapped_status:
            await db.orders.update_one(
                {"order_number": str(order_number), "platform": "trendyol"},
                {"$set": {"status": mapped_status}}
            )
            logger.info(f"Trendyol Webhook: Order {order_number} status updated to {mapped_status}")
