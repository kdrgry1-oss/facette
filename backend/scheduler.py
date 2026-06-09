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


async def _run_trendyol_auto_products_sync():
    """Scheduler tarafından Trendyol fiyat/stok senkronunu tetikler.
    HTTPException'ı yutar, log bırakır. Trendyol konfigürasyonu yoksa sessizce atlar.
    """
    from routes.deps import db
    from routes.marketplace_hub import log_integration_event
    try:
        from routes.integrations import _sync_inventory_to_trendyol, get_trendyol_config
        cfg = await get_trendyol_config()
        if not cfg.get("is_active"):
            return
        products = await db.products.find({"is_active": True}, {"_id": 0}).to_list(length=None)
        res = await _sync_inventory_to_trendyol(products)
        await log_integration_event(
            marketplace="trendyol", action="stock_update",
            status=("success" if res.get("success") else "failed"),
            direction="outbound",
            message=f"[cron] Trendyol stok/fiyat senkronu: {res.get('message', '')}"
        )
    except Exception as e:
        try:
            await log_integration_event(
                marketplace="trendyol", action="stock_update", status="failed",
                direction="outbound",
                message=f"[cron] Trendyol ürün senkron hatası: {e}"
            )
        except Exception:
            pass


async def _run_trendyol_auto_orders_pull():
    """Scheduler tarafından Trendyol sipariş çekmeyi tetikler."""
    from routes.marketplace_hub import log_integration_event
    try:
        from routes.integrations import get_trendyol_config
        cfg = await get_trendyol_config()
        if not cfg.get("is_active"):
            return
        # Doğrudan route fonksiyonunu çağırmıyoruz (require_admin için);
        # onun yerine mantığı burada çoğaltmadan, küçük bir internal job tetikliyoruz.
        import sys, os
        from datetime import datetime as _dt, timedelta as _td
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from trendyol_client import TrendyolClient
        from routes.deps import db as _db, generate_id
        from routes.integrations import map_trendyol_order, _sync_trendyol_status_passes

        client = TrendyolClient(
            supplier_id=cfg["supplier_id"],
            api_key=cfg["api_key"],
            api_secret=cfg["api_secret"],
            mode=cfg["mode"],
        )
        now_ = _dt.now()
        start = now_ - _td(days=14)
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(now_.timestamp() * 1000)
        # Trendyol tek sayfada en fazla 200 paket dondurur; TUM sayfalari dolas.
        # (Sayfalama yokken 200'den fazla siparis olunca 201+ hep atlaniyordu.)
        content = []
        _page = 0
        _MAX_PAGES = 50
        while _page < _MAX_PAGES:
            _resp = await client.get_orders(
                start_date_ms=start_ms, end_date_ms=end_ms, size=200, page=_page
            )
            _chunk = _resp.get("content", []) or []
            content.extend(_chunk)
            _total_pages = _resp.get("totalPages") or 0
            _page += 1
            if not _chunk or _page >= _total_pages:
                break
        imported = 0
        updated = 0
        for t_order in content:
            try:
                number = str(t_order.get("orderNumber"))
                existing = await _db.orders.find_one({"order_number": number, "platform": "trendyol"})
                data = map_trendyol_order(t_order)
                if existing:
                    await _db.orders.update_one({"_id": existing["_id"]}, {"$set": data})
                    updated += 1
                else:
                    data["id"] = generate_id()
                    data["created_at"] = datetime.now(timezone.utc).isoformat()
                    await _db.orders.insert_one(data)
                    imported += 1
            except Exception as _ex:
                logger.error(f"[cron] Trendyol order import hata: {_ex}")
        try:
            await _sync_trendyol_status_passes(client, start_ms, end_ms)
        except Exception as _ex2:
            logger.error(f"[cron] Trendyol status pass hata: {_ex2}")
        await log_integration_event(
            marketplace="trendyol", action="order_pull", status="success",
            direction="inbound",
            message=f"[cron] Trendyol sipariş çekildi: +{imported} yeni / {updated} güncellendi"
        )
    except Exception as e:
        try:
            await log_integration_event(
                marketplace="trendyol", action="order_pull", status="failed",
                direction="inbound",
                message=f"[cron] Trendyol sipariş çekme hatası: {e}"
            )
        except Exception:
            pass


