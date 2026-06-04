"""
TOTP tabanlı MFA (çok faktörlü kimlik doğrulama) — Amazon DPP uyumu.

Google Authenticator / Authy uyumlu. Opsiyoneldir: mfa_enabled=False kullanıcılar
normal login yapar (mevcut akış bozulmaz). mfa_secret AES vault ile şifreli saklanır.

Login akışı:
  POST /api/auth/login -> mfa_enabled ise {mfa_required: true, mfa_token} döner (tam JWT vermez)
  POST /api/auth/mfa/verify {mfa_token, code} -> kod doğruysa tam JWT döner
"""
import io
import base64
from datetime import datetime, timezone, timedelta

import jwt
import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException

from .deps import db, require_auth, create_token, JWT_SECRET, JWT_ALGORITHM, JWT_ISSUER
from security.crypto import encrypt, decrypt

router = APIRouter(prefix="/auth/mfa", tags=["MFA"])

ISSUER_NAME = "Facette Admin"
MFA_TOKEN_PURPOSE = "mfa_pending"


def create_mfa_pending_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "purpose": MFA_TOKEN_PURPOSE,
        "iat": now,
        "iss": JWT_ISSUER,
        "exp": now + timedelta(minutes=5),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_mfa_token(token: str) -> dict:
    payload = jwt.decode(
        token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "user_id"]}, issuer=JWT_ISSUER,
    )
    if payload.get("purpose") != MFA_TOKEN_PURPOSE:
        raise HTTPException(status_code=400, detail="Geçersiz MFA token")
    return payload


def _verify_totp(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(str(code).strip().replace(" ", ""), valid_window=1)


@router.get("/status")
async def mfa_status(current_user: dict = Depends(require_auth)):
    u = await db.users.find_one({"id": current_user["id"]}, {"_id": 0, "mfa_enabled": 1})
    return {"mfa_enabled": bool(u and u.get("mfa_enabled"))}


@router.post("/setup")
async def mfa_setup(current_user: dict = Depends(require_auth)):
    """Yeni TOTP secret üretir (henüz aktif değil), QR + otpauth URI döner."""
    secret = pyotp.random_base32()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=current_user.get("email", "user"), issuer_name=ISSUER_NAME
    )
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"mfa_pending_secret_enc": encrypt(secret)}},
    )
    # QR PNG -> base64 data URI
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()
    return {"otpauth_uri": uri, "qr_code": f"data:image/png;base64,{qr_b64}", "secret": secret}


@router.post("/enable")
async def mfa_enable(payload: dict, current_user: dict = Depends(require_auth)):
    """Pending secret'a karşı kod doğrulanırsa MFA aktifleşir."""
    code = (payload or {}).get("code")
    u = await db.users.find_one({"id": current_user["id"]}, {"_id": 0, "mfa_pending_secret_enc": 1})
    pending = decrypt(u.get("mfa_pending_secret_enc")) if u and u.get("mfa_pending_secret_enc") else None
    if not pending:
        raise HTTPException(status_code=400, detail="Önce MFA kurulumunu başlatın (setup)")
    if not _verify_totp(pending, code):
        raise HTTPException(status_code=400, detail="Kod doğrulanamadı")
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"mfa_enabled": True, "mfa_secret_enc": encrypt(pending),
                  "mfa_enabled_at": datetime.now(timezone.utc).isoformat()},
         "$unset": {"mfa_pending_secret_enc": ""}},
    )
    return {"success": True, "mfa_enabled": True}


@router.post("/disable")
async def mfa_disable(payload: dict, current_user: dict = Depends(require_auth)):
    """Geçerli TOTP kodu ile MFA devre dışı bırakılır."""
    code = (payload or {}).get("code")
    u = await db.users.find_one({"id": current_user["id"]}, {"_id": 0, "mfa_secret_enc": 1, "mfa_enabled": 1})
    if not (u and u.get("mfa_enabled")):
        return {"success": True, "mfa_enabled": False}
    secret = decrypt(u.get("mfa_secret_enc")) if u.get("mfa_secret_enc") else None
    if not _verify_totp(secret, code):
        raise HTTPException(status_code=400, detail="Kod doğrulanamadı")
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"mfa_enabled": False}, "$unset": {"mfa_secret_enc": "", "mfa_pending_secret_enc": ""}},
    )
    return {"success": True, "mfa_enabled": False}


@router.post("/verify")
async def mfa_verify(payload: dict):
    """Login 2. adımı: mfa_token + TOTP kodu -> tam JWT."""
    mfa_token = (payload or {}).get("mfa_token")
    code = (payload or {}).get("code")
    if not mfa_token or not code:
        raise HTTPException(status_code=400, detail="mfa_token ve kod zorunlu")
    try:
        decoded = _decode_mfa_token(mfa_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="MFA süresi doldu, tekrar giriş yapın")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Geçersiz MFA token")

    user = await db.users.find_one({"id": decoded["user_id"]}, {"_id": 0})
    if not user or not user.get("mfa_enabled"):
        raise HTTPException(status_code=400, detail="MFA aktif değil")
    secret = decrypt(user.get("mfa_secret_enc")) if user.get("mfa_secret_enc") else None
    if not _verify_totp(secret, code):
        raise HTTPException(status_code=401, detail="Kod doğrulanamadı")

    token = create_token(user["id"], user.get("is_admin", False))
    return {
        "token": token,
        "user": {
            "id": user["id"], "email": user["email"],
            "first_name": user.get("first_name", ""), "last_name": user.get("last_name", ""),
            "phone": user.get("phone", ""), "is_admin": user.get("is_admin", False),
            "created_at": user.get("created_at"),
        },
    }
