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


# NOTE: options + bulk-delete + reset-all, generic /{category_id} route'larından
# ÖNCE tanımlanır; aksi takdirde FastAPI "bulk-delete"/"options" path segment'ini
# category_id olarak yakalayıp yanlış handler'a yönlendirir.
@router.get("/{marketplace}/options")
async def search_marketplace_categories(
    marketplace: str,
    q: str = "",
    limit: int = 100,
    current_user: dict = Depends(require_admin),
):
    """Pazaryeri kategori ağacından arama. Şu an Trendyol cache'i destekli
    (trendyol_categories — subCategories düzleştirilir)."""
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    if marketplace != "trendyol":
        return {"items": [], "hint": f"{marketplace} için kategori cache yok, manuel ID girin"}
    q_ = (q or "").strip().lower()
    flat = []
    def _walk(nodes, path_prefix=""):
        for n in nodes or []:
            name = n.get("name", "")
            full_path = f"{path_prefix} > {name}" if path_prefix else name
            flat.append({
                "id": n.get("id"),
                "name": name,
                "full_path": full_path,
                "parent_id": n.get("parentId"),
                "leaf": not bool(n.get("subCategories")),
            })
            _walk(n.get("subCategories") or [], full_path)

    async for top in db.trendyol_categories.find({}, {"_id": 0}):
        _walk([top])

    if q_:
        flat = [c for c in flat if q_ in (c["name"] + " " + c["full_path"]).lower()]
    return {"items": flat[: max(1, min(500, int(limit)))], "count": len(flat)}


@router.post("/{marketplace}/bulk-delete")
async def bulk_delete_category_mappings(
    marketplace: str,
    payload: dict,
    current_user: dict = Depends(require_admin),
):
    """Seçili kategori eşleşmelerini toplu sil. Body: {category_ids: [...]}."""
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    ids = (payload or {}).get("category_ids") or []
    if not ids:
        return {"success": True, "deleted": 0}
    res = await db.category_mappings.delete_many({
        "marketplace": marketplace,
        "category_id": {"$in": ids},
    })
    return {"success": True, "deleted": res.deleted_count}


@router.post("/{marketplace}/reset-all")
async def reset_all(marketplace: str, current_user: dict = Depends(require_admin)):
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    res = await db.category_mappings.delete_many({"marketplace": marketplace})
    return {"success": True, "deleted": res.deleted_count}


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


# ---------------------------------------------------------------------------
# GELİŞMİŞ EŞLEŞTİRME (tüm pazaryerleri için generic)
# ---------------------------------------------------------------------------
# `/category-mapping/{mp}/{local_cat_id}/attributes`     → MP'nin bu kategori için
#                                                         zorunlu/opsiyonel özellikleri
# `/category-mapping/{mp}/{local_cat_id}/attribute-map`  → attribute mapping kaydet
# `/category-mapping/{mp}/{local_cat_id}/values`         → sistem ürünlerindeki distinct
#                                                         değerler + mapping
# `/category-mapping/{mp}/{local_cat_id}/value-map`      → değer mapping kaydet
#
# Trendyol için gerçek Trendyol API'lerinden veri çekilir (cache DB'de).
# Diğer pazaryerleri için placeholder veri + hint döner — kullanıcı manuel girebilir,
# ileride her MP için benzer API entegrasyonu yapılır.


