"""
=============================================================================
category_mapping.py — Multi-Marketplace Kategori Eşleştirme
=============================================================================

AMAÇ:
  Sistem kategorilerini her pazaryerinin kendi kategori ağacıyla eşleştirmek.
  Ticimax "Kategori İşlemleri" ekranı mantığıyla ama çoklu-pazaryeri.

MODEL (`category_mappings` collection):
  {
    "category_id": "<sistem kat id>",
    "category_name": "Elbise > Mini Elbise",
    "marketplace": "trendyol",
    "marketplace_category_id": "1234",
    "marketplace_category_name": "Kadın > Giyim > Mini Elbise",
    "status": "matched" | "unmatched",
    "updated_at": "..."
  }

KULLANAN FRONTEND:
  /app/frontend/src/pages/admin/CategoryMapping.jsx
=============================================================================
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone

from .deps import db, require_admin

router = APIRouter(prefix="/category-mapping", tags=["Category Mapping"])

MARKETPLACES = ["trendyol", "hepsiburada", "temu", "n11", "amazon-tr",
                "amazon-de", "aliexpress", "etsy", "hepsi-global",
                "fruugo", "emag", "trendyol-ihracat", "ciceksepeti"]


@router.get("/{marketplace}")
async def list_mappings(marketplace: str, current_user: dict = Depends(require_admin)):
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    cats = await db.categories.find({}, {"_id": 0}).to_list(length=2000)
    mappings = await db.category_mappings.find({"marketplace": marketplace}, {"_id": 0}).to_list(length=3000)
    mp_map = {m.get("category_id"): m for m in mappings}
    rows = []
    for c in cats:
        cid = c.get("id") or c.get("_id")
        m = mp_map.get(cid) or {}
        rows.append({
            "category_id": cid,
            "category_name": c.get("name", ""),
            "parent_name": c.get("parent_name") or "",
            "marketplace_category_id": m.get("marketplace_category_id"),
            "marketplace_category_name": m.get("marketplace_category_name"),
            "status": m.get("status") or ("matched" if m.get("marketplace_category_id") else "unmatched"),
            "updated_at": m.get("updated_at"),
        })
    matched = sum(1 for r in rows if r["status"] == "matched")
    return {"marketplace": marketplace, "total": len(rows),
            "matched": matched, "unmatched": len(rows) - matched, "items": rows}


@router.post("/{marketplace}/{category_id}")
async def set_mapping(marketplace: str, category_id: str, payload: dict,
                       current_user: dict = Depends(require_admin)):
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    cat = await db.categories.find_one({"id": category_id}, {"_id": 0})
    if not cat:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "category_id": category_id,
        "category_name": cat.get("name", ""),
        "marketplace": marketplace,
        "marketplace_category_id": (payload or {}).get("marketplace_category_id"),
        "marketplace_category_name": (payload or {}).get("marketplace_category_name"),
        "status": "matched",
        "updated_at": now,
        "updated_by": current_user.get("email"),
    }
    await db.category_mappings.update_one(
        {"category_id": category_id, "marketplace": marketplace},
        {"$set": doc}, upsert=True
    )
    return {"success": True, "mapping": doc}


@router.delete("/{marketplace}/{category_id}")
async def clear_mapping(marketplace: str, category_id: str,
                         current_user: dict = Depends(require_admin)):
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    await db.category_mappings.delete_one({"category_id": category_id, "marketplace": marketplace})
    return {"success": True}


@router.post("/{marketplace}/reset-all")
async def reset_all(marketplace: str, current_user: dict = Depends(require_admin)):
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    res = await db.category_mappings.delete_many({"marketplace": marketplace})
    return {"success": True, "deleted": res.deleted_count}
