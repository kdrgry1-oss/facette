"""
Application-level background scheduler (APScheduler).
Runs auto-cancellation of unpaid orders, etc.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def auto_cancel_unpaid_havale_orders():
    """Cancel havale/transfer orders that remain unpaid after 48 hours and restock."""
    from routes.deps import db  # lazy import
    from routes.orders import _stock_delta_for_order

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        # Accept both payment_method names
        query = {
            "payment_status": "pending",
            "status": {"$in": ["pending", "confirmed"]},
            "payment_method": {"$in": ["transfer", "havale", "bank_transfer", "eft"]},
            "created_at": {"$lt": cutoff},
        }
        cancelled = 0
        async for order in db.orders.find(query, {"_id": 0}):
            try:
                moves = await _stock_delta_for_order(order, +1)
                await db.orders.update_one(
                    {"id": order["id"]},
                    {"$set": {
                        "status": "cancelled",
                        "payment_status": "expired",
                        "cancel_reason": "48 saat içinde havale ödemesi yapılmadı (otomatik iptal)",
                        "auto_cancelled": True,
                        "cancelled_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }}
                )
                await db.stock_movements.insert_one({
                    "id": str(uuid.uuid4()),
                    "type": "auto_cancel_havale_48h",
                    "order_id": order["id"],
                    "order_number": order.get("order_number", ""),
                    "items": moves,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                cancelled += 1
            except Exception as e_item:
                logger.error(f"Failed to cancel order {order.get('order_number')}: {e_item}")
        if cancelled:
            logger.info(f"[scheduler] Auto-cancelled {cancelled} unpaid havale orders (>48h)")
    except Exception as e:
        logger.exception(f"[scheduler] auto_cancel_unpaid_havale_orders failed: {e}")


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    # Run every 30 minutes; catches orders promptly as they cross the 48h mark
    _scheduler.add_job(
        auto_cancel_unpaid_havale_orders,
        "interval",
        minutes=30,
        id="auto_cancel_havale_48h",
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30),
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("[scheduler] Background scheduler started (auto-cancel every 30 min)")
    return _scheduler


def shutdown_scheduler():
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None
