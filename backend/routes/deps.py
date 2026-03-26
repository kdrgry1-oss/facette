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
JWT_SECRET = os.environ.get('JWT_SECRET', 'facette-secure-secret-key-2024-extended-32bytes!')
JWT_ALGORITHM = "HS256"

# Logger
logger = logging.getLogger(__name__)

# Password helpers
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: str, is_admin: bool = False) -> str:
    payload = {
        "user_id": user_id,
        "is_admin": is_admin,
        "exp": datetime.now(timezone.utc) + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0, "password": 0})
        return user
    except:
        return None

async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Require authentication"""
    user = await get_current_user(credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Giriş yapmanız gerekiyor")
    return user

async def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Require admin authentication"""
    if not credentials:
        raise HTTPException(status_code=401, detail="Yetkilendirme gerekli")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if not payload.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token süresi dolmuş")
    except:
        raise HTTPException(status_code=401, detail="Geçersiz token")

def generate_id() -> str:
    """Generate unique ID"""
    return str(uuid.uuid4())

def generate_order_number() -> str:
    """Generate order number"""
    import time
    return f"FC{int(time.time())}"

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
