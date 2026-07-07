"""
iys.py — Ticari elektronik ileti İZNİ (İYS) + OTP doğrulama.

Akış (KVKK / İYS uyumu):
  1) Müşteri ödeme adımında "kampanya/fırsat almak istiyorum" kutusunu işaretler.
  2) SMS izni için telefonuna OTP gönderilir (POST /iys/otp/send) → müşteri kodu girer
     (POST /iys/otp/verify). Böylece numaranın gerçekten müşteriye ait olduğu doğrulanır.
  3) Sipariş oluşturulurken izin KAYIT ALTINA alınır (db.iys_consents): alıcı, kanal(lar),
     kaynak (HS_WEB), tarih, IP. Denetim izi (audit trail) yasal zorunluluktur.
  4) İzin NetGSM İYS'ye DİJİTAL olarak bildirilir (best-effort, arka planda).

Çıkış (izin iptali) yolları — müşteriye gösterilecek:
  • https://iys.org.tr üzerinden "Vatandaş Girişi" ile tüm izinlerini görüp iptal edebilir.
  • Her ticari e-postadaki "abonelikten çık" bağlantısı / her SMS'teki "RET" yönergesiyle.
  • Hesabım > Bildirim Tercihleri'nden kapatabilir (işaretsiz → İYS'ye RED bildirilir).
"""
import os
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException

from .deps import db, logger, generate_id, get_current_user
from fastapi import Depends
from notification_service import (
    _get_providers_config, SMS_IMPL, _sms_generic, normalize_phone_tr,
)

router = APIRouter(prefix="/iys", tags=["iys-consent"])

_OTP_TTL_MIN = 5
_OTP_MAX_TRY = 5


def _now():
    return datetime.now(timezone.utc)


def _gen_code() -> str:
    """6 haneli OTP — Math.random/secrets kısıtlaması yok (backend)."""
    import secrets
    return f"{secrets.randbelow(1000000):06d}"


async def _send_sms(to: str, message: str) -> dict:
    """Aktif SMS sağlayıcısıyla tekil SMS gönderir (OTP için)."""
    cfg = await _get_providers_config(db)
    providers = (cfg or {}).get("providers", {}) or {}
    sms_active = (cfg or {}).get("sms_active")
    impl = SMS_IMPL.get(sms_active, _sms_generic)
    prov_cfg = providers.get(sms_active, {}) if sms_active else {}
    try:
        return await impl(prov_cfg, to, message)
    except Exception as e:
        logger.warning(f"[iys] OTP SMS gönderilemedi: {e}")
        return {"success": False, "error": str(e)}


@router.post("/otp/send")
async def otp_send(payload: dict, request: Request):
    """Telefona OTP gönderir. body: {phone}."""
    phone = normalize_phone_tr(str((payload or {}).get("phone") or ""))
    if len(phone) < 12 or not phone.isdigit():
        raise HTTPException(status_code=400, detail="Geçerli bir telefon numarası giriniz.")
    # 1 dk mükerrer koruması
    recent = await db.otp_verifications.find_one(
        {"phone": phone, "created_at": {"$gte": (_now() - timedelta(minutes=1)).isoformat()}},
        {"_id": 0, "created_at": 1},
    )
    if recent:
        raise HTTPException(status_code=429, detail="Çok sık deneme. Lütfen 1 dakika sonra tekrar deneyin.")
    code = _gen_code()
    rec = {
        "id": generate_id(), "phone": phone, "code": code,
        "expires_at": (_now() + timedelta(minutes=_OTP_TTL_MIN)).isoformat(),
        "tries": 0, "used": False, "created_at": _now().isoformat(),
    }
    await db.otp_verifications.insert_one(rec)
    msg = f"Facette dogrulama kodunuz: {code} . Kod {_OTP_TTL_MIN} dakika gecerlidir."
    res = await _send_sms(phone, msg)
    if not res.get("success"):
        # Kod kaydı kalır; sağlayıcı hatasını müşteriye sade ver.
        return {"success": False, "detail": res.get("error") or "SMS gönderilemedi. Numaranızı kontrol edin."}
    return {"success": True, "ttl_min": _OTP_TTL_MIN}


