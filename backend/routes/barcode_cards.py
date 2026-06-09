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


def _card_html_for_variant(product: dict, variant: dict) -> str:
    """Tek varyant icin tek barkod ETIKETI (5cm x 4cm, FIYATSIZ)."""
    name = (product.get("name", "") or "").strip()
    brand = (product.get("brand") or "FACETTE").strip()
    stock_code = variant.get("stock_code") or product.get("stock_code") or ""
    bar_code = variant.get("barcode") or product.get("barcode") or stock_code
    size = (variant.get("size") or "").strip()
    color = (variant.get("color") or "").strip()

    barcode_img = _barcode_png_base64(bar_code) if bar_code else ""

    return f"""
    <div class="card">
      <div class="brand">{brand}</div>
      <div class="name">{name}</div>
      <div class="meta">{f'<span class="size">{size}</span>' if size else ''}{f'<span class="color">{color}</span>' if color else ''}</div>
      {f'<img class="barcode-img" src="{barcode_img}" alt="barcode"/>' if barcode_img else ''}
      <div class="barcode-text">{bar_code or ''}</div>
      <div class="stock">{f'Stok: {stock_code}' if stock_code else ''}</div>
    </div>
    """


def _build_html(cards_html: str, title: str = "Barkod Kartlari") -> str:
    """
    Etiket sayfasi: yan yana 2 barkod. Her etiket 5cm x 4cm.
    Kesme payi (bos seritler): en sol + orta + en sag = 0.5cm.
    Satir genisligi = 2*5 + 3*0.5 = 11.5cm. Kac varyant varsa alt alta dizilir.
    Olculeri degistirmek icin asagidaki cm degerlerini guncellemek yeterli.
    """
    LABEL_W = "5cm"      # her barkodun yatay olcusu
    LABEL_H = "4cm"      # her barkodun dikey olcusu
    CUT     = "0.5cm"    # kesme payi (sol/orta/sag)
    SHEET_W = "11.5cm"   # 2*5cm + 3*0.5cm

    css = """
  @page { size: auto; margin: 0; }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: #fff; color: #111;
    font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
  .no-print {
    display: flex; justify-content: space-between; align-items: center;
    margin: 8px; padding: 8px 12px; background: #fff7ed; border: 1px solid #fed7aa;
    border-radius: 8px; font-size: 13px;
  }
  .btn { padding: 6px 14px; border-radius: 6px; border: 1px solid #111;
    background: #111; color: #fff; cursor: pointer; font-size: 13px; font-weight: 600; }

  .sheet { width: __SHEET_W__; margin: 0 auto; padding: __CUT__ __CUT__ 0 __CUT__; }
  .grid {
    display: grid;
    grid-template-columns: __LABEL_W__ __LABEL_W__;
    column-gap: __CUT__;
    row-gap: 0;
  }
  .card {
    width: __LABEL_W__; height: __LABEL_H__;
    overflow: hidden; padding: 0.12cm 0.14cm;
    display: flex; flex-direction: column; align-items: center; justify-content: flex-start;
    text-align: center; gap: 1px; page-break-inside: avoid;
  }
  .brand { font-size: 7px; letter-spacing: 0.16em; text-transform: uppercase;
    color: #6b7280; font-weight: 700; width: 100%; }
  .name { font-size: 8.5px; font-weight: 700; line-height: 1.1; width: 100%;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .meta { font-size: 8px; line-height: 1.1; }
  .meta .size { font-weight: 800; color: #111; }
  .meta .color { color: #374151; margin-left: 5px; }
  .barcode-img { width: 100%; height: 1.45cm; object-fit: contain; margin-top: 1px; }
  .barcode-text { font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 9px; letter-spacing: 0.12em; }
  .stock { font-size: 7px; color: #6b7280; }

  @media print {
    .no-print { display: none; }
    .sheet { margin: 0; }
  }
"""
    css = (css.replace("__SHEET_W__", SHEET_W).replace("__LABEL_W__", LABEL_W)
              .replace("__LABEL_H__", LABEL_H).replace("__CUT__", CUT))

    return (
        "<!DOCTYPE html><html lang='tr'><head><meta charset='utf-8'/>"
        "<title>" + title + "</title><style>" + css + "</style></head><body>"
        "<div class='no-print'><span><strong>" + title + "</strong> "
        "&middot; Yazdirmak icin Ctrl/Cmd+P veya butonu kullanin. "
        "Yazdirma penceresinde olcek %100 / 'Gercek boyut' secili olmali.</span>"
        "<button class='btn' onclick='window.print()'>Yazdir</button></div>"
        "<div class='sheet'><div class='grid'>" + cards_html + "</div></div>"
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
