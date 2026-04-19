"""
Size Table (Ölçü Tablosu) module.

- Admin creates a size table per product: rows=sizes, cols=measurements (cm).
- System renders a 1200x1800 PNG (PIL) and attaches as the product's last image
  with `is_size_table: true`. Storefront hides these but shows the raw data as
  an HTML table under size selector.
"""
from fastapi import APIRouter, HTTPException, Depends
from io import BytesIO
from datetime import datetime, timezone
import base64
import uuid
import os

from PIL import Image, ImageDraw, ImageFont

from .deps import db, require_admin, logger

router = APIRouter(prefix="/size-tables", tags=["size-tables"])


def _find_font(size=28):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_size_table_image(
    product_name: str,
    sizes: list,          # e.g. ["S", "M", "L", "XL"]
    columns: list,        # e.g. ["Göğüs", "Bel", "Kalça", "Omuz"]
    values: dict,         # {"S": {"Göğüs": "96", "Bel": "80", ...}, ...}
    brand: str = "FACETTE",
    unit: str = "cm",
) -> bytes:
    """Render a 1200x1800 PNG size-table for storefront/integrator usage."""
    W, H = 1200, 1800
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    font_title = _find_font(64)
    font_subtitle = _find_font(32)
    font_th = _find_font(30)
    font_td = _find_font(28)
    font_brand = _find_font(80)

    # Header band
    draw.rectangle([(0, 0), (W, 160)], fill=(17, 24, 39))  # near-black
    draw.text((60, 40), "ÖLÇÜ TABLOSU", fill="white", font=font_title)
    draw.text((60, 115), product_name[:70], fill=(203, 213, 225), font=font_subtitle)

    # Meta line
    draw.text((60, 190), f"Tüm ölçüler {unit} cinsindendir.", fill=(107, 114, 128), font=font_subtitle)

    # Table geometry
    table_top = 260
    table_left = 60
    table_right = W - 60
    table_width = table_right - table_left
    # First column wider for size label
    col_size_w = 180
    rest_cols = max(1, len(columns))
    col_w = (table_width - col_size_w) / rest_cols
    row_h = 78
    header_h = 90

    # Header row
    draw.rectangle(
        [(table_left, table_top), (table_right, table_top + header_h)],
        fill=(241, 245, 249), outline=(203, 213, 225), width=2,
    )
    draw.text((table_left + 30, table_top + 28), "BEDEN", fill=(30, 41, 59), font=font_th)
    for i, col in enumerate(columns):
        x = table_left + col_size_w + i * col_w
        draw.line([(x, table_top), (x, table_top + header_h)], fill=(203, 213, 225), width=2)
        text = col[:14]
        draw.text((x + 20, table_top + 28), text.upper(), fill=(30, 41, 59), font=font_th)

    # Body rows
    for ri, size in enumerate(sizes):
        y = table_top + header_h + ri * row_h
        fill = (255, 255, 255) if ri % 2 == 0 else (249, 250, 251)
        draw.rectangle([(table_left, y), (table_right, y + row_h)], fill=fill, outline=(226, 232, 240), width=1)
        # Size label cell
        draw.rectangle([(table_left, y), (table_left + col_size_w, y + row_h)], fill=(255, 237, 213), outline=(226, 232, 240), width=1)
        draw.text((table_left + 40, y + 22), str(size), fill=(154, 52, 18), font=font_th)
        for i, col in enumerate(columns):
            x = table_left + col_size_w + i * col_w
            val = str(values.get(size, {}).get(col, "")).strip() or "-"
            draw.text((x + 30, y + 24), val, fill=(30, 41, 59), font=font_td)

    # Brand stamp bottom-right
    draw.text((W - 420, H - 180), brand, fill=(17, 24, 39), font=font_brand)
    draw.text((W - 420, H - 90), "facette.com", fill=(148, 163, 184), font=font_subtitle)

    # Footer note
    draw.text(
        (60, H - 110),
        "Değerler ± 1-2 cm tolerans taşıyabilir.",
        fill=(148, 163, 184),
        font=font_subtitle,
    )

    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


@router.get("/{product_id}")
async def get_size_table(product_id: str, current_user: dict = Depends(require_admin)):
    st = await db.size_tables.find_one({"product_id": product_id}, {"_id": 0})
    if not st:
        return {"product_id": product_id, "sizes": [], "columns": [], "values": {}, "exists": False}
    st["exists"] = True
    return st


@router.post("/{product_id}")
async def save_size_table(product_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    sizes = payload.get("sizes", [])
    columns = payload.get("columns", [])
    values = payload.get("values", {})
    if not isinstance(sizes, list) or not isinstance(columns, list):
        raise HTTPException(status_code=400, detail="sizes ve columns liste olmalı")

    doc = {
        "product_id": product_id,
        "sizes": sizes,
        "columns": columns,
        "values": values,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": current_user.get("email", ""),
    }
    await db.size_tables.update_one({"product_id": product_id}, {"$set": doc}, upsert=True)
    return {"success": True}


@router.post("/{product_id}/generate-image")
async def generate_size_table_image(product_id: str, current_user: dict = Depends(require_admin)):
    """Render a 1200x1800 PNG, store as base64 in the product's images array
    marked `is_size_table=true`, and return the data URL."""
    st = await db.size_tables.find_one({"product_id": product_id}, {"_id": 0})
    if not st:
        raise HTTPException(status_code=404, detail="Önce ölçü tablosunu kaydedin")
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    png = render_size_table_image(
        product_name=product.get("name", ""),
        sizes=st.get("sizes") or [],
        columns=st.get("columns") or [],
        values=st.get("values") or {},
    )
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    # Remove any previous size-table images and append fresh one as the last image
    imgs = list(product.get("images") or [])
    imgs = [i for i in imgs if not (isinstance(i, dict) and i.get("is_size_table"))]
    imgs.append({
        "id": str(uuid.uuid4()),
        "url": data_url,
        "is_size_table": True,
        "alt": "Ölçü Tablosu",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.products.update_one(
        {"id": product_id},
        {"$set": {"images": imgs, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    await db.size_tables.update_one(
        {"product_id": product_id},
        {"$set": {"last_rendered_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "data_url_length": len(data_url), "image_bytes": len(png)}


# Public endpoint for storefront – no auth
public_router = APIRouter(prefix="/size-tables-public", tags=["size-tables-public"])


@public_router.get("/{product_id}")
async def get_public_size_table(product_id: str):
    """Storefront reads the HTML-renderable data (NOT the image)."""
    st = await db.size_tables.find_one({"product_id": product_id}, {"_id": 0})
    if not st or not st.get("sizes"):
        return {"exists": False}
    return {
        "exists": True,
        "sizes": st.get("sizes") or [],
        "columns": st.get("columns") or [],
        "values": st.get("values") or {},
    }
