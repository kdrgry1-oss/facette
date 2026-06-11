"""
=============================================================================
ticimax_category_sync.py — Ticimax Web Servis KATEGORI Senkronizasyonu
=============================================================================
Amaç: Ticimax'taki kategori üyeliklerini yerel `products` koleksiyonuna
yansıtmak. Özellikle "En Yeniler" kategorisinin Ticimax'taki haliyle birebir
aynı olmasını sağlar. İstenirse TÜM kategoriler de eşitlenebilir.

YÖN: kategori → ürün
  Her Ticimax kategorisi için SelectUrun(KategoriID=X) ile o kategorideki
  ürünler çekilir; böylece "ürün nesnesinde kategori hangi alanda" sorusuna
  hiç girmeden, doğrulanmış WS imzasıyla (get_products) güvenli çalışırız.

EŞLEME STRATEJİSİ (stock-sync ile birebir aynı, öncelik sırası):
  1. csv_card_id == Ticimax UrunKartiID (ID alanı)
  2. variants[*].stock_code / barcode  == Ticimax Varyasyon.StokKodu / Barkod
  3. top-level stock_code / barcode

KATEGORİ EŞLEME: Türkçe-normalize isim bazlı
  Ticimax Kategori.Tanim  <->  bizim categories.name / full_name
  (kategori dokümanımızda Ticimax kategori ID'si tutulmadığı için isimle eşleriz)

GÜVENLİK:
  - apply=false (VARSAYILAN) → hiçbir şey yazılmaz, sadece "ne değişecek" raporu
  - apply=true               → değişiklikler products koleksiyonuna uygulanır
  - mode=en_yeniler          → SADECE "En Yeniler" kategorisi tam ayna (ekle/çıkar)
  - mode=all                 → bu taramada EN AZ BİR Ticimax kategorisinde görünen
                               ürünlerin kategori üyeliği Ticimax'a göre YENİDEN kurulur
                               (hiç görünmeyen ürünlere dokunulmaz)

ENDPOINT:
  POST /api/admin/ticimax/sync-categories?mode=en_yeniler&apply=false
  POST /api/admin/ticimax/sync-categories-async?mode=all&apply=true
=============================================================================
"""
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Set, Tuple
import sys, os, time, unicodedata

# routes -> backend path
_BACKEND_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_PATH not in sys.path:
    sys.path.insert(0, _BACKEND_PATH)

from .deps import db, logger, require_admin
from .marketplace_hub import log_integration_event

router = APIRouter(prefix="/admin/ticimax", tags=["admin-ticimax-category"])

# "En Yeniler" kategorisini tanımak için kabul edilen normalize isimler
_EN_YENILER_ALIASES = {
    "en yeniler", "en yeni urunler", "en yeni urun",
    "yeni urunler", "yeni urun", "yeniler", "yeni",
}


