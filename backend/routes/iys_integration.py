"""
iys_integration.py — Admin İYS modülü (sorgu/durum/ayar) — NetGSM İş Ortağı üzerinden.

Facette'in İYS aracı hizmet sağlayıcısı NetGSM'dir; bu modül DOĞRUDAN devlet
İYS'sine (api.iys.org.tr) GİTMEZ. Kimlik/marka bilgileri routes/iys.py'deki
_iys_config() ile AYNI kaynaktan (providers.netgsm) okunur — tek kanal, tek config.

Sorumluluk ayrımı:
  • routes/iys.py         → müşteri akışı: OTP, checkout izni, İYS'ye bildirim (add)
  • routes/iys_integration → admin akışı: izin SORGULAMA (search), durum, ayar, toplu kontrol
    İzin EKLEME admin panelden de yapılabilir; iys.py'deki record_consent'e delege edilir
    (denetim izi + NetGSM bildirimi tek yerden — çift gönderim yok).

NetGSM İYS Sorgu API (Docs: https://www.netgsm.com.tr/dokuman/#İys):
  POST https://api.netgsm.com.tr/iys/search
  Gövde: {"header": {username, password, brandCode}, "body": {"data": [{type, recipient, recipientType}]}}
  KRİTİK (canlıda doğrulandı, bkz. iys.py): gövdedeki header'a EK olarak HTTP Basic Auth
  şart — yoksa NetGSM code 40 ("iys modulunuzu aktiflestirin") döner. appkey varsa
  data öğesine eklenir (NetGSM resmî n8n entegrasyonuyla birebir).
  Yanıt: {"code":0,"query":{status,consentDate,source,...}} | {"code":50,"error":"Kayıt Bulunamadı."}

Veritabanı:
  iys_permissions (sorgu cache'i, 60 dk TTL): { recipient, recipient_type, message_type,
      status, source, consent_date, cached_at, expires_at, is_compliant }
"""
import asyncio
import base64
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import List, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .deps import db, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/iys", tags=["iys"])

NETGSM_IYS_SEARCH_URL = os.environ.get("NETGSM_IYS_SEARCH_URL") or "https://api.netgsm.com.tr/iys/search"

RecipientType = Literal["BIREYSEL", "TACIR"]
MessageType = Literal["MESAJ", "EPOSTA", "ARAMA"]
# İYS'nin kabul ettiği izin kaynakları — "ADMIN_PANEL" GEÇERSİZDİR (NetGSM code 70 döner).
ConsentSource = Literal[
    "HS_FIZIKSEL_ORTAM", "HS_ISLAK_IMZA", "HS_WEB", "HS_CAGRI_MERKEZI",
    "HS_SOSYAL_MEDYA", "HS_EPOSTA", "HS_MESAJ", "HS_MOBIL", "HS_EORTAM",
    "HS_ETKINLIK", "HS_2015", "HS_ATM", "HS_KARAR",
]

NETGSM_IYS_ERROR_MAP = {
    "30": "Geçersiz NetGSM kullanıcı adı/şifre veya API erişim izni yok",
    "40": "NetİYS modülü aktif değil veya istek reddedildi — NetGSM portalından NetİYS modülünün "
          "ve API alt kullanıcısında Dijital Servis yetkisinin açık olduğunu kontrol edin",
    "50": "Kayıt bulunamadı (bu adres için İYS'de izin kaydı yok)",
    "60": "İYS hesabı aktif değil veya İYS kredisi yetersiz",
    "70": "Hatalı JSON formatı / eksik ya da geçersiz parametre",
    "80": "İşlem sırasında hata oluştu, tekrar deneyin",
}


async def _creds() -> dict:
    """NetGSM İYS kimlik bilgileri — iys.py ile TEK kaynak (providers.netgsm + env)."""
    from .iys import _iys_config
    cfg = await _iys_config()
    return {
        "username": (cfg.get("username") or "").strip(),
        "password": (cfg.get("password") or "").strip(),
        "appkey": (cfg.get("appkey") or "").strip(),
        "brand_code": (cfg.get("brand_code") or cfg.get("iys_code") or "").strip(),
    }


def _normalize_recipient(recipient: str, message_type: str) -> str:
    """NetGSM İYS biçimi: telefon +90XXXXXXXXXX, e-posta küçük harf (iys.py ile aynı kural)."""
    recipient = (recipient or "").strip()
    if message_type == "EPOSTA":
        return recipient.lower()
    digits = re.sub(r"\D", "", recipient)
    if digits.startswith("90") and len(digits) == 12:
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 11:
        return f"+9{digits}"
    if len(digits) == 10 and digits.startswith("5"):
        return f"+90{digits}"
    return f"+{digits}" if digits else recipient


