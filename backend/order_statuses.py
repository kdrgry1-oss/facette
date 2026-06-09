"""
order_statuses.py — Merkezi sipariş durum kataloğu + ayar/bildirim yardımcıları.

- ORDER_STATUS_CATALOG: sistemdeki TÜM olası durumlar
  (key, admin etiketi, müşteri etiketi, bildirim event'i, renk, varsayılan aktif/sms/email).
- Ayar (db.settings._id="order_status_config"):
    { active: [key,...], notify: { key: {"sms":bool,"email":bool} } }
  Admin "Sipariş Durumları" sayfasından hangi durumlar sistemde görünsün +
  hangilerinde SMS/Mail gitsin seçer.
- get_status_config(db): kayıtlı ayarı varsayılanlarla birleştirir; ilgili event'ler
  için eksik bildirim şablonlarını (idempotent) tohumlar.
"""
from datetime import datetime, timezone

# key | label(admin) | customer_label | event | color | group | default_active | default_sms | default_email
ORDER_STATUS_CATALOG = [
    {"key": "pending", "label": "Onay Bekliyor", "customer_label": "Siparişiniz Alındı", "event": "order_pending", "color": "#9CA3AF", "group": "Başlangıç", "default_active": True, "default_sms": False, "default_email": False},
    {"key": "awaiting_payment", "label": "Ödeme Bekleniyor (Havale/EFT)", "customer_label": "Siparişiniz Alındı · Ödeme Bekleniyor", "event": "order_awaiting_payment", "color": "#F59E0B", "group": "Başlangıç", "default_active": True, "default_sms": True, "default_email": True},
    {"key": "payment_notified", "label": "Ödeme Bildirimi Alındı", "customer_label": "Ödeme Bildiriminiz Alındı", "event": "order_payment_notified", "color": "#FBBF24", "group": "Başlangıç", "default_active": True, "default_sms": False, "default_email": False},
    {"key": "confirmed", "label": "Onaylandı", "customer_label": "Siparişiniz Onaylandı", "event": "order_confirmed", "color": "#10B981", "group": "Hazırlık", "default_active": True, "default_sms": True, "default_email": True},
    {"key": "preparing", "label": "Hazırlanıyor", "customer_label": "Siparişiniz Hazırlanıyor", "event": "order_preparing", "color": "#3B82F6", "group": "Hazırlık", "default_active": False, "default_sms": False, "default_email": False},
    {"key": "processing", "label": "İşleme Alındı", "customer_label": "Siparişiniz İşleme Alındı", "event": "order_packed", "color": "#6366F1", "group": "Hazırlık", "default_active": False, "default_sms": False, "default_email": False},
    {"key": "ready_to_ship", "label": "Kargoya Hazır", "customer_label": "Siparişiniz Kargoya Hazırlanıyor", "event": "order_ready_to_ship", "color": "#0EA5E9", "group": "Hazırlık", "default_active": False, "default_sms": False, "default_email": False},
    {"key": "shipped", "label": "Kargoya Verildi", "customer_label": "Siparişiniz Kargoya Verildi", "event": "order_shipped", "color": "#8B5CF6", "group": "Kargo", "default_active": True, "default_sms": True, "default_email": True},
    {"key": "in_transit", "label": "Taşınıyor", "customer_label": "Siparişiniz Yolda", "event": "order_in_transit", "color": "#A855F7", "group": "Kargo", "default_active": False, "default_sms": False, "default_email": False},
    {"key": "out_for_delivery", "label": "Dağıtımda", "customer_label": "Siparişiniz Dağıtımda", "event": "order_out_for_delivery", "color": "#D946EF", "group": "Kargo", "default_active": False, "default_sms": False, "default_email": False},
    {"key": "delivered", "label": "Teslim Edildi", "customer_label": "Siparişiniz Teslim Edildi", "event": "order_delivered", "color": "#059669", "group": "Kargo", "default_active": True, "default_sms": True, "default_email": True},
    {"key": "undelivered", "label": "Teslim Edilemedi", "customer_label": "Teslimat Başarısız (Şubede)", "event": "order_undelivered", "color": "#F97316", "group": "Kargo", "default_active": True, "default_sms": False, "default_email": False},
    {"key": "return_requested", "label": "İade Talebi Oluşturuldu", "customer_label": "İade Talebiniz Oluşturuldu", "event": "order_return_requested", "color": "#F43F5E", "group": "İade", "default_active": True, "default_sms": True, "default_email": True},
    {"key": "return_in_transit", "label": "İade Kargoda", "customer_label": "İadeniz Kargoda", "event": "order_return_in_transit", "color": "#EC4899", "group": "İade", "default_active": False, "default_sms": False, "default_email": False},
    {"key": "returned", "label": "İade Tamamlandı", "customer_label": "İadeniz Tamamlandı", "event": "order_returned", "color": "#BE123C", "group": "İade", "default_active": True, "default_sms": False, "default_email": False},
    {"key": "refunded", "label": "İade Bedeli Ödendi", "customer_label": "İade Bedeliniz Ödendi", "event": "order_refunded", "color": "#9F1239", "group": "İade", "default_active": True, "default_sms": False, "default_email": False},
    {"key": "cancelled", "label": "İptal Edildi", "customer_label": "Siparişiniz İptal Edildi", "event": "order_cancelled", "color": "#6B7280", "group": "Son", "default_active": True, "default_sms": False, "default_email": False},
]

