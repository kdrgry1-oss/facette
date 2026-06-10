"""
=============================================================================
ticimax_product_pull.py — Ticimax'tan BELİRLİ ürün kart(lar)ını çekme
=============================================================================
Amaç: Ticimax'taki belirli UrunKartiID'leri, bizim sistemde İSTENEN kart ID
ile YENİ ürün olarak oluşturmak. (Örn: Ticimax 2982 → bizde 2984, 2983 → 2985)

EŞLEME: kaynak (Ticimax UrunKartiID) → hedef (bizim urun_karti_id)
  - Bizdeki ürün: urun_karti_id = hedef (kullanıcının verdiği, ör. 2984)
  - csv_card_id  = kaynak Ticimax UrunKartiID (ör. 2982) → stok/kategori senkronu
                   bununla eşleştirir; kaynak izlenebilir kalır.

GÜVENLİK:
  - Yalnızca BİZDE OLMAYAN ürünleri ekler. Hedef urun_karti_id veya kaynak
    csv_card_id bizde zaten varsa o eşleme ATLANIR (mevcut ürün ezilmez).
  - apply=false (VARSAYILAN) → sadece "ne eklenecek" raporu, DB'ye yazmaz.
  - apply=true → yeni ürünleri products koleksiyonuna ekler.

ENDPOINT:
  POST /api/admin/ticimax/pull-products-by-card?mappings=2982:2984,2983:2985&apply=false
=============================================================================
"""
from fastapi import APIRouter, Depends, Query
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
import sys, os, re, unicodedata

_BACKEND_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_PATH not in sys.path:
    sys.path.insert(0, _BACKEND_PATH)

from .deps import db, logger, require_admin, generate_id, generate_short_id
from .marketplace_hub import log_integration_event

router = APIRouter(prefix="/admin/ticimax", tags=["admin-ticimax-product-pull"])


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


def _slugify(text: str) -> str:
    repl = {"İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ç": "c", "ç": "c",
            "Ğ": "g", "ğ": "g", "Ö": "o", "ö": "o", "Ü": "u", "ü": "u"}
    text = "".join(repl.get(ch, ch) for ch in (text or ""))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "urun"


