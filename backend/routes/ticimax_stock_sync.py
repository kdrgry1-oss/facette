"""
=============================================================================
ticimax_stock_sync.py — Ticimax Web Servis Stok Senkronizasyonu
=============================================================================
Amaç: Ticimax SelectUrun + SelectVaryasyon ile canlı stok değerlerini çekip
yerel `products` koleksiyonunda hem ürün top-level `stock` alanını hem de
`variants[].stock` alanlarını günceller.

Eşleme stratejisi (öncelik sırası):
  1. csv_card_id == Ticimax UrunKartiID (ID alanı)
  2. variants[*].id  == Varyasyon.ID (Ticimax)
  3. variants[*].stock_code == Varyasyon.StokKodu
  4. variants[*].barcode == Varyasyon.Barkod

ENDPOINT:
  POST /api/admin/ticimax/sync-stock?max_products=500&aktif=1
=============================================================================
"""
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import sys, os

# routes -> backend path
_BACKEND_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_PATH not in sys.path:
    sys.path.insert(0, _BACKEND_PATH)

from .deps import db, logger, require_admin
from .marketplace_hub import log_integration_event

router = APIRouter(prefix="/admin/ticimax", tags=["admin-ticimax-stock"])


def _to_dict(zo) -> Dict:
    if zo is None: return {}
    if hasattr(zo, "__values__"):
        try: return dict(zo.__values__)
        except Exception: return {}
    return zo if isinstance(zo, dict) else {}


def _unwrap_variants(raw) -> List[Dict]:
    """`Varyasyonlar` Zeep ArrayOfVaryasyon → list[dict]"""
    if not raw:
        return []
    if hasattr(raw, "__values__"):
        try:
            vals = list(raw.__values__.values())
            raw = vals[0] if vals else []
        except Exception:
            raw = []
    if isinstance(raw, dict):
        # Bazen { "Varyasyon": [...] } formatı
        if "Varyasyon" in raw:
            raw = raw["Varyasyon"]
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    return [_to_dict(v) for v in raw if v]


