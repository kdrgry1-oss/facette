"""
=============================================================================
provider_settings.py — E-Fatura ve Kargo Entegratör Ayarları
=============================================================================

AMAÇ:
  Yöneticinin piyasada bulunan büyük e-fatura entegratörleri ve kargo
  firmaları arasından istediğini seçip, sadece o entegratörün gerektirdiği
  bilgileri girip sisteme entegre edebilmesi için ayar altyapısı.

NASIL ÇALIŞIR?
  - Her provider için "schema" (alanlar + validasyon ipucu) tanımlıdır.
    Frontend bu şemayı alıp dinamik form render eder.
  - Kayıt: `providers_config` koleksiyonunda tek bir döküman tutulur:
      {
        "kind": "einvoice" | "cargo",
        "active_provider": "dogan-edonusum",
        "providers": {
          "dogan-edonusum": {<credentials>},
          "nilvera": {<credentials>},
          ...
        }
      }
  - Fatura kesme veya kargo etiketi basma rutinleri `active_provider`'ı
    okuyup o provider'ın config'i ile işlem yapar.

ENDPOINT'LER:
  - GET  /api/provider-settings/einvoice/schemas  → Tüm e-fatura provider şemaları
  - GET  /api/provider-settings/einvoice/config   → Kayıtlı tüm config + aktif provider
  - POST /api/provider-settings/einvoice/config   → Tüm config güncelle
  - POST /api/provider-settings/einvoice/test     → Seçili provider'ın bağlantı testi
  - GET  /api/provider-settings/cargo/schemas     → Aynı, kargo firmaları için
  - GET  /api/provider-settings/cargo/config
  - POST /api/provider-settings/cargo/config
  - POST /api/provider-settings/cargo/test

KULLANAN FRONTEND:
  - /app/frontend/src/pages/admin/EInvoiceSettings.jsx
  - /app/frontend/src/pages/admin/CargoSettings.jsx
=============================================================================
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime, timezone

from .deps import db, require_admin

router = APIRouter(prefix="/provider-settings", tags=["Provider Settings"])


# ---------------------------------------------------------------------------
# PROVIDER ŞEMALARI — alan tanımları, etiketler, zorunluluklar.
# Frontend bu şemayı alıp dinamik form oluşturur. Yeni bir provider eklemek
# için bu dict'e yeni kayıt eklemek yeterlidir; frontend'de ekstra kod YOK.
# ---------------------------------------------------------------------------

# Alan tipi: text | password | number | email | select
def _f(key, label, type="text", required=False, placeholder="", help=None, options=None):
    d = {"key": key, "label": label, "type": type, "required": required,
         "placeholder": placeholder}
    if help: d["help"] = help
    if options: d["options"] = options
    return d


EINVOICE_PROVIDERS = {
    # TÜRKİYE'NİN EN ÇOK KULLANILAN E-FATURA ENTEGRATÖRLERİ
    "dogan-edonusum": {
        "name": "Doğan e-Dönüşüm",
        "website": "https://www.edonusum.com",
        "description": "Ticimax başta olmak üzere yaygın kullanılan e-Fatura / e-Arşiv servis sağlayıcı.",
        "fields": [
            _f("vkn_tckn", "VKN / TCKN", required=True, placeholder="7810816779"),
            _f("branch", "Şube Adı", required=True, placeholder="DFLT"),
            _f("earchive_username", "E-Arşiv Kullanıcı Adı", required=True),
            _f("earchive_password", "E-Arşiv Şifre", type="password", required=True),
            _f("einvoice_username", "E-Fatura Kullanıcı Adı", required=True),
            _f("einvoice_password", "E-Fatura Şifre", type="password", required=True),
            _f("einvoice_post_label", "E-Fatura Posta Etiketi",
               placeholder="urn:mail:defaultpk@facette.com"),
            _f("einvoice_unit_label", "E-Fatura Birim Etiketi",
               placeholder="urn:mail:defaultgqb@facette.com"),
            _f("einvoice_prefix", "E-Fatura Öneki (Prefix)", required=True, placeholder="FCT"),
            _f("earchive_prefix", "E-Arşiv Öneki (Prefix)", required=True, placeholder="FAC"),
            _f("bank_commission_vat", "Banka Komisyonu KDV Oranı", type="number", placeholder="20"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "nilvera": {
        "name": "Nilvera",
        "website": "https://nilvera.com",
        "description": "Bulut tabanlı e-Fatura / e-Arşiv / e-SMM / e-İrsaliye entegratörü.",
        "fields": [
            _f("vkn_tckn", "VKN / TCKN", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("api_key", "API Key"),
            _f("einvoice_prefix", "E-Fatura Öneki", required=True, placeholder="FCT"),
            _f("earchive_prefix", "E-Arşiv Öneki", required=True, placeholder="FAC"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "uyumsoft": {
        "name": "Uyumsoft",
        "website": "https://www.uyumsoft.com.tr",
        "description": "Kurumsal e-Dönüşüm çözümleri (e-Fatura, e-Arşiv, e-İrsaliye).",
        "fields": [
            _f("vkn_tckn", "VKN / TCKN", required=True),
            _f("username", "Web Servis Kullanıcı Adı", required=True),
            _f("password", "Web Servis Şifre", type="password", required=True),
            _f("einvoice_prefix", "E-Fatura Öneki", required=True, placeholder="FCT"),
            _f("earchive_prefix", "E-Arşiv Öneki", required=True, placeholder="FAC"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "logo-edonusum": {
        "name": "Logo e-Dönüşüm",
        "website": "https://www.logo.com.tr",
        "description": "Logo Yazılım tarafından sunulan e-Fatura / e-Arşiv entegratörü.",
        "fields": [
            _f("vkn_tckn", "VKN / TCKN", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("customer_code", "Müşteri Kodu"),
            _f("einvoice_prefix", "E-Fatura Öneki", required=True, placeholder="FCT"),
            _f("earchive_prefix", "E-Arşiv Öneki", required=True, placeholder="FAC"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "mikro": {
        "name": "Mikro Yazılım",
        "website": "https://www.mikro.com.tr",
        "description": "Mikro ERP üzerinden e-Dönüşüm hizmetleri.",
        "fields": [
            _f("vkn_tckn", "VKN / TCKN", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("api_url", "API URL"),
            _f("einvoice_prefix", "E-Fatura Öneki", required=True, placeholder="FCT"),
            _f("earchive_prefix", "E-Arşiv Öneki", required=True, placeholder="FAC"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "foriba-edm": {
        "name": "Foriba (EDM)",
        "website": "https://www.foriba.com",
        "description": "EDM Bilişim / Foriba — kurumsal e-Fatura entegratörü.",
        "fields": [
            _f("vkn_tckn", "VKN / TCKN", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("einvoice_prefix", "E-Fatura Öneki", required=True, placeholder="FCT"),
            _f("earchive_prefix", "E-Arşiv Öneki", required=True, placeholder="FAC"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "qnb-efinans": {
        "name": "QNB Finansbank e-Finans",
        "website": "https://www.qnbefinans.com",
        "description": "Finansbank bünyesindeki e-Fatura / e-Arşiv servisi.",
        "fields": [
            _f("vkn_tckn", "VKN / TCKN", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("customer_no", "Müşteri Numarası"),
            _f("einvoice_prefix", "E-Fatura Öneki", required=True, placeholder="FCT"),
            _f("earchive_prefix", "E-Arşiv Öneki", required=True, placeholder="FAC"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "turkcell-esirket": {
        "name": "Turkcell e-Şirket",
        "website": "https://www.turkcell.com.tr/tr/sirketinize-ozel/e-donusum",
        "description": "Turkcell e-Dönüşüm servisleri.",
        "fields": [
            _f("vkn_tckn", "VKN / TCKN", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("einvoice_prefix", "E-Fatura Öneki", required=True, placeholder="FCT"),
            _f("earchive_prefix", "E-Arşiv Öneki", required=True, placeholder="FAC"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "izibiz": {
        "name": "İzibiz",
        "website": "https://www.izibiz.com.tr",
        "description": "İzibiz e-Fatura / e-Arşiv entegratörü.",
        "fields": [
            _f("vkn_tckn", "VKN / TCKN", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("einvoice_prefix", "E-Fatura Öneki", required=True, placeholder="FCT"),
            _f("earchive_prefix", "E-Arşiv Öneki", required=True, placeholder="FAC"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "idea-teknoloji": {
        "name": "İdea Teknoloji",
        "website": "https://www.ideateknoloji.com.tr",
        "description": "İdea Teknoloji e-Dönüşüm servisleri.",
        "fields": [
            _f("vkn_tckn", "VKN / TCKN", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("einvoice_prefix", "E-Fatura Öneki", required=True, placeholder="FCT"),
            _f("earchive_prefix", "E-Arşiv Öneki", required=True, placeholder="FAC"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "kolaysoft": {
        "name": "Kolaysoft",
        "website": "https://www.kolaysoft.com.tr",
        "description": "Kolaysoft e-Fatura entegrasyonu.",
        "fields": [
            _f("vkn_tckn", "VKN / TCKN", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("einvoice_prefix", "E-Fatura Öneki", required=True, placeholder="FCT"),
            _f("earchive_prefix", "E-Arşiv Öneki", required=True, placeholder="FAC"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
}


CARGO_PROVIDERS = {
    "mng": {
        "name": "MNG Kargo",
        "website": "https://www.mngkargo.com.tr",
        "description": "MNG Kargo API entegrasyonu.",
        "fields": [
            _f("customer_number", "Müşteri Numarası", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("identity_type", "Kimlik Tipi", placeholder="1 (TCKN) / 2 (VKN)"),
            _f("identity_no", "Kimlik No"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "yurtici": {
        "name": "Yurtiçi Kargo",
        "website": "https://www.yurticikargo.com",
        "description": "Yurtiçi Kargo web servis entegrasyonu.",
        "fields": [
            _f("customer_code", "Müşteri Kodu", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("api_key", "API Key"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "aras": {
        "name": "Aras Kargo",
        "website": "https://www.araskargo.com.tr",
        "description": "Aras Kargo web servis entegrasyonu.",
        "fields": [
            _f("customer_code", "Müşteri Kodu", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "ptt": {
        "name": "PTT Kargo",
        "website": "https://www.ptt.gov.tr",
        "description": "PTT Kargo & Lojistik entegrasyonu.",
        "fields": [
            _f("customer_number", "Müşteri Numarası", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "surat": {
        "name": "Sürat Kargo",
        "website": "https://www.suratkargo.com.tr",
        "description": "Sürat Kargo web servis.",
        "fields": [
            _f("customer_code", "Müşteri Kodu", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "hepsijet": {
        "name": "HepsiJet",
        "website": "https://www.hepsijet.com",
        "description": "Hepsiburada'nın kargo kolu.",
        "fields": [
            _f("customer_number", "Müşteri Numarası", required=True),
            _f("api_key", "API Key", type="password", required=True),
            _f("api_secret", "API Secret", type="password"),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "trendyol-express": {
        "name": "Trendyol Express",
        "website": "https://www.trendyol.com",
        "description": "Trendyol'un kargo hizmeti (Trendyol siparişleri için).",
        "fields": [
            _f("supplier_id", "Supplier ID (Tedarikçi No)", required=True),
            _f("api_key", "API Key", type="password", required=True),
            _f("api_secret", "API Secret", type="password", required=True),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "sendeo": {
        "name": "Sendeo",
        "website": "https://sendeo.com.tr",
        "description": "Sendeo Kargo entegrasyonu.",
        "fields": [
            _f("customer_code", "Müşteri Kodu", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "kolay-gelsin": {
        "name": "Kolay Gelsin",
        "website": "https://www.kolaygelsin.com",
        "description": "Kolay Gelsin Kargo.",
        "fields": [
            _f("customer_code", "Müşteri Kodu", required=True),
            _f("api_key", "API Key", type="password", required=True),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "dhl": {
        "name": "DHL Express",
        "website": "https://www.dhl.com",
        "description": "DHL Express uluslararası kargo API entegrasyonu.",
        "fields": [
            _f("account_number", "Hesap Numarası", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "ups": {
        "name": "UPS",
        "website": "https://www.ups.com",
        "description": "UPS kargo entegrasyonu.",
        "fields": [
            _f("account_number", "Hesap Numarası", required=True),
            _f("access_key", "Access Key", type="password", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "fedex": {
        "name": "FedEx",
        "website": "https://www.fedex.com",
        "description": "FedEx kargo API entegrasyonu.",
        "fields": [
            _f("account_number", "Hesap Numarası", required=True),
            _f("api_key", "API Key", type="password", required=True),
            _f("api_secret", "API Secret", type="password", required=True),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
    "tnt": {
        "name": "TNT",
        "website": "https://www.tnt.com",
        "description": "TNT uluslararası kargo.",
        "fields": [
            _f("account_number", "Hesap Numarası", required=True),
            _f("username", "Kullanıcı Adı", required=True),
            _f("password", "Şifre", type="password", required=True),
            _f("env", "Ortam", type="select", required=True,
               options=[{"value": "test", "label": "Test"}, {"value": "prod", "label": "Canlı"}]),
        ],
    },
}


PROVIDERS_BY_KIND = {
    "einvoice": EINVOICE_PROVIDERS,
    "cargo": CARGO_PROVIDERS,
}


# ---------------------------------------------------------------------------
# Endpoint yardımcıları
# ---------------------------------------------------------------------------
def _kind_guard(kind: str):
    if kind not in PROVIDERS_BY_KIND:
        raise HTTPException(status_code=404, detail="Bilinmeyen ayar grubu")


async def _get_config_doc(kind: str) -> dict:
    _kind_guard(kind)
    doc = await db.providers_config.find_one({"kind": kind}, {"_id": 0})
    if not doc:
        doc = {"kind": kind, "active_provider": None, "providers": {}}
    return doc


# ---------------------------------------------------------------------------
# SCHEMAS
# ---------------------------------------------------------------------------
@router.get("/{kind}/schemas")
async def get_schemas(kind: str, current_user: dict = Depends(require_admin)):
    """
    Belirtilen tür için (einvoice|cargo) tüm provider şemalarını döner.
    Frontend bu şemayı alıp dinamik form render eder.
    """
    _kind_guard(kind)
    return {
        "kind": kind,
        "providers": [
            {"key": k, **{kk: vv for kk, vv in v.items()}}
            for k, v in PROVIDERS_BY_KIND[kind].items()
        ],
    }


# ---------------------------------------------------------------------------
# CONFIG (read / write)
# ---------------------------------------------------------------------------
@router.get("/{kind}/config")
async def get_config(kind: str, current_user: dict = Depends(require_admin)):
    """Kayıtlı active_provider + per-provider credential map döner."""
    doc = await _get_config_doc(kind)
    return doc


@router.post("/{kind}/config")
async def save_config(kind: str, payload: dict,
                      current_user: dict = Depends(require_admin)):
    """
    Tüm config'i (active_provider + providers map) günceller. Provider
    credential'ları `providers.<key>.<field>` şeklinde saklanır.
    """
    _kind_guard(kind)
    active = payload.get("active_provider")
    providers = payload.get("providers") or {}
    valid_keys = set(PROVIDERS_BY_KIND[kind].keys())
    if active and active not in valid_keys:
        raise HTTPException(status_code=400, detail=f"Geçersiz provider: {active}")

    # Yalnızca tanınan provider'ların verisini saklıyoruz (diğerlerini at)
    providers = {k: v for k, v in providers.items() if k in valid_keys}

    update_doc = {
        "kind": kind,
        "active_provider": active,
        "providers": providers,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": current_user.get("email") or current_user.get("id"),
    }
    await db.providers_config.update_one(
        {"kind": kind}, {"$set": update_doc}, upsert=True
    )
    return {"success": True, "message": "Ayarlar kaydedildi",
            "active_provider": active,
            "configured_providers": list(providers.keys())}


# ---------------------------------------------------------------------------
# CONNECTION TEST (mock)
# ---------------------------------------------------------------------------
@router.post("/{kind}/test")
async def test_connection(kind: str, payload: dict,
                          current_user: dict = Depends(require_admin)):
    """
    Seçili provider için bağlantı testi. Şu an mock — gerçek SDK'lar
    canlı API key'leri geldiğinde devreye alınacak. Zorunlu alanların
    dolu olduğunu doğrular.
    """
    _kind_guard(kind)
    provider_key = payload.get("provider")
    config = payload.get("config") or {}
    providers = PROVIDERS_BY_KIND[kind]
    if provider_key not in providers:
        raise HTTPException(status_code=404, detail="Provider bulunamadı")

    schema = providers[provider_key]
    missing = []
    for field in schema["fields"]:
        if field.get("required") and not str(config.get(field["key"], "")).strip():
            missing.append(field["label"])
    if missing:
        return {"success": False, "message": "Eksik alan(lar): " + ", ".join(missing),
                "missing": missing}

    # MOCK: başarılı gibi davran. Canlıda burada gerçek login/HTTP request
    # yapılacak. Kullanıcının canlıya geçişte yalnızca bu fonksiyonu
    # güncellemesi yeterlidir.
    return {
        "success": True,
        "provider": provider_key,
        "provider_name": schema["name"],
        "message": f"{schema['name']} yapılandırması doğrulandı. (Bağlantı testi canlıya geçişte aktif olacak.)",
        "mock": True,
    }
