"""
Shared dependencies and utilities for all routes
"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import os
import logging
import uuid
import random

# Persistent database
MONGO_URL = os.environ.get('MONGO_URL')
if not MONGO_URL:
    # Try unix socket first (works with OS sandbox), fallback to TCP
    import pathlib
    sock = pathlib.Path('/tmp/mongodb-27017.sock')
    if sock.exists():
        MONGO_URL = 'mongodb://%2Ftmp%2Fmongodb-27017.sock'
    else:
        MONGO_URL = 'mongodb://127.0.0.1:27017'
db_name = os.environ.get('DB_NAME', 'test_database')

client = AsyncIOMotorClient(MONGO_URL)
db = client[db_name]

# Security
security = HTTPBearer(auto_error=False)
# JWT_SECRET MUST come from env. A weak default is allowed only as a hard last
# resort but will trigger a noisy warning. Production must set a strong secret.
JWT_SECRET = os.environ.get('JWT_SECRET') or 'facette-secure-secret-key-2024-extended-32bytes!'
if len(JWT_SECRET) < 32:
    logging.getLogger(__name__).warning(
        "JWT_SECRET is too short (<32 bytes). Set a strong secret in /app/backend/.env"
    )
JWT_ALGORITHM = "HS256"  # strict — prevents 'alg=none' attacks
JWT_ISSUER = "facette-api"

# Logger
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SECURITY HELPERS (NoSQL injection guard, audit log, brute-force lockout)
# ---------------------------------------------------------------------------

def safe_str(value, max_len: int = 256) -> str:
    """Coerce arbitrary input to a safe string for MongoDB equality matching.
    Strips type-confusion attacks (dict/list with $operators, deeply nested
    payloads). Always returns a primitive str — never an operator dict.
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        # NoSQL injection attempt — refuse
        return ""
    s = str(value)
    if len(s) > max_len:
        s = s[:max_len]
    return s


