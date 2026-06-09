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
import re

from .deps import db, get_current_user, require_admin

# python-barcode zaten requirements.txt'te (0.16.1)
import barcode
from barcode.writer import ImageWriter, SVGWriter

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


def _barcode_svg_inline(code: str) -> str:
    """EAN-13/Code128 barkodu VEKTOR (SVG) uretir; kaliteli yazicida net cikar.
    SVG olculeri mm bazlidir -> %100 olcekte fiziksel olarak dogru basar."""
    if not code:
        return ""
    try:
        clean = "".join(ch for ch in str(code) if ch.isalnum())
        opts = {"write_text": False, "module_height": 13.0, "module_width": 0.43, "quiet_zone": 2.0}
        if len(clean) == 13 and clean.isdigit():
            bc = barcode.get("ean13", clean[:12], writer=SVGWriter())
        else:
            bc = barcode.get("code128", clean or str(code), writer=SVGWriter())
        buf = io.BytesIO()
        bc.write(buf, options=opts)
        svg = buf.getvalue().decode("utf-8")
        svg = re.sub(r"<\?xml[^>]*\?>", "", svg)
        svg = re.sub(r"<!DOCTYPE[^>]*>", "", svg, flags=re.S | re.I)
        svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
        svg = svg.replace("<svg ", '<svg class="barcode-svg" ', 1)
        return svg.strip()
    except Exception:
        return ""


def _card_html_for_variant(product: dict, variant: dict) -> str:
    """Tek varyant icin tek barkod ETIKETI (5cm x 4cm, FIYATSIZ)."""
    name = (product.get("name", "") or "").strip()
    brand = (product.get("brand") or "FACETTE").strip()
    stock_code = variant.get("stock_code") or product.get("stock_code") or ""
    bar_code = variant.get("barcode") or product.get("barcode") or stock_code
    size = (variant.get("size") or "").strip()
    color = (variant.get("color") or "").strip()

    barcode_svg = _barcode_svg_inline(bar_code)

    return f"""
    <div class="card">
      <div class="brand">{brand}</div>
      <div class="name">{name}</div>
      <div class="meta">{f'<span class="size">{size}</span>' if size else ''}{f'<span class="color">{color}</span>' if color else ''}</div>
      {barcode_svg}
      <div class="barcode-text">{bar_code or ''}</div>
      <div class="stock">{f'Stok: {stock_code}' if stock_code else ''}</div>
    </div>
    """


def _build_html(cards_html: str, title: str = "Barkod Kartlari") -> str:
    """
    Etiket sayfasi: yan yana 2 barkod, her etiket 5cm x 4cm.
    Kesme payi (bos seritler): sol + orta + sag = 0.5cm -> satir genisligi 11.5cm.
    Barkodlar VEKTOR (SVG) -> net baski. Toolbar'dan kopya adedi secilir.
    """
    LABEL_W = "5cm"
    LABEL_H = "4cm"
    CUT     = "0.5cm"
    SHEET_W = "11.5cm"

    css = """
  @page { size: auto; margin: 0; }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: #fff; color: #000;
    font-family: Arial, "Helvetica Neue", Helvetica, sans-serif;
    -webkit-font-smoothing: none; text-rendering: geometricPrecision; }
  .no-print {
    display: flex; justify-content: space-between; align-items: center; gap: 12px;
    margin: 8px; padding: 8px 12px; background: #fff7ed; border: 1px solid #fed7aa;
    border-radius: 8px; font-size: 13px; flex-wrap: wrap;
  }
  .no-print input { width: 64px; padding: 4px 6px; border: 1px solid #d1d5db; border-radius: 6px; }
  .btn { padding: 6px 16px; border-radius: 6px; border: 1px solid #111;
    background: #111; color: #fff; cursor: pointer; font-size: 13px; font-weight: 700; }

  .sheet { width: __SHEET_W__; margin: 0 auto; padding: __CUT__ __CUT__ 0 __CUT__; }
  .grid { display: grid; grid-template-columns: __LABEL_W__ __LABEL_W__; column-gap: __CUT__; row-gap: 0; }
  .card {
    width: __LABEL_W__; height: __LABEL_H__;
    overflow: hidden; padding: 0.1cm 0.12cm;
    display: flex; flex-direction: column; align-items: center; justify-content: space-between;
    text-align: center; page-break-inside: avoid;
  }
  .brand { font-size: 8px; letter-spacing: 0.14em; text-transform: uppercase; color:#000; font-weight: 700; width:100%; line-height:1; }
  .name { font-size: 11px; font-weight: 700; line-height: 1.05; width: 100%;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .meta { font-size: 10px; line-height: 1.05; font-weight: 600; }
  .meta .size { font-weight: 800; }
  .meta .color { margin-left: 6px; }
  .barcode-svg { display: block; max-width: 100%; height: auto; margin: 0 auto; }
  .barcode-text { font-family: "Courier New", monospace; font-weight: 700;
    font-size: 12px; letter-spacing: 0.14em; line-height: 1; }
  .stock { font-size: 8px; color:#000; line-height: 1; }
  @media print { .no-print { display: none; } .sheet { margin: 0; } }
"""
    css = (css.replace("__SHEET_W__", SHEET_W).replace("__LABEL_W__", LABEL_W)
              .replace("__LABEL_H__", LABEL_H).replace("__CUT__", CUT))

    script = (
        "<script>(function(){"
        "var grid=document.querySelector('.grid');"
        "var original=grid?grid.innerHTML:'';"
        "window.doPrint=function(){"
        "var n=parseInt((document.getElementById('copies')||{}).value,10)||1;if(n<1)n=1;"
        "var tmp=document.createElement('div');tmp.innerHTML=original;"
        "var cards=Array.prototype.slice.call(tmp.querySelectorAll('.card'));"
        "grid.innerHTML='';"
        "cards.forEach(function(c){for(var i=0;i<n;i++){grid.appendChild(c.cloneNode(true));}});"
        "window.print();"
        "};})();</script>"
    )

    return (
        "<!DOCTYPE html><html lang='tr'><head><meta charset='utf-8'/>"
        "<title>" + title + "</title><style>" + css + "</style></head><body>"
        "<div class='no-print'>"
        "<span><strong>" + title + "</strong> &middot; %100 olcek / 'Gercek boyut' ile yazdirin.</span>"
        "<span style='display:flex;align-items:center;gap:8px'>"
        "<label>Her barkoddan adet: <input id='copies' type='number' min='1' value='1'/></label>"
        "<button class='btn' onclick='doPrint()'>Yazdir</button>"
        "</span></div>"
        "<div class='sheet'><div class='grid'>" + cards_html + "</div></div>"
        + script +
        "</body></html>"
    )


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
