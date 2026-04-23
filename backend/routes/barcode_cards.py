"""
=============================================================================
barcode_cards.py — Ürün ve Sipariş barkod/etiket yazdırma endpoint'leri
=============================================================================

AMAÇ:
  Giyim mağazalarındaki gibi barkodlu ürün kartı ve (ileride) sipariş etiketi
  yazdırma. Her kart üzerinde:
    - Ürün adı + marka
    - Stok kodu (iç tanımlama)
    - GTIN/EAN-13 barkod (makine okuyabilir Code128 / EAN-13 fallback)
    - Beden / renk (varyant)
    - Fiyat (indirimli varsa üstü çizili + indirimli)
    - Kategori
  
  Çıktı HTML olarak döner; frontend yeni pencere açıp window.print() tetikler.
  Tarayıcının "PDF olarak kaydet" seçeneği ile PDF yapılabilir — zebra
  yazıcılara ayrıca PDF sürücüsü üzerinden gönderilebilir.

ENDPOINT'LER:
  - GET  /api/products/{product_id}/barcode-card
         Tek ürün, TÜM varyantları için ayrı kart (2 kart/satır A4).
  - POST /api/products/barcode-cards/bulk  body: {"ids": [id, id, ...]}
         Çoklu ürün, her ürünün tüm varyantları.

KULLANAN FRONTEND:
  /app/frontend/src/pages/admin/Products.jsx
    - handlePrintBarcode  → tek ürün
    - handleBulkPrintBarcodes → seçili ürünler
=============================================================================
"""
from fastapi import APIRouter, HTTPException, Response, Depends, Query
from typing import List
import base64
import io

from .deps import db, get_current_user, require_admin

# python-barcode zaten requirements.txt'te (0.16.1)
import barcode
from barcode.writer import ImageWriter

router = APIRouter(prefix="/products", tags=["Barcode Cards"])


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _barcode_png_base64(code: str) -> str:
    """
    Verilen kod için PNG barkod üretir ve base64 string döner (data: URI için).
    EAN-13 (13 hane rakam) denenir; uygun değilse Code128 fallback.
    """
    if not code:
        return ""
    try:
        buf = io.BytesIO()
        clean = "".join(ch for ch in str(code) if ch.isdigit() or ch.isalnum())
        if len(clean) == 13 and clean.isdigit():
            # EAN-13
            ean = barcode.get("ean13", clean[:12], writer=ImageWriter())
            ean.write(buf, options={"write_text": False, "module_height": 10.0})
        else:
            # Code128 (alfanumerik uyumlu)
            c128 = barcode.get("code128", clean or str(code), writer=ImageWriter())
            c128.write(buf, options={"write_text": False, "module_height": 10.0})
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


def _price_block(product: dict) -> str:
    """Fiyat HTML bloğu; indirimli fiyat varsa üstü çizili + indirimli gösterir."""
    price = product.get("price") or 0
    sale = product.get("sale_price")
    if sale and sale > 0 and sale < price:
        return (
            f'<div class="price-row">'
            f'<span class="price-old">{price:.2f} ₺</span>'
            f'<span class="price-new">{sale:.2f} ₺</span>'
            f'</div>'
        )
    return f'<div class="price-row"><span class="price-new">{price:.2f} ₺</span></div>'


def _card_html_for_variant(product: dict, variant: dict) -> str:
    """Tek bir varyant için tek kart HTML parçası."""
    name = product.get("name", "")
    brand = product.get("brand") or "FACETTE"
    category = product.get("category_name") or ""
    stock_code = variant.get("stock_code") or product.get("stock_code") or ""
    bar_code = variant.get("barcode") or product.get("barcode") or stock_code
    size = variant.get("size") or ""
    color = variant.get("color") or ""

    barcode_img = _barcode_png_base64(bar_code) if bar_code else ""

    return f"""
    <div class="card">
      <div class="brand">{brand}</div>
      <div class="name">{name}</div>
      <div class="meta">
        {f'<span class="tag">{category}</span>' if category else ''}
        {f'<span class="tag size-tag">{size}</span>' if size else ''}
        {f'<span class="tag">{color}</span>' if color else ''}
      </div>
      {_price_block(product)}
      <div class="codes">
        <div class="code-row"><span class="label">Stok Kodu:</span> <span class="mono">{stock_code or '-'}</span></div>
        <div class="code-row"><span class="label">GTIN:</span> <span class="mono">{bar_code or '-'}</span></div>
      </div>
      {f'<img class="barcode-img" src="{barcode_img}" alt="barcode"/>' if barcode_img else ''}
      <div class="barcode-text mono">{bar_code or ''}</div>
    </div>
    """