def _mask(recipient: str) -> str:
    if "@" in recipient:
        name, _, dom = recipient.partition("@")
        return f"{name[:2]}***@{dom}"
    return f"{recipient[:6]}****{recipient[-2:]}" if len(recipient) > 8 else "****"


async def _netgsm_search(items: List[dict], creds: dict, mode: str = "basic") -> dict:
    """NetGSM /iys/search — gövde header'ı + HTTP Basic Auth (iys.py'de kanıtlanan şart).
    DİKKAT: resmî SDK'da (netgsm/netiys) search data öğesi TAM 3 alandır
    (type, recipient, recipientType) — add'den farklı olarak appkey EKLENMEZ,
    fazladan alan istek reddine yol açabilir.

    mode — NetGSM hesap yapılandırmasına göre değişebildiği için test-connection
    çalışan biçimi bulur ve providers.netgsm.iys_search_mode'a kaydeder:
      "basic"        → HTTP Basic Auth + sade data (varsayılan; add ucunda kanıtlı)
      "plain"        → yalnız gövde header'ı (resmî SDK ile birebir)
      "basic_appkey" → Basic Auth + data öğesinde appkey"""
    base = [{"type": it["type"], "recipient": it["recipient"],
             "recipientType": it.get("recipientType", "BIREYSEL")} for it in items]
    if mode == "basic_appkey" and creds["appkey"]:
        base = [{**it, "appkey": creds["appkey"]} for it in base]
    payload = {
        "header": {"username": creds["username"], "password": creds["password"],
                   "brandCode": creds["brand_code"]},
        "body": {"data": base},
    }
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if mode != "plain":
        auth = base64.b64encode(f"{creds['username']}:{creds['password']}".encode()).decode()
        headers["Authorization"] = "Basic " + auth
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
        r = await c.post(NETGSM_IYS_SEARCH_URL, json=payload, headers=headers)
    try:
        body = r.json()
    except Exception:
        body = {"code": str(r.status_code), "error": (r.text or "")[:300]}
    code = str(body.get("code", "")).strip()
    ok = code in ("0", "00") and r.status_code == 200
    err_msg = None
    if not ok:
        err = body.get("error")
        err_msg = NETGSM_IYS_ERROR_MAP.get(code) or (err if isinstance(err, str) else None) \
            or f"NetGSM İYS hata kodu: {code or r.status_code}"
    return {"ok": ok, "code": code, "raw": body, "error_message": err_msg,
            "http_status": r.status_code}


# ── Sorgu cache'i (60 dk) ────────────────────────────────────────────────────
async def _cache_get(rec: str, rtype: str, mtype: str) -> Optional[dict]:
    doc = await db.iys_permissions.find_one(
        {"recipient": rec, "recipient_type": rtype, "message_type": mtype},
        {"_id": 0},
    )
    if doc and doc.get("expires_at", "") > datetime.now(timezone.utc).isoformat():
        return doc
    return None


async def _cache_put(rec: str, rtype: str, mtype: str, status: str,
                     source: str = "", consent_date: str = "", ttl_minutes: int = 60):
    now = datetime.now(timezone.utc)
    await db.iys_permissions.update_one(
        {"recipient": rec, "recipient_type": rtype, "message_type": mtype},
        {"$set": {
            "recipient": rec, "recipient_type": rtype, "message_type": mtype,
            "status": status, "source": source, "consent_date": consent_date,
            "cached_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=ttl_minutes)).isoformat(),
            "is_compliant": status == "ONAY",
        }},
        upsert=True,
    )


# ── Models ───────────────────────────────────────────────────────────────────
class IYSQuery(BaseModel):
    recipient: str
    recipient_type: RecipientType = "BIREYSEL"
    message_type: MessageType = "MESAJ"


class IYSRegister(IYSQuery):
    status: Literal["ONAY", "RET"] = "ONAY"
    source: ConsentSource = "HS_WEB"


class IYSSettings(BaseModel):
    brand_code: str = Field(..., min_length=1, max_length=32)
    appkey: Optional[str] = Field(None, max_length=128)


