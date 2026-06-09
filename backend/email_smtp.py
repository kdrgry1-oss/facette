"""
email_smtp.py — Tek noktadan SMTP (Zoho Mail) ile e-posta gönderimi.

Eski Resend (HTTPS API) yerine kurumsal SMTP kullanılır. Kimlik bilgileri
DB'de saklanır: settings.id="email_smtp"
  {
    "enabled": true,
    "host": "smtp.zoho.com",        # bölgeye göre smtp.zoho.eu olabilir
    "port": 465,                     # 465=SSL, 587=STARTTLS
    "secure": "ssl",                 # "ssl" | "tls"
    "username": "info@facette.com.tr",
    "password": "********",          # Zoho hesap/uygulama şifresi (admin'den girilir)
    "from_name": "FACETTE"
  }

ÖNEMLI: Şifre yalnızca DB'de tutulur; loglanmaz, API yanıtında maskelenir.
"""
import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr


async def get_smtp_config(db) -> dict:
    return await db.settings.find_one({"id": "email_smtp"}, {"_id": 0}) or {}


def is_configured(cfg: dict) -> bool:
    return bool(cfg.get("enabled") and cfg.get("username") and cfg.get("password"))


def _send_sync(cfg: dict, to: str, subject: str, html: str,
               from_name=None, reply_to=None, text=None):
    sender = cfg.get("username")
    name = from_name or cfg.get("from_name") or "FACETTE"
    msg = EmailMessage()
    msg["From"] = formataddr((name, sender))
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text or "Bu e-posta HTML biçimindedir. Lütfen HTML destekli bir istemcide görüntüleyin.")
    if html:
        msg.add_alternative(html, subtype="html")

    host = cfg.get("host") or "smtp.zoho.com"
    port = int(cfg.get("port") or 465)
    secure = (cfg.get("secure") or ("ssl" if port == 465 else "tls")).lower()
    ctx = ssl.create_default_context()

    if secure == "ssl" or port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=25, context=ctx) as s:
            s.login(sender, cfg.get("password") or "")
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=25) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.ehlo()
            s.login(sender, cfg.get("password") or "")
            s.send_message(msg)


async def send_smtp_email(db, to: str, subject: str, html: str,
                          from_name=None, reply_to=None, text=None) -> dict:
    """Tek alıcıya SMTP ile mail. Döner: {success, response}."""
    cfg = await get_smtp_config(db)
    if not is_configured(cfg):
        return {"success": False, "response": "smtp_not_configured"}
    try:
        await asyncio.to_thread(_send_sync, cfg, to, subject, html, from_name, reply_to, text)
        return {"success": True, "response": "sent"}
    except Exception as e:
        # Şifre/gövde loglanmaz; yalnızca hata mesajı
        return {"success": False, "response": str(e)[:300]}
