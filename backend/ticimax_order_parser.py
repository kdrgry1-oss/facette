"""
Ticimax sipariş parser - ortak helper.
Hem cron (scheduler.py) hem manuel/backfill (routes/integrations.py) kullanımları
için tek noktadan tutarlı eşleştirme sağlar.

Kaynak: routes/integrations.py içinden çıkarıldı (satır 1800-1930 dolaylarında olan
mantık). Cron daha önce minimal/yanlış map yapıyordu (AliciAdi top-level), bu helper
KargoAdresi/FaturaAdresi nested dict + UrunListesi item parse mantığını kullanır.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional


_STATUS_MAP = {
    "Yeni": "pending", "Onaylandı": "confirmed", "Hazırlanıyor": "processing",
    "Kargoya Verildi": "shipped", "Teslim Edildi": "delivered",
    "İptal": "cancelled", "İade": "returned",
}


def _to_dict(maybe_obj):
    """Zeep nesnesini ya da dict'i normal dict'e çevir."""
    if maybe_obj is None:
        return {}
    if hasattr(maybe_obj, "__values__"):
        try:
            return dict(maybe_obj.__values__)
        except Exception:
            return {}
    return maybe_obj if isinstance(maybe_obj, dict) else {}


def _parse_items(raw, ticimax_order_id: int, api_key: Optional[str] = None) -> List[Dict]:
    """UrunListesi/Urunler veya fallback ile item parse."""
    urunler_raw = raw.get("UrunListesi") or raw.get("Urunler") or []
    if hasattr(urunler_raw, "__values__"):
        try:
            vals = list(urunler_raw.__values__.values())
            urunler_raw = vals[0] if vals else []
        except Exception:
            urunler_raw = []
    if not urunler_raw and api_key:
        # Fallback: SOAP ile tek tek çek
        try:
            from ticimax_client import get_order_items  # local import
            urunler_raw = get_order_items(ticimax_order_id, wscode=api_key) or []
        except Exception:
            urunler_raw = []
    if not isinstance(urunler_raw, list):
        urunler_raw = [urunler_raw] if urunler_raw else []

    items = []
    for item in urunler_raw:
        if not item:
            continue
        d = _to_dict(item)
        if not d:
            continue
        items.append({
            "product_name": str(d.get("UrunAdi") or d.get("Adi") or ""),
            "name":         str(d.get("UrunAdi") or d.get("Adi") or ""),
            "stock_code":   str(d.get("StokKodu") or ""),
            "barcode":      str(d.get("Barkod") or ""),
            "quantity":     int(d.get("Adet") or d.get("Miktar") or 1),
            "price":        float(d.get("BirimFiyat") or d.get("Fiyat") or 0),
            "size":         str(d.get("Beden") or ""),
            "color":        str(d.get("Renk") or ""),
            "image":        str(d.get("Resim") or d.get("ResimUrl") or ""),
            "ticimax_urun_id": d.get("UrunID") or d.get("UrunKartiID"),
        })
    return items


def parse_ticimax_order(raw: Dict, api_key: Optional[str] = None) -> Optional[Dict]:
    """Tek bir Ticimax SelectSiparis kaydını standart `orders` dokümanına çevirir.
    
    Returns None if `raw` boş ya da ticimax_order_id yok.
    """
    if not raw:
        return None
    ticimax_order_id = raw.get("SiparisID") or raw.get("ID") or raw.get("OdemeID")
    if not ticimax_order_id:
        return None
    try:
        ticimax_order_id = int(ticimax_order_id)
    except Exception:
        return None

    order_number = str(raw.get("SiparisNo") or raw.get("SiparisKodu") or ticimax_order_id).strip().upper()
    order_code   = str(raw.get("SiparisKodu") or "")
    odenen       = float(raw.get("OdenenTutar") or 0)
    kargo_tutari = float(raw.get("KargoTutari") or 0)
    indirim      = float(raw.get("IndirimTutari") or raw.get("KuponIndirimi") or 0)
    kdv_tutari   = float(raw.get("KdvTutari") or 0)
    total        = float(raw.get("ToplamTutar") or raw.get("GenelToplam") or
                         raw.get("ToplamSiparisTutari") or odenen or 0)
    status_raw   = str(raw.get("Durum") or raw.get("SiparisDurumu") or
                       raw.get("SiparisDurumuStr") or "Yeni")
    status       = _STATUS_MAP.get(status_raw, "pending")
    created_at   = str(raw.get("SiparisTarihi") or raw.get("Tarih") or
                       datetime.now(timezone.utc).isoformat())
    ip_address   = str(raw.get("IPAdresi") or "")
    kaynak       = str(raw.get("Kaynak") or "")
    kargo_takip  = str(raw.get("KargoTakipNo") or "")
    kargo_link   = str(raw.get("KargoTakipLink") or "")
    kargo_firma  = str(raw.get("KargoFirmaTanim") or "")
    fatura_no    = str(raw.get("FaturaNo") or "")
    adi_soyadi   = str(raw.get("AdiSoyadi") or "")
    email        = str(raw.get("Mail") or raw.get("AliciEmail") or "").strip().lower()
    uye_id       = raw.get("UyeID") or raw.get("UyeId") or 0

    kargo_adresi = _to_dict(raw.get("KargoAdresi"))
    fatura_adresi = _to_dict(raw.get("FaturaAdresi"))

    # AliciAdi adres içinde "Ad Soyad" tek string olarak gelir → ilk kelime first_name
    full_name = str(kargo_adresi.get("AliciAdi") or fatura_adresi.get("AliciAdi") or adi_soyadi or "").strip()
    parts = [p for p in full_name.split(" ") if p]
    first_name = parts[0] if parts else ""
    last_name  = " ".join(parts[1:]) if len(parts) > 1 else ""

    phone = str(
        raw.get("UyeTelefon") or
        kargo_adresi.get("AliciTelefon") or kargo_adresi.get("Telefon") or kargo_adresi.get("CepTelefonu") or
        fatura_adresi.get("AliciTelefon") or fatura_adresi.get("Telefon") or
        ""
    ).strip()

    address_text = str(kargo_adresi.get("Adres") or fatura_adresi.get("Adres") or "")
    city = str(
        kargo_adresi.get("Sehir") or kargo_adresi.get("Il") or kargo_adresi.get("IlAdi") or
        fatura_adresi.get("Sehir") or fatura_adresi.get("Il") or ""
    )
    district = str(
        kargo_adresi.get("Ilce") or kargo_adresi.get("IlceAdi") or
        fatura_adresi.get("Ilce") or ""
    )
    posta_kodu = str(kargo_adresi.get("PostaKodu") or fatura_adresi.get("PostaKodu") or "")

    # Posta kodu varsa ama il boşsa, ilk 2 hane → il
    if not city and posta_kodu and len(posta_kodu) >= 2:
        try:
            from il_mapping import IL_CODE_TO_NAME  # type: ignore
            city = IL_CODE_TO_NAME.get(posta_kodu[:2], "")
        except Exception:
            pass

    items = _parse_items(raw, ticimax_order_id, api_key=api_key)
    if not items and not city and address_text == "":
        # Hiç anlamlı veri yoksa subtotal hesabını yine de yapalım
        pass

    subtotal = max(0.0, total - kargo_tutari + indirim) if total else 0.0

    doc = {
        "ticimax_order_id": ticimax_order_id,
        "ticimax_uye_id": int(uye_id) if uye_id else None,
        "order_number": order_number,
        "order_code": order_code,
        "items": items,
        "shipping_address": {
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "email": email,
            "address": address_text,
            "city": city,
            "district": district,
            "postal_code": posta_kodu,
        },
        "billing_address": {
            "name": fatura_adresi.get("AliciAdi") or adi_soyadi,
            "phone": fatura_adresi.get("AliciTelefon") or phone,
            "address": fatura_adresi.get("Adres") or "",
            "city": fatura_adresi.get("Sehir") or fatura_adresi.get("Il") or "",
            "district": fatura_adresi.get("Ilce") or "",
            "tax_no": fatura_adresi.get("VergiNo") or "",
            "tax_office": fatura_adresi.get("VergiDairesi") or "",
        },
        "subtotal": subtotal,
        "shipping_cost": kargo_tutari,
        "discount": indirim,
        "tax": kdv_tutari,
        "total": total,
        "paid_amount": odenen,
        "payment_method": str(raw.get("OdemeTipi") or "ticimax"),
        "payment_status": "paid" if (raw.get("OdemeTamamlandi") or odenen >= total > 0) else "pending",
        "status": status,
        "platform": "facette",
        "source": "ticimax",
        "channel_source": kaynak,
        "channel": "web",
        "ip_address": ip_address,
        "is_marketplace": False,
        "cargo_tracking_number": kargo_takip,
        "cargo_tracking_link": kargo_link,
        "cargo_provider_name": kargo_firma,
        "invoice_number": fatura_no,
        "created_at": created_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return doc


def is_marketplace_order(raw: Dict) -> bool:
    """Pazaryeri (Trendyol/HB/N11 vb.) siparişi mi?"""
    if not raw:
        return False
    siparis_no = str(raw.get("SiparisNo") or "").upper()
    kaynak = str(raw.get("Kaynak") or "").lower()
    mp_keywords = ("trendyol", "hepsiburada", "n11", "aliexpress", "amazon",
                   "ciceksepeti", "pttavm", "temu", "pazarama", "gittigidiyor", "epttavm")
    mp_prefixes = ("TY-", "HB-", "N11-", "AMZ-", "AE-")
    is_mp_flag = bool(raw.get("IsMarketplace") or (raw.get("PazaryeriButikId") or 0) > 0)
    if is_mp_flag:
        return True
    if any(kw in kaynak for kw in mp_keywords):
        return True
    if any(siparis_no.startswith(pref) for pref in mp_prefixes):
        return True
    return False
