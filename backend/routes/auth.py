"""
Authentication routes - Login, Register, Google OAuth
"""
from fastapi import APIRouter, HTTPException, Query, Request, Depends
from datetime import datetime, timezone
import uuid
import os

from .deps import (
    db, logger, hash_password, verify_password, 
    create_token, get_current_user, generate_id
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

@router.post("/register")
async def register(
    email: str = Query(...),
    password: str = Query(...),
    first_name: str = Query(None),
    last_name: str = Query(None)
):
    """Register new user"""
    existing = await db.users.find_one({"email": email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Bu e-posta zaten kayıtlı")
    
    user = {
        "id": generate_id(),
        "email": email.lower(),
        "password": hash_password(password),
        "first_name": first_name or "",
        "last_name": last_name or "",
        "phone": "",
        "is_admin": False,
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    await db.users.insert_one(user)
    token = create_token(user["id"])
    
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
async def login(
    email: str = Query(...),
    password: str = Query(...)
):
    """Login with email and password"""
    user = await db.users.find_one({"email": email.lower()}, {"_id": 0})
    if not user or not verify_password(password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Geçersiz e-posta veya şifre")
    
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Hesabınız devre dışı")
    
    token = create_token(user["id"], user.get("is_admin", False))
    
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

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user info"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmanız gerekiyor")
    return current_user


# =============================================================================
# SMS OTP PASSWORD RESET (FAZ 3)
# =============================================================================
import random
import hashlib
import secrets
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
async def forgot_password_request_otp(req: OTPRequestReq):
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
async def forgot_password_verify_otp(req: OTPVerifyReq):
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
