"""
=============================================================================
footer_template.py — Admin'in özelleştirebileceği HTML footer şablonu
=============================================================================
Footer tasarımını admin'in değiştirebilmesi için settings collection'ında
`id=footer` döküman tutulur. İki mod desteklenir:

  • HTML mode (basit):   custom_html alanına yazılan HTML render edilir.
  • Structured mode:     columns array'i ile sütun + link listesi yönetilir.

ENDPOINTS:
  GET  /api/footer-template            — Public (frontend Footer.jsx render için)
  PUT  /api/admin/footer-template      — Admin (HTML / columns güncelleme)
=============================================================================
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone

from .deps import db, require_admin

public_router = APIRouter(prefix="/footer-template", tags=["footer-public"])
admin_router = APIRouter(prefix="/admin/footer-template", tags=["footer-admin"])


_DEFAULT = {
    "id": "footer",
    "mode": "structured",  # "html" | "structured"
    "custom_html": "",
    "columns": [
        {
            "title": "Alışveriş",
            "links": [
                {"to": "/kategori/en-yeniler", "label": "En Yeniler"},
                {"to": "/kategori/elbise", "label": "Elbise"},
                {"to": "/kategori/pantolon", "label": "Pantolon"},
                {"to": "/kategori/ceket", "label": "Ceket"},
                {"to": "/kategori/aksesuar", "label": "Aksesuar"},
            ],
        },
        {
            "title": "Yardım",
            "links": [
                {"to": "/siparis-takip", "label": "Sipariş Takibi"},
                {"to": "/sayfa/uyelik-islemleri", "label": "Üyelik İşlemleri"},
                {"to": "/iade-islemleri", "label": "İade Talebi"},
                {"to": "/sayfa/iade-kosullari", "label": "İade İşlemleri"},
                {"to": "/sikca-sorulan-sorular", "label": "Sıkça Sorulan Sorular"},
                {"to": "/sayfa/iletisim", "label": "İletişim"},
            ],
        },
        {
            "title": "Kurumsal",
            "links": [
                {"to": "/sayfa/hakkimizda", "label": "Hakkımızda"},
                {"to": "/sayfa/mesafeli-satis", "label": "Mesafeli Satış Sözleşmesi"},
                {"to": "/sayfa/uyelik-sozlesmesi", "label": "Üyelik Sözleşmesi"},
                {"to": "/sayfa/kvkk", "label": "KVKK Aydınlatma Metni"},
                {"to": "/sayfa/gizlilik", "label": "Gizlilik Politikası"},
            ],
        },
        {
            "title": "İletişim",
            "static": [
                "info@facette.com.tr",
                "+90 543 330 03 10",
                "Pazartesi-Cumartesi 09:00 - 18:00",
            ],
        },
    ],
    "newsletter": {
        "title": "Facette Kulübü seni bekliyor",
        "description": "Yeni koleksiyonlar, özel kampanyalar ve sana özel fırsatlardan ilk sen haberdar ol.",
        "placeholder": "E-posta adresin",
    },
    "social": {
        "instagram": "https://instagram.com/facette",
        "facebook": "",
        "twitter": "",
    },
    "copyright": "© 2026 Facette. Tüm hakları saklıdır.",
}


@public_router.get("")
async def get_footer_template():
    """Frontend Footer.jsx için public endpoint."""
    doc = await db.settings.find_one({"id": "footer"}, {"_id": 0})
    return doc or _DEFAULT


@admin_router.get("")
async def admin_get_footer_template(current_user: dict = Depends(require_admin)):
    """Admin (yönetim için)."""
    doc = await db.settings.find_one({"id": "footer"}, {"_id": 0})
    return doc or _DEFAULT


@admin_router.put("")
async def admin_update_footer_template(
    payload: dict,
    current_user: dict = Depends(require_admin)
):
    """Footer şablonunu güncelle (whitelist)."""
    allowed = {"mode", "custom_html", "columns", "newsletter", "social", "copyright"}
    update = {k: v for k, v in (payload or {}).items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.settings.update_one(
        {"id": "footer"},
        {"$set": update, "$setOnInsert": {"id": "footer"}},
        upsert=True,
    )
    return {"success": True, "message": "Footer şablonu güncellendi"}


@public_router.post("/_diag/patch_labels2907")
async def _diag_patch_labels2907(payload: dict):
    """GEÇİCİ (key-korumalı) — kayıtlı footer'daki link etiketlerini `to`ya göre yamalar.
    Kod default'u kayıtlı footer'ı ezemediğinden gerekli. Kullanımdan sonra KALDIRILACAK.
    payload: {key, map: {"/iade-islemleri": "İade Talebi", ...}}"""
    if (payload or {}).get("key") != "fcttdiag2907":
        raise HTTPException(status_code=403, detail="forbidden")
    label_map = (payload or {}).get("map") or {}
    doc = await db.settings.find_one({"id": "footer"}, {"_id": 0})
    if not doc or not doc.get("columns"):
        return {"ok": False, "reason": "kayıtlı footer yok (kod default kullanılıyor)"}
    changed = []
    cols = doc.get("columns") or []
    for c in cols:
        for l in (c.get("links") or []):
            to = l.get("to")
            if to in label_map and l.get("label") != label_map[to]:
                changed.append({"to": to, "old": l.get("label"), "new": label_map[to]})
                l["label"] = label_map[to]
    await db.settings.update_one({"id": "footer"}, {"$set": {"columns": cols, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": True, "changed": changed}


@admin_router.post("/reset-default")
async def reset_footer_default(current_user: dict = Depends(require_admin)):
    """Footer'ı varsayılan değerlere döndür."""
    await db.settings.update_one(
        {"id": "footer"},
        {"$set": {**_DEFAULT, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"success": True, "message": "Footer varsayılana sıfırlandı"}