async def _marketplace_sync_tick():
    """
    Her dk'da bir çalışır; her marketplace_account'un auto_sync ayarlarına
    bakar, periyoda gelmişse ürün push ve sipariş pull tetikler.

    TASARIM:
      - `auto_sync.products_interval_min` dk geçtiyse → ürün push tetikle
      - `auto_sync.orders_interval_min` dk geçtiyse → sipariş pull tetikle
      - `marketplace_accounts.{_last_products_sync, _last_orders_sync}` alanlarına
        son çalışma zamanı yazılır (next check için kıyas).
      - Gerçek çağrı internal HTTP olarak yapılmaz; direkt servis fonksiyonu
        çağrılır. Şu an her pazaryeri için ortak "dummy push" ile log düşer;
        mevcut integrations.py servisleri ileride buraya bağlanacak.
      - Tüm deneme sonuçları integration_logs'a düşer (ayrı bir marker ile).
    """
    from routes.deps import db
    from routes.marketplace_hub import log_integration_event

    now = datetime.now(timezone.utc)
    try:
        async for acc in db.marketplace_accounts.find({"enabled": True}, {"_id": 0}):
            key = acc.get("key")
            sync = acc.get("auto_sync") or {}

            # --- Ürünler ---------------------------------------------------
            if sync.get("products_enabled"):
                last = acc.get("_last_products_sync")
                try:
                    last_dt = datetime.fromisoformat(last) if last else None
                except Exception:
                    last_dt = None
                interval = max(1, int(sync.get("products_interval_min") or 3))
                due = (not last_dt) or (now - last_dt) >= timedelta(minutes=interval)
                if due:
                    await log_integration_event(
                        marketplace=key, action="product_push", status="queued",
                        direction="outbound",
                        message=f"[cron] Otomatik ürün senkron tetiklendi (her {interval} dk)"
                    )
                    # Trendyol için gerçek push'u arka planda kuyruğa al
                    if key == "trendyol":
                        asyncio.create_task(_run_trendyol_auto_products_sync())
                    await db.marketplace_accounts.update_one(
                        {"key": key}, {"$set": {"_last_products_sync": now.isoformat()}}
                    )

            # --- Siparişler ------------------------------------------------
            if sync.get("orders_enabled"):
                last = acc.get("_last_orders_sync")
                try:
                    last_dt = datetime.fromisoformat(last) if last else None
                except Exception:
                    last_dt = None
                interval = max(1, int(sync.get("orders_interval_min") or 5))
                due = (not last_dt) or (now - last_dt) >= timedelta(minutes=interval)
                if due:
                    lookback = int(sync.get("orders_lookback_hours") or 100)
                    await log_integration_event(
                        marketplace=key, action="order_pull", status="queued",
                        direction="inbound",
                        message=f"[cron] Otomatik sipariş çek tetiklendi (her {interval} dk, son {lookback} saat)"
                    )
                    if key == "trendyol":
                        asyncio.create_task(_run_trendyol_auto_orders_pull())
                    await db.marketplace_accounts.update_one(
                        {"key": key}, {"$set": {"_last_orders_sync": now.isoformat()}}
                    )
    except Exception as e:
        logger.exception(f"[scheduler] marketplace sync tick failed: {e}")


