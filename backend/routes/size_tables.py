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
    product_size: str = "",
    model_info: dict = None,
) -> bytes:
    """Render a 1200x1800 JPEG size-table with a mannequin silhouette (suudcollection-tarzı)."""
    W, H = 1200, 1800
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    font_title = _find_font(64)
    font_subtitle = _find_font(32)
    font_th = _find_font(30)
    font_td = _find_font(28)
    font_brand = _find_font(80)
    font_sm = _find_font(26)

    # Header band
    draw.rectangle([(0, 0), (W, 160)], fill=(17, 24, 39))  # near-black
    draw.text((60, 40), "ÖLÇÜ TABLOSU", fill="white", font=font_title)
    draw.text((60, 115), product_name[:70], fill=(203, 213, 225), font=font_subtitle)

    # Meta line + Ürün Bedeni / Manken ("suud" örneği)
    _meta = f"Tüm ölçüler {unit} cinsindendir."
    if product_size:
        _meta += f"   ·   Ürün Bedeni: {product_size}"
    draw.text((60, 190), _meta, fill=(107, 114, 128), font=font_subtitle)
    if model_info:
        _mparts = [f"{k} {v} cm" for k, v in model_info.items() if str(v).strip()]
        if _mparts:
            draw.text((60, 238), "Manken: " + ", ".join(_mparts), fill=(107, 114, 128), font=font_sm)

    # --- MANKEN SİLUETİ (sol panel) + ölçü çizgileri ---
    # Ölçü sütun adlarına göre hangi çizgilerin gösterileceğini belirle.
    _col_lower = [str(c).lower() for c in columns]
    def _has(*keys):
        return any(any(k in c for k in keys) for c in _col_lower)
    cx = 290  # siluet merkez x
    # (yarı_genişlik, y) profili — düz omuz üstü / göğüs / bel / kalça / etek
    profile = [(150, 342), (150, 385), (138, 560), (146, 615), (92, 800), (148, 1010), (128, 1245), (120, 1320)]
    right_pts = [(cx + hw, y) for hw, y in profile]
    left_pts = [(cx - hw, y) for hw, y in reversed(profile)]
    draw.polygon(right_pts + left_pts, fill=(236, 238, 242), outline=(190, 196, 206))
    # Ölçü seviyeleri: (etiket, y, aktif mi) — etiketler tabloya değmeden SAĞA hizalanır.
    levels = [
        ("Omuz", 385, _has("omuz", "shoulder")),
        ("Göğüs", 585, _has("göğüs", "gogus", "bust", "chest")),
        ("Bel", 800, _has("bel", "waist")),
        ("Kalça", 1010, _has("kalça", "kalca", "hip", "basen")),
    ]
    for label, y, active in levels:
        if not active:
            continue
        hw = 150
        # kısa kesikli yatay ölçü çizgisi (formun içinden geçer)
        for xseg in range(cx - hw, cx + hw, 24):
            draw.line([(xseg, y), (min(xseg + 14, cx + hw), y)], fill=(154, 52, 18), width=3)
        txt = label.upper()
        tw = draw.textlength(txt, font=font_sm)
        lx = 540 - tw  # etiket sağ kenarı tablodan (560) önce biter
        draw.text((lx, y - 18), txt, fill=(60, 60, 68), font=font_sm)
        # siluet kenarından etikete uzanan gösterge çizgisi + nokta
        draw.line([(cx + hw, y), (lx - 14, y)], fill=(154, 52, 18), width=3)
        draw.ellipse([(cx + hw - 4, y - 4), (cx + hw + 4, y + 4)], fill=(154, 52, 18))
    # Boy oku (sol kenar)
    draw.line([(120, 320), (120, 1290)], fill=(150, 156, 166), width=3)
    draw.polygon([(112, 330), (128, 330), (120, 312)], fill=(150, 156, 166))
    draw.polygon([(112, 1280), (128, 1280), (120, 1298)], fill=(150, 156, 166))
    draw.text((70, 780), "BOY", fill=(120, 126, 136), font=font_sm)

    # Table geometry — sağ panele kaydırıldı (siluete yer aç)
    table_top = 300
    table_left = 560
    table_right = W - 60
    table_width = table_right - table_left
    # First column narrower (beden etiketi)
    col_size_w = 120
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
    img.save(out, format="JPEG", quality=90, optimize=True)  # 1200x1800 JPEG
    return out.getvalue()


async def _inherited_size_table(product_id: str):
    """Kendi ölçü tablosu olmayan ürün için, AYNI stok kodlu başka bir üründe
    kayıtlı (dolu) ölçü tablosunu döndürür. Stok kodu boşsa / kardeş yoksa None.
    En son güncellenen kardeş tabloyu seçer."""
    prod = await db.products.find_one({"id": product_id}, {"_id": 0, "id": 1, "stock_code": 1})
    if not prod:
        return None
    sc = (prod.get("stock_code") or "").strip()
    if not sc:
        return None
    sibling_ids = []
    async for p in db.products.find({"stock_code": sc, "id": {"$ne": product_id}}, {"_id": 0, "id": 1}):
        if p.get("id"):
            sibling_ids.append(p["id"])
    if not sibling_ids:
        return None
    return await db.size_tables.find_one(
        {"product_id": {"$in": sibling_ids}, "sizes": {"$exists": True, "$ne": []}},
        {"_id": 0},
        sort=[("updated_at", -1)],
    )


