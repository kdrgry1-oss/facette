"""
Admin routes - Dashboard, stats, settings
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from datetime import datetime, timezone, timedelta

from .deps import db, require_admin, generate_barcode_from_range, logger, generate_id

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/dashboard-stats")
async def get_dashboard_stats(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_admin)
):
    """Get dashboard statistics for admin"""
    try:
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        prev_start = start_date - timedelta(days=days)
        
        # Get totals
        total_orders = await db.orders.count_documents({})
        total_products = await db.products.count_documents({"is_active": True})
        total_customers = await db.users.count_documents({"is_admin": {"$ne": True}})
        
        # Get orders in date range
        orders_in_range = await db.orders.find({
            "created_at": {"$gte": start_date.isoformat()}
        }, {"_id": 0}).to_list(1000)
        
        # Calculate revenue
        total_revenue = sum(o.get("total", 0) for o in orders_in_range)
        
        # Previous period for comparison
        prev_orders = await db.orders.find({
            "created_at": {
                "$gte": prev_start.isoformat(),
                "$lt": start_date.isoformat()
            }
        }, {"_id": 0}).to_list(1000)
        prev_revenue = sum(o.get("total", 0) for o in prev_orders)
        
        # Growth calculations
        growth_orders = ((len(orders_in_range) - len(prev_orders)) / max(len(prev_orders), 1)) * 100 if prev_orders else 0
        growth_revenue = ((total_revenue - prev_revenue) / max(prev_revenue, 1)) * 100 if prev_revenue else 0
        
        # Today's stats
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        orders_today = [o for o in orders_in_range if o.get("created_at", "") >= today_start.isoformat()]
        revenue_today = sum(o.get("total", 0) for o in orders_today)
        
        # Order status breakdown
        status_breakdown = {}
        for order in orders_in_range:
            status = order.get("status", "pending")
            status_breakdown[status] = status_breakdown.get(status, 0) + 1
        
        # Pending and shipped counts
        pending_orders = await db.orders.count_documents({"status": "pending"})
        shipped_orders = await db.orders.count_documents({"status": "shipped"})
        
        # Recent orders
        recent_orders = await db.orders.find(
            {}, {"_id": 0, "id": 1, "order_number": 1, "total": 1, "status": 1, "created_at": 1}
        ).sort("created_at", -1).limit(5).to_list(5)
        
        # Top selling products
        pipeline = [
            {"$unwind": "$items"},
            {"$group": {
                "_id": "$items.name",
                "sold": {"$sum": "$items.quantity"},
                "revenue": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}}
            }},
            {"$sort": {"sold": -1}},
            {"$limit": 5}
        ]
        top_products_cursor = db.orders.aggregate(pipeline)
        top_products = []
        async for p in top_products_cursor:
            top_products.append({
                "name": p["_id"],
                "sold": p["sold"],
                "revenue": p["revenue"]
            })
        
        return {
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "total_products": total_products,
            "total_customers": total_customers,
            "pending_orders": pending_orders,
            "shipped_orders": shipped_orders,
            "orders_today": len(orders_today),
            "revenue_today": revenue_today,
            "growth_orders": round(growth_orders, 1),
            "growth_revenue": round(growth_revenue, 1),
            "recent_orders": recent_orders,
            "top_products": top_products,
            "order_status_breakdown": status_breakdown
        }
        
    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users")
async def get_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    current_user: dict = Depends(require_admin)
):
    """Get users list (admin only)"""
    skip = (page - 1) * limit
    query = {}
    
    if search:
        query["$or"] = [
            {"email": {"$regex": search, "$options": "i"}},
            {"first_name": {"$regex": search, "$options": "i"}},
            {"last_name": {"$regex": search, "$options": "i"}}
        ]
    
    users = await db.users.find(query, {"_id": 0, "password": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.users.count_documents(query)
    
    return {
        "users": users,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

import random

@router.get("/generate-stock-code")
async def generate_stock_code(
    prefix: str = Query("FCSS"),
    current_user: dict = Depends(require_admin)
):
    """Generate a unique 7-digit stock code suffix under the given prefix"""
    existing = await db.products.distinct("stock_code")
    for v_doc in await db.products.find({}, {"variants": 1}).to_list(None):
        for var in v_doc.get("variants", []):
            sc = var.get("stock_code", "")
            if sc:
                existing.append(sc)
    existing_set = set(existing)

    for _ in range(1000):
        suffix = str(random.randint(1000000, 9999999))
        code = f"{prefix}{suffix}"
        if code not in existing_set:
            return {"stock_code": code}
    
    raise HTTPException(status_code=500, detail="Benzersiz stok kodu üretilemedi")

@router.get("/generate-barcode")
async def generate_barcode(
    current_user: dict = Depends(require_admin)
):
    """Generate a unique 13-digit GTIN barcode within the configured range"""
    barcode = await generate_barcode_from_range()
    if not barcode:
        raise HTTPException(
            status_code=400, 
            detail="Barkod üretilemedi. Lütfen Ayarlar sayfasında barkod aralığınızı kontrol edin ve ürünlerinizde çakışma olmadığından emin olun."
        )
    return {"barcode": barcode}

@router.get("/cleanup/dry-run")
async def cleanup_dry_run(current_user: dict = Depends(require_admin)):
    """Salt-okunur veri temizlik raporu (#1 combine + #3 mükerrer varyant).
    HİÇBİR ŞEY DEĞİŞTİRMEZ; sadece rapor döner."""
    from collections import defaultdict

    def _norm(s):
        return str(s or "").strip().lower()

    def _has_image(p):
        imgs = p.get("images") or []
        return bool((imgs and str(imgs[0]).strip()) or str(p.get("image") or "").strip())

    SAMPLE = 50

    # Hafif ürün indeksi (id -> minimal)
    prod = {}
    async for p in db.products.find(
        {}, {"_id": 0, "id": 1, "name": 1, "is_active": 1, "images": 1, "image": 1}
    ):
        if p.get("id") is not None:
            prod[str(p["id"])] = p
    total_products = len(prod)

    # ---- #1  BOZUK combine_products ----
    c1 = {"missing": 0, "inactive": 0, "no_image": 0}
    n_with_combine = 0
    affected = 0
    would_empty = 0
    s1 = []
    async for p in db.products.find(
        {"combine_products": {"$exists": True, "$ne": []}},
        {"_id": 0, "id": 1, "name": 1, "combine_products": 1},
    ):
        ids = p.get("combine_products") or []
        if not ids:
            continue
        n_with_combine += 1
        bad = []
        good = 0
        for cid in ids:
            cid = str(cid)
            ref = prod.get(cid)
            if ref is None:
                c1["missing"] += 1; bad.append([cid, "missing"])
            elif ref.get("is_active") is False:
                c1["inactive"] += 1; bad.append([cid, "inactive"])
            elif not _has_image(ref):
                c1["no_image"] += 1; bad.append([cid, "no_image"])
            else:
                good += 1
        if bad:
            affected += 1
            if good == 0:
                would_empty += 1
            if len(s1) < SAMPLE:
                s1.append({"id": p.get("id"), "name": (p.get("name") or "")[:60],
                           "bad": len(bad), "total": len(ids), "detay": bad[:8]})

    # ---- #3  AYNI BARKOD + AYNI BEDEN mükerrer varyant ----
    # ---- #3  Ürün İÇİNDE aynı BEDEN birden fazla (2x S, 2x L ...) ----
    dup_products = 0
    dup_groups = 0
    dup_extra = 0
    s3 = []
    async for p in db.products.find(
        {"variants.0": {"$exists": True}},
        {"_id": 0, "id": 1, "name": 1, "variants": 1},
    ):
        variants = p.get("variants") or []
        groups = defaultdict(list)
        for i, v in enumerate(variants):
            groups[_norm(v.get("size"))].append(i)   # bedene göre grupla (barkod bağımsız)
        dups = {sz: idxs for sz, idxs in groups.items() if len(idxs) > 1}
        if dups:
            dup_products += 1
            for sz, idxs in dups.items():
                dup_groups += 1
                dup_extra += len(idxs) - 1
                if len(s3) < SAMPLE:
                    detay = [{"barcode": (variants[i].get("barcode") or ""),
                              "stock": variants[i].get("stock")} for i in idxs[:6]]
                    s3.append({"id": p.get("id"), "name": (p.get("name") or "")[:50],
                               "size": sz or "(boş)", "count": len(idxs), "detay": detay})

    # ---- #3b  GLOBAL: farklı ürünlerde AYNI BARKOD (top-level + varyant) ----
    barcode_products = defaultdict(set)
    async for p in db.products.find(
        {}, {"_id": 0, "id": 1, "barcode": 1, "variants": 1}
    ):
        pid = str(p.get("id"))
        bc = _norm(p.get("barcode"))
        if bc:
            barcode_products[bc].add(pid)
        for v in (p.get("variants") or []):
            vb = _norm(v.get("barcode"))
            if vb:
                barcode_products[vb].add(pid)
    cross = {bc: sorted(pids) for bc, pids in barcode_products.items() if len(pids) > 1}
    cross_samples = [{"barcode": bc, "product_ids": pids[:8], "product_count": len(pids)}
                     for bc, pids in list(cross.items())[:SAMPLE]]

    return {
        "total_products": total_products,
        "combine_broken": {
            "products_with_combine": n_with_combine,
            "affected_products": affected,
            "would_empty_after_clean": would_empty,
            "counts": c1,
            "samples": s1,
        },
        "duplicate_variants": {
            "affected_products": dup_products,
            "duplicate_groups": dup_groups,
            "removable_extra_variants": dup_extra,
            "samples": s3,
        },
        "duplicate_barcodes_cross_product": {
            "barcodes_used_by_multiple_products": len(cross),
            "samples": cross_samples,
        },
        "note": "DRY-RUN — hicbir veri degistirilmedi.",
    }


@router.post("/cleanup/dedupe-barcodes")
async def cleanup_dedupe_barcodes(payload: dict = None, current_user: dict = Depends(require_admin)):
    """Ürün İÇİNDE aynı barkodlu mükerrer varyantları siler.
    Her barkoddan EN YÜKSEK STOKLU olanı tutar, diğer kopyalarını kaldırır.
    Barkodsuz varyantlara ve farklı barkodlu (aynı beden bile olsa) varyantlara
    DOKUNMAZ. Başka hiçbir şeyi silmez/değiştirmez.

    payload: {"confirm": true}  -> uygular.   confirm yok/false -> sadece ÖNİZLEME."""
    payload = payload or {}
    confirm = bool(payload.get("confirm", False))

    def _norm(s):
        return str(s or "").strip().lower()

    preview = []
    total_removed = 0
    affected = 0

    async for p in db.products.find(
        {"variants.1": {"$exists": True}},
        {"_id": 0, "id": 1, "name": 1, "variants": 1},
    ):
        variants = p.get("variants") or []
        by_bc = {}
        for v in variants:
            bc = _norm(v.get("barcode"))
            if bc:
                by_bc.setdefault(bc, []).append(v)
        dup_bcs = {bc: vs for bc, vs in by_bc.items() if len(vs) > 1}
        if not dup_bcs:
            continue

        # Her mükerrer barkod için EN YÜKSEK STOKLU varyantın indeksini seç
        best_idx = {}
        for i, v in enumerate(variants):
            bc = _norm(v.get("barcode"))
            if not bc:
                continue
            if bc not in best_idx or (v.get("stock") or 0) > (variants[best_idx[bc]].get("stock") or 0):
                best_idx[bc] = i

        new_variants = []
        removed_here = 0
        for i, v in enumerate(variants):
            bc = _norm(v.get("barcode"))
            if not bc or len(by_bc.get(bc, [])) == 1 or best_idx.get(bc) == i:
                new_variants.append(v)   # barkodsuz / tekil / tutulan -> KORU
            else:
                removed_here += 1        # aynı barkodun fazlası -> SİL

        if removed_here > 0:
            affected += 1
            total_removed += removed_here
            preview.append({
                "id": p.get("id"),
                "name": (p.get("name") or "")[:50],
                "removed": removed_here,
                "kept_total": len(new_variants),
                "barcodes": [
                    {"barcode": bc, "had": len(vs),
                     "kept_stock": max(vs, key=lambda x: (x.get("stock") or 0)).get("stock")}
                    for bc, vs in dup_bcs.items()
                ][:8],
            })
            if confirm:
                await db.products.update_one(
                    {"id": p.get("id")},
                    {"$set": {"variants": new_variants,
                              "updated_at": datetime.now(timezone.utc).isoformat()}},
                )

    return {
        "mode": "APPLIED" if confirm else "PREVIEW",
        "affected_products": affected,
        "removed_variants": total_removed,
        "samples": preview[:80],
        "note": ("Silme uygulandi." if confirm else
                 "ONIZLEME — hicbir sey silinmedi. Uygulamak icin confirm:true gonder."),
    }


@router.post("/cleanup/combine-dead-refs")
async def cleanup_combine_dead_refs(payload: dict = None, current_user: dict = Depends(require_admin)):
    """combine_products ('Görünümü Tamamla') içindeki ÖLÜ referansları temizler:
    var olmayan / is_active=False / görselsiz ürün id'leri listeden çıkarılır.
    Ürünleri/varyantları SİLMEZ — sadece kırık işaretçileri temizler.

    payload: {"confirm": true} -> uygular.  confirm yok/false -> ÖNİZLEME."""
    payload = payload or {}
    confirm = bool(payload.get("confirm", False))

    prod = {}
    async for p in db.products.find(
        {}, {"_id": 0, "id": 1, "is_active": 1, "images": 1, "image": 1}
    ):
        if p.get("id") is not None:
            prod[str(p["id"])] = p

    def _has_image(p):
        imgs = p.get("images") or []
        return bool((imgs and str(imgs[0]).strip()) or str(p.get("image") or "").strip())

    preview = []
    total_removed = 0
    affected = 0
    async for p in db.products.find(
        {"combine_products": {"$exists": True, "$ne": []}},
        {"_id": 0, "id": 1, "name": 1, "combine_products": 1},
    ):
        ids = [str(c) for c in (p.get("combine_products") or [])]
        good = []
        bad = 0
        for cid in ids:
            ref = prod.get(cid)
            if ref is not None and ref.get("is_active") is not False and _has_image(ref):
                good.append(cid)
            else:
                bad += 1
        if bad > 0:
            affected += 1
            total_removed += bad
            preview.append({"id": p.get("id"), "name": (p.get("name") or "")[:50],
                            "removed": bad, "kept": len(good)})
            if confirm:
                await db.products.update_one(
                    {"id": p.get("id")},
                    {"$set": {"combine_products": good,
                              "updated_at": datetime.now(timezone.utc).isoformat()}},
                )

    return {
        "mode": "APPLIED" if confirm else "PREVIEW",
        "affected_products": affected,
        "removed_refs": total_removed,
        "samples": preview[:80],
        "note": ("Temizlik uygulandi." if confirm else
                 "ONIZLEME — hicbir sey degismedi. Uygulamak icin confirm:true gonder."),
    }
