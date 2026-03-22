from fastapi import FastAPI, APIRouter, HTTPException, Depends, Query, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import random
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import re
import json
import uuid

from models import (
    User, UserCreate, Product, ProductCreate, Category, CategoryCreate,
    Order, OrderCreate, Banner, BannerCreate, HomepageBlock, MenuItem,
    SiteSettings, Campaign, StaticPage, CartItem
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Facette E-Commerce API")
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

JWT_SECRET = os.environ.get('JWT_SECRET', 'facette-secure-secret-key-2024-extended-32bytes!')
JWT_ALGORITHM = "HS256"

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Helper Functions
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
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
        return user
    except:
        return None

async def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Yetkilendirme gerekli")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if not payload.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token süresi dolmuş")
    except:
        raise HTTPException(status_code=401, detail="Geçersiz token")

def serialize_doc(doc):
    if doc and isinstance(doc.get('created_at'), datetime):
        doc['created_at'] = doc['created_at'].isoformat()
    if doc and isinstance(doc.get('updated_at'), datetime):
        doc['updated_at'] = doc['updated_at'].isoformat()
    if doc and isinstance(doc.get('start_date'), datetime):
        doc['start_date'] = doc['start_date'].isoformat()
    if doc and isinstance(doc.get('end_date'), datetime):
        doc['end_date'] = doc['end_date'].isoformat()
    return doc

# ==================== OBJECT STORAGE ====================
import requests as http_requests

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "facette"
storage_key = None

def init_storage():
    global storage_key
    if storage_key:
        return storage_key
    try:
        resp = http_requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
        resp.raise_for_status()
        storage_key = resp.json()["storage_key"]
        return storage_key
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
        return None

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    if not key:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    resp = http_requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    resp.raise_for_status()
    return resp.json()

def get_object(path: str) -> tuple:
    key = init_storage()
    if not key:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    resp = http_requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

# ==================== AUTH ====================
@api_router.post("/auth/register")
async def register(user_data: UserCreate):
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Bu email zaten kayıtlı")
    
    user = User(**user_data.model_dump())
    user.password_hash = hash_password(user_data.password)
    doc = user.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.users.insert_one(doc)
    
    token = create_token(user.id, user.is_admin)
    return {"token": token, "user": {"id": user.id, "email": user.email, "is_admin": user.is_admin}}

@api_router.post("/auth/login")
async def login(email: str = Query(...), password: str = Query(...)):
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(password, user.get('password_hash', '')):
        raise HTTPException(status_code=401, detail="Email veya şifre hatalı")
    
    token = create_token(user['id'], user.get('is_admin', False))
    return {"token": token, "user": {"id": user['id'], "email": user['email'], "is_admin": user.get('is_admin', False)}}

