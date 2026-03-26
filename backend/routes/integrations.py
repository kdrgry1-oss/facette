"""
Integration routes - Iyzico, Trendyol, MNG Kargo, GIB, Netgsm, Ticimax, XML Feed
"""
from fastapi import APIRouter, HTTPException, Query, Depends, Response, BackgroundTasks, Request
from typing import List, Optional
from datetime import datetime, timezone
import os
import base64
import uuid
import re
import xml.etree.ElementTree as ET

from .deps import db, logger, get_current_user, require_admin, generate_id, generate_short_id

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
import httpx

async def get_trendyol_config():
    """Get Trendyol configuration from DB or env"""
    settings = await db.settings.find_one({"id": "trendyol"})
    if settings:
        mode = settings.get("mode", "sandbox")
        return {
            "api_key": settings.get("api_key", ""),
            "api_secret": settings.get("api_secret", ""),
            "supplier_id": settings.get("supplier_id", ""),
            "is_active": settings.get("is_active", False),
            "mode": mode,
            "default_markup": settings.get("default_markup", 0),
            "base_url": 'https://api.trendyol.com' if mode == 'live' else 'https://stageapigw.trendyol.com'
        }
    
    # Fallback to env
    mode = os.environ.get('TRENDYOL_MODE', 'sandbox')
    return {
        "api_key": os.environ.get('TRENDYOL_API_KEY', ''),
        "api_secret": os.environ.get('TRENDYOL_API_SECRET', ''),
        "supplier_id": os.environ.get('TRENDYOL_SUPPLIER_ID', ''),
        "is_active": bool(os.environ.get('TRENDYOL_API_KEY')),
        "mode": mode,
        "base_url": 'https://api.trendyol.com' if mode == 'live' else 'https://stageapigw.trendyol.com'
    }

async def get_trendyol_headers():
    config = await get_trendyol_config()
    if not config["api_key"] or not config["api_secret"]:
        return None
    credentials = f'{config["api_key"]}:{config["api_secret"]}'
    encoded = base64.b64encode(credentials.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "User-Agent": f'{config["supplier_id"]} - FacetteIntegration',
        "Content-Type": "application/json"
    }

def calculate_trendyol_price(base_price: float, product_data: dict, trendyol_config: dict) -> float:
    """Calculate price with markup logic"""
    use_default = product_data.get("use_default_markup", True)
    if use_default:
        markup = float(trendyol_config.get("default_markup", 0))
    else:
        markup = float(product_data.get("markup_rate", 0))
    
    final_price = base_price * (1 + markup / 100)
    return round(final_price, 2)

@router.get("/trendyol/settings")
async def get_trendyol_settings(current_user: dict = Depends(require_admin)):
    """Get Trendyol settings"""
    config = await get_trendyol_config()
    
    # Also check main settings for trendyol_markup as fallback
    default_markup = config.get("default_markup", 0)
    if default_markup == 0:
        main_settings = await db.settings.find_one({"id": "main"})
        if main_settings and main_settings.get("trendyol_markup"):
            default_markup = main_settings.get("trendyol_markup", 0)
    
    # Mask secrets
    return {
        "supplier_id": config.get("supplier_id", ""),
        "api_key": config.get("api_key", ""),
        "api_secret": "********" if config.get("api_secret") else "",
        "mode": config.get("mode", "sandbox"),
        "is_active": config.get("is_active", False),
        "default_markup": default_markup
    }

