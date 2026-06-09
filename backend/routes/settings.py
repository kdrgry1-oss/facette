from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from datetime import datetime, timezone
import re

from .deps import db, require_admin

router = APIRouter(prefix="/settings", tags=["Settings"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

@router.post("/maintenance/notify")
async def maintenance_notify_subscribe(payload: dict):
    """Public: bakım modu sırasında 'açılınca haber ver' e-posta toplama."""
    email = (payload.get("email") or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Geçerli bir e-posta adresi giriniz.")
    existing = await db.maintenance_subscribers.find_one({"email": email})
    if existing:
        return {"message": "E-posta adresiniz zaten kayıtlı. Açılınca size haber vereceğiz."}
    await db.maintenance_subscribers.insert_one({
        "email": email,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notified": False,
    })
    return {"message": "Teşekkürler! Site açılır açılmaz size haber vereceğiz."}

@router.get("/maintenance/subscribers")
async def maintenance_subscribers_list(current_user: dict = Depends(require_admin)):
    """Admin: bakım modu e-posta aboneleri."""
    items = await db.maintenance_subscribers.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return {"total": len(items), "subscribers": items}

@router.get("/maintenance")
async def get_maintenance_status():
    """Public, lightweight maintenance-mode status used by the storefront gate."""
    settings = await db.settings.find_one(
        {"id": "main"},
        {"_id": 0, "maintenance_mode": 1, "maintenance_title": 1, "maintenance_message": 1, "logo_url": 1, "site_name": 1},
    ) or {}
    return {
        "maintenance_mode": bool(settings.get("maintenance_mode", False)),
        "maintenance_title": settings.get("maintenance_title") or "Sitemiz sizin için yenileniyor",
        "maintenance_message": settings.get("maintenance_message") or "Çok yakında, daha iyi bir alışveriş deneyimiyle buradayız. Anlayışınız için teşekkür ederiz.",
        "logo_url": settings.get("logo_url") or "",
        "site_name": settings.get("site_name") or "FACETTE",
    }

@router.get("")
async def get_settings():
    """Get global settings"""
    settings = await db.settings.find_one({"id": "main"}, {"_id": 0})
    if not settings:
        settings = {
            "id": "main",
            "site_name": "FACETTE",
            "logo_url": "",
            "free_shipping_limit": 500,
            "rotating_texts": [],
            "contact_email": "",
            "contact_phone": "",
            "address": "",
            "payment_methods": {"credit_card": True, "bank_transfer": True, "cash_on_delivery": True},
            "barcode_range_start": "",
            "barcode_range_end": "",
            "default_vat_rate": 10,
            "trendyol_markup": 0,
            "company_info": {
                "company_name": "",
                "tax_office": "",
                "tax_number": "",
                "address": "",
                "city": "",
                "website": "",
                "phone": "",
                "email": ""
            }
        }
        await db.settings.insert_one(settings.copy())

    # Storefront kargo bilgisi (sabit kod yerine ayardan)
    cargo_fees = settings.get("cargo_fees") or {}
    default_company = settings.get("default_cargo_company") or ""
    fee = None
    if default_company and isinstance(cargo_fees, dict) and cargo_fees.get(default_company) not in (None, ""):
        try:
            fee = float(cargo_fees.get(default_company))
        except Exception:
            fee = None
    if fee is None:
        try:
            fee = float(settings.get("shipping_fee"))
        except Exception:
            fee = 0.0
    settings["shipping_fee"] = fee or 0.0
    # Ucretsiz kargo esigi -- aktif "otomatik" free_shipping kampanyalarindan (en dusuk min tutar)
    threshold = None
    try:
        async for _c in db.coupons.find({"is_active": True, "free_shipping": True, "auto_apply": True}, {"_id": 0, "min_cart_total": 1}):
            mc = _c.get("min_cart_total")
            if mc in (None, ""):
                continue
            mc = float(mc)
            if threshold is None or mc < threshold:
                threshold = mc
    except Exception:
        threshold = None
    settings["free_shipping_threshold"] = threshold

    return settings

@router.post("")
async def update_settings(
    settings_data: dict,
    current_user: dict = Depends(require_admin)
):
    """Update global settings"""
    settings_data.pop("_id", None)
    existing = await db.settings.find_one({"id": "main"})
    if not existing:
        settings_data["id"] = "main"
        await db.settings.insert_one(settings_data)
    else:
        await db.settings.update_one({"id": "main"}, {"$set": settings_data})
    
    return {"message": "Ayarlar güncellendi"}


# =============================================================================
# Ödeme Tipleri — Havale/EFT banka hesaplari + odeme entegrasyon ozeti
# Veri: db.settings._id="payment" { bank_accounts: [ {id,bank_name,branch,iban,
#       account_holder,is_default} ] }
# =============================================================================
import uuid as _uuid


def _seed_default_banks():
    return [{
        "id": _uuid.uuid4().hex[:12],
        "bank_name": "TÜRKİYE İŞ BANKASI",
        "branch": "CUMHURİYET CADDESİ ESENYURT ŞUBESİ",
        "iban": "TR86 0006 4000 0011 4540 1414 67",
        "account_holder": "FACETTE DIŞ TİC. A.Ş",
        "is_default": True,
    }]


def _ensure_single_default(banks):
    if banks and not any(b.get("is_default") for b in banks):
        banks[0]["is_default"] = True
    return banks


@router.get("/payment-overview")
async def payment_overview(current_user: dict = Depends(require_admin)):
    """Ödeme Tipleri sayfasi: aktif odeme entegrasyonlari + havale banka hesaplari."""
    pay = await db.settings.find_one({"id": "payment"}, {"_id": 0}) or {}
    banks = pay.get("bank_accounts") or []
    if not banks:
        banks = _seed_default_banks()
        await db.settings.update_one({"id": "payment"},
                                     {"$set": {"id": "payment", "bank_accounts": banks}}, upsert=True)
    iyz = await db.settings.find_one({"id": "iyzico"}, {"_id": 0}) or {}
    integrations = [{
        "key": "iyzico",
        "name": "iyzico (Kredi / Banka Kartı)",
        "configured": bool(iyz.get("api_key") and iyz.get("api_secret")),
        "active": bool(iyz.get("is_active")),
        "settings_path": "/admin/entegrasyonlar",
    }, {
        "key": "bank_transfer",
        "name": "Havale / EFT",
        "configured": bool(banks),
        "active": bool(banks),
        "settings_path": "/admin/odeme-tipleri",
    }]
    return {"integrations": integrations, "bank_accounts": banks}


@router.post("/bank-accounts")
async def upsert_bank_account(payload: Dict[str, Any], current_user: dict = Depends(require_admin)):
    pay = await db.settings.find_one({"id": "payment"}, {"_id": 0}) or {"id": "payment", "bank_accounts": []}
    banks = pay.get("bank_accounts") or []
    acc_id = str(payload.get("id") or "").strip() or _uuid.uuid4().hex[:12]
    acc = {
        "id": acc_id,
        "bank_name": str(payload.get("bank_name") or "").strip(),
        "branch": str(payload.get("branch") or "").strip(),
        "iban": str(payload.get("iban") or "").strip().upper(),
        "account_holder": str(payload.get("account_holder") or "").strip(),
        "is_default": bool(payload.get("is_default")),
    }
    if not acc["bank_name"] or not acc["iban"]:
        raise HTTPException(status_code=400, detail="Banka adı ve IBAN zorunlu")
    found = False
    for i, b in enumerate(banks):
        if b.get("id") == acc_id:
            banks[i] = acc
            found = True
            break
    if not found:
        banks.append(acc)
    if acc["is_default"]:
        for b in banks:
            b["is_default"] = (b.get("id") == acc_id)
    _ensure_single_default(banks)
    await db.settings.update_one({"id": "payment"},
                                 {"$set": {"id": "payment", "bank_accounts": banks}}, upsert=True)
    return {"bank_accounts": banks}


@router.delete("/bank-accounts/{acc_id}")
async def delete_bank_account(acc_id: str, current_user: dict = Depends(require_admin)):
    pay = await db.settings.find_one({"id": "payment"}, {"_id": 0}) or {}
    banks = [b for b in (pay.get("bank_accounts") or []) if b.get("id") != acc_id]
    _ensure_single_default(banks)
    await db.settings.update_one({"id": "payment"},
                                 {"$set": {"id": "payment", "bank_accounts": banks}}, upsert=True)
    return {"bank_accounts": banks}


@router.post("/bank-accounts/{acc_id}/default")
async def set_default_bank_account(acc_id: str, current_user: dict = Depends(require_admin)):
    pay = await db.settings.find_one({"id": "payment"}, {"_id": 0}) or {}
    banks = pay.get("bank_accounts") or []
    if not any(b.get("id") == acc_id for b in banks):
        raise HTTPException(status_code=404, detail="Hesap bulunamadı")
    for b in banks:
        b["is_default"] = (b.get("id") == acc_id)
    await db.settings.update_one({"id": "payment"},
                                 {"$set": {"id": "payment", "bank_accounts": banks}}, upsert=True)
    return {"bank_accounts": banks}



# =============================================================================
# Sipariş Durumları — sistemde görünür durumlar + durum başına SMS/Mail seçimi
# Veri: db.settings._id="order_status_config" { active:[key], notify:{key:{sms,email}} }
# =============================================================================
@router.get("/order-statuses")
async def get_order_statuses(current_user: dict = Depends(require_admin)):
    from order_statuses import ORDER_STATUS_CATALOG, get_status_config
    cfg = await get_status_config(db)
    out = []
    for s in ORDER_STATUS_CATALOG:
        nz = (cfg.get("notify") or {}).get(s["key"], {})
        out.append({
            "key": s["key"], "label": s["label"], "customer_label": s["customer_label"],
            "event": s["event"], "color": s["color"], "group": s["group"],
            "active": s["key"] in cfg.get("active", []),
            "sms": bool(nz.get("sms")), "email": bool(nz.get("email")),
        })
    return {"statuses": out}


@router.post("/order-statuses")
async def save_order_statuses(payload: Dict[str, Any], current_user: dict = Depends(require_admin)):
    from order_statuses import all_status_keys, CONFIG_ID
    valid = set(all_status_keys())
    active = [k for k in (payload.get("active") or []) if k in valid]
    notify_in = payload.get("notify") or {}
    notify = {}
    for k in valid:
        v = notify_in.get(k) or {}
        notify[k] = {"sms": bool(v.get("sms")), "email": bool(v.get("email"))}
    await db.settings.update_one(
        {"id": CONFIG_ID},
        {"$set": {"id": CONFIG_ID, "active": active, "notify": notify,
                  "templates_seeded": True,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"success": True, "active_count": len(active)}



@router.get("/public/bank-default")
async def public_default_bank():
    """Storefront (dekont sayfasi) icin varsayilan havale hesabi (public; IBAN zaten musteriyle paylasilir)."""
    pay = await db.settings.find_one({"id": "payment"}, {"_id": 0}) or {}
    banks = pay.get("bank_accounts") or []
    bank = next((b for b in banks if b.get("is_default")), None) or (banks[0] if banks else None)
    return {"bank": bank}


# =============================================================================
# Gönderici / Depo Adresi — kargo & iade etiketlerinde kullanılır (settings.store_info)
# =============================================================================
@router.get("/store-info")
async def get_store_info(current_user: dict = Depends(require_admin)):
    s = await db.settings.find_one({"id": "store_info"}, {"_id": 0}) or {}
    return {
        "sender_name": s.get("sender_name", ""),
        "sender_phone": s.get("sender_phone", ""),
        "sender_address": s.get("sender_address", ""),
        "sender_city": s.get("sender_city", ""),
        "sender_district": s.get("sender_district", ""),
        "sender_tax_no": s.get("sender_tax_no", ""),
    }


@router.post("/store-info")
async def save_store_info(payload: Dict[str, Any], current_user: dict = Depends(require_admin)):
    data = {
        "id": "store_info",
        "sender_name": str(payload.get("sender_name") or "").strip(),
        "sender_phone": str(payload.get("sender_phone") or "").strip(),
        "sender_address": str(payload.get("sender_address") or "").strip(),
        "sender_city": str(payload.get("sender_city") or "").strip(),
        "sender_district": str(payload.get("sender_district") or "").strip(),
        "sender_tax_no": str(payload.get("sender_tax_no") or "").strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.settings.update_one({"id": "store_info"}, {"$set": data}, upsert=True)
    return {"success": True}