@router.post("/otp/verify")
async def otp_verify(payload: dict):
    """OTP doğrular. body: {phone, code}. Başarılıysa {verified:true}."""
    phone = normalize_phone_tr(str((payload or {}).get("phone") or ""))
    code = str((payload or {}).get("code") or "").strip()
    rec = await db.otp_verifications.find_one(
        {"phone": phone, "used": False}, {"_id": 0}, sort=[("created_at", -1)]
    )
    if not rec:
        raise HTTPException(status_code=400, detail="Doğrulama kodu bulunamadı, yeniden gönderin.")
    try:
        exp = datetime.fromisoformat(str(rec.get("expires_at")).replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
    except Exception:
        exp = _now()
    if _now() > exp:
        raise HTTPException(status_code=400, detail="Kodun süresi doldu, yeniden gönderin.")
    if int(rec.get("tries", 0)) >= _OTP_MAX_TRY:
        raise HTTPException(status_code=429, detail="Çok fazla hatalı deneme. Yeni kod isteyin.")
    if code != rec.get("code"):
        await db.otp_verifications.update_one({"id": rec["id"]}, {"$inc": {"tries": 1}})
        raise HTTPException(status_code=400, detail="Kod hatalı.")
    await db.otp_verifications.update_one(
        {"id": rec["id"]}, {"$set": {"used": True, "verified_at": _now().isoformat()}})
    return {"verified": True, "phone": phone}


async def _phone_recently_verified(phone: str) -> bool:
    """create_order çağrısında SMS izni için OTP doğrulaması yapılmış mı (son 30 dk)."""
    p = normalize_phone_tr(str(phone or ""))
    if len(p) < 12:
        return False
    rec = await db.otp_verifications.find_one(
        {"phone": p, "used": True,
         "verified_at": {"$gte": (_now() - timedelta(minutes=30)).isoformat()}},
        {"_id": 0, "id": 1},
    )
    return bool(rec)


async def _iys_config() -> dict:
    """NetGSM İYS bilgileri — providers_config veya settings'ten. Eksikse rapor ertelenir."""
    doc = await db.settings.find_one({"id": "notification_providers"}, {"_id": 0}) or {}
    prov = (doc.get("providers", {}) or {}).get("netgsm", {}) or {}
    return {
        "username": prov.get("username") or os.environ.get("NETGSM_USERCODE", ""),
        "password": prov.get("password") or os.environ.get("NETGSM_PASSWORD", ""),
        "iys_code": prov.get("iys_code") or os.environ.get("NETGSM_IYS_CODE", ""),
        "brand_code": prov.get("iys_brand_code") or os.environ.get("NETGSM_IYS_BRAND_CODE", ""),
    }


async def _report_to_netgsm_iys(consent: dict):
    """İzin/RED kaydını RESMÎ İYS API'sine (api.iys.org.tr) dijital bildirir (best-effort).

    NOT: Önceki sürüm NetGSM'in placeholder ucuna (/iys/v2/consent/add) gidiyordu ve 404
    alıyordu. Artık İYS'nin resmî API'si kullanılır (iys_integration.add_consent_official) —
    IYS_API_USERNAME/PASSWORD (OAuth token) + IYS_BRAND_CODE gerekir. Her kanal (MESAJ/EPOSTA)
    ayrı izin olarak eklenir; en az biri başarılıysa reported=True."""
    from .iys_integration import add_consent_official
    channels = consent.get("channels", []) or []
    if not channels:
        return False
    email = (consent.get("email") or "").strip()
    phone = (consent.get("phone") or "").strip()
    # İYS telefon biçimi: +90XXXXXXXXXX
    if phone and not phone.startswith("+"):
        digits = phone.lstrip("0")
        phone = "+" + (digits if digits.startswith("90") else "90" + digits)
    status = consent.get("status", "ONAY")
    source = consent.get("source", "HS_WEB")
    cd = (consent.get("consent_date") or _now().isoformat()).replace("T", " ")[:19]
    any_ok, last = False, {}
    for ch in channels:
        recipient = phone if ch == "MESAJ" else email
        if not recipient:
            continue
        res = await add_consent_official(recipient, "BIREYSEL", ch, status, source, cd)
        last = res
        if res.get("ok"):
            any_ok = True
    await db.iys_consents.update_one(
        {"id": consent["id"]},
        {"$set": {"reported": any_ok, "report_status_code": last.get("status"),
                  "report_response": (last.get("body") or last.get("detail") or "")[:500],
                  "reported_at": _now().isoformat()}},
    )
    if not any_ok:
        logger.warning(f"[iys] resmî İYS bildirimi başarısız: {last}")
    return any_ok


@router.post("/consent/update")
async def consent_update(payload: dict, current_user: dict = Depends(get_current_user)):
    """Üye Hesabım > Pazarlama Tercihleri: e-posta/SMS iznini AÇ/KAPA. Kapatınca İYS'ye RED
    (RET), açınca ONAY bildirilir. Denetim izi + dijital bildirim record_consent ile yapılır."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmanız gerekiyor")
    email_on = bool((payload or {}).get("email"))
    sms_on = bool((payload or {}).get("sms"))
    email = current_user.get("email") or ""
    phone = current_user.get("phone") or ""
    if email:
        await record_consent(email, phone, ["EPOSTA"],
                             status="ONAY" if email_on else "RET",
                             source="HS_WEB", user_id=current_user.get("id"))
    if phone:
        await record_consent(email, phone, ["MESAJ"],
                             status="ONAY" if sms_on else "RET",
                             source="HS_WEB", user_id=current_user.get("id"))
    await db.users.update_one(
        {"id": current_user.get("id")},
        {"$set": {"accepts_marketing": bool(email_on or sms_on),
                  "marketing_prefs": {"email": email_on, "sms": sms_on},
                  "marketing_consent_at": _now().isoformat()}})
    return {"success": True, "email": email_on, "sms": sms_on}


async def record_consent(recipient_email: str, recipient_phone: str, channels: list,
                         status: str = "ONAY", source: str = "HS_WEB",
                         ip: str = "", order_id: str = "", user_id: str = None) -> dict:
    """İzin/RED kaydını db.iys_consents'e yazar ve NetGSM İYS'ye bildirir (best-effort).
    channels: ["MESAJ","EPOSTA"] alt kümesi. Denetim izi + dijital bildirim tek yerde."""
    channels = [c for c in (channels or []) if c in ("MESAJ", "EPOSTA")]
    if not channels:
        return {"recorded": False, "reason": "kanal yok"}
    rec = {
        "id": generate_id(),
        "email": (recipient_email or "").strip().lower(),
        "phone": normalize_phone_tr(recipient_phone or ""),
        "channels": channels, "status": status, "source": source,
        "ip": ip, "order_id": order_id, "user_id": user_id,
        "consent_date": _now().isoformat(),
        "reported": False, "created_at": _now().isoformat(),
    }
    await db.iys_consents.insert_one({**rec})
    try:
        await _report_to_netgsm_iys(rec)
    except Exception as e:
        logger.warning(f"[iys] rapor spawn hata: {e}")
    return {"recorded": True, "id": rec["id"]}


def _admin_or_403(current_user):
    if not (current_user and current_user.get("is_admin")):
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")


@router.get("/diagnostics")
async def iys_diagnostics(order_number: str = "", limit: int = 20,
                          current_user: dict = Depends(get_current_user)):
    """SALT-OKUNUR teşhis: NetGSM İYS kimlik bilgileri dolu mu + son izin kayıtlarının
    BİLDİRİM durumu (reported / HTTP kodu / NetGSM yanıtı). 'İYS'ye düşmedi' sorununun tam
    sebebini gösterir (kimlik eksik mi, NetGSM reddetti mi, kanal yok mu)."""
    _admin_or_403(current_user)
    # Resmî İYS API (api.iys.org.tr) kimlik durumu — bildirim ARTIK bunu kullanır.
    try:
        from .iys_integration import official_iys_config_present
        present = official_iys_config_present()
    except Exception as _e:
        present = {"error": str(_e)}
    q = {}
    ord_info = None
    if order_number:
        o = await db.orders.find_one(
            {"order_number": order_number},
            {"_id": 0, "id": 1, "marketing_consent": 1, "shipping_address": 1})
        if o:
            q["order_id"] = o["id"]
            ord_info = {"order_number": order_number,
                        "marketing_consent": o.get("marketing_consent"),
                        "phone": (o.get("shipping_address") or {}).get("phone"),
                        "email": (o.get("shipping_address") or {}).get("email")}
    recs = await db.iys_consents.find(q, {"_id": 0}).sort("created_at", -1)\
        .limit(max(1, min(int(limit or 20), 100))).to_list(None)
    return {
        "config_present": present,
        "all_credentials_ok": all(present.values()),
        "netgsm_url": os.environ.get("NETGSM_IYS_URL", "https://api.netgsm.com.tr/iys/v2/consent/add"),
        "order": ord_info,
        "consent_count": len(recs),
        "consents": [{
            "order_id": r.get("order_id"), "channels": r.get("channels"), "status": r.get("status"),
            "email": r.get("email"), "phone": r.get("phone"),
            "reported": r.get("reported"), "report_status_code": r.get("report_status_code"),
            "report_response": (r.get("report_response") or "")[:400],
            "consent_date": r.get("consent_date"), "reported_at": r.get("reported_at"),
        } for r in recs],
    }


@router.post("/retry")
async def iys_retry_report(payload: dict, current_user: dict = Depends(get_current_user)):
    """Kimlik bilgileri düzeltildikten sonra bildirilmemiş izinleri NetGSM İYS'ye YENİDEN
    bildirir. payload: {order_number?} verilirse o siparişin izinleri; yoksa bildirilmemiş
    (reported=false) son 100 izin denenir."""
    _admin_or_403(current_user)
    onum = str((payload or {}).get("order_number") or "").strip()
    if onum:
        o = await db.orders.find_one({"order_number": onum}, {"_id": 0, "id": 1})
        q = {"order_id": o["id"]} if o else {"order_id": "__none__"}
    else:
        q = {"reported": {"$ne": True}}
    recs = await db.iys_consents.find(q, {"_id": 0}).sort("created_at", -1).limit(100).to_list(None)
    results = []
    for r in recs:
        ok = await _report_to_netgsm_iys(r)
        results.append({"id": r.get("id"), "channels": r.get("channels"), "reported": bool(ok)})
    return {"retried": len(results), "ok": sum(1 for x in results if x["reported"]), "results": results[:50]}
