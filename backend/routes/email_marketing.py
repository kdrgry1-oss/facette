"""
=============================================================================
email_marketing.py — Brevo birincil, AWS SES yedek E-POSTA PAZARLAMA
=============================================================================
YALNIZ PAZARLAMA. İşlemsel e-posta (sipariş/şifre) Zoho ZeptoMail'den gider.
Brevo Marketing Campaigns birincil kanaldır; mevcut SES ayarları silinmez ve
ayar açıkken yalnız yapılandırma/yedek kanal olarak kullanılabilir.

Alıcılar: db.newsletter_subscribers içinde `active!=False` VE `consent==True` olanlar
(KVKK/İYS: yalnız açık rıza verenlere ticari e-posta). Her maile abonelikten-çık linki
eklenir; çıkanlara İYS'ye RET bildirilir.

ENDPOINTS:
  GET/PUT /api/admin/email-marketing/settings     — Brevo + yedek SES ayarları
  POST    /api/admin/email-marketing/test         — tek test maili
  GET     /api/admin/email-marketing/audience     — rıza vermiş aktif abone sayısı
  POST    /api/admin/email-marketing/campaigns     — kampanya oluştur + arka planda gönder
  GET     /api/admin/email-marketing/campaigns     — kampanya geçmişi
  GET     /api/admin/email-marketing/suppressions — kara liste (bounce/şikâyet)
  POST    /api/email-marketing/ses-webhook        — Public: AWS SNS bounce/şikâyet bildirimi
  GET     /api/email-marketing/unsubscribe        — Public: abonelikten çık (link)

GÖNDERİM SAĞLIĞI (SES hesabını korur): AWS, bounce oranı %5'i veya şikâyet oranı
%0,1'i aşan hesapların gönderimini ASKIYA ALIR. Bu yüzden SNS'ten gelen kalıcı
bounce/şikâyet adresleri `email_suppressions` kara listesine yazılır ve bir daha
ASLA maillenmez; abone kaydı da pasifleştirilir.
=============================================================================
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from datetime import datetime, timezone

from .deps import db, require_admin, generate_id, logger, require_permission

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from email_ses import get_ses_config, is_configured, send_ses_email  # noqa: E402
from email_brevo import (  # noqa: E402
    create_and_send_campaign,
    get_brevo_config,
    is_configured as brevo_is_configured,
    send_test_email as send_brevo_test,
    sync_contacts as sync_brevo_contacts,
    validate_config as validate_brevo_config,
)
from security.sns import validate_subscribe_url, verify_sns_message  # noqa: E402

admin_router = APIRouter(prefix="/admin/email-marketing", tags=["email-marketing-admin"])
public_router = APIRouter(prefix="/email-marketing", tags=["email-marketing-public"])

_SECRET_MASK = "********"


def _now():
    return datetime.now(timezone.utc).isoformat()


# ── SUPPRESSION (kara liste) ──────────────────────────────────────────────────
# NEDEN ZORUNLU: AWS SES, gönderen hesabın BOUNCE oranı %5'i veya ŞİKÂYET (spam
# işaretleme) oranı %0,1'i aşarsa önce uyarır, sonra gönderim yetkisini ASKIYA ALIR.
# Kalıcı bounce veren (kapanmış/yanlış) adreslere göndermeye devam etmek hesabı yakar.
# Bu yüzden bounce/şikâyet gelen adres bir daha ASLA maillenmez.
async def _suppress(email: str, reason: str, detail: str = "") -> None:
    email = (email or "").strip().lower()
    if not email:
        return
    await db.email_suppressions.update_one(
        {"email": email},
        {"$set": {"email": email, "reason": reason, "detail": (detail or "")[:300],
                  "updated_at": _now()},
         "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )
    # Aboneyi de pasifleştir: kitle sayısı ve gelecekteki kampanyalar doğru olsun.
    try:
        await db.newsletter_subscribers.update_one(
            {"email": email}, {"$set": {"active": False, "suppressed_reason": reason,
                                        "suppressed_at": _now()}})
    except Exception:
        pass


async def _suppressed_set() -> set:
    """Kampanya başında kara listeyi TEK sorguda çeker (alıcı başına sorgu atmamak için —
    hem hız hem MongoDB veri transferi maliyeti)."""
    try:
        rows = await db.email_suppressions.find({}, {"_id": 0, "email": 1}).to_list(100000)
        return {(r.get("email") or "").strip().lower() for r in rows if r.get("email")}
    except Exception as e:
        logger.warning(f"[email-marketing] suppression listesi okunamadı: {e}")
        return set()


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


# ── Sağlayıcı ayarları ──────────────────────────────────────────────────────
@admin_router.get("/settings")
async def get_settings(current_user: dict = Depends(require_admin)):
    brevo = await db.settings.find_one({"id": "email_brevo"}, {"_id": 0}) or {}
    ses = await db.settings.find_one({"id": "email_ses"}, {"_id": 0}) or {}
    routing = await db.settings.find_one({"id": "email_marketing_provider"}, {"_id": 0}) or {}
    return {
        "provider": routing.get("provider") or "brevo",
        "fallback_enabled": bool(routing.get("fallback_enabled", True)),
        "brevo_enabled": bool(brevo.get("enabled")),
        "brevo_api_key": _SECRET_MASK if brevo.get("api_key") else "",
        "brevo_from_email": brevo.get("from_email", ""),
        "brevo_from_name": brevo.get("from_name", ""),
        "brevo_reply_to": brevo.get("reply_to", ""),
        "brevo_list_id": str(brevo.get("list_id") or ""),
        "brevo_webhook_secret": _SECRET_MASK if brevo.get("webhook_secret") else "",
        "ses_enabled": bool(ses.get("enabled")),
        "ses_region": ses.get("region", ""),
        "ses_access_key": ses.get("access_key", ""),
        "ses_secret_key": _SECRET_MASK if ses.get("secret_key") else "",
        "ses_from_email": ses.get("from_email", ""),
        "ses_from_name": ses.get("from_name", ""),
        "ses_configuration_set": ses.get("configuration_set", ""),
        "ses_reply_to": ses.get("reply_to", ""),
        "brevo_configured": brevo_is_configured(await get_brevo_config(db)),
        "ses_configured": is_configured(await get_ses_config(db)),
        "configured": brevo_is_configured(await get_brevo_config(db)) or (
            bool(routing.get("fallback_enabled", True)) and is_configured(await get_ses_config(db))
        ),
    }


@admin_router.put("/settings")
async def save_settings(payload: dict, current_user: dict = Depends(require_admin)):
    payload = payload or {}
    provider = payload.get("provider") if payload.get("provider") in ("brevo", "ses") else "brevo"
    routing = {"provider": provider, "fallback_enabled": bool(payload.get("fallback_enabled", True)), "updated_at": _now()}

    brevo = {
        "enabled": bool(payload.get("brevo_enabled")),
        "from_email": str(payload.get("brevo_from_email") or "").strip(),
        "from_name": str(payload.get("brevo_from_name") or "").strip(),
        "reply_to": str(payload.get("brevo_reply_to") or "").strip(),
        "updated_at": _now(),
    }
    try:
        brevo["list_id"] = int(payload.get("brevo_list_id") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Brevo liste kimliği sayı olmalıdır.")
    api_key = str(payload.get("brevo_api_key") or "").strip()
    if api_key and api_key != _SECRET_MASK:
        try:
            from security.crypto import encrypt as _enc
            brevo["api_key"] = _enc(api_key)
        except Exception:
            brevo["api_key"] = api_key
    webhook_secret = str(payload.get("brevo_webhook_secret") or "").strip()
    if webhook_secret and webhook_secret != _SECRET_MASK:
        try:
            from security.crypto import encrypt as _enc
            brevo["webhook_secret"] = _enc(webhook_secret)
        except Exception:
            brevo["webhook_secret"] = webhook_secret

    ses_map = {
        "ses_enabled": "enabled", "ses_region": "region", "ses_access_key": "access_key",
        "ses_from_email": "from_email", "ses_from_name": "from_name",
        "ses_configuration_set": "configuration_set", "ses_reply_to": "reply_to",
    }
    ses = {dst: payload.get(src) for src, dst in ses_map.items() if src in payload}
    ses["updated_at"] = _now()
    secret = str(payload.get("ses_secret_key") or "").strip()
    if secret and secret != _SECRET_MASK:
        try:
            from security.crypto import encrypt as _enc
            ses["secret_key"] = _enc(secret)
        except Exception:
            ses["secret_key"] = secret

    await db.settings.update_one({"id": "email_marketing_provider"}, {"$set": routing, "$setOnInsert": {"id": "email_marketing_provider"}}, upsert=True)
    await db.settings.update_one({"id": "email_brevo"}, {"$set": brevo, "$setOnInsert": {"id": "email_brevo"}}, upsert=True)
    await db.settings.update_one({"id": "email_ses"}, {"$set": ses, "$setOnInsert": {"id": "email_ses"}}, upsert=True)
    return {"success": True, "provider": provider}


async def _selected_provider() -> tuple[str, dict]:
    routing = await db.settings.find_one({"id": "email_marketing_provider"}, {"_id": 0}) or {}
    primary = routing.get("provider") or "brevo"
    brevo = await get_brevo_config(db)
    ses = await get_ses_config(db)
    if primary == "brevo" and brevo_is_configured(brevo):
        return "brevo", brevo
    if primary == "ses" and is_configured(ses):
        return "ses", ses
    if routing.get("fallback_enabled", True):
        if primary != "brevo" and brevo_is_configured(brevo):
            return "brevo", brevo
        if primary != "ses" and is_configured(ses):
            return "ses", ses
    return primary, {}


@admin_router.post("/validate-provider")
async def validate_provider(current_user: dict = Depends(require_admin)):
    """Birincil sağlayıcının kimlik bilgilerini gönderim yapmadan doğrular."""
    provider, cfg = await _selected_provider()
    if not cfg:
        raise HTTPException(status_code=400, detail="Kullanılabilir e-posta pazarlama sağlayıcısı yok.")
    if provider == "brevo":
        result = await validate_brevo_config(cfg)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=f"Brevo doğrulanamadı: {result.get('error') or 'bilinmeyen hata'}")
    return {"success": True, "provider": provider}


@admin_router.post("/test")
async def send_test(payload: dict, current_user: dict = Depends(require_permission("tasarim.email"))):
    """Test e-postası gönderir. `subject`+`html` VERİLİRSE kullanıcının KAMPANYA İÇERİĞİNİ
    (markalı kabukla) gönderir — composer'dan 'Test olarak gönder'. Verilmezse SES Ayarları'nın
    sabit "SES Test" davranışı korunur. Placeholder'lar ({customer_name}/{kod}/{indirim}/URUN_LINKI)
    testte HAM gider (kişiselleştirme gerçek kampanyada uygulanır). `to` zorunlu."""
    to = (payload or {}).get("to", "").strip()
    if not to:
        raise HTTPException(status_code=400, detail="Test için e-posta adresi gerekli.")
    provider, cfg = await _selected_provider()
    if not cfg:
        raise HTTPException(status_code=400, detail="Brevo ayarları eksik/pasif ve kullanılabilir SES yedeği yok.")
    _subject = str((payload or {}).get("subject") or "").strip()
    _body = str((payload or {}).get("html") or "")
    if _subject and _body.strip():
        # Test gönderiminde de {customer_name} makul bir örnekle dolsun (ham görünmesin):
        # alıcının kayıtlı adı → yoksa "Değerli Üyemiz". {kod}/{indirim}/link ham kalır (kampanya-seviyesi).
        _cn = "Değerli Üyemiz"
        try:
            _u = await db.users.find_one({"email": to}, {"_id": 0, "first_name": 1, "name": 1})
            _cn = ((_u or {}).get("first_name") or (_u or {}).get("name") or "").strip() or "Değerli Üyemiz"
        except Exception:
            pass
        try:
            from notification_service import render_template as _render_tpl
            subject = _render_tpl(_subject, {"customer_name": _cn})
            _body = _render_tpl(_body, {"customer_name": _cn})
        except Exception:
            subject = _subject
        html = _wrap(subject, _body, unsub_url="")
    else:
        subject = f"Facette — {provider.upper()} Test"
        html = _wrap(subject, f"<p>Bu bir <b>{provider.upper()}</b> test e-postasıdır. Bu mail size ulaştıysa pazarlama kanalı çalışıyor. 🎉</p>", unsub_url="")
    if provider == "brevo":
        r = await send_brevo_test(cfg, to, subject, html, cfg.get("reply_to") or "")
    else:
        r = await send_ses_email(cfg, to, subject, html, cfg.get("reply_to") or "")
    if not r.get("success"):
        raise HTTPException(status_code=400, detail=f"Gönderilemedi: {r.get('error') or r.get('response') or 'bilinmeyen hata'}")
    return {"success": True, "provider": provider, "message_id": r.get("message_id", "")}


@admin_router.get("/audience")
async def audience(current_user: dict = Depends(require_admin)):
    """Ticari e-posta gönderilebilecek kitle = aktif + açık rıza (consent)."""
    total = await db.newsletter_subscribers.count_documents({})
    eligible = await db.newsletter_subscribers.count_documents({"active": {"$ne": False}, "consent": True})
    # Kara liste (bounce/şikâyet) sayısı — panelde görünsün ki gönderim sağlığı izlenebilsin.
    try:
        suppressed = await db.email_suppressions.count_documents({})
    except Exception:
        suppressed = 0
    return {"total": total, "eligible": eligible, "suppressed": suppressed}


def _is_full_html_document(html: str) -> bool:
    """İçerik TAM BİR HTML BELGESİ mi? (kendi <head>/logo/footer'ı olan, komple sayfa).
    Büyük/küçük harf duyarsız `<!doctype` VEYA `<html` içeriyorsa tam belge sayılır."""
    low = (html or "").lower()
    return ("<!doctype" in low) or ("<html" in low)


def _inject_unsub_into_full(html: str, unsub_html: str) -> str:
    """Tam-HTML belgesine abonelikten-çık satırını `</body>`'den hemen ÖNCE enjekte eder;
    `</body>` yoksa gövde sonuna ekler. (İYS/KVKK: ticari e-postada zorunlu.)"""
    if not unsub_html:
        return html
    import re as _re
    m = _re.search(r"</body\s*>", html or "", _re.IGNORECASE)
    if m:
        return (html[:m.start()] + unsub_html + html[m.start():])
    return (html or "") + unsub_html


def _wrap(subject: str, body_html: str, unsub_url: str) -> str:
    """Kampanya HTML'ini FACETTE marka kabuğuna sarar (işlemsel maillerle aynı görünüm) +
    abonelikten-çık satırı ekler (İYS/KVKK gereği ticari e-postada zorunlu).

    ÇİFT-FACETTE FİKSİ: İçerik TAM BİR HTML BELGESİ ise (kullanıcı kendi FACETTE logo/footer'ı
    olan komple sayfayı yapıştırmış) panel kabuğu (render_email = ikinci FACETTE header+footer)
    EKLENMEZ; HTML olduğu gibi gönderilir, YALNIZ abonelikten-çık satırı </body> öncesine enjekte
    edilir. İç-gövde/parça ise eski davranış: render_email ile FACETTE kabuğuna sarılır."""
    unsub = ""
    if unsub_url:
        unsub = (f'<p style="text-align:center;font-size:11px;color:#9a9a9a;margin-top:24px">'
                 f'Bu e-postayı Facette Kulübü üyesi olduğunuz için aldınız. '
                 f'<a href="{unsub_url}" style="color:#9a9a9a;text-decoration:underline">Abonelikten çık</a></p>')
    body = body_html or ""
    if _is_full_html_document(body):
        # Tam belge → kabuk YOK (çift FACETTE önlenir), abonelikten-çık VAR.
        return _inject_unsub_into_full(body, unsub)
    content = body + unsub
    try:
        from email_layout import render_email
        return render_email(subject, content)
    except Exception:
        return content


# ── Kampanyalar ───────────────────────────────────────────────────────────────
async def _run_ses_campaign(campaign_id: str):
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
    # MÜKERRER GÖNDERİM KORUMASI: kampanya yarıda kesilirse (deploy/yeniden başlatma)
    # baştan başlayıp HERKESE tekrar mail atılıyordu. Artık ilerleme `cursor` ile
    # (son işlenen abone id'si) saklanır; devam eden çalışma kaldığı yerden sürer.
    _resume = camp.get("cursor") or ""
    sent = int(camp.get("sent") or 0)
    failed = int(camp.get("failed") or 0)
    error_sample = camp.get("error_sample") or ""  # ilk hata mesajı (panelde 'neden' göstermek için)
    n = int(camp.get("total_processed") or 0)
    await db.email_campaigns.update_one({"id": campaign_id}, {"$set": {
        "status": "sending", "started_at": camp.get("started_at") or _now()}})

    suppressed = await _suppressed_set()
    skipped = int(camp.get("skipped") or 0)

    # KİŞİSELLEŞTİRME: bildirim sistemiyle AYNI motor (render_template) → {customer_name}
    # her aboneye gerçek adıyla dolar. {kod}/{indirim}/URUN_LINKI/GORSEL_URL KAMPANYA-seviyesi
    # (admin ne yazdıysa aynen gider — bilinmeyen placeholder render_template'te KORUNUR).
    try:
        from notification_service import render_template as _render_tpl
    except Exception:
        _render_tpl = None

    _q = {"active": {"$ne": False}, "consent": True}
    if _resume:
        _q["id"] = {"$gt": _resume}          # kaldığı yerden (id sırası deterministik)
    cur = db.newsletter_subscribers.find(
        _q, {"_id": 0, "email": 1, "id": 1, "name": 1, "first_name": 1, "full_name": 1}).sort("id", 1)
    async for s in cur:
        email = (s.get("email") or "").strip()
        if not email:
            continue
        # Kara listedeki adrese ASLA gönderme (SES itibarını korur).
        if email.lower() in suppressed:
            skipped += 1
            continue
        n += 1
        # customer_name: abone adı → yoksa users.first_name (e-posta ile) → yoksa nötr fallback.
        _name = (s.get("name") or s.get("first_name") or s.get("full_name") or "").strip()
        if not _name:
            try:
                _u = await db.users.find_one({"email": email}, {"_id": 0, "first_name": 1, "name": 1})
                _name = ((_u or {}).get("first_name") or (_u or {}).get("name") or "").strip()
            except Exception:
                _name = ""
        _cn = _name or "değerli müşterimiz"
        _subj = _render_tpl(subject, {"customer_name": _cn}) if _render_tpl else subject
        _body = _render_tpl(body, {"customer_name": _cn}) if _render_tpl else body
        unsub_url = f"{base}/api/email-marketing/unsubscribe?e={email}&t={s.get('id','')}"
        html = _wrap(_subj, _body, unsub_url)
        try:
            r = await send_ses_email(cfg, email, _subj, html, cfg.get("reply_to") or "")
            if r.get("success"):
                sent += 1
            else:
                failed += 1
                if not error_sample:
                    error_sample = str(r.get("error") or "bilinmeyen hata")[:400]
        except Exception as e:
            failed += 1
            if not error_sample:
                error_sample = str(e)[:400]
            logger.warning(f"[email-marketing] gönderim hata {email}: {e}")

        # ERKEN DURDURMA: ilk denemelerin TAMAMI başarısızsa (0 gönderim) config/SES sandbox
        # bozuk demektir → 679 aboneyi boşa deneyip SES itibarını yakmadan kampanyayı DURDUR ve
        # NET sebep yaz (panelde 'sending' sonsuza kadar takılı kalmasın).
        if n >= 12 and sent == 0 and failed >= n:
            _err = (error_sample or "Tüm gönderimler reddedildi")
            _lo = _err.lower()
            _sandbox = ("not verified" in _lo or "sandbox" in _lo or "messagerejected" in _lo)
            if _sandbox:
                _reason = ("AWS SES sandbox modunda: mail YALNIZ doğrulanmış adreslere gider, "
                           "doğrulanmamış aboneler reddedilir. Toplu gönderim için AWS'den SES "
                           f"production access (sandbox çıkışı) alınmalı. Örnek: {_err[:160]}")
            else:
                _reason = f"İlk {n} gönderimin tümü başarısız — gönderim durduruldu. Örnek: {_err[:160]}"
            await db.email_campaigns.update_one({"id": campaign_id}, {"$set": {
                "status": "failed", "sent": sent, "failed": failed, "skipped": skipped,
                "total_processed": n, "cursor": s.get("id") or "", "finished_at": _now(),
                "error_sample": error_sample, "error": _reason, "aborted": True}})
            logger.warning(f"[email-marketing] kampanya {campaign_id} ERKEN DURDURULDU: {_reason}")
            return

        # cursor HER kalemde yazılır ki yarıda kesilme en fazla 1 mükerrer mail versin.
        if n % 20 == 0:
            await db.email_campaigns.update_one({"id": campaign_id}, {"$set": {
                "sent": sent, "failed": failed, "skipped": skipped, "error_sample": error_sample,
                "total_processed": n, "cursor": s.get("id") or ""}})
        else:
            await db.email_campaigns.update_one({"id": campaign_id},
                                                {"$set": {"cursor": s.get("id") or ""}})
        await asyncio.sleep(0.05)  # SES kota dostu nazik hız
    await db.email_campaigns.update_one({"id": campaign_id}, {"$set": {
        "status": "sent", "sent": sent, "failed": failed, "skipped": skipped,
        "total": n, "total_processed": n, "finished_at": _now(), "error_sample": error_sample,
    }})
    logger.info(f"[email-marketing] kampanya {campaign_id} bitti: {sent} gönderildi, {failed} hata / {n}")


async def _run_brevo_campaign(campaign_id: str):
    """Rızalı yerel kitleyi Brevo listesiyle eşitler ve Marketing Campaigns API'sine yollar."""
    camp = await db.email_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not camp:
        return
    cfg = await get_brevo_config(db)
    if not brevo_is_configured(cfg):
        await db.email_campaigns.update_one({"id": campaign_id}, {"$set": {
            "status": "failed", "error": "Brevo yapılandırılmadı", "finished_at": _now(),
        }})
        return
    await db.email_campaigns.update_one({"id": campaign_id}, {"$set": {
        "status": "syncing", "started_at": camp.get("started_at") or _now(),
    }})

    suppressed = await _suppressed_set()
    rows = await db.newsletter_subscribers.find(
        {"active": {"$ne": False}, "consent": True},
        {"_id": 0, "email": 1, "id": 1, "name": 1, "first_name": 1, "full_name": 1},
    ).to_list(100000)
    contacts = [row for row in rows if (row.get("email") or "").strip().lower() not in suppressed]
    sync = await sync_brevo_contacts(cfg, contacts)
    if not sync.get("success"):
        await db.email_campaigns.update_one({"id": campaign_id}, {"$set": {
            "status": "failed", "failed": 0, "skipped": len(rows) - len(contacts),
            "error": sync.get("error") or "Brevo kitle eşitleme başarısız",
            "error_sample": sync.get("error") or "", "finished_at": _now(),
        }})
        return

    # Eski panel placeholder'ını Brevo'nun kişi alanına dönüştür. Brevo, boş FIRSTNAME
    # için boş değer kullanır; şablonlarda nötr hitap tercih edilmesi önerilir.
    subject = str(camp.get("subject") or "").replace("{customer_name}", "{{ contact.FIRSTNAME }}")
    body = str(camp.get("html") or "").replace("{customer_name}", "{{ contact.FIRSTNAME }}")
    html = _wrap(subject, body, "{{ unsubscribe }}")
    result = await create_and_send_campaign(
        cfg,
        name=f"Facette · {camp.get('subject') or campaign_id} · {campaign_id[:8]}",
        subject=subject,
        html=html,
        tag=f"facette-{campaign_id[:12]}",
    )
    if not result.get("success"):
        await db.email_campaigns.update_one({"id": campaign_id}, {"$set": {
            "status": "failed", "error": result.get("error") or "Brevo kampanyası başlatılamadı",
            "error_sample": result.get("error") or "", "external_campaign_id": result.get("campaign_id"),
            "synced": sync.get("synced", 0), "finished_at": _now(),
        }})
        return

    # Brevo isteği kabul edip kampanyayı kendi kuyruğuna aldığında teslimat henüz kesinleşmez.
    # Bu yüzden `sent` uydurulmaz; hedef toplam ve dış kampanya kimliği ayrı tutulur.
    await db.email_campaigns.update_one({"id": campaign_id}, {"$set": {
        "status": "submitted", "sent": 0, "failed": 0, "total": len(contacts),
        "skipped": len(rows) - len(contacts), "synced": sync.get("synced", 0),
        "external_campaign_id": result.get("campaign_id"), "finished_at": _now(),
    }})
    logger.info(f"[email-marketing] Brevo kampanya {campaign_id}, hedef {len(contacts)}, dış id {result.get('campaign_id')}")


async def _run_campaign(campaign_id: str):
    camp = await db.email_campaigns.find_one({"id": campaign_id}, {"_id": 0, "provider": 1})
    if (camp or {}).get("provider") == "brevo":
        await _run_brevo_campaign(campaign_id)
    else:
        await _run_ses_campaign(campaign_id)


@admin_router.post("/campaigns")
async def create_campaign(payload: dict, current_user: dict = Depends(require_permission("tasarim.email"))):
    subject = (payload or {}).get("subject", "").strip()
    html = (payload or {}).get("html", "").strip()
    if not subject or not html:
        raise HTTPException(status_code=400, detail="Konu ve içerik zorunlu.")
    provider, cfg = await _selected_provider()
    if not cfg:
        raise HTTPException(status_code=400, detail="Brevo ayarları eksik/pasif ve kullanılabilir SES yedeği yok.")
    eligible = await db.newsletter_subscribers.count_documents({"active": {"$ne": False}, "consent": True})
    if eligible == 0:
        raise HTTPException(status_code=400, detail="Rıza vermiş aktif abone yok.")
    doc = {
        "id": generate_id(), "subject": subject, "html": html,
        "status": "queued", "provider": provider, "total": eligible, "sent": 0, "failed": 0,
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


# ── HAZIR KAMPANYA ŞABLONLARI (email_templates) + ÖNİZLEME ─────────────────────
# Şablonlar YALNIZ iç gövde HTML'i tutar; gönderim/önizlemede _wrap → render_email
# ile FACETTE marka kabuğuna (logo + sosyal footer + abonelikten-çık) sarılır.
# Placeholder'lar: {customer_name} (bildirim sistemiyle AYNI — per-alıcı otomatik dolar),
# {kod}/{indirim}/URUN_LINKI/GORSEL_URL (kampanya-seviyesi, admin editörde doldurur).
_BTN_STYLE = ("display:inline-block;background:#1a1a1a;color:#ffffff;text-decoration:none;"
              "padding:15px 44px;font-size:13px;font-weight:500;letter-spacing:1.5px;"
              "text-transform:uppercase;border-radius:2px;")
_P_STYLE = "font-size:15px;line-height:1.75;color:#4a4a4a;margin:0 0 22px;"
_HINT_STYLE = "font-size:12px;line-height:1.6;color:#9a9a9a;margin:24px 0 0;"


def _seed_body(intro_html: str, cta_text: str, extra_html: str = "") -> str:
    """Ortak iç-gövde iskeleti: kısa metin + CTA buton (link placeholder) + ipucu satırı."""
    return (
        f'<p style="{_P_STYLE}">{intro_html}</p>'
        f'{extra_html}'
        f'<a href="URUN_LINKI" style="{_BTN_STYLE}">{cta_text}</a>'
        f'<p style="{_HINT_STYLE}">↑ <b>URUN_LINKI</b> yazan yeri kendi kampanya/koleksiyon '
        f'bağlantınızla değiştirin. {{customer_name}} her aboneye adıyla OTOMATİK dolar; '
        f'{{kod}}/{{indirim}} ve GORSEL_URL kendi bilginizle doldurulur (tüm alıcılarda aynı).</p>'
    )


_IMG_PLACEHOLDER = (
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
    'style="margin:0 0 22px;"><tr><td align="center">'
    '<img src="GORSEL_URL" alt="Görsel" width="512" '
    'style="display:block;width:100%;max-width:512px;height:auto;border:0;border-radius:2px;" />'
    '<div style="font-size:11px;color:#b8b8b8;margin-top:6px;">GORSEL_URL → kendi görsel bağlantınız</div>'
    '</td></tr></table>'
)


# Hazır (builtin) şablonlar — kadın giyim, sade/şık FACETTE sesi. builtin_key idempotent anahtar.
_SEED_EMAIL_TEMPLATES = [
    {
        # İLK KAMPANYA — markanın ilk e-posta gönderimi için önerilen (listede EN ÜSTTE).
        "builtin_key": "ilk-kampanya", "name": "İlk Kampanya / Kulübe Merhaba",
        "category": "Tanıtım", "recommended": True, "subject": "Facette Kulübü'ne Hoş Geldiniz",
        "html": _seed_body(
            "Merhaba {customer_name},<br><br>Biz FACETTE — zamansız kesimler ve yumuşak dokularla, "
            "günlük şıklığı sade bir dille anlatan bir kadın giyim markasıyız. "
            "Facette Kulübü'ne katıldığınız için çok mutluyuz.<br><br>"
            "Yeni koleksiyonlar, özel kampanyalar ve size özel fırsatlar ilk olarak burada. "
            "Tanışmamıza özel <b>{kod}</b> koduyla ilk alışverişinizde küçük bir hoş geldin "
            "hediyesi sizi bekliyor.",
            "Koleksiyonu Keşfet", _IMG_PLACEHOLDER),
    },
    {
        "builtin_key": "yeni-sezon", "name": "Yeni Sezon / Koleksiyon Lansmanı",
        "category": "Koleksiyon", "subject": "Yeni Sezon Geldi",
        "html": _seed_body(
            "Merhaba {customer_name},<br>Yeni sezon parçalarımız FACETTE'de. Zamansız kesimler, "
            "yumuşak dokular ve sezonun en sevilen tonları seni bekliyor.",
            "Koleksiyonu Keşfet", _IMG_PLACEHOLDER),
    },
    {
        "builtin_key": "indirim", "name": "İndirim Kampanyası",
        "category": "İndirim", "subject": "%{indirim} İndirim Başladı",
        "html": _seed_body(
            "Merhaba {customer_name},<br>Seçili ürünlerde <b>%{indirim} indirim</b> başladı. "
            "Sepette <b>{kod}</b> kodunu kullan, favori parçalarına şimdi sahip ol.",
            "Alışverişe Başla"),
    },
    {
        "builtin_key": "hosgeldin", "name": "Hoş Geldin / Yeni Üye",
        "category": "Üyelik", "subject": "FACETTE'ye Hoş Geldin",
        "html": _seed_body(
            "Merhaba {customer_name},<br>Aramıza hoş geldin. İlk siparişine özel <b>{kod}</b> "
            "(HOSGELDIN) koduyla tanışma indirimini kullanabilirsin.",
            "İlk Siparişini Ver"),
    },
    {
        "builtin_key": "tekrar-stokta", "name": "Tekrar Stokta",
        "category": "Ürün", "subject": "Favorilerin Tekrar Stokta",
        "html": _seed_body(
            "Merhaba {customer_name},<br>Beklediğin parçalar yeniden stokta. En sevilenler hızla "
            "tükeniyor — kaçırmadan incele.",
            "Şimdi İncele", _IMG_PLACEHOLDER),
    },
    {
        "builtin_key": "ozel-gun", "name": "Özel Gün (Bayram / Yılbaşı)",
        "category": "Özel Gün", "subject": "Sana Özel Kutlama İndirimi",
        "html": _seed_body(
            "Merhaba {customer_name},<br>Bu özel günü birlikte kutlayalım. Sana özel <b>%{indirim}</b> "
            "hediye — <b>{kod}</b> koduyla kendine ya da sevdiklerine şık bir seçim yap.",
            "Kutlamaya Katıl"),
    },
    {
        "builtin_key": "vip-erken-erisim", "name": "VIP / Kulüp Erken Erişim",
        "category": "VIP", "subject": "Sana Özel Erken Erişim",
        "html": _seed_body(
            "Merhaba {customer_name},<br>Facette Kulübü üyelerine özel: yeni koleksiyona <b>herkesten "
            "önce</b> eriş. Sınırlı sayıda — senin için ayrı tuttuk.",
            "Erken Erişimi Aç"),
    },
    {
        "builtin_key": "sepette-unutulanlar", "name": "Sepette Unutulanlar",
        "category": "Hatırlatma", "subject": "Sepetinde Bir Şey Unuttun",
        "html": _seed_body(
            "Merhaba {customer_name},<br>Beğendiğin parçalar sepetinde seni bekliyor. Stoklar "
            "sınırlı; dilersen alışverişini şimdi tamamlayabilirsin.",
            "Sepete Dön"),
    },
]


async def seed_email_templates() -> int:
    """Hazır şablonları İDEMPOTENT ekler/günceller (builtin_key anahtar). İlk GET'te çağrılır
    → ayrı startup hook gerektirmez. BUILTIN'ler KOD-SAHİPLİ: içerik (name/category/subject/html/
    recommended) koddaki güncel seed'e EŞİTLENİR (ör. {ad}→{customer_name} güncellemesi yayılsın).
    KULLANICI kopyaları AYRI dokümanlardır (builtin!=True) — onlara DOKUNULMAZ."""
    added = 0
    for t in _SEED_EMAIL_TEMPLATES:
        key = t["builtin_key"]
        _fields = {
            "builtin": True,
            "recommended": bool(t.get("recommended")),
            "name": t["name"], "category": t.get("category", "Genel"),
            "subject": t["subject"], "html": t["html"],
            "updated_at": _now(),
        }
        existing = await db.email_templates.find_one({"builtin_key": key}, {"_id": 0, "id": 1, "html": 1, "name": 1, "subject": 1, "category": 1})
        if existing:
            # İçerik değiştiyse builtin'i güncel seed'e eşitle (kod otorite).
            if any(existing.get(k) != _fields.get(k) for k in ("html", "name", "subject", "category")):
                try:
                    await db.email_templates.update_one({"builtin_key": key}, {"$set": _fields})
                except Exception as e:
                    logger.warning(f"[email-marketing] seed şablon güncellenemedi {key}: {e}")
            continue
        doc = {"id": f"builtin:{key}", "builtin_key": key, "created_at": _now(), **_fields}
        try:
            await db.email_templates.insert_one(doc)
            added += 1
        except Exception as e:
            logger.warning(f"[email-marketing] seed şablon eklenemedi {key}: {e}")
    return added


@admin_router.get("/templates")
async def list_templates(current_user: dict = Depends(require_admin)):
    """Hazır (builtin) + kullanıcının kaydettiği şablonlar. Builtin'ler önce, sonra en yeni."""
    await seed_email_templates()  # idempotent: yoksa ekler
    rows = await db.email_templates.find({}, {"_id": 0}).to_list(1000)
    # Builtin'ler: önerilen (İlk Kampanya) EN ÜSTTE, sonra seed sırası; sonra kullanıcı (en yeni üstte).
    _seed_order = {t["builtin_key"]: i for i, t in enumerate(_SEED_EMAIL_TEMPLATES)}
    builtin = sorted([r for r in rows if r.get("builtin")],
                     key=lambda r: (0 if r.get("recommended") else 1,
                                    _seed_order.get(r.get("builtin_key"), 999)))
    mine = sorted([r for r in rows if not r.get("builtin")],
                  key=lambda r: r.get("created_at") or "", reverse=True)
    return {"templates": builtin + mine}


@admin_router.post("/templates")
async def save_template(payload: dict, current_user: dict = Depends(require_admin)):
    """Kullanıcı şablonu kaydet/güncelle. Builtin'ler DEĞİŞTİRİLEMEZ — builtin id gelirse
    ya da id yoksa YENİ kullanıcı şablonu oluşturulur (kopyala-düzenle). Yalnız mevcut
    bir KULLANICI şablonunun id'si güncellenir."""
    p = payload or {}
    name = str(p.get("name") or "").strip()
    subject = str(p.get("subject") or "").strip()
    html = str(p.get("html") or "").strip()
    category = str(p.get("category") or "Genel").strip() or "Genel"
    if not name or not html:
        raise HTTPException(status_code=400, detail="Şablon adı ve içerik (HTML) zorunlu.")
    tid = str(p.get("id") or "").strip()
    now = _now()
    # Güncelleme YALNIZ mevcut bir kullanıcı (builtin olmayan) şablonu için.
    if tid and not tid.startswith("builtin:"):
        existing = await db.email_templates.find_one({"id": tid, "builtin": {"$ne": True}}, {"_id": 0})
        if existing:
            await db.email_templates.update_one({"id": tid}, {"$set": {
                "name": name, "subject": subject, "html": html, "category": category, "updated_at": now}})
            doc = await db.email_templates.find_one({"id": tid}, {"_id": 0})
            return {"success": True, "template": doc, "updated": True}
    doc = {
        "id": generate_id(), "builtin": False, "name": name, "category": category,
        "subject": subject, "html": html,
        "created_by": current_user.get("email", ""), "created_at": now, "updated_at": now,
    }
    await db.email_templates.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "template": doc, "updated": False}


@admin_router.delete("/templates/{template_id}")
async def delete_template(template_id: str, current_user: dict = Depends(require_admin)):
    """Kullanıcı şablonunu siler. Builtin (hazır) şablonlar SİLİNEMEZ."""
    if str(template_id).startswith("builtin:"):
        raise HTTPException(status_code=400, detail="Hazır şablonlar silinemez (kopyalayıp düzenleyin).")
    doc = await db.email_templates.find_one({"id": template_id}, {"_id": 0, "builtin": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı.")
    if doc.get("builtin"):
        raise HTTPException(status_code=400, detail="Hazır şablonlar silinemez.")
    await db.email_templates.delete_one({"id": template_id})
    return {"success": True}


@admin_router.post("/preview")
async def preview_email(payload: dict, current_user: dict = Depends(require_admin)):
    """Verilen {subject, html} için TAM markalı e-postayı (logo + footer + abonelikten-çık)
    döndürür — gönderim/secret YOK, sadece render. Kullanıcı göndermeden önce görür."""
    p = payload or {}
    subject = str(p.get("subject") or "").strip()
    html = str(p.get("html") or "")
    # Önizlemede örnek abonelikten-çık linki (gerçek gönderimde aboneye özel üretilir).
    full = _wrap(subject, html, "https://facette.com.tr/ornek-abonelikten-cik")
    return {"html": full, "subject": subject}


def _abs_img_url(imgs, base: str) -> str:
    """Ürünün İLK geçerli görselini MUTLAK https URL'ye çevirir. Dict {url} veya string;
    data: (base64) atlanır; '//x'→https, '/x'→site kökü. Yoksa ''."""
    for im in (imgs or []):
        u = (im.get("url") if isinstance(im, dict) else im)
        u = str(u or "").strip()
        if not u or u.startswith("data:"):
            continue
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http://"):
            return "https://" + u[len("http://"):]
        if u.startswith("https://"):
            return u
        if u.startswith("/"):
            return base + u
        return f"{base}/{u.lstrip('/')}"
    return ""


@admin_router.get("/products")
async def picker_products(category: str = "", q: str = "", limit: int = 24,
                          current_user: dict = Depends(require_admin)):
    """E-posta composer ürün seçici için MİNİMAL ürün listesi. `category` = YEREL kategori id
    (category_ids/category_id ile eşleşir). Yalnız aktif+görselli ürünler; base64 YOK — ilk
    görsel MUTLAK https, ad, fiyat, satış fiyatı, slug, ürün URL'si döner (payload hafif)."""
    try:
        limit = max(1, min(int(limit or 24), 60))
    except Exception:
        limit = 24
    query: dict = {"is_active": True, "is_deleted": {"$ne": True}, "images.0": {"$exists": True}}
    ands: list = []
    _catq = str(category or "").strip()
    if _catq:
        ands.append({"$or": [{"category_ids": _catq}, {"category_id": _catq}]})
    if str(q or "").strip():
        import re as _re
        ands.append({"name": {"$regex": _re.escape(q.strip()), "$options": "i"}})
    if ands:
        query["$and"] = ands
    rows = await db.products.find(
        query, {"_id": 0, "id": 1, "name": 1, "images": 1, "slug": 1, "price": 1, "sale_price": 1},
    ).limit(limit).to_list(limit)
    base = await _site_base()
    out = []
    for p in rows:
        img = _abs_img_url(p.get("images") or [], base)
        if not img:
            continue
        slug = p.get("slug") or p.get("id")
        out.append({
            "id": p.get("id"), "name": p.get("name") or "", "image": img,
            "slug": slug, "url": f"{base}/{slug}",
            "price": p.get("price"), "sale_price": p.get("sale_price"),
        })
    return {"products": out, "total": len(out)}


# ── BREVO ABONELİKTEN ÇIKIŞ / BOUNCE WEBHOOK ─────────────────────────────────
@public_router.post("/brevo-webhook")
async def brevo_webhook(payload: dict, request: Request):
    """Brevo pazarlama olaylarını yerel rıza/suppression verisine yansıtır."""
    import hmac as _hmac
    configured = await get_brevo_config(db)
    expected = (os.environ.get("BREVO_WEBHOOK_SECRET") or configured.get("webhook_secret") or "").strip()
    given = (request.query_params.get("key") or request.headers.get("X-Webhook-Secret") or "").strip()
    if not expected or not given or not _hmac.compare_digest(expected, given):
        raise HTTPException(status_code=403, detail="forbidden")

    event = str((payload or {}).get("event") or (payload or {}).get("msg_status") or "").lower()
    email = str((payload or {}).get("email") or "").strip().lower()
    if email and event in {"unsubscribe", "unsubscribed"}:
        await db.newsletter_subscribers.update_one({"email": email}, {"$set": {
            "active": False, "unsubscribed_at": _now(), "unsubscribed_via": "brevo",
        }})
        return {"ok": True, "handled": 1, "event": event}
    if email and event in {"hard_bounce", "hardbounce", "spam", "complaint", "invalid", "blocked"}:
        reason = "complaint" if event in {"spam", "complaint"} else "bounce"
        await _suppress(email, reason, f"brevo:{event}")
        return {"ok": True, "handled": 1, "event": event}
    return {"ok": True, "handled": 0, "event": event}


# ── BREVO PAZARLAMA OLAYLARI ─────────────────────────────────────────────────
@public_router.post("/brevo-webhook")
async def brevo_webhook(payload: dict, request: Request):
    """Brevo unsubscribe/spam/kalıcı bounce olaylarını yerel rıza listesine işler."""
    import hmac as _hmac
    cfg = await get_brevo_config(db)
    expected = str(os.environ.get("BREVO_WEBHOOK_SECRET") or cfg.get("webhook_secret") or "").strip()
    given = str(request.query_params.get("key") or request.headers.get("X-Webhook-Secret") or "").strip()
    if not expected or not given or not _hmac.compare_digest(expected, given):
        raise HTTPException(status_code=403, detail="forbidden")
    event = str((payload or {}).get("event") or (payload or {}).get("msg_status") or "").lower()
    email = str((payload or {}).get("email") or (payload or {}).get("to") or "").strip().lower()
    reason_map = {
        "unsubscribe": "unsubscribe", "unsubscribed": "unsubscribe",
        "spam": "complaint", "complaint": "complaint",
        "hard_bounce": "bounce", "hardbounce": "bounce", "invalid": "bounce",
    }
    reason = reason_map.get(event)
    if reason and email:
        await _suppress(email, reason, str((payload or {}).get("reason") or (payload or {}).get("description") or ""))
        logger.info(f"[email-marketing] Brevo {event}: {email} pasifleştirildi")
        return {"ok": True, "handled": 1}
    return {"ok": True, "handled": 0}


# ── SES BOUNCE / ŞİKÂYET BİLDİRİMİ (AWS SNS webhook) ──────────────────────────
# AWS kurulumu: SES → Configuration set → Event destination → SNS topic →
#   Subscription: HTTPS → https://api.facette.com.tr/api/email-marketing/ses-webhook?key=<SECRET>
# SECRET: ortam değişkeni SES_WEBHOOK_SECRET ya da settings.email_ses.webhook_secret.
# GÜVENLİK fail-closed: secret yoksa/yanlışsa 403. (Aksi halde herkes sahte bounce
# gönderip abonelerinizi kara listeye attırabilirdi.)
@public_router.post("/ses-webhook")
async def ses_webhook(payload: dict, request: Request):
    import os as _os, hmac as _hmac, json as _json
    _secret = (_os.environ.get("SES_WEBHOOK_SECRET", "") or "").strip()
    if not _secret:
        _cfg = await db.settings.find_one({"id": "email_ses"}, {"_id": 0, "webhook_secret": 1}) or {}
        _secret = str(_cfg.get("webhook_secret") or "").strip()
    _given = (request.query_params.get("key") or request.headers.get("X-Webhook-Secret") or "").strip()
    if not _secret or not _given or not _hmac.compare_digest(_given, _secret):
        raise HTTPException(status_code=403, detail="forbidden")

    # Paylaşılan webhook anahtarı tek başına yeterli değildir: AWS'nin önerdiği
    # şekilde SNS mesaj imzasını doğrula. SigningCertURL doğrulanmadan ağ isteği
    # yapılmaz; böylece sertifika alanı SSRF aracı olarak kullanılamaz.
    _expected_topic = (_os.environ.get("SES_SNS_TOPIC_ARN", "") or "").strip()
    try:
        await verify_sns_message(payload or {}, expected_topic_arn=_expected_topic)
    except Exception:
        logger.warning("[email-marketing] geçersiz SNS imzası veya topic reddedildi")
        raise HTTPException(status_code=403, detail="invalid SNS message")

    _type = (payload or {}).get("Type") or ""

    # 1) Abonelik onayı: SNS ilk kurulumda SubscribeURL gönderir; GET ile onaylanır.
    if _type == "SubscriptionConfirmation":
        _url = (payload or {}).get("SubscribeURL") or ""
        if not validate_subscribe_url(_url, payload or {}):
            raise HTTPException(status_code=403, detail="invalid SNS confirmation URL")
        try:
            import httpx as _hx
            async with _hx.AsyncClient(timeout=20, follow_redirects=False) as _c:
                _response = await _c.get(_url)
                _response.raise_for_status()
            logger.info("[email-marketing] SNS aboneliği onaylandı")
        except Exception:
            logger.warning("[email-marketing] SNS abonelik onayı başarısız")
            raise HTTPException(status_code=502, detail="SNS confirmation failed")
        return {"ok": True}

    # 2) Bildirim: Message alanı JSON string'dir.
    msg = (payload or {}).get("Message")
    if isinstance(msg, str):
        try:
            msg = _json.loads(msg)
        except Exception:
            msg = {}
    msg = msg or {}
    kind = (msg.get("notificationType") or msg.get("eventType") or "").lower()
    handled = 0

    if kind == "bounce":
        b = msg.get("bounce") or {}
        # YALNIZ kalıcı (Permanent) bounce kara listeye alınır. Geçici (Transient — kutu
        # dolu, sunucu meşgul) adresler sağlıklıdır; onları silmek kitleyi boşuna eritir.
        _perm = (b.get("bounceType") or "").lower() == "permanent"
        for r in (b.get("bouncedRecipients") or []):
            _em = (r.get("emailAddress") or "").strip()
            if not _em:
                continue
            if _perm:
                await _suppress(_em, "bounce", f"{b.get('bounceType')}/{b.get('bounceSubType')}")
                handled += 1
    elif kind == "complaint":
        c = msg.get("complaint") or {}
        for r in (c.get("complainedRecipients") or []):
            _em = (r.get("emailAddress") or "").strip()
            if not _em:
                continue
            # Şikâyet = "spam" işareti. En ağır sinyal; şartsız kara liste.
            await _suppress(_em, "complaint", c.get("complaintFeedbackType") or "")
            handled += 1

    if handled:
        logger.info(f"[email-marketing] SES {kind}: {handled} adres kara listeye alındı")
    return {"ok": True, "type": kind, "handled": handled}


@admin_router.get("/suppressions")
async def list_suppressions(limit: int = 200, current_user: dict = Depends(require_admin)):
    """Kara liste (bounce/şikâyet) — hangi adrese neden gönderilmiyor."""
    limit = max(1, min(limit, 1000))
    rows = await db.email_suppressions.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    total = await db.email_suppressions.count_documents({})
    return {"total": total, "items": rows}


# ── Public: abonelikten çık ────────────────────────────────────────────────────
@public_router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(e: str = "", t: str = ""):
    email = (e or "").strip().lower()
    sub = None
    # DENETİM SEC-4 F17: token (t) ZORUNLU — eskiden yalnız e-posta ile herkes başkasını
    # abonelikten çıkarabiliyordu. Kampanya linkleri zaten &t=<id> içeriyor.
    if email and t:
        sub = await db.newsletter_subscribers.find_one({"email": email, "id": t})
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
