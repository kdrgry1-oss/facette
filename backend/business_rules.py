"""
business_rules.py — Merkezî İşletme Kuralları / Ayarlar motoru (çok-kiracılı SaaS).

AMAÇ:
  Kodda gömülü olan tüm işletme kurallarını (iptal süreleri, ücretler, eşikler,
  çalışma saatleri vb.) TEK yerden admin panelinden yönetilebilir kılmak. Böylece
  bu SaaS'ı kullanan her firma kendi kurallarını değiştirebilir.

TASARIM:
  - RULE_CATALOG: her kuralın meta bilgisi (grup, etiket, tip, varsayılan, seçenekler,
    yardım metni). Kod bu katalogdaki ANAHTAR + VARSAYILAN ile okur.
  - db.settings id="business_rules" tek dokümanda kullanıcı değerleri saklanır.
  - get_rule(key): kullanıcı değeri varsa onu, yoksa katalog varsayılanını döner (cache'li).
  - Yeni bir kuralı yönetilebilir yapmak = kataloğa bir satır ekleyip kodda
    sabit yerine `await get_rule("...")` çağırmak.

NOT: "options" alanı, admin panelinde o ayarın DEĞİŞTİRME ALTERNATİFLERİ olarak
     gösterilir (kullanıcı isteğine göre hazır seçenekler). type='number' için
     serbest giriş + öneri; type='select' için sabit seçenekler; type='toggle' için
     aç/kapa; type='time' için saat; type='multiselect' için çoklu seçim.
"""
from typing import Any, Dict
import time as _time

# =============================================================================
# KURAL KATALOĞU
# =============================================================================
# group: admin panelinde bölüm başlığı
# key: kod ve DB anahtarı
# label: kullanıcıya görünen ad
# type: number | select | toggle | time | multiselect | text
# default: kod varsayılanı (kullanıcı değeri yoksa)
# unit: gösterim birimi (saat, ₺, % ...)
# options: number → öneri değerleri; select/multiselect → seçenek listesi
# help: kısa açıklama
RULE_CATALOG = [
    # ---- Sipariş & İptal ----
    {"group": "Sipariş & İptal", "key": "order.havale_cancel_hours", "label": "Havale/EFT ödenmemiş sipariş otomatik iptal süresi",
     "type": "number", "default": 72, "unit": "saat", "options": [24, 48, 72, 96, 120],
     "help": "Havale/EFT ile ödenip bu süre içinde ödeme gelmezse sipariş otomatik iptal edilir ve stok iade edilir."},
    {"group": "Sipariş & İptal", "key": "order.unpaid_card_cancel_hours", "label": "Ödenmemiş kart siparişi otomatik iptal süresi",
     "type": "number", "default": 3, "unit": "saat", "options": [1, 2, 3, 6, 12, 24],
     "help": "3DS başlatılıp ödemesi tamamlanmayan kart siparişleri bu süre sonra 'Ödeme Alınamadı' olur ve stok iade edilir."},
    {"group": "Sipariş & İptal", "key": "order.cancel_reason_required", "label": "İade/iptal talebinde sebep zorunlu",
     "type": "toggle", "default": True, "options": [True, False],
     "help": "Açıkken müşteri iade/iptal sebebini doldurmadan talebi gönderemez."},

    # ---- Kargo & Teslimat ----
    {"group": "Kargo & Teslimat", "key": "shipping.cod_fee", "label": "Kapıda ödeme ücreti",
     "type": "number", "default": 10, "unit": "₺", "options": [0, 10, 15, 20, 25],
     "help": "Kapıda ödeme seçilince sipariş toplamına eklenen hizmet bedeli."},
    {"group": "Kargo & Teslimat", "key": "shipping.same_day_cutoff", "label": "Aynı gün kargo son saati",
     "type": "time", "default": "10:30", "options": ["09:00", "10:00", "10:30", "12:00", "14:00", "16:00"],
     "help": "Mesai gününde bu saate kadar verilen siparişler aynı gün kargolanır (ürün kartındaki geri sayım bu saate göre çalışır)."},
    {"group": "Kargo & Teslimat", "key": "shipping.work_days", "label": "Çalışma (kargo) günleri",
     "type": "multiselect", "default": [1, 2, 3, 4, 5], "options": [1, 2, 3, 4, 5, 6, 7],
     "help": "Kargonun çıktığı günler (1=Pzt … 7=Paz). Resmî tatiller ayrıca hariç tutulur."},
    {"group": "Kargo & Teslimat", "key": "shipping.exclude_official_holidays", "label": "Resmî tatillerde kargo çıkma",
     "type": "toggle", "default": True, "options": [True, False],
     "help": "Açıkken resmî tatil günleri 'aynı gün/yarın kargo' hesabından hariç tutulur."},

    # ---- Ödeme & İndirim ----
    # NOT: Havale/EFT indirimi ayrı yerde (Genel Ayarlar > Ödeme) yönetilir; burada mükerrer tutulmaz.
    {"group": "Ödeme & İndirim", "key": "payment.points_redeem_max_pct", "label": "Puan ile ödenebilecek azami oran",
     "type": "number", "default": 10, "unit": "%", "options": [5, 10, 15, 20, 25],
     "help": "Müşteri sipariş tutarının en fazla bu oranını puanla ödeyebilir."},
    {"group": "Ödeme & İndirim", "key": "product.gift_wrap_price", "label": "Hediye paketi ücreti",
     "type": "number", "default": 130, "unit": "₺", "options": [0, 50, 100, 130, 150, 200],
     "help": "Hediye paketi seçilince eklenen ücret."},

    # ---- İade ----
    {"group": "İade & Değişim", "key": "return.window_days", "label": "İade/değişim süresi",
     "type": "number", "default": 14, "unit": "gün", "options": [7, 14, 15, 30],
     "help": "Teslimattan sonra müşterinin iade/değişim talebi açabileceği gün sayısı."},

    # ---- Ürün & Vitrin ----
    {"group": "Ürün & Vitrin", "key": "product.max_combine", "label": "Azami 'Stilini Tamamla' ürün sayısı",
     "type": "number", "default": 12, "unit": "adet", "options": [4, 6, 8, 12, 16],
     "help": "Bir ürüne elle atanabilecek maksimum kombin ('Stilini Tamamla') ürün sayısı."},
    {"group": "Ürün & Vitrin", "key": "product.fit_recommendation_enabled", "label": "Kalıba göre beden önerisi göster",
     "type": "toggle", "default": True, "options": [True, False],
     "help": "Ürün kalıbına göre 'bir beden büyük/küçük alın' önerisini ürün kartında gösterir."},

    # ---- Bildirim & Oturum ----
    {"group": "Panel & Oturum", "key": "panel.auto_logout_minutes", "label": "Panel otomatik çıkış (inaktivite)",
     "type": "number", "default": 60, "unit": "dakika", "options": [15, 30, 60, 120, 0],
     "help": "Panelde bu süre işlem yapılmazsa otomatik çıkış yapılır ve filtreler sıfırlanır. 0 = kapalı."},
]

