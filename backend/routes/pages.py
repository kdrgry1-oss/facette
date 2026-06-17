"""
İçerik sayfaları (Hakkımızda, KVKK, İade, SSS, Mesafeli Satış, vb.) — Footer/Header/Checkout linkleri.
db.pages koleksiyonu. Public: GET /pages/{slug} (StaticPage.jsx). Admin: liste/ekle/güncelle/sil + seed.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone

from .deps import db, logger, require_admin, generate_id

router = APIRouter(prefix="/pages", tags=["Pages"])


@router.get("")
async def list_pages(current_user: dict = Depends(require_admin)):
    """Admin: tüm içerik sayfaları (aktif/pasif dahil)."""
    rows = await db.pages.find({}, {"_id": 0}).sort("title", 1).to_list(500)
    return rows


@router.post("/seed-defaults")
async def seed_default_pages(force: bool = False, current_user: dict = Depends(require_admin)):
    """FACETTE varsayılan içerik sayfalarını yükler (Hakkımızda, KVKK, İade, SSS, Gizlilik,
    Mesafeli Satış, Ön Bilgilendirme, İletişim).
    force=false (varsayılan): yalnızca eksik slug'ları ekler, mevcut içeriği KORUR.
    force=true: tüm varsayılan sayfaların içeriğini yeniden yazar (üzerine yazar).
    """
    try:
        from page_seed_data import FACETTE_DEFAULT_PAGES
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Seed verisi yüklenemedi: {e}")
    created, updated, skipped = [], [], []
    now = datetime.now(timezone.utc).isoformat()
    for p in FACETTE_DEFAULT_PAGES:
        existing = await db.pages.find_one({"slug": p["slug"]})
        doc = {
            "title": p["title"], "slug": p["slug"], "content": p["content"],
            "meta_title": p.get("meta_title", ""), "meta_description": p.get("meta_description", ""),
            "is_active": True, "updated_at": now,
        }
        if existing:
            if force:
                await db.pages.update_one({"slug": p["slug"]}, {"$set": doc})
                updated.append(p["slug"])
            else:
                skipped.append(p["slug"])
        else:
            doc["id"] = generate_id()
            doc["created_at"] = now
            await db.pages.insert_one(doc)
            created.append(p["slug"])
    return {
        "ok": True, "created": created, "updated": updated, "skipped": skipped,
        "message": f"{len(created)} eklendi, {len(updated)} güncellendi, {len(skipped)} atlandı",
    }


@router.get("/{slug}")
async def get_page(slug: str):
    """Public: slug (veya id) ile aktif içerik sayfası. StaticPage.jsx kullanır."""
    page = await db.pages.find_one(
        {"$or": [{"slug": slug}, {"id": slug}], "is_active": {"$ne": False}},
        {"_id": 0},
    )
    if not page:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadı")
    return page


@router.post("")
async def create_page(payload: dict, current_user: dict = Depends(require_admin)):
    slug = (payload.get("slug") or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="slug zorunlu")
    if await db.pages.find_one({"slug": slug}):
        raise HTTPException(status_code=400, detail="Bu slug zaten kullanılıyor")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": generate_id(), "title": payload.get("title", ""), "slug": slug,
        "content": payload.get("content", ""), "meta_title": payload.get("meta_title", ""),
        "meta_description": payload.get("meta_description", ""),
        "is_active": payload.get("is_active", True),
        "created_at": now, "updated_at": now,
    }
    await db.pages.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{page_id}")
async def update_page(page_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    existing = await db.pages.find_one({"$or": [{"id": page_id}, {"slug": page_id}]})
    if not existing:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadı")
    allowed = ("title", "slug", "content", "meta_title", "meta_description", "is_active")
    update_set = {k: payload[k] for k in allowed if k in payload}
    update_set["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.pages.update_one({"id": existing["id"]}, {"$set": update_set})
    return {"ok": True}


@router.delete("/{page_id}")
async def delete_page(page_id: str, current_user: dict = Depends(require_admin)):
    res = await db.pages.delete_one({"$or": [{"id": page_id}, {"slug": page_id}]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadı")
    return {"ok": True}
