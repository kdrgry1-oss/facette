"""
İYS (İleti Yönetim Sistemi) entegrasyonu — Netgsm İş Ortağı API'si üzerinden.

Türkiye yasal zorunluluğu: B2C ticari ileti (SMS/email/arama) öncesi izin kontrolü.
İYS hizmeti Netgsm (Aracı Hizmet Sağlayıcı) üzerinden kullanılır — doğrudan
api.iys.org.tr erişimi GEREKMEZ. Netgsm hesap bilgileri (usercode/password) +
İYS Marka Kodu yeterlidir.

Netgsm İYS API (Docs: https://www.netgsm.com.tr/dokuman/#İys-adres-yükleme):
  POST https://api.netgsm.com.tr/iys/add     → izin ekleme (ONAY/RET), body.data[] toplu destekler
  POST https://api.netgsm.com.tr/iys/search  → izin sorgulama

  İstek gövdesi (JSON):
    {
      "header": {"username": "...", "password": "...", "brandCode": "..."},
      "body": {"data": [ { type, source, recipient, status, consentDate, recipientType } ]}
    }

  Yanıt:
    add    → {"code": 0, "error": false, "uid": "..."}          (0 = kuyruğa alındı)
    search → {"code": 0, "error": false, "query": {status, consentDate, source, ...}}
             {"code": 50, "error": "Kayıt Bulunamadı."}          (izin kaydı yok)

Kimlik bilgisi çözümleme sırası:
  1. Bildirim ayarları (db.settings id=notification_providers → providers.netgsm)
  2. Secrets Vault: NETGSM_USERNAME / NETGSM_PASSWORD / IYS_BRAND_CODE
  3. Ortam değişkenleri: NETGSM_USERNAME / NETGSM_PASSWORD / IYS_BRAND_CODE (veya NETGSM_BRANDCODE)

Marka kodu ayrıca admin panelinden kaydedilebilir (db.settings id=iys_settings).

Veritabanı:
  iys_permissions: { recipient, recipient_type, message_type, status, source,
                     consent_date, cached_at, expires_at, is_compliant }
"""
import asyncio
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

NETGSM_IYS_ADD_URL = "https://api.netgsm.com.tr/iys/add"
NETGSM_IYS_SEARCH_URL = "https://api.netgsm.com.tr/iys/search"

RecipientType = Literal["BIREYSEL", "TACIR"]
MessageType = Literal["MESAJ", "EPOSTA", "ARAMA"]
ConsentSource = Literal[
    "HS_FIZIKSEL_ORTAM", "HS_ISLAK_IMZA", "HS_WEB", "HS_CAGRI_MERKEZI",
    "HS_SOSYAL_MEDYA", "HS_EPOSTA", "HS_MESAJ", "HS_MOBIL", "HS_EORTAM",
    "HS_ETKINLIK", "HS_2015", "HS_ATM", "HS_KARAR",
]

# Netgsm İYS API hata kodları (https://apidocs.iys.org.tr/#tag/HATA-KODLARI + Netgsm doc)
NETGSM_IYS_ERROR_MAP = {
    "30": "Geçersiz kullanıcı adı/şifre veya API erişim izniniz yok",
    "40": "Marka kodu (brandCode) hatalı veya NetİYS aboneliğinizde tanımlı değil",
    "50": "Kayıt bulunamadı (bu adres için İYS'de izin kaydı yok)",
    "60": "İYS hesabınız aktif değil veya İYS kredisi yetersiz",
    "70": "Hatalı JSON formatı / eksik veya geçersiz parametre",
    "80": "İşlem sırasında hata oluştu, tekrar deneyin",
}


