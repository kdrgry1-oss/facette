"""
=============================================================================
notifications.py — Admin bildirim ayarları ve şablon CRUD
=============================================================================
Endpoints:
  GET  /api/notifications/providers           → mevcut config
  POST /api/notifications/providers           → kaydet (sms_active, whatsapp_active, email_active, providers{})
  GET  /api/notifications/providers/catalog   → kanal+sağlayıcı listesi (UI için)

  GET  /api/notifications/templates           → tüm event×channel şablonları
  POST /api/notifications/templates           → tek şablonu kaydet (upsert)
  POST /api/notifications/templates/seed      → default şablonları oluştur (boş değilse dokunmaz)

  POST /api/notifications/test                → test gönderimi
  GET  /api/notifications/logs                → son N log
=============================================================================
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .deps import db, require_admin
from notification_service import (
    SMS_PROVIDERS,
    DEFAULT_EVENTS,
    CHANNELS,
    send_notification,
    test_provider,
    render_template,
    _get_template,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


class ProviderConfigReq(BaseModel):
    sms_active: Optional[str] = None
    whatsapp_active: bool = False
    email_active: bool = True
    providers: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class TemplateReq(BaseModel):
    event: str
    channel: str  # sms|email|whatsapp
    enabled: bool = True
    subject: Optional[str] = ""
    body: str = ""
    meta_template_name: Optional[str] = None
    meta_template_lang: Optional[str] = "tr"
    meta_template_params: Optional[List[str]] = None


class TestReq(BaseModel):
    channel: str
    provider_key: Optional[str] = None
    to: str
    message: str = "Facette test bildirimi ✓"


class TestTemplateReq(BaseModel):
    event: str
    channel: str  # sms|whatsapp|email
    to: str
    order_number: Optional[str] = None  # verilirse bu siparişi baz al; boşsa en son kargolanan


@router.get("/providers/catalog")
async def get_catalog(current_user: dict = Depends(require_admin)):
    return {
        "sms_providers": SMS_PROVIDERS,
        "channels": CHANNELS,
        "events": DEFAULT_EVENTS,
    }


@router.get("/providers")
async def get_providers(current_user: dict = Depends(require_admin)):
    cfg = await db.settings.find_one({"id": "notification_providers"}, {"_id": 0})
    if not cfg:
        cfg = {
            "id": "notification_providers",
            "sms_active": None,
            "whatsapp_active": False,
            "email_active": True,
            "providers": {},
        }
    # Secret alanları maskele (ekranda görünsün ama ham şekilde değil)
    SECRET_FIELDS = {"password", "auth_token", "api_hash", "api_key", "access_token", "api_secret"}
    masked = dict(cfg)
    prov = {}
    for pkey, fields in (cfg.get("providers") or {}).items():
        prov[pkey] = {}
        for f, v in (fields or {}).items():
            if f in SECRET_FIELDS and v:
                s = str(v)
                prov[pkey][f] = (s[:2] + "****" + s[-2:]) if len(s) > 6 else "****"
                prov[pkey][f"__has_{f}"] = True
            else:
                prov[pkey][f] = v
    masked["providers"] = prov
    return masked


@router.post("/providers")
async def save_providers(req: ProviderConfigReq, current_user: dict = Depends(require_admin)):
    # Mevcut config (gizli alanlar için). Eğer UI maskeli bir değeri aynen geri gönderdiyse
    # orijinal değeri koru (yani "xx****yy" gönderilmişse değiştirmiyor sayılır).
    existing = await db.settings.find_one({"id": "notification_providers"}, {"_id": 0}) or {}
    existing_provs = existing.get("providers", {})
    SECRET_FIELDS = {"password", "auth_token", "api_hash", "api_key", "access_token", "api_secret"}
    merged_provs: Dict[str, Dict[str, Any]] = {}
    for pkey, fields in req.providers.items():
        merged = dict(fields or {})
        old = existing_provs.get(pkey, {}) or {}
        for f in list(merged.keys()):
            if f in SECRET_FIELDS:
                val = merged[f]
                # UI'den maskeli/boş geldi → eski değeri koru
                if not val or (isinstance(val, str) and "****" in val):
                    if old.get(f):
                        merged[f] = old[f]
        # __has_ bayraklarını DB'ye yazma
        merged = {k: v for k, v in merged.items() if not k.startswith("__has_")}
        merged_provs[pkey] = merged

    data = {
        "id": "notification_providers",
        "sms_active": req.sms_active,
        "whatsapp_active": req.whatsapp_active,
        "email_active": req.email_active,
        "providers": merged_provs,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": current_user.get("email", ""),
    }
    await db.settings.update_one({"id": "notification_providers"}, {"$set": data}, upsert=True)
    return {"success": True, "message": "Bildirim sağlayıcı ayarları kaydedildi"}


@router.get("/templates")
async def list_templates(current_user: dict = Depends(require_admin)):
    rows = await db.notification_templates.find({}, {"_id": 0}).to_list(length=None)
    return {"templates": rows}


@router.post("/templates")
async def upsert_template(req: TemplateReq, current_user: dict = Depends(require_admin)):
    if req.channel not in CHANNELS:
        raise HTTPException(status_code=400, detail="Geçersiz kanal")
    data = req.model_dump()
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["updated_by"] = current_user.get("email", "")
    await db.notification_templates.update_one(
        {"event": req.event, "channel": req.channel},
        {"$set": data},
        upsert=True,
    )
    return {"success": True}


_DEFAULT_TEMPLATES = {
    # (event, channel) → payload
    ("order_confirmed", "sms"):
        "Merhaba {customer_name}, {order_number} numarali siparisiniz onaylandi. Facette",
    ("order_shipped", "sms"):
        "Siparisiniz kargoya verildi. Kargo takip: {tracking_number}. Facette",
    ("order_delivered", "sms"):
        "Siparisiniz teslim edildi. Facette'i tercih ettiginiz icin tesekkurler.",
    ("order_undelivered", "sms"):
        "Kargonuz teslim edilemedi, subede bekliyor. Takip: {tracking_number}. Facette",
    ("order_cancelled", "sms"):
        "{order_number} numarali siparisiniz iptal edildi. Bilgi: destek@facette.com",
    ("password_reset_otp", "sms"):
        "Facette dogrulama kodunuz: {otp_code} (5 dk gecerli).",
    ("abandoned_cart", "sms"):
        "Sepetinizde urunler kaldi! Siparis tamamlama baglantisi: {cart_url}",
}


# Zengin HTML e-posta şablonları (ZaraHome / Trendyol esinlenmiş minimal tasarım)
_EMAIL_HTML_TEMPLATES = {
    "order_confirmed": {
        "subject": "Siparişin alındı · {order_number}",
        "body": """
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;background:#fafafa;padding:0;margin:0;">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;">
    <div style="text-align:center;padding:32px 24px 16px;border-bottom:1px solid #efefef;">
      <h1 style="margin:0;font-size:22px;font-weight:300;letter-spacing:6px;color:#111;">FACETTE</h1>
    </div>
    <div style="padding:48px 24px 16px;text-align:center;">
      <div style="display:inline-flex;align-items:center;justify-content:center;width:56px;height:56px;border-radius:50%;background:#f7f3ee;margin-bottom:18px;">
        <span style="font-size:28px;color:#b08968;">✓</span>
      </div>
      <h2 style="margin:0 0 8px;font-size:18px;font-weight:500;color:#111;letter-spacing:1px;">SİPARİŞİN ALINDI</h2>
      <p style="color:#6b6b6b;font-size:13px;line-height:1.7;margin:8px 0 4px;">Sevgili {customer_name},</p>
      <p style="color:#6b6b6b;font-size:13px;line-height:1.7;margin:0;">Siparişin için teşekkür ederiz. Hazırlanmaya başladığında seni bilgilendireceğiz.</p>
    </div>
    <div style="padding:0 24px 16px;">
      <table cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#fafafa;padding:18px;border-radius:4px;">
        <tr><td style="font-size:11px;letter-spacing:1.5px;color:#999;text-transform:uppercase;padding-bottom:8px;">Sipariş Numarası</td></tr>
        <tr><td style="font-size:16px;color:#111;font-weight:500;">{order_number}</td></tr>
        <tr><td style="font-size:11px;color:#999;padding-top:12px;">Sipariş tarihi: {order_date}</td></tr>
      </table>
    </div>
    {items_html}
    <div style="padding:0 24px 16px;">
      <table cellpadding="0" cellspacing="0" border="0" style="width:100%;font-size:13px;color:#444;">
        <tr><td style="padding:6px 0;">Ara Toplam</td><td style="text-align:right;padding:6px 0;">{subtotal} TL</td></tr>
        <tr><td style="padding:6px 0;">Kargo</td><td style="text-align:right;padding:6px 0;">{shipping_cost} TL</td></tr>
        <tr><td style="padding:6px 0;color:#b08968;">İndirim</td><td style="text-align:right;padding:6px 0;color:#b08968;">-{discount} TL</td></tr>
        <tr><td style="padding:14px 0 6px;font-weight:600;color:#111;border-top:1px solid #eee;">Toplam</td><td style="text-align:right;padding:14px 0 6px;font-weight:600;color:#111;border-top:1px solid #eee;">{amount}</td></tr>
      </table>
    </div>
    <div style="padding:16px 24px 32px;border-top:1px solid #efefef;">
      <p style="font-size:11px;letter-spacing:1.5px;color:#999;text-transform:uppercase;margin:0 0 8px;">Teslimat Adresi</p>
      <p style="font-size:13px;color:#444;line-height:1.6;margin:0;">{shipping_full_name}<br/>{shipping_address}<br/>{shipping_district} / {shipping_city}<br/>{shipping_phone}</p>
    </div>
    <div style="text-align:center;padding:0 24px 40px;">
      <a href="{order_link}" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:14px 36px;font-size:12px;letter-spacing:2px;text-transform:uppercase;">Siparişimi Görüntüle</a>
    </div>
    <div style="background:#fafafa;padding:24px;text-align:center;color:#999;font-size:11px;letter-spacing:0.5px;line-height:1.7;">
      <p style="margin:0;">FACETTE · facette.com.tr</p>
      <p style="margin:6px 0 0;">Sorularınız için: destek@facette.com.tr</p>
    </div>
  </div>