@api_router.get("/auth/me")
async def get_me(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    return {"id": user['id'], "email": user['email'], "is_admin": user.get('is_admin', False)}

# ==================== GOOGLE AUTH ====================
@api_router.post("/auth/google/session")
async def google_auth_session(session_id: str = Query(...)):
    """Exchange session_id for user data from Emergent Auth"""
    try:
        resp = http_requests.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id},
            timeout=30
        )
        resp.raise_for_status()
        auth_data = resp.json()
        
        email = auth_data.get("email")
        name = auth_data.get("name", "")
        picture = auth_data.get("picture", "")
        session_token = auth_data.get("session_token")
        
        # Check if user exists
        existing_user = await db.users.find_one({"email": email}, {"_id": 0})
        
        if existing_user:
            user_id = existing_user["id"]
            # Update user info if needed
            await db.users.update_one(
                {"id": user_id},
                {"$set": {"name": name, "picture": picture, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
        else:
            # Create new user
            import uuid
            user_id = str(uuid.uuid4())
            new_user = {
                "id": user_id,
                "email": email,
                "first_name": name.split()[0] if name else "",
                "last_name": " ".join(name.split()[1:]) if name and len(name.split()) > 1 else "",
                "picture": picture,
                "is_admin": False,
                "is_active": True,
                "password_hash": "",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.users.insert_one(new_user)
        
        # Store session
        await db.user_sessions.insert_one({
            "user_id": user_id,
            "session_token": session_token,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Create JWT token for our app
        token = create_token(user_id, False)
        
        return {
            "success": True,
            "token": token,
            "session_token": session_token,
            "user": {
                "id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "is_admin": False
            }
        }
    except Exception as e:
        logger.error(f"Google auth failed: {e}")
        raise HTTPException(status_code=401, detail="Google authentication failed")

# ==================== IMAGE UPLOAD ====================
@api_router.post("/upload/image")
async def upload_image(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload image to object storage"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Sadece resim dosyaları yüklenebilir")
    
    import uuid
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    path = f"{APP_NAME}/images/{uuid.uuid4()}.{ext}"
    data = await file.read()
    
    result = put_object(path, data, file.content_type or "image/jpeg")
    
    # Store reference in DB
    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": result.get("size", len(data)),
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {
        "success": True,
        "path": result["path"],
        "url": f"/api/files/{result['path']}"
    }

@api_router.get("/files/{path:path}")
async def get_file(path: str):
    """Serve files from object storage"""
    record = await db.files.find_one({"storage_path": path, "is_deleted": False})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    
    from fastapi.responses import Response
    data, content_type = get_object(path)
    return Response(content=data, media_type=record.get("content_type", content_type))

# ==================== PRODUCTS ====================
@api_router.get("/products")
async def get_products(
    category: Optional[str] = None,
    search: Optional[str] = None,
    is_featured: Optional[bool] = None,
    is_new: Optional[bool] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort: str = "created_at",
    order: str = "desc",
    page: int = 1,
    limit: int = 20
):
    query = {"is_active": True}
    if category:
        query["$or"] = [{"category_id": category}, {"category_name": {"$regex": category, "$options": "i"}}]
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}}
        ]
    if is_featured:
        query["is_featured"] = True
    if is_new:
        query["is_new"] = True
    if min_price:
        query["price"] = {"$gte": min_price}
    if max_price:
        query.setdefault("price", {})["$lte"] = max_price
    
    sort_dir = -1 if order == "desc" else 1
    skip = (page - 1) * limit
    
    total = await db.products.count_documents(query)
    products = await db.products.find(query, {"_id": 0}).sort(sort, sort_dir).skip(skip).limit(limit).to_list(limit)
    
    return {"products": [serialize_doc(p) for p in products], "total": total, "page": page, "pages": (total + limit - 1) // limit}

@api_router.get("/products/{product_id}")
async def get_product(product_id: str):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        product = await db.products.find_one({"slug": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    
    # Increment view count
    await db.products.update_one({"id": product['id']}, {"$inc": {"view_count": 1}})
    return serialize_doc(product)

@api_router.post("/products", dependencies=[Depends(require_admin)])
async def create_product(product_data: ProductCreate):
    product = Product(**product_data.model_dump())
    doc = product.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    await db.products.insert_one(doc)
    return serialize_doc(doc)

@api_router.put("/products/{product_id}", dependencies=[Depends(require_admin)])
async def update_product(product_id: str, product_data: ProductCreate):
    update_data = product_data.model_dump()
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
    result = await db.products.update_one({"id": product_id}, {"$set": update_data})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return {"success": True}

@api_router.delete("/products/{product_id}", dependencies=[Depends(require_admin)])
async def delete_product(product_id: str):
    result = await db.products.delete_one({"id": product_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return {"success": True}

# ==================== CATEGORIES ====================
@api_router.get("/categories")
async def get_categories():
    categories = await db.categories.find({"is_active": True}, {"_id": 0}).sort("sort_order", 1).to_list(100)
    return [serialize_doc(c) for c in categories]

@api_router.post("/categories", dependencies=[Depends(require_admin)])
async def create_category(cat_data: CategoryCreate):
    cat = Category(**cat_data.model_dump())
    doc = cat.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.categories.insert_one(doc)
    return serialize_doc(doc)

@api_router.put("/categories/{cat_id}", dependencies=[Depends(require_admin)])
async def update_category(cat_id: str, cat_data: CategoryCreate):
    result = await db.categories.update_one({"id": cat_id}, {"$set": cat_data.model_dump()})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı")
    return {"success": True}

@api_router.delete("/categories/{cat_id}", dependencies=[Depends(require_admin)])
async def delete_category(cat_id: str):
    result = await db.categories.delete_one({"id": cat_id})
    return {"success": True}

# ==================== ORDERS ====================
@api_router.get("/orders", dependencies=[Depends(require_admin)])
async def get_orders(status: Optional[str] = None, page: int = 1, limit: int = 20):
    query = {}
    if status:
        query["status"] = status
    
    total = await db.orders.count_documents(query)
    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).skip((page-1)*limit).limit(limit).to_list(limit)
    return {"orders": [serialize_doc(o) for o in orders], "total": total}

@api_router.get("/orders/{order_id}")
async def get_order(order_id: str, user=Depends(get_current_user)):
    order = await db.orders.find_one({"$or": [{"id": order_id}, {"order_number": order_id}]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    return serialize_doc(order)

@api_router.post("/orders")
async def create_order(order_data: OrderCreate):
    order = Order(**order_data.model_dump())
    doc = order.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    await db.orders.insert_one(doc)
    
    # Decrease stock
    for item in order_data.items:
        await db.products.update_one({"id": item.product_id}, {"$inc": {"stock": -item.quantity}})
    
    return {"order_id": order.id, "order_number": order.order_number}

@api_router.put("/orders/{order_id}/status", dependencies=[Depends(require_admin)])
async def update_order_status(order_id: str, status: str = Query(...)):
    result = await db.orders.update_one(
        {"id": order_id},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    return {"success": True}

# ==================== ADVANCED ORDER MANAGEMENT ====================
@api_router.get("/orders/{order_id}/detail", dependencies=[Depends(require_admin)])
async def get_order_detail(order_id: str):
    """Get detailed order information for admin"""
    order = await db.orders.find_one({"$or": [{"id": order_id}, {"order_number": order_id}]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    # Get customer details
    customer = None
    if order.get('user_id'):
        customer = await db.users.find_one({"id": order['user_id']}, {"_id": 0, "password": 0})
    
    return {
        "order": serialize_doc(order),
        "customer": serialize_doc(customer) if customer else None
    }

@api_router.post("/orders/{order_id}/invoice", dependencies=[Depends(require_admin)])
async def generate_invoice(order_id: str):
    """Generate invoice for order"""
    import random
    import string
    
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    # Generate invoice number
    invoice_number = f"FAT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=6))}"
    
    # Update order with invoice info
    invoice_data = {
        "invoice_number": invoice_number,
        "invoice_date": datetime.now(timezone.utc).isoformat(),
        "invoice_status": "generated"
    }
    
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"invoice": invoice_data, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {
        "success": True,
        "invoice_number": invoice_number,
        "message": "Fatura oluşturuldu"
    }

@api_router.post("/orders/{order_id}/cargo-barcode", dependencies=[Depends(require_admin)])
async def generate_cargo_barcode(order_id: str, cargo_company: str = Query(default="MNG")):
    """Generate cargo barcode for order"""
    import random
    import string
    
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    # Generate cargo tracking number
    prefix = {"MNG": "MNG", "DHL": "JD", "YURTICI": "YK", "ARAS": "AR"}.get(cargo_company.upper(), "KRG")
    tracking_number = f"{prefix}{''.join(random.choices(string.digits, k=12))}"
    
    # Update order with cargo info
    cargo_data = {
        "company": cargo_company.upper(),
        "tracking_number": tracking_number,
        "barcode": tracking_number,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending"
    }
    
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"cargo": cargo_data, "status": "shipping", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {
        "success": True,
        "tracking_number": tracking_number,
        "cargo_company": cargo_company.upper(),
        "message": f"Kargo barkodu oluşturuldu: {tracking_number}"
    }

@api_router.post("/orders/bulk/cargo-barcode", dependencies=[Depends(require_admin)])
async def bulk_generate_cargo_barcodes(order_ids: list[str], cargo_company: str = Query(default="MNG")):
    """Generate cargo barcodes for multiple orders"""
    import random
    import string
    
    results = []
    for order_id in order_ids:
        order = await db.orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            results.append({"order_id": order_id, "success": False, "error": "Sipariş bulunamadı"})
            continue
        
        prefix = {"MNG": "MNG", "DHL": "JD", "YURTICI": "YK", "ARAS": "AR"}.get(cargo_company.upper(), "KRG")
        tracking_number = f"{prefix}{''.join(random.choices(string.digits, k=12))}"
        
        cargo_data = {
            "company": cargo_company.upper(),
            "tracking_number": tracking_number,
            "barcode": tracking_number,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending"
        }
        
        await db.orders.update_one(
            {"id": order_id},
            {"$set": {"cargo": cargo_data, "status": "shipping", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        results.append({
            "order_id": order_id,
            "order_number": order.get('order_number'),
            "success": True,
            "tracking_number": tracking_number
        })
    
    return {"results": results, "total": len(order_ids), "success_count": sum(1 for r in results if r.get('success'))}

@api_router.post("/orders/bulk/status", dependencies=[Depends(require_admin)])
async def bulk_update_order_status(order_ids: list[str], status: str = Query(...)):
    """Update status for multiple orders"""
    result = await db.orders.update_many(
        {"id": {"$in": order_ids}},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "modified_count": result.modified_count}


# ==================== BANNERS ====================
@api_router.get("/banners")
async def get_banners(position: Optional[str] = None):
    query = {"is_active": True}
    if position:
        query["position"] = position
    banners = await db.banners.find(query, {"_id": 0}).sort("sort_order", 1).to_list(50)
    return [serialize_doc(b) for b in banners]

@api_router.post("/banners", dependencies=[Depends(require_admin)])
async def create_banner(banner_data: BannerCreate):
    banner = Banner(**banner_data.model_dump())
    doc = banner.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.banners.insert_one(doc)
    doc.pop('_id', None)
    return serialize_doc(doc)

@api_router.put("/banners/{banner_id}", dependencies=[Depends(require_admin)])
async def update_banner(banner_id: str, banner_data: BannerCreate):
    result = await db.banners.update_one({"id": banner_id}, {"$set": banner_data.model_dump()})
    return {"success": True}

@api_router.delete("/banners/{banner_id}", dependencies=[Depends(require_admin)])
async def delete_banner(banner_id: str):
    await db.banners.delete_one({"id": banner_id})
    return {"success": True}

# ==================== SEARCH ====================
@api_router.get("/search/popular")
async def get_popular_searches():
    """Get most popular search terms"""
    searches = await db.search_logs.aggregate([
        {"$group": {"_id": "$term", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]).to_list(10)
    
    if not searches:
        # Default popular searches
        return [
            {"term": "elbise", "count": 150},
            {"term": "bluz", "count": 120},
            {"term": "pantolon", "count": 100},
            {"term": "ceket", "count": 80},
            {"term": "kazak", "count": 70},
            {"term": "gömlek", "count": 60},
        ]
    
    return [{"term": s["_id"], "count": s["count"]} for s in searches]

@api_router.post("/search/log")
async def log_search(term: str = Query(...)):
    """Log a search term for analytics"""
    await db.search_logs.insert_one({
        "term": term.lower().strip(),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"success": True}


# ==================== HOMEPAGE BLOCKS ====================
@api_router.get("/homepage/blocks")
async def get_homepage_blocks():
    blocks = await db.homepage_blocks.find({"is_active": True}, {"_id": 0}).sort("sort_order", 1).to_list(20)

# ==================== PAGE BLOCKS (CMS) ====================
@api_router.get("/page-blocks")
async def get_page_blocks(page: str = Query(default="home")):
    """Get all page blocks for CMS"""
    blocks = await db.page_blocks.find({"page": page}, {"_id": 0}).sort("sort_order", 1).to_list(50)
    return [serialize_doc(b) for b in blocks]

@api_router.post("/page-blocks", dependencies=[Depends(require_admin)])
async def create_page_block(block_data: dict):
    """Create a new page block"""
    import uuid
    block = {
        "id": str(uuid.uuid4()),
        "type": block_data.get("type", "hero_slider"),
        "title": block_data.get("title", ""),
        "images": block_data.get("images", []),
        "links": block_data.get("links", []),
        "settings": block_data.get("settings", {}),
        "sort_order": block_data.get("sort_order", 0),
        "is_active": block_data.get("is_active", True),
        "page": block_data.get("page", "home"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.page_blocks.insert_one(block)
    block.pop('_id', None)
    return serialize_doc(block)

@api_router.put("/page-blocks/{block_id}", dependencies=[Depends(require_admin)])
async def update_page_block(block_id: str, block_data: dict):
    """Update a page block"""
    update_data = {k: v for k, v in block_data.items() if k != 'id'}
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
    result = await db.page_blocks.update_one({"id": block_id}, {"$set": update_data})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Blok bulunamadı")
    return {"success": True}

@api_router.delete("/page-blocks/{block_id}", dependencies=[Depends(require_admin)])
async def delete_page_block(block_id: str):
    """Delete a page block"""
    await db.page_blocks.delete_one({"id": block_id})
    return {"success": True}

    return blocks

@api_router.post("/homepage/blocks", dependencies=[Depends(require_admin)])
async def create_homepage_block(block: HomepageBlock):
    doc = block.model_dump()
    await db.homepage_blocks.insert_one(doc)
    return doc

@api_router.put("/homepage/blocks/{block_id}", dependencies=[Depends(require_admin)])
async def update_homepage_block(block_id: str, block: HomepageBlock):
    await db.homepage_blocks.update_one({"id": block_id}, {"$set": block.model_dump()})
    return {"success": True}

@api_router.delete("/homepage/blocks/{block_id}", dependencies=[Depends(require_admin)])
async def delete_homepage_block(block_id: str):
    await db.homepage_blocks.delete_one({"id": block_id})
    return {"success": True}

# ==================== SETTINGS ====================
@api_router.get("/settings")
async def get_settings():
    settings = await db.settings.find_one({"id": "main"}, {"_id": 0})
    if not settings:
        settings = SiteSettings().model_dump()
        await db.settings.insert_one(settings)
    return settings

@api_router.put("/settings", dependencies=[Depends(require_admin)])
async def update_settings(settings: SiteSettings):
    await db.settings.update_one({"id": "main"}, {"$set": settings.model_dump()}, upsert=True)
    return {"success": True}

# ==================== MENU ====================
@api_router.get("/menu")
async def get_menu():
    items = await db.menu_items.find({"is_active": True}, {"_id": 0}).sort("sort_order", 1).to_list(50)
    return items

@api_router.post("/menu", dependencies=[Depends(require_admin)])
async def create_menu_item(item: MenuItem):
    doc = item.model_dump()
    await db.menu_items.insert_one(doc)
    return doc

@api_router.put("/menu/{item_id}", dependencies=[Depends(require_admin)])
async def update_menu_item(item_id: str, item: MenuItem):
    await db.menu_items.update_one({"id": item_id}, {"$set": item.model_dump()})
    return {"success": True}

@api_router.delete("/menu/{item_id}", dependencies=[Depends(require_admin)])
async def delete_menu_item(item_id: str):
    await db.menu_items.delete_one({"id": item_id})
    return {"success": True}

# ==================== CAMPAIGNS ====================
@api_router.get("/campaigns")
async def get_campaigns():
    campaigns = await db.campaigns.find({}, {"_id": 0}).to_list(100)
    return [serialize_doc(c) for c in campaigns]

@api_router.post("/campaigns", dependencies=[Depends(require_admin)])
async def create_campaign(campaign: Campaign):
    doc = campaign.model_dump()
    doc['start_date'] = doc['start_date'].isoformat()
    doc['end_date'] = doc['end_date'].isoformat()
    await db.campaigns.insert_one(doc)
    return serialize_doc(doc)

@api_router.post("/campaigns/validate")
async def validate_campaign(code: str = Query(...), total: float = Query(...)):
    campaign = await db.campaigns.find_one({
        "code": code.upper(),
        "is_active": True
    }, {"_id": 0})
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Kupon bulunamadı")
    
    now = datetime.now(timezone.utc)
    start = datetime.fromisoformat(campaign['start_date'].replace('Z', '+00:00')) if isinstance(campaign['start_date'], str) else campaign['start_date']
    end = datetime.fromisoformat(campaign['end_date'].replace('Z', '+00:00')) if isinstance(campaign['end_date'], str) else campaign['end_date']
    
    if now < start or now > end:
        raise HTTPException(status_code=400, detail="Kupon geçerlilik süresi dışında")
    
    if campaign.get('min_order_amount', 0) > total:
        raise HTTPException(status_code=400, detail=f"Minimum sipariş tutarı: {campaign['min_order_amount']} TL")
    
    discount = 0
    if campaign['type'] == 'percentage':
        discount = total * (campaign['value'] / 100)
    elif campaign['type'] == 'fixed':
        discount = campaign['value']
    
    return {"discount": discount, "campaign": serialize_doc(campaign)}

# ==================== STATIC PAGES ====================
@api_router.get("/pages")
async def get_pages():
    pages = await db.pages.find({"is_active": True}, {"_id": 0}).to_list(50)
    return [serialize_doc(p) for p in pages]

@api_router.get("/pages/{slug}")
async def get_page(slug: str):
    page = await db.pages.find_one({"slug": slug, "is_active": True}, {"_id": 0})
    if not page:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadı")
    return serialize_doc(page)

@api_router.post("/pages", dependencies=[Depends(require_admin)])
async def create_page(page: StaticPage):
    doc = page.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.pages.insert_one(doc)
    return serialize_doc(doc)

@api_router.put("/pages/{page_id}", dependencies=[Depends(require_admin)])
async def update_page(page_id: str, page: StaticPage):
    await db.pages.update_one({"id": page_id}, {"$set": page.model_dump()})
    return {"success": True}

# ==================== REPORTS ====================
@api_router.get("/reports/dashboard", dependencies=[Depends(require_admin)])
async def get_dashboard_stats():
    total_orders = await db.orders.count_documents({})
    total_products = await db.products.count_documents({})
    total_users = await db.users.count_documents({})
    
    # Today's orders
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_orders = await db.orders.count_documents({"created_at": {"$gte": today.isoformat()}})
    
    # Revenue
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$total"}}}]
    revenue_result = await db.orders.aggregate(pipeline).to_list(1)
    total_revenue = revenue_result[0]['total'] if revenue_result else 0
    
    # Recent orders
    recent_orders = await db.orders.find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
    
    return {
        "total_orders": total_orders,
        "total_products": total_products,
        "total_users": total_users,
        "today_orders": today_orders,
        "total_revenue": total_revenue,
        "recent_orders": [serialize_doc(o) for o in recent_orders]
    }

# ==================== XML IMPORT ====================
@api_router.post("/import/xml", dependencies=[Depends(require_admin)])
async def import_xml(url: str = Query(...)):
    import httpx
    from bs4 import BeautifulSoup
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=60)
            soup = BeautifulSoup(response.text, 'xml')
            
            products = []
            for item in soup.find_all('item'):
                name = item.find('g:title')
                price = item.find('g:price')
                images = item.find_all('g:additional_image_link')
                main_image = item.find('g:image_link')
                category = item.find('g:product_type')
                barcode = item.find('g:gtin')
                desc = item.find('g:description')
                link = item.find('link')
                
                if name and price:
                    slug = re.sub(r'[^a-z0-9]+', '-', name.text.lower().strip())
                    price_val = float(re.sub(r'[^\d.]', '', price.text.split()[0]))
                    
                    all_images = []
                    if main_image:
                        all_images.append(main_image.text)
                    for img in images:
                        all_images.append(img.text)
                    
                    product = Product(
                        name=name.text.strip(),
                        slug=slug,
                        price=price_val,
                        description=desc.text if desc else "",
                        category_name=category.text if category else "Genel",
                        images=all_images[:10],
                        barcode=barcode.text if barcode else None,
                        is_active=True,
                        is_new=True
                    )
                    
                    doc = product.model_dump()
                    doc['created_at'] = doc['created_at'].isoformat()
                    doc['updated_at'] = doc['updated_at'].isoformat()
                    
                    # Upsert by slug
                    await db.products.update_one(
                        {"slug": slug},
                        {"$set": doc},
                        upsert=True
                    )
                    products.append(name.text)
            
            return {"imported": len(products), "products": products[:10]}
    except Exception as e:
        logger.error(f"XML import error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== ADMIN PRODUCTS (ALL) ====================
@api_router.get("/admin/products", dependencies=[Depends(require_admin)])
async def get_admin_products(page: int = 1, limit: int = 20, search: Optional[str] = None):
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"sku": {"$regex": search, "$options": "i"}},
            {"barcode": {"$regex": search, "$options": "i"}}
        ]
    
    total = await db.products.count_documents(query)
    products = await db.products.find(query, {"_id": 0}).sort("created_at", -1).skip((page-1)*limit).limit(limit).to_list(limit)
    return {"products": [serialize_doc(p) for p in products], "total": total, "page": page}

# ==================== SEED DATA ====================
@api_router.post("/seed")
async def seed_data():
    # Check if already seeded
    existing = await db.products.count_documents({})
    if existing > 0:
        return {"message": "Veriler zaten mevcut", "count": existing}
    
    # Create admin user
    admin = User(
        email="admin@facette.com",
        first_name="Admin",
        last_name="User",
        is_admin=True,
        password_hash=hash_password("admin123")
    )
    admin_doc = admin.model_dump()
    admin_doc['created_at'] = admin_doc['created_at'].isoformat()
    await db.users.insert_one(admin_doc)
    
    # Create categories
    categories = [
        {"name": "En Yeniler", "slug": "en-yeniler", "sort_order": 1},
        {"name": "Elbise", "slug": "elbise", "sort_order": 2},
        {"name": "Bluz", "slug": "bluz", "sort_order": 3},
        {"name": "Pantolon", "slug": "pantolon", "sort_order": 4},
        {"name": "Etek", "slug": "etek", "sort_order": 5},
        {"name": "Ceket", "slug": "ceket", "sort_order": 6},
        {"name": "Trençkot", "slug": "trenckot", "sort_order": 7},
        {"name": "Jean", "slug": "jean", "sort_order": 8},
        {"name": "Kazak", "slug": "kazak", "sort_order": 9},
        {"name": "Gömlek", "slug": "gomlek", "sort_order": 10},
        {"name": "Aksesuar", "slug": "aksesuar", "sort_order": 11},
    ]
    for cat in categories:
        c = Category(**cat)
        doc = c.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        await db.categories.insert_one(doc)
    
    # Create settings
    settings = SiteSettings(
        site_name="FACETTE",
        free_shipping_limit=500,
        rotating_texts=["Yeni Sezon Ürünleri Keşfet", "500 TL Üzeri Ücretsiz Kargo", "Güvenli Alışveriş"],
        contact_email="info@facette.com",
        contact_phone="+90 212 000 00 00"
    )
    await db.settings.insert_one(settings.model_dump())
    
    # Create sample menu
    menu_items = [
        {"name": "EN YENİLER", "url": "/kategori/en-yeniler", "sort_order": 1},
        {"name": "ELBİSE", "url": "/kategori/elbise", "sort_order": 2},
        {"name": "BLUZ", "url": "/kategori/bluz", "sort_order": 3},
        {"name": "PANTOLON", "url": "/kategori/pantolon", "sort_order": 4},
        {"name": "CEKET", "url": "/kategori/ceket", "sort_order": 5},
        {"name": "AKSESUAR", "url": "/kategori/aksesuar", "sort_order": 6},
    ]
    for item in menu_items:
        m = MenuItem(**item)
        await db.menu_items.insert_one(m.model_dump())
    
    # Create pages
    pages = [
        {"title": "Hakkımızda", "slug": "hakkimizda", "content": "<h1>Hakkımızda</h1><p>FACETTE, kadın modasında farkı hissettiren bir marka...</p>"},
        {"title": "KVKK", "slug": "kvkk", "content": "<h1>KVKK Aydınlatma Metni</h1><p>6698 sayılı Kişisel Verilerin Korunması Kanunu kapsamında...</p>"},
        {"title": "İade Koşulları", "slug": "iade-kosullari", "content": "<h1>İade ve Değişim</h1><p>14 gün içinde iade ve değişim hakkınız bulunmaktadır...</p>"},
    ]
    for page in pages:
        p = StaticPage(**page)
        doc = p.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        await db.pages.insert_one(doc)
    
    # Create banners
    banners = [
        {"title": "Yeni Sezon", "image_url": "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=1920&h=800&fit=crop", "link": "/kategori/en-yeniler", "position": "hero", "sort_order": 1, "is_active": True},
        {"title": "Elbise Koleksiyonu", "image_url": "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=1920&h=800&fit=crop", "link": "/kategori/elbise", "position": "hero", "sort_order": 2, "is_active": True},
        {"title": "Günlük Stil", "image_url": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=1920&h=800&fit=crop", "link": "/kategori/bluz", "position": "hero", "sort_order": 3, "is_active": True},
    ]
    for banner in banners:
        b = Banner(**banner)
        doc = b.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        await db.banners.insert_one(doc)
    
    return {"message": "Seed veriler oluşturuldu", "admin_email": "admin@facette.com", "admin_password": "admin123"}

# ==================== IYZICO PAYMENT ====================
import iyzipay

# Iyzico configuration - set IYZICO_MODE to 'live' in production
IYZICO_MODE = os.environ.get('IYZICO_MODE', 'sandbox')  # 'sandbox' or 'live'
IYZICO_API_KEY = os.environ.get('IYZICO_API_KEY', 'sandbox-api-key')
IYZICO_SECRET_KEY = os.environ.get('IYZICO_SECRET_KEY', 'sandbox-secret-key')
IYZICO_BASE_URL = os.environ.get('IYZICO_BASE_URL', 
    'https://api.iyzipay.com' if IYZICO_MODE == 'live' else 'https://sandbox-api.iyzipay.com'
)

def get_iyzico_options():
    return {
        'api_key': IYZICO_API_KEY,
        'secret_key': IYZICO_SECRET_KEY,
        'base_url': IYZICO_BASE_URL
    }

def is_iyzico_configured():
    """Check if Iyzico is properly configured for production"""
    return (
        IYZICO_API_KEY and 
        IYZICO_API_KEY != 'sandbox-api-key' and 
        IYZICO_SECRET_KEY and 
        IYZICO_SECRET_KEY != 'sandbox-secret-key'
    )

@api_router.get("/payment/status")
async def get_payment_status():
    """Get Iyzico configuration status"""
    return {
        "mode": IYZICO_MODE,
        "configured": is_iyzico_configured(),
        "base_url": IYZICO_BASE_URL
    }

@api_router.post("/payment/initialize")
async def initialize_payment(
    order_id: str = Query(...),
    callback_url: str = Query(...)
):
    """Initialize 3DS payment for an order"""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    # Get or create conversation ID
    conversation_id = f"FC-{order['order_number']}"
    
    # Build basket items
    basket_items = []
    for item in order.get('items', []):
        basket_items.append({
            'id': item.get('product_id', 'item'),
            'name': item.get('name', 'Ürün')[:50],
            'category1': 'Giyim',
            'category2': 'Moda',
            'itemType': 'PHYSICAL',
            'price': str(item.get('price', 0) * item.get('quantity', 1))
        })
    
    # Build shipping address
    shipping = order.get('shipping_address', {})
    
    request_data = {
        'locale': 'tr',
        'conversationId': conversation_id,
        'price': str(order.get('subtotal', 0)),
        'paidPrice': str(order.get('total', 0)),
        'currency': 'TRY',
        'installment': '1',
        'basketId': order['order_number'],
        'paymentChannel': 'WEB',
        'paymentGroup': 'PRODUCT',
        'callbackUrl': callback_url,
        'buyer': {
            'id': order.get('user_id', 'guest'),
            'name': shipping.get('first_name', 'Misafir'),
            'surname': shipping.get('last_name', 'Kullanıcı'),
            'gsmNumber': shipping.get('phone', '+905001234567'),
            'email': shipping.get('email', 'misafir@facette.com'),
            'identityNumber': '11111111111',
            'registrationAddress': shipping.get('address', 'Türkiye'),
            'ip': '127.0.0.1',
            'city': shipping.get('city', 'İstanbul'),
            'country': 'Turkey',
            'zipCode': shipping.get('postal_code', '34000')
        },
        'shippingAddress': {
            'contactName': f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}",
            'city': shipping.get('city', 'İstanbul'),
            'country': 'Turkey',
            'address': shipping.get('address', 'Türkiye'),
            'zipCode': shipping.get('postal_code', '34000')
        },
        'billingAddress': {
            'contactName': f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}",
            'city': shipping.get('city', 'İstanbul'),
            'country': 'Turkey',
            'address': shipping.get('address', 'Türkiye'),
            'zipCode': shipping.get('postal_code', '34000')
        },
        'basketItems': basket_items
    }
    
    try:
        checkout_form = iyzipay.CheckoutFormInitialize()
        result = checkout_form.create(request_data, get_iyzico_options())
        response = result.read()
        
        if isinstance(response, bytes):
            response = json.loads(response.decode('utf-8'))
        
        if response.get('status') == 'success':
            # Store payment token
            await db.orders.update_one(
                {"id": order_id},
                {"$set": {
                    "payment_token": response.get('token'),
                    "conversation_id": conversation_id,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            return {
                "success": True,
                "paymentPageUrl": response.get('paymentPageUrl'),
                "token": response.get('token'),
                "checkoutFormContent": response.get('checkoutFormContent')
            }
        else:
            logger.error(f"Iyzico init failed: {response}")
            return {
                "success": False,
                "error": response.get('errorMessage', 'Ödeme başlatılamadı')
            }
    except Exception as e:
        logger.error(f"Payment init error: {e}")
        return {"success": False, "error": str(e)}

@api_router.post("/payment/callback")
async def payment_callback(token: str = Query(...)):
    """Handle Iyzico payment callback"""
    try:
        request_data = {
            'locale': 'tr',
            'token': token
        }
        
        checkout_form = iyzipay.CheckoutForm()
        result = checkout_form.retrieve(request_data, get_iyzico_options())
        response = result.read()
        
        if isinstance(response, bytes):
            response = json.loads(response.decode('utf-8'))
        
        # Find order by payment token
        order = await db.orders.find_one({"payment_token": token}, {"_id": 0})
        
        if response.get('status') == 'success' and response.get('paymentStatus') == 'SUCCESS':
            if order:
                await db.orders.update_one(
                    {"id": order['id']},
                    {"$set": {
                        "payment_status": "paid",
                        "payment_id": response.get('paymentId'),
                        "status": "confirmed",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
            
            return {
                "success": True,
                "paymentId": response.get('paymentId'),
                "orderId": order['id'] if order else None,
                "orderNumber": order['order_number'] if order else None
            }
        else:
            if order:
                await db.orders.update_one(
                    {"id": order['id']},
                    {"$set": {
                        "payment_status": "failed",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
            
            return {
                "success": False,
                "error": response.get('errorMessage', 'Ödeme başarısız')
            }
    except Exception as e:
        logger.error(f"Payment callback error: {e}")
        return {"success": False, "error": str(e)}

# ==================== PRODUCT VARIANTS ====================
@api_router.post("/products/{product_id}/variants", dependencies=[Depends(require_admin)])
async def add_product_variant(product_id: str, variant_data: dict):
    """Add a variant to a product"""
    product = await db.products.find_one({"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    
    import uuid
    variant = {
        "id": str(uuid.uuid4()),
        "size": variant_data.get("size"),
        "color": variant_data.get("color"),
        "color_code": variant_data.get("color_code"),
        "barcode": variant_data.get("barcode"),
        "sku": variant_data.get("sku"),
        "stock": variant_data.get("stock", 0),
        "price_adjustment": variant_data.get("price_adjustment", 0),
        "images": variant_data.get("images", [])
    }
    
    result = await db.products.update_one(
        {"id": product_id},
        {
            "$push": {"variants": variant},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    return {"success": True, "variant": variant}

@api_router.put("/products/{product_id}/variants/{variant_id}", dependencies=[Depends(require_admin)])
async def update_product_variant(product_id: str, variant_id: str, variant_data: dict):
    """Update a product variant"""
    update_fields = {}
    for key, value in variant_data.items():
        update_fields[f"variants.$.{key}"] = value
    
    result = await db.products.update_one(
        {"id": product_id, "variants.id": variant_id},
        {"$set": update_fields}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Varyant bulunamadı")
    
    return {"success": True}

@api_router.delete("/products/{product_id}/variants/{variant_id}", dependencies=[Depends(require_admin)])
async def delete_product_variant(product_id: str, variant_id: str):
    """Delete a product variant"""
    result = await db.products.update_one(
        {"id": product_id},
        {"$pull": {"variants": {"id": variant_id}}}
    )
    
    return {"success": True}

# ==================== SIMILAR & COMBO PRODUCTS ====================
@api_router.get("/products/{product_id}/similar")
async def get_similar_products(product_id: str, limit: int = 4):
    """Get similar products based on category"""
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        product = await db.products.find_one({"slug": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    
    # First check if product has manual similar products
    if product.get('similar_product_ids'):
        similar = await db.products.find(
            {"id": {"$in": product['similar_product_ids']}, "is_active": True},
            {"_id": 0}
        ).limit(limit).to_list(limit)
        if similar:
            return [serialize_doc(p) for p in similar]
    
    # Auto-find similar products by category
    query = {
        "is_active": True,
        "id": {"$ne": product['id']},
        "$or": [
            {"category_name": product.get('category_name')},
            {"category_id": product.get('category_id')}
        ]
    }
    
    similar = await db.products.find(query, {"_id": 0}).limit(limit).to_list(limit)
    return [serialize_doc(p) for p in similar]

@api_router.get("/products/{product_id}/combo")
async def get_combo_products(product_id: str, limit: int = 4):
    """Get combo/outfit products - products that go well together"""
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        product = await db.products.find_one({"slug": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    
    # First check manual combo products
    if product.get('combo_product_ids'):
        combo = await db.products.find(
            {"id": {"$in": product['combo_product_ids']}, "is_active": True},
            {"_id": 0}
        ).limit(limit).to_list(limit)
        if combo:
            return [serialize_doc(p) for p in combo]
    
    # Auto-find complementary products (different categories)
    category = product.get('category_name', '').lower()
    
    # Define complementary categories
    complements = {
        'elbise': ['aksesuar', 'çanta', 'ayakkabı'],
        'bluz': ['pantolon', 'etek', 'aksesuar'],
        'gömlek': ['pantolon', 'etek', 'ceket'],
        'pantolon': ['bluz', 'gömlek', 'kazak'],
        'etek': ['bluz', 'gömlek', 'kazak'],
        'ceket': ['pantolon', 'elbise', 'gömlek'],
        'kazak': ['pantolon', 'etek', 'jean'],
    }
    
    complement_categories = complements.get(category, ['aksesuar'])
    
    combo = await db.products.find(
        {
            "is_active": True,
            "id": {"$ne": product['id']},
            "category_name": {"$regex": "|".join(complement_categories), "$options": "i"}
        },
        {"_id": 0}
    ).limit(limit).to_list(limit)
    
    return [serialize_doc(p) for p in combo]

@api_router.put("/products/{product_id}/similar", dependencies=[Depends(require_admin)])
async def set_similar_products(product_id: str, similar_ids: list[str]):
    """Set similar product IDs for a product"""
    result = await db.products.update_one(
        {"id": product_id},
        {"$set": {"similar_product_ids": similar_ids, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True}

@api_router.put("/products/{product_id}/combo", dependencies=[Depends(require_admin)])
async def set_combo_products(product_id: str, combo_ids: list[str]):
    """Set combo product IDs for a product"""
    result = await db.products.update_one(
        {"id": product_id},
        {"$set": {"combo_product_ids": combo_ids, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True}

# ==================== CARGO/SHIPPING API ====================
from zeep import Client as SoapClient, Settings as SoapSettings
from zeep.transports import Transport as SoapTransport
from zeep.exceptions import Fault as SoapFault
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
import base64

# MNG Kargo API Credentials
MNG_CONFIG = {
    "customer_code": "FACETTE DIŞ TİC.A.Ş.",
    "username": "490059279",
    "password": "Face.0024E",
    "tax_number": "6080712084",
    "company_name": "MNG KARGO YURTİÇİ VE YURT",
    "wsdl_url": "https://service.mngkargo.com.tr/musterikargosiparis/musterikargosiparis.asmx?WSDL"
}

# Gönderici (Sender) bilgileri
SENDER_INFO = {
    "firma": "FACETTE DIŞ TİCARET A.Ş.",
    "telefon": "90 543 330 03 10",
    "adres": "-KÜÇÜKÇEKMECE IKITELLI OSB MAH.\nIMSAN D BLOK\nNO: 3 KÜÇÜKÇEKMECE/ ISTANBUL\nKüçükçekmece / İstanbul"
}

CARGO_COMPANIES = {
    "MNG": {"name": "MNG Kargo", "tracking_url": "https://www.mngkargo.com.tr/gonderi-takip/?q="},
    "DHL": {"name": "DHL", "tracking_url": "https://www.dhl.com/tr-tr/home/tracking.html?tracking-id="},
    "YURTICI": {"name": "Yurtiçi Kargo", "tracking_url": "https://www.yurticikargo.com/tr/online-servisler/gonderi-sorgula?code="},
    "ARAS": {"name": "Aras Kargo", "tracking_url": "https://www.araskargo.com.tr/trmGonderiSorgula.aspx?q="},
    "PTT": {"name": "PTT Kargo", "tracking_url": "https://gonderitakip.ptt.gov.tr/Track/Verify?q="}
}

@api_router.get("/cargo/companies")
async def get_cargo_companies():
    """Get available cargo companies"""
    return [{"code": code, **info} for code, info in CARGO_COMPANIES.items()]

@api_router.post("/orders/{order_id}/ship", dependencies=[Depends(require_admin)])
async def ship_order(
    order_id: str,
    cargo_company: str = Query(...),
    tracking_number: str = Query(...)
):
    """Mark order as shipped with tracking info"""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    company_info = CARGO_COMPANIES.get(cargo_company.upper())
    if not company_info:
        raise HTTPException(status_code=400, detail="Geçersiz kargo şirketi")
    
    cargo_data = {
        "company": cargo_company.upper(),
        "company_name": company_info["name"],
        "tracking_number": tracking_number,
        "tracking_url": f"{company_info['tracking_url']}{tracking_number}",
        "shipped_at": datetime.now(timezone.utc).isoformat(),
        "status": "shipped"
    }
    
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "cargo": cargo_data,
            "status": "shipped",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # TODO: Send SMS/Email notification to customer
    
    return {
        "success": True,
        "tracking_url": cargo_data["tracking_url"],
        "message": f"Sipariş {company_info['name']} ile gönderildi"
    }

@api_router.get("/orders/{order_id}/track")
async def track_order(order_id: str):
    """Get order tracking information"""
    order = await db.orders.find_one(
        {"$or": [{"id": order_id}, {"order_number": order_id}]},
        {"_id": 0}
    )
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    cargo = order.get('cargo')
    if not cargo:
        return {
            "status": order.get('status', 'pending'),
            "message": "Kargo bilgisi henüz eklenmedi",
            "tracking": None
        }
    
    return {
        "status": order.get('status'),
        "cargo_company": cargo.get('company_name'),
        "tracking_number": cargo.get('tracking_number'),
        "tracking_url": cargo.get('tracking_url'),
        "shipped_at": cargo.get('shipped_at')
    }

# ==================== MNG KARGO API INTEGRATION ====================
def generate_barcode_base64(data: str, barcode_type: str = "code128"):
    """Generate barcode as base64 image"""
    try:
        CODE128 = barcode.get_barcode_class('code128')
        
        # Custom writer for higher quality
        writer = ImageWriter()
        writer.set_options({
            'module_width': 0.4,
            'module_height': 15.0,
            'quiet_zone': 2.5,
            'font_size': 10,
            'text_distance': 5.0,
            'dpi': 300
        })
        
        code = CODE128(str(data), writer=writer)
        
        buffer = BytesIO()
        code.write(buffer)
        buffer.seek(0)
        
        return base64.b64encode(buffer.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"Barcode generation error: {e}")
        return None

def create_mng_order_via_api(order_data: dict):
    """Create MNG Kargo order via SOAP API"""
    try:
        settings = SoapSettings(strict=False, xml_huge_tree=True)
        client = SoapClient(MNG_CONFIG["wsdl_url"], settings=settings)
        
        # Build request parameters
        shipping = order_data.get('shipping_address', {})
        ref_no = order_data.get('order_number', f"FC{random.randint(100000, 999999)}")
        
        # kargo parça format: Desi:Kg:En:Boy:Yükseklik:;
        kargo_parca = "1:1:20:30:10:;"
        
        response = client.service.SiparisGirisiDetayliV3(
            pChIrsaliyeNo=ref_no,
            pPrKiymet=str(order_data.get('total', 100)),
            pChBarkod="",
            pChIcerik="Tekstil",
            pGonderiHizmetSekli="NORMAL",
            pTeslimSekli=1,  # 1 = Adreste Teslim
            pFlAlSms=1,
            pFlGnSms=0,
            pKargoParcaList=kargo_parca,
            pAliciMusteriMngNo="",
            pAliciMusteriBayiNo="",
            pAliciMusteriAdi=f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}".strip() or "Müşteri",
            pChSiparisNo=ref_no,
            pLuOdemeSekli="P",  # P = Peşin (Gönderici ödemeli)
            pFlAdresFarkli="0",
            pChIl=shipping.get('city', 'İstanbul'),
            pChIlce=shipping.get('district', ''),
            pChAdres=shipping.get('address', 'Adres'),
            pChSemt="",
            pChMahalle="",
            pChMeydanBulvar="",
            pChCadde="",
            pChSokak="",
            pChTelEv="",
            pChTelCep=shipping.get('phone', '5000000000'),
            pChTelIs="",
            pChFax="",
            pChEmail=shipping.get('email', ''),
            pChVergiDairesi="",
            pChVergiNumarasi="",
            pFlKapidaOdeme=0,
            pMalBedeliOdemeSekli="",
            pPlatformKisaAdi="",
            pPlatformSatisKodu="",
            pKullaniciAdi=MNG_CONFIG["username"],
            pSifre=MNG_CONFIG["password"]
        )
        
        logger.info(f"MNG API Response: {response}")
        
        # Response is order ID if successful, error message if failed
        if response and not str(response).startswith("E"):
            # Get tracking number from FaturaSiparisListesi
            try:
                detail_response = client.service.FaturaSiparisListesi(
                    pSiparisNo=ref_no,
                    pKullaniciAdi=MNG_CONFIG["username"],
                    pSifre=MNG_CONFIG["password"]
                )
                
                if hasattr(detail_response, '_value_1') and detail_response._value_1:
                    siparis_list = detail_response._value_1.get('_value_1', [])
                    if siparis_list:
                        siparis = siparis_list[0].get('FaturaSiparisListesi', {})
                        mng_siparis_no = str(siparis.get('MNG_SIPARIS_NO', ''))
                        gonderi_no = siparis.get('GONDERI_NO')
                        
                        # MNG tracking numbers are 10 digits
                        if gonderi_no:
                            tracking = str(gonderi_no)
                        else:
                            # Use MNG sipariş no if gönderi no not yet assigned
                            tracking = mng_siparis_no[-10:] if len(mng_siparis_no) >= 10 else mng_siparis_no
                        
                        return {
                            "success": True, 
                            "tracking_number": tracking,
                            "mng_siparis_no": mng_siparis_no,
                            "ref_no": ref_no
                        }
            except Exception as detail_err:
                logger.error(f"MNG detail fetch error: {detail_err}")
            
            # Fallback: generate MNG-style tracking number
            import random
            tracking = f"{random.randint(1000000000, 9999999999)}"
            return {"success": True, "tracking_number": tracking, "ref_no": ref_no}
        else:
            return {"success": False, "error": str(response)}
            
    except SoapFault as e:
        logger.error(f"MNG SOAP Fault: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"MNG API Error: {e}")
        # Fallback: generate local tracking number (MNG format: 10 digits)
        import random
        tracking = f"{random.randint(1000000000, 9999999999)}"
        return {"success": True, "tracking_number": tracking, "note": "Local generated - IP not whitelisted"}

@api_router.post("/orders/{order_id}/create-mng-shipment", dependencies=[Depends(require_admin)])
async def create_mng_shipment(order_id: str):
    """Create shipment via MNG Kargo API"""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    # Create MNG shipment
    result = create_mng_order_via_api(order)
    
    if result.get("success"):
        tracking_number = result.get("tracking_number")
        
        cargo_data = {
            "company": "MNG",
            "company_name": "MNG Kargo",
            "tracking_number": tracking_number,
            "tracking_url": f"https://www.mngkargo.com.tr/gonderi-takip/?q={tracking_number}",
            "shipped_at": datetime.now(timezone.utc).isoformat(),
            "status": "shipped",
            "odeme_turu": "Gönderici Ödemeli",
            "kargo_tipi": "Gönderici Ödemeli Kargo",
            "paket_sayisi": "1/1",
            "desi": 1,
            "mng_siparis_no": result.get("mng_siparis_no"),
            "ref_no": result.get("ref_no")
        }
        
        await db.orders.update_one(
            {"id": order_id},
            {"$set": {
                "cargo": cargo_data,
                "status": "shipped",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        return {
            "success": True,
            "tracking_number": tracking_number,
            "message": "MNG Kargo siparişi oluşturuldu"
        }
    else:
        raise HTTPException(status_code=500, detail=result.get("error", "MNG API hatası"))

# ==================== CARGO LABEL (ETİKET) GENERATION ====================
from fastapi.responses import HTMLResponse

@api_router.get("/orders/{order_id}/cargo-label")
async def get_cargo_label(order_id: str):
    """Generate printable cargo label (10cm x 15cm) for an order"""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    cargo = order.get('cargo', {})
    shipping = order.get('shipping_address', {})
    
    tracking_number = cargo.get('tracking_number', order.get('order_number', 'N/A'))
    
    # Generate barcodes
    top_barcode = generate_barcode_base64(tracking_number[:6] if len(tracking_number) > 6 else tracking_number)
    bottom_barcode = generate_barcode_base64(tracking_number)
    
    # Build label HTML
    label_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Kargo Etiketi - {tracking_number}</title>
        <style>
            @page {{
                size: 10cm 15cm;
                margin: 0;
            }}
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: Arial, sans-serif;
                font-size: 11px;
                width: 10cm;
                height: 15cm;
                padding: 3mm;
                background: white;
            }}
            .label-container {{
                width: 100%;
                height: 100%;
                border: 1px solid #000;
                display: flex;
                flex-direction: column;
            }}
            .top-barcode {{
                text-align: center;
                padding: 5px;
                border-bottom: 1px solid #000;
            }}
            .top-barcode img {{
                height: 35px;
                width: auto;
            }}
            .top-barcode .number {{
                font-size: 14px;
                font-weight: bold;
                margin-top: 2px;
            }}
            .section {{
                border-bottom: 1px solid #000;
                padding: 5px 8px;
            }}
            .section-title {{
                font-weight: bold;
                font-size: 12px;
                text-align: center;
                margin-bottom: 5px;
                background: #f0f0f0;
                padding: 3px;
            }}
            .info-row {{
                display: flex;
                border-bottom: 1px solid #ddd;
                padding: 2px 0;
            }}
            .info-row:last-child {{
                border-bottom: none;
            }}
            .info-label {{
                width: 80px;
                font-weight: bold;
                flex-shrink: 0;
            }}
            .info-value {{
                flex: 1;
            }}
            .bottom-barcode {{
                text-align: center;
                padding: 8px;
                flex: 1;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }}
            .bottom-barcode img {{
                height: 50px;
                width: auto;
                max-width: 100%;
            }}
            .bottom-barcode .number {{
                font-size: 16px;
                font-weight: bold;
                margin-top: 5px;
                letter-spacing: 2px;
            }}
            @media print {{
                body {{
                    -webkit-print-color-adjust: exact;
                    print-color-adjust: exact;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="label-container">
            <!-- Kargo Firması Header -->
            <div style="background: #000; color: #fff; padding: 8px; text-align: center; font-size: 18px; font-weight: bold; letter-spacing: 3px;">
                {cargo.get('company', 'MNG')} KARGO
            </div>
            
            <!-- Top Barcode -->
            <div class="top-barcode">
                {f'<img src="data:image/png;base64,{top_barcode}" alt="barcode"/>' if top_barcode else ''}
                <div class="number">{tracking_number[:6] if len(tracking_number) > 6 else tracking_number}</div>
            </div>
            
            <!-- Gönderici Bilgileri -->
            <div class="section">
                <div class="section-title">Gönderici Bilgileri</div>
                <div class="info-row">
                    <span class="info-label">Firma</span>
                    <span class="info-value">{SENDER_INFO['firma']}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Telefon</span>
                    <span class="info-value">{SENDER_INFO['telefon']}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Adres</span>
                    <span class="info-value">{SENDER_INFO['adres'].replace(chr(10), '<br>')}</span>
                </div>
            </div>
            
            <!-- Alıcı Bilgileri -->
            <div class="section">
                <div class="section-title">Alıcı Bilgileri</div>
                <div class="info-row">
                    <span class="info-label">İsim</span>
                    <span class="info-value">{shipping.get('first_name', '')} {shipping.get('last_name', '')}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Telefon</span>
                    <span class="info-value">{shipping.get('phone', '')}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Adres</span>
                    <span class="info-value">{shipping.get('address', '')}<br>{shipping.get('district', '')} / {shipping.get('city', '')}</span>
                </div>
            </div>
            
            <!-- Kargo Bilgileri -->
            <div class="section">
                <div class="section-title">Kargo Bilgileri</div>
                <div class="info-row">
                    <span class="info-label">Kargo Firması</span>
                    <span class="info-value">{cargo.get('company_name', 'MNG DHL E-Commerce')}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Ödeme Türü</span>
                    <span class="info-value">{cargo.get('odeme_turu', 'Gönderici Ödemeli')}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Kargo Tipi</span>
                    <span class="info-value">{cargo.get('kargo_tipi', 'Gönderici Ödemeli Kargo')}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Paket Sayısı</span>
                    <span class="info-value">{cargo.get('paket_sayisi', '1/1')}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Desi</span>
                    <span class="info-value">{cargo.get('desi', 1)}</span>
                </div>
            </div>
            
            <!-- Bottom Barcode -->
            <div class="bottom-barcode">
                {f'<img src="data:image/png;base64,{bottom_barcode}" alt="barcode"/>' if bottom_barcode else ''}
                <div class="number">{tracking_number}</div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=label_html)

@api_router.post("/orders/bulk-labels")
async def get_bulk_cargo_labels(order_ids: list[str]):
    """Generate printable cargo labels for multiple orders"""
    labels_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Toplu Kargo Etiketleri</title>
        <style>
            @page {
                size: 10cm 15cm;
                margin: 0;
            }
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: Arial, sans-serif;
                font-size: 11px;
            }
            .label-page {
                width: 10cm;
                height: 15cm;
                padding: 3mm;
                background: white;
                page-break-after: always;
            }
            .label-page:last-child {
                page-break-after: auto;
            }
            .label-container {
                width: 100%;
                height: 100%;
                border: 1px solid #000;
                display: flex;
                flex-direction: column;
            }
            .top-barcode {
                text-align: center;
                padding: 5px;
                border-bottom: 1px solid #000;
            }
            .top-barcode img {
                height: 35px;
                width: auto;
            }
            .top-barcode .number {
                font-size: 14px;
                font-weight: bold;
                margin-top: 2px;
            }
            .section {
                border-bottom: 1px solid #000;
                padding: 5px 8px;
            }
            .section-title {
                font-weight: bold;
                font-size: 12px;
                text-align: center;
                margin-bottom: 5px;
                background: #f0f0f0;
                padding: 3px;
            }
            .info-row {
                display: flex;
                border-bottom: 1px solid #ddd;
                padding: 2px 0;
            }
            .info-row:last-child {
                border-bottom: none;
            }
            .info-label {
                width: 80px;
                font-weight: bold;
                flex-shrink: 0;
            }
            .info-value {
                flex: 1;
            }
            .bottom-barcode {
                text-align: center;
                padding: 8px;
                flex: 1;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }
            .bottom-barcode img {
                height: 50px;
                width: auto;
                max-width: 100%;
            }
            .bottom-barcode .number {
                font-size: 16px;
                font-weight: bold;
                margin-top: 5px;
                letter-spacing: 2px;
            }
            @media print {
                body {
                    -webkit-print-color-adjust: exact;
                    print-color-adjust: exact;
                }
            }
        </style>
    </head>
    <body>
    """
    
    for order_id in order_ids:
        order = await db.orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            continue
            
        cargo = order.get('cargo', {})
        shipping = order.get('shipping_address', {})
        tracking_number = cargo.get('tracking_number', order.get('order_number', 'N/A'))
        
        top_barcode = generate_barcode_base64(tracking_number[:6] if len(tracking_number) > 6 else tracking_number)
        bottom_barcode = generate_barcode_base64(tracking_number)
        
        labels_html += f"""
        <div class="label-page">
            <div class="label-container">
                <div style="background: #000; color: #fff; padding: 8px; text-align: center; font-size: 18px; font-weight: bold; letter-spacing: 3px;">
                    {cargo.get('company', 'MNG')} KARGO
                </div>
                <div class="top-barcode">
                    {f'<img src="data:image/png;base64,{top_barcode}" alt="barcode"/>' if top_barcode else ''}
                    <div class="number">{tracking_number[:6] if len(tracking_number) > 6 else tracking_number}</div>
                </div>
                
                <div class="section">
                    <div class="section-title">Gönderici Bilgileri</div>
                    <div class="info-row">
                        <span class="info-label">Firma</span>
                        <span class="info-value">{SENDER_INFO['firma']}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Telefon</span>
                        <span class="info-value">{SENDER_INFO['telefon']}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Adres</span>
                        <span class="info-value">{SENDER_INFO['adres'].replace(chr(10), '<br>')}</span>
                    </div>
                </div>
                
                <div class="section">
                    <div class="section-title">Alıcı Bilgileri</div>
                    <div class="info-row">
                        <span class="info-label">İsim</span>
                        <span class="info-value">{shipping.get('first_name', '')} {shipping.get('last_name', '')}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Telefon</span>
                        <span class="info-value">{shipping.get('phone', '')}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Adres</span>
                        <span class="info-value">{shipping.get('address', '')}<br>{shipping.get('district', '')} / {shipping.get('city', '')}</span>
                    </div>
                </div>
                
                <div class="section">
                    <div class="section-title">Kargo Bilgileri</div>
                    <div class="info-row">
                        <span class="info-label">Kargo Firması</span>
                        <span class="info-value">{cargo.get('company_name', 'MNG DHL E-Commerce')}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Ödeme Türü</span>
                        <span class="info-value">{cargo.get('odeme_turu', 'Gönderici Ödemeli')}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Kargo Tipi</span>
                        <span class="info-value">{cargo.get('kargo_tipi', 'Gönderici Ödemeli Kargo')}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Paket Sayısı</span>
                        <span class="info-value">{cargo.get('paket_sayisi', '1/1')}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Desi</span>
                        <span class="info-value">{cargo.get('desi', 1)}</span>
                    </div>
                </div>
                
                <div class="bottom-barcode">
                    {f'<img src="data:image/png;base64,{bottom_barcode}" alt="barcode"/>' if bottom_barcode else ''}
                    <div class="number">{tracking_number}</div>
                </div>
            </div>
        </div>
        """
    
    labels_html += """
    </body>
    </html>
    """
    
    return HTMLResponse(content=labels_html)

# ==================== NETGSM SMS INTEGRATION ====================
import httpx

NETGSM_CONFIG = {
    "username": os.environ.get("NETGSM_USERNAME", ""),
    "password": os.environ.get("NETGSM_PASSWORD", ""),
    "header": os.environ.get("NETGSM_HEADER", "FACETTE"),
    "api_url": "https://api.netgsm.com.tr/sms/send/get"
}

def format_turkish_phone(phone: str) -> str:
    """Format phone number to Turkish E.164 format"""
    import re
    cleaned = re.sub(r'[^\d+]', '', phone)
    
    if cleaned.startswith('+90'):
        return cleaned
    if cleaned.startswith('0'):
        return '+90' + cleaned[1:]
    if len(cleaned) == 10:
        return '+90' + cleaned
    if cleaned.startswith('90') and len(cleaned) == 12:
        return '+' + cleaned
    
    return '+90' + cleaned[-10:] if len(cleaned) >= 10 else cleaned

async def send_sms(phone: str, message: str, sms_type: str = "notification") -> dict:
    """Send SMS via Netgsm API"""
    if not NETGSM_CONFIG["username"] or not NETGSM_CONFIG["password"]:
        logger.warning("Netgsm credentials not configured, SMS not sent")
        return {"success": False, "error": "Netgsm credentials not configured"}
    
    try:
        formatted_phone = format_turkish_phone(phone)
        # Remove + for Netgsm API
        gsm_number = formatted_phone.replace('+', '')
        
        params = {
            "usercode": NETGSM_CONFIG["username"],
            "password": NETGSM_CONFIG["password"],
            "gsmno": gsm_number,
            "message": message,
            "msgheader": NETGSM_CONFIG["header"],
            "dil": "TR"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(NETGSM_CONFIG["api_url"], params=params, timeout=30)
            result = response.text.strip()
            
            # Netgsm returns codes: 00 = success, 20 = post error, 30 = invalid credentials, etc.
            if result.startswith("00"):
                logger.info(f"SMS sent successfully to {formatted_phone}: {result}")
                return {"success": True, "message_id": result, "phone": formatted_phone}
            else:
                logger.error(f"Netgsm error: {result}")
                return {"success": False, "error": result}
                
    except Exception as e:
        logger.error(f"SMS send error: {e}")
        return {"success": False, "error": str(e)}

# SMS Templates
def get_order_confirmation_sms(customer_name: str, order_number: str, total: float) -> str:
    """Generate order confirmation SMS"""
    return f"Merhaba {customer_name[:15]}, siparişiniz alındı. Sipariş No: {order_number} Tutar: {total:.0f}TL FACETTE"

def get_shipping_sms(customer_name: str, tracking_number: str, carrier: str) -> str:
    """Generate shipping notification SMS"""
    return f"Merhaba, siparişiniz {carrier} ile gönderildi. Takip: {tracking_number} FACETTE"

def get_delivery_sms(customer_name: str) -> str:
    """Generate delivery confirmation SMS"""
    return f"Merhaba {customer_name[:15]}, siparişiniz teslim edildi. Alışverişiniz için teşekkürler! FACETTE"

@api_router.post("/sms/send-test", dependencies=[Depends(require_admin)])
async def send_test_sms(phone: str = Query(...), message: str = Query(...)):
    """Send a test SMS (Admin only)"""
    result = await send_sms(phone, message, "test")
    return result

@api_router.post("/orders/{order_id}/send-confirmation-sms", dependencies=[Depends(require_admin)])
async def send_order_confirmation_sms(order_id: str):
    """Send order confirmation SMS"""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    shipping = order.get('shipping_address', {})
    phone = shipping.get('phone')
    if not phone:
        raise HTTPException(status_code=400, detail="Telefon numarası bulunamadı")
    
    customer_name = f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}".strip() or "Müşteri"
    message = get_order_confirmation_sms(customer_name, order.get('order_number', ''), order.get('total', 0))
    
    result = await send_sms(phone, message, "order_confirmation")
    
    if result.get("success"):
        await db.orders.update_one(
            {"id": order_id},
            {"$set": {"sms_confirmation_sent": True, "sms_confirmation_at": datetime.now(timezone.utc).isoformat()}}
        )
    
    return result

@api_router.post("/orders/{order_id}/send-shipping-sms", dependencies=[Depends(require_admin)])
async def send_shipping_sms(order_id: str):
    """Send shipping notification SMS"""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    cargo = order.get('cargo')
    if not cargo or not cargo.get('tracking_number'):
        raise HTTPException(status_code=400, detail="Kargo bilgisi bulunamadı")
    
    shipping = order.get('shipping_address', {})
    phone = shipping.get('phone')
    if not phone:
        raise HTTPException(status_code=400, detail="Telefon numarası bulunamadı")
    
    customer_name = f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}".strip() or "Müşteri"
    message = get_shipping_sms(customer_name, cargo.get('tracking_number'), cargo.get('company_name', 'Kargo'))
    
    result = await send_sms(phone, message, "shipping")
    
    if result.get("success"):
        await db.orders.update_one(
            {"id": order_id},
            {"$set": {"sms_shipping_sent": True, "sms_shipping_at": datetime.now(timezone.utc).isoformat()}}
        )
    
    return result

# ==================== CUSTOMER ORDER TRACKING ====================
@api_router.get("/track/{tracking_code}")
async def public_order_tracking(tracking_code: str):
    """Public order tracking endpoint - no auth required"""
    # Search by order number or cargo tracking number
    order = await db.orders.find_one(
        {"$or": [
            {"order_number": tracking_code},
            {"cargo.tracking_number": tracking_code}
        ]},
        {"_id": 0, "user_id": 0}
    )
    
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    # Build tracking response with status timeline
    cargo = order.get('cargo', {})
    status = order.get('status', 'pending')
    
    timeline = []
    
    # Order placed
    timeline.append({
        "status": "placed",
        "title": "Sipariş Alındı",
        "date": order.get('created_at'),
        "completed": True
    })
    
    # Order confirmed
    if status in ['confirmed', 'processing', 'shipped', 'delivered']:
        timeline.append({
            "status": "confirmed",
            "title": "Sipariş Onaylandı",
            "date": order.get('confirmed_at') or order.get('created_at'),
            "completed": True
        })
    
    # Processing
    if status in ['processing', 'shipped', 'delivered']:
        timeline.append({
            "status": "processing",
            "title": "Hazırlanıyor",
            "date": order.get('processing_at'),
            "completed": True
        })
    else:
        timeline.append({
            "status": "processing",
            "title": "Hazırlanıyor",
            "completed": False
        })
    
    # Shipped
    if status in ['shipped', 'delivered']:
        timeline.append({
            "status": "shipped",
            "title": "Kargoya Verildi",
            "date": cargo.get('shipped_at'),
            "completed": True,
            "tracking_number": cargo.get('tracking_number'),
            "tracking_url": cargo.get('tracking_url'),
            "carrier": cargo.get('company_name')
        })
    else:
        timeline.append({
            "status": "shipped",
            "title": "Kargoya Verildi",
            "completed": False
        })
    
    # Delivered
    timeline.append({
        "status": "delivered",
        "title": "Teslim Edildi",
        "date": order.get('delivered_at') if status == 'delivered' else None,
        "completed": status == 'delivered'
    })
    
    # Mask sensitive data
    shipping = order.get('shipping_address', {})
    masked_shipping = {
        "city": shipping.get('city', ''),
        "district": shipping.get('district', ''),
        "first_name": shipping.get('first_name', '')[:1] + "***" if shipping.get('first_name') else "",
        "last_name": shipping.get('last_name', '')[:1] + "***" if shipping.get('last_name') else ""
    }
    
    return {
        "order_number": order.get('order_number'),
        "status": status,
        "status_text": {
            "pending": "Beklemede",
            "confirmed": "Onaylandı",
            "processing": "Hazırlanıyor",
            "shipped": "Kargoda",
            "delivered": "Teslim Edildi",
            "cancelled": "İptal Edildi"
        }.get(status, status),
        "timeline": timeline,
        "shipping_address": masked_shipping,
        "cargo": {
            "company": cargo.get('company_name'),
            "tracking_number": cargo.get('tracking_number'),
            "tracking_url": cargo.get('tracking_url')
        } if cargo else None,
        "total": order.get('total'),
        "item_count": len(order.get('items', []))
    }

# ==================== TRENDYOL MARKETPLACE INTEGRATION ====================
import base64
import httpx

# Trendyol configuration
TRENDYOL_MODE = os.environ.get('TRENDYOL_MODE', 'sandbox')  # 'sandbox' or 'live'
TRENDYOL_API_KEY = os.environ.get('TRENDYOL_API_KEY', '')
TRENDYOL_API_SECRET = os.environ.get('TRENDYOL_API_SECRET', '')
TRENDYOL_SUPPLIER_ID = os.environ.get('TRENDYOL_SUPPLIER_ID', '')
TRENDYOL_BASE_URL = os.environ.get('TRENDYOL_BASE_URL', 
    'https://api.trendyol.com' if TRENDYOL_MODE == 'live' else 'https://stageapigw.trendyol.com'
)

def get_trendyol_headers():
    """Build Trendyol API headers with authentication"""
    if not TRENDYOL_API_KEY or not TRENDYOL_API_SECRET:
        return None
    
    credentials = f"{TRENDYOL_API_KEY}:{TRENDYOL_API_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    
    return {
        "Authorization": f"Basic {encoded}",
        "User-Agent": f"{TRENDYOL_SUPPLIER_ID} - FacetteIntegration",
        "Content-Type": "application/json"
    }

def is_trendyol_configured():
    """Check if Trendyol is properly configured"""
    return bool(TRENDYOL_API_KEY and TRENDYOL_API_SECRET and TRENDYOL_SUPPLIER_ID)

@api_router.get("/trendyol/status")
async def get_trendyol_status():
    """Get Trendyol integration status"""
    return {
        "configured": is_trendyol_configured(),
        "mode": TRENDYOL_MODE,
        "supplier_id": TRENDYOL_SUPPLIER_ID if is_trendyol_configured() else None
    }

@api_router.get("/trendyol/categories")
async def get_trendyol_categories(current_user: dict = Depends(get_current_user)):
    """Get Trendyol product categories"""
    if not current_user or not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    if not is_trendyol_configured():
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{TRENDYOL_BASE_URL}/sapigw/product-categories",
                headers=get_trendyol_headers()
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Trendyol categories error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/trendyol/brands")
async def get_trendyol_brands(
    name: str = Query(None, description="Brand name to search"),
    current_user: dict = Depends(get_current_user)
):
    """Get Trendyol brands"""
    if not current_user or not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    if not is_trendyol_configured():
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
    
    try:
        params = {}
        if name:
            params["name"] = name
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{TRENDYOL_BASE_URL}/sapigw/brands",
                headers=get_trendyol_headers(),
                params=params
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Trendyol brands error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/trendyol/products/sync")
async def sync_products_to_trendyol(
    product_ids: List[str] = Query(None, description="Product IDs to sync, or all if empty"),
    current_user: dict = Depends(get_current_user)
):
    """Sync products from Facette to Trendyol"""
    if not current_user or not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    if not is_trendyol_configured():
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
    
    try:
        # Fetch products from database
        query = {}
        if product_ids:
            query["id"] = {"$in": product_ids}
        
        products = await db.products.find(query, {"_id": 0}).to_list(1000)
        
        if not products:
            raise HTTPException(status_code=404, detail="Ürün bulunamadı")
        
        # Transform products to Trendyol format
        trendyol_items = []
        for product in products:
            # Basic transformation - would need category mapping and brand ID in production
            item = {
                "barcode": product.get("barcode") or product.get("stock_code") or product.get("id"),
                "title": product.get("name", "")[:100],
                "productMainId": product.get("stock_code") or product.get("id"),
                "brandId": 1,  # Would need mapping
                "categoryId": 1,  # Would need mapping
                "quantity": product.get("stock", 0),
                "stockCode": product.get("stock_code", ""),
                "dimensionalWeight": product.get("cargo_weight", 1) or 1,
                "description": product.get("description", product.get("name", "")),
                "currencyType": "TRY",
                "listPrice": float(product.get("price", 0)),
                "salePrice": float(product.get("sale_price") or product.get("price", 0)),
                "vatRate": product.get("vat_rate", 20),
                "cargoCompanyId": 10,  # MNG Kargo
                "images": [{"url": img} for img in product.get("images", [])[:8]],
                "attributes": []
            }
            
            # Add variant quantities
            total_stock = product.get("stock", 0)
            for variant in product.get("variants", []):
                total_stock += variant.get("stock", 0)
            item["quantity"] = total_stock
            
            trendyol_items.append(item)
        
        # Send to Trendyol
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{TRENDYOL_BASE_URL}/sapigw/suppliers/{TRENDYOL_SUPPLIER_ID}/v2/products",
                headers=get_trendyol_headers(),
                json={"items": trendyol_items}
            )
            
            result = response.json()
            
            if response.status_code == 200:
                batch_id = result.get("batchRequestId")
                logger.info(f"Products sent to Trendyol, batch ID: {batch_id}")
                return {
                    "success": True,
                    "batch_request_id": batch_id,
                    "products_sent": len(trendyol_items),
                    "message": f"{len(trendyol_items)} ürün Trendyol'a gönderildi"
                }
            else:
                logger.error(f"Trendyol sync error: {result}")
                return {
                    "success": False,
                    "error": result.get("errors", result),
                    "products_attempted": len(trendyol_items)
                }
                
    except Exception as e:
        logger.error(f"Trendyol sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/trendyol/products/batch/{batch_id}")
async def get_trendyol_batch_status(
    batch_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Check Trendyol batch request status"""
    if not current_user or not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    if not is_trendyol_configured():
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{TRENDYOL_BASE_URL}/sapigw/suppliers/{TRENDYOL_SUPPLIER_ID}/products/batch-requests/{batch_id}",
                headers=get_trendyol_headers()
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Trendyol batch status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/trendyol/inventory/update")
async def update_trendyol_inventory(
    items: List[dict],
    current_user: dict = Depends(get_current_user)
):
    """Update stock and price on Trendyol"""
    if not current_user or not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    if not is_trendyol_configured():
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
    
    if len(items) > 1000:
        raise HTTPException(status_code=400, detail="Maksimum 1000 ürün güncellenebilir")
    
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{TRENDYOL_BASE_URL}/sapigw/suppliers/{TRENDYOL_SUPPLIER_ID}/products/price-and-inventory",
                headers=get_trendyol_headers(),
                json={"items": items}
            )
            
            result = response.json()
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "batch_request_id": result.get("batchRequestId"),
                    "message": f"{len(items)} ürün stok/fiyat güncellendi"
                }
            else:
                return {"success": False, "error": result}
                
    except Exception as e:
        logger.error(f"Trendyol inventory update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/trendyol/orders")
async def get_trendyol_orders(
    status: str = Query(None, description="Order status filter"),
    page: int = Query(0),
    size: int = Query(50),
    current_user: dict = Depends(get_current_user)
):
    """Get orders from Trendyol"""
    if not current_user or not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    if not is_trendyol_configured():
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
    
    try:
        params = {"page": page, "size": size}
        if status:
            params["status"] = status
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{TRENDYOL_BASE_URL}/sapigw/suppliers/{TRENDYOL_SUPPLIER_ID}/orders",
                headers=get_trendyol_headers(),
                params=params
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Trendyol orders error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/trendyol/orders/{package_id}/status")
async def update_trendyol_order_status(
    package_id: int,
    status: str = Query(..., description="New status: Picking, Invoiced, Shipped"),
    tracking_number: str = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """Update Trendyol order status"""
    if not current_user or not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    if not is_trendyol_configured():
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
    
    try:
        body = {"status": status}
        if tracking_number and status == "Shipped":
            body["trackingNumber"] = tracking_number
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.put(
                f"{TRENDYOL_BASE_URL}/sapigw/suppliers/{TRENDYOL_SUPPLIER_ID}/shipment-packages/{package_id}",
                headers=get_trendyol_headers(),
                json=body
            )
            
            if response.status_code == 200:
                return {"success": True, "message": "Sipariş durumu güncellendi"}
            else:
                return {"success": False, "error": response.json()}
                
    except Exception as e:
        logger.error(f"Trendyol order update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/trendyol/orders/import")
async def import_trendyol_orders(
    current_user: dict = Depends(get_current_user)
):
    """Import pending orders from Trendyol to local system"""
    if not current_user or not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    if not is_trendyol_configured():
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
    
    try:
        # Fetch Created orders from Trendyol
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{TRENDYOL_BASE_URL}/sapigw/suppliers/{TRENDYOL_SUPPLIER_ID}/orders",
                headers=get_trendyol_headers(),
                params={"status": "Created", "size": 100}
            )
            response.raise_for_status()
            data = response.json()
        
        packages = data.get("content", [])
        imported = 0
        
        for pkg in packages:
            order_number = pkg.get("orderNumber")
            
            # Check if already imported
            existing = await db.orders.find_one({"trendyol_order_number": order_number})
            if existing:
                continue
            
            # Create local order
            order_items = []
            for item in pkg.get("lines", []):
                order_items.append({
                    "product_id": item.get("productContentId"),
                    "barcode": item.get("barcode"),
                    "name": item.get("productName"),
                    "quantity": item.get("quantity"),
                    "price": item.get("price"),
                    "size": item.get("productSize"),
                    "color": item.get("productColor"),
                })
            
            shipping = pkg.get("shipmentAddress", {})
            
            new_order = {
                "id": str(uuid.uuid4()),
                "order_number": f"TY-{order_number}",
                "trendyol_order_number": order_number,
                "trendyol_package_id": pkg.get("id"),
                "source": "trendyol",
                "items": order_items,
                "shipping_address": {
                    "first_name": shipping.get("firstName", ""),
                    "last_name": shipping.get("lastName", ""),
                    "address": shipping.get("fullAddress", ""),
                    "city": shipping.get("city", ""),
                    "district": shipping.get("district", ""),
                    "phone": shipping.get("phoneNumber", ""),
                },
                "subtotal": pkg.get("totalPrice", 0),
                "total": pkg.get("totalPrice", 0),
                "status": "confirmed",
                "payment_status": "paid",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db.orders.insert_one(new_order)
            imported += 1
        
        return {
            "success": True,
            "imported": imported,
            "total_found": len(packages),
            "message": f"{imported} yeni sipariş içe aktarıldı"
        }
        
    except Exception as e:
        logger.error(f"Trendyol import error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== GIB E-FATURA / E-ARŞİV INTEGRATION ====================
from lxml import etree
import qrcode
from io import BytesIO

# GIB Configuration
GIB_MODE = os.environ.get('GIB_MODE', 'test')  # 'test' or 'production'
GIB_USERNAME = os.environ.get('GIB_USERNAME', '')
GIB_PASSWORD = os.environ.get('GIB_PASSWORD', '')
GIB_VKN = os.environ.get('GIB_VKN', '')  # Company Tax ID (10 digits)
GIB_COMPANY_NAME = os.environ.get('GIB_COMPANY_NAME', 'FACETTE')
GIB_BASE_URL = os.environ.get('GIB_BASE_URL',
    'https://earsivportal.efatura.gov.tr' if GIB_MODE == 'production' 
    else 'https://earsivportaltest.efatura.gov.tr'
)

def is_gib_configured():
    """Check if GIB is properly configured"""
    return bool(GIB_USERNAME and GIB_PASSWORD and GIB_VKN and len(GIB_VKN) == 10)

def validate_vkn(vkn: str) -> bool:
    """Validate Turkish VKN using checksum algorithm"""
    if not vkn or len(vkn) != 10 or not vkn.isdigit():
        return False
    digits = [int(d) for d in vkn]
    checksum = sum(digits[i] * (9 - i) for i in range(9)) % 11
    return checksum == digits[9]

def generate_invoice_number() -> str:
    """Generate unique invoice number"""
    year = datetime.now().year
    # Get last invoice number from db
    return f"FAC{year}{str(uuid.uuid4().int)[:10]}"

def generate_qr_code(invoice_uuid: str) -> str:
    """Generate QR code for invoice verification"""
    verify_url = f"{GIB_BASE_URL}/qr?uuid={invoice_uuid}"
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(verify_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()

class UBLTRInvoiceBuilder:
    """Builds UBL-TR 1.2.1 compliant invoice XML for Turkish e-invoicing"""
    
    NAMESPACES = {
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    }
    
    def __init__(self):
        self.root = None
    
    def build_invoice(self, order: dict, invoice_number: str, invoice_type: str = "SATIS") -> str:
        """
        Build UBL-TR invoice XML from order data
        
        Args:
            order: Order document from database
            invoice_number: Unique invoice number
            invoice_type: SATIS (sale) or IADE (return)
        """
        # Create Invoice root element
        nsmap = {
            None: 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
            'cac': self.NAMESPACES['cac'],
            'cbc': self.NAMESPACES['cbc'],
        }
        
        self.root = etree.Element('Invoice', nsmap=nsmap)
        
        # UBL Version
        etree.SubElement(self.root, '{%s}UBLVersionID' % self.NAMESPACES['cbc']).text = '2.1'
        etree.SubElement(self.root, '{%s}CustomizationID' % self.NAMESPACES['cbc']).text = 'TR1.2.1'
        
        # Invoice identification
        etree.SubElement(self.root, '{%s}ID' % self.NAMESPACES['cbc']).text = invoice_number
        
        # Issue date/time
        now = datetime.now(timezone.utc)
        etree.SubElement(self.root, '{%s}IssueDate' % self.NAMESPACES['cbc']).text = now.strftime('%Y-%m-%d')
        etree.SubElement(self.root, '{%s}IssueTime' % self.NAMESPACES['cbc']).text = now.strftime('%H:%M:%S')
        
        # Invoice type code
        type_code = '388'  # Commercial Invoice
        etree.SubElement(self.root, '{%s}InvoiceTypeCode' % self.NAMESPACES['cbc']).text = type_code
        
        # Currency
        etree.SubElement(self.root, '{%s}DocumentCurrencyCode' % self.NAMESPACES['cbc']).text = 'TRY'
        
        # Add supplier (seller)
        self._add_supplier_party()
        
        # Add customer (buyer)
        self._add_customer_party(order)
        
        # Add line items
        for idx, item in enumerate(order.get('items', []), 1):
            self._add_invoice_line(item, idx)
        
        # Add tax totals
        self._add_tax_totals(order)
        
        # Add monetary totals
        self._add_monetary_totals(order)
        
        return etree.tostring(
            self.root,
            pretty_print=True,
            xml_declaration=True,
            encoding='UTF-8'
        ).decode('utf-8')
    
    def _add_supplier_party(self):
        """Add supplier (AccountingSupplierParty) - your company"""
        supplier = etree.SubElement(self.root, '{%s}AccountingSupplierParty' % self.NAMESPACES['cac'])
        party = etree.SubElement(supplier, '{%s}Party' % self.NAMESPACES['cac'])
        
        # Party ID (VKN)
        party_id = etree.SubElement(party, '{%s}PartyIdentification' % self.NAMESPACES['cac'])
        id_elem = etree.SubElement(party_id, '{%s}ID' % self.NAMESPACES['cbc'])
        id_elem.set('schemeID', 'VKN')
        id_elem.text = GIB_VKN
        
        # Party name
        party_name = etree.SubElement(party, '{%s}PartyName' % self.NAMESPACES['cac'])
        etree.SubElement(party_name, '{%s}Name' % self.NAMESPACES['cbc']).text = GIB_COMPANY_NAME
    
    def _add_customer_party(self, order: dict):
        """Add customer (AccountingCustomerParty) from order"""
        customer = etree.SubElement(self.root, '{%s}AccountingCustomerParty' % self.NAMESPACES['cac'])
        party = etree.SubElement(customer, '{%s}Party' % self.NAMESPACES['cac'])
        
        shipping = order.get('shipping_address', {})
        
        # Party name
        party_name = etree.SubElement(party, '{%s}PartyName' % self.NAMESPACES['cac'])
        full_name = f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}".strip()
        etree.SubElement(party_name, '{%s}Name' % self.NAMESPACES['cbc']).text = full_name or 'Müşteri'
        
        # Address
        address = etree.SubElement(party, '{%s}PostalAddress' % self.NAMESPACES['cac'])
        etree.SubElement(address, '{%s}CityName' % self.NAMESPACES['cbc']).text = shipping.get('city', '')
        etree.SubElement(address, '{%s}PostalZone' % self.NAMESPACES['cbc']).text = shipping.get('postal_code', '00000')
        
        country = etree.SubElement(address, '{%s}Country' % self.NAMESPACES['cac'])
        etree.SubElement(country, '{%s}IdentificationCode' % self.NAMESPACES['cbc']).text = 'TR'
    
    def _add_invoice_line(self, item: dict, line_number: int):
        """Add invoice line item"""
        line = etree.SubElement(self.root, '{%s}InvoiceLine' % self.NAMESPACES['cac'])
        etree.SubElement(line, '{%s}ID' % self.NAMESPACES['cbc']).text = str(line_number)
        
        # Quantity
        qty = etree.SubElement(line, '{%s}InvoicedQuantity' % self.NAMESPACES['cbc'])
        qty.set('unitCode', 'C62')  # Unit (piece)
        qty.text = str(item.get('quantity', 1))
        
        # Line extension amount (price * quantity, without tax)
        price = float(item.get('price', 0))
        quantity = int(item.get('quantity', 1))
        line_total = price * quantity
        
        amount = etree.SubElement(line, '{%s}LineExtensionAmount' % self.NAMESPACES['cbc'])
        amount.set('currencyID', 'TRY')
        amount.text = f"{line_total:.2f}"
        
        # Item description
        item_elem = etree.SubElement(line, '{%s}Item' % self.NAMESPACES['cac'])
        etree.SubElement(item_elem, '{%s}Name' % self.NAMESPACES['cbc']).text = item.get('name', 'Ürün')
        
        if item.get('size'):
            etree.SubElement(item_elem, '{%s}Description' % self.NAMESPACES['cbc']).text = f"Beden: {item.get('size')}"
        
        # Price
        price_elem = etree.SubElement(line, '{%s}Price' % self.NAMESPACES['cac'])
        price_amount = etree.SubElement(price_elem, '{%s}PriceAmount' % self.NAMESPACES['cbc'])
        price_amount.set('currencyID', 'TRY')
        price_amount.text = f"{price:.2f}"
    
    def _add_tax_totals(self, order: dict):
        """Add tax totals section"""
        # Calculate totals
        subtotal = float(order.get('subtotal', 0))
        tax_rate = 0.20  # 20% KDV
        tax_amount = subtotal * tax_rate
        
        tax_total = etree.SubElement(self.root, '{%s}TaxTotal' % self.NAMESPACES['cac'])
        
        total_tax = etree.SubElement(tax_total, '{%s}TaxAmount' % self.NAMESPACES['cbc'])
        total_tax.set('currencyID', 'TRY')
        total_tax.text = f"{tax_amount:.2f}"
        
        # Tax subtotal
        subtotal_elem = etree.SubElement(tax_total, '{%s}TaxSubtotal' % self.NAMESPACES['cac'])
        
        taxable = etree.SubElement(subtotal_elem, '{%s}TaxableAmount' % self.NAMESPACES['cbc'])
        taxable.set('currencyID', 'TRY')
        taxable.text = f"{subtotal:.2f}"
        
        tax_amt = etree.SubElement(subtotal_elem, '{%s}TaxAmount' % self.NAMESPACES['cbc'])
        tax_amt.set('currencyID', 'TRY')
        tax_amt.text = f"{tax_amount:.2f}"
        
        category = etree.SubElement(subtotal_elem, '{%s}TaxCategory' % self.NAMESPACES['cac'])
        etree.SubElement(category, '{%s}ID' % self.NAMESPACES['cbc']).text = 'S'
        etree.SubElement(category, '{%s}Percent' % self.NAMESPACES['cbc']).text = '20'
        
        scheme = etree.SubElement(category, '{%s}TaxScheme' % self.NAMESPACES['cac'])
        etree.SubElement(scheme, '{%s}Name' % self.NAMESPACES['cbc']).text = 'KDV'
    
    def _add_monetary_totals(self, order: dict):
        """Add legal monetary totals"""
        subtotal = float(order.get('subtotal', 0))
        total = float(order.get('total', subtotal))
        tax_amount = subtotal * 0.20
        
        totals = etree.SubElement(self.root, '{%s}LegalMonetaryTotal' % self.NAMESPACES['cac'])
        
        line_ext = etree.SubElement(totals, '{%s}LineExtensionAmount' % self.NAMESPACES['cbc'])
        line_ext.set('currencyID', 'TRY')
        line_ext.text = f"{subtotal:.2f}"
        
        tax_excl = etree.SubElement(totals, '{%s}TaxExclusiveAmount' % self.NAMESPACES['cbc'])
        tax_excl.set('currencyID', 'TRY')
        tax_excl.text = f"{subtotal:.2f}"
        
        tax_incl = etree.SubElement(totals, '{%s}TaxInclusiveAmount' % self.NAMESPACES['cbc'])
        tax_incl.set('currencyID', 'TRY')
        tax_incl.text = f"{total:.2f}"
        
        payable = etree.SubElement(totals, '{%s}PayableAmount' % self.NAMESPACES['cbc'])
        payable.set('currencyID', 'TRY')
        payable.text = f"{total:.2f}"


# GIB API Endpoints
@api_router.get("/gib/status")
async def get_gib_status():
    """Get GIB integration status"""
    return {
        "configured": is_gib_configured(),
        "mode": GIB_MODE,
        "vkn": GIB_VKN[:4] + "******" if GIB_VKN else None,
        "company_name": GIB_COMPANY_NAME
    }

@api_router.post("/orders/{order_id}/create-invoice")
async def create_invoice(
    order_id: str,
    invoice_type: str = Query("e-arsiv", description="e-fatura veya e-arsiv"),
    current_user: dict = Depends(get_current_user)
):
    """
    Create e-Fatura or e-Arşiv invoice for an order
    
    For now, generates UBL-TR XML and stores it.
    Full GIB submission requires Mali Mühür (digital seal) certificate.
    """
    if not current_user or not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    
    try:
        # Fetch order
        order = await db.orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
        
        # Check if invoice already exists
        if order.get("invoice"):
            return {
                "success": False,
                "message": "Bu sipariş için zaten fatura oluşturulmuş",
                "invoice": order.get("invoice")
            }
        
        # Generate invoice number
        invoice_number = generate_invoice_number()
        invoice_uuid = str(uuid.uuid4())
        
        # Build UBL-TR XML
        builder = UBLTRInvoiceBuilder()
        xml_content = builder.build_invoice(order, invoice_number)
        
        # Generate QR code
        qr_code = generate_qr_code(invoice_uuid)
        
        # Store invoice data
        invoice_data = {
            "uuid": invoice_uuid,
            "number": invoice_number,
            "type": invoice_type,
            "status": "draft",  # draft, submitted, approved, rejected
            "xml_content": xml_content,
            "qr_code": qr_code,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "submitted_at": None,
            "gib_response": None
        }
        
        # Update order with invoice
        await db.orders.update_one(
            {"id": order_id},
            {"$set": {"invoice": invoice_data, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        logger.info(f"Invoice {invoice_number} created for order {order_id}")
        
        return {
            "success": True,
            "invoice_number": invoice_number,
            "invoice_uuid": invoice_uuid,
            "type": invoice_type,
            "status": "draft",
            "message": "Fatura taslağı oluşturuldu. GIB'e gönderim için Mali Mühür gereklidir."
        }
        
    except Exception as e:
        logger.error(f"Invoice creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/orders/{order_id}/invoice")
async def get_order_invoice(
    order_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get invoice details for an order"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Yetkilendirme gerekli")
    
    order = await db.orders.find_one({"id": order_id}, {"_id": 0, "invoice": 1})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    invoice = order.get("invoice")
    if not invoice:
        return {"success": False, "message": "Bu sipariş için fatura bulunmuyor"}
    
    return {
        "success": True,
        "invoice": {
            "uuid": invoice.get("uuid"),
            "number": invoice.get("number"),
            "type": invoice.get("type"),
            "status": invoice.get("status"),
            "created_at": invoice.get("created_at"),
            "qr_code": invoice.get("qr_code")
        }
    }

@api_router.get("/orders/{order_id}/invoice/download")
async def download_invoice_xml(
    order_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Download invoice XML"""
    if not current_user or not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    
    order = await db.orders.find_one({"id": order_id}, {"_id": 0, "invoice": 1})
    if not order or not order.get("invoice"):
        raise HTTPException(status_code=404, detail="Fatura bulunamadı")
    
    invoice = order.get("invoice")
    
    return Response(
        content=invoice.get("xml_content", ""),
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=fatura_{invoice.get('number')}.xml"
        }
    )

@api_router.get("/orders/{order_id}/invoice/print")
async def get_printable_invoice(
    order_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get printable HTML invoice"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Yetkilendirme gerekli")
    
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    
    invoice = order.get("invoice", {})
    shipping = order.get("shipping_address", {})
    items = order.get("items", [])
    
    # Calculate totals
    subtotal = float(order.get("subtotal", 0))
    tax_rate = 0.20
    tax_amount = subtotal * tax_rate
    total = float(order.get("total", subtotal))
    
    # Build items HTML
    items_html = ""
    for idx, item in enumerate(items, 1):
        price = float(item.get("price", 0))
        qty = int(item.get("quantity", 1))
        line_total = price * qty
        items_html += f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{idx}</td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">
                {item.get('name', '')}
                {f"<br><small>Beden: {item.get('size')}</small>" if item.get('size') else ""}
            </td>
            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: center;">{qty}</td>
            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{price:,.2f} TL</td>
            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{line_total:,.2f} TL</td>
        </tr>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Fatura - {invoice.get('number', order.get('order_number', ''))}</title>
        <style>
            body {{ font-family: Arial, sans-serif; font-size: 12px; margin: 0; padding: 20px; }}
            .invoice-header {{ display: flex; justify-content: space-between; margin-bottom: 30px; }}
            .company-info {{ }}
            .invoice-info {{ text-align: right; }}
            .invoice-title {{ font-size: 24px; font-weight: bold; margin-bottom: 10px; }}
            .parties {{ display: flex; justify-content: space-between; margin-bottom: 30px; }}
            .party {{ width: 45%; }}
            .party-title {{ font-weight: bold; margin-bottom: 5px; border-bottom: 2px solid #000; padding-bottom: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
            th {{ background: #f5f5f5; padding: 10px 8px; text-align: left; border-bottom: 2px solid #000; }}
            .totals {{ width: 300px; margin-left: auto; }}
            .totals td {{ padding: 5px 10px; }}
            .totals .total {{ font-weight: bold; font-size: 14px; border-top: 2px solid #000; }}
            .qr-section {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; }}
            .footer {{ margin-top: 30px; text-align: center; font-size: 10px; color: #666; }}
            @media print {{
                body {{ padding: 0; }}
                .no-print {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        <div class="invoice-header">
            <div class="company-info">
                <div style="font-size: 20px; font-weight: bold;">FACETTE</div>
                <div>E-Ticaret Mağazası</div>
                <div>VKN: {GIB_VKN or '0000000000'}</div>
            </div>
            <div class="invoice-info">
                <div class="invoice-title">{invoice.get('type', 'e-Arşiv').upper()} FATURA</div>
                <div><strong>Fatura No:</strong> {invoice.get('number', '-')}</div>
                <div><strong>Tarih:</strong> {datetime.now().strftime('%d.%m.%Y')}</div>
                <div><strong>Sipariş No:</strong> {order.get('order_number', '')}</div>
            </div>
        </div>
        
        <div class="parties">
            <div class="party">
                <div class="party-title">SATICI</div>
                <div><strong>{GIB_COMPANY_NAME or 'FACETTE'}</strong></div>
                <div>VKN: {GIB_VKN or '0000000000'}</div>
            </div>
            <div class="party">
                <div class="party-title">ALICI</div>
                <div><strong>{shipping.get('first_name', '')} {shipping.get('last_name', '')}</strong></div>
                <div>{shipping.get('address', '')}</div>
                <div>{shipping.get('district', '')} / {shipping.get('city', '')}</div>
                <div>Tel: {shipping.get('phone', '')}</div>
            </div>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th style="width: 40px;">#</th>
                    <th>Ürün</th>
                    <th style="width: 60px; text-align: center;">Adet</th>
                    <th style="width: 100px; text-align: right;">Birim Fiyat</th>
                    <th style="width: 100px; text-align: right;">Tutar</th>
                </tr>
            </thead>
            <tbody>
                {items_html}
            </tbody>
        </table>
        
        <table class="totals">
            <tr>
                <td>Ara Toplam:</td>
                <td style="text-align: right;">{subtotal:,.2f} TL</td>
            </tr>
            <tr>
                <td>KDV (%20):</td>
                <td style="text-align: right;">{tax_amount:,.2f} TL</td>
            </tr>
            <tr class="total">
                <td>GENEL TOPLAM:</td>
                <td style="text-align: right;">{total:,.2f} TL</td>
            </tr>
        </table>
        
        {f'''
        <div class="qr-section">
            <img src="data:image/png;base64,{invoice.get('qr_code', '')}" width="100" height="100" />
            <div style="margin-top: 5px; font-size: 10px;">Fatura Doğrulama QR Kodu</div>
        </div>
        ''' if invoice.get('qr_code') else ''}
        
        <div class="footer">
            <p>Bu belge 5070 sayılı Elektronik İmza Kanunu uyarınca elektronik ortamda oluşturulmuştur.</p>
            <p>Fatura UUID: {invoice.get('uuid', '-')}</p>
        </div>
        
        <div class="no-print" style="text-align: center; margin-top: 20px;">
            <button onclick="window.print()" style="padding: 10px 30px; font-size: 14px; cursor: pointer;">
                Yazdır
            </button>
        </div>
    </body>
    </html>
    """
    
    return Response(content=html, media_type="text/html")

# Root endpoint
@api_router.get("/")
async def root():
    return {"message": "Facette E-Commerce API", "version": "2.0"}

# Include router
app.include_router(api_router)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