# ── Kimlik bilgileri ─────────────────────────────────────────────────────────
async def _get_credentials() -> dict:
    """Netgsm usercode/password + İYS marka kodunu çözümler.
    Sıra: bildirim ayarları → iys_settings → Secrets Vault → env."""
    username = password = brand = ""

    # 1) Bildirim sağlayıcı ayarları (Ayarlar → Bildirimler → Netgsm)
    try:
        cfg = await db.settings.find_one({"id": "notification_providers"}, {"_id": 0}) or {}
        ng = (cfg.get("providers") or {}).get("netgsm") or {}
        username = ng.get("username") or ""
        password = ng.get("password") or ""
        brand = ng.get("iys_brand_code") or ""
    except Exception:
        pass

    # 2) İYS'ye özel ayar dokümanı (admin panelinden kaydedilen marka kodu)
    try:
        iys_cfg = await db.settings.find_one({"id": "iys_settings"}, {"_id": 0}) or {}
        brand = iys_cfg.get("brand_code") or brand
    except Exception:
        pass

    # 3) Secrets Vault
    try:
        from .secrets_vault import get_secret
        username = username or (await get_secret("NETGSM_USERNAME")) or ""
        password = password or (await get_secret("NETGSM_PASSWORD")) or ""
        brand = brand or (await get_secret("IYS_BRAND_CODE")) or ""
    except Exception:
        pass

    # 4) Ortam değişkenleri
    username = username or os.environ.get("NETGSM_USERNAME", "")
    password = password or os.environ.get("NETGSM_PASSWORD", "")
    brand = brand or os.environ.get("IYS_BRAND_CODE", "") or os.environ.get("NETGSM_BRANDCODE", "")

    return {"username": username.strip(), "password": password.strip(), "brand_code": str(brand).strip()}


# ── Adres normalizasyonu ─────────────────────────────────────────────────────
def _normalize_recipient(recipient: str, message_type: str) -> str:
    """Netgsm İYS formatı: telefonlar +905XXXXXXXXX (E.164), e-postalar aynen.
    NOT: SMS gönderim API'sinden farklı olarak İYS API'si '+' işareti İSTER."""
    recipient = (recipient or "").strip()
    if message_type == "EPOSTA":
        return recipient.lower()
    digits = re.sub(r"\D", "", recipient)
    if digits.startswith("90") and len(digits) == 12:
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 11:
        return f"+9{digits}"
    if digits.startswith("5") and len(digits) == 10:
        return f"+90{digits}"
    return f"+{digits}" if digits else recipient


def _mask(recipient: str) -> str:
    if "@" in recipient:
        name, _, dom = recipient.partition("@")
        return f"{name[:2]}***@{dom}"
    return f"{recipient[:6]}****{recipient[-2:]}" if len(recipient) > 8 else "****"


# ── Netgsm İYS HTTP istemcisi ────────────────────────────────────────────────
async def _netgsm_iys_call(url: str, data_items: List[dict], creds: dict, refid: Optional[str] = None) -> dict:
    """Netgsm İYS API'sine JSON POST atar, ham yanıtı normalize eder."""
    header = {"username": creds["username"], "password": creds["password"], "brandCode": creds["brand_code"]}
    if refid:
        header["refid"] = refid
    payload = {"header": header, "body": {"data": data_items}}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(url, json=payload, headers={"Content-Type": "application/json"})
        try:
            body = r.json()
        except Exception:
            body = {"code": str(r.status_code), "error": r.text[:300]}
    code = str(body.get("code", "")).strip()
    ok = code == "0" and r.status_code == 200
    err = body.get("error")
    err_msg = None
    if not ok:
        err_msg = NETGSM_IYS_ERROR_MAP.get(code) or (err if isinstance(err, str) else None) or f"Netgsm İYS hata kodu: {code or r.status_code}"
    return {"ok": ok, "code": code, "raw": body, "error_message": err_msg, "http_status": r.status_code}


# ── Local cache (60 dk TTL) ──────────────────────────────────────────────────
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
    consent_date: Optional[str] = Field(None, description="YYYY-MM-DD HH:MM:SS — boşsa şimdi")
    refid: Optional[str] = None


class IYSSettings(BaseModel):
    brand_code: str = Field(..., min_length=1, max_length=32)


# ── Endpoints ────────────────────────────────────────────────────────────────
@router.get("/status")
async def iys_status(_=Depends(require_admin)):
    """Konfigürasyon durumu. Netgsm bilgileri + marka kodu tanımlı mı?"""
    creds = await _get_credentials()
    return {
        "provider": "netgsm",
        "configured": bool(creds["username"] and creds["password"] and creds["brand_code"]),
        "username_set": bool(creds["username"]),
        "password_set": bool(creds["password"]),
        "brand_code": creds["brand_code"] or "(eksik)",
        "add_url": NETGSM_IYS_ADD_URL,
        "search_url": NETGSM_IYS_SEARCH_URL,
        "hint": None if (creds["username"] and creds["password"] and creds["brand_code"]) else (
            "Netgsm kullanıcı adı/şifresini Ayarlar → Bildirimler → Netgsm'den, "
            "İYS Marka Kodunu bu sayfadan veya Secrets Vault'a IYS_BRAND_CODE olarak girin."
        ),
    }