@router.post("/trendyol/settings")
async def save_trendyol_settings(
    settings: dict,
    current_user: dict = Depends(require_admin)
):
    """Save Trendyol settings"""
    from datetime import datetime, timezone
    
    update_data = {
        "supplier_id": settings.get("supplier_id", ""),
        "api_key": settings.get("api_key", ""),
        "mode": settings.get("mode", "sandbox"),
        "is_active": settings.get("is_active", False),
        "default_markup": settings.get("default_markup", 0),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if settings.get("api_secret") and settings.get("api_secret") != "********":
        update_data["api_secret"] = settings.get("api_secret")
        
    await db.settings.update_one(
        {"id": "trendyol"},
        {"$set": update_data},
        upsert=True
    )
    return {"success": True, "message": "Trendyol ayarları kaydedildi"}

@router.get("/trendyol/status")
async def get_trendyol_status():
    """Get Trendyol integration status"""
    config = await get_trendyol_config()
    return {
        "configured": config["is_active"],
        "mode": config["mode"],
        "supplier_id": config["supplier_id"] if config["is_active"] else None
    }

@router.get("/trendyol/debug")
async def debug_trendyol_orders():
    config = await get_trendyol_config()
    import sys, os
    import time
    from datetime import datetime, timezone, timedelta
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from trendyol_client import TrendyolClient
    
    client = TrendyolClient(
        supplier_id=config["supplier_id"],
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        mode=config["mode"]
    )
    
    now = datetime.now()
    start = now - timedelta(days=14)
    end_date_ms = int(now.timestamp() * 1000)
    start_date_ms = int(start.timestamp() * 1000)
    
    try:
        resp = await client.get_orders(start_date_ms=start_date_ms, end_date_ms=end_date_ms, size=50)
        return resp
    except Exception as e:
        return {"error": str(e)}

@router.post("/trendyol/categories/sync")
async def sync_trendyol_categories(current_user: dict = Depends(require_admin)):
    """Sync and save category tree from Trendyol API to local DB"""
    config = await get_trendyol_config()
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from trendyol_client import TrendyolClient
    
    try:
        client = TrendyolClient(
            supplier_id=config["supplier_id"],
            api_key=config["api_key"],
            api_secret=config["api_secret"],
            mode=config["mode"]
        )
        categories = await client.get_categories()
        
        # Save to DB (Drop and re-insert for clean sync)
        if categories:
            await db.trendyol_categories.delete_many({})
            await db.trendyol_categories.insert_many(categories)
            
        return {"success": True, "message": f"{len(categories)} kategori senkronize edildi."}
    except Exception as e:
        logger.error(f"Error fetching trendyol categories: {str(e)}")
        raise HTTPException(status_code=500, detail="Trendyol kategorileri alınamadı")



@router.get("/trendyol/categories/{category_id}/attributes")
async def get_trendyol_category_attributes(category_id: int, current_user: dict = Depends(require_admin)):
    """Get attributes for a specific category (From DB or Trendyol API directly)"""
    config = await get_trendyol_config()
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from trendyol_client import TrendyolClient
    
    # Check if already in local DB
    existing = await db.trendyol_attributes.find_one({"category_id": category_id})
    if existing:
        return {"success": True, "attributes": existing.get("attributes", [])}
        
    try:
        client = TrendyolClient(
            supplier_id=config["supplier_id"],
            api_key=config["api_key"],
            api_secret=config["api_secret"],
            mode=config["mode"]
        )
        attributes = await client.get_category_attributes(category_id)
        
        # Save to local DB for future use
        if attributes:
            await db.trendyol_attributes.update_one(
                {"category_id": category_id},
                {"$set": {"category_id": category_id, "attributes": attributes}},
                upsert=True
            )
            
        return {"success": True, "attributes": attributes}
    except Exception as e:
        logger.error(f"Error fetching trendyol attributes for category {category_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Özellikler (attributes) alınamadı")

@router.post("/trendyol/brands/sync")
async def sync_trendyol_brands(current_user: dict = Depends(require_admin)):
    """Sync brands from Trendyol API to local DB"""
    config = await get_trendyol_config()
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from trendyol_client import TrendyolClient
    
    try:
        client = TrendyolClient(
            supplier_id=config["supplier_id"],
            api_key=config["api_key"],
            api_secret=config["api_secret"],
            mode=config["mode"]
        )
        # Assuming maximum 500 per page, just fetching first page for demonstration. In prod, paginate.
        brands_data = await client.get_brands(size=5000)
        brands = brands_data.get("brands", [])
        
        if brands:
            await db.trendyol_brands.delete_many({})
            await db.trendyol_brands.insert_many(brands)
            
        return {"success": True, "message": f"{len(brands)} marka senkronize edildi."}
    except Exception as e:
        logger.error(f"Error fetching trendyol brands: {str(e)}")
        raise HTTPException(status_code=500, detail="Trendyol markaları alınamadı")

@router.post("/trendyol/products/sync")
async def sync_products_to_trendyol(
    request: Request,
    current_user: dict = Depends(require_admin)
):
    """Sync products to Trendyol via Batch Request"""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
    
    payload = await request.json()
    product_ids = payload.get("product_ids", [])
    category_filters = payload.get("category_filters", [])
    
    query = {}
    if product_ids:
        query = {"id": {"$in": product_ids}}
    elif category_filters:
        # Build an $or query for each category + its filters
        or_conditions = []
        for cf in category_filters:
            cat_id = cf.get("category_id")
            filters = cf.get("filters", {})
            try:
                from bson.objectid import ObjectId
                cat = await db.categories.find_one({"_id": ObjectId(cat_id)})
            except:
                cat = await db.categories.find_one({"id": cat_id})
                
            if not cat: continue
            
            cat_q = {"category_name": cat.get("name")}
            if filters.get("stock_code"):
                cat_q["stock_code"] = {"$regex": filters["stock_code"], "$options": "i"}
            if filters.get("date_range"):
                try:
                    from datetime import datetime, timezone
                    # Format: YYYY-MM-DD
                    date_obj = datetime.strptime(filters["date_range"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    cat_q["created_at"] = {"$gte": date_obj.isoformat()}
                except Exception:
                    pass
            or_conditions.append(cat_q)
            
        if or_conditions:
            query = {"$or": or_conditions}
        else:
            query = {"is_active": True}
    else:
        # Sync only active products if no specific IDs are provided
        query = {"is_active": True}
        
    products = await db.products.find(query).to_list(length=None)
    
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from trendyol_client import TrendyolClient
    
    client = TrendyolClient(
        supplier_id=config["supplier_id"],
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        mode=config["mode"]
    )
    
    items_to_send = []
    errors = []
    
    def resolve_attributes(base_attrs, product, variant, category):
        item_attrs = base_attrs.copy()
        processed = {int(a["attributeId"]) for a in item_attrs if "attributeId" in a}
        
        attr_mappings = category.get("attribute_mappings", [])
        val_mappings = category.get("value_mappings", {})
        default_mappings = category.get("default_mappings", {})
        
        for mapping in attr_mappings:
            ty_id = mapping.get("trendyol_attr_id")
            if not ty_id: continue
            ty_id = int(ty_id)
            if ty_id in processed:
                continue
                
            local_key = str(mapping.get("local_attr")).lower()
            local_val = None
            
            if variant:
                if local_key in ["renk", "color"]:
                    local_val = variant.get("color")
                elif local_key in ["beden", "boy", "size"]:
                    local_val = variant.get("size")
                    
            if not local_val:
                for a in product.get("attributes", []):
                    if str(a.get("type")).lower() == local_key:
                        local_val = a.get("value")
                        break
                        
            if local_val:
                str_ty_id = str(ty_id)
                if str_ty_id in val_mappings and str(local_val) in val_mappings[str_ty_id]:
                    mapped_val = val_mappings[str_ty_id][str(local_val)]
                    if mapped_val:
                        if str(mapped_val).isdigit():
                            item_attrs.append({
                                "attributeId": ty_id,
                                "attributeValueId": int(mapped_val)
                            })
                        else:
                            item_attrs.append({
                                "attributeId": ty_id,
                                "customAttributeValue": str(mapped_val)
                            })
                        processed.add(ty_id)
                        continue
                
            str_ty_id = str(ty_id)
            if str_ty_id in default_mappings and default_mappings[str_ty_id]:
                def_val = default_mappings[str_ty_id]
                if str(def_val).isdigit():
                    item_attrs.append({
                        "attributeId": ty_id,
                        "attributeValueId": int(def_val)
                    })
                else:
                    item_attrs.append({
                        "attributeId": ty_id,
                        "customAttributeValue": str(def_val)
                    })
                processed.add(ty_id)

        for ty_str, def_val in default_mappings.items():
            if not def_val: continue
            try: ty_id = int(ty_str)
            except: continue
            if ty_id not in processed:
                if str(def_val).isdigit():
                    item_attrs.append({
                        "attributeId": ty_id,
                        "attributeValueId": int(def_val)
                    })
                else:
                    item_attrs.append({
                        "attributeId": ty_id,
                        "customAttributeValue": str(def_val)
                    })
                processed.add(ty_id)
                
        return item_attrs
    
    for product in products:
        try:
            # 1. Category Mapping check
            category = await db.categories.find_one({"name": product.get("category_name")})
            if not category or not category.get("trendyol_category_id"):
                errors.append(f"{product.get('name')} - Trendyol kategori eşleştirmesi (Mapping) yok.")
                continue
                
            trendyol_cat_id = category["trendyol_category_id"]
            
            # 2. Attributes check and formatting
            raw_attrs = product.get("trendyol_attributes", {})
            attributes = []
            for attr_id, val_id in raw_attrs.items():
                if val_id:
                    # Trendyol expects attributeId and attributeValueId, or customAttributeValue
                    if str(val_id).isdigit():
                        attributes.append({
                            "attributeId": int(attr_id),
                            "attributeValueId": int(val_id)
                        })
                    else:
                        attributes.append({
                            "attributeId": int(attr_id),
                            "customAttributeValue": str(val_id)
                        })
            
            # 3. Base Product Details
            base_item = {
                "title": product.get("name"),
                "productMainId": product.get("stock_code") or product.get("id"),
                "categoryId": int(trendyol_cat_id),
                "description": product.get("description") or product.get("short_description") or "",
                "currencyType": product.get("currency", "TRY"),
                "listPrice": calculate_trendyol_price(float(product.get("price", 0)), product, config),
                "salePrice": calculate_trendyol_price(float(product.get("sale_price") or product.get("price", 0)), product, config),
                "vatRate": int(product.get("vat_rate", 20)),
                "cargoCompanyId": 10, # Assuming 10 is MNG Kargo (Needs specific Cargo Provider ID)
                "dimensionalWeight": float(product.get("cargo_weight", 1)),
                "images": [{"url": img} for img in product.get("images", [])[:8]]
            }
            
            if not base_item["images"]:
                errors.append(f"{product.get('name')} - En az 1 görsel gerekli.")
                continue
            
            # 4. Handle Variants or No-Variants
            variants = product.get("variants", [])
            if not variants:
                if not product.get("barcode"):
                    errors.append(f"{product.get('name')} - Barkod eksik (Zorunlu alan).")
                    continue
                item = base_item.copy()
                item["barcode"] = product.get("barcode")
                item["stockCode"] = product.get("stock_code") or product.get("barcode")
                item["quantity"] = int(product.get("stock", 0))
                item["attributes"] = resolve_attributes(attributes, product, None, category)
                items_to_send.append(item)
            else:
                for v in variants:
                    if not v.get("barcode"):
                        errors.append(f"{product.get('name')} - Varyant ({v.get('size')}) barkodu eksik.")
                        continue
                    item = base_item.copy()
                    item["barcode"] = v.get("barcode")
                    item["stockCode"] = v.get("stock_code") or v.get("barcode")
                    item["quantity"] = int(v.get("stock", 0))
                    item["attributes"] = resolve_attributes(attributes, product, v, category)
                    items_to_send.append(item)
                    
        except Exception as e:
            errors.append(f"{product.get('name')} - Hazırlama Hatası: {str(e)}")
            
    if not items_to_send:
        # Save failure log
        from datetime import datetime, timezone
        log_doc = {
            "id": generate_id(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "products_attempted": len(products),
            "products_sent": 0,
            "batch_request_id": None,
            "errors": errors,
            "message": "Gönderilecek geçerli ürün bulunamadı."
        }
        await db.trendyol_sync_logs.insert_one(log_doc)
        return {
            "success": False,
            "message": "Trendyol'a gönderilecek geçerli ürün bulunamadı. Lütfen eksikleri giderin.",
            "errors": errors
        }
        
    try:
        from datetime import datetime, timezone
        started_at = datetime.now(timezone.utc).isoformat()
        response = await client.create_products(items_to_send)
        batch_id = response.get("batchRequestId")
        # Save success log
        log_doc = {
            "id": generate_id(),
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "success" if not errors else "partial",
            "products_attempted": len(products),
            "products_sent": len(items_to_send),
            "batch_request_id": batch_id,
            "errors": errors,
            "message": f"{len(items_to_send)} ürün aktarıldı."
        }
        await db.trendyol_sync_logs.insert_one(log_doc)
        return {
            "success": True,
            "message": f"{len(items_to_send)} ürün Trendyol entegrasyonuna aktarıldı (Batch Request).",
            "batchRequestId": batch_id,
            "errors": errors
        }
    except Exception as e:
        logger.error(f"Error syncing products to Trendyol: {str(e)}")
        from datetime import datetime, timezone
        log_doc = {
            "id": generate_id(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "error",
            "products_attempted": len(products),
            "products_sent": 0,
            "batch_request_id": None,
            "errors": errors + [f"API Hatası: {str(e)}"],
            "message": "Trendyol API hatası oluştu."
        }
        await db.trendyol_sync_logs.insert_one(log_doc)
        if hasattr(e, "response") and hasattr(e.response, "json"):
            raise HTTPException(status_code=500, detail=e.response.json())
        raise HTTPException(status_code=500, detail="Trendyol API ürün gönderimi başarısız oldu.")

@router.get("/trendyol/sync-logs")
async def get_trendyol_sync_logs(
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(require_admin)
):
    """Get paginated Trendyol sync logs"""
    skip = (page - 1) * limit
    logs = await db.trendyol_sync_logs.find({}, {"_id": 0}).sort("started_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.trendyol_sync_logs.count_documents({})
    return {"logs": logs, "total": total, "page": page}

@router.post("/trendyol/products/inventory-sync")
async def sync_trendyol_inventory(current_user: dict = Depends(require_admin)):
    """Bulk sync stock and prices to Trendyol"""
    products = await db.products.find({"is_active": True}).to_list(length=None)
    return await _sync_inventory_to_trendyol(products)

@router.post("/trendyol/products/{product_id}/sync-inventory")
async def sync_single_product_inventory(
    product_id: str,
    current_user: dict = Depends(require_admin)
):
    """Sync stock and prices for a single product to Trendyol"""
    product = await db.products.find_one({"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return await _sync_inventory_to_trendyol([product])

async def _sync_inventory_to_trendyol(products: list):
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
        
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from trendyol_client import TrendyolClient
    
    client = TrendyolClient(
        supplier_id=config["supplier_id"],
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        mode=config["mode"]
    )
    
    items_to_send = []
    
    for product in products:
        variants = product.get("variants", [])
        if not variants:
            if product.get("barcode"):
                items_to_send.append({
                    "barcode": product["barcode"],
                    "quantity": int(product.get("stock", 0)),
                    "salePrice": float(product.get("sale_price") or product.get("price", 0)),
                    "listPrice": float(product.get("price", 0))
                })
        else:
            for v in variants:
                if v.get("barcode"):
                    items_to_send.append({
                        "barcode": v["barcode"],
                        "quantity": int(v.get("stock", 0)),
                        "salePrice": float(product.get("sale_price") or product.get("price", 0)),
                        "listPrice": float(product.get("price", 0))
                    })
    
    from datetime import datetime, timezone
    started_at = datetime.now(timezone.utc).isoformat()
    
    if not items_to_send:
        # Log failure to sync screen
        log_doc = {
            "id": generate_id(),
            "started_at": started_at,
            "status": "failed",
            "products_attempted": len(products),
            "products_sent": 0,
            "batch_request_id": None,
            "errors": ["Gönderilecek stok/fiyat bilgisi bulunamadı (barkodlar eksik olabilir)."],
            "message": "Envanter güncellemesi başarısız (geçerli barkod yok)."
        }
        await db.trendyol_sync_logs.insert_one(log_doc)
        return {"success": False, "message": "Gönderilecek stok/fiyat bilgisi bulunamadı (barkod eksik?)"}
        
    try:
        res = await client.update_inventory(items_to_send)
        batch_id = res.get("batchRequestId", "")
        
        # Log to the new sync logs screen
        log_doc = {
            "id": generate_id(),
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "success",
            "products_attempted": len(products),
            "products_sent": len(items_to_send),
            "batch_request_id": batch_id,
            "errors": [],
            "message": "Stok ve fiyat güncellemesi başarıyla gönderildi."
        }
        await db.trendyol_sync_logs.insert_one(log_doc)
        
        return {"success": True, "message": f"{len(items_to_send)} kalem ürünün stok/fiyat bilgisi Trendyol'a gönderildi.", "batch_id": batch_id}
    except Exception as e:
        logger.error(f"Trendyol inventory sync error: {str(e)}")
        log_doc = {
            "id": generate_id(),
            "started_at": started_at,
            "status": "error",
            "products_attempted": len(products),
            "products_sent": 0,
            "batch_request_id": None,
            "errors": [f"API Hatası: {str(e)}"],
            "message": "Stok/fiyat güncellemesi sırasında hata oluştu."
        }
        await db.trendyol_sync_logs.insert_one(log_doc)
        raise HTTPException(status_code=500, detail=f"Trendyol stok/fiyat güncelleme hatası: {str(e)}")

@router.get("/trendyol/products/batch-status/{batch_id}")
async def get_trendyol_batch_status(batch_id: str, current_user: dict = Depends(require_admin)):
    """Check the status of a batch request"""
    config = await get_trendyol_config()
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from trendyol_client import TrendyolClient
    
    try:
        client = TrendyolClient(
            supplier_id=config["supplier_id"],
            api_key=config["api_key"],
            api_secret=config["api_secret"],
            mode=config["mode"]
        )
        status = await client.get_batch_request_result(batch_id)
        return {"success": True, "status": status}
    except Exception as e:
        logger.error(f"Error fetching batch status: {str(e)}")
        raise HTTPException(status_code=500, detail="Batch durumu alınamadı.")

from pydantic import BaseModel
from typing import List, Optional

class TrendyolOrderPreviewReq(BaseModel):
    order_number: Optional[str] = None
    start_date_ms: Optional[int] = None
    end_date_ms: Optional[int] = None

class TrendyolOrderImportReq(BaseModel):
    orders: List[dict]

async def log_integration_event(platform: str, action: str, entity_type: str, entity_id: str, status: str, message: str, details: dict = None):
    try:
        from datetime import datetime, timezone
        await db.integration_logs.insert_one({
            "platform": platform,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "status": status,
            "message": message,
            "details": details or {},
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        logger.error(f"Failed to log integration event: {str(e)}")

def map_trendyol_order(t_order: dict) -> dict:
    from datetime import datetime, timezone
    order_number = t_order.get("orderNumber")
    
    items = []
    total_price = t_order.get("totalPrice", 0)
    gross_amount = t_order.get("grossAmount", 0)
    total_discount = t_order.get("totalDiscount", 0)
    
    for line in t_order.get("lines", []):
        qty = max(line.get("quantity", 1), 1)
        line_gross = line.get("lineGrossAmount", line.get("amount", 0))
        unit_price = line_gross / qty # İndirimsiz birim fiyat
        
        # Trendyol 'price' field is actually the net discounted price
        net_price = line.get("price", line.get("lineUnitPrice", 0))
        
        discount = line.get("discount", 0)
        discount_per_item = discount / qty if discount else 0

        items.append({
            "product_id": line.get("productCode"),
            "product_name": line.get("productName"),
            "quantity": qty,
            "unit_price": unit_price, # İndirimsiz birim fiyat
            "discount_amount": discount_per_item, # Birim başına indirim
            "price": net_price, # Net ödenen birim fiyat (Faturalandırılan)
            "size": line.get("productSize", ""),
            "color": line.get("productColor", ""),
            "currency": line.get("currencyCode", "TRY")
        })

    shipment_address = t_order.get("shipmentAddress", {})
    invoice_address = t_order.get("invoiceAddress", {})
    
    status_map = {
        "Created": "pending",
        "Picking": "processing",
        "Invoiced": "processing",
        "Shipped": "shipped",
        "Cancelled": "cancelled",
        "Delivered": "delivered",
        "UnDelivered": "returned",
        "Returned": "returned"
    }
    
    order_doc = {
        "order_number": str(order_number),
        "platform": "trendyol",
        "trendyol_package_id": t_order.get("id"),
        "user_id": None,
        "items": items,
        "shipping_address": {
            "first_name": shipment_address.get("firstName", "Trendyol"),
            "last_name": shipment_address.get("lastName", "Müşterisi"),
            "phone": shipment_address.get("phone", ""),
            "email": t_order.get("customerEmail", ""),
            "address": shipment_address.get("fullAddress", ""),
            "city": shipment_address.get("city", ""),
            "district": shipment_address.get("district", "")
        },
        "billing_address": {
            "first_name": invoice_address.get("firstName", "Trendyol"),
            "last_name": invoice_address.get("lastName", "Müşterisi"),
            "phone": invoice_address.get("phone", ""),
            "address": invoice_address.get("fullAddress", ""),
            "city": invoice_address.get("city", ""),
            "district": invoice_address.get("district", ""),
            "tax_number": invoice_address.get("taxNumber", ""),
            "tax_office": invoice_address.get("taxOffice", "")
        },
        "subtotal": gross_amount if gross_amount else total_price,
        "shipping_cost": 0,
        "discount_amount": total_discount,
        "total": total_price,
        "payment_method": "marketplace",
        "payment_status": "paid",
        "status": status_map.get(t_order.get("status"), "pending"),
        "cargo_tracking_number": t_order.get("cargoTrackingNumber", ""),
        "cargo_tracking_link": t_order.get("cargoTrackingLink", ""),
        "cargo_provider_name": t_order.get("cargoProviderName", ""),
        "invoice_link": t_order.get("invoiceLink", ""),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    return order_doc

@router.post("/trendyol/orders/preview")
async def preview_trendyol_orders(req: TrendyolOrderPreviewReq, current_user: dict = Depends(require_admin)):
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from trendyol_client import TrendyolClient
    client = TrendyolClient(
        supplier_id=config["supplier_id"], api_key=config["api_key"],
        api_secret=config["api_secret"], mode=config["mode"]
    )
    try:
        resp = await client.get_orders(
            start_date_ms=req.start_date_ms, 
            end_date_ms=req.end_date_ms, 
            order_number=req.order_number, 
            size=100
        )
        content = resp.get("content", [])
        return {"success": True, "orders": content}
    except Exception as e:
        logger.error(f"Error previewing Trendyol orders: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trendyol/orders/import-selected")
async def import_selected_trendyol_orders(req: TrendyolOrderImportReq, current_user: dict = Depends(require_admin)):
    try:
        from datetime import datetime, timezone
        from .deps import generate_id
        imported_count = 0
        updated_count = 0
        errors = []
        for t_order in req.orders:
            order_number = str(t_order.get("orderNumber"))
            try:
                order_data = map_trendyol_order(t_order)
                existing = await db.orders.find_one({"order_number": order_number, "platform": "trendyol"})
                if existing:
                    await db.orders.update_one({"_id": existing["_id"]}, {"$set": order_data})
                    updated_count += 1
                else:
                    order_data["id"] = generate_id()
                    order_data["created_at"] = datetime.now(timezone.utc).isoformat()
                    await db.orders.insert_one(order_data)
                    imported_count += 1
                await log_integration_event("trendyol", "import_order", "order", order_number, "success", "Sipariş başarıyla aktarıldı.")
            except Exception as e:
                err_msg = str(e)
                errors.append({"orderNumber": order_number, "error": err_msg})
                await log_integration_event("trendyol", "import_order", "order", order_number, "error", f"Aktarım hatası: {err_msg}", {"raw": t_order})
                
        return {"success": True, "imported": imported_count, "updated": updated_count, "errors": errors}
    except Exception as e:
        logger.error(f"Error importing selected orders: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trendyol/orders/import")
async def import_trendyol_orders(current_user: dict = Depends(require_admin)):
    """Import orders from Trendyol (Last 15 days) auto job"""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
    
    import sys, os
    import time
    from datetime import datetime, timezone, timedelta
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from trendyol_client import TrendyolClient
    from .deps import generate_id
    
    client = TrendyolClient(
        supplier_id=config["supplier_id"],
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        mode=config["mode"]
    )
    
    # Calculate timestamps (e.g. last 15 days as Trendyol recommends no more than 15 days wide searches)
    now = datetime.now()
    start = now - timedelta(days=15)
    end_date_ms = int(now.timestamp() * 1000)
    start_date_ms = int(start.timestamp() * 1000)
    
    imported_count = 0
    updated_count = 0
    
    try:
        # Fetch first page of 200 items (in a real scenario we'd paginate if totalElements > size)
        resp = await client.get_orders(start_date_ms=start_date_ms, end_date_ms=end_date_ms, size=200)
        content = resp.get("content", [])
        
        for t_order in content:
            order_number = t_order.get("orderNumber")
            existing_order = await db.orders.find_one({"order_number": str(order_number), "platform": "trendyol"})
            try:
                order_data = map_trendyol_order(t_order)
                if existing_order:
                    await db.orders.update_one(
                        {"_id": existing_order["_id"]},
                        {"$set": order_data}
                    )
                    updated_count += 1
                else:
                    order_data["id"] = generate_id()
                    order_data["created_at"] = datetime.now(timezone.utc).isoformat()
                    await db.orders.insert_one(order_data)
                    imported_count += 1
            except Exception as e:
                logger.error(f"Error mapping/saving order {order_number}: {e}")
                await log_integration_event("trendyol", "auto_import", "order", str(order_number), "error", f"Otomatik aktarım hatası: {str(e)}", {"raw": t_order})
        
        return {
            "success": True, 
            "message": f"Trendyol'dan {imported_count} yeni sipariş aktarıldı, {updated_count} sipariş güncellendi.",
            "imported": imported_count,
            "updated": updated_count
        }
    except Exception as e:
        logger.error(f"Error importing Trendyol orders: {str(e)}")
        await log_integration_event("trendyol", "auto_import_job", "system", "-", "error", f"Toplu aktarım hatası: {str(e)}")
        raise HTTPException(status_code=500, detail="Sipariş aktarımı sırasında bir hata oluştu.")

class CategoryMappingReq(BaseModel):
    local_category_id: str
    local_name: str
    trendyol_category_id: int
    trendyol_category_name: str

@router.get("/trendyol/category-mappings")
async def get_trendyol_category_mappings(current_user: dict = Depends(require_admin)):
    """Get all local categories with their Trendyol mappings, excluding hidden ones"""
    try:
        categories = await db.categories.find({"trendyol_hidden": {"$ne": True}}).to_list(1000)
        mappings = []
        for c in categories:
            mappings.append({
                "id": str(c["_id"]) if "_id" in c else c.get("id"),
                "local_name": c.get("name"),
                "trendyol_category_id": c.get("trendyol_category_id"),
                "trendyol_category_name": c.get("trendyol_category_name"),
                "attribute_mappings": c.get("attribute_mappings", []),
                "value_mappings": c.get("value_mappings", {}),
                "default_mappings": c.get("default_mappings", {}),
                "has_children": c.get("has_children", c.get("children_count", 0) > 0),
                "is_matched": bool(c.get("trendyol_category_id"))
            })
        return {"success": True, "mappings": mappings}
    except Exception as e:
        logger.error(f"Error fetching category mappings: {e}")
        raise HTTPException(status_code=500, detail="Kategori eşleştirmeleri alınamadı.")

@router.post("/trendyol/category-mappings")
async def save_trendyol_category_mapping(req: CategoryMappingReq, current_user: dict = Depends(require_admin)):
    """Save a Trendyol category mapping to a local category"""
    from bson.objectid import ObjectId
    try:
        # Support both string UUID and ObjectId
        filter_q = {"id": req.local_category_id} if len(req.local_category_id) > 24 else {"$or": [{"id": req.local_category_id}, {"_id": ObjectId(req.local_category_id)}]}
        
        await db.categories.update_one(
            filter_q,
            {"$set": {
                "trendyol_category_id": req.trendyol_category_id,
                "trendyol_category_name": req.trendyol_category_name
            }}
        )
        return {"success": True, "message": "Eşleştirme kaydedildi"}
    except Exception as e:
        logger.error(f"Error saving category mapping: {e}")
        raise HTTPException(status_code=500, detail="Eşleştirme kaydedilemedi.")



@router.post("/trendyol/category-mappings/{local_category_id}/value-mappings")
async def save_trendyol_category_value_mappings(local_category_id: str, req: Request, current_user: dict = Depends(require_admin)):
    payload = await req.json()
    value_mappings = payload.get("value_mappings", {})
    from bson.objectid import ObjectId
    filter_q = {"id": local_category_id} if len(local_category_id) > 24 else {"$or": [{"id": local_category_id}, {"_id": ObjectId(local_category_id)}]}
    
    await db.categories.update_one(
        filter_q,
        {"$set": {"value_mappings": value_mappings}}
    )
    return {"success": True}

@router.get("/trendyol/category-values/{local_category_id}")
async def get_local_category_values(local_category_id: str, current_user: dict = Depends(require_admin)):
    from bson.objectid import ObjectId
    import re
    
    filter_q = {"id": local_category_id} if len(local_category_id) > 24 else {"$or": [{"id": local_category_id}, {"_id": ObjectId(local_category_id)}]}
    category = await db.categories.find_one(filter_q)
    
    if not category:
         raise HTTPException(status_code=404, detail="Kategori bulunamadı")
         
    # Case-insensitive category name search
    name = category.get("name")
    cat_id = category.get("id") or str(category.get("_id"))
    
    query = {
        "$or": [
            {"category_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
            {"category_id": cat_id}
        ]
    }
    
    products = await db.products.find(query).to_list(None)
    
    val_map = {
        "Renk": set(),
        "Beden": set(),
        "Boy": set()
    }
    
    for p in products:
        # Pull from variants (standard for clothing)
        for v in p.get("variants", []):
            if v.get("color"): 
                c = str(v["color"]).strip()
                if c and c.lower() != "none": val_map["Renk"].add(c)
            if v.get("size"): 
                s = str(v["size"]).strip()
                if s and s.lower() != "none":
                    val_map["Beden"].add(s)
        
        # Pull from attributes array (from CSV imports or manual entry)
        for a in p.get("attributes", []):
            t = str(a.get("type", "")).strip()
            val = str(a.get("value", "")).strip()
            if t and val and val.lower() != "none":
                if t not in val_map:
                    val_map[t] = set()
                val_map[t].add(val)
                
    result = []
    for k, v in val_map.items():
        if v:
            # Sort values naturally if possible
            sorted_vals = sorted(list(v))
            result.append({"attribute_name": k, "values": sorted_vals})
            
    return {"success": True, "local_values": result}

@router.delete("/trendyol/category-mappings/{local_category_id}")
async def delete_trendyol_category_mapping(local_category_id: str, current_user: dict = Depends(require_admin)):
    """Hide a category from the Trendyol mappings list and clear its mapping"""
    from bson.objectid import ObjectId
    try:
        filter_q = {"id": local_category_id} if len(local_category_id) > 24 else {"$or": [{"id": local_category_id}, {"_id": ObjectId(local_category_id)}]}
        
        await db.categories.update_one(
            filter_q,
            {
                "$unset": {
                    "trendyol_category_id": "",
                    "trendyol_category_name": "",
                    "attribute_mappings": ""
                },
                "$set": {
                    "trendyol_hidden": True
                }
            }
        )
        return {"success": True, "message": "Kategori listeden kaldırıldı ve eşleştirmesi silindi"}
    except Exception as e:
        logger.error(f"Error hiding category mapping: {e}")
        raise HTTPException(status_code=500, detail="Eşleştirme silinemedi.")

@router.post("/trendyol/category-mappings/bulk-delete")
async def bulk_delete_trendyol_category_mappings(req: Request, current_user: dict = Depends(require_admin)):
    payload = await req.json()
    category_ids = payload.get("category_ids", [])
    if not category_ids:
        return {"success": True}
    from bson.objectid import ObjectId
    try:
        flat_filters = []
        for cid in category_ids:
            cid_str = str(cid)
            flat_filters.append({"id": cid_str})
            if len(cid_str) <= 24:
                try:
                    flat_filters.append({"_id": ObjectId(cid_str)})
                except Exception:
                    pass

        if not flat_filters:
            return {"success": True}

        await db.categories.update_many(
            {"$or": flat_filters},
            {
                "$unset": {
                    "trendyol_category_id": "",
                    "trendyol_category_name": "",
                    "attribute_mappings": ""
                },
                "$set": {
                    "trendyol_hidden": True
                }
            }
        )
        return {"success": True, "message": "Seçili kategoriler kaldırıldı"}
    except Exception as e:
        logger.error(f"Error bulk hiding categories: {e}")
        raise HTTPException(status_code=500, detail="Kategoriler silinemedi.")

class AttributeMapping(BaseModel):
    local_attr: str
    trendyol_attr_id: int

class AttributeMappingReq(BaseModel):
    attribute_mappings: List[AttributeMapping]
    default_mappings: Optional[dict] = {}

@router.post("/trendyol/category-mappings/{local_category_id}/attributes")
async def save_trendyol_attribute_mapping(local_category_id: str, req: AttributeMappingReq, current_user: dict = Depends(require_admin)):
    from bson.objectid import ObjectId
    try:
        filter_q = {"id": local_category_id} if len(local_category_id) > 24 else {"$or": [{"id": local_category_id}, {"_id": ObjectId(local_category_id)}]}
        
        mappings = [{"local_attr": m.local_attr, "trendyol_attr_id": m.trendyol_attr_id} for m in req.attribute_mappings]
        
        await db.categories.update_one(
            filter_q,
            {"$set": {
                "attribute_mappings": mappings,
                "default_mappings": req.default_mappings
            }}
        )
        return {"success": True, "message": "Özellik eşleştirmeleri kaydedildi"}
    except Exception as e:
        logger.error(f"Error saving attribute mapping: {e}")
        raise HTTPException(status_code=500, detail="Özellik eşleştirmeleri kaydedilemedi.")

@router.get("/trendyol/categories")
async def get_local_trendyol_categories(current_user: dict = Depends(require_admin)):
    """Fetch previously downloaded Trendyol categories for UI lists"""
    try:
        categories = await db.trendyol_categories.find({}, {"_id": 0, "id": 1, "name": 1, "subCategories": 1}).to_list(1000)
        # Flatten simple list for datalist mapping
        def flatten(cats, parent_name=""):
            result = []
            for c in cats:
                full_name = f"{parent_name} > {c['name']}" if parent_name else c["name"]
                result.append({"id": c["id"], "name": full_name})
                if c.get("subCategories"):
                    result.extend(flatten(c["subCategories"], full_name))
            return result
        flat_list = flatten(categories)
        return {"success": True, "categories": flat_list}
    except Exception as e:
        logger.error(f"Error fetching trendyol categories from db: {e}")
        return {"success": False, "categories": []}

@router.get("/integration-logs")
async def get_integration_logs(
    platform: str = Query(None),
    status: str = Query(None),
    limit: int = 50,
    current_user: dict = Depends(require_admin)
):
    """Fetch integration logs for UI"""
    try:
        query = {}
        if platform:
            query["platform"] = platform
        if status:
            query["status"] = status
            
        logs = await db.integration_logs.find(query).sort("created_at", -1).limit(limit).to_list(1000)
        # remove mongo _id
        for log in logs:
            if "_id" in log:
                log["_id"] = str(log["_id"])
        return {"success": True, "logs": logs}
    except Exception as e:
        logger.error(f"Error fetching integration logs: {e}")
        raise HTTPException(status_code=500, detail="Loglar alınamadı.")


@router.get("/trendyol/orders/label/{cargo_tracking_number}")
async def get_trendyol_cargo_label(cargo_tracking_number: str, current_user: dict = Depends(require_admin)):
    """Fetch PDF Cargo label from Trendyol"""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")
        
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from trendyol_client import TrendyolClient
    from fastapi.responses import Response
    
    try:
        client = TrendyolClient(
            supplier_id=config["supplier_id"],
            api_key=config["api_key"],
            api_secret=config["api_secret"],
            mode=config["mode"]
        )
        pdf_bytes = await client.get_cargo_label(cargo_tracking_number)
        return Response(content=pdf_bytes, media_type="application/pdf")
    except Exception as e:
        logger.error(f"Error fetching Trendyol cargo label: {str(e)}")
        raise HTTPException(status_code=500, detail="Kargo etiketi alınırken hata oluştu.")

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

# ==================== TİCİMAX ====================

def _generate_slug(name: str) -> str:
    slug = name.lower()
    tr_map = {'ı':'i','ğ':'g','ü':'u','ş':'s','ö':'o','ç':'c',
              'İ':'i','Ğ':'g','Ü':'u','Ş':'s','Ö':'o','Ç':'c'}
    for tr, en in tr_map.items():
        slug = slug.replace(tr, en)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug).strip('-')
    return slug or str(uuid.uuid4())[:8]

@router.get("/ticimax/status")
async def get_ticimax_status():
    """Check Ticimax connection status"""
    settings = await db.settings.find_one({"id": "ticimax"}) or {}
    domain = settings.get("domain", "www.facette.com.tr")
    api_key = settings.get("api_key", "HANXFWINXLDBY0WH47WMB6QKTE20T5")
    return {
        "configured": True,
        "domain": domain,
        "mode": "live",
        "api_key_set": bool(api_key),
        "last_sync": settings.get("last_sync")
    }

@router.post("/ticimax/settings")
async def save_ticimax_settings(
    settings: dict,
    current_user: dict = Depends(require_admin)
):
    """Save Ticimax settings (domain + api_key)"""
    await db.settings.update_one(
        {"id": "ticimax"},
        {"$set": {
            "domain": settings.get("domain", "www.facette.com.tr"),
            "api_key": settings.get("api_key", "HANXFWINXLDBY0WH47WMB6QKTE20T5"),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    return {"success": True, "message": "Ticimax ayarları kaydedildi"}

@router.post("/ticimax/categories/import")
async def import_ticimax_categories(
    include_subcategories: bool = Query(True, description="Alt kategorileri de recursive çek"),
    current_user: dict = Depends(require_admin)
):
    """
    Ticimax'tan tüm kategorileri ve alt kategorileri DB'ye aktarır.
    include_subcategories=True (varsayılan): Tüm kategori hiyerarşisini recursive çeker.
    include_subcategories=False: Sadece kök kategorileri çeker.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    if include_subcategories:
        from ticimax_client import get_all_categories as tc_get_categories
    else:
        from ticimax_client import get_categories as _tc_root
        tc_get_categories = lambda: _tc_root(parent_id=0)

    try:
        raw_categories = tc_get_categories()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ticimax bağlantı hatası: {str(e)}")

    imported = 0
    updated = 0
    for cat in raw_categories:
        if not cat:
            continue

        # Gerçek Ticimax alan adları (API'den doğrulandı):
        # ID, PID, Tanim, Aktif, AltKategoriSayisi, Sira, Url, Icerik, Kod,
        # KategoriMenuGoster, SeoAnahtarKelime, SeoSayfaAciklama, SeoSayfaBaslik
        cat_id = str(cat.get("ID") or cat.get("KategoriID") or "")
        name = str(cat.get("Tanim") or cat.get("SeoSayfaBaslik") or cat.get("KategoriAdi") or "")
        parent_id_raw = cat.get("PID") or cat.get("UstKategoriID") or 0
        parent_id = str(parent_id_raw) if str(parent_id_raw) != "0" else None
        is_active = bool(cat.get("Aktif", True))

        if not cat_id or not name:
            continue

        # PaylasimAyar nested objesini düzenle
        paylasim = cat.get("PaylasimAyar") or {}
        if hasattr(paylasim, '__values__'):
            paylasim = dict(paylasim.__values__)

        doc = {
            "ticimax_id": cat_id,
            "name": name,
            "slug": _generate_slug(name),
            "parent_id": parent_id,
            "is_active": is_active,
            "source": "ticimax",
            # ── Ticimax iç özellikleri ──
            "ticimax_sub_count": int(cat.get("AltKategoriSayisi") or 0),
            "ticimax_sira": int(cat.get("Sira") or 0),
            "ticimax_url": str(cat.get("Url") or ""),
            "ticimax_kod": str(cat.get("Kod") or "") if cat.get("Kod") else None,
            "ticimax_icerik": str(cat.get("Icerik") or "") if cat.get("Icerik") else None,
            "ticimax_menu_goster": bool(cat.get("KategoriMenuGoster", False)),
            "ticimax_seo_baslik": str(cat.get("SeoSayfaBaslik") or ""),
            "ticimax_seo_aciklama": str(cat.get("SeoSayfaAciklama") or "") if cat.get("SeoSayfaAciklama") else None,
            "ticimax_seo_anahtar": str(cat.get("SeoAnahtarKelime") or "") if cat.get("SeoAnahtarKelime") else None,
            "ticimax_paylasim_baslik": paylasim.get("Baslik"),
            "ticimax_paylasim_aciklama": paylasim.get("Aciklama"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        existing = await db.categories.find_one({"ticimax_id": cat_id})
        if existing:
            await db.categories.update_one({"ticimax_id": cat_id}, {"$set": doc})
            updated += 1
        else:
            doc["id"] = await generate_short_id("categories")
            await db.categories.insert_one(doc)
            imported += 1

    await db.settings.update_one(
        {"id": "ticimax"},
        {"$set": {"last_sync": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )

    return {
        "success": True,
        "imported": imported,
        "updated": updated,
        "total": imported + updated,
        "message": f"{imported} yeni kategori eklendi, {updated} kategori güncellendi"
    }


@router.post("/ticimax/products/import")
async def import_ticimax_products(
    limit: int = Query(500, ge=1, le=5000),
    aktif: int = Query(1, description="1=aktif, 0=pasif, -1=hepsi"),
    current_user: dict = Depends(require_admin)
):
    """
    Ticimax'tan ürünleri tüm iç özellikleriyle MongoDB'ye aktarır.
    Her ürün için varyasyonlar, resimler ve asorti stok da çekilir.
    aktif=1 (varsayılan): Sadece aktif ürünler.
    aktif=0: Sadece pasif ürünler.
    aktif=-1: Tüm ürünler (aktif + pasif).
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from ticimax_client import (
        get_products as tc_get_products,
        get_product_count,
        get_variants,
        get_product_images,
        get_assorted_stock,
    )

    aktif_param = None if aktif == -1 else aktif

    try:
        total_remote = get_product_count(aktif=aktif_param)
        logger.info(f"Ticimax ürün sayısı (aktif={aktif_param}): {total_remote}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ticimax bağlantı hatası: {str(e)}")

    # Eğer count 0 döndüyse, aktif=None ile tekrar dene
    if total_remote == 0 and aktif_param is not None:
        try:
            total_remote = get_product_count(aktif=None)
            logger.info(f"Ticimax ürün sayısı (aktif=None): {total_remote}")
        except Exception:
            pass

    page_size = 50
    imported = 0
    updated = 0
    page = 1
    fetched = 0

    while fetched < min(limit, total_remote or limit):
        try:
            result = tc_get_products(page=page, page_size=page_size, aktif=aktif_param)
        except Exception as e:
            logger.error(f"Page {page} fetch error: {e}")
            # Count yanlış geldiyse çıkmak yerine None ile deneyelim
            if aktif_param is not None:
                try:
                    result = tc_get_products(page=page, page_size=page_size, aktif=None)
                except Exception:
                    break
            else:
                break

        products_raw = result if isinstance(result, list) else []
        if not products_raw:
            break

        for raw in products_raw:
            if not raw:
                continue

            # Ana ürün tanımlayıcısı
            ticimax_id = raw.get("UrunID") or raw.get("ID") or raw.get("urunID")
            if not ticimax_id:
                continue
            ticimax_id = int(ticimax_id)

            # ── Temel alanlar ──────────────────────────────────────────
            name        = str(raw.get("UrunAdi") or raw.get("Adi") or "")
            stock_code  = str(raw.get("StokKodu") or raw.get("stokkodu") or "")
            barcode     = str(raw.get("Barkod") or raw.get("barkod") or "")
            description = str(raw.get("Aciklama") or raw.get("UrunAciklama") or raw.get("KisaAciklama") or "")
            is_active   = bool(raw.get("AktifMi") if raw.get("AktifMi") is not None
                               else raw.get("Aktif", True))

            # ── Fiyat alanları ─────────────────────────────────────────
            price       = float(raw.get("SatisFiyat1") or raw.get("Fiyat") or 0)
            sale_price  = raw.get("SatisFiyat2") or raw.get("IndirimliFiyat")
            sale_price  = float(sale_price) if sale_price else None
            # Ek fiyat kademesi
            fiyat3      = raw.get("SatisFiyat3")
            fiyat3      = float(fiyat3) if fiyat3 else None
            alis_fiyat  = raw.get("AlisFiyat") or raw.get("AlisfFiyat")
            alis_fiyat  = float(alis_fiyat) if alis_fiyat else None
            kdv_orani   = int(raw.get("KDVOrani") or raw.get("KdvOrani") or 20)
            doviz_cins  = str(raw.get("DovizCins") or raw.get("Doviz") or "TL")

            # ── Kategori & marka ───────────────────────────────────────
            category_name  = str(raw.get("KategoriAdi") or raw.get("Kategori") or "")
            kategori_id    = raw.get("KategoriID") or raw.get("KategoriId")
            kategori_id    = int(kategori_id) if kategori_id else None
            brand          = str(raw.get("MarkaAdi") or raw.get("Marka") or "FACETTE")
            marka_id       = raw.get("MarkaID") or raw.get("MarkaId")
            marka_id       = int(marka_id) if marka_id else None

            # ── Stok ──────────────────────────────────────────────────
            stock_qty      = int(raw.get("StokAdedi") or raw.get("Stok") or 0)
            kritik_stok    = raw.get("KritikStokAdedi") or raw.get("KritikStok")
            kritik_stok    = int(kritik_stok) if kritik_stok else None

            # ── Ek özellikler ─────────────────────────────────────────
            birim          = str(raw.get("Birim") or raw.get("BirimAdi") or "")
            agirlik        = raw.get("DesiAgirlik") or raw.get("Agirlik")
            agirlik        = float(agirlik) if agirlik else None
            urun_kodu      = str(raw.get("UrunKodu") or raw.get("Kod") or "")
            grup_kodu      = str(raw.get("GrupKodu") or "")
            sira           = int(raw.get("Sira") or raw.get("SiraNo") or 0)
            siparis_adedi  = int(raw.get("MinSiparisAdedi") or raw.get("MinSipAdet") or 1)
            # SEO alanları
            seo_baslik     = str(raw.get("SeoSayfaBaslik") or raw.get("MetaTitle") or "")
            seo_aciklama   = str(raw.get("SeoSayfaAciklama") or raw.get("MetaDesc") or "")
            seo_anahtar    = str(raw.get("SeoAnahtarKelime") or raw.get("MetaKeyword") or "")
            url            = str(raw.get("Url") or raw.get("SeoUrl") or "")
            # Değerlendirme
            yorum_sayisi   = int(raw.get("YorumSayisi") or 0)
            puan           = float(raw.get("Puan") or raw.get("Yildiz") or 0)
            # Teslimat
            kargo_bedava   = bool(raw.get("KargoBedava") or raw.get("UcretsizKargo") or False)
            temin_suresi   = int(raw.get("TeminSuresi") or raw.get("TedarikSuresi") or 1)
            # Üretici / tedarikçi
            tedarikci_kodu = str(raw.get("TedarikciKodu") or raw.get("TedarikciStokKodu") or "")
            # Vergi / muhasebe
            gtip_kodu      = str(raw.get("GTIPKodu") or raw.get("GtipKodu") or "")

            # ── VARYASYONlar ──────────────────────────────────────────
            variants = []
            try:
                raw_variants = get_variants(ticimax_id)
                for v in raw_variants:
                    if not v:
                        continue
                    v_price = v.get("SatisFiyat1") or v.get("Fiyat")
                    variants.append({
                        "id": str(v.get("VaryasyonID") or generate_id()),
                        "ticimax_varyasyon_id": v.get("VaryasyonID"),
                        "stock_code": str(v.get("StokKodu") or ""),
                        "barcode": str(v.get("Barkod") or ""),
                        "size": str(v.get("Beden") or v.get("DegerAdi") or v.get("Deger1") or ""),
                        "color": str(v.get("Renk") or v.get("RenkAdi") or ""),
                        "stock": int(v.get("StokAdedi") or v.get("Miktar") or 0),
                        "price": float(v_price) if v_price else price,
                        "sale_price": float(v.get("SatisFiyat2")) if v.get("SatisFiyat2") else None,
                        "barcode_2": str(v.get("Barkod2") or ""),
                        "kritik_stok": int(v.get("KritikStokAdedi") or 0),
                        "is_active": bool(v.get("AktifMi") if v.get("AktifMi") is not None else True),
                    })
            except Exception as ve:
                logger.warning(f"Varyasyon hatası (ID={ticimax_id}): {ve}")

            # ── ASORTİ STOK ───────────────────────────────────────────
            try:
                asorti = get_assorted_stock(ticimax_id)
                for a in asorti:
                    if not a:
                        continue
                    sz  = str(a.get("Beden") or a.get("DegerAdi") or a.get("Deger") or "")
                    qty = int(a.get("Miktar") or a.get("StokAdedi") or 0)
                    matched = next((v for v in variants if v.get("size") == sz), None)
                    if matched:
                        matched["stock"] = qty
                    elif sz:
                        variants.append({
                            "id": generate_id(),
                            "ticimax_varyasyon_id": None,
                            "stock_code": stock_code,
                            "barcode": barcode,
                            "size": sz,
                            "color": "",
                            "stock": qty,
                            "price": price,
                            "sale_price": sale_price,
                            "is_active": True,
                        })
            except Exception as ae:
                logger.warning(f"Asorti hatası (ID={ticimax_id}): {ae}")

            # ── RESİMLER ──────────────────────────────────────────────
            images = []
            try:
                raw_images = get_product_images(ticimax_id)
                for img in raw_images:
                    if not img:
                        continue
                    url_img = str(img.get("ResimUrl") or img.get("Url") or
                                  img.get("ResimYolu") or img.get("ResimPath") or "")
                    if url_img and not url_img.startswith("http"):
                        url_img = f"https://www.facette.com.tr{url_img}"
                    if url_img:
                        images.append({
                            "url": url_img,
                            "sira": int(img.get("Sira") or img.get("ResimSira") or 0),
                            "ana_resim": bool(img.get("AnaResim") or img.get("IsAnaResim") or False),
                        })
                # Sıraya göre sırala, ana resim önce
                images.sort(key=lambda x: (not x.get("ana_resim"), x.get("sira", 0)))
            except Exception as ie:
                logger.warning(f"Resim hatası (ID={ticimax_id}): {ie}")

            # Ana resim URL'si
            ana_resim_url = images[0]["url"] if images else ""
            image_urls = [img["url"] for img in images]  # geriye dönük uyumluluk

            doc = {
                "ticimax_id":       ticimax_id,
                "name":             name,
                "slug":             (_generate_slug(name) + f"-{ticimax_id}") if name else str(ticimax_id),
                "description":      description,
                # ── Fiyat ────────────
                "price":            price,
                "sale_price":       sale_price,
                "vat_rate":         kdv_orani,
                # ── Kategori / Marka ─
                "category_name":    category_name,
                "brand":            brand,
                # ── Stok ─────────────
                "stock":            stock_qty,
                "stock_code":       stock_code,
                "barcode":          barcode,
                # ── Durum ────────────
                "is_active":        is_active,
                "is_featured":      False,
                "is_new":           False,
                # ── Medya ────────────
                "images":           image_urls,
                "image_detail":     images,
                "thumbnail":        ana_resim_url,
                # ── Varyasyonlar ─────
                "variants":         variants,
                # ── Kaynak ───────────
                "source":           "ticimax",
                "updated_at":       datetime.now(timezone.utc).isoformat(),
                # ── Ticimax iç alanları (tümü) ─────────────────────────
                "ticimax_urun_kodu":    urun_kodu,
                "ticimax_grup_kodu":    grup_kodu,
                "ticimax_kategori_id":  kategori_id,
                "ticimax_marka_id":     marka_id,
                "ticimax_sira":         sira,
                "ticimax_fiyat3":       fiyat3,
                "ticimax_alis_fiyat":   alis_fiyat,
                "ticimax_doviz":        doviz_cins,
                "ticimax_birim":        birim,
                "ticimax_agirlik":      agirlik,
                "ticimax_kritik_stok":  kritik_stok,
                "ticimax_min_siparis":  siparis_adedi,
                "ticimax_kargo_bedava": kargo_bedava,
                "ticimax_temin_suresi": temin_suresi,
                "ticimax_seo_baslik":   seo_baslik,
                "ticimax_seo_aciklama": seo_aciklama,
                "ticimax_seo_anahtar":  seo_anahtar,
                "ticimax_url":          url,
                "ticimax_yorum_sayisi": yorum_sayisi,
                "ticimax_puan":         puan,
                "ticimax_tedarikci_kodu": tedarikci_kodu,
                "ticimax_gtip_kodu":    gtip_kodu,
            }

            existing = await db.products.find_one({"ticimax_id": ticimax_id})
            if existing:
                await db.products.update_one({"ticimax_id": ticimax_id}, {"$set": doc})
                updated += 1
            else:
                doc["id"] = await generate_short_id("products")
                doc["created_at"] = datetime.now(timezone.utc).isoformat()
                await db.products.insert_one(doc)
                imported += 1

            fetched += 1
            if fetched >= limit:
                break

        page += 1
        if len(products_raw) < page_size:
            break

    await db.settings.update_one(
        {"id": "ticimax"},
        {"$set": {"last_sync": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )

    return {
        "success": True,
        "imported": imported,
        "updated": updated,
        "total": imported + updated,
        "total_remote": total_remote,
        "message": f"{imported} yeni ürün eklendi, {updated} ürün güncellendi"
    }


@router.post("/ticimax/orders/import")
async def import_ticimax_orders(
    limit: int = Query(200, ge=1, le=2000),
    days: int = Query(20, ge=1, le=365, description="Son kaç günün siparişleri çekilsin"),
    current_user: dict = Depends(require_admin)
):
    """Fetch orders from Ticimax (last N days) and upsert into local MongoDB."""
    import sys, os
    from datetime import timedelta
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from ticimax_client import get_orders as tc_get_orders, get_order_items

    # Tarih aralığı hesapla (MongoDB filtreleme için)
    end_dt   = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    start_date_str = start_dt.strftime("%d.%m.%Y")
    end_date_str   = end_dt.strftime("%d.%m.%Y")
    logger.info(f"Ticimax sipariş import: son {days} gün ({start_date_str} - {end_date_str})")

    # Önce tarih filtresiyle dene, hata gelirse filtresiz çek
    try:
        orders_raw = tc_get_orders(
            page=1,
            page_size=limit,
            start_date=start_date_str,
            end_date=end_date_str,
        )
        logger.info(f"Tarihli çekim başarılı: {len(orders_raw)} sipariş")
    except Exception as e:
        logger.warning(f"Tarih filtreli çekim başarısız ({e}), filtresiz deneniyor...")
        try:
            orders_raw = tc_get_orders(page=1, page_size=limit)
            logger.info(f"Filtresiz çekim başarılı: {len(orders_raw)} sipariş")
        except Exception as e2:
            raise HTTPException(status_code=502, detail=f"Ticimax bağlantı hatası: {str(e2)}")

    imported = 0
    updated = 0

    for raw in orders_raw:
        if not raw:
            continue
        ticimax_order_id = raw.get("SiparisID") or raw.get("ID") or raw.get("OdemeID")
        if not ticimax_order_id:
            continue
        ticimax_order_id = int(ticimax_order_id)

        # Real Ticimax order field names
        order_number = str(raw.get("SiparisNo") or raw.get("SiparisKodu") or raw.get("SiparisID") or ticimax_order_id)
        total        = float(raw.get("ToplamTutar") or raw.get("GenelToplam") or raw.get("Tutar") or 0)
        status_raw   = str(raw.get("SiparisDurumu") or raw.get("Durum") or "Yeni")
        status_map   = {
            "Yeni": "pending", "Onaylandı": "confirmed", "Hazırlanıyor": "processing",
            "Kargoya Verildi": "shipped", "Teslim Edildi": "delivered",
            "İptal": "cancelled", "İade": "returned"
        }
        status       = status_map.get(status_raw, "pending")
        created_at   = str(raw.get("SiparisTarihi") or raw.get("Tarih") or
                           datetime.now(timezone.utc).isoformat())

        first_name   = str(raw.get("TeslimatAdi") or raw.get("FaturaAdi") or raw.get("Adi") or "")
        last_name    = str(raw.get("TeslimatSoyadi") or raw.get("FaturaSoyadi") or raw.get("Soyadi") or "")
        phone        = str(raw.get("TeslimatTelefon") or raw.get("Telefon") or raw.get("GSM") or "")
        email        = str(raw.get("Email") or raw.get("EPosta") or raw.get("UyeEmail") or "")
        address      = str(raw.get("TeslimatAdres") or raw.get("FaturaAdres") or raw.get("Adres") or "")
        city         = str(raw.get("TeslimatIl") or raw.get("TeslimatSehir") or raw.get("Sehir") or "")
        district     = str(raw.get("TeslimatIlce") or raw.get("Ilce") or "")

        # Fetch line items
        items = []
        try:
            raw_items = get_order_items(ticimax_order_id)
            for item in raw_items:
                if not item:
                    continue
                items.append({
                    "product_name": str(item.get("UrunAdi") or item.get("Adi") or ""),
                    "stock_code":   str(item.get("StokKodu") or ""),
                    "barcode":      str(item.get("Barkod") or ""),
                    "quantity":     int(item.get("Adet") or item.get("Miktar") or 1),
                    "price":        float(item.get("BirimFiyat") or item.get("Fiyat") or 0),
                    "size":         str(item.get("Beden") or ""),
                    "color":        str(item.get("Renk") or ""),
                })
        except Exception:
            pass

        doc = {
            "ticimax_order_id": ticimax_order_id,
            "order_number": order_number,
            "items": items,
            "shipping_address": {
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "email": email,
                "address": address,
                "city": city,
                "district": district,
            },
            "subtotal": total,
            "shipping_cost": 0,
            "total": total,
            "payment_method": "ticimax",
            "payment_status": "paid",
            "status": status,
            "platform": "ticimax",
            "source": "ticimax",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        existing = await db.orders.find_one({"ticimax_order_id": ticimax_order_id})
        if existing:
            await db.orders.update_one({"ticimax_order_id": ticimax_order_id}, {"$set": doc})
            updated += 1
        else:
            doc["id"] = generate_id()
            doc["user_id"] = None
            doc["created_at"] = created_at
            await db.orders.insert_one(doc)
            imported += 1

    await db.settings.update_one(
        {"id": "ticimax"},
        {"$set": {"last_sync": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )

    return {
        "success": True,
        "imported": imported,
        "updated": updated,
        "total": imported + updated,
        "message": f"{imported} yeni sipariş eklendi, {updated} sipariş güncellendi"
    }


# ==================== XML FEED IMPORT ====================

XML_FEED_URL = "https://www.facette.com.tr/XMLExport/7BECCB0A782647BFAB843E68AD11E468"
_NS = {"g": "http://base.google.com/ns/1.0"}

def _xml_text(item: ET.Element, tag: str, ns: dict = _NS) -> str:
    el = item.find(tag, ns)
    return (el.text or "").strip() if el is not None else ""

def _xml_all(item: ET.Element, tag: str, ns: dict = _NS) -> list:
    return [(el.text or "").strip() for el in item.findall(tag, ns) if el is not None and el.text]

@router.post("/xml/products/import")
async def import_xml_products(
    xml_url: str = Query(XML_FEED_URL, description="Google Shopping XML URL"),
    current_user: dict = Depends(require_admin)
):
    """
    Google Shopping XML feed'inden ürünleri çekip MongoDB'ye upsert eder.
    Varsayılan URL: facette.com.tr XML export
    """
    import html

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(xml_url)
            resp.raise_for_status()
            xml_bytes = resp.content
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"XML feed çekilemedi: {str(e)}")

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise HTTPException(status_code=422, detail=f"XML parse hatası: {str(e)}")

    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else root.findall(".//item")

    if not items:
        raise HTTPException(status_code=422, detail="XML'de hiç ürün (item) bulunamadı")

    imported = 0
    updated = 0
    errors = 0

    for item in items:
        try:
            xml_id = _xml_text(item, "g:id")
            title  = _xml_text(item, "g:title")
            if not xml_id or not title:
                continue

            desc = html.unescape(_xml_text(item, "g:description"))

            def parse_price(s: str) -> Optional[float]:
                if not s:
                    return None
                try:
                    return float(s.split()[0])
                except (ValueError, IndexError):
                    return None

            price      = parse_price(_xml_text(item, "g:price")) or 0.0
            sale_price = parse_price(_xml_text(item, "g:sale_price"))

            availability  = _xml_text(item, "g:availability")
            in_stock      = availability.lower() == "in stock"
            product_type  = _xml_text(item, "g:product_type")
            goog_cat      = _xml_text(item, "g:google_product_category")
            category_name = product_type or goog_cat
            brand         = _xml_text(item, "g:brand") or "FACETTE"
            product_url   = _xml_text(item, "g:link")
            mpn           = _xml_text(item, "g:mpn")
            label_0       = _xml_text(item, "g:custom_label_0")
            label_1       = _xml_text(item, "g:custom_label_1")

            main_image   = _xml_text(item, "g:image_link")
            extra_images = _xml_all(item, "g:additional_image_link")
            all_images: list = []
            seen_imgs: set = set()
            for img in [main_image] + extra_images:
                if img and img not in seen_imgs:
                    all_images.append(img)
                    seen_imgs.add(img)

            slug = product_url.rstrip("/").split("/")[-1] if product_url else None
            if not slug:
                slug = _generate_slug(title) + f"-{xml_id}"

            doc = {
                "xml_id":        xml_id,
                "name":          title,
                "slug":          slug,
                "description":   desc,
                "price":         price,
                "sale_price":    sale_price,
                "brand":         brand,
                "category_name": category_name,
                "stock":         1 if in_stock else 0,
                "is_active":     True,
                "is_featured":   False,
                "is_new":        False,
                "images":        all_images,
                "thumbnail":     all_images[0] if all_images else "",
                "barcode":       mpn,
                "source":        "xml_feed",
                "product_url":   product_url,
                "availability":  availability,
                "xml_label_0":   label_0,
                "xml_label_1":   label_1,
                "updated_at":    datetime.now(timezone.utc).isoformat(),
            }

            existing = await db.products.find_one({"xml_id": xml_id})
            if existing:
                await db.products.update_one({"xml_id": xml_id}, {"$set": doc})
                updated += 1
            else:
                doc["id"]         = generate_id()
                doc["created_at"] = datetime.now(timezone.utc).isoformat()
                doc["variants"]   = []
                await db.products.insert_one(doc)
                imported += 1

        except Exception as e:
            logger.error(f"XML item parse hatası (id={_xml_text(item, 'g:id')}): {e}")
            errors += 1
            continue

    await db.settings.update_one(
        {"id": "xml_feed"},
        {"$set": {"xml_url": xml_url, "last_sync": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )

    return {
        "success":  True,
        "imported": imported,
        "updated":  updated,
        "total":    imported + updated,
        "errors":   errors,
        "message":  f"{imported} yeni ürün eklendi, {updated} ürün güncellendi" + (f", {errors} hata" if errors else "")
    }

@router.get("/xml/status")
async def get_xml_feed_status():
    """XML feed son senkronizasyon bilgisi"""
    settings = await db.settings.find_one({"id": "xml_feed"}) or {}
    return {
        "xml_url":    settings.get("xml_url", XML_FEED_URL),
        "last_sync":  settings.get("last_sync"),
        "configured": True,
    }

# ==================== TRENDYOL CLAIMS (İADE/İPTAL) ====================

@router.get("/trendyol/claims/sync")
async def sync_trendyol_claims(
    days_back: int = 90,
    current_user: dict = Depends(require_admin)
):
    """Trendyol'dan iade/iptal (claim) kayıtlarını çeker ve MongoDB'ye kaydeder."""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")

    from trendyol_client import TrendyolClient
    from datetime import timedelta

    client = TrendyolClient(
        supplier_id=config["supplier_id"],
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        mode=config["mode"]
    )

    end_date = datetime.now(timezone.utc)
    total_synced = 0
    order_cache = {}  # order_number -> order_data cache

    # Trendyol max 15 günlük aralık destekliyor, parçalıyoruz
    chunk_days = 15
    current_end = end_date

    while True:
        current_start = current_end - timedelta(days=chunk_days)
        days_elapsed = (end_date - current_start).days

        if days_elapsed > days_back:
            current_start = end_date - timedelta(days=days_back)

        start_ts = int(current_start.timestamp() * 1000)
        end_ts = int(current_end.timestamp() * 1000)

        current_page = 0
        page_size = 200

        while True:
            try:
                url = f"{client.base_url}/order/sellers/{client.supplier_id}/claims"
                params = {
                    "page": current_page,
                    "size": page_size,
                    "startDate": start_ts,
                    "endDate": end_ts,
                }
                async with httpx.AsyncClient(timeout=30.0) as http_client:
                    headers = client._get_headers()
                    response = await http_client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    result = response.json()
            except Exception as e:
                logger.error(f"Claims sync error: {str(e)}")
                break

            data = result if isinstance(result, dict) else {}
            content = data.get("content", [])
            total_pages = data.get("totalPages", 0)

            if not content:
                break

            for claim in content:
                claim_id = str(claim.get("claimId", claim.get("id", "")))
                if not claim_id:
                    continue

                # Zaten kayıtlı iade varsa atla (sadece yeni olanları işle)
                existing_claim = await db.trendyol_claims.find_one({"claim_id": claim_id}, {"_id": 1, "items": 1})
                if existing_claim:
                    total_synced += 1
                    continue

                # Claim items'dan tip ve sebep çıkar
                claim_items = []
                claim_type = ""
                claim_reason = ""
                refund_amount = 0
                
                # Claims API'sinde iskonto bilgisi yok. Sipariş API'sinden çek.
                order_number = str(claim.get("orderNumber", ""))
                order_discount_map = {}  # barcode -> {discount, gross_price, net_price}
                if order_number:
                    # Cache kontrolü: aynı sipariş numarasını tekrar çekme
                    cache_key = f"order_{order_number}"
                    if cache_key not in order_cache:
                        try:
                            order_data = await client.get_orders(order_number=order_number)
                            order_cache[cache_key] = order_data
                        except Exception as e:
                            logger.warning(f"Could not fetch order {order_number} for discount: {e}")
                            order_cache[cache_key] = {}
                    
                    cached = order_cache.get(cache_key, {})
                    for pkg in cached.get("content", []):
                        for line in pkg.get("lines", []):
                            bc = line.get("barcode", "")
                            line_gross = line.get("lineGrossAmount", line.get("amount", 0))
                            line_net = line.get("price", 0)
                            line_disc = line.get("discount", 0)
                            qty = max(line.get("quantity", 1), 1)
                            if bc:
                                order_discount_map[bc] = {
                                    "gross": line_gross / qty if line_gross else 0,
                                    "net": line_net / qty if line_net else 0,
                                    "discount": line_disc / qty if line_disc else 0,
                                }

                for item in claim.get("items", []):
                    order_line = item.get("orderLine", {})
                    for ci in item.get("claimItems", []):
                        reason_info = ci.get("customerClaimItemReason", {})
                        if not claim_type:
                            code = reason_info.get("code", "").upper()
                            if code in ["ABANDON", "UNDELIVERED", "NOTDELIVERED"]:
                                claim_type = "CANCEL"
                            else:
                                claim_type = "RETURN"
                        if not claim_reason:
                            claim_reason = reason_info.get("name", "")

                        barcode = order_line.get("barcode", "")
                        claim_price = order_line.get("price", 0)
                        
                        # İskontoyu sipariş verisinden al
                        order_info = order_discount_map.get(barcode, {})
                        if order_info:
                            gross_price = order_info.get("gross", claim_price)
                            net_price = order_info.get("net", claim_price)
                            discount = order_info.get("discount", 0)
                        else:
                            # Fallback: Claims API verisini kullan (iskonto yok)
                            gross_price = claim_price
                            net_price = claim_price
                            discount = 0
                        
                        claim_items.append({
                            "claim_item_id": str(ci.get("id", "")),
                            "productName": order_line.get("productName", ""),
                            "barcode": barcode,
                            "unit_price": gross_price,
                            "discount_amount": discount,
                            "price": net_price,
                            "quantity": 1,
                            "reason": reason_info.get("name", "")
                        })
                        refund_amount += net_price

                # Tarih formatı
                claim_date = claim.get("claimDate")
                created_date_str = ""
                if claim_date:
                    try:
                        created_date_str = datetime.fromtimestamp(claim_date / 1000, tz=timezone.utc).isoformat()
                    except:
                        created_date_str = str(claim_date)

                # Fatura numarasını çıkar: sipariş verisinden veya claim'den
                invoice_number = ""
                for item in claim.get("items", []):
                    ol = item.get("orderLine", {})
                    inv = ol.get("invoiceNumber", "") or item.get("invoiceNumber", "")
                    if inv:
                        invoice_number = str(inv)
                        break
                if not invoice_number:
                    invoice_number = str(claim.get("invoiceNumber", "") or "")
                # Sipariş verisinden fatura no çek
                if not invoice_number and order_discount_map:
                    try:
                        _order_data = await client.get_orders(order_number=order_number)
                        for pkg in _order_data.get("content", []):
                            inv_no = pkg.get("invoiceNumber", "")
                            if inv_no:
                                invoice_number = str(inv_no)
                                break
                    except Exception:
                        pass

                claim_doc = {
                    "claim_id": claim_id,
                    "order_number": order_number,
                    "claim_type": claim_type,
                    "claim_reason": claim_reason,
                    "claim_status": claim.get("status", "Returned"),
                    "customer_name": f"{claim.get('customerFirstName', '')} {claim.get('customerLastName', '')}".strip(),
                    "created_date": created_date_str,
                    "items": claim_items,
                    "refund_amount": refund_amount,
                    "invoice_number": invoice_number,
                    "invoice_link": claim.get("invoiceLink", ""), # Yeni eklendi
                    "cargo_tracking_number": str(claim.get("cargoTrackingNumber", "")),
                    "cargo_provider_name": claim.get("cargoProviderName", ""),
                    "raw_data": claim,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }

                await db.trendyol_claims.update_one(
                    {"claim_id": claim_id},
                    {"$set": claim_doc, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat()}},
                    upsert=True
                )
                total_synced += 1

            current_page += 1
            if current_page >= total_pages:
                break

        current_end = current_start
        if days_elapsed >= days_back:
            break

    return {
        "message": f"Son {days_back} gündeki toplam {total_synced} iade/iptal kaydı senkronize edildi",
        "total_synced": total_synced,
        "days_back": days_back
    }


@router.post("/trendyol/claims/fix-discounts")
async def fix_claim_discounts(current_user: dict = Depends(require_admin)):
    """Fix discount data for existing claims by fetching from order API"""
    settings = await db.settings.find_one({"id": "trendyol"}, {"_id": 0})
    if not settings or not settings.get("api_key"):
        raise HTTPException(status_code=400, detail="Trendyol API ayarları eksik")
    
    from trendyol_client import TrendyolClient
    client = TrendyolClient(settings["supplier_id"], settings["api_key"], settings["api_secret"])
    
    # Get claims that need discount fix (where items have 0 discount)
    claims = await db.trendyol_claims.find({}, {"_id": 0, "claim_id": 1, "order_number": 1, "items": 1}).to_list(None)
    
    order_cache = {}
    fixed = 0
    
    for claim in claims:
        order_number = claim.get("order_number", "")
        if not order_number:
            continue
        
        items = claim.get("items", [])
        needs_fix = any(item.get("discount_amount", 0) == 0 and item.get("unit_price", 0) == item.get("price", 0) for item in items)
        if not needs_fix:
            continue
        
        # Get order data (cached)
        if order_number not in order_cache:
            try:
                order_cache[order_number] = await client.get_orders(order_number=order_number)
            except Exception:
                order_cache[order_number] = {}
        
        cached = order_cache.get(order_number, {})
        discount_map = {}
        invoice_number = ""
        for pkg in cached.get("content", []):
            if not invoice_number:
                invoice_number = pkg.get("invoiceNumber", "")
            for line in pkg.get("lines", []):
                bc = line.get("barcode", "")
                qty = max(line.get("quantity", 1), 1)
                if bc:
                    discount_map[bc] = {
                        "gross": (line.get("lineGrossAmount", line.get("amount", 0)) or 0) / qty,
                        "net": (line.get("price", 0) or 0) / qty,
                        "discount": (line.get("discount", 0) or 0) / qty,
                    }
        
        updated_items = []
        refund_amount = 0
        for item in items:
            bc = item.get("barcode", "")
            if bc in discount_map:
                item["unit_price"] = discount_map[bc]["gross"]
                item["discount_amount"] = discount_map[bc]["discount"]
                item["price"] = discount_map[bc]["net"]
            refund_amount += item.get("price", 0)
            updated_items.append(item)
        
        update_set = {"items": updated_items, "refund_amount": refund_amount}
        if invoice_number:
            update_set["invoice_number"] = invoice_number
        
        await db.trendyol_claims.update_one(
            {"claim_id": claim["claim_id"]},
            {"$set": update_set}
        )
        fixed += 1
    
    return {"success": True, "fixed": fixed, "message": f"{fixed} iadenin iskonto bilgisi güncellendi"}


@router.get("/trendyol/claims")
async def get_trendyol_claims(
    page: int = 1,
    limit: int = 20,
    claim_type: str = "",
    search: str = "",
    current_user: dict = Depends(require_admin)
):
    """Yerel veritabanındaki iade/iptal kayıtlarını listele."""
    query = {}
    if claim_type:
        query["claim_type"] = claim_type
    if search:
        query["$or"] = [
            {"order_number": {"$regex": search, "$options": "i"}},
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"claim_id": {"$regex": search, "$options": "i"}}
        ]

    total = await db.trendyol_claims.count_documents(query)
    skip = (page - 1) * limit
    claims = await db.trendyol_claims.find(query, {"_id": 0, "raw_data": 0}).skip(skip).limit(limit).sort("created_date", -1).to_list(limit)

    # İstatistikler
    total_returns = await db.trendyol_claims.count_documents({"claim_type": "RETURN"})
    total_cancels = await db.trendyol_claims.count_documents({"claim_type": "CANCEL"})
    
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$refund_amount"}}}]
    refund_result = await db.trendyol_claims.aggregate(pipeline).to_list(1)
    total_refund = refund_result[0]["total"] if refund_result else 0

    return {
        "claims": claims,
        "total": total,
        "page": page,
        "limit": limit,
        "stats": {
            "total_returns": total_returns,
            "total_cancels": total_cancels,
            "total_refund": total_refund
        }
    }

@router.get("/trendyol/claims/{claim_id}")
async def get_trendyol_claim_detail(claim_id: str, current_user: dict = Depends(require_admin)):
    """Tek bir iade/iptal kaydının detayını getir."""
    claim = await db.trendyol_claims.find_one({"claim_id": claim_id}, {"_id": 0})
    if not claim:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    return claim


@router.post("/trendyol/claims/{claim_id}/gider-pusulasi")
async def generate_gider_pusulasi(claim_id: str, current_user: dict = Depends(require_admin)):
    """Generate expense receipt (gider pusulası) data for a return claim"""
    claim = await db.trendyol_claims.find_one({"claim_id": claim_id}, {"_id": 0})
    if not claim:
        raise HTTPException(status_code=404, detail="İade kaydı bulunamadı")

    settings = await db.settings.find_one({"id": "main"}, {"_id": 0})
    company = settings.get("company_info", {}) if settings else {}

    items = claim.get("items", [])
    total_net = sum(item.get("price", 0) * item.get("quantity", 1) for item in items)
    total_discount = sum(item.get("discount_amount", 0) * item.get("quantity", 1) for item in items)
    total_gross = sum(item.get("unit_price", 0) * item.get("quantity", 1) for item in items)
    vat_rate = settings.get("default_vat_rate", 10) if settings else 10
    vat_amount = round(total_net * vat_rate / (100 + vat_rate), 2)
    net_without_vat = round(total_net - vat_amount, 2)

    last_gp = await db.gider_pusulasi.find_one({}, sort=[("number", -1)])
    gp_number = (last_gp.get("number", 0) + 1) if last_gp else 1

    gider_pusulasi = {
        "number": gp_number,
        "display_number": f"GP-{gp_number:06d}",
        "claim_id": claim_id,
        "order_number": claim.get("order_number", ""),
        "date": datetime.now(timezone.utc).isoformat(),
        "company": company,
        "customer": {
            "name": claim.get("customer_name", ""),
            "address": claim.get("shipping_address", ""),
            "city": claim.get("shipping_city", ""),
        },
        "items": [{
            "name": item.get("productName", ""),
            "barcode": item.get("barcode", ""),
            "quantity": item.get("quantity", 1),
            "unit_price": item.get("unit_price", 0),
            "discount": item.get("discount_amount", 0),
            "net_price": item.get("price", 0),
            "reason": item.get("reason", "")
        } for item in items],
        "totals": {
            "gross": total_gross,
            "discount": total_discount,
            "net": total_net,
            "vat_rate": vat_rate,
            "vat_amount": vat_amount,
            "net_without_vat": net_without_vat,
        },
        "claim_type": claim.get("claim_type", ""),
        "claim_reason": claim.get("claim_reason", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.gider_pusulasi.update_one(
        {"claim_id": claim_id},
        {"$set": gider_pusulasi},
        upsert=True
    )

    await db.trendyol_claims.update_one(
        {"claim_id": claim_id},
        {"$set": {"has_gider_pusulasi": True, "gider_pusulasi_no": gider_pusulasi["display_number"]}}
    )

    return {"success": True, "gider_pusulasi": gider_pusulasi}


@router.post("/trendyol/claims/bulk-gider-pusulasi")
async def bulk_generate_gider_pusulasi(payload: dict, current_user: dict = Depends(require_admin)):
    """Generate expense receipts for multiple claims"""
    claim_ids = payload.get("claim_ids", [])
    if not claim_ids:
        raise HTTPException(status_code=400, detail="Claim ID listesi boş")

    results = []
    for cid in claim_ids:
        try:
            result = await generate_gider_pusulasi(cid, current_user)
            results.append(result.get("gider_pusulasi"))
        except Exception:
            pass

    return {"success": True, "gider_pusulalari": results, "count": len(results)}



# ==================== TRENDYOL STOK & FİYAT GÜNCELLEME ====================

@router.post("/trendyol/products/{product_id}/update-stock-price")
async def update_trendyol_stock_price(
    product_id: str,
    current_user: dict = Depends(require_admin)
):
    """Tek bir ürünün stok ve fiyatını Trendyol'a gönderir."""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")

    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    from trendyol_client import TrendyolClient
    client = TrendyolClient(
        supplier_id=config["supplier_id"],
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        mode=config["mode"]
    )

    # Varyantlı ürün mü?
    items = []
    variants = product.get("variants", [])
    trendyol_multiplier = product.get("trendyol_multiplier", 0)
    base_price = product.get("price", 0)
    sale_price = product.get("sale_price") or base_price
    
    if trendyol_multiplier > 0:
        sale_price = sale_price * (1 + trendyol_multiplier / 100)
        base_price = base_price * (1 + trendyol_multiplier / 100)

    if variants:
        for v in variants:
            barcode = v.get("barcode", "")
            if not barcode:
                continue
            v_price = base_price + (v.get("price_diff", 0) or 0)
            v_sale = sale_price + (v.get("price_diff", 0) or 0)
            items.append({
                "barcode": barcode,
                "quantity": v.get("stock", 0),
                "salePrice": round(v_sale, 2),
                "listPrice": round(v_price, 2)
            })
    else:
        barcode = product.get("barcode", "")
        if barcode:
            items.append({
                "barcode": barcode,
                "quantity": product.get("stock", 0),
                "salePrice": round(sale_price, 2),
                "listPrice": round(base_price, 2)
            })

    if not items:
        raise HTTPException(status_code=400, detail="Ürünün barkodu bulunamadı")

    try:
        url = f"{client.base_url}/sapigw/suppliers/{client.supplier_id}/products/price-and-inventory"
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            headers = client._get_headers()
            response = await http_client.put(url, headers=headers, json={"items": items})
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Trendyol stock/price update error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Trendyol API hatası: {e.response.text}")
    except Exception as e:
        logger.error(f"Trendyol stock/price update error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    batch_id = result.get("batchRequestId", "")
    await db.products.update_one(
        {"id": product_id},
        {"$set": {"trendyol_stock_price_batch": str(batch_id), "trendyol_stock_price_updated": datetime.now(timezone.utc).isoformat()}}
    )

    return {
        "success": True,
        "message": f"{len(items)} kalem stok/fiyat güncellendi",
        "batch_id": batch_id,
        "items_count": len(items)
    }

@router.post("/trendyol/categories/{category_id}/update-stock-price")
async def update_trendyol_category_stock_price(
    category_id: str,
    current_user: dict = Depends(require_admin)
):
    """Bir kategorideki tüm ürünlerin stok ve fiyatlarını Trendyol'a gönderir."""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")

    # Kategorideki tüm ürünleri bul
    category = await db.categories.find_one({"id": category_id}, {"_id": 0})
    if not category:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı")

    products = await db.products.find(
        {"category_name": category.get("name"), "is_active": True},
        {"_id": 0}
    ).to_list(500)

    if not products:
        # Fallback: try category id
        products = await db.products.find(
            {"category_id": category_id, "is_active": True},
            {"_id": 0}
        ).to_list(500)

    if not products:
        raise HTTPException(status_code=404, detail="Bu kategoride ürün bulunamadı")

    from trendyol_client import TrendyolClient
    client = TrendyolClient(
        supplier_id=config["supplier_id"],
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        mode=config["mode"]
    )

    items = []
    for product in products:
        trendyol_multiplier = product.get("trendyol_multiplier", 0)
        base_price = product.get("price", 0)
        sale_price = product.get("sale_price") or base_price
        
        if trendyol_multiplier > 0:
            sale_price = sale_price * (1 + trendyol_multiplier / 100)
            base_price = base_price * (1 + trendyol_multiplier / 100)

        variants = product.get("variants", [])
        if variants:
            for v in variants:
                barcode = v.get("barcode", "")
                if not barcode:
                    continue
                v_price = base_price + (v.get("price_diff", 0) or 0)
                v_sale = sale_price + (v.get("price_diff", 0) or 0)
                items.append({
                    "barcode": barcode,
                    "quantity": v.get("stock", 0),
                    "salePrice": round(v_sale, 2),
                    "listPrice": round(v_price, 2)
                })
        else:
            barcode = product.get("barcode", "")
            if barcode:
                items.append({
                    "barcode": barcode,
                    "quantity": product.get("stock", 0),
                    "salePrice": round(sale_price, 2),
                    "listPrice": round(base_price, 2)
                })

    if not items:
        raise HTTPException(status_code=400, detail="Bu kategorideki ürünlerin barkodu bulunamadı")

    # Trendyol max 1000 item per request
    batch_ids = []
    for i in range(0, len(items), 1000):
        chunk = items[i:i+1000]
        try:
            url = f"{client.base_url}/sapigw/suppliers/{client.supplier_id}/products/price-and-inventory"
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                headers = client._get_headers()
                response = await http_client.put(url, headers=headers, json={"items": chunk})
                response.raise_for_status()
                result = response.json()
                batch_ids.append(result.get("batchRequestId", ""))
        except Exception as e:
            logger.error(f"Trendyol category stock/price update error: {str(e)}")

    return {
        "success": True,
        "message": f"{category.get('name')} kategorisindeki {len(items)} kalem stok/fiyat güncellendi",
        "items_count": len(items),
        "batch_ids": batch_ids
    }

# ==================== TRENDYOL KARGO ETİKETİ ====================

@router.get("/trendyol/cargo/label/{shipment_package_id}")
async def get_trendyol_cargo_label(
    shipment_package_id: str,
    current_user: dict = Depends(require_admin)
):
    """Trendyol kargo etiketi PDF/ZPL verisini getirir."""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")

    from trendyol_client import TrendyolClient
    client = TrendyolClient(
        supplier_id=config["supplier_id"],
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        mode=config["mode"]
    )

    try:
        url = f"{client.base_url}/shipment/sellers/{client.supplier_id}/shipment-packages/{shipment_package_id}/shipping-label"
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            headers = client._get_headers()
            response = await http_client.get(url, headers=headers)
            response.raise_for_status()
            
            content_type = response.headers.get("content-type", "")
            
            if "application/pdf" in content_type:
                return Response(
                    content=response.content,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=label_{shipment_package_id}.pdf"}
                )
            else:
                # ZPL veya text format
                return Response(
                    content=response.content,
                    media_type=content_type or "application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename=label_{shipment_package_id}"}
                )
    except httpx.HTTPStatusError as e:
        logger.error(f"Cargo label error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Etiket alınamadı: {e.response.text}")
    except Exception as e:
        logger.error(f"Cargo label error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== TRENDYOL CLAIMS APPROVE/ISSUE ====================

@router.get("/trendyol/claims/issue-reasons")
async def get_trendyol_issue_reasons(current_user: dict = Depends(require_admin)):
    """Fetch claim issue reasons from Trendyol"""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")

    from trendyol_client import TrendyolClient
    client = TrendyolClient(
        supplier_id=config["supplier_id"],
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        mode=config["mode"]
    )

    try:
        url = f"{client.base_url}/order/sellers/{client.supplier_id}/claim-issue-reasons"
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            headers = client._get_headers()
            response = await http_client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch issue reasons: {str(e)}")
        # Return common fallback reasons
        return [
            {"id": 1, "name": "Kullanım Hatası / Tüketici Kaynaklı Hasar"},
            {"id": 2, "name": "Ürün Orijinal Kutusunda / Ambalajında Değil"},
            {"id": 4, "name": "Eksik Aksesuar / Parça"},
            {"id": 6, "name": "İade Süresi Geçmiş"},
            {"id": 21, "name": "Ürün Kullanılmış / Etiketi Koparılmış"}
        ]

@router.post("/trendyol/claims/{claim_id}/approve")
async def approve_trendyol_claim(
    claim_id: str,
    payload: dict,
    current_user: dict = Depends(require_admin)
):
    """Approve a list of claim items in Trendyol"""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")

    claim_item_ids = payload.get("claim_item_ids", [])
    if not claim_item_ids:
        raise HTTPException(status_code=400, detail="Onaylanacak iade kalemleri belirtilmedi.")

    from trendyol_client import TrendyolClient
    client = TrendyolClient(
        supplier_id=config["supplier_id"],
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        mode=config["mode"]
    )

    try:
        url = f"{client.base_url}/order/sellers/{client.supplier_id}/claims/{claim_id}/items/approve"
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            headers = client._get_headers()
            req_data = {
                "claimLineItemIdList": claim_item_ids
            }
            response = await http_client.put(url, headers=headers, json=req_data)
            response.raise_for_status()
            
            await log_integration_event("trendyol", "claim_approve", current_user["email"], claim_id, "success", f"{len(claim_item_ids)} kalem onaylandı", req_data)
            
            # Update claim in DB with action status
            await db.trendyol_claims.update_one(
                {"claim_id": claim_id},
                {"$set": {
                    "panel_action": "approved",
                    "panel_action_date": datetime.now(timezone.utc).isoformat(),
                    "panel_action_by": current_user["email"],
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            return {"success": True, "message": "İade işlemi Trendyol tarafında onaylandı."}

    except httpx.HTTPStatusError as e:
        logger.error(f"Claim approve error: {e.response.status_code} - {e.response.text}")
        await log_integration_event("trendyol", "claim_approve", current_user["email"], claim_id, "error", f"API Hatası: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Onay işlemi başarısız: {e.response.text}")
    except Exception as e:
        logger.error(f"Claim approve error: {str(e)}")
        await log_integration_event("trendyol", "claim_approve", current_user["email"], claim_id, "error", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trendyol/claims/{claim_id}/issue")
async def issue_trendyol_claim(
    claim_id: str,
    payload: dict,
    current_user: dict = Depends(require_admin)
):
    """Reject/Issue a list of claim items in Trendyol"""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")

    claim_item_ids = payload.get("claim_item_ids", [])
    issue_reason_id = payload.get("issue_reason_id")
    description = payload.get("description", "")

    if not claim_item_ids or not issue_reason_id:
        raise HTTPException(status_code=400, detail="İtiraz edilecek kalemler veya itiraz sebebi belirtilmedi.")

    from trendyol_client import TrendyolClient
    client = TrendyolClient(
        supplier_id=config["supplier_id"],
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        mode=config["mode"]
    )

    try:
        url = f"{client.base_url}/order/sellers/{client.supplier_id}/claims/{claim_id}/issue"
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            headers = client._get_headers()
            req_data = {
                "claimIssueReasonId": int(issue_reason_id),
                "claimItemIdList": claim_item_ids,
                "description": description
            }
            response = await http_client.post(url, headers=headers, json=req_data)
            response.raise_for_status()
            
            await log_integration_event("trendyol", "claim_issue", current_user["email"], claim_id, "success", f"{len(claim_item_ids)} kalem için itiraz açıldı", req_data)
            
            # Update claim in DB with action status
            await db.trendyol_claims.update_one(
                {"claim_id": claim_id},
                {"$set": {
                    "panel_action": "issued",
                    "panel_action_date": datetime.now(timezone.utc).isoformat(),
                    "panel_action_by": current_user["email"],
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            return {"success": True, "message": "İade işlemi için Trendyol tarafında itiraz oluşturuldu."}

    except httpx.HTTPStatusError as e:
        logger.error(f"Claim issue error: {e.response.status_code} - {e.response.text}")
        await log_integration_event("trendyol", "claim_issue", current_user["email"], claim_id, "error", f"API Hatası: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"İtiraz işlemi başarısız: {e.response.text}")
    except Exception as e:
        logger.error(f"Claim issue error: {str(e)}")
        await log_integration_event("trendyol", "claim_issue", current_user["email"], claim_id, "error", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ==================== TRENDYOL Q&A ====================

@router.get("/trendyol/questions/sync")
async def sync_trendyol_questions(current_user: dict = Depends(require_admin)):
    """Sync unanswered questions from Trendyol and store in DB"""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")

    supplier_id = config["supplier_id"]
    headers = await get_trendyol_headers()
    if not headers:
        raise HTTPException(status_code=400, detail="Trendyol kimlik bilgileri eksik")

    base_url = "https://apigw.trendyol.com" if config.get("mode") == "live" else "https://stageapigw.trendyol.com"
    synced = 0
    total_fetched = 0
    page = 0
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{base_url}/integration/qna/sellers/{supplier_id}/questions/filter"
            
            while True:
                params = {"size": 50, "page": page} # Removed status="WAITING_FOR_ANSWER" to pull all
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                questions = data.get("content", [])
                
                if not questions:
                    break

                for q in questions:
                    q_id = str(q.get("id"))
                    existing = await db.trendyol_questions.find_one({"question_id": q_id})
                    c_date = q.get("creationDate")
                    created_date_iso = ""
                    if c_date:
                        try:
                            created_date_iso = datetime.fromtimestamp(c_date / 1000, tz=timezone.utc).isoformat()
                        except:
                            created_date_iso = str(c_date)
                            
                    doc = {
                        "question_id": q_id,
                        "product_id": str(q.get("productId", "")),
                        "product_name": q.get("productName", ""),
                        "question_text": q.get("text", ""),
                        "customer_name": q.get("userName", "") if q.get("showUserName") else "Gizli Kullanıcı",
                        "status": q.get("status", "WAITING_FOR_ANSWER"),
                        "created_date": created_date_iso,
                        "answer": q.get("answers", [{}])[0].get("text", "") if q.get("answers") else "",
                        "image_url": q.get("imageUrl", ""),
                        "synced_at": datetime.now(timezone.utc).isoformat(),
                    }
                    if existing:
                        await db.trendyol_questions.update_one({"question_id": q_id}, {"$set": doc})
                    else:
                        doc["id"] = generate_id()
                        doc["created_at"] = datetime.now(timezone.utc).isoformat()
                        await db.trendyol_questions.insert_one(doc)
                        synced += 1
                
                total_fetched += len(questions)
                total_pages = data.get("totalPages", 1)
                page += 1
                
                if page >= total_pages or page > 50: # Limit to ~2500 questions per sync to avoid rate limits
                    break

        return {"success": True, "synced": synced, "total_fetched": total_fetched}
    except httpx.HTTPStatusError as e:
        logger.error(f"Q&A sync error: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logger.error(f"Q&A sync error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trendyol/questions")
async def get_trendyol_questions(
    status: Optional[str] = None,
    page: int = 0,
    size: int = 20,
    current_user: dict = Depends(require_admin)
):
    """Get questions from local DB"""
    query = {}
    if status:
        query["status"] = status

    skip = page * size
    questions = await db.trendyol_questions.find(query).sort("created_at", -1).skip(skip).limit(size).to_list(size)
    total = await db.trendyol_questions.count_documents(query)

    for q in questions:
        q.pop("_id", None)

    return {"questions": questions, "total": total, "page": page, "size": size}


@router.post("/trendyol/questions/{question_id}/answer")
async def answer_trendyol_question(question_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    """Send an answer to a Trendyol customer question"""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")

    answer_text = payload.get("answer", "").strip()
    if not answer_text:
        raise HTTPException(status_code=400, detail="Yanit metni bos olamaz")

    supplier_id = config["supplier_id"]
    headers = await get_trendyol_headers()
    base_url = "https://apigw.trendyol.com" if config.get("mode") == "live" else "https://stageapigw.trendyol.com"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{base_url}/integration/qna/sellers/{supplier_id}/questions/{question_id}/answers"
            body = {"text": answer_text}
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()

        await db.trendyol_questions.update_one(
            {"question_id": question_id},
            {"$set": {"answer": answer_text, "status": "ANSWERED", "answered_at": datetime.now(timezone.utc).isoformat()}}
        )

        await log_integration_event("trendyol", "answer_question", current_user["email"], question_id, "success", "Soru yanitlandi")
        return {"success": True, "message": "Soru basariyla yanitlandi"}
    except httpx.HTTPStatusError as e:
        logger.error(f"Q&A answer error: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logger.error(f"Q&A answer error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== TRENDYOL INVOICE ====================

@router.post("/trendyol/invoices/{order_number}")
async def upload_invoice_to_trendyol(order_number: str, payload: dict, current_user: dict = Depends(require_admin)):
    """Upload invoice link to Trendyol for a given order number"""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapilandirilmamis")

    invoice_link = payload.get("invoice_link", "").strip()
    invoice_number = payload.get("invoice_number", "").strip()
    if not invoice_link:
        raise HTTPException(status_code=400, detail="Fatura linki bos olamaz")

    order = await db.orders.find_one({"order_number": order_number, "platform": "trendyol"})
    if not order:
        raise HTTPException(status_code=404, detail="Siparis bulunamadi")

    package_id = order.get("trendyol_package_id")
    if not package_id:
        raise HTTPException(status_code=400, detail="Trendyol paket ID bulunamadi")

    supplier_id = config["supplier_id"]
    headers = await get_trendyol_headers()
    base_url = config["base_url"]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{base_url}/sapigw/suppliers/{supplier_id}/shipment-packages/{package_id}/invoices"
            body = {
                "invoiceNumber": invoice_number or f"FAT-{order_number}",
                "invoiceLink": invoice_link
            }
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()

        await db.orders.update_one(
            {"order_number": order_number},
            {"$set": {"invoice_link": invoice_link, "invoice_number": invoice_number, "invoice_uploaded_at": datetime.now(timezone.utc).isoformat()}}
        )

        await log_integration_event("trendyol", "upload_invoice", current_user["email"], order_number, "success", "Fatura yuklendi", body)
        return {"success": True, "message": "Fatura Trendyol'a basariyla yuklendi"}
    except httpx.HTTPStatusError as e:
        logger.error(f"Invoice upload error: {e.response.text}")
        await log_integration_event("trendyol", "upload_invoice", current_user["email"], order_number, "error", e.response.text)
        raise HTTPException(status_code=e.response.status_code, detail=f"Fatura yukleme hatasi: {e.response.text}")
    except Exception as e:
        logger.error(f"Invoice upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trendyol/products/{product_id}/sync")
async def sync_product_to_trendyol(product_id: str, current_user: dict = Depends(require_admin)):
    """Full product synchronization to Trendyol"""
    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")

    from datetime import datetime, timezone
    started_at = datetime.now(timezone.utc).isoformat()
    product = None
    
    try:
        product = await db.products.find_one({"id": product_id}, {"_id": 0})
        if not product:
            raise Exception("Ürün bulunamadı")

        ty_cat_id = product.get("trendyol_category_id")
        if not ty_cat_id:
            # Try finding in the category mapped to this product
            cat = await db.categories.find_one({"name": product.get("category_name")})
            if not cat:
                cat = await db.categories.find_one({"id": product.get("category_id")})
            
            if cat and cat.get("trendyol_category_id"):
                ty_cat_id = cat.get("trendyol_category_id")
            else:
                raise Exception("Ürün için Trendyol kategorisi seçilmemiş")

        # Fetch mapping details from category
        mapping_cat = await db.categories.find_one({"trendyol_category_id": ty_cat_id})
        attr_mappings = mapping_cat.get("attribute_mappings", []) if mapping_cat else []
        val_mappings = mapping_cat.get("value_mappings", {}) if mapping_cat else {}
        default_mappings = mapping_cat.get("default_mappings", {}) if mapping_cat else {}

        from trendyol_client import TrendyolClient
        client = TrendyolClient(
            supplier_id=config["supplier_id"],
            api_key=config["api_key"],
            api_secret=config["api_secret"],
            mode=config["mode"]
        )

        # Calculate prices
        base_price = product.get("price", 0)
        list_price = calculate_trendyol_price(base_price, product, config)
        sale_price = calculate_trendyol_price(product.get("sale_price") or base_price, product, config)

        # Build items
        items = []
        variants = product.get("variants", [])
        
        # Common attributes for all variants
        common_attrs = []
        for am in attr_mappings:
            ty_attr_id = int(am["trendyol_attr_id"])
            local_name = am["local_attr"]
            # Find value in product attributes
            val = next((a["value"] for a in product.get("attributes", []) if a["type"] == local_name), None)
            # Try default if not found
            if not val:
                val = default_mappings.get(str(ty_attr_id))
                
            if val:
                mapping_key = f"{ty_attr_id}:{val}"
                ty_val_id = val_mappings.get(mapping_key)
                if ty_val_id:
                    common_attrs.append({"attributeId": ty_attr_id, "attributeValueId": int(ty_val_id)})
                else:
                    common_attrs.append({"attributeId": ty_attr_id, "customAttributeValue": val})

        if variants:
            for v in variants:
                v_attrs = common_attrs.copy()
                
                # Map Size (Beden) and Color (Renk)
                for am in attr_mappings:
                    ty_attr_id = str(am["trendyol_attr_id"])
                    local_name = am["local_attr"]
                    
                    # Check if it's Beden or Renk
                    if local_name.lower() == "beden":
                        sz = v.get("size")
                        if sz:
                            m_key = f"{ty_attr_id}:{sz}"
                            v_id = val_mappings.get(m_key)
                            if v_id: v_attrs.append({"attributeId": int(ty_attr_id), "attributeValueId": int(v_id)})
                            else: v_attrs.append({"attributeId": int(ty_attr_id), "customAttributeValue": sz})
                    
                    elif local_name.lower() == "renk":
                        clr = v.get("color")
                        if clr:
                            m_key = f"{ty_attr_id}:{clr}"
                            v_id = val_mappings.get(m_key)
                            if v_id: v_attrs.append({"attributeId": int(ty_attr_id), "attributeValueId": int(v_id)})
                            else: v_attrs.append({"attributeId": int(ty_attr_id), "customAttributeValue": clr})

                # Pricing with price_diff
                diff = float(v.get("price_diff", 0) or 0)
                v_list = round(list_price + diff, 2)
                v_sale = round(sale_price + diff, 2)

                item = {
                    "barcode": v.get("barcode") or product.get("barcode"),
                    "title": product.get("name"),
                    "productMainId": product.get("stock_code"),
                    "brandId": product.get("trendyol_brand_id") or 968,
                    "categoryId": int(ty_cat_id),
                    "quantity": v.get("stock", 0),
                    "stockCode": v.get("stock_code") or product.get("stock_code"),
                    "dimensionalWeight": product.get("cargo_weight") or 1,
                    "description": product.get("description", ""),
                    "currencyType": "TRY",
                    "listPrice": v_list,
                    "salePrice": v_sale,
                    "vatRate": product.get("vat_rate", 20),
                    "cargoCompanyId": 10,
                    "images": [{"url": img} for img in product.get("images", [])],
                    "attributes": v_attrs
                }
                items.append(item)
        else:
            # Single product
            item = {
                "barcode": product.get("barcode"),
                "title": product.get("name"),
                "productMainId": product.get("stock_code"),
                "brandId": product.get("trendyol_brand_id") or 968,
                "categoryId": int(ty_cat_id),
                "quantity": product.get("stock", 0),
                "stockCode": product.get("stock_code"),
                "dimensionalWeight": product.get("cargo_weight") or 1,
                "description": product.get("description", ""),
                "currencyType": "TRY",
                "listPrice": list_price,
                "salePrice": sale_price,
                "vatRate": product.get("vat_rate", 20),
                "cargoCompanyId": 10,
                "images": [{"url": img} for img in product.get("images", [])],
                "attributes": common_attrs
            }
            items.append(item)

        result = await client.create_products(items)
        batch_id = result.get("batchRequestId", "")
        
        # Log to the new sync logs screen
        log_doc = {
            "id": generate_id(),
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "success",
            "products_attempted": 1,
            "products_sent": len(items),
            "batch_request_id": batch_id,
            "errors": [],
            "message": f"'{product.get('name')}' ürünü tekli olarak aktarıldı."
        }
        await db.trendyol_sync_logs.insert_one(log_doc)

        await log_integration_event(
            platform="trendyol",
            action="product_sync",
            entity_type="product",
            entity_id=product_id,
            status="success",
            message=f"Sync initiated. Batch ID: {batch_id}",
            details={"batch_id": batch_id, "items_count": len(items)}
        )
        
        await db.products.update_one(
            {"id": product_id},
            {"$set": {
                "trendyol_sync_batch": str(batch_id),
                "trendyol_sync_last": datetime.now(timezone.utc).isoformat(),
                "trendyol_status": "synced"
            }}
        )
        
        return {"success": True, "message": "Eşleştirme başlatıldı", "batch_id": batch_id}
    except Exception as e:
        logger.error(f"Trendyol sync error: {str(e)}")
        log_doc = {
            "id": generate_id(),
            "started_at": started_at if 'started_at' in locals() else datetime.now(timezone.utc).isoformat(),
            "status": "error",
            "products_attempted": 1,
            "products_sent": 0,
            "batch_request_id": None,
            "errors": [f"Hata: {str(e)}"],
            "message": f"'{product.get('name') if product else product_id}' aktarımı sırasında hata oluştu."
        }
        await db.trendyol_sync_logs.insert_one(log_doc)
        await log_integration_event("trendyol", "product_sync", "product", product_id, "error", str(e))
        raise HTTPException(status_code=400 if "Ürün" in str(e) or "kategori" in str(e).lower() else 500, detail=f"Trendyol senkronizasyon hatası: {str(e)}")



# ==================== DOĞAN E-DÖNÜŞÜM ENTEGRASYONU ====================

@router.get("/dogan/settings")
async def get_dogan_settings(current_user: dict = Depends(require_admin)):
    """Get Doğan e-Dönüşüm settings"""
    settings = await db.settings.find_one({"id": "dogan_edonusum"}, {"_id": 0})
    if not settings:
        return {"id": "dogan_edonusum", "enabled": False, "username": "", "password": "", "is_test": True}
    # Mask password
    if settings.get("password"):
        settings["password_masked"] = settings["password"][:3] + "***"
    return settings


@router.post("/dogan/settings")
async def save_dogan_settings(payload: dict, current_user: dict = Depends(require_admin)):
    """Save Doğan e-Dönüşüm settings"""
    payload["id"] = "dogan_edonusum"
    await db.settings.update_one({"id": "dogan_edonusum"}, {"$set": payload}, upsert=True)
    return {"success": True, "message": "Doğan e-Dönüşüm ayarları kaydedildi"}


@router.post("/dogan/test-connection")
async def test_dogan_connection(current_user: dict = Depends(require_admin)):
    """Test connection to Doğan e-Dönüşüm"""
    settings = await db.settings.find_one({"id": "dogan_edonusum"}, {"_id": 0})
    if not settings or not settings.get("username"):
        raise HTTPException(status_code=400, detail="Doğan e-Dönüşüm ayarları eksik")

    from dogan_client import DoganClient
    client = DoganClient(
        username=settings["username"],
        password=settings["password"],
        is_test=settings.get("is_test", True)
    )
    result = client.test_connection()
    return result


@router.post("/dogan/check-user")
async def check_dogan_user(payload: dict, current_user: dict = Depends(require_admin)):
    """Check if a VKN is registered for e-Fatura"""
    vkn = payload.get("vkn", "")
    if not vkn:
        raise HTTPException(status_code=400, detail="VKN gerekli")

    settings = await db.settings.find_one({"id": "dogan_edonusum"}, {"_id": 0})
    if not settings or not settings.get("username"):
        raise HTTPException(status_code=400, detail="Doğan e-Dönüşüm ayarları eksik")

    from dogan_client import DoganClient
    client = DoganClient(
        username=settings["username"],
        password=settings["password"],
        is_test=settings.get("is_test", True)
    )
    result = client.check_user(vkn)
    return result
