from fastapi import FastAPI, APIRouter, HTTPException, Depends, Query, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import re
import json

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

# ==================== HOMEPAGE BLOCKS ====================
@api_router.get("/homepage/blocks")
async def get_homepage_blocks():
    blocks = await db.homepage_blocks.find({"is_active": True}, {"_id": 0}).sort("sort_order", 1).to_list(20)
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

# Root endpoint
@api_router.get("/")
async def root():
    return {"message": "Facette E-Commerce API", "version": "1.0"}

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