@router.get("/{marketplace}/{local_category_id}/attributes")
async def get_advanced_attributes(
    marketplace: str,
    local_category_id: str,
    current_user: dict = Depends(require_admin),
):
    """Sistem kategorisinin MP'deki karşılığı için zorunlu/opsiyonel özellikler."""
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    mapping = await db.category_mappings.find_one(
        {"category_id": local_category_id, "marketplace": marketplace}, {"_id": 0}
    )
    if not mapping or not mapping.get("marketplace_category_id"):
        return {
            "attributes": [],
            "attribute_mappings": [],
            "default_mappings": {},
            "hint": "Önce sistem kategorisini pazaryeri kategorisiyle eşleştirin",
        }
    mp_cat_id = mapping["marketplace_category_id"]

    # Trendyol için gerçek attribute listesini Trendyol API'sinden çek
    if marketplace == "trendyol":
        try:
            from .integrations import get_trendyol_config
            from trendyol_client import TrendyolClient
            cfg = await get_trendyol_config()
            if cfg.get("is_active") and cfg.get("api_key"):
                client = TrendyolClient(
                    supplier_id=cfg["supplier_id"],
                    api_key=cfg["api_key"],
                    api_secret=cfg["api_secret"],
                    mode=cfg.get("mode", "sandbox"),
                )
                data = await client.get_category_attributes(int(mp_cat_id))
                attrs = data.get("categoryAttributes") or data.get("attributes") or []
                # Cache'le
                await db.trendyol_category_attributes.update_one(
                    {"category_id": int(mp_cat_id)},
                    {"$set": {"category_id": int(mp_cat_id), "attributes": attrs,
                              "updated_at": datetime.now(timezone.utc).isoformat()}},
                    upsert=True,
                )
                return {
                    "attributes": attrs,
                    "attribute_mappings": mapping.get("attribute_mappings", []),
                    "default_mappings": mapping.get("default_mappings", {}),
                    "value_mappings": mapping.get("value_mappings", {}),
                }
        except Exception:
            # DB cache'den dene
            pass
        cached = await db.trendyol_category_attributes.find_one(
            {"category_id": int(mp_cat_id)}, {"_id": 0}
        )
        return {
            "attributes": (cached or {}).get("attributes", []),
            "attribute_mappings": mapping.get("attribute_mappings", []),
            "default_mappings": mapping.get("default_mappings", {}),
            "value_mappings": mapping.get("value_mappings", {}),
            "from_cache": bool(cached),
        }

    # Diğer MP'ler — yerel cache (varsa) veya boş + hint
    coll_name = f"{marketplace}_category_attributes"
    cached = await db[coll_name].find_one({"category_id": str(mp_cat_id)}, {"_id": 0})
    return {
        "attributes": (cached or {}).get("attributes", []),
        "attribute_mappings": mapping.get("attribute_mappings", []),
        "default_mappings": mapping.get("default_mappings", {}),
        "value_mappings": mapping.get("value_mappings", {}),
        "hint": f"{marketplace} için canlı attribute listesi henüz entegre değil — manuel ad-ad eşleştirebilir veya Trendyol'daki ortak attribute'ları kullanabilirsiniz",
    }


@router.post("/{marketplace}/{local_category_id}/attribute-map")
async def save_attribute_mappings(
    marketplace: str,
    local_category_id: str,
    payload: dict,
    current_user: dict = Depends(require_admin),
):
    """Body: {attribute_mappings: [{local_attr, mp_attr_id}], default_mappings: {}}"""
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    update = {}
    if "attribute_mappings" in payload:
        update["attribute_mappings"] = payload["attribute_mappings"] or []
    if "default_mappings" in payload:
        update["default_mappings"] = payload["default_mappings"] or {}
    if "value_mappings" in payload:
        update["value_mappings"] = payload["value_mappings"] or {}
    if not update:
        return {"success": True, "message": "Güncellenecek alan yok"}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.category_mappings.update_one(
        {"category_id": local_category_id, "marketplace": marketplace},
        {"$set": update},
    )
    return {"success": True, "message": "Özellik eşleştirmesi kaydedildi"}


@router.get("/{marketplace}/{local_category_id}/values")
async def get_advanced_values(
    marketplace: str,
    local_category_id: str,
    current_user: dict = Depends(require_admin),
):
    """Bu sistem kategorisindeki ürünlerin attribute değerleri (distinct)."""
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    # Ürünlerden distinct attribute değerlerini topla
    local_values = {}
    cursor = db.products.find(
        {"category_id": local_category_id}, {"_id": 0, "attributes": 1, "variants": 1}
    )
    async for p in cursor:
        # üst seviye attributes: {name, value}
        for a in p.get("attributes", []) or []:
            nm = a.get("name") or a.get("attribute_name")
            vv = a.get("value") or a.get("attribute_value")
            if not nm or not vv:
                continue
            local_values.setdefault(nm, set()).add(str(vv))
        for v in p.get("variants", []) or []:
            for a in v.get("attributes", []) or []:
                nm = a.get("name") or a.get("attribute_name")
                vv = a.get("value") or a.get("attribute_value")
                if not nm or not vv:
                    continue
                local_values.setdefault(nm, set()).add(str(vv))

    out = {k: sorted(list(v)) for k, v in local_values.items()}
    mapping = await db.category_mappings.find_one(
        {"category_id": local_category_id, "marketplace": marketplace}, {"_id": 0}
    ) or {}
    return {
        "local_values": out,
        "value_mappings": mapping.get("value_mappings", {}),
    }