# ── Endpoints ────────────────────────────────────────────────────────────────
@router.get("/status")
async def iys_status(_=Depends(require_admin)):
    """Konfigürasyon durumu — NetGSM kimlik + İYS marka kodu tanımlı mı?"""
    c = await _creds()
    configured = bool(c["username"] and c["password"] and c["brand_code"])
    return {
        "provider": "netgsm",
        "configured": configured,
        "username_set": bool(c["username"]),
        "password_set": bool(c["password"]),
        "appkey_set": bool(c["appkey"]),
        "brand_code": c["brand_code"] or "(eksik)",
        "search_url": NETGSM_IYS_SEARCH_URL,
        "hint": None if configured else (
            "NetGSM kullanıcı adı/şifresi Ayarlar → Bildirimler → Netgsm'den okunur. "
            "İYS Marka Kodunu bu sayfadan kaydedin (aynı netgsm bloğuna yazılır)."
        ),
    }


@router.get("/settings")
async def iys_get_settings(_=Depends(require_admin)):
    doc = await db.settings.find_one({"id": "notification_providers"}, {"_id": 0}) or {}
    ng = (doc.get("providers") or {}).get("netgsm") or {}
    return {"brand_code": ng.get("iys_brand_code") or ng.get("brand_code") or "",
            "appkey": ng.get("appkey") or ""}


@router.post("/settings")
async def iys_save_settings(payload: IYSSettings, _=Depends(require_admin)):
    """İYS Marka Kodu (+ opsiyonel appkey) — providers.netgsm bloğuna yazılır.
    Böylece hem bu modül hem checkout bildirimi (routes/iys.py) AYNI yerden okur."""
    upd = {"providers.netgsm.iys_brand_code": payload.brand_code.strip()}
    if payload.appkey is not None:
        upd["providers.netgsm.appkey"] = payload.appkey.strip()
    await db.settings.update_one(
        {"id": "notification_providers"},
        {"$set": {"id": "notification_providers", **upd}},
        upsert=True,
    )
    return {"ok": True, "brand_code": payload.brand_code.strip()}


async def _get_search_mode() -> str:
    doc = await db.settings.find_one({"id": "notification_providers"}, {"_id": 0}) or {}
    return ((doc.get("providers") or {}).get("netgsm") or {}).get("iys_search_mode") or "basic"


@router.post("/test-connection")
async def iys_test_connection(_=Depends(require_admin)):
    """NetGSM İYS bağlantısını test eder ve ÇALIŞAN istek biçimini otomatik bulur.
    Üç biçim sırayla denenir (basic → plain → basic_appkey); başarılı olan
    providers.netgsm.iys_search_mode'a kaydedilir, sorgular hep onu kullanır.
    'Kayıt bulunamadı' (50) yanıtı da BAŞARILI bağlantı demektir."""
    c = await _creds()
    if not (c["username"] and c["password"] and c["brand_code"]):
        return {"ok": False, "message": "Eksik yapılandırma — NetGSM kullanıcı/şifre veya marka kodu tanımlı değil"}
    probe = [{"type": "MESAJ", "recipient": "+905301234567", "recipientType": "BIREYSEL"}]
    attempts = []
    for mode in ("basic", "plain", "basic_appkey"):
        try:
            res = await _netgsm_search(probe, c, mode=mode)
        except Exception as e:
            attempts.append({"mode": mode, "error": str(e)[:200]})
            continue
        attempts.append({"mode": mode, "code": res["code"],
                         "http_status": res["http_status"],
                         "raw": res["raw"] if not (res["ok"] or res["code"] == "50") else None})
        if res["ok"] or res["code"] == "50":
            await db.settings.update_one(
                {"id": "notification_providers"},
                {"$set": {"providers.netgsm.iys_search_mode": mode}}, upsert=True)
            return {"ok": True, "code": res["code"], "mode": mode,
                    "message": f"NetGSM İYS bağlantısı başarılı (istek biçimi: {mode})"}
    last = attempts[-1] if attempts else {}
    return {"ok": False,
            "message": NETGSM_IYS_ERROR_MAP.get(str(last.get("code")),
                       "Hiçbir istek biçimi kabul edilmedi") + " — detay için 'attempts' alanına bakın",
            "attempts": attempts}