def _norm(s: Any) -> str:
    repl = {"İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ç": "c", "ç": "c",
            "Ğ": "g", "ğ": "g", "Ö": "o", "ö": "o", "Ü": "u", "ü": "u"}
    s = "".join(repl.get(ch, ch) for ch in (str(s) if s is not None else ""))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _parse_mappings(mappings: str) -> List[Tuple[int, int]]:
    """'2982:2984,2983:2985' → [(2982,2984),(2983,2985)]"""
    out: List[Tuple[int, int]] = []
    for part in (mappings or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        src, dst = part.split(":", 1)
        try:
            out.append((int(src.strip()), int(dst.strip())))
        except Exception:
            continue
    return out


async def _build_local_category_index() -> Tuple[Dict[str, str], Dict[str, Optional[str]], Dict[str, str]]:
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
    for c in cats:
        cid = c.get("id")
        if cid and _norm(c.get("name")) and _norm(c.get("name")) not in name_to_id:
            name_to_id[_norm(c.get("name"))] = cid
    for c in cats:
        cid = c.get("id")
        if not cid:
            continue
        fn = _norm(full_name(cid))
        if fn and fn not in name_to_id:
            name_to_id[fn] = cid
    return name_to_id, parent_map, id_to_name


def _expand_with_ancestors(selected_ids: List[str], parent_map: Dict[str, Optional[str]]) -> List[str]:
    result, seen = [], set()
    for cid in [str(c) for c in (selected_ids or []) if c]:
        cur, guard = cid, 0
        while cur and cur not in seen and guard < 50:
            seen.add(cur)
            result.append(cur)
            cur = parent_map.get(cur)
            guard += 1
    return result


def _fetch_card(source_card_id: int, api_key: str) -> Optional[Dict]:
    """Ticimax'tan tek ürün kartını çeker (urun_karti_id filtresiyle, sonra ID ile doğrular)."""
    from ticimax_client import get_products  # type: ignore
    try:
        rows = get_products(page=1, page_size=50, aktif=None,
                            urun_karti_id=source_card_id, wscode=api_key)
    except Exception as e:
        logger.warning(f"[product-pull] get_products(card={source_card_id}) hata: {e}")
        return None
    rows = [_to_dict(r) for r in (rows or [])]
    # Filtre desteklenmemiş olabilir → dönenler arasında ID/UrunKartiID eşleşeni bul
    for d in rows:
        cid = d.get("ID") or d.get("UrunKartiID") or d.get("UrunID")
        try:
            if cid is not None and int(cid) == int(source_card_id):
                return d
        except Exception:
            continue
    # Tek satır döndüyse ve kimlik okunamadıysa onu kabul et
    if len(rows) == 1:
        return rows[0]
    return None


def _build_variants(source_card_id: int, base_price: float, api_key: str) -> List[Dict]:
    from ticimax_client import get_variants, get_product_images  # type: ignore  # noqa
    out: List[Dict] = []
    try:
        from ticimax_client import get_variants as _gv  # type: ignore
        for v in [_to_dict(x) for x in (_gv(source_card_id, wscode=api_key) or [])]:
            if not v:
                continue
            vp = v.get("SatisFiyat1") or v.get("Fiyat")
            out.append({
                "id": str(v.get("VaryasyonID") or v.get("ID") or generate_id()),
                "ticimax_varyasyon_id": v.get("VaryasyonID") or v.get("ID"),
                "stock_code": str(v.get("StokKodu") or ""),
                "barcode": str(v.get("Barkod") or ""),
                "size": str(v.get("Beden") or v.get("DegerAdi") or v.get("Deger1") or ""),
                "color": str(v.get("Renk") or v.get("RenkAdi") or ""),
                "stock": int(v.get("StokAdedi") or v.get("Miktar") or 0),
                "price": float(vp) if vp else base_price,
                "sale_price": float(v.get("SatisFiyat2")) if v.get("SatisFiyat2") else None,
                "is_active": bool(v.get("AktifMi") if v.get("AktifMi") is not None else True),
            })
    except Exception as e:
        logger.warning(f"[product-pull] varyasyon hata (card={source_card_id}): {e}")
    return out


def _build_images(source_card_id: int, api_key: str) -> List[str]:
    from ticimax_client import get_product_images  # type: ignore
    urls: List[Dict] = []
    try:
        for img in [_to_dict(x) for x in (get_product_images(source_card_id, wscode=api_key) or [])]:
            if not img:
                continue
            u = str(img.get("ResimUrl") or img.get("Url") or img.get("ResimYolu") or img.get("ResimPath") or "")
            if u and not u.startswith("http"):
                u = f"https://www.facette.com.tr{u}"
            if u:
                urls.append({"url": u,
                             "sira": int(img.get("Sira") or img.get("ResimSira") or 0),
                             "ana": bool(img.get("AnaResim") or img.get("IsAnaResim") or False)})
        urls.sort(key=lambda x: (not x["ana"], x["sira"]))
    except Exception as e:
        logger.warning(f"[product-pull] resim hata (card={source_card_id}): {e}")
    return [x["url"] for x in urls]


async def _run_pull(mappings: List[Tuple[int, int]], apply: bool) -> Dict:
    started = datetime.now(timezone.utc)
    import ticimax_client as _tc  # type: ignore

    settings = await db.settings.find_one({"id": "ticimax"}) or {}
    api_key = settings.get("api_key") or os.environ.get("TICIMAX_API_KEY") or "SSIQWRIYHQWROZGJAEIC2CRRZ5RV5V"
    _domain = settings.get("domain") or settings.get("api_url") or os.environ.get("TICIMAX_DOMAIN")
    if _domain:
        try:
            _tc.set_domain(_domain)
        except Exception:
            pass

    name_to_id, parent_map, id_to_name = await _build_local_category_index()
    now_iso = datetime.now(timezone.utc).isoformat()

    planned: List[Dict] = []
    created = 0
    skipped_existing: List[Dict] = []
    not_found: List[int] = []
    errors: List[str] = []

    for source_card, target_card in mappings:
        # 1) Bizde zaten var mı? (hedef kart ID veya kaynak Ticimax referansı)
        exists = await db.products.find_one(
            {"$or": [
                {"urun_karti_id": str(target_card)},
                {"urun_karti_id": target_card},
                {"csv_card_id": source_card},
                {"csv_card_id": str(source_card)},
                {"ticimax_fields.URUNKARTIID": str(target_card)},
            ]},
            {"_id": 0, "id": 1, "name": 1, "urun_karti_id": 1},
        )
        if exists:
            skipped_existing.append({"source_card": source_card, "target_card": target_card,
                                     "existing_product": exists.get("name"),
                                     "existing_id": exists.get("id")})
            continue

        # 2) Ticimax'tan kartı çek
        d = _fetch_card(source_card, api_key)
        if not d:
            not_found.append(source_card)
            continue

        name = str(d.get("UrunAdi") or d.get("Adi") or d.get("Tanim") or "").strip()
        price = float(d.get("SatisFiyat1") or d.get("Fiyat") or d.get("SatisFiyati") or 0)
        sale_price = d.get("SatisFiyat2") or d.get("IndirimliFiyat")
        sale_price = float(sale_price) if sale_price else None
        description = str(d.get("Aciklama") or d.get("UrunAciklama") or d.get("KisaAciklama") or "")
        stock_code = str(d.get("StokKodu") or "")
        barcode = str(d.get("Barkod") or d.get("BarkodNo") or "")
        stock_qty = int(d.get("StokAdedi") or d.get("ToplamStokAdedi") or d.get("Stok") or 0)
        kdv = int(d.get("KDVOrani") or d.get("KdvOrani") or 20)
        brand = str(d.get("MarkaAdi") or d.get("Marka") or "FACETTE")
        category_name = str(d.get("KategoriAdi") or d.get("Kategori") or "")

        # Kategori eşleştir (isim bazlı)
        local_cat_id = name_to_id.get(_norm(category_name)) if category_name else None
        cats = [local_cat_id] if local_cat_id else []
        cat_ids_all = _expand_with_ancestors(cats, parent_map)

        variants = _build_variants(source_card, price, api_key)
        images = _build_images(source_card, api_key)

        doc = {
            "id": await generate_short_id("products"),
            "urun_karti_id": str(target_card),                 # BİZİM yeni kart ID (2984/2985)
            "csv_card_id": source_card,                        # Ticimax kaynak (2982/2983) → senkron eşleşmesi
            "ticimax_source_card_id": source_card,
            "ticimax_fields": {"URUNKARTIID": str(target_card)},
            "name": name or f"Ürün {target_card}",
            "slug": f"{_slugify(name)}-{target_card}",
            "description": description,
            "short_description": "",
            "price": price,
            "sale_price": sale_price,
            "vat_rate": kdv,
            "category_id": local_cat_id or "",
            "category_name": category_name,
            "categories": cats,
            "category_ids": cat_ids_all,
            "brand": brand,
            "images": images,
            "variants": variants,
            "stock": stock_qty,
            "stock_code": stock_code,
            "barcode": barcode,
            "is_active": bool(d.get("Aktif") if d.get("Aktif") is not None else True),
            "is_featured": False,
            "is_new": True,
            "source": "ticimax_pull",
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        planned.append({
            "source_card": source_card, "target_card": target_card,
            "name": doc["name"], "price": price, "variants": len(variants),
            "images": len(images), "category": category_name or "(eşleşmedi)",
            "matched_local_category": id_to_name.get(local_cat_id) if local_cat_id else None,
        })

        if apply:
            try:
                await db.products.insert_one(doc)
                created += 1
            except Exception as e:
                errors.append(f"{source_card}->{target_card}: {e}")

    duration = (datetime.now(timezone.utc) - started).total_seconds()
    result = {
        "success": True,
        "apply": apply,
        "requested": [{"source": s, "target": t} for s, t in mappings],
        "planned": planned,
        "planned_count": len(planned),
        "created": created,
        "skipped_existing": skipped_existing,
        "not_found_on_ticimax": not_found,
        "errors": errors,
        "duration_sec": round(duration, 1),
    }
    if not apply:
        result["note"] = ("DRY-RUN: hiçbir ürün eklenmedi. Raporu kontrol edip apply=true ile "
                          "tekrar çağırarak ekleyebilirsiniz.")
    return result


@router.post("/pull-products-by-card")
async def pull_products_by_card(
    mappings: str = Query(..., description="kaynak:hedef çiftleri, ör: 2982:2984,2983:2985"),
    apply: bool = Query(False, description="false=DRY-RUN (varsayılan), true=ekle"),
    current_user: dict = Depends(require_admin),
):
    """
    Belirli Ticimax ürün kart(lar)ını, istenen hedef kart ID ile YENİ ürün olarak ekler.
    Örnek: mappings=2982:2984,2983:2985  → Ticimax 2982'yi bizde 2984, 2983'ü 2985 yapar.
    Yalnızca bizde olmayanları ekler; mevcut ürünleri ezmez. apply=false → sadece rapor.
    """
    pairs = _parse_mappings(mappings)
    if not pairs:
        return {"success": False, "error": "Geçersiz mappings. Örnek: 2982:2984,2983:2985"}
    res = await _run_pull(pairs, apply=apply)
    try:
        await log_integration_event(
            marketplace="ticimax",
            action=f"product_pull{'_apply' if apply else '_dryrun'}",
            status="success" if res.get("success") else "error",
            message=f"planned={res.get('planned_count')} created={res.get('created')}",
        )
    except Exception:
        pass
    return res
