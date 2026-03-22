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