async def _send_abandoned_cart_reminders():
    """Her gün 10:00 UTC'de, son 2-48 saat içinde aktif olup sipariş vermemiş
    e-posta sahibi sepetlere 1 kez hatırlatma maili gönderir. İşaretlenmiş
    sepetlere tekrar gönderilmez.
    """
    from routes.deps import db
    try:
        from routes.catalog_extras import _send_email_via_resend  # lazy
    except Exception as e:
        logger.warning(f"[scheduler] abandoned cart mail skip (import): {e}")
        return
    import os
    if not os.environ.get("RESEND_API_KEY", "").strip():
        return  # no key → skip silently
    now = datetime.now(timezone.utc)
    # 2 saatten eski, 48 saatten yeni aktif sepetler
    start = (now - timedelta(hours=48)).isoformat()
    end = (now - timedelta(hours=2)).isoformat()
    q = {
        "updated_at": {"$gte": start, "$lte": end},
        "total": {"$gt": 0},
        "email": {"$ne": ""},
        "abandoned_reminder_sent": {"$ne": True},
    }
    try:
        carts = await db.cart_sessions.find(q, {"_id": 0}).to_list(500)
        if not carts:
            return
        recipients = list({c.get("email") for c in carts if c.get("email")})
        if not recipients:
            return
        subject = "Sepetinizi unutmayın ✨ Favori ürünleriniz sizi bekliyor"
        html = (
            "<h2>Sepetinizdeki ürünler tükeniyor!</h2>"
            "<p>Seçtiğiniz ürünleri tamamlamak için hazır bir alışveriş sepetiniz var.</p>"
            "<p><a href=\"https://facette.com\" style=\"background:#000;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none\">Sepete Dön</a></p>"
            "<p style=\"font-size:12px;color:#888;margin-top:24px\">Bu e-posta otomatik gönderilmiştir.</p>"
        )
        ok, failed, errs = await _send_email_via_resend(recipients, subject, html)
        # işaretle
        for c in carts:
            await db.cart_sessions.update_one(
                {"session_id": c.get("session_id")},
                {"$set": {"abandoned_reminder_sent": True, "abandoned_reminder_at": now.isoformat()}},
            )
        logger.info(f"[scheduler] Abandoned cart reminders: sent={ok} failed={failed} errs={errs[:1]}")
    except Exception as e:
        logger.exception(f"[scheduler] abandoned cart reminders failed: {e}")




async def _ticimax_sync_stock():
    """Ticimax SelectUrun ile canlı stok senkronu — 2 saatte bir tetiklenir.
    routes/ticimax_stock_sync içindeki gerçek implementasyonu çağırır.
    """
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(__file__))
        from routes.ticimax_stock_sync import sync_ticimax_stock  # type: ignore
        result = await sync_ticimax_stock(
            max_products=2000, aktif=None, page_size=50,
            current_user={"role": "admin", "id": "scheduler"},
        )
        logger.info(f"[scheduler][ticimax_stock] {result.get('message','done')}")
    except Exception as e:
        logger.exception(f"[scheduler] ticimax_stock_sync failed: {e}")