_CATALOG_BY_KEY = {r["key"]: r for r in RULE_CATALOG}

# --- basit cache (30 sn) — her istekte DB'ye gitmemek için ---
_cache: Dict[str, Any] = {}
_cache_at = 0.0
_CACHE_TTL = 30.0


async def _load(db) -> Dict[str, Any]:
    global _cache, _cache_at
    now = _time.time()
    if (now - _cache_at) < _CACHE_TTL and _cache:
        return _cache
    doc = await db.settings.find_one({"id": "business_rules"}, {"_id": 0}) or {}
    _cache = doc.get("values") or {}
    _cache_at = now
    return _cache


def _default(key: str):
    r = _CATALOG_BY_KEY.get(key) or {}
    return r.get("default")


async def get_rule(db, key: str, fallback=None):
    """Kuralı DB'den (kullanıcı değeri) yoksa katalog varsayılanından döner."""
    try:
        vals = await _load(db)
    except Exception:
        vals = {}
    if key in vals and vals[key] is not None:
        return vals[key]
    d = _default(key)
    return d if d is not None else fallback


def invalidate():
    global _cache_at
    _cache_at = 0.0


async def get_all_for_admin(db):
    """Admin paneli için: katalog meta + mevcut değerler (gruplanmış)."""
    vals = await _load(db)
    groups: Dict[str, list] = {}
    for r in RULE_CATALOG:
        cur = vals.get(r["key"], r["default"])
        item = {**r, "value": cur}
        groups.setdefault(r["group"], []).append(item)
    return [{"group": g, "rules": items} for g, items in groups.items()]


async def save_rules(db, patch: dict):
    """Yalnız katalogdaki anahtarları kaydeder (bilinmeyen anahtar reddedilir)."""
    clean = {}
    for k, v in (patch or {}).items():
        if k in _CATALOG_BY_KEY:
            clean[k] = v
    if clean:
        cur = await db.settings.find_one({"id": "business_rules"}, {"_id": 0}) or {}
        vals = cur.get("values") or {}
        vals.update(clean)
        await db.settings.update_one(
            {"id": "business_rules"}, {"$set": {"values": vals}}, upsert=True
        )
        invalidate()
    return {"saved": list(clean.keys())}


# =============================================================================
# RESMÎ TATİLLER (TR) — 2026-2030 (aynı gün/yarın kargo hesabı için)
# Sabit tarihli millî bayramlar + dinî bayramlar (Ramazan/Kurban, yaklaşık resmî tarihler).
# =============================================================================
TR_OFFICIAL_HOLIDAYS = {
    # sabit millî
    "2026-01-01","2026-04-23","2026-05-01","2026-05-19","2026-07-15","2026-08-30","2026-10-29",
    "2027-01-01","2027-04-23","2027-05-01","2027-05-19","2027-07-15","2027-08-30","2027-10-29",
    "2028-01-01","2028-04-23","2028-05-01","2028-05-19","2028-07-15","2028-08-30","2028-10-29",
    "2029-01-01","2029-04-23","2029-05-01","2029-05-19","2029-07-15","2029-08-30","2029-10-29",
    "2030-01-01","2030-04-23","2030-05-01","2030-05-19","2030-07-15","2030-08-30","2030-10-29",
    # Ramazan Bayramı (arife dahil yaklaşık)
    "2026-03-20","2026-03-21","2026-03-22",
    "2027-03-10","2027-03-11","2027-03-12",
    "2028-02-26","2028-02-27","2028-02-28","2028-02-29",
    "2029-02-14","2029-02-15","2029-02-16",
    "2030-02-04","2030-02-05","2030-02-06",
    # Kurban Bayramı (yaklaşık)
    "2026-05-27","2026-05-28","2026-05-29","2026-05-30",
    "2027-05-16","2027-05-17","2027-05-18","2027-05-19",
    "2028-05-05","2028-05-06","2028-05-07","2028-05-08",
    "2029-04-24","2029-04-25","2029-04-26","2029-04-27",
    "2030-04-13","2030-04-14","2030-04-15","2030-04-16",
}