</div>
""".strip(),
    },
    "order_shipped": {
        "subject": "Kargoya verildi · {order_number}",
        "body": """
<div style="font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;background:#fafafa;margin:0;padding:0;">
  <div style="max-width:600px;margin:0 auto;background:#fff;">
    <div style="text-align:center;padding:32px 24px 16px;border-bottom:1px solid #efefef;">
      <h1 style="margin:0;font-size:22px;font-weight:300;letter-spacing:6px;color:#111;">FACETTE</h1>
    </div>
    <div style="padding:48px 24px 24px;text-align:center;">
      <div style="font-size:42px;margin-bottom:8px;">📦</div>
      <h2 style="margin:0 0 8px;font-size:18px;font-weight:500;color:#111;letter-spacing:1px;">KARGOYA VERİLDİ</h2>
      <p style="color:#6b6b6b;font-size:13px;line-height:1.7;margin:0;">Sevgili {customer_name}, siparişin {cargo_provider} kargosuna teslim edildi.</p>
    </div>
    <div style="padding:0 24px 16px;">
      <table cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#fafafa;padding:18px;border-radius:4px;">
        <tr><td style="font-size:11px;letter-spacing:1.5px;color:#999;text-transform:uppercase;padding-bottom:6px;">Kargo Takip Numarası</td></tr>
        <tr><td style="font-size:18px;color:#111;font-weight:600;font-family:monospace;letter-spacing:1px;">{tracking_number}</td></tr>
      </table>
    </div>
    <div style="text-align:center;padding:8px 24px 40px;">
      <a href="{tracking_link}" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:14px 36px;font-size:12px;letter-spacing:2px;text-transform:uppercase;">Kargo Takibi</a>
    </div>
    <div style="background:#fafafa;padding:24px;text-align:center;color:#999;font-size:11px;letter-spacing:0.5px;">
      <p style="margin:0;">FACETTE · facette.com.tr</p>
    </div>
  </div>
