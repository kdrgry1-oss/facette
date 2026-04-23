"""
Product routes - CRUD, search, filtering
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from datetime import datetime, timezone
import re

from .deps import db, logger, get_current_user, require_admin, generate_id, generate_short_id, generate_barcode_from_range
from fastapi import Response, UploadFile, File
import pandas as pd
import io

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
    limit: int = Query(20, ge=1, le=500),
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
        # Türkçe karakter dönüşümü (giyim -> GİYİM, aksesuar -> AKSESUAR)
        tr_upper_map = {'i': 'İ', 'ı': 'I', 'g': 'G', 'ğ': 'Ğ', 'u': 'U', 'ü': 'Ü', 's': 'S', 'ş': 'Ş', 'o': 'O', 'ö': 'Ö', 'c': 'C', 'ç': 'Ç'}
        category_upper = category.upper()
        for lower, upper in tr_upper_map.items():
            category_upper = category_upper.replace(lower.upper(), upper)
        
        # Slug formatını normal metne çevir (en-yeniler -> en yeniler)
        category_spaced = category.replace('-', ' ')
        category_spaced_upper = category_spaced.upper()
        for lower, upper in tr_upper_map.items():
            category_spaced_upper = category_spaced_upper.replace(lower.upper(), upper)
        
        query["$or"] = [
            {"category_name": {"$regex": category, "$options": "i"}},
            {"category_name": {"$regex": category_spaced, "$options": "i"}},
            {"category_name": {"$regex": category_spaced_upper, "$options": "i"}},
            {"category_slug": category},
            {"breadcrumb": {"$regex": category, "$options": "i"}},
            {"breadcrumb": {"$regex": category_upper, "$options": "i"}},
            {"breadcrumb": {"$regex": category_spaced, "$options": "i"}},
            {"breadcrumb": {"$regex": category_spaced_upper, "$options": "i"}}
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
        "id": await generate_short_id("products"),
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
        "supplier": product_data.get("supplier", ""),
        "manufacturer": product_data.get("manufacturer", "FACETTE"),
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
        "hepsiburada_attributes": product_data.get("hepsiburada_attributes", {}),
        "temu_attributes": product_data.get("temu_attributes", {}),
        "hepsiburada_category_id": product_data.get("hepsiburada_category_id", ""),
        "hepsiburada_category_name": product_data.get("hepsiburada_category_name", ""),
        "temu_category_id": product_data.get("temu_category_id", ""),
        "temu_category_name": product_data.get("temu_category_name", ""),
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

@router.get("/export/excel")
async def export_products_excel(current_user: dict = Depends(require_admin)):
    """Export all products to an Excel file (variants as rows with dynamic attributes)"""
    try:
        products = await db.products.find({}, {"_id": 0}).to_list(None)
        
        # Collect all unique attribute names
        all_attr_names = set()
        for p in products:
            for attr in p.get("attributes", []):
                attr_name = attr.get("name") or attr.get("type")
                if attr_name:
                    all_attr_names.add(attr_name)
        
        rows = []
        for p in products:
            variants = p.get("variants", [])
            if not variants:
                variants = [{
                    "barcode": p.get("barcode", ""),
                    "stock_code": p.get("stock_code", ""),
                    "price": p.get("price", 0),
                    "sale_price": p.get("sale_price"),
                    "stock": p.get("stock", 0),
                    "size": "",
                    "color": ""
                }]
            
            for v in variants:
                row = {
                    "ID": p.get("id"),
                    "Ürün Adı": p.get("name"),
                    "Kategori": p.get("category_name"),
                    "Marka": p.get("brand"),
                    "Stok Kodu": v.get("stock_code") or p.get("stock_code"),
                    "Barkod": v.get("barcode") or p.get("barcode"),
                    "Beden": v.get("size", ""),
                    "Renk": v.get("color", ""),
                    "Piyasa Fiyatı": v.get("price") or p.get("price", 0),
                    "Satış Fiyatı": v.get("sale_price") or p.get("sale_price") or p.get("price", 0),
                    "Stok": v.get("stock", 0),
                    "Açıklama": p.get("description", ""),
                    "Aktif": "Evet" if p.get("is_active") else "Hayır"
                }
                
                # pre-fill attributes with empty string
                for attr_name in all_attr_names:
                    row[f"Özellik: {attr_name}"] = ""
                    
                # apply product attributes
                for attr in p.get("attributes", []):
                    attr_name = attr.get("name") or attr.get("type")
                    if attr_name and attr.get("value"):
                        row[f"Özellik: {attr_name}"] = attr["value"]
                        
                rows.append(row)
        
        df = pd.DataFrame(rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Ürünler')
        
        headers = {
            'Content-Disposition': 'attachment; filename="urunler.xlsx"',
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }
        return Response(content=output.getvalue(), headers=headers)
        
    except Exception as e:
        logger.error(f"Excel export error: {e}")
        raise HTTPException(status_code=500, detail=f"Dışa aktarma hatası: {str(e)}")

@router.post("/import/excel")
async def import_products_excel(file: UploadFile = File(...), current_user: dict = Depends(require_admin)):
    """Import or update products from an Excel file"""
    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
        
        # Validation
        required = ["Ürün Adı", "Kategori", "Satış Fiyatı"]
        for col in required:
            if col not in df.columns:
                raise Exception(f"Eksik sütun: {col}")
        
        stats = {"created": 0, "updated": 0, "errors": 0}
        
        for _, row in df.iterrows():
            try:
                barcode = str(row.get("Barkod", "")).strip()
                if not barcode or barcode == "nan":
                    continue
                
                # Parse dynamic attributes from columns
                parsed_attrs = []
                import uuid
                for col in df.columns:
                    if str(col).startswith("Özellik: "):
                        attr_name = str(col).replace("Özellik: ", "").strip()
                        val = str(row.get(col, "")).strip()
                        
                        # Ensure attribute exists in global library
                        existing_global = await db.attributes.find_one({"name": attr_name})
                        if not existing_global:
                            await db.attributes.insert_one({
                                "id": f"attr_{uuid.uuid4().hex[:8]}",
                                "name": attr_name,
                                "values": []
                            })
                            
                        if val and val != "nan":
                            parsed_attrs.append({"type": attr_name, "name": attr_name, "value": val})
                
                # Try finding product by variant barcode
                existing = await db.products.find_one({"variants.barcode": barcode})
                
                if existing:
                    # Update variant in existing product
                    update_fields = {
                        "variants.$.stock": int(row.get("Stok", 0) if pd.notna(row.get("Stok")) else 0),
                        "variants.$.price": float(row.get("Piyasa Fiyatı", row.get("Satış Fiyatı", 0)) if pd.notna(row.get("Piyasa Fiyatı", row.get("Satış Fiyatı", 0))) else 0),
                        "variants.$.sale_price": float(row.get("Satış Fiyatı", 0) if pd.notna(row.get("Satış Fiyatı")) else 0),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    if parsed_attrs:
                        update_fields["attributes"] = parsed_attrs

                    await db.products.update_one(
                        {"id": existing["id"], "variants.barcode": barcode},
                        {"$set": update_fields}
                    )
                    stats["updated"] += 1
                else:
                    # Create new product or add as variant to existing product with same name
                    name = str(row.get("Ürün Adı"))
                    prod_by_name = await db.products.find_one({"name": name})
                    
                    variant = {
                        "barcode": barcode,
                        "stock_code": str(row.get("Stok Kodu", "")).replace("nan", ""),
                        "size": str(row.get("Beden", "")).replace("nan", ""),
                        "color": str(row.get("Renk", "")).replace("nan", ""),
                        "price": float(row.get("Piyasa Fiyatı", row.get("Satış Fiyatı", 0)) if pd.notna(row.get("Piyasa Fiyatı", row.get("Satış Fiyatı", 0))) else 0),
                        "sale_price": float(row.get("Satış Fiyatı", 0) if pd.notna(row.get("Satış Fiyatı")) else 0),
                        "stock": int(row.get("Stok", 0) if pd.notna(row.get("Stok")) else 0)
                    }
                    
                    if prod_by_name:
                        # Add as new variant
                        update_fields = {
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }
                        if parsed_attrs:
                            update_fields["attributes"] = parsed_attrs
                        
                        await db.products.update_one(
                            {"id": prod_by_name["id"]},
                            {"$push": {"variants": variant}, "$set": update_fields}
                        )
                        stats["updated"] += 1
                    else:
                        # Create full new product
                        new_id = await generate_short_id("products")
                        new_p = {
                            "id": new_id,
                            "name": name,
                            "slug": generate_slug(name),
                            "category_name": str(row.get("Kategori", "")).replace("nan", ""),
                            "brand": str(row.get("Marka", "")).replace("nan", ""),
                            "description": str(row.get("Açıklama", "")).replace("nan", ""),
                            "price": variant["price"],
                            "sale_price": variant["sale_price"],
                            "stock": variant["stock"],
                            "is_active": True,
                            "variants": [variant],
                            "images": [],
                            "attributes": parsed_attrs,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }
                        await db.products.insert_one(new_p)
                        stats["created"] += 1
            except Exception as row_err:
                logger.error(f"Import row error: {row_err}")
                stats["errors"] += 1
                
        return {"success": True, "stats": stats}
        
    except Exception as e:
        logger.error(f"Excel import error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/attributes/import-technical-xlsx")
async def import_technical_details_xlsx(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_admin)
):
    """
    Import technical details from Excel in format:
    UrunKartID | StokKodu | UrunAdi | Ozellik | Deger
    Groups by UrunAdi, fuzzy matches with existing products, returns preview.
    """
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl yüklenmemiş")

    content = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(content))
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="Dosya boş veya başlık satırı eksik")

    headers = [str(h).strip() if h else "" for h in rows[0]]

    # Find column indices
    name_col = None
    ozellik_col = None
    deger_col = None
    stok_kodu_col = None

    for i, h in enumerate(headers):
        hl = h.lower().replace("ı", "i").replace("ö", "o").replace("ü", "u")
        if "urunadi" in hl.replace(" ", "") or "ürün adı" in h.lower() or "urun adi" in h.lower():
            name_col = i
        elif "ozellik" in hl.replace(" ", "") or "özellik" in h.lower():
            ozellik_col = i
        elif "deger" in hl.replace(" ", "") or "değer" in h.lower():
            deger_col = i
        elif "stokkodu" in hl.replace(" ", "") or "stok kodu" in h.lower():
            stok_kodu_col = i

    if name_col is None:
        raise HTTPException(status_code=400, detail="UrunAdi sütunu bulunamadı")
    if deger_col is None:
        raise HTTPException(status_code=400, detail="Deger sütunu bulunamadı")

    # Group by product name - deduplicate attributes (last value wins for same type)
    product_groups = {}
    # Metadata column headers that should not be treated as attributes
    meta_headers_lower = {h.lower().strip() for h in headers if h}

    for row in rows[1:]:
        name = str(row[name_col]).strip() if row[name_col] else None
        if not name or name.lower() in ("none", "null", ""):
            continue

        ozellik = str(row[ozellik_col]).strip() if ozellik_col is not None and row[ozellik_col] else ""
        deger = str(row[deger_col]).strip() if row[deger_col] else ""
        stok_kodu = str(row[stok_kodu_col]).strip() if stok_kodu_col is not None and row[stok_kodu_col] else ""

        if not deger or deger.lower() in ("none", "null"):
            continue

        if name not in product_groups:
            product_groups[name] = {"stok_kodu": stok_kodu, "attributes": {}, "extra_colors": []}

        if ozellik and ozellik.lower() not in ("none", "null", "") and ozellik.lower() not in meta_headers_lower:
            # Use dict to deduplicate (last value wins)
            product_groups[name]["attributes"][ozellik] = deger
        elif not ozellik or ozellik.lower() in ("none", "null", ""):
            # Empty ozellik with a deger = extra color variant
            product_groups[name]["extra_colors"].append(deger)

    # Convert attribute dicts to list format
    for name, data in product_groups.items():
        data["attributes_list"] = [{"type": k, "value": v} for k, v in data["attributes"].items()]

    # Now match products by name - one Excel product can match MULTIPLE DB products
    all_products = await db.products.find({}, {"_id": 0, "id": 1, "name": 1, "stock_code": 1}).to_list(None)

    def normalize(s):
        return s.lower().replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c").replace("İ", "i").strip()

    results = []
    used_product_ids = set()

    for excel_name, data in product_groups.items():
        excel_norm = normalize(excel_name)

        # Find ALL matching products (for color variants)
        matches = []
        for p in all_products:
            p_norm = normalize(p["name"])
            if p_norm == excel_norm:
                matches.append((p, 100))
            elif excel_norm in p_norm:
                # Excel name is a substring of DB name (e.g., "Basic Triko" in "Basic Triko Siyah")
                overlap = len(excel_norm.split()) / len(p_norm.split()) * 100
                if overlap >= 50:
                    matches.append((p, round(overlap, 1)))
            elif p_norm in excel_norm:
                overlap = len(p_norm.split()) / len(excel_norm.split()) * 100
                if overlap >= 50:
                    matches.append((p, round(overlap, 1)))

        if matches:
            matches.sort(key=lambda x: x[1], reverse=True)
            for match_p, match_score in matches:
                if match_p["id"] not in used_product_ids:
                    results.append({
                        "excel_name": excel_name,
                        "stok_kodu": data["stok_kodu"],
                        "attributes": data["attributes_list"],
                        "extra_colors": data["extra_colors"],
                        "matched_product_id": match_p["id"],
                        "matched_product_name": match_p["name"],
                        "match_score": match_score
                    })
                    used_product_ids.add(match_p["id"])
        else:
            results.append({
                "excel_name": excel_name,
                "stok_kodu": data["stok_kodu"],
                "attributes": data["attributes_list"],
                "extra_colors": data["extra_colors"],
                "matched_product_id": None,
                "matched_product_name": None,
                "match_score": 0
            })

    results.sort(key=lambda r: r["match_score"], reverse=True)

    return {
        "success": True,
        "total_excel_products": len(results),
        "matched": sum(1 for r in results if r["matched_product_id"]),
        "unmatched": sum(1 for r in results if not r["matched_product_id"]),
        "results": results
    }


@router.post("/attributes/apply-technical-xlsx")
async def apply_technical_details(payload: dict, current_user: dict = Depends(require_admin)):
    """
    Apply matched technical details to products.
    Payload: { updates: [{product_id, attributes: [{type, value}], extra_colors: []}] }
    """
    updates = payload.get("updates", [])
    if not updates:
        raise HTTPException(status_code=400, detail="Güncellenecek ürün yok")

    updated = 0
    attr_lib_updates = {}

    for update in updates:
        product_id = update.get("product_id")
        attributes = update.get("attributes", [])
        if not product_id or not attributes:
            continue

        # Replace attributes with Excel data (clean import)
        new_attrs = [{"type": a["type"], "name": a["type"], "value": a["value"]} for a in attributes]

        # Track for attribute library
        for new_attr in attributes:
            if new_attr["type"] not in attr_lib_updates:
                attr_lib_updates[new_attr["type"]] = set()
            attr_lib_updates[new_attr["type"]].add(new_attr["value"])

        await db.products.update_one(
            {"id": product_id},
            {"$set": {
                "attributes": new_attrs,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        updated += 1

    # Update global attribute library with new values
    for attr_name, val_set in attr_lib_updates.items():
        existing_lib = await db.attributes.find_one({"name": {"$regex": f"^{re.escape(attr_name)}$", "$options": "i"}})
        if existing_lib:
            current_vals = set(existing_lib.get("values", []))
            merged_vals = list(current_vals.union(val_set))
            if len(merged_vals) > len(current_vals):
                await db.attributes.update_one(
                    {"_id": existing_lib["_id"]},
                    {"$set": {"values": merged_vals, "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
        else:
            await db.attributes.insert_one({
                "id": generate_id(),
                "name": attr_name,
                "values": list(val_set),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            })

    return {"success": True, "updated": updated, "message": f"{updated} ürünün özellikleri güncellendi"}
