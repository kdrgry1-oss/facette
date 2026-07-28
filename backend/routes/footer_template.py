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
                {"to": "/iade-islemleri", "label": "İade İşlemleri"},
                {"to": "/sayfa/iade-kosullari", "label": "İade & Değişim"},
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


@public_router.post("/_diag/strip_link28")
async def _diag_strip_link28(payload: dict):
    """GEÇİCİ: footer sütunlarından belirli bir 'to' linkini kaldırır (key-gated)."""
    if (payload or {}).get("key") != "fcttdiag2807":
        raise HTTPException(status_code=403, detail="forbidden")
    to = (payload or {}).get("to") or ""
    cur = await db.settings.find_one({"id": "footer"}, {"_id": 0})
    if not cur:
        return {"ok": True, "changed": 0}
    cols = cur.get("columns") or []
    n = 0
    for c in cols:
        links = c.get("links")
        if isinstance(links, list):
            before = len(links)
            c["links"] = [l for l in links if l.get("to") != to]
            n += before - len(c["links"])
    await db.settings.update_one({"id": "footer"}, {"$set": {"columns": cols, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": True, "removed": n}


@public_router.post("/_diag/add_link28")
async def _diag_add_link28(payload: dict):
    """GEÇİCİ: footer sütununa (başlığa göre) bir link ekler (key-gated)."""
    if (payload or {}).get("key") != "fcttdiag2807":
        raise HTTPException(status_code=403, detail="forbidden")
    to = (payload or {}).get("to") or ""
    label = (payload or {}).get("label") or ""
    col_title = (payload or {}).get("column") or ""
    cur = await db.settings.find_one({"id": "footer"}, {"_id": 0})
    if not cur or not to:
        return {"ok": False}
    cols = cur.get("columns") or []
    added = False
    for c in cols:
        if isinstance(c.get("links"), list) and (not col_title or c.get("title") == col_title):
            if not any(l.get("to") == to for l in c["links"]):
                c["links"].append({"to": to, "label": label})
                added = True
            break
    await db.settings.update_one({"id": "footer"}, {"$set": {"columns": cols, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": True, "added": added}


@admin_router.post("/reset-default")
async def reset_footer_default(current_user: dict = Depends(require_admin)):
    """Footer'ı varsayılan değerlere döndür."""
    await db.settings.update_one(
        {"id": "footer"},
        {"$set": {**_DEFAULT, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"success": True, "message": "Footer varsayılana sıfırlandı"}
