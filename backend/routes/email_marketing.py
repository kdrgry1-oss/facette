"""
=============================================================================
email_marketing.py — AWS SES tabanlı E-POSTA PAZARLAMA (toplu kampanya)
=============================================================================
YALNIZ PAZARLAMA. İşlemsel e-posta (sipariş/şifre) ESKİSİ GİBİ Zoho ZeptoMail'den
(email_smtp.py) gider — buraya dokunulmaz. SES ayrı kanaldır (email_ses.py, boto3 HTTPS).

Alıcılar: db.newsletter_subscribers içinde `active!=False` VE `consent==True` olanlar
(KVKK/İYS: yalnız açık rıza verenlere ticari e-posta). Her maile abonelikten-çık linki
eklenir; çıkanlara İYS'ye RET bildirilir.

ENDPOINTS:
  GET/PUT /api/admin/email-marketing/settings     — SES ayarları (secret maskeli/şifreli)
  POST    /api/admin/email-marketing/test         — tek test maili
  GET     /api/admin/email-marketing/audience     — rıza vermiş aktif abone sayısı
  POST    /api/admin/email-marketing/campaigns     — kampanya oluştur + arka planda gönder
  GET     /api/admin/email-marketing/campaigns     — kampanya geçmişi
  GET     /api/email-marketing/unsubscribe        — Public: abonelikten çık (link)
=============================================================================
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from datetime import datetime, timezone

from .deps import db, require_admin, generate_id, logger

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from email_ses import get_ses_config, is_configured, send_ses_email  # noqa: E402

admin_router = APIRouter(prefix="/admin/email-marketing", tags=["email-marketing-admin"])
public_router = APIRouter(prefix="/email-marketing", tags=["email-marketing-public"])

_SECRET_MASK = "********"


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _site_base() -> str:
    """Abonelikten-çık linki için PUBLIC site adresi (beyaz etiket: firma ayarından)."""
    try:
        s = await db.settings.find_one({"id": "main"}, {"_id": 0, "company_info": 1}) or {}
        url = ((s.get("company_info") or {}).get("site_url") or "").strip().rstrip("/")
        if url:
            return url
    except Exception:
        pass
    return (os.environ.get("SITE_URL") or "https://facette.com.tr").rstrip("/")


# ── SES ayarları ────────────────────────────────────────────────────────────
@admin_router.get("/settings")
async def get_settings(current_user: dict = Depends(require_admin)):
    cfg = await db.settings.find_one({"id": "email_ses"}, {"_id": 0}) or {}
    return {
        "enabled": bool(cfg.get("enabled")),
        "region": cfg.get("region", ""),
        "access_key": cfg.get("access_key", ""),
        "secret_key": _SECRET_MASK if cfg.get("secret_key") else "",
        "from_email": cfg.get("from_email", ""),
        "from_name": cfg.get("from_name", ""),
        "configuration_set": cfg.get("configuration_set", ""),
        "configured": is_configured(await get_ses_config(db)),
    }


@admin_router.put("/settings")
async def save_settings(payload: dict, current_user: dict = Depends(require_admin)):
    allowed = {"enabled", "region", "access_key", "secret_key", "from_email", "from_name", "configuration_set"}
    update = {k: v for k, v in (payload or {}).items() if k in allowed}
    # Secret: maske geldiyse DOKUNMA; yeni değer geldiyse ŞİFRELE (at-rest).
    if "secret_key" in update:
        if update["secret_key"] in ("", _SECRET_MASK):
            update.pop("secret_key")
        else:
            try:
                from security.crypto import encrypt as _enc
                update["secret_key"] = _enc(update["secret_key"])
            except Exception:
                pass
    update["updated_at"] = _now()
    await db.settings.update_one({"id": "email_ses"}, {"$set": update, "$setOnInsert": {"id": "email_ses"}}, upsert=True)
    return {"success": True}


@admin_router.post("/test")
async def send_test(payload: dict, current_user: dict = Depends(require_admin)):
    to = (payload or {}).get("to", "").strip()
    if not to:
        raise HTTPException(status_code=400, detail="Test için e-posta adresi gerekli.")
    cfg = await get_ses_config(db)
    if not is_configured(cfg):
        raise HTTPException(status_code=400, detail="SES ayarları eksik/pasif. Bölge, anahtarlar ve gönderen adresi girip aktifleştirin.")
    html = _wrap("Facette — SES Test", "<p>Bu bir <b>AWS SES</b> test e-postasıdır. Bu mail size ulaştıysa pazarlama kanalı çalışıyor. 🎉</p>", unsub_url="")
    r = await send_ses_email(cfg, to, "Facette — SES Test", html)
    if not r.get("success"):
        raise HTTPException(status_code=400, detail=f"Gönderilemedi: {r.get('error') or 'bilinmeyen hata'}")
    return {"success": True, "message_id": r.get("message_id", "")}


@admin_router.get("/audience")
async def audience(current_user: dict = Depends(require_admin)):
    """Ticari e-posta gönderilebilecek kitle = aktif + açık rıza (consent)."""
    total = await db.newsletter_subscribers.count_documents({})
    eligible = await db.newsletter_subscribers.count_documents({"active": {"$ne": False}, "consent": True})
    return {"total": total, "eligible": eligible}


def _wrap(subject: str, body_html: str, unsub_url: str) -> str:
    """Kampanya HTML'ini FACETTE marka kabuğuna sarar (işlemsel maillerle aynı görünüm) +
    abonelikten-çık satırı ekler (İYS/KVKK gereği ticari e-postada zorunlu)."""
    unsub = ""
    if unsub_url:
        unsub = (f'<p style="text-align:center;font-size:11px;color:#9a9a9a;margin-top:24px">'
                 f'Bu e-postayı Facette Kulübü üyesi olduğunuz için aldınız. '
                 f'<a href="{unsub_url}" style="color:#9a9a9a;text-decoration:underline">Abonelikten çık</a></p>')
    content = (body_html or "") + unsub
    try:
        from email_layout import render_email
        return render_email(subject, content)
    except Exception:
        return content


# ── Kampanyalar ───────────────────────────────────────────────────────────────
async def _run_campaign(campaign_id: str):
    """Arka plan: rıza vermiş aktif abonelere SES ile gönderir; sayaçları günceller."""
    camp = await db.email_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not camp:
        return
    cfg = await get_ses_config(db)
    if not is_configured(cfg):
        await db.email_campaigns.update_one({"id": campaign_id}, {"$set": {"status": "failed", "error": "SES yapılandırılmadı", "finished_at": _now()}})
        return
    base = await _site_base()
    subject = camp.get("subject") or ""
    body = camp.get("html") or ""
    await db.email_campaigns.update_one({"id": campaign_id}, {"$set": {"status": "sending", "started_at": _now()}})
    sent = 0
    failed = 0
    n = 0
    cur = db.newsletter_subscribers.find({"active": {"$ne": False}, "consent": True}, {"_id": 0, "email": 1, "id": 1})
    async for s in cur:
        email = (s.get("email") or "").strip()
        if not email:
            continue
        n += 1
        unsub_url = f"{base}/api/email-marketing/unsubscribe?e={email}&t={s.get('id','')}"
        html = _wrap(subject, body, unsub_url)
        try:
            r = await send_ses_email(cfg, email, subject, html)
            if r.get("success"):
                sent += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logger.warning(f"[email-marketing] gönderim hata {email}: {e}")
        if n % 20 == 0:
            await db.email_campaigns.update_one({"id": campaign_id}, {"$set": {"sent": sent, "failed": failed}})
        await asyncio.sleep(0.05)  # SES kota dostu nazik hız
    await db.email_campaigns.update_one({"id": campaign_id}, {"$set": {
        "status": "sent", "sent": sent, "failed": failed, "total": n, "finished_at": _now(),
    }})
    logger.info(f"[email-marketing] kampanya {campaign_id} bitti: {sent} gönderildi, {failed} hata / {n}")


@admin_router.post("/campaigns")
async def create_campaign(payload: dict, current_user: dict = Depends(require_admin)):
    subject = (payload or {}).get("subject", "").strip()
    html = (payload or {}).get("html", "").strip()
    if not subject or not html:
        raise HTTPException(status_code=400, detail="Konu ve içerik zorunlu.")
    cfg = await get_ses_config(db)
    if not is_configured(cfg):
        raise HTTPException(status_code=400, detail="SES ayarları eksik/pasif — önce ayarları girip aktifleştirin.")
    eligible = await db.newsletter_subscribers.count_documents({"active": {"$ne": False}, "consent": True})
    if eligible == 0:
        raise HTTPException(status_code=400, detail="Rıza vermiş aktif abone yok.")
    doc = {
        "id": generate_id(), "subject": subject, "html": html,
        "status": "queued", "total": eligible, "sent": 0, "failed": 0,
        "created_by": current_user.get("email", ""), "created_at": _now(),
    }
    await db.email_campaigns.insert_one(doc)
    doc.pop("_id", None)
    # Arka planda gönder (istek beklemez)
    asyncio.create_task(_run_campaign(doc["id"]))
    return {"success": True, "campaign": doc, "eligible": eligible}


@admin_router.get("/campaigns")
async def list_campaigns(limit: int = 50, current_user: dict = Depends(require_admin)):
    limit = max(1, min(limit, 200))
    rows = await db.email_campaigns.find({}, {"_id": 0, "html": 0}).sort("created_at", -1).to_list(limit)
    return {"campaigns": rows}


# ── Public: abonelikten çık ────────────────────────────────────────────────────
@public_router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(e: str = "", t: str = ""):
    email = (e or "").strip().lower()
    sub = None
    if email and t:
        sub = await db.newsletter_subscribers.find_one({"email": email, "id": t})
    elif email:
        sub = await db.newsletter_subscribers.find_one({"email": email})
    if sub:
        await db.newsletter_subscribers.update_one({"id": sub["id"]}, {"$set": {
            "active": False, "unsubscribed_at": _now(),
        }})
        # İYS'ye RET bildir (best-effort)
        try:
            from .iys import record_consent
            await record_consent(recipient_email=email, recipient_phone="", channels=["EPOSTA"], status="RET", source="HS_WEB")
        except Exception:
            pass
    msg = "Abonelikten çıkarıldınız. Artık pazarlama e-postası almayacaksınız." if sub \
        else "Kayıt bulunamadı veya zaten çıkış yapılmış."
    html = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Abonelik</title></head>
<body style="font-family:system-ui,Arial,sans-serif;background:#fafafa;margin:0;padding:0">
<div style="max-width:460px;margin:12vh auto;background:#fff;border:1px solid #eee;border-radius:14px;padding:40px 32px;text-align:center">
<div style="font-size:22px;letter-spacing:.3em;font-weight:600;color:#111">FACETTE</div>
<p style="color:#444;margin-top:20px;line-height:1.6">{msg}</p>
</div></body></html>"""
    return HTMLResponse(content=html)