@router.post("/query")
async def iys_query(q: IYSQuery, _=Depends(require_admin)):
    """Tek izin sorgula — önce 60 dk cache, sonra NetGSM /iys/search."""
    rec = _normalize_recipient(q.recipient, q.message_type)

    cached = await _cache_get(rec, q.recipient_type, q.message_type)
    if cached:
        return {
            "source": "cache", "recipient": rec,
            "status": cached.get("status", "UNKNOWN"),
            "is_compliant": bool(cached.get("is_compliant")),
            "consent_source": cached.get("source"),
            "consent_date": cached.get("consent_date"),
            "cached_at": cached.get("cached_at"),
        }

    c = await _creds()
    if not (c["username"] and c["password"] and c["brand_code"]):
        return {"source": "not_configured", "recipient": rec, "status": "UNKNOWN",
                "is_compliant": False,
                "message": "NetGSM/İYS yapılandırması eksik — /admin/iys sayfasındaki durumu kontrol edin"}
    try:
        res = await _netgsm_search(
            [{"type": q.message_type, "recipient": rec, "recipientType": q.recipient_type}],
            c, mode=await _get_search_mode())
        if res["ok"]:
            query = res["raw"].get("query") or {}
            if isinstance(query, list):
                query = query[0] if query else {}
            status = query.get("status", "UNKNOWN")
            await _cache_put(rec, q.recipient_type, q.message_type, status,
                             query.get("source", ""), query.get("consentDate", ""))
            logger.info(f"[iys] sorgu {_mask(rec)} [{q.message_type}] = {status}")
            return {"source": "api", "recipient": rec, "status": status,
                    "is_compliant": status == "ONAY",
                    "consent_source": query.get("source"),
                    "consent_date": query.get("consentDate"),
                    "creation_date": query.get("creationDate"),
                    "transaction_id": query.get("transactionId")}
        if res["code"] == "50":
            # Kayıt yok = izin verilmemiş → ticari ileti GÖNDERİLEMEZ
            await _cache_put(rec, q.recipient_type, q.message_type, "KAYIT_YOK")
            return {"source": "api", "recipient": rec, "status": "KAYIT_YOK",
                    "is_compliant": False,
                    "message": "İYS'de bu adres için izin kaydı bulunamadı"}
        return {"source": "error", "recipient": rec, "status": "UNKNOWN",
                "is_compliant": False, "code": res["code"], "message": res["error_message"]}
    except Exception as e:
        logger.warning(f"[iys] sorgu hatası: {e}")
        return {"source": "exception", "recipient": rec, "status": "UNKNOWN",
                "is_compliant": False, "error": str(e)}


@router.post("/register")
async def iys_register(p: IYSRegister, _=Depends(require_admin)):
    """İzin ekle/iptal — checkout ile AYNI NetGSM yolu (record_consent → /iys/add).
    Tek kanal: denetim izi (iys_consents) + Basic Auth'lu bildirim tek yerden yapılır.
    NOT: source HS_* değerlerinden biri OLMALIDIR (ADMIN_PANEL geçersizdir — İYS reddeder)."""
    if p.message_type == "ARAMA":
        raise HTTPException(
            status_code=400,
            detail="ARAMA izinleri şu an panelden eklenemiyor — İYS web portalı üzerinden yönetin. "
                   "(SMS ve E-Posta izinleri buradan eklenebilir.)")
    from .iys import record_consent
    rec = _normalize_recipient(p.recipient, p.message_type)
    is_email = p.message_type == "EPOSTA"
    res = await record_consent(
        recipient_email=rec if is_email else "",
        recipient_phone="" if is_email else rec,
        channels=[p.message_type],
        status=p.status,
        source=p.source,
    )
    await _cache_put(rec, p.recipient_type, p.message_type, p.status, p.source)
    return {"ok": bool(res.get("recorded")), "via": "netgsm", "recipient": rec, **res}


@router.post("/query-batch")
async def iys_query_batch(queries: List[IYSQuery], _=Depends(require_admin)):
    """Toplu sorgulama (max 50) — pazarlama kampanyaları öncesi izin doğrulama."""
    if len(queries) > 50:
        raise HTTPException(status_code=400, detail="Max 50 sorgu")

    sem = asyncio.Semaphore(5)  # NetGSM'i boğmamak için eşzamanlılık limiti

    async def _one(q: IYSQuery):
        async with sem:
            return await iys_query(q, _=_)

    results = await asyncio.gather(*[_one(q) for q in queries], return_exceptions=True)
    out, compliant = [], 0
    for q, r in zip(queries, results):
        if isinstance(r, Exception):
            out.append({"recipient": q.recipient, "error": str(r), "is_compliant": False})
        else:
            out.append({"recipient": q.recipient,
                        **{k: v for k, v in r.items() if k != "recipient"}})
            if r.get("is_compliant"):
                compliant += 1
    return {"total": len(queries), "compliant": compliant,
            "non_compliant": len(queries) - compliant, "items": out}
