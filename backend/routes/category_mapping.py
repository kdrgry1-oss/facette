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
import asyncio
import re as _re

from .deps import db, require_admin

router = APIRouter(prefix="/category-mapping", tags=["Category Mapping"])

MARKETPLACES = ["trendyol", "hepsiburada", "temu", "n11", "amazon-tr",
                "amazon-de", "aliexpress", "etsy", "hepsi-global",
                "fruugo", "emag", "trendyol-ihracat", "ciceksepeti"]


@router.get("/{marketplace}")
async def list_mappings(
    marketplace: str,
    show_excluded: bool = False,
    current_user: dict = Depends(require_admin),
):
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    # Hariç tutulanları filtrele (kullanıcı "Sil" tıkladığı kategoriler)
    if show_excluded:
        cats = await db.categories.find({}, {"_id": 0}).to_list(length=2000)
    else:
        cats = await db.categories.find(
            {"excluded_marketplaces": {"$ne": marketplace}},
            {"_id": 0},
        ).to_list(length=2000)
    mappings = await db.category_mappings.find({"marketplace": marketplace}, {"_id": 0}).to_list(length=3000)
    mp_map = {m.get("category_id"): m for m in mappings}

    # Tüm kategorileri indeksle (path oluşturma için TÜM listeyi al, excluded olsa bile)
    all_cats = await db.categories.find({}, {"_id": 0, "id": 1, "name": 1, "parent_id": 1}).to_list(length=5000)
    by_id = {str(c.get("id")): c for c in all_cats}

    def full_path(cat_id: str, max_depth: int = 8) -> str:
        parts = []
        seen = set()
        cur = by_id.get(str(cat_id))
        depth = 0
        while cur and depth < max_depth and cur.get("id") not in seen:
            seen.add(cur.get("id"))
            parts.insert(0, cur.get("name", ""))
            pid = cur.get("parent_id")
            if not pid:
                break
            cur = by_id.get(str(pid))
            depth += 1
        return " / ".join([p for p in parts if p])

    rows = []
    for c in cats:
        cid = c.get("id") or c.get("_id")
        m = mp_map.get(cid) or {}
        path = full_path(cid)
        rows.append({
            "category_id": cid,
            "category_name": c.get("name", ""),
            "category_path": path or c.get("name", ""),
            "parent_name": c.get("parent_name") or "",
            "marketplace_category_id": m.get("marketplace_category_id"),
            "marketplace_category_name": m.get("marketplace_category_name"),
            "status": m.get("status") or ("matched" if m.get("marketplace_category_id") else "unmatched"),
            "excluded": marketplace in (c.get("excluded_marketplaces") or []),
            "updated_at": m.get("updated_at"),
        })
    matched = sum(1 for r in rows if r["status"] == "matched")
    excluded_count = sum(1 for r in rows if r["excluded"])
    return {"marketplace": marketplace, "total": len(rows),
            "matched": matched, "unmatched": len(rows) - matched,
            "excluded": excluded_count, "items": rows}


# NOTE: options + bulk-delete + reset-all, generic /{category_id} route'larından
# ÖNCE tanımlanır; aksi takdirde FastAPI "bulk-delete"/"options" path segment'ini
# category_id olarak yakalayıp yanlış handler'a yönlendirir.
def _tr_lower(s: str) -> str:
    """Türkçe-uyumlu lowercase (İ→i, I→ı)."""
    if not s:
        return ""
    return (
        s.replace("İ", "i")
         .replace("I", "ı")
         .replace("Ş", "ş")
         .replace("Ğ", "ğ")
         .replace("Ü", "ü")
         .replace("Ö", "ö")
         .replace("Ç", "ç")
         .lower()
    )


_hb_sync_lock = asyncio.Lock()


async def _get_hb_client():
    """Hepsiburada kimligini once Pazaryerleri Yonetimi (marketplace_accounts),
    yoksa eski db.settings'ten okur. Ortam: env/mode 'prod/production/canli' degilse sandbox."""
    # 1) Birincil: marketplace_accounts.credentials (Pazaryerleri Yonetimi ekrani)
    acc = await db.marketplace_accounts.find_one({"key": "hepsiburada"}, {"_id": 0})
    cr = (acc or {}).get("credentials") or {}
    mid = (cr.get("merchant_id") or "").strip()
    sk = (cr.get("secret_key") or cr.get("password") or "").strip()
    du = (cr.get("dev_username") or "").strip()
    env = (cr.get("env") or cr.get("mode") or "").strip().lower()
    # 2) Yedek: eski db.settings (Entegrasyonlar modali). Kimlik VE ortam icin tamamlayici.
    s = None
    if not (mid and sk and du) or not env:
        s = await db.settings.find_one({"id": "hepsiburada"}, {"_id": 0}) or {}
        mid = mid or (s.get("merchant_id") or "").strip()
        sk = sk or (s.get("secret_key") or s.get("password") or "").strip()
        du = du or (s.get("dev_username") or "").strip()
        env = env or (s.get("mode") or "").strip().lower()
    if not (mid and sk and du):
        return None, "Hepsiburada kimlik bilgileri eksik (Merchant ID / Secret Key / Developer Username). Entegrasyonlar → Hepsiburada altından kaydedin."
    # Opsiyonel: OMS (siparis) icin AYRI Basic auth kimligi (varsa). Once marketplace_accounts, sonra db.settings.
    oms_u = (cr.get("oms_username") or "").strip()
    oms_p = (cr.get("oms_password") or "").strip()
    if (not oms_u or not oms_p):
        if s is None:
            s = await db.settings.find_one({"id": "hepsiburada"}, {"_id": 0}) or {}
        oms_u = oms_u or (s.get("oms_username") or "").strip()
        oms_p = oms_p or (s.get("oms_password") or "").strip()
    test = env not in ("prod", "production", "live", "canli", "canlı")
    from hepsiburada_client import HepsiburadaClient
    return HepsiburadaClient(mid, sk, du, test=test, oms_username=oms_u, oms_password=oms_p), None


