"""Amazon entegrasyonu icin yan etkisiz donusum ve hata siniflandirma yardimcilari."""
from __future__ import annotations

import re
from typing import Any

_COLOR_KEYS = {"color", "colour", "renk", "web color", "web renk"}
_SECRET_RE = re.compile(
    r"(?i)(authorization|bearer|access[_-]?token|refresh[_-]?token|client[_-]?secret)"
    r"\s*[:=]?\s*[^\s,;]+"
)


def _color_from_attributes(attributes: Any) -> str:
    if isinstance(attributes, dict):
        for key, raw in attributes.items():
            if isinstance(raw, dict):
                label = raw.get("label") or raw.get("name") or key
                value = raw.get("value") or raw.get("attribute_value")
            else:
                label, value = key, raw
            if str(label or "").strip().lower() in _COLOR_KEYS and value not in (None, ""):
                return str(value).strip()
    elif isinstance(attributes, list):
        for raw in attributes:
            if not isinstance(raw, dict):
                continue
            label = raw.get("label") or raw.get("name") or raw.get("type") or raw.get("attribute_name")
            value = raw.get("value") or raw.get("attribute_value")
            if str(label or "").strip().lower() in _COLOR_KEYS and value not in (None, ""):
                return str(value).strip()
    return ""


def canonical_amazon_color(product: dict, variant: dict | None = None, fallback: str = "") -> str:
    """Rengi varyant -> urun -> attributes -> kanonik ad-cozucu sirasiyla bulur."""
    product, variant = product or {}, variant or {}
    return (
        str(variant.get("color") or "").strip()
        or str(product.get("color") or "").strip()
        or _color_from_attributes(variant.get("attributes"))
        or _color_from_attributes(product.get("attributes"))
        or str(fallback or "").strip()
    )


def amazon_image_candidates(product: dict, variant: dict | None = None) -> list[str]:
    """Renk/varyant gorsellerini ana gorsel yapip urun gorselleriyle tamamlar."""
    urls: list[str] = []

    def add(raw: Any) -> None:
        if isinstance(raw, str):
            url = raw
        elif isinstance(raw, dict):
            url = raw.get("url") or raw.get("src") or raw.get("image")
        else:
            return
        url = str(url or "").strip()
        if url.startswith(("http://", "https://")) and url not in urls:
            urls.append(url)

    variant = variant or {}
    for key in ("image", "main_image"):
        add(variant.get(key))
    for image in (variant.get("images") or []):
        add(image)
    for key in ("image", "main_image"):
        add((product or {}).get(key))
    for image in ((product or {}).get("images") or []):
        add(image)
    return urls[:9]


def build_amazon_seller_sku(variant: dict, product: dict, color: str = "") -> str:
    """Stok kodu + kanonik renk + beden ile renkler arasinda benzersiz SellerSKU kurar."""
    variant, product = variant or {}, product or {}
    stock_code = str(variant.get("stock_code") or product.get("stock_code") or "").strip()
    size = str(variant.get("size") or "").strip()
    color_slug = re.sub(r"[^A-Za-z0-9ğüşöçıİĞÜŞÖÇ]+", "", str(color or ""))[:20]
    parts = [part for part in (stock_code, color_slug, size) if part]
    return "-".join(parts) or str(variant.get("barcode") or "").strip()


def amazon_sibling_query(codes: list[str]) -> dict:
    """_resolve_stock_code'un tum kaynaklariyla ayni kapsama sahip Mongo kardes sorgusu."""
    text_codes = list(dict.fromkeys(str(code).strip() for code in codes if str(code).strip()))
    numeric_codes = [int(code) for code in text_codes if code.isdigit()]
    card_codes: list[Any] = text_codes + [code for code in numeric_codes if code not in text_codes]
    return {"$or": [
        {"stock_code": {"$in": text_codes}},
        {"sku": {"$in": text_codes}},
        {"variants.stock_code": {"$in": text_codes}},
        {"variants.sku": {"$in": text_codes}},
        {"urun_karti_id": {"$in": card_codes}},
        {"csv_card_id": {"$in": card_codes}},
    ]}


def safe_amazon_failure(res: dict | None = None, error: Exception | str | None = None) -> dict:
    """Amazon hatasindan yalniz kod/mesaj/http alir; token benzeri degerleri maskeler."""
    res = res or {}
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    candidates = data.get("issues") or data.get("errors") or res.get("issues") or []
    first = candidates[0] if isinstance(candidates, list) and candidates else {}
    if not isinstance(first, dict):
        first = {}
    code = first.get("code") or res.get("reject_status") or data.get("status") or "AMAZON_SYNC_ERROR"
    message = first.get("message") or res.get("error") or (str(error) if error else "Amazon stok guncellemesi reddedildi")
    message = _SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", str(message))[:300]
    return {"code": str(code)[:80], "message": message, "http": res.get("status")}


def amazon_retry_policy(failure_count: int) -> tuple[int, bool]:
    """Ilk 7 hatada katlanan backoff; 8. ve sonrasinda 24 saatlik karantina."""
    count = max(1, int(failure_count or 1))
    if count >= 8:
        return 24 * 60 * 60, True
    return min(6 * 60 * 60, 60 * (2 ** (count - 1))), False