async def _ticimax_sync_orders():
    """Periyodik olarak Ticimax'tan site siparişlerini çek (idempotent).
    Son 30 günün siparişleri, 5 sayfa × 100. Yeni site siparişlerini DB'ye yazar.
    """
    try:
        import sys, os, uuid
        sys.path.insert(0, os.path.dirname(__file__))
        from ticimax_client import get_orders as tc_get_orders
        from routes.deps import db  # lazy import
        from routes.marketplace_hub import log_integration_event  # lazy import
        s = await db.settings.find_one({"id": "ticimax"}) or {}
        api_key = s.get("api_key") or "SSIQWRIYHQWROZGJAEIC2CRRZ5RV5V"
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=30)
        start_str = start_dt.strftime("%d.%m.%Y")
        end_str = end_dt.strftime("%d.%m.%Y")
        new_count = 0
        skipped_mp = 0
        seen_pages = 0

        # Ortak parser (KargoAdresi/FaturaAdresi nested + UrunListesi item)
        from ticimax_order_parser import parse_ticimax_order, is_marketplace_order

        updated_count = 0
        for page in range(1, 6):
            try:
                orders = tc_get_orders(
                    page=page, page_size=100, wscode=api_key,
                    start_date=start_str, end_date=end_str,
                    exclude_marketplace=False, only_with_phone=False,
                )
            except Exception as e:
                logger.warning(f"[cron][ticimax] page {page} error: {e}")
                break
            if not orders:
                break
            seen_pages += 1
            for o in orders:
                if not o:
                    continue
                if is_marketplace_order(o):
                    skipped_mp += 1
                    continue
                doc = parse_ticimax_order(o, api_key=api_key)
                if not doc:
                    continue
                tc_id = doc["ticimax_order_id"]
                tc_no = doc["order_number"]
                # Idempotent: varsa update, yoksa insert
                exist = await db.orders.find_one(
                    {"$or": [{"order_number": tc_no}, {"ticimax_order_id": tc_id}]},
                    {"_id": 0, "id": 1}
                )
                try:
                    if exist:
                        # Sadece güncelleme (created_at korunur, id korunur, user_id korunur)
                        await db.orders.update_one(
                            {"id": exist["id"]},
                            {"$set": {**{k: v for k, v in doc.items() if k != "created_at"},
                                      "updated_at": datetime.now(timezone.utc).isoformat()}}
                        )
                        updated_count += 1
                    else:
                        doc["id"] = str(uuid.uuid4())[:8]
                        doc["user_id"] = None
                        doc["imported_from"] = "ticimax_cron"
                        doc["imported_at"] = datetime.now(timezone.utc).isoformat()
                        await db.orders.insert_one(doc)
                        new_count += 1
                except Exception as ie:
                    logger.warning(f"[cron][ticimax] upsert err: {ie}")
        if new_count > 0 or updated_count > 0:
            logger.info(f"[cron][ticimax] +{new_count} yeni / ~{updated_count} güncellendi (skipped MP={skipped_mp}, pages={seen_pages})")
            await log_integration_event(
                marketplace="ticimax", action="order_pull", status="success",
                direction="inbound",
                message=f"[cron] {new_count} yeni + {updated_count} güncellendi"
            )
    except Exception as e:
        logger.exception(f"[cron][ticimax] sync fatal: {e}")



DEFAULT_PII_RETENTION_DAYS = 30
PII_RETENTION_PLATFORMS = ["amazon"]  # varsayılan kapsam: Amazon SP-API kaynaklı siparişler