async def _fetch_hb_category_attributes(mp_cat_id, with_values=True):
    """HB kategori ozelliklerini canli ceker, frontend formatina normalize eder, cache'ler.
    Normalize: {id, name, required, multiValue, type, allowCustom, attributeValues:[{id,name}]}.
    Enum ozellikler icin gecerli degerleri (iter_attribute_values) da doldurur.
    Doner: (attrs_list, error)."""
    client, err = await _get_hb_client()
    if err:
        return [], err
    cid = int(mp_cat_id) if str(mp_cat_id).isdigit() else mp_cat_id
    try:
        data = await asyncio.to_thread(client.get_category_attributes, cid)
    except Exception as e:
        return [], f"HB özellik çekme hatası: {e}"
    cat_attrs = (data or {}).get("attributes", []) or []
    out = []
    media_attrs = []
    for a in cat_attrs:
        atype = (a.get("type") or "").lower()
        # media (gorsel) tipli alanlar urun gonderiminde urun gorsellerinden doldurulur;
        # metin/yerel-ozellik eslestirmesi yapilmaz -> mapping listesine alinmaz, ayri saklanir.
        if atype == "media":
            media_attrs.append({"id": a.get("id"), "name": a.get("name"),
                                "required": bool(a.get("mandatory")), "type": a.get("type")})
            continue
        norm = {
            "id": a.get("id"),
            "name": a.get("name"),
            "required": bool(a.get("mandatory")),
            "multiValue": bool(a.get("multiValue")),
            "type": a.get("type"),
            "allowCustom": atype != "enum",
            "attributeValues": [],
        }
        if with_values and atype == "enum":
            try:
                vals = await asyncio.to_thread(client.iter_attribute_values, cid, a.get("id"))
                norm["attributeValues"] = [{"id": v.get("id"), "name": v.get("value")}
                                           for v in (vals or []) if isinstance(v, dict)]
            except Exception:
                norm["attributeValues"] = []
        out.append(norm)
    try:
        key = int(mp_cat_id) if str(mp_cat_id).isdigit() else str(mp_cat_id)
        await db.hepsiburada_category_attributes.update_one(
            {"category_id": key},
            {"$set": {"category_id": key, "attributes": out, "_v": 2,
                      "media_attributes": media_attrs,
                      "base_attributes": (data or {}).get("baseAttributes", []),
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    except Exception:
        pass
    return out, None


async def _sync_hb_categories(force=False):
    """leaf+active+available HB kategorilerini db.hepsiburada_categories'e cache'ler.
    Eszamanli cagrilarda kilit ile tek seferde calisir."""
    async with _hb_sync_lock:
        if not force:
            existing = await db.hepsiburada_categories.count_documents({})
            if existing > 0:
                return existing, None
        client, err = await _get_hb_client()
        if err:
            return 0, err
        try:
            cats = await asyncio.to_thread(client.iter_all_categories, True, True, True)
        except Exception as e:
            return 0, f"HB kategori çekme hatası: {e}"
        docs = []
        for c in cats:
            if not (c.get("leaf") and c.get("available")):
                continue
            paths = c.get("paths") or []
            full_path = " > ".join(paths) if paths else (c.get("displayName") or c.get("name") or "")
            docs.append({
                "category_id": c.get("categoryId"),
                "name": c.get("name") or c.get("displayName"),
                "full_path": full_path,
                "parent_id": c.get("parentCategoryId"),
                "leaf": True,
                "_path_lower": _tr_lower(full_path),
            })
        await db.hepsiburada_categories.delete_many({})
        if docs:
            for i in range(0, len(docs), 1000):
                await db.hepsiburada_categories.insert_many(docs[i:i + 1000])
        return len(docs), None


@router.post("/{marketplace}/sync-categories")
async def sync_marketplace_categories(marketplace: str, current_user: dict = Depends(require_admin)):
    """Pazaryeri kategori cache'ini canli API'den yeniler (su an: hepsiburada)."""
    if marketplace != "hepsiburada":
        raise HTTPException(status_code=400, detail="Şimdilik sadece Hepsiburada senkronizasyonu destekleniyor")
    n, err = await _sync_hb_categories(force=True)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {"success": True, "count": n, "message": f"{n} Hepsiburada kategorisi senkronize edildi"}


@router.get("/{marketplace}/options")
async def search_marketplace_categories(
    marketplace: str,
    q: str = "",
    limit: int = 200,
    mode: str = "flat",
    current_user: dict = Depends(require_admin),
):
    """Pazaryeri kategori ağacından arama.

    - mode=flat (default): {items: [{id, name, full_path, leaf}]} — q ile filtreli.
      Çoklu kelime AND mantığı (Türkçe-uyumlu) ve full_path üzerinde arama.
    - mode=tree: {tree: [...nested raw nodes]} — Tree View için ham ağaç.
    """
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")

    if marketplace == "hepsiburada":
        if (mode or "flat").lower() == "tree":
            return {"tree": [], "hint": "Hepsiburada için liste (arama) görünümünü kullanın."}
        # Cache bosse canli API'den senkronize et (ilk aramada bir kez)
        if await db.hepsiburada_categories.count_documents({}) == 0:
            _, err = await _sync_hb_categories()
            if err:
                return {"items": [], "hint": f"Hepsiburada kategorileri çekilemedi: {err}"}
        tokens = [t for t in _tr_lower((q or "").strip()).split() if t]
        query = {}
        if tokens:
            query = {"$and": [{"_path_lower": {"$regex": _re.escape(t)}} for t in tokens]}
        rows = []
        lim = max(1, min(2000, int(limit)))
        async for c in db.hepsiburada_categories.find(query, {"_id": 0, "_path_lower": 0}).limit(lim):
            rows.append({
                "id": c.get("category_id"),
                "name": c.get("name"),
                "full_path": c.get("full_path"),
                "parent_id": c.get("parent_id"),
                "leaf": True,
            })
        rows.sort(key=lambda c: len(c["full_path"] or ""))
        return {"items": rows, "count": len(rows)}

    if marketplace != "trendyol":
        return {"items": [], "tree": [], "hint": f"{marketplace} için kategori cache yok, manuel ID girin"}

    # Tree mode — ham ağacı döndür (frontend kendi içinde filtreler ve render eder)
    if (mode or "flat").lower() == "tree":
        tree = []
        async for top in db.trendyol_categories.find({}, {"_id": 0}):
            tree.append(top)
        return {"tree": tree, "count": len(tree)}

    # Flat mode (geriye uyumlu)
    tokens = [t for t in _tr_lower((q or "").strip()).split() if t]
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

    if tokens:
        def _match(c):
            hay = _tr_lower(c["full_path"])
            return all(t in hay for t in tokens)
        flat = [c for c in flat if _match(c)]

    # Sıralama: leaf'ler yukarda, daha kısa path öne
    flat.sort(key=lambda c: (not c["leaf"], len(c["full_path"])))

    return {"items": flat[: max(1, min(2000, int(limit)))], "count": len(flat)}


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
    # Bu kategorileri listeden GİZLE
    await db.categories.update_many(
        {"id": {"$in": ids}},
        {"$addToSet": {"excluded_marketplaces": marketplace}},
    )
    return {"success": True, "deleted": res.deleted_count}


@router.post("/{marketplace}/reset-all")
async def reset_all(marketplace: str, current_user: dict = Depends(require_admin)):
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    res = await db.category_mappings.delete_many({"marketplace": marketplace})
    # Tüm gizlenmiş kategorileri tekrar göster
    await db.categories.update_many(
        {"excluded_marketplaces": marketplace},
        {"$pull": {"excluded_marketplaces": marketplace}},
    )
    return {"success": True, "deleted": res.deleted_count}


@router.post("/{marketplace}/attr-cache")
async def upload_attribute_cache(
    marketplace: str,
    payload: dict,
    current_user: dict = Depends(require_admin),
):
    """Hepsiburada/Temu/N11 için manuel attribute cache yükle.
    Body: {marketplace_category_id: "...", attributes: [{id, name, required, attributeValues:[{id,name}]}]}.
    Kullanıcı kendi MP panelinden export ettiği listeyi buraya POST eder.
    """
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    cat_id = payload.get("marketplace_category_id") or payload.get("category_id")
    attrs = payload.get("attributes")
    if not cat_id or not isinstance(attrs, list):
        raise HTTPException(
            status_code=400,
            detail="Body: {marketplace_category_id: '...', attributes: [...]}"
        )
    coll = f"{marketplace}_category_attributes" if marketplace != "trendyol" else "trendyol_category_attributes"
    key = int(cat_id) if str(cat_id).isdigit() else str(cat_id)
    await db[coll].update_one(
        {"category_id": key},
        {"$set": {
            "category_id": key, "attributes": attrs,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "manual_upload",
            "uploaded_by": current_user.get("email"),
        }},
        upsert=True,
    )
    return {"success": True, "count": len(attrs),
            "message": f"{marketplace} kategori #{cat_id} için {len(attrs)} özellik cache'e yazıldı"}


# ─────────────────────────────────────────────────────────────────────────────
# ŞİRKET BİLGİSİ → MP "Üretici / İthalatçı" özelliklerini OTOMATİK doldur
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_company_value(attr_name: str, company: dict):
    """Trendyol/MP attribute adından şirket bilgisini eşler.
    - "...mail..." → email
    - "...adres..." → address (mail içermiyorsa)
    - "üretici/ithalatçı ad(ı)" → company_name (mail/adres içermiyorsa)
    """
    import re as _re
    if not attr_name or not company:
        return None
    nm = attr_name.lower().strip()
    has_uretici_or_ithalatci = bool(_re.search(r"üretici|i?thala?tç[ıi]|i?thalatci", nm))
    if not has_uretici_or_ithalatci:
        return None
    if "mail" in nm:
        v = (company.get("email") or "").strip()
        return v or None
    if "adres" in nm:
        v = (company.get("address") or "").strip()
        return v or None
    # "Üretici Adı" / "Birincil İthalatçı Adı" / "İhracatçı Adı"
    if _re.search(r"\bad[ıi]\b|\bismi?\b|\bunvan", nm):
        v = (company.get("company_name") or "").strip()
        return v or None
    return None


@router.post("/{marketplace}/{local_category_id}/fill-company-defaults")
async def fill_company_defaults(
    marketplace: str,
    local_category_id: str,
    current_user: dict = Depends(require_admin),
):
    """Sistem ayarlarındaki şirket bilgisini (settings.main.company_info) bu
    kategorinin Trendyol/MP attribute listesinden 'Üretici / İthalatçı Adı /
    Mail / Adres' alanları için default_mappings olarak yazar. Mevcut değerler
    KORUNUR."""
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    mapping = await db.category_mappings.find_one(
        {"category_id": local_category_id, "marketplace": marketplace}, {"_id": 0}
    )
    if not mapping or not mapping.get("marketplace_category_id"):
        raise HTTPException(status_code=400, detail="Önce sistem kategorisini pazaryeri kategorisi ile eşleştirin")

    settings = await db.settings.find_one({"id": "main"}, {"_id": 0, "company_info": 1})
    company = (settings or {}).get("company_info") or {}
    if not company:
        raise HTTPException(status_code=400, detail="Ayarlar > Şirket Bilgisi boş — önce doldurun")

    mp_cat_id = mapping["marketplace_category_id"]
    coll = "trendyol_category_attributes" if marketplace == "trendyol" else f"{marketplace}_category_attributes"
    cached = await db[coll].find_one(
        {"category_id": int(mp_cat_id) if str(mp_cat_id).isdigit() else str(mp_cat_id)},
        {"_id": 0},
    )
    attrs = (cached or {}).get("attributes", []) or []
    if not attrs:
        raise HTTPException(status_code=400, detail="Pazaryeri özellik listesi cache'de yok — önce 'Canlı Çek' deyin")

    defaults = dict(mapping.get("default_mappings") or {})
    filled = []
    for a in attrs:
        aid = str(a.get("id") or a.get("attribute", {}).get("id") or "")
        nm = a.get("name") or a.get("attribute", {}).get("name") or ""
        if not aid or not nm or defaults.get(aid):
            continue
        v = _resolve_company_value(nm, company)
        if v:
            defaults[aid] = v
            filled.append({"id": aid, "name": nm, "value": v})

    if filled:
        await db.category_mappings.update_one(
            {"category_id": local_category_id, "marketplace": marketplace},
            {"$set": {"default_mappings": defaults,
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
    return {
        "success": True,
        "filled_count": len(filled),
        "filled": filled,
        "default_mappings": defaults,
        "message": (f"{len(filled)} şirket alanı dolduruldu" if filled
                    else "Doldurulacak yeni alan yok (zaten dolu ya da bu kategoride üretici/ithalatçı alanı yok)"),
    }


@router.post("/{marketplace}/bulk-fill-company-defaults")
async def bulk_fill_company_defaults(
    marketplace: str,
    current_user: dict = Depends(require_admin),
):
    """Tüm matched kategoriler için Üretici/İthalatçı alanlarını sistem
    ayarlarındaki şirket bilgisinden default olarak yaz."""
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    settings = await db.settings.find_one({"id": "main"}, {"_id": 0, "company_info": 1})
    company = (settings or {}).get("company_info") or {}
    if not company:
        raise HTTPException(status_code=400, detail="Ayarlar > Şirket Bilgisi boş — önce doldurun")

    matched = await db.category_mappings.find(
        {"marketplace": marketplace, "marketplace_category_id": {"$nin": [None, ""]}},
        {"_id": 0},
    ).to_list(length=3000)

    now = datetime.now(timezone.utc).isoformat()
    coll = "trendyol_category_attributes" if marketplace == "trendyol" else f"{marketplace}_category_attributes"
    total_filled = 0
    processed = 0
    details = []
    for cm in matched:
        mp_cat_id = cm.get("marketplace_category_id")
        try:
            cached = await db[coll].find_one(
                {"category_id": int(mp_cat_id) if str(mp_cat_id).isdigit() else str(mp_cat_id)},
                {"_id": 0},
            )
        except Exception:
            cached = None
        attrs = (cached or {}).get("attributes", []) or []
        if not attrs:
            details.append({"category_name": cm.get("category_name"), "filled": 0, "note": "cache yok"})
            continue
        processed += 1
        defaults = dict(cm.get("default_mappings") or {})
        filled = 0
        for a in attrs:
            aid = str(a.get("id") or a.get("attribute", {}).get("id") or "")
            nm = a.get("name") or a.get("attribute", {}).get("name") or ""
            if not aid or not nm or defaults.get(aid):
                continue
            v = _resolve_company_value(nm, company)
            if v:
                defaults[aid] = v
                filled += 1
        if filled:
            await db.category_mappings.update_one(
                {"category_id": cm.get("category_id"), "marketplace": marketplace},
                {"$set": {"default_mappings": defaults, "updated_at": now}},
            )
            total_filled += filled
        details.append({"category_name": cm.get("category_name"), "filled": filled})
    return {
        "success": True,
        "processed": processed,
        "total_filled": total_filled,
        "details": details,
        "message": f"{processed} kategoride toplam {total_filled} şirket alanı dolduruldu",
    }



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
        # Trendyol "Materyal Bileşeni" → bizdeki veri "Ürün İçerik Bilgisi"nde durur
        if "materyal bileşeni" in nm:
            return "Ürün İçerik Bilgisi"
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
                # Trendyol client doğrudan LIST döndürebilir veya {categoryAttributes: [...]} dict döndürebilir
                if isinstance(data, list):
                    mp_attrs = data
                elif isinstance(data, dict):
                    mp_attrs = data.get("categoryAttributes") or data.get("attributes") or []
                else:
                    mp_attrs = []
                await db.trendyol_category_attributes.update_one(
                    {"category_id": int(mp_cat_id)},
                    {"$set": {"category_id": int(mp_cat_id), "attributes": mp_attrs, "updated_at": now}},
                    upsert=True,
                )
                fetched_live = True
            except Exception as e:
                import logging
                logging.exception(f"Trendyol attr fetch hatası cat={mp_cat_id}: {e}")
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


# ─────────────── BEDEN / SIZE EŞLEŞTİRME HELPER'LARI ───────────────
# Trendyol Beden gibi "size" attribute'larında "S" → "XS" gibi yanlış substring
# match'lerini engellemek için sertleştirilmiş bir algoritma.

# Bidirectional alias seti. Her grup içindeki tüm isimler birbirine EŞDEĞER kabul edilir.
# Bu, "XXS yoksa 2XS aktar", "STD yoksa Standart aktar" gibi senaryoları çözer.
_SIZE_ALIAS_PAIRS = [
    {"std", "standart", "standart beden", "tek beden", "tek ebat", "free size", "freesize", "onesize", "one size"},
    {"xxs", "2xs"},
    {"xxxs", "3xs"},
    {"xxl", "2xl"},
    {"xxxl", "3xl"},
    {"xxxxl", "4xl"},
    {"xxxxxl", "5xl"},
    {"xxxxxxl", "6xl"},
    # İngilizce/Türkçe karşılıklar (yalnızca size attribute'unda devreye girer)
    {"s", "small"},
    {"m", "medium", "orta"},
    {"l", "large", "büyük"},
    {"xl", "extra large", "x-large", "xlarge", "extralarge"},
]

# "Beden"in türevleri — bu attribute isimlerinde size matcher kullan
_SIZE_ATTR_KEYWORDS = ["beden", "size", "boy ölçü", "numara"]


def _is_size_attr(attr_name: str) -> bool:
    n = (attr_name or "").lower()
    return any(k in n for k in _SIZE_ATTR_KEYWORDS)


def _norm_size(s: str) -> str:
    """Bedeni normalize et — lowercase, boşluk/tire/slash/nokta temizle."""
    if s is None:
        return ""
    out = str(s).lower().strip()
    for ch in (" ", "-", "_", ".", "/"):
        out = out.replace(ch, "")
    return out


def _match_size_value(lv: str, mp_values: list):
    """Beden değeri için sıkı eşleştirme.
    1) Birebir (normalize edilmiş): "XS" == "xs", "2XL" == "2xl"
    2) Alias pair: "XXS" varsa "2XS"a, yoksa "XXS"a — tek yön değil çift yön
    3) Aksi → None (substring match'e izin yok!)
    """
    if not lv or not mp_values:
        return None
    lv_n = _norm_size(lv)

    # 1) Exact normalized
    for mv in mp_values:
        if _norm_size(mv.get("name", "")) == lv_n:
            return mv

    # 2) Alias pair
    for pair in _SIZE_ALIAS_PAIRS:
        if lv_n in pair:
            for mv in mp_values:
                if _norm_size(mv.get("name", "")) in pair:
                    return mv

    return None


def _match_general_value(lv: str, mp_values: list, aliases: dict):
    """Beden DIŞINDAKİ attribute'lar için. Daha güvenli substring kuralları."""
    if not lv or not mp_values:
        return None
    lv_lower = str(lv).lower().strip()
    if not lv_lower:
        return None
    ali = aliases.get(lv_lower, [])

    # 1) Birebir
    for mv in mp_values:
        if (mv.get("name") or "").lower().strip() == lv_lower:
            return mv

    # 2) Alias birebir
    for a in ali:
        for mv in mp_values:
            if (mv.get("name") or "").lower().strip() == a.lower():
                return mv

    # 3) Substring — yalnızca uzun (>=4 karakter) string'lerde, kısa karışmasın
    if len(lv_lower) >= 4:
        for mv in mp_values:
            mvn = (mv.get("name") or "").lower().strip()
            if mvn and (mvn in lv_lower or lv_lower in mvn):
                return mv
        for a in ali:
            if len(a) >= 4:
                for mv in mp_values:
                    mvn = (mv.get("name") or "").lower().strip()
                    if mvn and (mvn in a or a in mvn):
                        return mv

    return None




async def _auto_setup_mapping(marketplace: str, category_id: str) -> dict:
    """Yeni eşleştirilmiş bir kategori için TÜM otomatik kurulumu yapar:
      1) Live Trendyol attribute'larını çek ve cache'le
      2) Attribute isim eşleştirme (Trendyol → sistem global attrs)
      3) Değer eşleştirme (sistem değerleri → Trendyol value_ids, alias tablosu)
      4) Şirket bilgisini default'lara yaz (Üretici/İthalatçı Adı/Adres)
      5) Yaş Grubu=Yetişkin, Menşei=Türkiye varsayılanları
    Mevcut manuel değerler EZİLMEZ.
    """
    mapping = await db.category_mappings.find_one(
        {"category_id": category_id, "marketplace": marketplace}, {"_id": 0}
    )
    if not mapping or not mapping.get("marketplace_category_id"):
        return {"ok": False, "reason": "no_mp_cat_id"}
    mp_cat_id = mapping["marketplace_category_id"]
    now = datetime.now(timezone.utc).isoformat()
    summary = {"attr_matched": 0, "value_matched": 0, "company_filled": 0, "defaults_set": 0}

    # 1) Live Trendyol attrs
    mp_attrs = []
    if marketplace == "trendyol":
        try:
            from .integrations import get_trendyol_config
            from trendyol_client import TrendyolClient
            cfg = await get_trendyol_config()
            if cfg and cfg.get("is_active") and cfg.get("api_key"):
                client = TrendyolClient(
                    supplier_id=cfg["supplier_id"], api_key=cfg["api_key"],
                    api_secret=cfg["api_secret"], mode=cfg.get("mode", "live"),
                )
                data = await client.get_category_attributes(int(mp_cat_id))
                if isinstance(data, list):
                    mp_attrs = data
                elif isinstance(data, dict):
                    mp_attrs = data.get("categoryAttributes") or data.get("attributes") or []
                await db.trendyol_category_attributes.update_one(
                    {"category_id": int(mp_cat_id)},
                    {"$set": {"category_id": int(mp_cat_id), "attributes": mp_attrs, "updated_at": now}},
                    upsert=True,
                )
        except Exception:
            pass
    if marketplace == "hepsiburada":
        try:
            hb_attrs, _e = await _fetch_hb_category_attributes(mp_cat_id)
            mp_attrs = hb_attrs or mp_attrs
        except Exception:
            pass
    if not mp_attrs:
        coll = "trendyol_category_attributes" if marketplace == "trendyol" else f"{marketplace}_category_attributes"
        try:
            cached = await db[coll].find_one(
                {"category_id": int(mp_cat_id) if str(mp_cat_id).isdigit() else str(mp_cat_id)},
                {"_id": 0}
            )
            mp_attrs = (cached or {}).get("attributes", []) or []
        except Exception:
            mp_attrs = []
    if not mp_attrs:
        return {"ok": False, "reason": "no_attrs", "summary": summary}

    # 2) Attribute name auto-match
    global_attrs = await db.attributes.find({}, {"_id": 0}).to_list(length=2000)
    def _match_global(nm: str):
        n = (nm or "").lower().strip()
        if not n:
            return None
        if "materyal bileşeni" in n:
            return "Ürün İçerik Bilgisi"
        for ga in global_attrs:
            gn = (ga.get("name") or "").lower().strip()
            if not gn:
                continue
            if gn == n or n in gn or gn in n:
                return ga.get("name")
            if (n in ("color", "web color", "renk") and gn == "renk") or \
               (n in ("size", "beden") and gn == "beden"):
                return ga.get("name")
        return None

    existing_attr_maps = list(mapping.get("attribute_mappings") or [])
    existing_ids = {str(m.get("mp_attr_id") or m.get("trendyol_attr_id")) for m in existing_attr_maps}
    for a in mp_attrs:
        aid = str(a.get("id") or a.get("attribute", {}).get("id") or "")
        nm = a.get("name") or a.get("attribute", {}).get("name") or ""
        if not aid or aid in existing_ids:
            continue
        local = _match_global(nm)
        if local:
            existing_attr_maps.append({"local_attr": local, "mp_attr_id": int(aid) if aid.isdigit() else aid})
            existing_ids.add(aid)
            summary["attr_matched"] += 1

    # 3) Value auto-match — Beden için SIKI, diğerleri için alias + uzun substring
    aliases = {
        "kırmızı": ["red"], "mavi": ["blue"], "yeşil": ["green"], "sarı": ["yellow"],
        "siyah": ["black"], "beyaz": ["white"], "gri": ["gray", "grey"], "pembe": ["pink"],
        "mor": ["purple"], "turuncu": ["orange"], "kahverengi": ["brown"], "bej": ["beige"],
        "lacivert": ["navy", "dark blue"], "altın": ["gold"], "gümüş": ["silver"],
    }
    # Lokal değerleri topla (ürünlerden + global attributes + ticimax master)
    local_values: dict = {}
    def _add(nm, vv):
        if not nm or vv in (None, ""):
            return
        local_values.setdefault(str(nm).strip(), set()).add(str(vv).strip())
    def _walk(attrs):
        if isinstance(attrs, dict):
            for k, v in attrs.items():
                if isinstance(v, dict):
                    _add(v.get("label") or v.get("name") or k, v.get("value") or v.get("attribute_value"))
                elif v is not None:
                    _add(k, v)
        elif isinstance(attrs, list):
            for a in attrs:
                if isinstance(a, dict):
                    _add(a.get("label") or a.get("name") or a.get("type"), a.get("value") or a.get("attribute_value"))
    cat_doc = await db.categories.find_one({"id": category_id}, {"_id": 0, "name": 1})
    cat_name = (cat_doc or {}).get("name", "") or ""
    or_q = [{"category_id": category_id}]
    if cat_name:
        or_q.append({"category_name": cat_name})
    async for p in db.products.find({"$or": or_q}, {"_id": 0, "attributes": 1, "variants": 1}):
        _walk(p.get("attributes"))
        for v in p.get("variants", []) or []:
            _walk(v.get("attributes"))
            if v.get("color"):
                _add("Renk", v["color"])
                _add("Web Color", v["color"])
            if v.get("size"):
                _add("Beden", v["size"])
    async for ga in db.attributes.find({}, {"_id": 0, "name": 1, "values": 1}):
        for val in (ga.get("values") or []):
            _add(ga.get("name"), val)
    async for tm in db.ticimax_attribute_master.find({}, {"_id": 0}):
        for d in (tm.get("degerler") or []):
            if isinstance(d, dict):
                _add(tm.get("ozellik_tanim"), d.get("tanim"))
    local_values = {k: list(v) for k, v in local_values.items()}

    val_mappings = dict(mapping.get("value_mappings") or {})
    for a in mp_attrs:
        aid = str(a.get("id") or a.get("attribute", {}).get("id") or "")
        nm = a.get("name") or a.get("attribute", {}).get("name") or ""
        mp_values = a.get("attributeValues") or []
        if not aid or not mp_values:
            continue
        is_size = _is_size_attr(nm)
        candidates = local_values.get(nm, [])
        # Beden için sistem global "Beden" set'ini de ekle (cross-attribute kazanç)
        if is_size and "Beden" in local_values and nm != "Beden":
            candidates = list(set(list(candidates) + local_values["Beden"]))
        for lv in candidates:
            key = f"{aid}|{lv}"
            if val_mappings.get(key):
                continue
            if is_size:
                found = _match_size_value(lv, mp_values)
            else:
                found = _match_general_value(lv, mp_values, aliases)
            if found:
                val_mappings[key] = str(found.get("id"))
                summary["value_matched"] += 1

    # 4) Şirket bilgisini default'a yaz
    default_mappings = dict(mapping.get("default_mappings") or {})
    settings = await db.settings.find_one({"id": "main"}, {"_id": 0, "company_info": 1})
    company = (settings or {}).get("company_info") or {}
    for a in mp_attrs:
        aid = str(a.get("id") or a.get("attribute", {}).get("id") or "")
        nm = a.get("name") or a.get("attribute", {}).get("name") or ""
        if not aid or default_mappings.get(aid):
            continue
        v = _resolve_company_value(nm, company)
        if v:
            default_mappings[aid] = v
            summary["company_filled"] += 1

    # 5) Yaş Grubu=Yetişkin, Menşei=Türkiye + diğer ZORUNLU alanlar için "Belirtilmemiş"
    UNSPECIFIED_TERMS = ["belirtilmemiş", "belirtilmemis", "diğer", "diger", "other", "yok"]
    for a in mp_attrs:
        aid = str(a.get("id") or a.get("attribute", {}).get("id") or "")
        nm = (a.get("name") or a.get("attribute", {}).get("name") or "").lower()
        if not aid:
            continue
        # Yaş Grubu özel
        if "yaş grubu" in nm or "yas grubu" in nm:
            if not default_mappings.get(aid):
                for v in (a.get("attributeValues") or []):
                    if (v.get("name") or "").strip().lower() in ["yetişkin", "yetiskin"]:
                        default_mappings[aid] = str(v.get("id"))
                        summary["defaults_set"] += 1
                        break
            continue
        # Menşei özel
        if "menşe" in nm or "mense" in nm:
            if not default_mappings.get(aid):
                for v in (a.get("attributeValues") or []):
                    if (v.get("name") or "").strip().lower() in ["türkiye", "turkiye", "tr"]:
                        default_mappings[aid] = str(v.get("id"))
                        summary["defaults_set"] += 1
                        break
            continue
        # DİĞER zorunlu alanlar — "Belirtilmemiş" default (kullanıcı sonradan değiştirebilir)
        if not a.get("required"):
            continue
        if default_mappings.get(aid):
            continue
        # Dosya linki / sertifika gerektirenler skip
        if any(p in nm for p in ["analiz testi", "test raporu", "sertifika dosya", "dosya linki"]):
            continue
        # Üretici/ithalatçı zaten company_filled adımında doldurulmuştur
        if any(p in nm for p in ["üretici", "ithalat"]):
            continue
        # "Belirtilmemiş" değerini bul
        unspecified_val = None
        for v in (a.get("attributeValues") or []):
            vn = (v.get("name") or "").strip().lower()
            if vn in UNSPECIFIED_TERMS:
                unspecified_val = v
                break
        if unspecified_val:
            default_mappings[aid] = str(unspecified_val.get("id"))
            summary["defaults_set"] += 1

    # 5b) Yerel kategori adına göre özelleşmiş attribute defaults
    # Örn: yerel "Şort" → Kalıp="Mini Şort"; "Bermuda" → Kalıp="Bermuda"; "Şort Etek" → Kalıp="Şort Etek"
    # Burada DÜŞÜK öncelikli — daha önce manuel/auto set edilmiş bir değer EZİLMEZ.
    if cat_name:
        cat_name_lc = cat_name.lower()
        # Kural seti: (kategori_isim_keyword, [(trendyol_attr_isim, trendyol_value_isim), ...])
        # Sıra ÖNEMLİ: önce daha SPESİFİK (uzun) eşleşmeler denenir.
        CAT_NAME_HINTS = [
            ("şort etek",   [("Kalıp", "Şort Etek"), ("Siluet", "Şort Etek")]),
            ("sort etek",   [("Kalıp", "Şort Etek"), ("Siluet", "Şort Etek")]),
            ("bermuda",     [("Kalıp", "Bermuda")]),
            ("mini şort",   [("Kalıp", "Mini Şort")]),
            ("mini sort",   [("Kalıp", "Mini Şort")]),
            ("şort",        [("Kalıp", "Mini Şort")]),
            ("sort",        [("Kalıp", "Mini Şort")]),
            ("kimono",      [("Kalıp", "Loose"), ("Boy", "Midi")]),
            ("kaftan",      [("Kalıp", "Loose"), ("Boy", "Uzun")]),
            ("pelerin",     [("Kalıp", "Loose")]),
            ("mini elbise", [("Boy", "Mini")]),
            ("midi elbise", [("Boy", "Midi")]),
            ("maxi elbise", [("Boy", "Uzun")]),
            ("uzun elbise", [("Boy", "Uzun")]),
            ("uzun kol",    [("Kol Boyu", "Uzun Kol")]),
            ("kısa kol",    [("Kol Boyu", "Kısa Kol")]),
            ("kisa kol",    [("Kol Boyu", "Kısa Kol")]),
            ("askılı",      [("Kol Boyu", "Askılı")]),
            ("askili",      [("Kol Boyu", "Askılı")]),
            ("kolsuz",      [("Kol Boyu", "Kolsuz")]),
            ("tişört",      [("Kol Boyu", "Kısa Kol")]),
            ("tisort",      [("Kol Boyu", "Kısa Kol")]),
            ("t-shirt",     [("Kol Boyu", "Kısa Kol")]),
            ("tshirt",      [("Kol Boyu", "Kısa Kol")]),
        ]
        applied_hints = set()  # aynı attribute'e iki kez yazma
        for keyword, rules in CAT_NAME_HINTS:
            if keyword not in cat_name_lc:
                continue
            for tr_attr_name, tr_val_name in rules:
                # Bu attribute mp_attrs içinde var mı?
                for a in mp_attrs:
                    aid = str(a.get("id") or a.get("attribute", {}).get("id") or "")
                    nm = a.get("name") or a.get("attribute", {}).get("name") or ""
                    if not aid or aid in applied_hints:
                        continue
                    if (nm or "").strip().lower() != tr_attr_name.lower():
                        continue
                    # Mevcut default varsa EZME (manuel/önceki adım kazanır)
                    if default_mappings.get(aid):
                        applied_hints.add(aid)
                        continue
                    # Trendyol değer listesinden adı eşleşeni bul
                    target = None
                    tv = tr_val_name.strip().lower()
                    for v in (a.get("attributeValues") or []):
                        if (v.get("name") or "").strip().lower() == tv:
                            target = v
                            break
                    if target:
                        default_mappings[aid] = str(target.get("id"))
                        applied_hints.add(aid)
                        summary["defaults_set"] += 1
                        summary.setdefault("hints_applied", []).append(
                            f"{cat_name} → {tr_attr_name}={tr_val_name}"
                        )

    # Save all updates
    await db.category_mappings.update_one(
        {"category_id": category_id, "marketplace": marketplace},
        {"$set": {
            "attribute_mappings": existing_attr_maps,
            "value_mappings": val_mappings,
            "default_mappings": default_mappings,
            "updated_at": now,
        }}
    )
    return {"ok": True, "summary": summary, "mp_attrs_count": len(mp_attrs)}


@router.post("/{marketplace}/rebuild-size-mappings")
async def rebuild_size_mappings(marketplace: str, current_user: dict = Depends(require_admin)):
    """
    Mevcut tüm kategori mapping'lerinde BEDEN (Size) attribute'undaki yanlış
    eşleştirmeleri yeniden hesaplar. Önce var olan size value_mappings'leri
    SİLER, sonra `_match_size_value` ile yeniden ekler (exact → alias pair).
    
    Kullanıcı feedback'i: "S → XS gibi yanlış eşleşmeler var. Birebir aramayı dene,
    olmazsa XXS↔2XS, STD↔Standart gibi karşılıklara düş, ama yanlış eşleşme YAPMA."
    """
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    attr_coll = "trendyol_category_attributes" if marketplace == "trendyol" else f"{marketplace}_category_attributes"
    now = datetime.now(timezone.utc).isoformat()
    summary = {
        "mappings_checked": 0,
        "size_keys_removed": 0,
        "size_keys_added": 0,
        "categories_updated": 0,
        "details": [],
    }
    mappings = await db.category_mappings.find(
        {"marketplace": marketplace, "marketplace_category_id": {"$nin": [None, ""]}},
        {"_id": 0},
    ).to_list(length=5000)
    for cm in mappings:
        summary["mappings_checked"] += 1
        category_id = cm.get("category_id")
        mp_cat_id = cm.get("marketplace_category_id")
        if not mp_cat_id:
            continue
        try:
            cache = await db[attr_coll].find_one(
                {"category_id": int(mp_cat_id) if str(mp_cat_id).isdigit() else str(mp_cat_id)},
                {"_id": 0},
            )
        except Exception:
            cache = None
        mp_attrs = (cache or {}).get("attributes") or []
        if not mp_attrs:
            continue
        size_attr_ids = set()  # str
        size_attrs = {}  # aid → mp_values
        for a in mp_attrs:
            aid = str(a.get("id") or a.get("attribute", {}).get("id") or "")
            nm = a.get("name") or a.get("attribute", {}).get("name") or ""
            if not aid or not _is_size_attr(nm):
                continue
            size_attr_ids.add(aid)
            size_attrs[aid] = a.get("attributeValues") or []

        if not size_attr_ids:
            continue

        # Mevcut value_mappings'i temizle (yalnızca size attribute key'leri)
        vm = dict(cm.get("value_mappings") or {})
        removed = 0
        for k in list(vm.keys()):
            if "|" not in k:
                continue
            aid_part = k.split("|", 1)[0]
            if aid_part in size_attr_ids:
                vm.pop(k, None)
                removed += 1

        # Yerel kandidat bedenleri topla
        cat_doc = await db.categories.find_one({"id": category_id}, {"_id": 0, "name": 1})
        cat_name = (cat_doc or {}).get("name", "") or ""
        or_q = [{"category_id": category_id}]
        if cat_name:
            or_q.append({"category_name": cat_name})
        candidates = set()
        async for p in db.products.find({"$or": or_q}, {"_id": 0, "variants": 1, "sizes": 1}):
            for sz in (p.get("sizes") or []):
                if sz:
                    candidates.add(str(sz).strip())
            for v in (p.get("variants") or []):
                if v.get("size"):
                    candidates.add(str(v["size"]).strip())
        # Sistemdeki global Beden attribute değerlerini de ekle
        async for ga in db.attributes.find({"name": {"$regex": "beden", "$options": "i"}}, {"_id": 0, "values": 1}):
            for vv in (ga.get("values") or []):
                if vv:
                    candidates.add(str(vv).strip())

        # Yeniden eşleştir
        added = 0
        for aid, mp_values in size_attrs.items():
            for lv in candidates:
                key = f"{aid}|{lv}"
                if vm.get(key):
                    continue
                found = _match_size_value(lv, mp_values)
                if found:
                    vm[key] = str(found.get("id"))
                    added += 1

        if removed or added:
            await db.category_mappings.update_one(
                {"category_id": category_id, "marketplace": marketplace},
                {"$set": {"value_mappings": vm, "updated_at": now}},
            )
            summary["size_keys_removed"] += removed
            summary["size_keys_added"] += added
            summary["categories_updated"] += 1
            summary["details"].append({
                "category_id": category_id,
                "category_name": cat_name,
                "removed": removed,
                "added": added,
            })

    return {"success": True, "summary": summary, "message": (
        f"{summary['categories_updated']} kategori güncellendi. "
        f"{summary['size_keys_removed']} eski beden eşleşmesi temizlendi, "
        f"{summary['size_keys_added']} yeni eşleşme oluşturuldu."
    )}





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
    # 🚀 OTOMATIK kurulum: attribute eşleştir + değer eşleştir + şirket bilgisi + Yaş Grubu/Menşei
    auto_skip = bool((payload or {}).get("skip_auto_setup"))
    auto_result = None
    if not auto_skip and doc["marketplace_category_id"]:
        try:
            auto_result = await _auto_setup_mapping(marketplace, category_id)
        except Exception as e:
            import logging
            logging.exception(f"_auto_setup_mapping hatası: {e}")
            auto_result = {"ok": False, "reason": str(e)}
    return {"success": True, "mapping": doc, "auto_setup": auto_result}


@router.post("/{marketplace}/{local_category_id}/refresh-attributes")
async def refresh_attributes(
    marketplace: str,
    local_category_id: str,
    current_user: dict = Depends(require_admin),
):
    """Tek kategori için MP attribute listesini anlık yenile.
    Trendyol: canlı API çağrısı yapar, cache'i günceller.
    Diğer MP'ler: cache entry yoksa yok mesajı döner.
    """
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    mapping = await db.category_mappings.find_one(
        {"category_id": local_category_id, "marketplace": marketplace}, {"_id": 0}
    )
    if not mapping or not mapping.get("marketplace_category_id"):
        raise HTTPException(
            status_code=400,
            detail="Önce sistem kategorisini pazaryeri kategorisiyle eşleştirin",
        )
    mp_cat_id = mapping["marketplace_category_id"]
    if marketplace == "trendyol":
        try:
            from .integrations import get_trendyol_config
            from trendyol_client import TrendyolClient
            cfg = await get_trendyol_config()
            if not (cfg.get("is_active") and cfg.get("api_key")):
                raise HTTPException(status_code=400, detail="Trendyol credential girilmemiş (Ayarlar → Trendyol)")
            client = TrendyolClient(
                supplier_id=cfg["supplier_id"], api_key=cfg["api_key"],
                api_secret=cfg["api_secret"], mode=cfg.get("mode", "sandbox"),
            )
            data = await client.get_category_attributes(int(mp_cat_id))
            attrs = data.get("categoryAttributes") or data.get("attributes") or []
            await db.trendyol_category_attributes.update_one(
                {"category_id": int(mp_cat_id)},
                {"$set": {
                    "category_id": int(mp_cat_id), "attributes": attrs,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True,
            )
            return {"success": True, "fetched": True, "count": len(attrs),
                    "message": f"Trendyol canlı: {len(attrs)} özellik çekildi"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Trendyol API hatası: {e}")
    # Diğer pazaryerleri — canlı entegrasyon yok
    return {
        "success": False,
        "fetched": False,
        "message": f"{marketplace} için canlı API entegrasyonu henüz eklenmedi. "
                   f"Manuel JSON upload için /attr-cache endpoint'ini kullanın."
    }


@router.delete("/{marketplace}/{category_id}")
async def clear_mapping(marketplace: str, category_id: str,
                         current_user: dict = Depends(require_admin)):
    """
    Kategoriyi bu pazaryeri için mapping listesinden TAMAMEN gizler:
      1. Mevcut mapping kaydını siler
      2. Kategorinin `excluded_marketplaces` array'ine bu pazaryerini ekler
         → Bu kategori artık bu pazaryerinin Kategori Eşleştirme sayfasında
           görünmez (kullanıcı tekrar görmek isterse `Hepsini Sıfırla` butonu
           ile resetler).
    """
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    await db.category_mappings.delete_one(
        {"category_id": category_id, "marketplace": marketplace}
    )
    # Kategoriyi bu pazaryeri için gizle
    await db.categories.update_one(
        {"id": category_id},
        {"$addToSet": {"excluded_marketplaces": marketplace}},
    )
    return {"success": True}


@router.post("/{marketplace}/{category_id}/include")
async def include_category(marketplace: str, category_id: str,
                            current_user: dict = Depends(require_admin)):
    """Daha önce silinen (gizlenen) kategoriyi tekrar listeye getirir."""
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")
    await db.categories.update_one(
        {"id": category_id},
        {"$pull": {"excluded_marketplaces": marketplace}},
    )
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

    if marketplace == "hepsiburada":
        key = int(mp_cat_id) if str(mp_cat_id).isdigit() else str(mp_cat_id)
        cached = await db.hepsiburada_category_attributes.find_one({"category_id": key}, {"_id": 0})
        attrs = (cached or {}).get("attributes")
        if not attrs or (cached or {}).get("_v") != 2:
            attrs, hb_err = await _fetch_hb_category_attributes(mp_cat_id)
            if hb_err:
                return {
                    "attributes": [],
                    "attribute_mappings": mapping.get("attribute_mappings", []),
                    "default_mappings": mapping.get("default_mappings", {}),
                    "value_mappings": mapping.get("value_mappings", {}),
                    "hint": f"Hepsiburada özellikleri çekilemedi: {hb_err}",
                }
        return {
            "attributes": attrs or [],
            "attribute_mappings": mapping.get("attribute_mappings", []),
            "default_mappings": mapping.get("default_mappings", {}),
            "value_mappings": mapping.get("value_mappings", {}),
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
    sistemdeki global attribute değerleri + Ticimax master değerler birleştirilerek döner.

    Ürün attributes formatı hem LIST hem DICT olabilir; ikisini de destekler.

    Ticimax `ticimax_attribute_master` koleksiyonundan
    (örn. {ozellik_tanim:'Web Color', degerler:[{tanim:'Bej'}, ...]}) da değerler eklenir.
    """
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Pazaryeri bulunamadı")

    local_values: dict[str, set] = {}

    def _add(nm: str | None, vv):
        if not nm or vv in (None, ""):
            return
        sv = str(vv).strip()
        if not sv:
            return
        local_values.setdefault(str(nm).strip(), set()).add(sv)

    def _collect_attrs(attrs):
        """attributes alanı list veya dict olabilir."""
        if isinstance(attrs, list):
            for a in attrs:
                if isinstance(a, dict):
                    nm = a.get("name") or a.get("type") or a.get("attribute_name") or a.get("label")
                    vv = a.get("value") or a.get("attribute_value")
                    _add(nm, vv)
                elif isinstance(a, str):
                    # Bazı eski kayıtlarda string olarak tutulmuş — atla
                    pass
        elif isinstance(attrs, dict):
            for k, v in attrs.items():
                if isinstance(v, dict):
                    nm = v.get("label") or v.get("name") or k
                    vv = v.get("value") or v.get("attribute_value")
                    _add(nm, vv)
                else:
                    _add(k, v)

    # 1) Bu kategorideki ürünlerden distinct attribute değerlerini topla
    #    (hem category_id hem category_name ile match — bazı ürünler
    #     "EN YENİLER" gibi koleksiyon kategorisinde olabiliyor)
    cat_doc = await db.categories.find_one({"id": local_category_id}, {"_id": 0, "name": 1})
    cat_name = (cat_doc or {}).get("name", "") or ""
    or_q = [{"category_id": local_category_id}]
    if cat_name:
        or_q.append({"category_name": cat_name})
    cursor = db.products.find(
        {"$or": or_q},
        {"_id": 0, "attributes": 1, "variants": 1},
    )
    async for p in cursor:
        _collect_attrs(p.get("attributes"))
        for v in p.get("variants", []) or []:
            _collect_attrs(v.get("attributes"))
            if v.get("color"):
                _add("Renk", v["color"])
                _add("Web Color", v["color"])
            if v.get("size"):
                _add("Beden", v["size"])

    # 🎯 Bu kategorideki ürünlerden GELEN özellik adları. Bu adlar için global
    # `attributes` / ticimax master değerleriyle KİRLETME yapılmaz — yalnızca
    # ürünlerin gerçek özellik değerleri gösterilir. (örn. "Boy" özelliğine
    # global attributes'taki ölçü/numara değerleri 150-200, "30 ML", veya "Cep"e
    # 1-2-3-4 gibi alakasız değerler karışmasın → "başka yerden çekme" sorunu).
    product_value_names = {k.casefold() for k in local_values.keys()}

    # 2) Global /api/attributes içerisindeki değerleri SADECE üründe karşılığı
    #    OLMAYAN özellik adları için (fallback) birleştir.
    async for ga in db.attributes.find({}, {"_id": 0, "name": 1, "values": 1}):
        nm = (ga.get("name") or "").strip()
        if not nm or nm.casefold() in product_value_names:
            continue
        for val in ga.get("values", []) or []:
            sv = str(val).strip()
            if sv:
                local_values.setdefault(nm, set()).add(sv)

    # 3) Ticimax master değerlerini (`ticimax_attribute_master`) — yine sadece
    #    üründe karşılığı olmayan özellik adları için (fallback).
    #    Format: {ozellik_id, ozellik_tanim, degerler:[{id,tanim}, ...]}
    async for tm in db.ticimax_attribute_master.find({}, {"_id": 0}):
        nm = (tm.get("ozellik_tanim") or "").strip()
        if not nm or nm.casefold() in product_value_names:
            continue
        for d in tm.get("degerler") or []:
            sv = (d.get("tanim") or "").strip() if isinstance(d, dict) else str(d).strip()
            if sv:
                local_values.setdefault(nm, set()).add(sv)

    out = {k: sorted(list(v)) for k, v in local_values.items()}
    # Trendyol "Materyal Bileşeni" serbest metin alanı için değerleri
    # "Ürün İçerik Bilgisi" (ve kumaş içeriği) kaynaklarından köprüle —
    # böylece değer-eşleştirme ekranında da görünür.
    _icerik = set()
    for _src in ("Ürün İçerik Bilgisi", "Kumaş Bilgisi", "Kumaş İçeriği", "Ürün İçeriği", "Kumaş içeriği"):
        _icerik |= set(out.get(_src, []))
    if _icerik:
        out["Materyal Bileşeni"] = sorted(set(out.get("Materyal Bileşeni", [])) | _icerik)
    mapping = await db.category_mappings.find_one(
        {"category_id": local_category_id, "marketplace": marketplace}, {"_id": 0}
    ) or {}
    return {
        "local_values": out,
        "value_mappings": mapping.get("value_mappings", {}),
    }