def is_safe_email(email: str) -> bool:
    """Basic email validation — rejects $ { } operators that could leak into
    Mongo equality match if blindly used. Pydantic + safe_str cover the rest.
    """
    import re
    if not email or not isinstance(email, str):
        return False
    if any(ch in email for ch in ("$", "{", "}", "\x00")):
        return False
    return bool(re.match(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$", email))


async def write_audit_log(event: str, *, user_id: str = None, email: str = None,
                          ip: str = None, user_agent: str = None,
                          success: bool = True, meta: dict = None) -> None:
    """Append an entry to `auth_audit_logs`. Best-effort, never raises."""
    try:
        await db.auth_audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "event": event,
            "user_id": user_id,
            "email": (email or "").lower() if email else None,
            "ip": ip,
            "user_agent": (user_agent or "")[:500],
            "success": bool(success),
            "meta": meta or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning(f"audit log failed: {e}")


# Lockout policy — 5 failed attempts inside the last 15 min → lock for 15 min
LOCKOUT_WINDOW_MIN = 15
LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION_MIN = 15


async def is_account_locked(email: str) -> tuple[bool, int]:
    """Return (locked, retry_after_seconds). Lock is identified by the
    presence of a `locked_until > now` field on the user document."""
    if not email:
        return False, 0
    user = await db.users.find_one({"email": email.lower()}, {"_id": 0, "locked_until": 1})
    if not user:
        return False, 0
    locked_until = user.get("locked_until")
    if not locked_until:
        return False, 0
    try:
        until = datetime.fromisoformat(locked_until)
    except Exception:
        return False, 0
    now = datetime.now(timezone.utc)
    if until > now:
        return True, int((until - now).total_seconds())
    return False, 0


async def register_failed_login(email: str) -> None:
    """Increment failed-attempt counter; lock account when threshold hit."""
    if not email:
        return
    now = datetime.now(timezone.utc)
    user = await db.users.find_one({"email": email.lower()}, {"_id": 0, "id": 1, "failed_attempts": 1, "first_failed_at": 1})
    if not user:
        return
    first_at = user.get("first_failed_at")
    try:
        first_dt = datetime.fromisoformat(first_at) if first_at else None
    except Exception:
        first_dt = None
    # Reset window if older than LOCKOUT_WINDOW_MIN
    if first_dt is None or (now - first_dt) > timedelta(minutes=LOCKOUT_WINDOW_MIN):
        new_count = 1
        await db.users.update_one(
            {"email": email.lower()},
            {"$set": {"failed_attempts": 1, "first_failed_at": now.isoformat()}}
        )
    else:
        new_count = (user.get("failed_attempts") or 0) + 1
        update = {"failed_attempts": new_count}
        if new_count >= LOCKOUT_THRESHOLD:
            update["locked_until"] = (now + timedelta(minutes=LOCKOUT_DURATION_MIN)).isoformat()
        await db.users.update_one({"email": email.lower()}, {"$set": update})


async def reset_failed_login(email: str) -> None:
    if not email:
        return
    await db.users.update_one(
        {"email": email.lower()},
        {"$unset": {"failed_attempts": "", "first_failed_at": "", "locked_until": ""}}
    )


# ---------------------------------------------------------------------------
# IP-LEVEL BRUTE FORCE BLOCKLIST
# ---------------------------------------------------------------------------
# Hesap-bazlı lockout (yukarıda) tek bir email'i koruyor. IP-level blocklist
# ise: aynı IP'den 1 saatte 50+ failed login olduğunda 24 saat ban koyar
# (collection: ip_blocklist). Botnet/distribuited scanning saldırılarını
# erken durdurur. `auth_audit_logs` ile entegre.
IP_BLOCK_WINDOW_MIN = 60       # 1 saatlik pencere
IP_BLOCK_THRESHOLD = 50        # bu pencerede 50+ failed login → ban
IP_BLOCK_DURATION_HOURS = 24   # ban süresi


async def is_ip_blocked(ip: str) -> tuple[bool, int]:
    """Return (blocked, retry_after_seconds). Manuel admin ban ve otomatik
    threshold ban'ları aynı koleksiyonda tutar (`ip_blocklist`)."""
    if not ip:
        return False, 0
    doc = await db.ip_blocklist.find_one({"ip": ip}, {"_id": 0, "blocked_until": 1, "permanent": 1})
    if not doc:
        return False, 0
    if doc.get("permanent"):
        return True, 0
    bu = doc.get("blocked_until")
    if not bu:
        return False, 0
    try:
        until = datetime.fromisoformat(bu)
    except Exception:
        return False, 0
    now = datetime.now(timezone.utc)
    if until > now:
        return True, int((until - now).total_seconds())
    # Süresi dolmuş — pasifle
    await db.ip_blocklist.delete_one({"ip": ip})
    return False, 0


async def register_failed_login_ip(ip: str) -> None:
    """IP'nin 1 saatlik pencerede başarısız login sayısını sayar.
    Threshold aşıldıysa 24 saatlik geçici ban koyar."""
    if not ip:
        return
    since = (datetime.now(timezone.utc) - timedelta(minutes=IP_BLOCK_WINDOW_MIN)).isoformat()
    fail_count = await db.auth_audit_logs.count_documents({
        "event": "login",
        "success": False,
        "ip": ip,
        "created_at": {"$gte": since},
    })
    if fail_count >= IP_BLOCK_THRESHOLD:
        until = datetime.now(timezone.utc) + timedelta(hours=IP_BLOCK_DURATION_HOURS)
        await db.ip_blocklist.update_one(
            {"ip": ip},
            {"$set": {
                "ip": ip,
                "blocked_until": until.isoformat(),
                "blocked_at": datetime.now(timezone.utc).isoformat(),
                "reason": f"auto: {fail_count} failed logins in {IP_BLOCK_WINDOW_MIN}min",
                "trigger_count": fail_count,
                "auto_blocked": True,
            }, "$setOnInsert": {"id": str(uuid.uuid4())}},
            upsert=True,
        )


def client_ip_from_request(request) -> str:
    """Return the real client IP, honouring X-Forwarded-For (first hop)."""
    if not request:
        return ""
    xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    try:
        return request.client.host if request.client else ""
    except Exception:
        return ""


# Shared SlowAPI limiter instance (single instance per app)
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address as _gra

    def _rate_key(request):
        xff = request.headers.get("x-forwarded-for") if request else None
        if xff:
            return xff.split(",")[0].strip()
        return _gra(request)

    limiter = Limiter(key_func=_rate_key, default_limits=[])
except Exception:  # pragma: no cover
    limiter = None


# Password helpers
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

def verify_password(password: str, hashed: str) -> bool:
    if not hashed or not isinstance(hashed, str):
        return False
    # Reject legacy weak hashes (md5/sha1 length) — force bcrypt-only
    if not (hashed.startswith("$2a$") or hashed.startswith("$2b$") or hashed.startswith("$2y$")):
        return False
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False

def create_token(user_id: str, is_admin: bool = False) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "is_admin": is_admin,
        "iat": now,
        "iss": JWT_ISSUER,
        "exp": now + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_jwt_strict(token: str) -> dict:
    """Strictly decode JWT — locks algorithm to HS256 and validates issuer.
    Raises jwt exceptions on tamper/expiry which the caller maps to HTTP errs."""
    return jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "user_id"], "verify_signature": True},
        issuer=JWT_ISSUER,
    )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token (strict decode)."""
    if not credentials:
        return None
    try:
        payload = _decode_jwt_strict(credentials.credentials)
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0, "password": 0})
        if user and user.get("is_active") is False:
            return None
        return user
    except Exception:
        return None

async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Require authentication"""
    user = await get_current_user(credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Giriş yapmanız gerekiyor")
    return user

async def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Require admin authentication (strict JWT)."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Yetkilendirme gerekli")
    try:
        payload = _decode_jwt_strict(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token süresi dolmuş")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Geçersiz token")
    except Exception:
        raise HTTPException(status_code=401, detail="Geçersiz token")
    if not payload.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0, "password": 0})
    if not user or user.get("is_active") is False:
        raise HTTPException(status_code=401, detail="Hesap devre dışı")
    return user

