"""
Ticimax sipariş parser - ortak helper.
Hem cron (scheduler.py) hem manuel/backfill (routes/integrations.py) hem de
/import (routes/integrations.py import_ticimax_orders) tek noktadan tutarlı eşleştirme
kullanır.

DÜZELTME (2026-06-11): Gerçek Ticimax SelectSiparis yanıt yapısına göre düzeltildi.
  - Urunler: {"WebSiparisUrun": [...]} dict → liste olarak açılır (eskiden tek eleman sarılıyordu)
  - Beden/Renk: EkSecenekList.WebSiparisUrunEkSecenekOzellik (TipID=1 renk, TipID=2 beden)
    (eskiden olmayan Beden/Renk alanları okunuyordu → hep boş)
  - Fiyat: SatisAniIndirimliFiyat / Tutar (eskiden olmayan BirimFiyat → hep 0)
  - Ödeme: Odemeler.WebSiparisOdeme[].OdemeTipi int kodu (eskiden top-level OdemeTipi → hep None)
  - Durum: top-level Durum int kodu (9,13,17...) → iç status; string label fallback
    (eskiden Durum=int, _STATUS_MAP string bekliyordu → iade siparişleri "pending"e düşüyordu)
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional


# ── Ticimax durum INT kodu → iç status (SelectSiparisDurumlari ile birebir) ──
_STATUS_CODE_MAP = {
    0: "pending", 1: "pending", 2: "confirmed", 3: "pending",
    4: "processing", 5: "processing", 6: "shipped", 7: "delivered",
    8: "cancelled", 9: "returned", 10: "cancelled",
    11: "return_requested", 12: "returned", 13: "refunded",
    14: "cancelled", 15: "cancelled", 16: "return_requested",
    17: "partial_refunded", 18: "delivered", 19: "processing",
    20: "processing", 21: "processing", 22: "refunded",
}
# String label → iç status (Durum int yoksa fallback)
_STATUS_STR_MAP = {
    "siparişiniz alındı": "pending", "onay bekliyor": "pending",
    "onaylandı": "confirmed", "ödeme bekliyor": "pending",
    "paketleniyor": "processing", "tedarik ediliyor": "processing",
    "kargoya verildi": "shipped", "teslim edildi": "delivered",
    "iptal edildi": "cancelled", "iptal": "cancelled",
    "iade edildi": "returned", "iade talebi alındı": "return_requested",
    "iade ulaştı ödeme yapılacak": "returned", "iade ödemesi yapıldı": "refunded",
    "kısmi iade talebi": "return_requested", "kısmi iade yapıldı": "partial_refunded",
    "cüzdana iade yapıldı": "refunded", "teslim edilemedi": "delivered",
    "yeni": "pending", "iade": "returned",
}
# Ödeme INT kodu → (method, okunabilir etiket)
_PAYMENT_CODE_MAP = {
    1:  ("bank_transfer",    "Havale/EFT"),
    2:  ("cash_on_delivery", "Kapıda Ödeme (Nakit)"),
    3:  ("cod_card",         "Kapıda Ödeme (Kredi Kartı)"),
    10: ("credit_card",      "Kredi Kartı"),
    17: ("credit_card",      "Kredi Kartı"),
    31: ("credit_card",      "Kredi Kartı"),
}

_STATUS_MAP = _STATUS_STR_MAP  # geriye dönük uyum (eski isim)


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


def _inner_list(container):
    """{"WebSiparisUrun":[...]} / {"WebSiparisOdeme":[...]} gibi tek-anahtarlı
    sarmalı, ya da zaten liste olanı düz listeye çevirir."""
    c = container
    if hasattr(c, "__values__"):
        try:
            c = dict(c.__values__)
        except Exception:
            c = {}
    if isinstance(c, list):
        return c
    if isinstance(c, dict):
        for v in c.values():
            if isinstance(v, list):
                return v
    return []


def _item_variant(d: Dict):
    """EkSecenekList → (beden, renk). TipID=1 renk, TipID=2 beden."""
    color = size = ""
    for opt in _inner_list(d.get("EkSecenekList")):
        od = _to_dict(opt)
        tip = od.get("TipID")
        tanim = od.get("Tanim") or ""
        if tip == 1 and not color:
            color = tanim
        elif tip == 2 and not size:
            size = tanim
    return size, color


def extract_items(raw: Dict, ticimax_order_id: int, api_key: Optional[str] = None) -> List[Dict]:
    """Sipariş kalemlerini doğru alanlardan çıkar. Inline gelmezse SOAP fallback."""
    urunler = _inner_list(raw.get("UrunListesi") or raw.get("Urunler"))
    if not urunler and api_key:
        try:
            from ticimax_client import get_order_items  # local import
            urunler = get_order_items(ticimax_order_id, wscode=api_key) or []
        except Exception:
            urunler = []

    items: List[Dict] = []
    for it in urunler:
        d = _to_dict(it)
        if not d:
            continue
        size, color = _item_variant(d)
        price = (d.get("SatisAniIndirimliFiyat") or d.get("Tutar") or
                 d.get("SatisAniSatisFiyat") or d.get("BirimFiyat") or d.get("Fiyat") or 0)
        items.append({
            "product_name": str(d.get("UrunAdi") or d.get("Adi") or ""),
            "name":         str(d.get("UrunAdi") or d.get("Adi") or ""),
            "stock_code":   str(d.get("StokKodu") or ""),
            "barcode":      str(d.get("Barkod") or ""),
            "quantity":     int(d.get("Adet") or d.get("Miktar") or 1),
            "price":        round(float(price or 0), 2),
            "size":         size or str(d.get("Beden") or ""),
            "color":        color or str(d.get("Renk") or ""),
            "image":        str(d.get("ResimYolu") or d.get("Resim") or d.get("ResimUrl") or ""),
            "ticimax_urun_id": d.get("UrunID") or d.get("UrunKartiID"),
        })
    return items


def extract_payment(raw: Dict):
    """Odemeler.WebSiparisOdeme[].OdemeTipi int kodundan ödeme yöntemi.
    Dönüş: (payment_method, payment_method_raw_label, paid_amount)."""
    ods = _inner_list(raw.get("Odemeler"))
    paid = 0.0
    code = None
    for p in ods:
        pd = _to_dict(p)
        if code is None:
            code = pd.get("OdemeTipi")
        paid += float(pd.get("Tutar") or 0)

    if isinstance(code, int) and code in _PAYMENT_CODE_MAP:
        method, label = _PAYMENT_CODE_MAP[code]
        return method, label, round(paid, 2)

    # String fallback (bazı eski yanıtlarda top-level metin gelebilir)
    raw_txt = str(raw.get("OdemeTipi") or raw.get("OdemeSekli") or
                  raw.get("OdemeYontemi") or raw.get("OdemeAdi") or "").strip()
    low = raw_txt.lower()
    if "havale" in low or "eft" in low or "banka" in low:
        return "bank_transfer", raw_txt or "Havale/EFT", round(paid, 2)
    if "kapıda" in low or "kapida" in low:
        return "cash_on_delivery", raw_txt or "Kapıda Ödeme", round(paid, 2)
    if "kart" in low or "kredi" in low:
        return "credit_card", raw_txt or "Kredi Kartı", round(paid, 2)
    return "ticimax", raw_txt or (f"Kod {code}" if code is not None else ""), round(paid, 2)


def map_status(raw: Dict) -> str:
    """Top-level Durum int kodundan iç status; yoksa string label fallback."""
    code = raw.get("Durum")
    if isinstance(code, bool):
        code = None
    else:
        try:
            code = int(code) if code is not None and str(code).strip() != "" else None
        except Exception:
            code = None
    if code is not None and code in _STATUS_CODE_MAP:
        return _STATUS_CODE_MAP[code]
    label = str(raw.get("SiparisDurumu") or raw.get("StrSiparisDurumu") or
                raw.get("SiparisDurumuStr") or "").strip().lower()
    return _STATUS_STR_MAP.get(label, "pending")


def _parse_items(raw, ticimax_order_id: int, api_key: Optional[str] = None) -> List[Dict]:
    """Geriye dönük uyum — extract_items'a yönlendirir."""
    return extract_items(raw, ticimax_order_id, api_key=api_key)


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
    kargo_tutari = float(raw.get("KargoTutari") or 0)
    indirim      = float(raw.get("IndirimTutari") or raw.get("KuponIndirimi") or 0)
    kdv_tutari   = float(raw.get("KdvTutari") or raw.get("ToplamKdv") or 0)
    total        = float(raw.get("SiparisToplamTutari") or raw.get("ToplamTutar") or
                         raw.get("GenelToplam") or raw.get("ToplamSiparisTutari") or 0)
    status       = map_status(raw)
    payment_method, payment_raw, odenen = extract_payment(raw)
    if total <= 0:
        total = odenen
    created_at   = str(raw.get("SiparisTarihi") or raw.get("Tarih") or
                       datetime.now(timezone.utc).isoformat())
    ip_address   = str(raw.get("IPAdresi") or "")
    kaynak       = str(raw.get("Kaynak") or raw.get("SiparisKaynagi") or "")
    kargo_takip  = str(raw.get("KargoTakipNo") or "")
    kargo_link   = str(raw.get("KargoTakipLink") or "")
    kargo_firma  = str(raw.get("KargoFirmaTanim") or raw.get("KargoFirmaAdi") or "")
    fatura_no    = str(raw.get("FaturaNo") or "")
    adi_soyadi   = str(raw.get("AdiSoyadi") or "")
    email        = str(raw.get("Mail") or raw.get("AliciEmail") or "").strip().lower()
    uye_id       = raw.get("UyeID") or raw.get("UyeId") or 0

    kargo_adresi = _to_dict(raw.get("KargoAdresi"))
    fatura_adresi = _to_dict(raw.get("FaturaAdresi"))

    # İsim: AliciAdi / FirmaAdi adres içinde, yoksa top-level AdiSoyadi
    full_name = str(
        kargo_adresi.get("AliciAdi") or kargo_adresi.get("FirmaAdi") or
        fatura_adresi.get("AliciAdi") or fatura_adresi.get("FirmaAdi") or
        adi_soyadi or ""
    ).strip()
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

    if not city and posta_kodu and len(posta_kodu) >= 2:
        try:
            from il_mapping import IL_CODE_TO_NAME  # type: ignore
            city = IL_CODE_TO_NAME.get(posta_kodu[:2], "")
        except Exception:
            pass

    items = extract_items(raw, ticimax_order_id, api_key=api_key)
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
            "name": fatura_adresi.get("AliciAdi") or fatura_adresi.get("FirmaAdi") or adi_soyadi,
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
        "payment_method": payment_method,
        "payment_method_raw": payment_raw,
        "payment_status": "paid" if (raw.get("OdemeTamamlandi") or (odenen >= total > 0)) else "pending",
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
    kaynak = str(raw.get("Kaynak") or raw.get("SiparisKaynagi") or "").lower()
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
