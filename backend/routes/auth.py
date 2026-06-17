"""
Authentication routes - Login, Register, Google OAuth
"""
from fastapi import APIRouter, HTTPException, Query, Request, Depends
from datetime import datetime, timezone
import uuid
import os

from .deps import (
    db, logger, hash_password, verify_password, 
    create_token, get_current_user, generate_id,
    safe_str, is_safe_email, write_audit_log,
    is_account_locked, register_failed_login, reset_failed_login,
    is_ip_blocked, register_failed_login_ip,
    client_ip_from_request, limiter,
    validate_strong_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "") or "49503095707-cahr1ntbc30lqeho6nj1pbggq3tatien.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

@router.post("/register")
@(limiter.limit("5/minute") if limiter else (lambda f: f))
async def register(
    request: Request,
    email: str = Query(...),
    password: str = Query(...),
    first_name: str = Query(None),
    last_name: str = Query(None),
    phone: str = Query(None)
):
    """Register new user"""
    email = safe_str(email, 256).lower().strip()
    password = safe_str(password, 200)
    if not is_safe_email(email):
        raise HTTPException(status_code=400, detail="Geçersiz e-posta adresi")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Şifre en az 6 karakter olmalı")

    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Bu e-posta zaten kayıtlı")

    # Telefon: normalize + mukerrer kontrol (ayni cep no ile ikinci hesap acilamaz)
    from notification_service import normalize_phone_tr
    phone_norm = normalize_phone_tr(safe_str(phone, 32) or "") if phone else ""
    _last10 = phone_norm[-10:]
    if len(_last10) == 10 and _last10.isdigit():
        dup_phone = await db.users.find_one({"phone": {"$regex": _last10}}, {"_id": 0, "id": 1})
        if dup_phone:
            raise HTTPException(status_code=400, detail="Bu telefon numarası zaten kayıtlı")

    user = {
        "id": generate_id(),
        "email": email,
        "password": hash_password(password),
        "first_name": safe_str(first_name, 100) or "",
        "last_name": safe_str(last_name, 100) or "",
        "phone": phone_norm,
        "is_admin": False,
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.users.insert_one(user)
    token = create_token(user["id"])
    # Hoş geldin e-postası (best-effort; kaydı asla bloklamaz)
    try:
        import os as _os
        from notification_service import send_notification
        await send_notification(
            db, "welcome",
            to_email=email,
            variables={
                "customer_name": (user.get("first_name") or "").strip() or "değerli müşterimiz",
                "site_url": _os.environ.get("SITE_URL", "https://facette.com.tr").rstrip("/"),
            },
            channels=["email"],
        )
    except Exception as _e:
        logger.warning(f"welcome email failed for {email}: {_e}")
    await write_audit_log(
        "register", user_id=user["id"], email=email,
        ip=client_ip_from_request(request),
        user_agent=request.headers.get("user-agent"),
        success=True,
    )

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "is_admin": user["is_admin"]
        }
    }

