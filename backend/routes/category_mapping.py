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


@router.post("/{marketplace}/bulk-auto-match-attributes")
async def bulk_auto_match_attributes(
    marketplace: str,
    current_user: dict = Depends(require_admin),
):
    """
    Bu MP için matched durumundaki TÜM sistem kategorilerine
    otomatik attribute eşleştirme uygular.

    Algoritma:
      1) Global attributes (sistem) bir kez çekilir.
      2) Her matched kategori için MP attribute'ları alınır.
      3) İsim eşleştirmesi (exact / contains / yaygın alias: color↔renk, size↔beden) uygulanır.
      4) Kullanıcının MANUEL yaptığı eşleştirmeler EZİLMEZ — yalnızca boş olanlara eklenir.

    Rapor formatı:
      {
        marketplace, total_categories, processed, skipped_no_mp_cat,
        total_new_mappings, details: [{category_id, category_name, new:int, total_mp_attrs:int, fetched:bool}]
      }
    """
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")

    # 1) Global attributes — sistemdeki tüm tanımlı özellikler
    global_attrs = await db.attributes.find({}, {"_id": 0}).to_list(length=2000)

    def _match_global(mp_name: str) -> str | None:
        nm = (mp_name or "").lower().strip()
        if not nm:
            return None
        for ga in global_attrs:
            gn = (ga.get("name") or "").lower().strip()
            if not gn:
                continue
            if gn == nm or nm in gn or gn in nm:
                return ga.get("name")
            if (nm in ("color", "web color", "renk") and gn == "renk") or \
               (nm in ("size", "beden") and gn == "beden"):
                return ga.get("name")
        return None

    # 2) Trendyol için canlı probe hazırlığı
    tr_client = None
    if marketplace == "trendyol":
        try:
            from .integrations import get_trendyol_config
            from trendyol_client import TrendyolClient
            cfg = await get_trendyol_config()
            if cfg.get("is_active") and cfg.get("api_key"):
                tr_client = TrendyolClient(
                    supplier_id=cfg["supplier_id"],
                    api_key=cfg["api_key"],
                    api_secret=cfg["api_secret"],
                    mode=cfg.get("mode", "sandbox"),
                )
        except Exception:
            tr_client = None

    # 3) Matched kategorileri sırayla dolaş
    matched_cats = await db.category_mappings.find(
        {"marketplace": marketplace, "marketplace_category_id": {"$nin": [None, ""]}},
        {"_id": 0}
    ).to_list(length=3000)

    now = datetime.now(timezone.utc).isoformat()
    details = []
    total_new = 0
    processed = 0
    skipped = 0

    for cm in matched_cats:
        cid = cm.get("category_id")
        cname = cm.get("category_name", "")
        mp_cat_id = cm.get("marketplace_category_id")
        if not mp_cat_id:
            skipped += 1
            continue
        processed += 1

        # MP attr listesini al — Trendyol canlı + cache, diğerleri cache
        mp_attrs = []
        fetched_live = False
        if marketplace == "trendyol" and tr_client:
            try:
                data = await tr_client.get_category_attributes(int(mp_cat_id))
                mp_attrs = data.get("categoryAttributes") or data.get("attributes") or []
                await db.trendyol_category_attributes.update_one(
                    {"category_id": int(mp_cat_id)},
                    {"$set": {"category_id": int(mp_cat_id), "attributes": mp_attrs, "updated_at": now}},
                    upsert=True,
                )
                fetched_live = True
            except Exception:
                mp_attrs = []
        if not mp_attrs:
            coll = "trendyol_category_attributes" if marketplace == "trendyol" else f"{marketplace}_category_attributes"
            try:
                cached = await db[coll].find_one(
                    {"category_id": int(mp_cat_id) if str(mp_cat_id).isdigit() else str(mp_cat_id)},
                    {"_id": 0}
                )
                mp_attrs = (cached or {}).get("attributes", [])
            except Exception:
                mp_attrs = []

        if not mp_attrs:
            details.append({
                "category_id": cid, "category_name": cname,
                "new": 0, "total_mp_attrs": 0, "fetched": False,
                "note": "MP attribute listesi boş (cache ya da canlı alınamadı)",
            })
            continue

        # Eski mapping'ler — ezilmesin
        existing = cm.get("attribute_mappings", []) or []
        existing_ids = {str(m.get("mp_attr_id") or m.get("trendyol_attr_id")) for m in existing}
        new_mappings = list(existing)
        matched_now = 0

        for a in mp_attrs:
            mp_attr_id = str(a.get("id") or a.get("attribute", {}).get("id") or "")
            if not mp_attr_id or mp_attr_id in existing_ids:
                continue
            mp_attr_name = a.get("name") or a.get("attribute", {}).get("name") or ""
            local = _match_global(mp_attr_name)
            if local:
                new_mappings.append({
                    "local_attr": local,
                    "mp_attr_id": int(mp_attr_id) if mp_attr_id.isdigit() else mp_attr_id,
                })
                matched_now += 1

        if matched_now:
            await db.category_mappings.update_one(
                {"category_id": cid, "marketplace": marketplace},
                {"$set": {"attribute_mappings": new_mappings, "updated_at": now}},
            )
            total_new += matched_now

        details.append({
            "category_id": cid, "category_name": cname,
            "new": matched_now, "total_mp_attrs": len(mp_attrs), "fetched": fetched_live,
        })

    return {
        "success": True,
        "marketplace": marketplace,
        "total_categories": len(matched_cats),
        "processed": processed,
        "skipped_no_mp_cat": skipped,
        "total_new_mappings": total_new,
        "details": details,
        "message": (
            f"{processed} kategori işlendi, toplam {total_new} yeni özellik eşleşti"
            if processed else "Eşleştirilecek matched kategori bulunamadı"
        ),
    }


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
    """Bu sistem kategorisindeki ürünlerin attribute değerleri (distinct) +
    sistemdeki global attribute değerleri de birleştirilerek döner.
    Böylece eşleştirme ekranında "Ürünlerde bu kategoride renk kullanılmamış"
    olsa bile global attributes (ör. Renk → Kırmızı/Mavi) görünür.
    """
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")

    # 1) Bu kategorideki ürünlerden distinct attribute değerlerini topla
    local_values = {}
    cursor = db.products.find(
        {"category_id": local_category_id}, {"_id": 0, "attributes": 1, "variants": 1}
    )
    async for p in cursor:
        for a in p.get("attributes", []) or []:
            nm = a.get("name") or a.get("type") or a.get("attribute_name")
            vv = a.get("value") or a.get("attribute_value")
            if not nm or not vv:
                continue
            local_values.setdefault(nm, set()).add(str(vv))
        for v in p.get("variants", []) or []:
            for a in v.get("attributes", []) or []:
                nm = a.get("name") or a.get("type") or a.get("attribute_name")
                vv = a.get("value") or a.get("attribute_value")
                if not nm or not vv:
                    continue
                local_values.setdefault(nm, set()).add(str(vv))

    # 2) Global /api/attributes içerisindeki tüm değerleri de birleştir
    async for ga in db.attributes.find({}, {"_id": 0, "name": 1, "values": 1}):
        nm = (ga.get("name") or "").strip()
        if not nm:
            continue
        for val in ga.get("values", []) or []:
            sv = str(val).strip()
            if sv:
                local_values.setdefault(nm, set()).add(sv)

    out = {k: sorted(list(v)) for k, v in local_values.items()}
    mapping = await db.category_mappings.find_one(
        {"category_id": local_category_id, "marketplace": marketplace}, {"_id": 0}
    ) or {}
    return {
        "local_values": out,
        "value_mappings": mapping.get("value_mappings", {}),
    }