_BY_KEY = {s["key"]: s for s in ORDER_STATUS_CATALOG}
CONFIG_ID = "order_status_config"


def all_status_keys():
    return [s["key"] for s in ORDER_STATUS_CATALOG]


def event_for(key):
    s = _BY_KEY.get(key)
    return s["event"] if s else None


def customer_label_for(key):
    s = _BY_KEY.get(key)
    return s["customer_label"] if s else key


def default_active_keys():
    return [s["key"] for s in ORDER_STATUS_CATALOG if s.get("default_active")]


def _default_notify():
    return {s["key"]: {"sms": bool(s.get("default_sms")), "email": bool(s.get("default_email"))}
            for s in ORDER_STATUS_CATALOG}


def merge_config(saved):
    saved = saved or {}
    valid = set(all_status_keys())
    active = saved.get("active")
    if not isinstance(active, list):
        active = default_active_keys()
    active = [k for k in active if k in valid]
    if not active:
        active = default_active_keys()
    notify = _default_notify()
    for k, v in (saved.get("notify") or {}).items():
        if k in valid and isinstance(v, dict):
            notify[k] = {"sms": bool(v.get("sms")), "email": bool(v.get("email"))}
    return {"active": active, "notify": notify}


# ---- Varsayılan bildirim şablonları (eksikse tohumlanır; admin düzenleyebilir) ----
DEFAULT_STATUS_TEMPLATES = {
    "order_awaiting_payment": {
        "sms": "Sayin {customer_name}, {order_number} numarali siparisiniz alindi. Tutar: {amount}. Havale/EFT icin {bank_name} IBAN {bank_iban} ({bank_account_holder}). Odeme bildirimi: {payment_url}",
        "email_subject": "Siparişiniz Alındı · Ödeme Bekleniyor — {order_number}",
        "email_body": (
            "<p>Merhaba {customer_name},</p>"
            "<p><b>{order_number}</b> numaralı siparişiniz alındı. Siparişiniz onay için ödeme beklemektedir.</p>"
            "<p><b>Tutar:</b> {amount}</p>"
            "<div style='border:1px solid #eee;border-radius:8px;padding:14px;margin:14px 0;'>"
            "<div style='font-weight:700;margin-bottom:8px;'>Havale / EFT Bilgileri</div>"
            "<div>Banka: {bank_name}</div><div>Şube: {bank_branch}</div>"
            "<div>IBAN: <b>{bank_iban}</b></div><div>Hesap Sahibi: {bank_account_holder}</div></div>"
            "<p>Ödemenizi yaptıktan sonra hızlı işleme alabilmemiz için lütfen dekontunuzu iletin:</p>"
            "<p><a href='{payment_url}' style='background:#111;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;'>Ödeme Bildirimi Yap</a></p>"
        ),
    },
    "order_payment_notified": {
        "sms": "Sayin {customer_name}, {order_number} numarali siparisiniz icin odeme bildiriminiz alindi, kontrol ediliyor.",
        "email_subject": "Ödeme Bildiriminiz Alındı — {order_number}",
        "email_body": "<p>Merhaba {customer_name},</p><p><b>{order_number}</b> numaralı siparişiniz için ödeme bildiriminiz alındı ve kontrol ediliyor. Onay sonrası bilgilendirileceksiniz.</p>",
    },
    "order_return_requested": {
        "sms": "Sayin {customer_name}, {order_number} numarali siparisiniz icin iade talebiniz olusturuldu. Iade kargo kodu: {return_code} (3 gun gecerli).",
        "email_subject": "İade Talebiniz Oluşturuldu — {order_number}",
        "email_body": "<p>Merhaba {customer_name},</p><p><b>{order_number}</b> numaralı siparişiniz için iade talebiniz oluşturuldu.</p><p>İade kargo kodunuz: <b>{return_code}</b> (3 gün geçerli).</p>",
    },
    "order_preparing": {"sms": "Sayin {customer_name}, {order_number} numarali siparisiniz hazirlaniyor."},
    "order_ready_to_ship": {"sms": "Sayin {customer_name}, {order_number} numarali siparisiniz kargoya hazirlaniyor."},
    "order_in_transit": {"sms": "Sayin {customer_name}, {order_number} numarali siparisiniz yolda. Takip: {tracking_url}"},
    "order_out_for_delivery": {"sms": "Sayin {customer_name}, {order_number} numarali siparisiniz dagitimda."},
    "order_return_in_transit": {"sms": "Sayin {customer_name}, {order_number} numarali iadeniz kargoda."},
    "order_returned": {"sms": "Sayin {customer_name}, {order_number} numarali iadeniz tamamlandi."},
    "order_refunded": {"sms": "Sayin {customer_name}, {order_number} numarali siparisinizin iade bedeli odendi."},
    "order_pending": {"sms": "Sayin {customer_name}, {order_number} numarali siparisiniz alindi."},
}