@router.post("/sync-stock")
async def sync_ticimax_stock(
    max_products: int = Query(2000, ge=10, le=20000),
    aktif: Optional[int] = Query(None, description="1=aktif, 0=pasif, None=hepsi"),
    page_size: int = Query(50, ge=10, le=100),
    current_user: dict = Depends(require_admin),
):
    """Ticimax SelectUrun ile canlı stok değerlerini çek + DB'de güncelle.

    Returns:
      {
        success, ticimax_total, fetched, matched_products, updated_variants,
        not_found, errors, duration_sec
      }
    """
    started = datetime.now(timezone.utc)
    from ticimax_client import get_products, get_product_count  # type: ignore

    settings = await db.settings.find_one({"id": "ticimax"}) or {}
    api_key = settings.get("api_key") or "SSIQWRIYHQWROZGJAEIC2CRRZ5RV5V"

    # 1) Toplam sayı (UI için bilgi)
    try:
        ticimax_total = get_product_count(aktif=aktif, wscode=api_key)
    except Exception as e:
        logger.warning(f"[stock-sync] product count error: {e}")
        ticimax_total = 0

    # 2) Sayfa sayfa SelectUrun
    fetched: List[Dict] = []
    pages_to_fetch = (min(max_products, ticimax_total or max_products) // page_size) + 1
    for page in range(1, pages_to_fetch + 2):
        try:
            chunk = get_products(page=page, page_size=page_size, aktif=aktif, wscode=api_key)
        except Exception as e:
            logger.warning(f"[stock-sync] page {page} err: {e}")
            break
        if not chunk:
            break
        fetched.extend(chunk)
        if len(fetched) >= max_products:
            break
        # Ticimax SelectUrun KayitSayisinaGoreGetir=True olduğu için
        # offset bazlı pagination doğru çalışıyor.
    if len(fetched) > max_products:
        fetched = fetched[:max_products]

    # 3) Her Ticimax ürünü için DB'deki eşleşeni bul ve stok güncelle
    matched_products = 0
    updated_variants_total = 0
    errors: List[str] = []
    not_found_ids: List[int] = []

    for raw in fetched:
        d = _to_dict(raw)
        if not d:
            continue
        tc_card_id = d.get("ID") or d.get("UrunKartiID")
        if not tc_card_id:
            continue
        try:
            tc_card_id = int(tc_card_id)
        except Exception:
            continue

        ticimax_total_stock = float(d.get("ToplamStokAdedi") or 0)
        variants_raw = _unwrap_variants(d.get("Varyasyonlar"))

        # DB ürünü: csv_card_id == tc_card_id
        product_doc = await db.products.find_one(
            {"csv_card_id": tc_card_id}, {"_id": 0, "id": 1, "variants": 1}
        )
        if not product_doc:
            not_found_ids.append(tc_card_id)
            continue
        matched_products += 1

        # Variant bazlı eşleme map: by ID, stock_code, barcode
        local_variants = product_doc.get("variants") or []
        var_map = {}
        for lv in local_variants:
            for k in ("id", "stock_code", "barcode"):
                v = lv.get(k)
                if v: var_map[(k, str(v))] = lv

        # Ticimax variant'larını gez, lokali güncelle
        new_variants: List[Dict] = list(local_variants)  # mutable copy
        new_variants_lookup = {lv.get("id"): idx for idx, lv in enumerate(new_variants) if lv.get("id")}
        local_total_stock = 0
        for tv in variants_raw:
            tv_id   = tv.get("ID") or tv.get("VaryasyonID")
            tv_code = tv.get("StokKodu") or ""
            tv_bar  = tv.get("Barkod") or ""
            tv_stk  = float(tv.get("StokAdedi") or 0)

            local_v = None
            if tv_id and ("id", str(tv_id)) in var_map:
                local_v = var_map[("id", str(tv_id))]
            elif tv_code and ("stock_code", tv_code) in var_map:
                local_v = var_map[("stock_code", tv_code)]
            elif tv_bar and ("barcode", tv_bar) in var_map:
                local_v = var_map[("barcode", tv_bar)]

            if local_v is not None:
                lv_id = local_v.get("id")
                if lv_id in new_variants_lookup:
                    idx = new_variants_lookup[lv_id]
                    if new_variants[idx].get("stock") != int(tv_stk):
                        new_variants[idx] = {**new_variants[idx], "stock": int(tv_stk)}
                        updated_variants_total += 1
                    local_total_stock += int(tv_stk)
            else:
                # Lokal'de yok ama Ticimax'te var — bilgi amaçlı sayım
                local_total_stock += int(tv_stk)

        # Ürün top-level stock güncelle (ya Ticimax'in toplamı ya da local sum)
        new_stock = int(ticimax_total_stock if ticimax_total_stock > 0 else local_total_stock)
        try:
            await db.products.update_one(
                {"id": product_doc["id"]},
                {"$set": {
                    "stock": new_stock,
                    "variants": new_variants,
                    "stock_synced_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
        except Exception as e:
            errors.append(f"product {product_doc['id']}: {e}")

    duration = (datetime.now(timezone.utc) - started).total_seconds()

    # Log'a yaz
    await log_integration_event(
        marketplace="ticimax", action="stock_sync", status="success",
        direction="inbound",
        message=(f"Stok senkronu: {matched_products}/{len(fetched)} ürün eşleşti, "
                 f"{updated_variants_total} varyasyon güncellendi"),
    )

    return {
        "success": True,
        "ticimax_total": ticimax_total,
        "fetched": len(fetched),
        "matched_products": matched_products,
        "updated_variants": updated_variants_total,
        "not_found_in_db": len(not_found_ids),
        "not_found_sample": not_found_ids[:10],
        "errors": errors[:5],
        "duration_sec": round(duration, 2),
        "message": (f"{matched_products} ürün stoğu güncellendi "
                    f"({updated_variants_total} varyasyon) — {round(duration,1)}s")
    }


@router.post("/sync-stock-async")
async def sync_ticimax_stock_async(
    background_tasks: BackgroundTasks,
    max_products: int = Query(5000, ge=10, le=20000),
    aktif: Optional[int] = Query(None),
    page_size: int = Query(50, ge=10, le=100),
    current_user: dict = Depends(require_admin),
):
    """Aynı işlem ama background — admin UI'ya hemen 'started' döner,
    işlem sonu integration_logs'a yazılır."""
    async def _runner():
        try:
            from ticimax_client import get_products  # noqa
            await sync_ticimax_stock(max_products=max_products, aktif=aktif,
                                     page_size=page_size, current_user=current_user)
        except Exception as e:
            await log_integration_event(
                marketplace="ticimax", action="stock_sync", status="error",
                direction="inbound", message=f"Background stok senkron hatası: {e}"
            )
    background_tasks.add_task(_runner)
    return {"success": True, "message": "Stok senkronu arka planda başlatıldı. Otomasyon Durumu > Loglar'dan takip edebilirsiniz."}