@router.post("/login")
@(limiter.limit("10/minute") if limiter else (lambda f: f))
async def login(
    request: Request,
    email: str = Query(...),
    password: str = Query(...)
):
    """Login with email and password (rate-limited + lockout-protected)."""
    email = safe_str(email, 256).lower().strip()
    password = safe_str(password, 200)
    ip = client_ip_from_request(request)
    ua = request.headers.get("user-agent")

    if not is_safe_email(email):
        await write_audit_log("login", email=email, ip=ip, user_agent=ua,
                              success=False, meta={"reason": "invalid_email_format"})
        raise HTTPException(status_code=400, detail="Geçersiz e-posta veya şifre")

    # IP-level brute force blocklist (account lockout'tan önce kontrol — saldırı için DoS bypass)
    ip_blocked, ip_retry = await is_ip_blocked(ip)
    if ip_blocked:
        await write_audit_log("login", email=email, ip=ip, user_agent=ua,
                              success=False, meta={"reason": "ip_blocked", "retry_after": ip_retry})
        msg = "Bu IP adresinden çok fazla başarısız deneme yapıldı."
        if ip_retry > 0:
            msg += f" {max(1, ip_retry // 3600)} saat sonra tekrar deneyin."
        raise HTTPException(status_code=429, detail=msg)

    locked, retry_after = await is_account_locked(email)
    if locked:
        await write_audit_log("login", email=email, ip=ip, user_agent=ua,
                              success=False, meta={"reason": "locked", "retry_after": retry_after})
        raise HTTPException(status_code=429,
                            detail=f"Çok fazla başarısız deneme. {retry_after // 60 + 1} dk sonra tekrar deneyin.")

    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(password, user.get("password", "")):
        await register_failed_login(email)
        # IP-level threshold de tetiklensin
        await register_failed_login_ip(ip)
        await write_audit_log("login", email=email, ip=ip, user_agent=ua,
                              success=False, meta={"reason": "bad_credentials"})
        raise HTTPException(status_code=401, detail="Geçersiz e-posta veya şifre")

    if not user.get("is_active", True):
        await write_audit_log("login", user_id=user["id"], email=email,
                              ip=ip, user_agent=ua, success=False,
                              meta={"reason": "inactive"})
        raise HTTPException(status_code=403, detail="Hesabınız devre dışı")

    await reset_failed_login(email)

    # MFA aktifse: tam token verme, ikinci adım iste
    if user.get("mfa_enabled"):
        from .mfa import create_mfa_pending_token
        await write_audit_log("login_mfa_challenge", user_id=user["id"], email=email,
                              ip=ip, user_agent=ua, success=True)
        return {
            "mfa_required": True,
            "mfa_token": create_mfa_pending_token(user["id"]),
        }

    token = create_token(user["id"], user.get("is_admin", False))
    await write_audit_log("login", user_id=user["id"], email=email,
                          ip=ip, user_agent=ua, success=True)

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "phone": user.get("phone", ""),
            "is_admin": user.get("is_admin", False),
            "created_at": user.get("created_at")
        }
    }