def _build_html(cards_html: str, title: str = "Barkod Kartları") -> str:
    """Tüm kartları tek HTML sayfasına yerleştirir. A4 2 sütunlu print grid."""
    return f"""
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8"/>
<title>{title}</title>
<style>
  @page {{ size: A4; margin: 10mm; }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    margin: 0; padding: 10px; color: #111; background: #fff;
  }}
  .grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }}
  .card {{
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px 14px;
    page-break-inside: avoid;
    background: #fff;
    display: flex; flex-direction: column; gap: 4px;
    min-height: 200px;
  }}
  .brand {{
    font-size: 10px; letter-spacing: 0.25em; text-transform: uppercase;
    color: #6b7280; font-weight: 700;
  }}
  .name {{
    font-size: 14px; font-weight: 700; line-height: 1.2;
    max-height: 2.8em; overflow: hidden;
  }}
  .meta {{ display: flex; gap: 6px; flex-wrap: wrap; margin: 4px 0; }}
  .tag {{
    font-size: 10px; padding: 2px 8px; border-radius: 999px;
    background: #f3f4f6; color: #374151; border: 1px solid #e5e7eb;
  }}
  .size-tag {{ background: #111; color: #fff; border-color: #111; font-weight: 700; }}
  .price-row {{ display: flex; align-items: baseline; gap: 8px; margin: 2px 0; }}
  .price-old {{ font-size: 11px; color: #9ca3af; text-decoration: line-through; }}
  .price-new {{ font-size: 18px; font-weight: 800; color: #000; }}
  .codes {{ margin-top: 4px; font-size: 11px; color: #4b5563; }}
  .code-row {{ display: flex; gap: 6px; }}
  .label {{ color: #9ca3af; font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; }}
  .mono {{ font-family: "SF Mono", Menlo, Consolas, monospace; }}
  .barcode-img {{
    width: 100%; height: 48px; margin-top: 6px; object-fit: contain;
  }}
  .barcode-text {{
    text-align: center; font-size: 11px; letter-spacing: 0.1em; color: #111;
    margin-top: 2px;
  }}
  @media print {{
    body {{ padding: 0; }}
    .no-print {{ display: none; }}
  }}
  .no-print {{
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 10px; padding: 8px 12px; background: #fff7ed; border: 1px solid #fed7aa;
    border-radius: 8px; font-size: 13px;
  }}
  .btn {{
    padding: 6px 14px; border-radius: 6px; border: 1px solid #111; background: #111;
    color: #fff; cursor: pointer; font-size: 13px; font-weight: 600;
  }}
</style>
</head>
<body>
  <div class="no-print">
    <span><strong>{title}</strong> · Yazdırmak için Ctrl/Cmd+P veya sağdaki butonu kullanın.</span>
    <button class="btn" onclick="window.print()">Yazdır</button>
  </div>
  <div class="grid">
    {cards_html}
  </div>
</body>
</html>
"""


def _product_cards_html(product: dict) -> str:
    """
    Bir ürünün tüm varyantları için kart HTML üretir. Varyant yoksa ürün
    seviyesinde tek kart üretilir (stock_code + barcode).
    """
    variants = product.get("variants") or []
    if not variants:
        # Varyant yoksa ürün seviyesinde tek kart (ana barkod)
        fake = {
            "stock_code": product.get("stock_code"),
            "barcode": product.get("barcode"),
            "size": "",
            "color": "",
        }
        return _card_html_for_variant(product, fake)
    return "".join(_card_html_for_variant(product, v) for v in variants)


# ---------------------------------------------------------------------------
# ENDPOINT: Tek ürün kartı
# ---------------------------------------------------------------------------
@router.get("/{product_id}/barcode-card")
async def get_product_barcode_card(
    product_id: str,
    token: str = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """
    Tek ürün için yazdırılabilir barkod kartı sayfası döner.
    Ürünün her varyantı için ayrı kart.
    Query `token` parametresi frontend'de window.open içinde kimlik
    doğrulama için kullanılabilsin diye gevşek tutuldu — asıl kontrol
    `get_current_user` dependency'sinde.
    """
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    cards = _product_cards_html(product)
    html = _build_html(cards, title=f"{product.get('name', 'Ürün')} — Barkod Kartı")
    return Response(content=html, media_type="text/html; charset=utf-8")


# ---------------------------------------------------------------------------
# ENDPOINT: Toplu ürün kartları
# ---------------------------------------------------------------------------
@router.post("/barcode-cards/bulk")
async def get_bulk_barcode_cards(
    payload: dict,
    current_user: dict = Depends(require_admin),
):
    """
    {"ids": [...]} → Gönderilen ürün id'lerinin hepsi için tek yazdırılabilir
    HTML dokümanı. Seçilen her ürünün tüm varyantları için ayrı kart basar.
    """
    ids = payload.get("ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="Ürün seçilmedi")

    cursor = db.products.find({"id": {"$in": ids}}, {"_id": 0})
    products = await cursor.to_list(length=len(ids))

    if not products:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    cards = "".join(_product_cards_html(p) for p in products)
    html = _build_html(cards, title=f"{len(products)} Ürün — Barkod Kartları")
    return Response(content=html, media_type="text/html; charset=utf-8")