# ───────────────────────── yardımcılar ─────────────────────────
def _norm(s: Any) -> str:
    """Türkçe-duyarsız normalize: lower + aksan sadeleştirme + boşluk sadeleştirme."""
    if s is None:
        return ""
    s = str(s)
    # Türkçe özel dönüşümler (unicode NFKD bazılarını kaçırır)
    repl = {"İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s",
            "Ç": "c", "ç": "c", "Ğ": "g", "ğ": "g",
            "Ö": "o", "ö": "o", "Ü": "u", "ü": "u"}
    s = "".join(repl.get(ch, ch) for ch in s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = " ".join(s.split())
    return s


def _to_dict(zo) -> Dict:
    try:
        from ticimax_client import _to_dict as _td  # type: ignore
        d = _td(zo)
        return d if isinstance(d, dict) else {}
    except Exception:
        if isinstance(zo, dict):
            return zo
        out = {}
        for k in dir(zo):
            if k.startswith("_"):
                continue
            try:
                v = getattr(zo, k)
            except Exception:
                continue
            if not callable(v):
                out[k] = v
        return out


def _unwrap_variants(raw) -> List[Dict]:
    try:
        from ticimax_client import _unwrap_list  # type: ignore
        return [_to_dict(x) for x in _unwrap_list(raw)]
    except Exception:
        if raw is None:
            return []
        if isinstance(raw, list):
            return [_to_dict(x) for x in raw]
        # zeep array sarmalı
        for attr in dir(raw):
            if attr.startswith("_"):
                continue
            try:
                v = getattr(raw, attr)
            except Exception:
                continue
            if isinstance(v, list):
                return [_to_dict(x) for x in v]
        return []


async def _build_local_category_index() -> Tuple[Dict[str, str], Dict[str, Optional[str]], Dict[str, str]]:
    """
    Döner:
      name_to_id : normalize(isim) -> bizim kategori id  (name + full_name ikisi de)
      parent_map : kategori id -> parent_id
      id_to_name : kategori id -> görünen ad (rapor için)
    full_name'i runtime'da parent zinciriyle kurarız (categories route ile aynı mantık).
    """
    cats = await db.categories.find({}, {"_id": 0}).to_list(5000)
    by_id = {c["id"]: c for c in cats if c.get("id")}
    parent_map = {c["id"]: c.get("parent_id") for c in cats if c.get("id")}
    id_to_name = {c["id"]: (c.get("name") or "") for c in cats if c.get("id")}

    def full_name(cid: str) -> str:
        path, cur, guard = [], cid, 0
        while cur and cur in by_id and guard < 50:
            path.append(by_id[cur].get("name", ""))
            cur = by_id[cur].get("parent_id")
            guard += 1
        return " > ".join(reversed(path))

    name_to_id: Dict[str, str] = {}
    # Önce yaprak/normal isimler, sonra full_name (çakışmada kısa ada öncelik verme:
    # tam ad daha spesifik olduğundan onu da ekleriz ama mevcut anahtarı ezmeyiz)
    for c in cats:
        cid = c.get("id")
        if not cid:
            continue
        nm = _norm(c.get("name"))
        if nm and nm not in name_to_id:
            name_to_id[nm] = cid
    for c in cats:
        cid = c.get("id")
        if not cid:
            continue
        fn = _norm(full_name(cid))
        if fn and fn not in name_to_id:
            name_to_id[fn] = cid
        # full_name'in son parçası (ör. "giyim > ust giyim > elbise" -> "elbise")
        if fn:
            last = fn.split(" > ")[-1].strip()
            if last and last not in name_to_id:
                name_to_id[last] = cid

    return name_to_id, parent_map, id_to_name


def _expand_with_ancestors(selected_ids: List[str], parent_map: Dict[str, Optional[str]]) -> List[str]:
    """Seçilen kategori id'lerini atalarıyla düzleştirir (category_ids / vitrin filtresi için)."""
    result, seen = [], set()
    for cid in [str(c) for c in (selected_ids or []) if c]:
        cur, guard = cid, 0
        while cur and cur not in seen and guard < 50:
            seen.add(cur)
            result.append(cur)
            cur = parent_map.get(cur)
            guard += 1
    return result


async def _match_local_product(d: Dict, variants_raw: List[Dict]) -> Optional[Dict]:
    """stock-sync ile birebir aynı 3-aşamalı eşleme. id + mevcut categories döner."""
    proj = {"_id": 0, "id": 1, "name": 1, "categories": 1, "category_id": 1,
            "category_ids": 1, "csv_card_id": 1}
    tc_card_id = d.get("ID") or d.get("UrunKartiID")
    try:
        tc_card_id = int(tc_card_id) if tc_card_id else None
    except Exception:
        tc_card_id = None

    # ÖNCELİK 1
    product_doc = None
    if tc_card_id:
        product_doc = await db.products.find_one({"csv_card_id": tc_card_id}, proj)

    # ÖNCELİK 2 — varyant stok kodu / barkod
    if not product_doc and variants_raw:
        tv_codes = [str(v.get("StokKodu") or "").strip() for v in variants_raw if v.get("StokKodu")]
        tv_bars = [str(v.get("Barkod") or "").strip() for v in variants_raw if v.get("Barkod")]
        or_clauses = []
        if tv_codes:
            or_clauses.append({"variants.stock_code": {"$in": tv_codes}})
            or_clauses.append({"stock_code": {"$in": tv_codes}})
        if tv_bars:
            or_clauses.append({"variants.barcode": {"$in": tv_bars}})
            or_clauses.append({"barcode": {"$in": tv_bars}})
        if or_clauses:
            product_doc = await db.products.find_one({"$or": or_clauses}, proj)

    # ÖNCELİK 3 — top-level stok kodu / barkod
    if not product_doc:
        top_code = str(d.get("StokKodu") or "").strip()
        top_bar = str(d.get("Barkod") or d.get("BarkodNo") or "").strip()
        tcl = []
        if top_code:
            tcl.append({"variants.stock_code": top_code})
            tcl.append({"stock_code": top_code})
        if top_bar:
            tcl.append({"variants.barcode": top_bar})
            tcl.append({"barcode": top_bar})
        if tcl:
            product_doc = await db.products.find_one({"$or": tcl}, proj)

    return product_doc


# ───────────────────────── ana iş ─────────────────────────
async def _run_category_sync(
    mode: str,
    apply: bool,
    aktif: Optional[int],
    page_size: int,
    max_per_category: int,
    sleep_between: float,
) -> Dict:
    started = datetime.now(timezone.utc)
    import ticimax_client as _tc  # type: ignore
    from ticimax_client import get_all_categories, get_products  # type: ignore

    settings = await db.settings.find_one({"id": "ticimax"}) or {}
    api_key = settings.get("api_key") or os.environ.get("TICIMAX_API_KEY") or "AKG0M8DTRSEBAIA898JA6HW22EDIU3"
    # Domain'i de DB'den (yoksa env'den) uygula — yeni Ticimax sitesi için
    _domain = settings.get("domain") or settings.get("api_url") or os.environ.get("TICIMAX_DOMAIN")
    if _domain:
        try:
            _tc.set_domain(_domain)
        except Exception as e:
            logger.warning(f"[cat-sync] set_domain hata: {e}")

    # 1) Yerel kategori indeksi
    name_to_id, parent_map, id_to_name = await _build_local_category_index()

    # 2) Ticimax kategorileri
    try:
        tc_cats = get_all_categories(wscode=api_key, sleep_between=sleep_between)
    except Exception as e:
        logger.error(f"[cat-sync] get_all_categories error: {e}")
        return {"success": False, "error": f"Ticimax kategorileri alınamadı: {e}"}

    tc_cats = [_to_dict(c) for c in (tc_cats or [])]

    # 3) Hedef Ticimax kategorilerini seç
    targets: List[Dict] = []          # işlenecek (eşleşen) Ticimax kategorileri
    unmatched_categories: List[Dict] = []  # bizde karşılığı bulunamayan Ticimax kategorileri
    en_yeniler_local_id: Optional[str] = None

    def _local_id_for(tc_name: str) -> Optional[str]:
        return name_to_id.get(_norm(tc_name))

    if mode == "en_yeniler":
        # Önce tam "en yeniler", yoksa alias'lar
        cand = None
        for c in tc_cats:
            if _norm(c.get("Tanim")) == "en yeniler":
                cand = c
                break
        if not cand:
            for c in tc_cats:
                if _norm(c.get("Tanim")) in _EN_YENILER_ALIASES:
                    cand = c
                    break
        if not cand:
            return {
                "success": False,
                "error": "Ticimax'ta 'En Yeniler' (veya benzeri) kategori bulunamadı.",
                "ticimax_categories_sample": [c.get("Tanim") for c in tc_cats[:40]],
            }
        # Bizde karşılığı
        en_yeniler_local_id = _local_id_for(cand.get("Tanim")) or name_to_id.get("en yeniler")
        if not en_yeniler_local_id:
            return {
                "success": False,
                "error": "Bizde 'En Yeniler' adlı kategori bulunamadı. Önce bu kategoriyi oluşturun.",
                "ticimax_en_yeniler": cand.get("Tanim"),
            }
        targets = [cand]
    else:  # all
        for c in tc_cats:
            lid = _local_id_for(c.get("Tanim"))
            if lid:
                targets.append({**c, "_local_id": lid})
            else:
                unmatched_categories.append({
                    "ticimax_id": c.get("ID"),
                    "ticimax_name": c.get("Tanim"),
                })

    # 4) Her hedef kategori için Ticimax ürünlerini çek + yerelde eşleştir
    #    product_id -> set(local_category_id)  (Ticimax'a göre olması gereken üyelik)
    desired: Dict[str, Set[str]] = {}
    # rapor: hangi üründe hangi kategori bulundu
    not_found: List[Dict] = []        # Ticimax'ta var, bizde eşleşmeyen ürünler
    per_category_stats: List[Dict] = []
    seen_product_ids: Set[str] = set()
    api_calls = 0

    for tc in targets:
        tc_id = tc.get("ID")
        tc_name = tc.get("Tanim")
        local_cat_id = tc.get("_local_id") or en_yeniler_local_id
        if not tc_id or not local_cat_id:
            continue

        matched_here = 0
        notfound_here = 0
        fetched = 0
        page = 1
        while fetched < max_per_category:
            try:
                chunk = get_products(page=page, page_size=page_size,
                                     aktif=aktif, kategori_id=int(tc_id), wscode=api_key)
                api_calls += 1
            except Exception as e:
                logger.warning(f"[cat-sync] kategori {tc_id} sayfa {page} hata: {e}")
                break
            if not chunk:
                break
            for raw in chunk:
                d = _to_dict(raw)
                if not d:
                    continue
                variants_raw = _unwrap_variants(d.get("Varyasyonlar"))
                pdoc = await _match_local_product(d, variants_raw)
                if not pdoc:
                    notfound_here += 1
                    not_found.append({
                        "ticimax_category": tc_name,
                        "ticimax_card_id": d.get("ID") or d.get("UrunKartiID"),
                        "ticimax_name": d.get("UrunAdi") or d.get("Tanim") or d.get("Adi"),
                        "stock_code": d.get("StokKodu"),
                        "barcode": d.get("Barkod") or d.get("BarkodNo"),
                    })
                    continue
                pid = pdoc["id"]
                seen_product_ids.add(pid)
                desired.setdefault(pid, set()).add(local_cat_id)
                matched_here += 1
            fetched += len(chunk)
            page += 1
            if len(chunk) < page_size:
                break
            time.sleep(sleep_between)  # rate limit (Ticimax ~12sn)

        per_category_stats.append({
            "ticimax_id": tc_id,
            "ticimax_name": tc_name,
            "local_category_id": local_cat_id,
            "local_category_name": id_to_name.get(local_cat_id, ""),
            "matched_products": matched_here,
            "not_found_products": notfound_here,
            "fetched": fetched,
        })

    # 5) Değişiklikleri hesapla (apply=false ise sadece rapor)
    #    En Yeniler modunda TAM AYNA: olması gerekenlere ekle, olmaması gerekenlerden çıkar.
    planned_changes: List[Dict] = []
    to_update: List[Tuple[str, List[str]]] = []  # (product_id, new_selected_categories)

    if mode == "en_yeniler":
        target_local = en_yeniler_local_id
        # Şu an bizde "En Yeniler"de olan ürünler
        current_in_local = await db.products.find(
            {"categories": target_local}, {"_id": 0, "id": 1, "name": 1, "categories": 1}
        ).to_list(100000)
        current_ids = {p["id"] for p in current_in_local}
        desired_ids = {pid for pid, cats in desired.items() if target_local in cats}

        # EKLENECEKLER: Ticimax En Yeniler'de var, bizde yok
        for pid in desired_ids - current_ids:
            doc = await db.products.find_one({"id": pid}, {"_id": 0, "id": 1, "name": 1, "categories": 1})
            if not doc:
                continue
            cur = [str(x) for x in (doc.get("categories") or []) if x]
            new_cats = cur + [target_local] if target_local not in cur else cur
            planned_changes.append({"product_id": pid, "name": doc.get("name"),
                                    "action": "ekle", "category": id_to_name.get(target_local)})
            to_update.append((pid, new_cats))

        # ÇIKARILACAKLAR: bizde En Yeniler'de, Ticimax'ta artık yok
        for p in current_in_local:
            if p["id"] in desired_ids:
                continue
            cur = [str(x) for x in (p.get("categories") or []) if x]
            new_cats = [c for c in cur if c != target_local]
            planned_changes.append({"product_id": p["id"], "name": p.get("name"),
                                    "action": "cikar", "category": id_to_name.get(target_local)})
            to_update.append((p["id"], new_cats))

    else:  # all — bu taramada görünen ürünlerin üyeliğini Ticimax'a göre YENİDEN kur
        for pid, cat_set in desired.items():
            doc = await db.products.find_one({"id": pid}, {"_id": 0, "id": 1, "name": 1, "categories": 1})
            if not doc:
                continue
            cur = set(str(x) for x in (doc.get("categories") or []) if x)
            new_set = set(cat_set)
            if cur != new_set:
                added = new_set - cur
                removed = cur - new_set
                planned_changes.append({
                    "product_id": pid, "name": doc.get("name"),
                    "added": [id_to_name.get(c, c) for c in added],
                    "removed": [id_to_name.get(c, c) for c in removed],
                })
                to_update.append((pid, list(new_set)))

    # 6) Uygula
    applied = 0
    if apply:
        for pid, new_cats in to_update:
            new_cats = [str(c) for c in new_cats if c]
            cat_ids_all = _expand_with_ancestors(new_cats, parent_map)
            primary = new_cats[0] if new_cats else ""
            set_doc = {
                "categories": new_cats,
                "category_ids": cat_ids_all,
                "category_id": primary,
                "category_synced_at": datetime.now(timezone.utc).isoformat(),
            }
            if primary:
                set_doc["category_name"] = id_to_name.get(primary, "")
            res = await db.products.update_one({"id": pid}, {"$set": set_doc})
            if res.modified_count:
                applied += 1

    duration = (datetime.now(timezone.utc) - started).total_seconds()

    result = {
        "success": True,
        "mode": mode,
        "apply": apply,
        "ticimax_categories_total": len(tc_cats),
        "targets_processed": len(targets),
        "unmatched_categories": unmatched_categories,        # bizde karşılığı yok
        "unmatched_categories_count": len(unmatched_categories),
        "matched_products_unique": len(seen_product_ids),
        "not_found_products": not_found,                      # Ticimax'ta var, bizde yok (detaylı)
        "not_found_products_count": len(not_found),
        "per_category": per_category_stats,
        "planned_changes_count": len(planned_changes),
        "planned_changes": planned_changes[:1000],            # raporu şişirmemek için ilk 1000
        "applied_products": applied,
        "api_calls": api_calls,
        "duration_sec": round(duration, 1),
    }
    if not apply:
        result["note"] = ("DRY-RUN: hiçbir değişiklik yazılmadı. Raporu kontrol edip "
                          "apply=true ile tekrar çağırarak uygulayabilirsiniz.")
    return result


# ───────────────────────── endpoint'ler ─────────────────────────
@router.post("/sync-categories")
async def sync_ticimax_categories(
    mode: str = Query("en_yeniler", regex="^(en_yeniler|all)$",
                      description="en_yeniler = sadece 'En Yeniler' tam ayna; all = tüm kategoriler"),
    apply: bool = Query(False, description="false=DRY-RUN rapor (varsayılan), true=uygula"),
    aktif: Optional[int] = Query(1, description="1=aktif (varsayılan), 0=pasif, boş=hepsi"),
    page_size: int = Query(50, ge=10, le=100),
    max_per_category: int = Query(5000, ge=10, le=50000),
    sleep_between: float = Query(13.0, ge=0, le=30, description="Ticimax rate limit beklemesi (sn)"),
    current_user: dict = Depends(require_admin),
):
    """
    Ticimax kategori üyeliklerini yerel ürünlere yansıtır.

    mode=en_yeniler (varsayılan): SADECE 'En Yeniler' kategorisi Ticimax'taki
      haliyle BİREBİR aynı olur (eksikler eklenir, fazlalar çıkarılır).
    mode=all: Bu taramada görünen ürünlerin TÜM kategori üyeliği Ticimax'a göre
      yeniden kurulur (riskli — önce apply=false ile raporu inceleyin).

    apply=false (varsayılan) → sadece "ne değişecek" raporu döner, DB'ye dokunmaz.
    apply=true → değişiklikleri products koleksiyonuna uygular.
    """
    res = await _run_category_sync(
        mode=mode, apply=apply, aktif=aktif, page_size=page_size,
        max_per_category=max_per_category, sleep_between=sleep_between,
    )
    try:
        await log_integration_event(
            marketplace="ticimax",
            action=f"category_sync_{mode}{'_apply' if apply else '_dryrun'}",
            status="success" if res.get("success") else "error",
            message=f"matched={res.get('matched_products_unique')} "
                    f"changes={res.get('planned_changes_count')} "
                    f"applied={res.get('applied_products')}",
        )
    except Exception:
        pass
    return res


@router.post("/sync-categories-async")
async def sync_ticimax_categories_async(
    background_tasks: BackgroundTasks,
    mode: str = Query("en_yeniler", regex="^(en_yeniler|all)$"),
    apply: bool = Query(False),
    aktif: Optional[int] = Query(1),
    page_size: int = Query(50, ge=10, le=100),
    max_per_category: int = Query(5000, ge=10, le=50000),
    sleep_between: float = Query(13.0, ge=0, le=30),
    current_user: dict = Depends(require_admin),
):
    """Arka planda çalıştırır (çok kategorili 'all' modunda rate limit yüzünden uzun sürer)."""
    async def _runner():
        try:
            res = await _run_category_sync(
                mode=mode, apply=apply, aktif=aktif, page_size=page_size,
                max_per_category=max_per_category, sleep_between=sleep_between,
            )
            await db.settings.update_one(
                {"id": "ticimax_category_sync_last"},
                {"$set": {"id": "ticimax_category_sync_last",
                          "result": res,
                          "finished_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
            logger.info(f"[cat-sync-async] bitti: {res.get('planned_changes_count')} değişiklik, "
                        f"applied={res.get('applied_products')}")
        except Exception as e:
            logger.error(f"[cat-sync-async] hata: {e}")
            try:
                await log_integration_event(marketplace="ticimax", action="category_sync_async",
                                            status="error", message=str(e))
            except Exception:
                pass

    background_tasks.add_task(_runner)
    return {"success": True, "queued": True, "mode": mode, "apply": apply,
            "message": "Kategori senkronizasyonu arka planda başlatıldı. Sonuç için "
                       "GET /api/admin/ticimax/sync-categories-status çağırın."}


@router.get("/sync-categories-status")
async def sync_ticimax_categories_status(current_user: dict = Depends(require_admin)):
    """Son async kategori senkronizasyonunun sonucunu döner."""
    doc = await db.settings.find_one({"id": "ticimax_category_sync_last"}, {"_id": 0})
    if not doc:
        return {"success": True, "found": False, "message": "Henüz async senkronizasyon çalışmadı."}
    return {"success": True, "found": True, **doc}


# ───────────────────────── bağlantı ayarları ─────────────────────────
@router.get("/settings")
async def get_ticimax_settings(current_user: dict = Depends(require_admin)):
    """Mevcut Ticimax bağlantı ayarını döner (yetki kodu maskelenir)."""
    s = await db.settings.find_one({"id": "ticimax"}, {"_id": 0}) or {}
    key = s.get("api_key") or ""
    masked = (key[:6] + "…" + key[-4:]) if len(key) > 12 else ("***" if key else "")
    return {
        "success": True,
        "domain": s.get("domain") or s.get("api_url") or "",
        "api_key_masked": masked,
        "configured": bool(key),
    }


@router.post("/settings")
async def set_ticimax_settings(
    payload: dict,
    current_user: dict = Depends(require_admin),
):
    """
    Ticimax bağlantı bilgisini kaydeder (kodu elle düzenlemeye gerek kalmadan).
    Beklenen gövde: {"domain": "facette.ticimaxeticaret.com", "api_key": "AKG0M8..."}
    """
    domain = (payload.get("domain") or payload.get("api_url") or "").strip()
    domain = domain.replace("https://", "").replace("http://", "").strip("/")
    api_key = (payload.get("api_key") or "").strip()
    if not domain and not api_key:
        return {"success": False, "error": "domain ve/veya api_key gerekli."}
    set_doc = {"id": "ticimax"}
    if domain:
        set_doc["domain"] = domain
    if api_key:
        set_doc["api_key"] = api_key
    set_doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.settings.update_one({"id": "ticimax"}, {"$set": set_doc}, upsert=True)
    # runtime'a da uygula
    if domain:
        try:
            import ticimax_client as _tc  # type: ignore
            _tc.set_domain(domain)
        except Exception:
            pass
    return {"success": True, "domain": domain or "(değişmedi)", "api_key_set": bool(api_key)}


@router.get("/check-access")
async def check_ticimax_access(current_user: dict = Depends(require_admin)):
    """UrunServis erişimini ve örnek kategori listesini test eder (yetki kodu doğru mu?)."""
    settings = await db.settings.find_one({"id": "ticimax"}) or {}
    api_key = settings.get("api_key") or os.environ.get("TICIMAX_API_KEY") or "AKG0M8DTRSEBAIA898JA6HW22EDIU3"
    domain = settings.get("domain") or settings.get("api_url") or os.environ.get("TICIMAX_DOMAIN")
    import ticimax_client as _tc  # type: ignore
    if domain:
        try:
            _tc.set_domain(domain)
        except Exception:
            pass
    out = {"success": True, "domain": _tc.TICIMAX_DOMAIN}
    try:
        info = _tc.check_urun_service_access(wscode=api_key)
        out["urun_service"] = info
    except Exception as e:
        out["urun_service_error"] = str(e)
    try:
        cats = _tc.get_categories(parent_id=0, wscode=api_key)
        out["root_categories_count"] = len(cats)
        out["root_categories_sample"] = [
            {"ID": c.get("ID"), "Tanim": c.get("Tanim"),
             "AltKategoriSayisi": c.get("AltKategoriSayisi")}
            for c in cats[:30]
        ]
    except Exception as e:
        out["categories_error"] = str(e)
    return out