@router.post("/convert-guest-order")
async def convert_guest_order(payload: dict):
    """Checkout sonrası guest sipariş veren kullanıcı için hızlı hesap oluşturma.
    payload: {order_id: str, password: str}
    Sipariş bilgilerinden email + first_name + last_name otomatik alınır.
    Eğer email'de mevcut kullanıcı varsa hesap oluşturulmaz, sadece sipariş bağlanır.
    """
    order_id = (payload or {}).get("order_id", "").strip()
    password = (payload or {}).get("password", "")
    if not order_id:
        raise HTTPException(status_code=400, detail="order_id gerekli")
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="Şifre en az 6 karakter olmalı")

    order = await db.orders.find_one({"$or": [{"id": order_id}, {"order_number": order_id}]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    if order.get("user_id"):
        raise HTTPException(status_code=400, detail="Bu sipariş zaten bir hesaba bağlı")

    addr = order.get("shipping_address") or {}
    email = (addr.get("email") or order.get("email") or "").lower().strip()
    first_name = addr.get("first_name") or addr.get("full_name", "").split(" ")[0] or ""
    last_name = addr.get("last_name") or ""
    phone = addr.get("phone") or order.get("phone") or ""
    if not email:
        raise HTTPException(status_code=400, detail="Sipariş e-postası bulunamadı")

    from notification_service import normalize_phone_tr
    phone_norm = normalize_phone_tr(phone) if phone else ""
    _last10 = phone_norm[-10:]

    async def _save_guest_address(uid, _order):
        try:
            a = _order.get("shipping_address") or {}
            if not (a.get("address") and a.get("city")):
                return
            dup = await db.addresses.find_one(
                {"user_id": uid, "address": a.get("address", ""),
                 "city": a.get("city", ""), "district": a.get("district", "")},
                {"_id": 0, "id": 1})
            if dup:
                return
            has_any = await db.addresses.find_one({"user_id": uid}, {"_id": 0, "id": 1})
            await db.addresses.insert_one({
                "id": generate_id(), "user_id": uid,
                "title": a.get("title") or "Teslimat Adresi",
                "first_name": a.get("first_name", ""), "last_name": a.get("last_name", ""),
                "phone": a.get("phone", ""), "address": a.get("address", ""),
                "city": a.get("city", ""), "district": a.get("district", ""),
                "postal_code": a.get("postal_code", ""),
                "is_default": not bool(has_any),
                "is_corporate": False, "company_name": "", "tax_no": "", "tax_office": "",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as _e:
            logger.warning(f"convert-guest adres kaydi atlandi: {_e}")

    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
    if not existing and len(_last10) == 10 and _last10.isdigit():
        # Ayni cep no baska bir hesaba aitse mukerrer uyelik acma — o hesaba bagla
        existing = await db.users.find_one({"phone": {"$regex": _last10}}, {"_id": 0, "id": 1})

    if existing:
        # Var olan hesaba bagla (mukerrer hesap olusturma)
        user_id = existing["id"]
        await db.orders.update_one({"id": order["id"]}, {"$set": {"user_id": user_id}})
        await _save_guest_address(user_id, order)
        from .deps import create_token as _ct
        token = _ct(user_id, is_admin=False)
        return {"token": token, "existing_account": True, "message": "Sipariş mevcut hesabınıza bağlandı"}

    # Yeni hesap oluştur
    user = {
        "id": generate_id(),
        "email": email,
        "password": hash_password(password),
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone_norm or phone,
        "role": "customer",
        "is_active": True,
        "source": "checkout_guest_convert",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    await db.orders.update_one({"id": order["id"]}, {"$set": {"user_id": user["id"]}})
    await _save_guest_address(user["id"], order)

    from .deps import create_token as _ct
    token = _ct(user["id"], is_admin=False)
    user.pop("_id", None)
    user.pop("password", None)
    return {"token": token, "user": user, "existing_account": False, "message": "Hesabınız oluşturuldu ve sipariş bağlandı"}


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user info"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmanız gerekiyor")
    return current_user


@router.post("/change-password")
async def change_password(
    payload: dict,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Mevcut kullanıcı kendi şifresini değiştirir.
    Body: { current_password, new_password }
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmanız gerekiyor")
    cur = safe_str((payload or {}).get("current_password", ""), 200)
    new = safe_str((payload or {}).get("new_password", ""), 200)
    if not cur or not new:
        raise HTTPException(status_code=400, detail="Mevcut ve yeni şifre zorunlu")
    # Personel/admin hesapları için güçlü şifre politikası (Amazon DPP); müşteri min 6
    if current_user.get("is_admin"):
        validate_strong_password(new)
    elif len(new) < 6:
        raise HTTPException(status_code=400, detail="Yeni şifre en az 6 karakter olmalı")
    user = await db.users.find_one({"id": current_user["id"]})
    if not user or not verify_password(cur, user.get("password", "")):
        await write_audit_log(
            "password_change", user_id=current_user["id"], email=current_user.get("email"),
            ip=client_ip_from_request(request), user_agent=request.headers.get("user-agent"),
            success=False, meta={"reason": "wrong_current_password"},
        )
        raise HTTPException(status_code=400, detail="Mevcut şifre hatalı")
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"password": hash_password(new),
                  "password_changed_at": datetime.now(timezone.utc).isoformat()}}
    )
    await write_audit_log(
        "password_change", user_id=current_user["id"], email=current_user.get("email"),
        ip=client_ip_from_request(request), user_agent=request.headers.get("user-agent"),
        success=True,
    )
    return {"success": True, "message": "Şifre güncellendi"}


# =============================================================================
# SMS OTP PASSWORD RESET (FAZ 3)
# =============================================================================
import random
import hashlib
import secrets
import re
from pydantic import BaseModel


class OTPRequestReq(BaseModel):
    phone: str


class OTPVerifyReq(BaseModel):
    phone: str
    code: str


class OTPResetReq(BaseModel):
    reset_token: str
    new_password: str


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


@router.post("/forgot-password/request-otp")
@(limiter.limit("3/minute") if limiter else (lambda f: f))
async def forgot_password_request_otp(request: Request, req: OTPRequestReq):
    """Telefon numarasına 6 haneli SMS OTP gönderir.
    Privacy: numara sistemde olmasa bile aynı yanıt döner (enumeration önleme).
    Rate limit: Aynı telefon için 60 sn içinde tek istek.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from notification_service import normalize_phone_tr, send_notification

    phone_norm = normalize_phone_tr(req.phone)

    # Rate limit — aynı numaraya son 60 sn içinde kod atılmışsa sessizce aynı cevabı döndür
    now = datetime.now(timezone.utc)
    recent = await db.password_reset_otps.find_one(
        {"phone": phone_norm, "created_at": {"$gt": (now.replace(microsecond=0).isoformat()[:-6])}},
        sort=[("created_at", -1)],
    )
    # Daha güvenli: zaman karşılaştırması timestamp'le
    if recent:
        try:
            prev = datetime.fromisoformat(recent["created_at"])
            if (now - prev).total_seconds() < 60:
                return {"success": True, "message": "Eğer numara sistemimizde kayıtlıysa SMS kodu gönderildi."}
        except Exception:
            pass

    user = await db.users.find_one({"phone": {"$regex": phone_norm[-10:], "$options": "i"}}, {"_id": 0, "id": 1, "email": 1, "phone": 1, "first_name": 1}) if phone_norm else None

    # Bu telefon için var olan kullanılmamış kodları iptal et
    await db.password_reset_otps.update_many(
        {"phone": phone_norm, "used": False},
        {"$set": {"used": True, "invalidated": True}},
    )

    code = f"{random.randint(0, 999999):06d}"
    expires = (now.timestamp() + 300)  # 5 dk
    record = {
        "phone": phone_norm,
        "code_hash": _hash_otp(code),
        "user_id": (user or {}).get("id"),
        "expires_at": expires,
        "used": False,
        "attempts": 0,
        "created_at": now.isoformat(),
    }
    await db.password_reset_otps.insert_one(record)

    if user:
        try:
            await send_notification(
                db, "password_reset_otp",
                to_phone=phone_norm,
                variables={"otp_code": code, "customer_name": user.get("first_name", "")},
                channels=["sms"],
            )
        except Exception as e:
            logger.warning(f"OTP sms failed: {e}")
    else:
        logger.info(f"OTP request for unknown phone (silent): {phone_norm}")

    return {"success": True, "message": "Eğer numara sistemimizde kayıtlıysa SMS kodu gönderildi."}


@router.post("/forgot-password/verify-otp")
@(limiter.limit("10/minute") if limiter else (lambda f: f))
async def forgot_password_verify_otp(request: Request, req: OTPVerifyReq):
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from notification_service import normalize_phone_tr

    phone_norm = normalize_phone_tr(req.phone)
    now_ts = datetime.now(timezone.utc).timestamp()

    rec = await db.password_reset_otps.find_one(
        {"phone": phone_norm, "used": False, "expires_at": {"$gt": now_ts}},
        sort=[("created_at", -1)],
    )
    if not rec:
        raise HTTPException(status_code=400, detail="Kod geçersiz veya süresi dolmuş")

    if rec.get("attempts", 0) >= 5:
        raise HTTPException(status_code=429, detail="Çok fazla deneme yaptınız")

    await db.password_reset_otps.update_one({"_id": rec["_id"]}, {"$inc": {"attempts": 1}})

    if _hash_otp(req.code) != rec.get("code_hash"):
        raise HTTPException(status_code=400, detail="Kod hatalı")

    if not rec.get("user_id"):
        raise HTTPException(status_code=400, detail="Kullanıcı bulunamadı")

    reset_token = secrets.token_urlsafe(32)
    await db.password_reset_otps.update_one(
        {"_id": rec["_id"]},
        {"$set": {"used": True, "reset_token": reset_token, "reset_token_expires": now_ts + 600}},
    )
    return {"reset_token": reset_token, "expires_in": 600}


@router.post("/forgot-password/reset")
async def forgot_password_reset(req: OTPResetReq):
    if not req.new_password or len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Şifre en az 6 karakter olmalı")

    now_ts = datetime.now(timezone.utc).timestamp()
    rec = await db.password_reset_otps.find_one(
        {"reset_token": req.reset_token, "reset_token_expires": {"$gt": now_ts}}
    )
    if not rec:
        raise HTTPException(status_code=400, detail="Reset token geçersiz veya süresi dolmuş")

    user_id = rec.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Kullanıcı bulunamadı")

    await db.users.update_one(
        {"id": user_id},
        {"$set": {"password": hash_password(req.new_password), "password_updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await db.password_reset_otps.delete_one({"_id": rec["_id"]})
    return {"success": True, "message": "Şifreniz güncellendi"}


class EmailResetReq(BaseModel):
    email: str


@router.post("/forgot-password/email")
@(limiter.limit("3/minute") if limiter else (lambda f: f))
async def forgot_password_email(request: Request, req: EmailResetReq):
    """E-posta ile şifre sıfırlama BAĞLANTISI gönderir (ZeptoMail üzerinden).
    Privacy: e-posta sistemde olmasa bile aynı yanıt döner (enumeration önleme).
    Üretilen token mevcut /forgot-password/reset endpoint'i ile tüketilir.
    """
    import os as _os
    email = (req.email or "").strip().lower()
    generic = {"success": True, "message": "Eğer e-posta adresi sistemimizde kayıtlıysa şifre sıfırlama bağlantısı gönderildi."}
    if not email or "@" not in email:
        return generic

    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    user = await db.users.find_one(
        {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
        {"_id": 0, "id": 1, "email": 1, "first_name": 1},
    )
    if not user or not user.get("id"):
        logger.info(f"Email reset for unknown email (silent): {email}")
        return generic

    # Rate limit — aynı e-postaya son 60 sn içinde link atıldıysa sessizce aynı cevap
    recent = await db.password_reset_otps.find_one(
        {"email": email, "channel": "email"}, sort=[("created_at", -1)]
    )
    if recent:
        try:
            if (now - datetime.fromisoformat(recent["created_at"])).total_seconds() < 60:
                return generic
        except Exception:
            pass

    # Önceki e-posta token'larını geçersiz kıl
    await db.password_reset_otps.update_many(
        {"email": email, "channel": "email"},
        {"$set": {"invalidated": True, "reset_token_expires": 0}},
    )

    reset_token = secrets.token_urlsafe(32)
    await db.password_reset_otps.insert_one({
        "email": email,
        "channel": "email",
        "user_id": user.get("id"),
        "used": True,  # OTP doğrulama adımı yok; token doğrudan geçerli
        "reset_token": reset_token,
        "reset_token_expires": now_ts + 1800,  # 30 dk
        "created_at": now.isoformat(),
    })

    site = _os.environ.get("SITE_URL", "https://facette.com.tr").rstrip("/")
    link = f"{site}/sifre-sifirla?token={reset_token}"
    name = (user.get("first_name") or "").strip()
    from email_layout import email_shell
    html = email_shell(
        icon="🔒",
        eyebrow="HESAP GÜVENLİĞİ",
        title="Şifrenizi sıfırlayın",
        intro_html=(
            "Merhaba " + (name or "değerli müşterimiz") + ",<br>"
            "Facette hesabınız için bir şifre sıfırlama talebi aldık. "
            "Yeni bir şifre belirlemek için aşağıdaki butona tıklamanız yeterli."
        ),
        cta_text="ŞİFREYİ SIFIRLA", cta_url=link,
        fallback_url=link,
        note_title="Bu bağlantı 30 dakika geçerlidir.",
        note_html="Eğer bu talebi siz oluşturmadıysanız bu e-postayı yok sayabilirsiniz; şifreniz değişmeden kalır.",
        preheader="Şifre sıfırlama bağlantınız",
    )
    try:
        from email_smtp import send_smtp_email
        res = await send_smtp_email(db, user["email"], "Şifre Sıfırlama — FACETTE", html)
        if not res.get("success"):
            logger.warning(f"reset email send failed for {email}: {res.get('response')}")
    except Exception as e:
        logger.warning(f"reset email exception for {email}: {e}")

    return generic

@router.post("/google")
async def google_signin(request: Request, payload: dict):
    """Standart Google Sign-In — frontend GIS'ten gelen ID token'i dogrular,
    kullaniciyi olusturur/bulur ve uygulama JWT'sini dondurur (kendi Client ID'miz)."""
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
    except Exception:
        raise HTTPException(status_code=500, detail="Google dogrulama kutuphanesi yuklu degil")

    credential = safe_str((payload or {}).get("credential", ""), 4096)
    if not credential:
        raise HTTPException(status_code=400, detail="Google kimlik tokeni eksik")
    try:
        idinfo = google_id_token.verify_oauth2_token(
            credential, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Google tokeni dogrulanamadi")

    if not idinfo.get("email_verified", False):
        raise HTTPException(status_code=400, detail="Google e-postasi dogrulanmamis")
    email = safe_str(idinfo.get("email", ""), 256).lower().strip()
    if not is_safe_email(email):
        raise HTTPException(status_code=400, detail="Google hesabindan gecerli e-posta alinamadi")
    name = safe_str(idinfo.get("name", ""), 200)
    picture = safe_str(idinfo.get("picture", ""), 500)
    first_name, _, last_name = name.partition(" ")
    ip = client_ip_from_request(request)
    ua = request.headers.get("user-agent")

    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user = {
            "id": generate_id(),
            "email": email,
            "password": hash_password(uuid.uuid4().hex),  # Google kullanicisi
            "first_name": first_name or name or email.split("@")[0],
            "last_name": last_name or "",
            "phone": "",
            "is_admin": False,
            "is_active": True,
            "auth_provider": "google",
            "picture": picture,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
    else:
        updates = {}
        if not user.get("auth_provider"):
            updates["auth_provider"] = "google"
        if picture and not user.get("picture"):
            updates["picture"] = picture
        if updates:
            await db.users.update_one({"id": user["id"]}, {"$set": updates})

    if not user.get("is_active", True):
        await write_audit_log("google_login", user_id=user["id"], email=email, ip=ip,
                              user_agent=ua, success=False, meta={"reason": "inactive"})
        raise HTTPException(status_code=403, detail="Hesabiniz devre disi")

    token = create_token(user["id"])
    await write_audit_log("google_login", user_id=user["id"], email=email, ip=ip,
                          user_agent=ua, success=True)
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "is_admin": user.get("is_admin", False),
            "picture": user.get("picture", ""),
        },
    }


@router.post("/google/session")
async def google_session(request: Request, session_id: str = Query(...)):
    """Emergent-managed Google Auth — session_id'yi kullanıcı + app JWT token'a çevirir.

    Frontend, auth.emergentagent.com'dan dönen session_id'yi buraya POST eder.
    Backend, Emergent session-data API'sini çağırıp kullanıcıyı oluşturur/günceller
    ve uygulamanın kendi JWT token'ını döndürür (mevcut JWT auth ile uyumlu).
    """
    import httpx
    session_id = safe_str(session_id, 512)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id},
            )
    except Exception:
        raise HTTPException(status_code=502, detail="Kimlik doğrulama servisine ulaşılamadı")

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Google oturumu doğrulanamadı")

    data = resp.json()
    email = safe_str(data.get("email", ""), 256).lower().strip()
    if not is_safe_email(email):
        raise HTTPException(status_code=400, detail="Google hesabından geçerli e-posta alınamadı")
    name = safe_str(data.get("name", ""), 200)
    picture = safe_str(data.get("picture", ""), 500)
    first_name, _, last_name = name.partition(" ")
    ip = client_ip_from_request(request)
    ua = request.headers.get("user-agent")

    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user = {
            "id": generate_id(),
            "email": email,
            "password": hash_password(uuid.uuid4().hex),  # Google kullanıcısı — kullanılamaz şifre
            "first_name": first_name or name or email.split("@")[0],
            "last_name": last_name or "",
            "phone": "",
            "is_admin": False,
            "is_active": True,
            "auth_provider": "google",
            "picture": picture,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
    else:
        updates = {}
        if not user.get("auth_provider"):
            updates["auth_provider"] = "google"
        if picture and not user.get("picture"):
            updates["picture"] = picture
        if updates:
            await db.users.update_one({"id": user["id"]}, {"$set": updates})

    if not user.get("is_active", True):
        await write_audit_log("google_login", user_id=user["id"], email=email, ip=ip,
                              user_agent=ua, success=False, meta={"reason": "inactive"})
        raise HTTPException(status_code=403, detail="Hesabınız devre dışı")

    token = create_token(user["id"])
    await write_audit_log("google_login", user_id=user["id"], email=email, ip=ip,
                          user_agent=ua, success=True)
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "is_admin": user.get("is_admin", False),
            "picture": user.get("picture", ""),
        },
    }


@router.get("/google/login")
async def google_login(request: Request):
    """Initiate Google OAuth login"""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth yapılandırılmamış")
    
    # Get the base URL from request
    base_url = str(request.base_url).rstrip('/')
    redirect_uri = f"{base_url}/api/auth/google/callback"
    
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=email%20profile"
        f"&access_type=offline"
    )
    
    return {"auth_url": google_auth_url}

@router.get("/google/callback")
async def google_callback(code: str, request: Request):
    """Handle Google OAuth callback"""
    import httpx
    
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth yapılandırılmamış")
    
    base_url = str(request.base_url).rstrip('/')
    redirect_uri = f"{base_url}/api/auth/google/callback"
    
    # Exchange code for token
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            }
        )
        
        if token_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Google token alınamadı")
        
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        
        # Get user info
        user_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if user_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Google kullanıcı bilgisi alınamadı")
        
        google_user = user_response.json()
    
    # Find or create user
    email = google_user.get("email", "").lower()
    user = await db.users.find_one({"email": email})
    
    if not user:
        user = {
            "id": generate_id(),
            "email": email,
            "password": "",  # No password for OAuth users
            "first_name": google_user.get("given_name", ""),
            "last_name": google_user.get("family_name", ""),
            "google_id": google_user.get("id"),
            "avatar": google_user.get("picture"),
            "is_admin": False,
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
    else:
        # Update Google info
        await db.users.update_one(
            {"email": email},
            {"$set": {
                "google_id": google_user.get("id"),
                "avatar": google_user.get("picture"),
            }}
        )
        user = await db.users.find_one({"email": email}, {"_id": 0})
    
    token = create_token(user["id"], user.get("is_admin", False))
    
    # Redirect to frontend with token
    frontend_url = os.environ.get("FRONTEND_URL", "")
    if frontend_url:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(f"{frontend_url}/auth/callback?token={token}")
    
    return {"token": token, "user": user}