async def ensure_status_templates(db):
    """Katalog event'leri için eksik bildirim şablonlarını (idempotent) ekler."""
    try:
        for ev, tpl in DEFAULT_STATUS_TEMPLATES.items():
            if tpl.get("sms"):
                ex = await db.notification_templates.find_one({"event": ev, "channel": "sms"}, {"_id": 0})
                if not ex:
                    await db.notification_templates.insert_one({
                        "event": ev, "channel": "sms", "enabled": True,
                        "subject": "", "body": tpl["sms"],
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
            if tpl.get("email_body"):
                ex = await db.notification_templates.find_one({"event": ev, "channel": "email"}, {"_id": 0})
                if not ex:
                    await db.notification_templates.insert_one({
                        "event": ev, "channel": "email", "enabled": True,
                        "subject": tpl.get("email_subject", ""), "body": tpl["email_body"],
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
    except Exception:
        pass


async def get_status_config(db):
    saved = await db.settings.find_one({"id": CONFIG_ID}, {"_id": 0})
    cfg = merge_config(saved)
    if not (saved and saved.get("templates_seeded")):
        await ensure_status_templates(db)
        await db.settings.update_one(
            {"id": CONFIG_ID}, {"$set": {"id": CONFIG_ID, "templates_seeded": True}}, upsert=True
        )
    return cfg
