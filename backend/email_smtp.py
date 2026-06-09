"""
email_smtp.py — E-posta gonderimi Zoho ZeptoMail HTTPS API'si (port 443) uzerinden.
Railway giden SMTP portlarini (25/465/587) engelledigi icin SMTP yerine HTTPS API kullanilir.
Fonksiyon adlari korunmustur; cagiran tum moduller degismeden calisir.

settings.id="email_smtp" alanlari (mevcut ayar sayfasiyla uyumlu):
  enabled   : bool  -> gonderim aktif mi
  username  : str   -> GONDEREN e-posta adresi (or. info@facette.com.tr)
  password  : str   -> ZeptoMail "Send Mail Token" (API anahtari)
  from_name : str   -> gonderen adi (or. FACETTE)
  host      : str   -> 'eu' iceriyorsa api.zeptomail.eu, aksi halde api.zeptomail.com
"""
import httpx


async def get_smtp_config(db) -> dict:
    return await db.settings.find_one({"id": "email_smtp"}, {"_id": 0}) or {}


def is_configured(cfg: dict) -> bool:
    return bool(cfg.get("enabled") and cfg.get("username") and cfg.get("password"))


def _endpoint(cfg: dict) -> str:
    host = (cfg.get("host") or "").lower()
    base = "https://api.zeptomail.eu" if "eu" in host else "https://api.zeptomail.com"
    return base + "/v1.1/email"


def _auth_header(token: str) -> str:
    token = (token or "").strip()
    if token.lower().startswith("zoho-enczapikey"):
        return token
    return "Zoho-enczapikey " + token


async def send_smtp_email(db, to: str, subject: str, html: str,
                          from_name=None, reply_to=None, text=None) -> dict:
    cfg = await get_smtp_config(db)
    if not is_configured(cfg):
        return {"success": False, "response": "email_not_configured"}

    sender = cfg.get("username")
    name = from_name or cfg.get("from_name") or "FACETTE"
    payload = {
        "from": {"address": sender, "name": name},
        "to": [{"email_address": {"address": to}}],
        "subject": subject or "",
        "htmlbody": html or "",
    }
    if text:
        payload["textbody"] = text
    if reply_to:
        payload["reply_to"] = [{"address": reply_to}]

    headers = {
        "Authorization": _auth_header(cfg.get("password")),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(_endpoint(cfg), headers=headers, json=payload)
        ok = r.status_code in (200, 201, 202)
        return {"success": ok, "response": (r.text or "")[:400]}
    except Exception as e:
        return {"success": False, "response": str(e)[:300]}
