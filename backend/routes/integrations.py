"""
Integration routes - Iyzico, Trendyol, MNG Kargo, GIB, Netgsm
"""
from fastapi import APIRouter, HTTPException, Query, Depends, Response
from typing import List
from datetime import datetime, timezone
import os
import base64
import uuid

from .deps import db, logger, get_current_user, require_admin

router = APIRouter(tags=["Integrations"])

# ==================== IYZICO ====================
IYZICO_MODE = os.environ.get('IYZICO_MODE', 'sandbox')
IYZICO_API_KEY = os.environ.get('IYZICO_API_KEY', '')
IYZICO_SECRET_KEY = os.environ.get('IYZICO_SECRET_KEY', '')
IYZICO_BASE_URL = os.environ.get('IYZICO_BASE_URL', 
    'https://api.iyzipay.com' if IYZICO_MODE == 'live' else 'https://sandbox-api.iyzipay.com'
)

def is_iyzico_configured():
    return bool(IYZICO_API_KEY and IYZICO_SECRET_KEY and IYZICO_API_KEY != 'sandbox-api-key')

@router.get("/payment/status")
async def get_payment_status():
    """Get Iyzico configuration status"""
    return {
        "mode": IYZICO_MODE,
        "configured": is_iyzico_configured(),
        "base_url": IYZICO_BASE_URL
    }

# ==================== TRENDYOL ====================
TRENDYOL_MODE = os.environ.get('TRENDYOL_MODE', 'sandbox')
TRENDYOL_API_KEY = os.environ.get('TRENDYOL_API_KEY', '')
TRENDYOL_API_SECRET = os.environ.get('TRENDYOL_API_SECRET', '')
TRENDYOL_SUPPLIER_ID = os.environ.get('TRENDYOL_SUPPLIER_ID', '')
TRENDYOL_BASE_URL = os.environ.get('TRENDYOL_BASE_URL', 
    'https://api.trendyol.com' if TRENDYOL_MODE == 'live' else 'https://stageapigw.trendyol.com'
)

def get_trendyol_headers():
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
    return bool(TRENDYOL_API_KEY and TRENDYOL_API_SECRET and TRENDYOL_SUPPLIER_ID)

@router.get("/trendyol/status")
async def get_trendyol_status():
    """Get Trendyol integration status"""
    return {
        "configured": is_trendyol_configured(),
        "mode": TRENDYOL_MODE,
        "supplier_id": TRENDYOL_SUPPLIER_ID if is_trendyol_configured() else None
    }

@router.post("/trendyol/products/sync")
async def sync_products_to_trendyol(
    product_ids: List[str] = Query(None),
    current_user: dict = Depends(require_admin)
):
    """Sync products to Trendyol"""
    if not is_trendyol_configured():
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
    
    # Implementation would go here - for now return mock response
    return {
        "success": True,
        "message": "Trendyol senkronizasyonu için yapılandırma gerekli",
        "products_sent": 0
    }

@router.post("/trendyol/orders/import")
async def import_trendyol_orders(current_user: dict = Depends(require_admin)):
    """Import orders from Trendyol"""
    if not is_trendyol_configured():
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
    
    return {"success": True, "imported": 0, "message": "Trendyol sipariş içe aktarma için yapılandırma gerekli"}

# ==================== GIB E-FATURA ====================
GIB_MODE = os.environ.get('GIB_MODE', 'test')
GIB_USERNAME = os.environ.get('GIB_USERNAME', '')
GIB_PASSWORD = os.environ.get('GIB_PASSWORD', '')
GIB_VKN = os.environ.get('GIB_VKN', '')
GIB_COMPANY_NAME = os.environ.get('GIB_COMPANY_NAME', 'FACETTE')

def is_gib_configured():
    return bool(GIB_USERNAME and GIB_PASSWORD and GIB_VKN and len(GIB_VKN) == 10)

@router.get("/gib/status")
async def get_gib_status():
    """Get GIB integration status"""
    return {
        "configured": is_gib_configured(),
        "mode": GIB_MODE,
        "vkn": GIB_VKN[:4] + "******" if GIB_VKN else None,
        "company_name": GIB_COMPANY_NAME
    }
