"""
Facette E-Commerce API - Main Server
Modular architecture with routes
"""
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
import logging
from pathlib import Path

# Load .env early so env-based integrations (EMERGENT_LLM_KEY etc.) are available
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except Exception:
    pass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import routes
from routes import (
    auth_router,
    products_router,
    orders_router,
    categories_router,
    banners_router,
    cms_router,
    integrations_router,
    admin_router,
    customer_router,
    variants_router,
    webhooks_router,
    attributes_router,
    upload_router,
    settings_router,
)
from routes.vendors import router as vendors_router
from routes.admin_rbac import router as admin_rbac_router
from routes.size_tables import router as size_tables_router, public_router as size_tables_public_router
from routes.manufacturing import router as manufacturing_router, suppliers_router as manufacturing_suppliers_router
from routes.ai_chatbot import router as ai_chatbot_router
from routes.locations import router as locations_router
from routes.attribution import router as attribution_router
from routes.members import router as members_router
from routes.coupons import admin_router as coupons_admin_router, public_router as coupons_public_router
from routes.reports import router as reports_router
from routes.extras import (
    cart_router,
    admin_cart_router,
    reviews_public_router,
    reviews_admin_router,
    seo_public_router,
    seo_admin_router,
)
from routes.catalog_extras import (
    brands_router, tags_router, member_groups_router, announcements_router, popups_router,
    alerts_public_router, alerts_admin_router,
    havale_public_router, havale_admin_router,
    admin_orders_router,
    rules_router,
    extra_reports_router,
    tickets_public_router, tickets_admin_router,
    email_admin_router,
    currency_router,
)
from routes.admin_tasks import router as admin_tasks_router
from routes.barcode_cards import router as barcode_cards_router
from routes.provider_settings import router as provider_settings_router
from routes.marketplace_hub import router as marketplace_hub_router

# Database
from routes.deps import client, db

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    # Startup
    logger.info("Starting Facette E-Commerce API...")
    
    try:
        # Create admin user if not exists
        admin = await db.users.find_one({"email": "admin@facette.com"})
        if not admin:
            from routes.deps import hash_password, generate_id
            from datetime import datetime, timezone
            await db.users.insert_one({
                "id": generate_id(),
                "email": "admin@facette.com",
                "password": hash_password("admin123"),
                "first_name": "Admin",
                "last_name": "User",
                "is_admin": True,
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            logger.info("Admin user created: admin@facette.com / admin123")
        
        # Create indexes
        await db.products.create_index("slug")
        await db.products.create_index("stock_code")
        await db.orders.create_index("order_number")
        await db.orders.create_index("user_id")
        await db.users.create_index("email", unique=True)
        
        logger.info("Database indexes created")
    except Exception as e:
        logger.warning(f"Database initialization warning (server will still start): {e}")

    # Start background scheduler (auto-cancel 48h unpaid havale orders)
    try:
        from scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning(f"Scheduler start warning: {e}")

    yield
    
    # Shutdown
    logger.info("Shutting down...")
    try:
        from scheduler import shutdown_scheduler
        shutdown_scheduler()
    except Exception:
        pass
    client.close()

# Create FastAPI app
app = FastAPI(
    title="Facette E-Commerce API",
    version="3.0",
    description="Modular E-Commerce API with Iyzico, Trendyol, MNG Kargo, GIB integrations",
    lifespan=lifespan
)

# CORS
cors_origins = os.environ.get("CORS_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins.split(",") if cors_origins != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Main API Router
api_router = APIRouter(prefix="/api")

# Include all route modules
api_router.include_router(auth_router)
api_router.include_router(products_router)
api_router.include_router(orders_router)
api_router.include_router(categories_router)
api_router.include_router(banners_router)
api_router.include_router(cms_router)
api_router.include_router(integrations_router, prefix="/integrations")
api_router.include_router(admin_router)
api_router.include_router(customer_router)
api_router.include_router(variants_router)
api_router.include_router(webhooks_router)
api_router.include_router(attributes_router)
api_router.include_router(upload_router)
api_router.include_router(settings_router)
api_router.include_router(vendors_router, prefix="/vendors")
api_router.include_router(admin_rbac_router)
api_router.include_router(size_tables_router)
api_router.include_router(size_tables_public_router)
api_router.include_router(manufacturing_router)
api_router.include_router(manufacturing_suppliers_router)
api_router.include_router(ai_chatbot_router)
api_router.include_router(locations_router)
api_router.include_router(attribution_router)
api_router.include_router(members_router)
api_router.include_router(coupons_admin_router)
api_router.include_router(coupons_public_router)
api_router.include_router(reports_router)
api_router.include_router(cart_router)
api_router.include_router(admin_cart_router)
api_router.include_router(reviews_public_router)
api_router.include_router(reviews_admin_router)
api_router.include_router(seo_public_router)
api_router.include_router(seo_admin_router)
# Ticimax P1 — catalog extras, ops, reports, communications
for _r in (
    brands_router, tags_router, member_groups_router, announcements_router, popups_router,
    alerts_public_router, alerts_admin_router,
    havale_public_router, havale_admin_router,
    admin_orders_router,
    rules_router,
    extra_reports_router,
    tickets_public_router, tickets_admin_router,
    email_admin_router,
    currency_router,
):
    api_router.include_router(_r)
api_router.include_router(admin_tasks_router)
# Barcode cards (products & variants) — tek tek veya toplu yazdırılabilir HTML
# kartlar. Products.jsx'deki "Barkod Yazdır" akışları buraya bağlıdır.
api_router.include_router(barcode_cards_router)
# E-Fatura ve Kargo entegratör ayarları (provider seçimi + credential formu).
# Frontend: EInvoiceSettings.jsx + CargoSettings.jsx bu endpoint'leri kullanır.
api_router.include_router(provider_settings_router)
# Marketplace Hub: tüm e-ticaret pazaryerlerinin (Trendyol, HB, Temu, N11,
# Amazon, AliExpress, Etsy, ...) merkezi yönetimi: credentials, transfer_rules,
# auto_sync ayarları + integration_logs.
api_router.include_router(marketplace_hub_router)

# Root endpoint
@api_router.get("/")
async def root():
    return {
        "message": "Facette E-Commerce API",
        "version": "3.0",
        "status": "running"
    }

# Health check
@api_router.get("/health")
async def health():
    return {"status": "healthy"}

# Include API router
app.include_router(api_router)

# Static files (if needed)
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