@router.get("/{product_id}")
async def get_size_table(product_id: str, current_user: dict = Depends(require_admin)):
    st = await db.size_tables.find_one({"product_id": product_id}, {"_id": 0})
    if not st:
        # Kalıtım: aynı stok kodlu başka üründe tablo varsa otomatik getir (oto-doldurma).
        # exists=True döner ki editör doldursun; admin "Kaydet" deyince bu ürüne kalıcı yazılır.
        inh = await _inherited_size_table(product_id)
        if inh and inh.get("sizes"):
            return {
                "product_id": product_id,
                "sizes": inh.get("sizes") or [],
                "columns": inh.get("columns") or [],
                "values": inh.get("values") or {},
                "exists": True,
                "inherited": True,
                "inherited_from": inh.get("product_id"),
            }
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
        # "suud" örneği: Ürün Bedeni + Manken ölçüleri (Boy/Göğüs/Bel/Basen ...)
        "product_size": str(payload.get("product_size") or "").strip(),
        "model_info": payload.get("model_info") if isinstance(payload.get("model_info"), dict) else {},
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
        st = await _inherited_size_table(product_id)  # aynı stok kodundan kalıtım
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
        product_size=st.get("product_size") or "",
        model_info=st.get("model_info") or {},
    )
    data_url = "data:image/jpeg;base64," + base64.b64encode(png).decode("ascii")

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
    return {"success": True, "data_url": data_url, "image_bytes": len(png)}


# ---------------------------------------------------------------------------
# TEK SEFERLİK ONARIM: ölçü tablosu görsellerinin kaybolan is_size_table işareti.
# Bir görsel taşıma/dönüştürme işlemi {url, is_size_table:true} dict'lerini düz URL
# string'ine çevirmiş → tablo görselleri müşteri galerisine sızdı ve "Beden Tablosu"
# butonu kayboldu. Tespit (gerçek veriyle doğrulandı): tablo görselleri 1200×1800 ve
# DÖRT kenar şeridi SAF BEYAZ (mean=255) — ürün fotoğrafları (stüdyo fonu) asla değil.
# Yalnız /uploads/ string URL'leri taranır; kapak (index 0) asla işaretlenmez.
# ---------------------------------------------------------------------------

def _is_chart_image_sync(url: str) -> bool:
    import requests as _req
    from PIL import ImageStat
    r = _req.get(url, timeout=25)
    r.raise_for_status()
    im = Image.open(BytesIO(r.content))
    if im.size != (1200, 1800):
        return False
    g = im.convert("L")
    w, h = g.size
    b = 25
    for box in [(0, 0, w, b), (0, h - b, w, h), (0, 0, b, h), (w - b, 0, w, h)]:
        if ImageStat.Stat(g.crop(box)).mean[0] < 254.0:
            return False
    return True


async def repair_size_table_markers():
    """Startup'ta bir kez çalışır (settings bayrağıyla korunur)."""
    import asyncio
    flag = await db.settings.find_one({"id": "size_table_marker_repair"}, {"_id": 0})
    if flag and flag.get("done"):
        return
    scanned = marked = prods = 0
    cursor = db.products.find(
        {"images": {"$elemMatch": {"$regex": "/uploads/"}}},
        {"_id": 0, "id": 1, "images": 1},
    )
    async for p in cursor:
        imgs = p.get("images") or []
        new_imgs, changed = [], False
        for i, im in enumerate(imgs):
            if i > 0 and isinstance(im, str) and "/uploads/" in im:
                scanned += 1
                try:
                    is_chart = await asyncio.to_thread(_is_chart_image_sync, im)
                except Exception:
                    is_chart = False
                if is_chart:
                    new_imgs.append({
                        "id": str(uuid.uuid4()), "url": im, "is_size_table": True,
                        "alt": "Ölçü Tablosu",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                    changed = True
                    marked += 1
                    continue
            new_imgs.append(im)
        if changed:
            await db.products.update_one({"id": p["id"]}, {"$set": {"images": new_imgs}})
            prods += 1
    await db.settings.update_one(
        {"id": "size_table_marker_repair"},
        {"$set": {"done": True, "scanned": scanned, "marked": marked, "products": prods,
                  "at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    logger.info(f"[size-table repair] tarandı={scanned} işaretlendi={marked} ürün={prods}")


# Public endpoint for storefront – no auth
public_router = APIRouter(prefix="/size-tables-public", tags=["size-tables-public"])


@public_router.get("/{product_id}")
async def get_public_size_table(product_id: str):
    """Storefront reads the HTML-renderable data (NOT the image)."""
    st = await db.size_tables.find_one({"product_id": product_id}, {"_id": 0})
    if not st or not st.get("sizes"):
        st = await _inherited_size_table(product_id)  # aynı stok kodundan kalıtım
    if not st or not st.get("sizes"):
        return {"exists": False}
    return {
        "exists": True,
        "sizes": st.get("sizes") or [],
        "columns": st.get("columns") or [],
        "values": st.get("values") or {},
        "product_size": st.get("product_size") or "",
        "model_info": st.get("model_info") or {},
    }