async def _pii_retention_purge():
    """Amazon DPP uyumu — PII saklama süresi (varsayılan 30 gün) dolan siparişlerde
    kişisel verileri (isim, telefon, e-posta, adres) anonimleştirir.
    Muhasebe için sipariş no/tutar/ürün korunur; sadece kişisel tanımlayıcılar silinir.
    Config: db.settings id='pii_retention' { enabled, days, platforms }.
    """
    from routes.deps import db
    try:
        cfg = await db.settings.find_one({"id": "pii_retention"}) or {}
        if cfg.get("enabled") is False:
            return
        days = int(cfg.get("days") or DEFAULT_PII_RETENTION_DAYS)
        platforms = cfg.get("platforms") or PII_RETENTION_PLATFORMS
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        query = {
            "platform": {"$in": platforms},
            "status": {"$in": ["shipped", "delivered", "completed"]},
            "pii_redacted": {"$ne": True},
            "$or": [
                {"shipped_at": {"$lt": cutoff}},
                {"delivered_at": {"$lt": cutoff}},
                {"updated_at": {"$lt": cutoff}},
            ],
        }
        redacted = 0
        async for order in db.orders.find(query, {"_id": 0, "id": 1}):
            await db.orders.update_one(
                {"id": order["id"]},
                {"$set": {
                    "shipping_address.first_name": "[silindi]",
                    "shipping_address.last_name": "",
                    "shipping_address.full_name": "[silindi]",
                    "shipping_address.phone": "[silindi]",
                    "shipping_address.email": "[silindi]",
                    "shipping_address.address": "[silindi]",
                    "shipping_address.address_line": "[silindi]",
                    "billing_address.first_name": "[silindi]",
                    "billing_address.phone": "[silindi]",
                    "billing_address.email": "[silindi]",
                    "billing_address.address": "[silindi]",
                    "customer_email": "[silindi]",
                    "customer_phone": "[silindi]",
                    "customer_name": "[silindi]",
                    "buyer_email": "[silindi]",
                    "user_data": None,
                    "pii_redacted": True,
                    "pii_redacted_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            redacted += 1
        if redacted:
            logger.info(f"[scheduler][pii] {redacted} siparişte PII anonimleştirildi (>{days} gün, {platforms})")
            await db.audit_logs.insert_one({
                "id": str(uuid.uuid4()),
                "action": "pii_retention_purge",
                "category": "compliance",
                "details": {"redacted": redacted, "days": days, "platforms": platforms},
                "actor": "system_scheduler",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as e:
        logger.exception(f"[scheduler] pii_retention_purge failed: {e}")


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
    # Marketplace auto-sync tick — her 1 dk'da çalışır, sonra tek tek
    # account'lara ait interval'lere göre ürün/sipariş senkronu planlar.
    # Bu sayede "3 dk'da bir ürün gönder" gibi ince ayarlar çalışır.
    _scheduler.add_job(
        _marketplace_sync_tick,
        "interval",
        minutes=1,
        id="marketplace_auto_sync_tick",
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=45),
        max_instances=1,
        coalesce=True,
    )
    # Günde bir, terkedilmiş sepet mail hatırlatmaları (Resend key varsa çalışır).
    _scheduler.add_job(
        _send_abandoned_cart_reminders,
        "interval",
        hours=24,
        id="abandoned_cart_reminders",
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=2),
        max_instances=1,
        coalesce=True,
    )
    # Ticimax site siparişlerini periyodik çek — 6 saatte bir (günde 4 kez)
    _scheduler.add_job(
        _ticimax_sync_orders,
        "interval",
        hours=6,
        id="ticimax_orders_sync",
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=5),
        max_instances=1,
        coalesce=True,
    )
    # Ticimax canlı stok senkronu — 2 saatte bir
    _scheduler.add_job(
        _ticimax_sync_stock,
        "interval",
        hours=2,
        id="ticimax_stock_sync",
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=10),
        max_instances=1,
        coalesce=True,
    )
    # Iter 43 — Günlük stok tükenme uyarısı (her gün sabah 9:00 UTC, ~12:00 TR)
    async def _daily_stockout_alert():
        try:
            from routes.production_hooks import send_stockout_alert_email
            class _SystemAdmin:
                def get(self, k, *a): return "system@facette.com" if k == "email" else None
            await send_stockout_alert_email(admin=_SystemAdmin())
            logger.info("[scheduler] daily stockout alert sent")
        except Exception as e:
            logger.warning(f"[scheduler] stockout alert failed: {e}")
    from apscheduler.triggers.cron import CronTrigger
    _scheduler.add_job(
        _daily_stockout_alert,
        CronTrigger(hour=9, minute=0),
        id="daily_stockout_alert",
        max_instances=1, coalesce=True,
    )
    # Amazon DPP — PII saklama süresi dolan siparişlerde kişisel verileri anonimleştir
    # (her gün 03:00 UTC). Amazon "Restricted" rol uyumu için kritik kontrol.
    _scheduler.add_job(
        _pii_retention_purge,
        CronTrigger(hour=3, minute=0),
        id="pii_retention_purge",
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=3),
        max_instances=1, coalesce=True,
    )
    _scheduler.start()
    logger.info("[scheduler] Background scheduler started (auto-cancel every 30 min + marketplace auto-sync every 1 min + abandoned cart reminders daily + Ticimax orders every 6h)")
    return _scheduler


def shutdown_scheduler():
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None