@router.get("/settings")
async def iys_get_settings(_=Depends(require_admin)):
    doc = await db.settings.find_one({"id": "iys_settings"}, {"_id": 0}) or {}
    return {"brand_code": doc.get("brand_code", "")}


@router.post("/settings")
async def iys_save_settings(payload: IYSSettings, _=Depends(require_admin)):
    """İYS Marka Kodunu kaydet (Netgsm portalındaki NetİYS modülünde görünen kod)."""
    await db.settings.update_one(
        {"id": "iys_settings"},
        {"$set": {"id": "iys_settings", "brand_code": payload.brand_code.strip(),
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True, "brand_code": payload.brand_code.strip()}


@router.post("/test-connection")
async def iys_test_connection(_=Depends(require_admin)):
    """Netgsm İYS API bağlantısını gerçek bir sorgu ile test eder (dummy numara).
    'Kayıt bulunamadı' (50) yanıtı da BAŞARILI bağlantı demektir."""
    creds = await _get_credentials()
    if not (creds["username"] and creds["password"] and creds["brand_code"]):
        return {"ok": False, "message": "Eksik yapılandırma — kullanıcı adı, şifre veya marka kodu tanımlı değil"}
    try:
        res = await _netgsm_iys_call(
            NETGSM_IYS_SEARCH_URL,
            [{"type": "MESAJ", "recipient": "+905000000000", "recipientType": "BIREYSEL"}],
            creds,
        )
        if res["ok"] or res["code"] == "50":
            return {"ok": True, "message": "Netgsm İYS bağlantısı başarılı", "code": res["code"]}
        return {"ok": False, "message": res["error_message"], "code": res["code"], "raw": res["raw"]}
    except Exception as e:
        return {"ok": False, "message": f"Bağlantı hatası: {e}"}


@router.post("/query")
async def iys_query(q: IYSQuery, _=Depends(require_admin)):
    """Tek izin sorgula — önce 60 dk'lık local cache, sonra Netgsm İYS API."""
    rec = _normalize_recipient(q.recipient, q.message_type)

    cached = await _cache_get(rec, q.recipient_type, q.message_type)
    if cached:
        return {
            "source": "cache",
            "recipient": rec,
            "status": cached.get("status", "UNKNOWN"),
            "is_compliant": bool(cached.get("is_compliant")),
            "consent_source": cached.get("source"),
            "consent_date": cached.get("consent_date"),
            "cached_at": cached.get("cached_at"),
        }

    creds = await _get_credentials()
    if not (creds["username"] and creds["password"] and creds["brand_code"]):
        return {"source": "not_configured", "status": "UNKNOWN", "is_compliant": False,
                "message": "Netgsm/İYS yapılandırması eksik — /admin/iys durumunu kontrol edin"}
    try:
        res = await _netgsm_iys_call(
            NETGSM_IYS_SEARCH_URL,
            [{"type": q.message_type, "recipient": rec, "recipientType": q.recipient_type}],
            creds,
        )
        if res["ok"]:
            query = res["raw"].get("query") or {}
            if isinstance(query, list):
                query = query[0] if query else {}
            status = query.get("status", "UNKNOWN")
            await _cache_put(rec, q.recipient_type, q.message_type, status,
                             query.get("source", ""), query.get("consentDate", ""))
            logger.info(f"İYS sorgu → {_mask(rec)} [{q.message_type}] = {status}")
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
        return {"source": "error", "recipient": rec, "status": "UNKNOWN", "is_compliant": False,
                "code": res["code"], "message": res["error_message"]}
    except Exception as e:
        logger.warning(f"İYS sorgu hatası: {e}")
        return {"source": "exception", "recipient": rec, "status": "UNKNOWN",
                "is_compliant": False, "error": str(e)}


@router.post("/register")
async def iys_register(p: IYSRegister, _=Depends(require_admin)):
    """Tek izin ekle (ONAY) veya iptal et (RET) — Netgsm İYS üzerinden.
    NOT: Netgsm izni kuyruğa alır; sonuç webhook ile veya sorgu ile doğrulanır."""
    creds = await _get_credentials()
    if not (creds["username"] and creds["password"] and creds["brand_code"]):
        raise HTTPException(status_code=400, detail="Netgsm/İYS yapılandırması eksik")

    rec = _normalize_recipient(p.recipient, p.message_type)
    consent_date = p.consent_date or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    item = {
        "type": p.message_type, "source": p.source, "recipient": rec,
        "status": p.status, "consentDate": consent_date, "recipientType": p.recipient_type,
    }
    if p.refid:
        item["refid"] = p.refid
    try:
        res = await _netgsm_iys_call(NETGSM_IYS_ADD_URL, [item], creds, refid=p.refid)
        if res["ok"]:
            await _cache_put(rec, p.recipient_type, p.message_type, p.status, p.source, consent_date)
            logger.info(f"İYS kayıt → {_mask(rec)} [{p.message_type}] = {p.status}")
            return {"ok": True, "recipient": rec, "status": p.status,
                    "uid": res["raw"].get("uid"),
                    "message": "İzin Netgsm İYS kuyruğuna alındı"}
        return {"ok": False, "recipient": rec, "code": res["code"],
                "message": res["error_message"], "error_items": res["raw"].get("erroritem")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Netgsm İYS hatası: {e}")


@router.post("/register-batch")
async def iys_register_batch(items: List[IYSRegister], _=Depends(require_admin)):
    """Toplu izin ekleme — Netgsm add endpoint'i data[] dizisini doğal destekler (max 100)."""
    if not items:
        raise HTTPException(status_code=400, detail="Boş liste")
    if len(items) > 100:
        raise HTTPException(status_code=400, detail="Tek istekte max 100 kayıt")
    creds = await _get_credentials()
    if not (creds["username"] and creds["password"] and creds["brand_code"]):
        raise HTTPException(status_code=400, detail="Netgsm/İYS yapılandırması eksik")

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    data_items = []
    for p in items:
        rec = _normalize_recipient(p.recipient, p.message_type)
        data_items.append({
            "type": p.message_type, "source": p.source, "recipient": rec,
            "status": p.status, "consentDate": p.consent_date or now_str,
            "recipientType": p.recipient_type,
        })
    try:
        res = await _netgsm_iys_call(NETGSM_IYS_ADD_URL, data_items, creds)
        if res["ok"]:
            for p, d in zip(items, data_items):
                await _cache_put(d["recipient"], p.recipient_type, p.message_type,
                                 p.status, p.source, d["consentDate"])
            return {"ok": True, "count": len(items), "uid": res["raw"].get("uid"),
                    "message": f"{len(items)} izin Netgsm İYS kuyruğuna alındı"}
        return {"ok": False, "code": res["code"], "message": res["error_message"],
                "error_items": res["raw"].get("erroritem")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Netgsm İYS hatası: {e}")


@router.post("/query-batch")
async def iys_query_batch(queries: List[IYSQuery], _=Depends(require_admin)):
    """Toplu sorgulama (max 50) — pazarlama kampanyaları öncesi izin doğrulama."""
    if len(queries) > 50:
        raise HTTPException(status_code=400, detail="Max 50 sorgu")

    sem = asyncio.Semaphore(5)  # Netgsm'i boğmamak için eşzamanlılık limiti

    async def _one(q: IYSQuery):
        async with sem:
            return await iys_query(q, _=_)

    results = await asyncio.gather(*[_one(q) for q in queries], return_exceptions=True)
    out, compliant = [], 0
    for q, r in zip(queries, results):
        if isinstance(r, Exception):
            out.append({"recipient": q.recipient, "error": str(r), "is_compliant": False})
        else:
            out.append({"recipient": q.recipient, **{k: v for k, v in r.items() if k != "recipient"}})
            if r.get("is_compliant"):
                compliant += 1
    return {"total": len(queries), "compliant": compliant,
            "non_compliant": len(queries) - compliant, "items": out}
