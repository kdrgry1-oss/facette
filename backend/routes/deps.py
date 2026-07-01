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
        cf_ip = request.headers.get("cf-connecting-ip") if request else None
        tcp_src = None
        try:
            tcp_src = request.client.host if request and request.client else None
        except Exception:
            pass
        computed = xff.split(",")[0].strip() if xff else _gra(request)
        # [GEÇİCİ DEBUG - 2026-07-01] Rate-limit IP zincirini teşhis için loglanıyor.
        # Railway loglarında bir kaç istek sonrası bu satırları görüp gerçek
        # değerleri karşılaştırdıktan sonra bu bloğu KALDIR (veya logger.debug'a indir).
        try:
            logging.getLogger("rate_limit_debug").warning(
                "RATE_KEY_DEBUG path=%s xff_raw=%r cf_connecting_ip=%r tcp_client=%r computed_key=%r",
                getattr(request, "url", None) and request.url.path,
                xff, cf_ip, tcp_src, computed,
            )
        except Exception:
            pass
        return computed

    limiter = Limiter(key_func=_rate_key, default_limits=[])
except Exception as _limiter_init_exc:  # pragma: no cover
    limiter = None
    try:
        logging.getLogger("rate_limit_debug").warning(
            "RATE_LIMITER_INIT_FAILED: %r", _limiter_init_exc
        )
    except Exception:
        pass


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


async def get_effective_permissions(user: dict) -> list:
    """Kullanicinin etkin yetki listesini dondurur.

    Kural (admin_rbac /me/permissions ile birebir ayni):
      - email == 'admin@facette.com' VEYA role_id yok  -> ['*'] (super admin)
      - aksi halde rol kaydindaki permissions listesi
    """
    role_id = (user or {}).get("role_id") or ""
    if (user or {}).get("email") == "admin@facette.com" or not role_id:
        return ["*"]
    role = await db.roles.find_one({"id": role_id}, {"_id": 0})
    if not role:
        return []
    return role.get("permissions", []) or []


def require_permission(perm_key: str):
    """Belirli bir RBAC yetkisini ZORUNLU kilan FastAPI dependency uretir.

    super_admin ('*') her yetkiyi gecer. Yetkisi olmayan -> 403.
    Kullanim:  current_user: dict = Depends(require_permission("returns.approve"))
    """
    async def _checker(current_user: dict = Depends(require_admin)) -> dict:
        perms = await get_effective_permissions(current_user)
        if "*" in perms or perm_key in perms:
            return current_user
        raise HTTPException(status_code=403, detail=f"Bu işlem için yetkiniz yok ({perm_key})")
    return _checker

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

def _ean13_check_digit(twelve: str) -> str:
    """12 haneli taban için EAN-13 (mod-10) kontrol hanesi."""
    total = 0
    for i, ch in enumerate(twelve):
        d = ord(ch) - 48
        total += d if (i % 2 == 0) else d * 3
    return str((10 - (total % 10)) % 10)


async def build_used_barcode_set() -> set:
    """Tum urun ve varyant barkodlarini (legacy dahil) tek seferde toplar."""
    used = set()
    async for p in db.products.find({}, {"_id": 0, "barcode": 1, "variants": 1}):
        for var in (p.get("variants") or []):
            bc = str(var.get("barcode", "") or "")
            if bc:
                used.add(bc)
        pbc = str(p.get("barcode", "") or "")
        if pbc:
            used.add(pbc)
    return used


async def generate_barcode_from_range(used_barcodes_set=None) -> str:
    """GS1 onekine gore BENZERSIZ, gecerli EAN-13 (GTIN-13) barkod uretir.

    settings.gs1_prefix (varsayilan '8683851', 7 hane) + sirali urun referansi
    (kalan haneler; 7 hane onek => 5 hane = 100.000 barkod) + EAN-13 kontrol hanesi.
    Atomik sirali sayac (db.counters._id='gs1_item_ref') kullanir ve kullanilan/
    legacy barkodlari atlar. Boylece hicbir barkod cakismaz; her cagri (her varyant)
    farkli barkod alir.
    """
    from pymongo import ReturnDocument
    settings = await db.settings.find_one({"id": "main"}, {"_id": 0}) or {}
    prefix = str(settings.get("gs1_prefix") or "8683851").strip()
    if not prefix.isdigit() or len(prefix) >= 12:
        return None
    ref_len = 12 - len(prefix)          # 7 hane onek => 5
    max_ref = 10 ** ref_len             # 100000

    if used_barcodes_set is None:
        used_barcodes_set = await build_used_barcode_set()

    for _ in range(max_ref + 1):
        c = await db.counters.find_one_and_update(
            {"_id": "gs1_item_ref"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        ref = int((c or {}).get("seq", 1)) - 1      # 0'dan basla (00000)
        if ref >= max_ref:
            logger.error("GS1 barkod kapasitesi (%s) doldu - yeni onek/blok gerekli." % max_ref)
            return None
        base = prefix + str(ref).zfill(ref_len)     # 12 hane
        barcode = base + _ean13_check_digit(base)   # 13 hane GTIN-13
        if barcode in used_barcodes_set:
            continue                                # legacy/kullanilmis -> atla
        used_barcodes_set.add(barcode)
        return barcode
    return None


async def generate_urun_karti_id() -> str:
    """Yeni urun icin Urun Kart ID uretir: sistemdeki EN BUYUK sayisal
    Urun Kart ID + 1. Hic yoksa settings.urun_karti_start (varsayilan 1000).
    Manuel ayni no varsa bir sonraki bos numaraya ilerler.
    """
    settings = await db.settings.find_one({"id": "main"}, {"_id": 0}) or {}
    try:
        start = int(settings.get("urun_karti_start") or 1000)
    except Exception:
        start = 1000
    mx = 0
    async for p in db.products.find({"urun_karti_id": {"$nin": [None, ""]}}, {"_id": 0, "urun_karti_id": 1}):
        v = str(p.get("urun_karti_id") or "").strip()
        if v.isdigit():
            iv = int(v)
            if iv > mx:
                mx = iv
    nxt = max(mx + 1, start)
    for _ in range(100000):
        cand = str(nxt)
        ex = await db.products.find_one({"urun_karti_id": cand}, {"_id": 1})
        if not ex:
            return cand
        nxt += 1
    return str(nxt)


async def build_used_urun_id_set() -> set:
    """Sistemdeki tum varyant urun_id (ve urun-seviyesi urun_id) degerlerini toplar."""
    used = set()
    async for p in db.products.find({}, {"_id": 0, "urun_id": 1, "variants": 1}):
        pu = str(p.get("urun_id") or "").strip()
        if pu.isdigit():
            used.add(pu)
        for v in (p.get("variants") or []):
            vu = str(v.get("urun_id") or "").strip()
            if vu.isdigit():
                used.add(vu)
    return used


def next_urun_id(used_set) -> str:
    """Sistemdeki EN BUYUK sayisal urun_id + 1; kullanilmis degerleri atlar.
    used_set yerinde guncellenir; ardisik her cagri bir sonraki BOS id'yi dondurur
    (her beden icin +1 ilerler).
    """
    if used_set is None:
        used_set = set()
    mx = 0
    for u in used_set:
        s = str(u).strip()
        if s.isdigit():
            iv = int(s)
            if iv > mx:
                mx = iv
    nid = mx + 1
    while str(nid) in used_set:
        nid += 1
    used_set.add(str(nid))
    return str(nid)


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
