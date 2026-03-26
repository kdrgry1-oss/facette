"""
Product routes - CRUD, search, filtering
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from datetime import datetime, timezone
import re

from .deps import db, logger, get_current_user, require_admin, generate_id, generate_barcode_from_range

router = APIRouter(prefix="/products", tags=["Products"])

def generate_slug(name: str) -> str:
    """Generate URL-friendly slug from name"""
    slug = name.lower()
    # Turkish character replacements
    tr_map = {'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c', 'İ': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c'}
    for tr, en in tr_map.items():
        slug = slug.replace(tr, en)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug

@router.get("")
async def get_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = Query("created_at"),
    order: str = Query("desc"),
    is_featured: Optional[bool] = None,
    is_new: Optional[bool] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    status: Optional[str] = None,
    brand: Optional[str] = None,
    min_stock: Optional[int] = None,
    max_stock: Optional[int] = None,
    is_showcase: Optional[bool] = None,
    is_opportunity: Optional[bool] = None,
    is_free_shipping: Optional[bool] = None,
    stock_code: Optional[str] = None,
    barcode: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
):
    """Get products with filtering and pagination"""
    skip = (page - 1) * limit
    query = {}
    
    # Status default to active for storefront compatibility unless specified differently
    if status == "all":
        pass
    elif status == "passive":
        query["is_active"] = False
    else:
        query["is_active"] = True

    if brand:
        query["brand"] = {"$regex": brand, "$options": "i"}

    if min_stock is not None:
        query["stock"] = {"$gte": min_stock}

    if max_stock is not None:
        if "stock" in query:
            query["stock"]["$lte"] = max_stock
        else:
            query["stock"] = {"$lte": max_stock}
            
    if is_showcase is not None:
        query["is_showcase"] = is_showcase
        
    if is_opportunity is not None:
        query["is_opportunity"] = is_opportunity
        
    if is_free_shipping is not None:
        query["is_free_shipping"] = is_free_shipping

    if stock_code:
        query["stock_code"] = {"$regex": stock_code, "$options": "i"}

    if barcode:
        query["variants.barcode"] = {"$regex": barcode, "$options": "i"}
    
    if date_from or date_to:
        date_q = {}
        try:
            from datetime import datetime, timezone
            if date_from:
                date_q["$gte"] = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
            if date_to:
                # end of day
                date_q["$lte"] = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc).isoformat()
            query["created_at"] = date_q
        except Exception:
            pass
    
    if category:
        query["$or"] = [
            {"category_name": {"$regex": category, "$options": "i"}},
            {"category_slug": category}
        ]
    
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"keywords": {"$regex": search, "$options": "i"}},
            {"stock_code": {"$regex": search, "$options": "i"}}
        ]
    
    if is_featured is not None:
        query["is_featured"] = is_featured
    
    if is_new is not None:
        query["is_new"] = is_new
    
    if min_price is not None:
        query["price"] = {"$gte": min_price}
    
    if max_price is not None:
        if "price" in query:
            query["price"]["$lte"] = max_price
        else:
            query["price"] = {"$lte": max_price}
    
    sort_order = -1 if order == "desc" else 1
    
    products = await db.products.find(query, {"_id": 0}).sort(sort, sort_order).skip(skip).limit(limit).to_list(limit)
    total = await db.products.count_documents(query)
    
    return {
        "products": products,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

@router.get("/{product_id}")
async def get_product(product_id: str):
    """Get single product by ID or slug"""
    product = await db.products.find_one(
        {"$or": [{"id": product_id}, {"slug": product_id}]},
        {"_id": 0}
    )
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return product

@router.post("")
async def create_product(
    product_data: dict,
    current_user: dict = Depends(require_admin)
):
    """Create new product (admin only)"""
    variants = product_data.get("variants", [])
    
    # Fetch settings for default VAT
    settings = await db.settings.find_one({"id": "main"})
    default_vat = settings.get("default_vat_rate", 20) if settings else 20

    # Auto-generate barcodes efficiently
    used_barcodes_set = None # Will be initialized on first call
    
    # Auto-generate barcodes for variants if missing
    for v in variants:
        if not v.get("barcode"):
            barcode = await generate_barcode_from_range(used_barcodes_set)
            if barcode:
                v["barcode"] = barcode
    
    # Also generate for main product if no variants and barcode is empty
    if not variants and not product_data.get("barcode"):
        barcode = await generate_barcode_from_range(used_barcodes_set)
        if barcode:
            product_data["barcode"] = barcode

    product = {
        "id": generate_id(),
        "name": product_data.get("name", ""),
        "slug": product_data.get("slug") or generate_slug(product_data.get("name", "")),
        "description": product_data.get("description", ""),
        "short_description": product_data.get("short_description", ""),
        "price": float(product_data.get("price", 0)),
        "sale_price": product_data.get("sale_price"),
        "category_name": product_data.get("category_name", ""),
        "brand": product_data.get("brand", "FACETTE"),
        "images": product_data.get("images", []),
        "variants": product_data.get("variants", []),
        "attributes": product_data.get("attributes", []),
        "stock": int(product_data.get("stock", 0)),
        "stock_code": product_data.get("stock_code", ""),
        "barcode": product_data.get("barcode", ""),
        "sku": product_data.get("sku", ""),
        "is_active": product_data.get("is_active", True),
        "is_featured": product_data.get("is_featured", False),
        "is_new": product_data.get("is_new", False),
        "is_showcase": product_data.get("is_showcase", False),
        "is_opportunity": product_data.get("is_opportunity", False),
        "is_free_shipping": product_data.get("is_free_shipping", False),
        "vat_rate": product_data.get("vat_rate", default_vat),
        "use_default_markup": product_data.get("use_default_markup", True),
        "markup_rate": float(product_data.get("markup_rate", 0)),
        "trendyol_attributes": product_data.get("trendyol_attributes", {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.products.insert_one(product)
    logger.info(f"Product created: {product['id']}")
    
    return {"id": product["id"], "message": "Ürün oluşturuldu"}

@router.put("/{product_id}")
async def update_product(
    product_id: str,
    product_data: dict,
    current_user: dict = Depends(require_admin)
):
    """Update product (admin only)"""
    existing = await db.products.find_one({"id": product_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    
    # Update slug if name changed
    if product_data.get("name") and product_data.get("name") != existing.get("name"):
        product_data["slug"] = generate_slug(product_data["name"])
    
    
    # Auto-generate barcodes for variants if missing
    variants = product_data.get("variants", [])
    used_barcodes_set = None
    for v in variants:
        if not v.get("barcode") or v.get("barcode") == "":
            barcode = await generate_barcode_from_range(used_barcodes_set)
            if barcode:
                v["barcode"] = barcode
    
    product_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.products.update_one({"id": product_id}, {"$set": product_data})
    
    return {"message": "Ürün güncellendi"}

@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    current_user: dict = Depends(require_admin)
):
    """Delete product (admin only)"""
    result = await db.products.delete_one({"id": product_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    
    return {"message": "Ürün silindi"}

@router.post("/{product_id}/toggle-active")
async def toggle_product_active(
    product_id: str,
    current_user: dict = Depends(require_admin)
):
    """Toggle product active status"""
    product = await db.products.find_one({"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    
    new_status = not product.get("is_active", True)
    await db.products.update_one(
        {"id": product_id},
        {"$set": {"is_active": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"is_active": new_status}

@router.get("/search/popular")
async def get_popular_searches():
    """Get popular search terms"""
    # In production, track and return actual popular searches
    return [
        {"term": "elbise", "count": 150},
        {"term": "bluz", "count": 120},
        {"term": "pantolon", "count": 100},
        {"term": "jean", "count": 90},
        {"term": "kazak", "count": 80},
    ]


# ==================== PRODUCT ATTRIBUTE IMPORT ====================
import io
from fastapi import UploadFile, File

@router.post("/attributes/import-xlsx")
async def import_attributes_from_xlsx(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_admin)
):
    """
    Parse an XLSX file and extract product attributes per stock_code.
    Columns: one column for stock_code, rest are attribute types with values in cells.
    Returns: list of {stock_code, attributes: [{type, value}], matched_product_id}
    """
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl yuklenmemis. pip install openpyxl")

    content = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(content))
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=400, detail="Bos dosya")

    headers = [str(h).strip() if h else "" for h in rows[0]]

    # Find stock code column - look for "stok kodu", "stock_code", "barkod", "kod" etc.
    stock_col_idx = None
    stock_col_keywords = ["stok kodu", "stock code", "stock_code", "barkod", "barcode", "kod", "urun kodu", "urun_kodu"]
    for i, h in enumerate(headers):
        if any(kw in h.lower().replace(" ", " ") for kw in stock_col_keywords):
            stock_col_idx = i
            break
    if stock_col_idx is None:
        stock_col_idx = 0  # Default to first column

    # Attribute columns = all other columns
    attr_headers = [(i, h) for i, h in enumerate(headers) if i != stock_col_idx and h]

    results = []
    stock_codes = []

    for row in rows[1:]:
        stock_code = str(row[stock_col_idx]).strip() if row[stock_col_idx] else None
        if not stock_code or stock_code.lower() in ("none", "null", ""):
            continue

        attributes = []
        for col_idx, attr_type in attr_headers:
            value = row[col_idx] if col_idx < len(row) else None
            if value is not None and str(value).strip() not in ("", "None", "null"):
                attributes.append({
                    "type": attr_type,
                    "value": str(value).strip()
                })

        if attributes:
            results.append({
                "stock_code": stock_code,
                "attributes": attributes,
                "matched_product_id": None,
                "matched_product_name": None
            })
            stock_codes.append(stock_code)

    # Match with products by stock_code
    if stock_codes:
        products = await db.products.find(
            {"stock_code": {"$in": stock_codes}},
            {"_id": 0, "id": 1, "name": 1, "stock_code": 1}
        ).to_list(1000)
        product_map = {p["stock_code"]: p for p in products}

        for r in results:
            p = product_map.get(r["stock_code"])
            if p:
                r["matched_product_id"] = p["id"]
                r["matched_product_name"] = p["name"]

    return {
        "total_rows": len(results),
        "matched": sum(1 for r in results if r["matched_product_id"]),
        "unmatched": sum(1 for r in results if not r["matched_product_id"]),
        "attribute_types": [h for _, h in attr_headers],
        "results": results
    }


@router.post("/attributes/save-bulk")
async def save_attributes_bulk(payload: dict, current_user: dict = Depends(require_admin)):
    """
    Save attributes to multiple products.
    Payload: { updates: [{product_id, attributes: [{type, value, trendyol_attr_id, trendyol_attr_value_id}]}] }
    """
    updates = payload.get("updates", [])
    if not updates:
        raise HTTPException(status_code=400, detail="Guncellenecek urun yok")

    updated = 0
    for update in updates:
        product_id = update.get("product_id")
        attributes = update.get("attributes", [])
        if not product_id or not attributes:
            continue

        await db.products.update_one(
            {"id": product_id},
            {"$set": {
                "attributes": attributes,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        updated += 1

    return {"success": True, "updated": updated}


@router.get("/{product_id}/attributes")
async def get_product_attributes(product_id: str, current_user: dict = Depends(require_admin)):
    """Get attributes for a single product"""
    product = await db.products.find_one({"id": product_id}, {"_id": 0, "attributes": 1, "name": 1, "stock_code": 1})
    if not product:
        raise HTTPException(status_code=404, detail="Urun bulunamadi")
    return {"attributes": product.get("attributes", []), "name": product.get("name"), "stock_code": product.get("stock_code")}


@router.put("/{product_id}/attributes")
async def update_product_attributes(product_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    """Update attributes for a single product"""
    attributes = payload.get("attributes", [])
    await db.products.update_one(
        {"id": product_id},
        {"$set": {"attributes": attributes, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "message": "Ozellikler guncellendi"}

@router.post("/bulk-update-vat")
async def bulk_update_vat(
    payload: dict,
    current_user: dict = Depends(require_admin)
):
    """Bulk update VAT for all products"""
    vat_rate = payload.get("vat_rate")
    if vat_rate is None:
        raise HTTPException(status_code=400, detail="VAT rate is required")
    
    result = await db.products.update_many({}, {"$set": {"vat_rate": vat_rate}})
    return {"message": f"{result.modified_count} ürünün KDV oranı %{vat_rate} olarak güncellendi."}