</div>
""".strip(),
    },
    "order_delivered": {
        "subject": "Siparişin teslim edildi · {order_number}",
        "body": """<div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;padding:48px 24px;text-align:center;"><h1 style="font-size:22px;font-weight:300;letter-spacing:6px;color:#111;margin:0 0 32px;">FACETTE</h1><div style="font-size:42px;margin:16px 0;">🎉</div><h2 style="font-size:18px;font-weight:500;letter-spacing:1px;margin:0 0 12px;">SİPARİŞİN TESLİM EDİLDİ</h2><p style="color:#6b6b6b;font-size:13px;line-height:1.7;">Merhaba {customer_name}, {order_number} numaralı siparişin teslim edildi. Tercihin için teşekkür ederiz.</p></div>""",
    },
    "order_cancelled": {
        "subject": "Siparişin iptal edildi · {order_number}",
        "body": """<div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;padding:48px 24px;text-align:center;"><h1 style="font-size:22px;font-weight:300;letter-spacing:6px;margin:0 0 32px;">FACETTE</h1><h2 style="font-size:18px;font-weight:500;margin:0 0 12px;">Siparişin iptal edildi</h2><p style="color:#6b6b6b;font-size:13px;line-height:1.7;">Merhaba {customer_name}, {order_number} numaralı siparişin iptal edilmiştir. Ödemeniz iade edilecektir.</p></div>""",
    },
    "order_undelivered": {
        "subject": "Kargon şubede bekliyor · {order_number}",
        "body": """<div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;padding:48px 24px;text-align:center;"><h1 style="font-size:22px;font-weight:300;letter-spacing:6px;margin:0 0 32px;">FACETTE</h1><h2 style="font-size:18px;font-weight:500;margin:0 0 12px;">Kargon teslim edilemedi</h2><p style="color:#6b6b6b;font-size:13px;line-height:1.7;">Merhaba {customer_name}, kargon teslim edilemedi ve şubede bekliyor.<br/>Takip: <strong>{tracking_number}</strong></p></div>""",
    },
}

