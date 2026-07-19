"""
company.py — BEYAZ ETİKET firma kimliği tek kaynağı.

Amaç: Yeni bir firmayı KODDAN DEĞİL ayardan geçir. Firma-özel her değer (mağaza adı,
logo, e-posta/telefon, adres, IBAN, vergi, site adresi, sosyal medya) burada
merkezîleşir. Öncelik zinciri:  settings.main.company_info (admin)  →  settings.main
üst-alanları / env  →  gömülü FACETTE varsayılanı.

Tüketiciler (email_layout, dogan e-fatura tedarikçi, GPSR üretici, site linkleri) bu
tek kaynaktan okur; ayar boş bırakılırsa mevcut FACETTE davranışı korunur (regresyon yok).
"""
import os
import time

# Gömülü FACETTE varsayılanları (ayar boşsa bunlar kullanılır).
_DEFAULTS = {
    "store_name": "FACETTE",
    "company_name": "FACETTE DIŞ TİCARET A.Ş.",
    "logo_url": "https://facette.com.tr/logo.png",
    "site_url": "https://facette.com.tr",
    "website": "facette.com.tr",
    "contact_email": "info@facette.com.tr",
    "email": "info@facette.com.tr",
    "contact_phone": "",
    "phone": "",
    "whatsapp": "",
    "address": "İkitelli O.S.B. İmsan San. Sit. D BLOK NO:3",
    "city": "",
    "tax_office": "",
    "tax_number": "",
    "iban": "",
    "instagram": "https://www.instagram.com/facette",
    "facebook": "",
    "x": "",
    "tiktok": "https://www.tiktok.com/@facette",
}

_cache = None
_cache_at = 0.0
_TTL = 60.0


def defaults() -> dict:
    return dict(_DEFAULTS)


async def get_company(db) -> dict:
    """Firma bilgisini birleştirilmiş döndürür (varsayılan → env/main → company_info).
    60 sn cache'lenir (her e-posta/istekte DB'ye gitmemek için)."""
    global _cache, _cache_at
    now = time.time()
    if _cache is not None and (now - _cache_at) < _TTL:
        return _cache
    try:
        s = await db.settings.find_one(
            {"id": "main"},
            {"_id": 0, "company_info": 1, "site_name": 1, "logo_url": 1,
             "contact_email": 1, "contact_phone": 1, "address": 1}) or {}
    except Exception:
        s = {}
    merged = dict(_DEFAULTS)
    # 1) env (deployment düzeyi) — SITE_URL
    _site_env = os.environ.get("SITE_URL")
    if _site_env:
        merged["site_url"] = _site_env.rstrip("/")
        merged["website"] = _site_env.replace("https://", "").replace("http://", "").rstrip("/")
    # 2) settings.main üst-alanları
    if s.get("site_name"):
        merged["store_name"] = s["site_name"]
    if s.get("logo_url"):
        merged["logo_url"] = s["logo_url"]
    if s.get("contact_email"):
        merged["contact_email"] = merged["email"] = s["contact_email"]
    if s.get("contact_phone"):
        merged["contact_phone"] = merged["phone"] = s["contact_phone"]
    if s.get("address"):
        merged["address"] = s["address"]
    # 3) company_info (en özel — admin doğrudan girer) yalnız dolu alanlar ezer
    ci = s.get("company_info") or {}
    for k, v in ci.items():
        if v not in (None, ""):
            merged[k] = v
    # alias tutarlılığı
    if ci.get("email"):
        merged["email"] = merged["contact_email"] = ci["email"]
    if ci.get("phone"):
        merged["phone"] = merged["contact_phone"] = ci["phone"]
    if ci.get("website"):
        merged["website"] = str(ci["website"]).replace("https://", "").replace("http://", "").rstrip("/")
    if ci.get("store_name"):
        merged["store_name"] = ci["store_name"]
    _cache = merged
    _cache_at = now
    return merged


async def get_site_url(db) -> str:
    """Storefront mutlak taban URL'i (e-posta linkleri için). company.site_url → env → default."""
    c = await get_company(db)
    return (c.get("site_url") or "https://facette.com.tr").rstrip("/")


def invalidate() -> None:
    global _cache_at
    _cache_at = 0.0