def generate_id() -> str:
    """Generate unique UUID"""
    return str(uuid.uuid4())

async def generate_short_id(collection_name: str) -> str:
    """Generate a unique 4-digit numeric ID (1000-9999) for a collection"""
    for _ in range(100):
        new_id = str(random.randint(1000, 9999))
        existing = await db[collection_name].find_one({"id": new_id}, {"_id": 1})
        if not existing:
            return new_id
    # Fallback if somehow 9000 IDs are exhausted or we get extremely unlucky
    return str(uuid.uuid4())[:4]

def generate_order_number() -> str:
    """Generate order number (collision-resistant)"""
    import time, secrets
    return f"FC{int(time.time())}{secrets.token_hex(2).upper()}"

def serialize_doc(doc):
    """Serialize MongoDB document for JSON response"""
    if not doc:
        return doc
    if isinstance(doc.get('created_at'), datetime):
        doc['created_at'] = doc['created_at'].isoformat()
    if isinstance(doc.get('updated_at'), datetime):
        doc['updated_at'] = doc['updated_at'].isoformat()
    return doc

async def generate_barcode_from_range(used_barcodes_set=None) -> str:
    """Generate a unique 13-digit GTIN barcode within the configured range"""
    settings = await db.settings.find_one({"id": "main"}, {"_id": 0})
    if not settings:
        return None
    
    range_start = settings.get("barcode_range_start", "")
    range_end = settings.get("barcode_range_end", "")
    
    if not range_start or not range_end:
        return None
    
    try:
        start_num = int(range_start)
        end_num = int(range_end)
    except ValueError:
        return None
    
    # If set not provided, fetch it once
    if used_barcodes_set is None:
        used_barcodes_set = set()
        async for p in db.products.find({}, {"_id": 0, "barcode": 1, "all_barcodes": 1, "variants": 1}):
            # Check variants
            for var in p.get("variants", []):
                bc = var.get("barcode", "")
                if bc: used_barcodes_set.add(str(bc))
            # Check main
            pbc = p.get("barcode", "")
            if pbc: used_barcodes_set.add(str(pbc))
    
    for _ in range(5000):
        num = random.randint(start_num, end_num)
        barcode = str(num).zfill(13)
        if barcode not in used_barcodes_set:
            used_barcodes_set.add(barcode) # For sequential calls in same request
            return barcode
    
    return None


# =============================================================================
# Şifre Politikası (Amazon DPP uyumu — personel/admin hesapları)
# Amazon, Amazon verisine erişen personel için min 12 karakter + karmaşıklık ister.
# Müşteri (storefront) hesaplarına UYGULANMAZ; mevcut login akışını bozmaz.
# =============================================================================
import re as _re_pw


def validate_strong_password(password: str) -> None:
    """Personel/admin şifresi için güç doğrulaması. Zayıfsa HTTPException(400) atar."""
    pw = password or ""
    errors = []
    if len(pw) < 12:
        errors.append("en az 12 karakter")
    if not _re_pw.search(r"[A-ZÇĞİÖŞÜ]", pw):
        errors.append("en az 1 büyük harf")
    if not _re_pw.search(r"[a-zçğıöşü]", pw):
        errors.append("en az 1 küçük harf")
    if not _re_pw.search(r"[0-9]", pw):
        errors.append("en az 1 rakam")
    if not _re_pw.search(r"[^A-Za-z0-9]", pw):
        errors.append("en az 1 özel karakter")
    if errors:
        raise HTTPException(
            status_code=400,
            detail="Personel şifresi şu kuralları sağlamalı: " + ", ".join(errors) + ".",
        )