# FACETTE Muli marka e-posta şablonları (email_templates.py) — eski ZaraHome tasarımını override eder.
try:
    from email_templates import FACETTE_EMAIL_TEMPLATES as _FET
    _EMAIL_HTML_TEMPLATES = _FET
except Exception:
    pass


@router.post("/templates/seed")
async def seed_templates(
    force: bool = False,
    current_user: dict = Depends(require_admin),
):
    """Default şablonları oluştur. force=true ise mevcut zengin olmayan
    e-posta şablonlarını da günceller (override)."""
    created = 0
    updated = 0
    for ev in DEFAULT_EVENTS:
        ev_key = ev["key"]
        for ch in CHANNELS:
            existing = await db.notification_templates.find_one({"event": ev_key, "channel": ch}, {"_id": 0})
            # Zengin email şablonu varsa onu kullan
            if ch == "email" and ev_key in _EMAIL_HTML_TEMPLATES:
                rich = _EMAIL_HTML_TEMPLATES[ev_key]
                body = rich["body"]
                subj = rich["subject"]
            else:
                body = _DEFAULT_TEMPLATES.get((ev_key, ch), "")
                subj = ev["name"] if ch == "email" else ""
                if ch == "email" and not body:
                    body = f"<p>Merhaba {{customer_name}},</p><p>{ev['name']} bildirimi.</p>"

            if existing:
                # force ile yeniden seedle (manuel düzenlenmemişlere yeniden uygula)
                if not force:
                    continue
                if existing.get("manually_edited"):
                    continue  # admin manuel değiştirdiyse dokunma
                await db.notification_templates.update_one(
                    {"event": ev_key, "channel": ch},
                    {"$set": {
                        "subject": subj,
                        "body": body,
                        "enabled": bool(body),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }}
                )
                updated += 1
            else:
                await db.notification_templates.insert_one({
                    "event": ev_key,
                    "channel": ch,
                    "enabled": bool(body),
                    "subject": subj,
                    "body": body,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                created += 1
    return {"success": True, "created": created, "updated": updated}


@router.post("/test")
async def send_test(req: TestReq, current_user: dict = Depends(require_admin)):
    res = await test_provider(db, req.channel, req.provider_key, req.to, req.message)
    return res


@router.post("/test-template")
async def send_test_template(req: TestTemplateReq, current_user: dict = Depends(require_admin)):
    """
    Seçilen sipariş durumunun (event) GERÇEK şablonunu, en son kargoya verilen
    siparişin gerçek verisiyle doldurup verilen numaraya/e-postaya gönderir.
    Böylece her durumda SMS/WhatsApp/E-posta'nın tam nasıl gideceği görülür.
    """
    # Sipariş no verildiyse O siparişi baz al; verilmediyse en son kargoya verileni.
    req_no = (req.order_number or "").strip()
    if req_no:
        order = await db.orders.find_one({"order_number": req_no}, {"_id": 0})
        if not order:
            # numara biçimi/harf farkını tolere et (tam eşleşme, büyük/küçük harf duyarsız)
            import re as _re
            order = await db.orders.find_one(
                {"order_number": {"$regex": f"^{_re.escape(req_no)}$", "$options": "i"}}, {"_id": 0}
            )
        if not order:
            raise HTTPException(status_code=404, detail=f"Sipariş bulunamadı: {req_no}")
    else:
        # En son kargoya verilen siparişi baz al (tüm değişkenler bu siparişte dolu)
        order = await db.orders.find_one({"status": "shipped"}, {"_id": 0}, sort=[("shipped_at", -1)])
        if not order:
            order = await db.orders.find_one(
                {"cargo_tracking_number": {"$nin": [None, ""]}}, {"_id": 0}, sort=[("updated_at", -1)]
            )
        if not order:
            order = await db.orders.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
        if not order:
            raise HTTPException(status_code=404, detail="Baz alınacak sipariş bulunamadı")

    addr = order.get("shipping_address") or {}
    full_name = (
        f"{addr.get('first_name','')} {addr.get('last_name','')}".strip()
        or addr.get("name") or addr.get("full_name") or "Müşterimiz"
    )
    cargo = order.get("cargo") or {}
    real_tn = (
        cargo.get("mng_nz_barkod") or cargo.get("mng_nz_gonderi_no")
        or cargo.get("mng_gonderi_no") or order.get("cargo_tracking_number") or ""
    ).strip()
    track_link = cargo.get("tracking_link") or order.get("cargo_tracking_url") or ""
    ev_name = next((e["name"] for e in DEFAULT_EVENTS if e["key"] == req.event), req.event)

    variables = {
        "customer_name": full_name,
        "name": full_name,
        "first_name": addr.get("first_name", ""),
        "order_number": order.get("order_number") or "",
        "tracking_number": real_tn,
        "tracking_link": track_link,
        "tracking_url": track_link,
        "cargo_provider": cargo.get("provider_name") or order.get("cargo_provider_name") or "MNG Kargo",
        "amount": float(order.get("total") or 0),
        "total": float(order.get("total") or 0),
        "status_label": ev_name,
        "otp_code": "123456",
        "cart_url": "https://facette.com.tr/sepet",
    }

    to_phone = req.to.strip() if req.channel in ("sms", "whatsapp") else None
    to_email = req.to.strip() if req.channel == "email" else None

    res = await send_notification(
        db, req.event,
        to_phone=to_phone, to_email=to_email,
        variables=variables, channels=[req.channel],
    )

    # Render edilmiş önizleme (panelde göstermek için)
    preview = ""
    try:
        tpl = await _get_template(db, req.event, req.channel)
        if tpl:
            preview = render_template(tpl.get("body", "") or "", variables)
    except Exception:
        pass

    return {
        "success": True,
        "based_on_order": order.get("order_number"),
        "event": req.event,
        "event_name": ev_name,
        "channel": req.channel,
        "variables": variables,
        "preview": preview,
        "result": res,
    }


@router.get("/logs")
async def list_logs(limit: int = Query(50, ge=1, le=500), current_user: dict = Depends(require_admin)):
    rows = (
        await db.notification_logs.find({}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(length=limit)
    )
    return {"logs": rows}
