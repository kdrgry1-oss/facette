"""
Reports v2 — Yeni rapor seti (Stok Değer, Yavaş/Hızlı Satan, İade Oranı Uyarısı,
Kanal Bazlı Net Kâr) + product_costs (manuel maliyet) yönetimi.

Endpoints (admin-only):
  GET    /api/admin/reports2/stock-valuation                  — Toplam alış + satış değeri
  GET    /api/admin/reports2/slow-movers?days=60&min_stock=1  — N gündür satılmayan ürünler
  GET    /api/admin/reports2/fast-movers?days=30&top=50       — En hızlı satanlar (velocity)
  GET    /api/admin/reports2/return-rate?threshold=20         — İade oranı X% üzerinde olan ürünler
  GET    /api/admin/reports2/profit-by-channel?days=30        — Site/Trendyol/HB net kâr
  GET    /api/admin/reports2/dead-stock?days=90               — N gündür hiç satılmamış (ölü) stok

  Product costs (manuel maliyet):
  GET    /api/admin/product-costs?q=&page=&limit=
  POST   /api/admin/product-costs                            — { product_id, cost_price }
  POST   /api/admin/product-costs/bulk                        — toplu (Excel sonrası)
"""
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from .deps import db, require_admin, generate_id


router = APIRouter(prefix="/admin/reports2", tags=["admin-reports-v2"])
costs_router = APIRouter(prefix="/admin/product-costs", tags=["product-costs"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days_ago(days: int) -> str:
    return (_now() - timedelta(days=days)).isoformat()


async def _build_cost_map(product_ids: Optional[List[str]] = None) -> dict:
    """product_id → cost_price (manuel girilen). Eksik olanlar fallback olarak
    products.cost_price → products.price*0.5 olarak alınır."""
    q = {}
    if product_ids:
        q["product_id"] = {"$in": product_ids}
    cost_map: dict = {}
    async for c in db.product_costs.find(q, {"_id": 0}):
        cost_map[str(c.get("product_id"))] = float(c.get("cost_price") or 0)
    return cost_map


# ---------------------------------------------------------------------------
# 1) STOK DEĞER RAPORU — Toplam alış + satış değeri
# ---------------------------------------------------------------------------
@router.get("/stock-valuation")
async def stock_valuation(
    brand: Optional[str] = None,
    category: Optional[str] = None,
    manufacturer: Optional[str] = None,
    _=Depends(require_admin),
):
    """Elinizdeki stoğun toplam alış (manuel maliyet) ve satış (price) değerini hesaplar.
    İsteğe bağlı brand/category/manufacturer filtresi.
    """
    q: dict = {"stock": {"$gt": 0}}
    if brand: q["brand"] = brand
    if category: q["category"] = category
    if manufacturer: q["manufacturer"] = manufacturer

    cost_map = await _build_cost_map()

    total_units = 0
    total_sale_value = 0.0
    total_cost_value = 0.0
    by_brand: dict = defaultdict(lambda: {"units": 0, "cost": 0.0, "sale": 0.0})
    by_category: dict = defaultdict(lambda: {"units": 0, "cost": 0.0, "sale": 0.0})
    cursor = db.products.find(q, {"_id": 0, "id": 1, "name": 1, "stock": 1, "price": 1,
                                    "brand": 1, "category": 1, "cost_price": 1, "stock_code": 1})
    async for p in cursor:
        units = int(p.get("stock") or 0)
        sale = float(p.get("price") or 0)
        cost = cost_map.get(str(p.get("id")))
        if cost is None:
            cost = float(p.get("cost_price") or 0) or round(sale * 0.5, 2)
        total_units += units
        total_sale_value += units * sale
        total_cost_value += units * cost
        b = p.get("brand") or "—"
        c = p.get("category") or "—"
        by_brand[b]["units"] += units
        by_brand[b]["cost"] += units * cost
        by_brand[b]["sale"] += units * sale
        by_category[c]["units"] += units
        by_category[c]["cost"] += units * cost
        by_category[c]["sale"] += units * sale

    margin = (total_sale_value - total_cost_value)
    margin_pct = (margin / total_sale_value * 100) if total_sale_value else 0

    return {
        "totals": {
            "units": total_units,
            "cost_value": round(total_cost_value, 2),
            "sale_value": round(total_sale_value, 2),
            "potential_profit": round(margin, 2),
            "potential_margin_pct": round(margin_pct, 2),
        },
        "by_brand": [{"name": k, **{x: round(v[x], 2) if x != "units" else v[x] for x in v}}
                     for k, v in sorted(by_brand.items(), key=lambda kv: -kv[1]["sale"])[:50]],
        "by_category": [{"name": k, **{x: round(v[x], 2) if x != "units" else v[x] for x in v}}
                        for k, v in sorted(by_category.items(), key=lambda kv: -kv[1]["sale"])[:50]],
        "checked_at": _now().isoformat(),
    }


# ---------------------------------------------------------------------------
# 2) HIZLI / YAVAŞ SATAN ÜRÜNLER — velocity bazlı
# ---------------------------------------------------------------------------
async def _velocity_aggregate(days: int):
    since = _days_ago(days)
    pipeline = [
        {"$match": {"created_at": {"$gte": since}, "status": {"$nin": ["cancelled", "returned"]}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.product_id",
            "name": {"$first": "$items.name"},
            "sold_qty": {"$sum": {"$ifNull": ["$items.quantity", 1]}},
            "revenue": {"$sum": {"$multiply": [{"$ifNull": ["$items.quantity", 1]},
                                                 {"$ifNull": ["$items.price", 0]}]}},
            "order_count": {"$sum": 1},
        }},
    ]
    out = []
    async for r in db.orders.aggregate(pipeline):
        if not r["_id"]:
            continue
        out.append({
            "product_id": str(r["_id"]),
            "name": r.get("name") or "—",
            "sold_qty": int(r["sold_qty"]),
            "revenue": round(float(r["revenue"]), 2),
            "order_count": int(r["order_count"]),
            "daily_velocity": round(r["sold_qty"] / max(days, 1), 3),
        })
    return out


@router.get("/fast-movers")
async def fast_movers(
    days: int = Query(30, ge=1, le=365),
    top: int = Query(50, ge=1, le=500),
    _=Depends(require_admin),
):
    """En hızlı satan ürünler. velocity = adet / gün. Stok tükenme tahmini eklenir."""
    items = await _velocity_aggregate(days)
    items.sort(key=lambda x: -x["sold_qty"])
    items = items[:top]
    # Stok bilgisini ekle
    ids = [i["product_id"] for i in items]
    stock_map = {}
    async for p in db.products.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "stock": 1, "stock_code": 1, "price": 1, "brand": 1, "category": 1}):
        stock_map[str(p["id"])] = p
    for it in items:
        p = stock_map.get(it["product_id"]) or {}
        it["stock"] = int(p.get("stock") or 0)
        it["stock_code"] = p.get("stock_code")
        it["price"] = float(p.get("price") or 0)
        it["brand"] = p.get("brand")
        it["category"] = p.get("category")
        # Stok tükenme tahmini (gün)
        it["days_until_stockout"] = int(it["stock"] / it["daily_velocity"]) if it["daily_velocity"] > 0 else None
    return {"days": days, "items": items}


@router.get("/slow-movers")
async def slow_movers(
    days: int = Query(60, ge=1, le=365),
    min_stock: int = Query(1, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _=Depends(require_admin),
):
    """N gün içinde N adetten az satan ama stoğu olan ürünler.
    `days` = bakılan periyot, `min_stock` = minimum stok eşiği.
    """
    # Önce satılanları topla
    sold = {it["product_id"]: it for it in await _velocity_aggregate(days)}
    items = []
    cursor = db.products.find({"stock": {"$gte": min_stock}},
                               {"_id": 0, "id": 1, "name": 1, "stock": 1, "price": 1, "stock_code": 1,
                                "brand": 1, "category": 1, "created_at": 1})
    async for p in cursor:
        pid = str(p["id"])
        sold_info = sold.get(pid)
        sold_qty = sold_info["sold_qty"] if sold_info else 0
        # "Yavaş satan" tanımı: günlük velocity < 0.1 (yani 30 günde 3 adetten az)
        velocity = (sold_qty / days) if days else 0
        if velocity < 0.1:
            items.append({
                "product_id": pid,
                "name": p.get("name"),
                "stock_code": p.get("stock_code"),
                "stock": int(p.get("stock") or 0),
                "sold_qty_period": sold_qty,
                "daily_velocity": round(velocity, 3),
                "price": float(p.get("price") or 0),
                "brand": p.get("brand"),
                "category": p.get("category"),
                "tied_value": round(int(p.get("stock") or 0) * float(p.get("price") or 0), 2),
            })
    items.sort(key=lambda x: -x["tied_value"])
    return {"days": days, "min_stock": min_stock, "total": len(items), "items": items[:limit]}


@router.get("/dead-stock")
async def dead_stock(
    days: int = Query(90, ge=30, le=730),
    _=Depends(require_admin),
):
    """N gündür HİÇ satılmamış stokta olan ürünler — likidasyon/kampanya adayları."""
    sold_ids = set()
    pipeline = [
        {"$match": {"created_at": {"$gte": _days_ago(days)}}},
        {"$unwind": "$items"},
        {"$group": {"_id": "$items.product_id"}},
    ]
    async for r in db.orders.aggregate(pipeline):
        if r["_id"]: sold_ids.add(str(r["_id"]))

    items = []
    cursor = db.products.find({"stock": {"$gt": 0}},
                               {"_id": 0, "id": 1, "name": 1, "stock": 1, "price": 1, "stock_code": 1, "brand": 1})
    async for p in cursor:
        if str(p["id"]) in sold_ids:
            continue
        items.append({
            "product_id": str(p["id"]),
            "name": p.get("name"),
            "stock_code": p.get("stock_code"),
            "stock": int(p.get("stock") or 0),
            "price": float(p.get("price") or 0),
            "brand": p.get("brand"),
            "tied_value": round(int(p.get("stock") or 0) * float(p.get("price") or 0), 2),
        })
    items.sort(key=lambda x: -x["tied_value"])
    return {"days": days, "total": len(items), "items": items[:500]}


# ---------------------------------------------------------------------------
# 3) İADE ORANI UYARISI — eşik aşan ürünler
# ---------------------------------------------------------------------------
@router.get("/return-rate")
async def return_rate(
    threshold: float = Query(20.0, ge=0, le=100, description="Yüzde eşiği (örn: 20)"),
    days: int = Query(90, ge=7, le=365),
    min_orders: int = Query(5, ge=1, description="En az kaç sipariş olmalı"),
    _=Depends(require_admin),
):
    """Belirli periyotta iade oranı `threshold`% üzerinde olan ürünleri listeler."""
    since = _days_ago(days)
    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.product_id",
            "name": {"$first": "$items.name"},
            "total_sold": {"$sum": {"$cond": [{"$ne": ["$status", "cancelled"]},
                                                {"$ifNull": ["$items.quantity", 1]}, 0]}},
            "returned_qty": {"$sum": {"$cond": [{"$eq": ["$status", "returned"]},
                                                  {"$ifNull": ["$items.quantity", 1]}, 0]}},
        }},
        {"$match": {"total_sold": {"$gte": min_orders}}},
    ]
    items = []
    async for r in db.orders.aggregate(pipeline):
        sold = int(r.get("total_sold") or 0)
        ret = int(r.get("returned_qty") or 0)
        if sold == 0:
            continue
        rate = (ret / sold) * 100
        if rate >= threshold:
            items.append({
                "product_id": str(r["_id"]),
                "name": r.get("name") or "—",
                "sold": sold,
                "returned": ret,
                "return_rate_pct": round(rate, 2),
                "severity": "critical" if rate >= 40 else ("high" if rate >= 30 else "warning"),
            })
    items.sort(key=lambda x: -x["return_rate_pct"])
    return {"threshold": threshold, "days": days, "total": len(items), "items": items}


# ---------------------------------------------------------------------------
# 4) KANAL BAZLI NET KÂR — Site / Trendyol / HB ...
# ---------------------------------------------------------------------------
@router.get("/profit-by-channel")
async def profit_by_channel(
    days: int = Query(30, ge=1, le=365),
    _=Depends(require_admin),
):
    """Her kanal için: satış, maliyet, komisyon (varsa), kargo, iade, net kâr."""
    since = _days_ago(days)

    # Pazaryeri komisyon varsayılanları (yüzde) — gelecekte ayrı config'den okunabilir
    DEFAULT_COMMISSION_PCT = {
        "trendyol": 18.0, "hepsiburada": 17.0, "n11": 12.0, "amazon": 15.0,
        "temu": 5.0, "ciceksepeti": 12.0, "pttavm": 8.0,
        "site": 3.0, "manual": 0.0,
    }

    cost_map = await _build_cost_map()

    pipeline = [
        {"$match": {"created_at": {"$gte": since}, "status": {"$ne": "cancelled"}}},
        {"$project": {
            "channel": {"$ifNull": ["$marketplace", "$source", "site"]},
            "status": 1, "items": 1, "total": 1, "shipping_total": 1,
        }},
    ]
    rows: dict = defaultdict(lambda: {
        "orders": 0, "revenue": 0.0, "cost": 0.0, "shipping": 0.0,
        "commission": 0.0, "refunds": 0.0,
    })
    async for o in db.orders.aggregate(pipeline):
        ch = (o.get("channel") or "site").lower()
        rows[ch]["orders"] += 1
        rev = float(o.get("total") or 0)
        rows[ch]["revenue"] += rev
        rows[ch]["shipping"] += float(o.get("shipping_total") or 0)
        # Maliyet: items üzerinden cost_map ile çarpım
        for it in (o.get("items") or []):
            pid = str(it.get("product_id") or "")
            qty = int(it.get("quantity") or 1)
            price = float(it.get("price") or 0)
            cost = cost_map.get(pid)
            if cost is None:
                cost = round(price * 0.5, 2)
            rows[ch]["cost"] += qty * cost
        # Komisyon (yaklaşık)
        rows[ch]["commission"] += rev * (DEFAULT_COMMISSION_PCT.get(ch, 5.0) / 100)
        # İade
        if o.get("status") == "returned":
            rows[ch]["refunds"] += rev

    out = []
    for ch, r in rows.items():
        net = r["revenue"] - r["cost"] - r["commission"] - r["refunds"]
        margin = (net / r["revenue"] * 100) if r["revenue"] else 0
        out.append({
            "channel": ch,
            "orders": r["orders"],
            "revenue": round(r["revenue"], 2),
            "cost": round(r["cost"], 2),
            "commission": round(r["commission"], 2),
            "shipping": round(r["shipping"], 2),
            "refunds": round(r["refunds"], 2),
            "net_profit": round(net, 2),
            "margin_pct": round(margin, 2),
            "commission_pct": DEFAULT_COMMISSION_PCT.get(ch, 5.0),
        })
    out.sort(key=lambda x: -x["net_profit"])

    # Toplam satır
    totals = {
        "orders": sum(r["orders"] for r in out),
        "revenue": round(sum(r["revenue"] for r in out), 2),
        "cost": round(sum(r["cost"] for r in out), 2),
        "commission": round(sum(r["commission"] for r in out), 2),
        "refunds": round(sum(r["refunds"] for r in out), 2),
        "net_profit": round(sum(r["net_profit"] for r in out), 2),
    }
    if totals["revenue"]:
        totals["margin_pct"] = round(totals["net_profit"] / totals["revenue"] * 100, 2)
    else:
        totals["margin_pct"] = 0
    return {"days": days, "items": out, "totals": totals}


# ---------------------------------------------------------------------------
# Manuel maliyet (product_costs) yönetimi
# ---------------------------------------------------------------------------
class ProductCostIn(BaseModel):
    product_id: str
    cost_price: float = Field(..., ge=0)
    currency: str = "TRY"


@costs_router.get("")
async def list_costs(
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    only_missing: bool = Query(False, description="Sadece maliyeti girilmemiş ürünleri göster"),
    _=Depends(require_admin),
):
    """Ürün listesi + manuel girilmiş maliyet. only_missing=true ile sadece eksik olanlar."""
    cost_map = await _build_cost_map()
    pq: dict = {}
    if q:
        pq["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"stock_code": {"$regex": q, "$options": "i"}},
            {"sku": {"$regex": q, "$options": "i"}},
        ]
    skip = (page - 1) * limit
    cursor = db.products.find(pq, {"_id": 0, "id": 1, "name": 1, "stock_code": 1,
                                    "price": 1, "stock": 1, "brand": 1, "category": 1}) \
                       .skip(skip).limit(limit if not only_missing else limit * 3)
    items = []
    async for p in cursor:
        pid = str(p["id"])
        cost = cost_map.get(pid)
        if only_missing and cost is not None:
            continue
        price = float(p.get("price") or 0)
        items.append({
            "product_id": pid,
            "name": p.get("name"),
            "stock_code": p.get("stock_code"),
            "stock": int(p.get("stock") or 0),
            "price": price,
            "cost_price": cost,
            "brand": p.get("brand"),
            "category": p.get("category"),
            "margin_pct": round((price - cost) / price * 100, 2) if (cost and price) else None,
        })
        if len(items) >= limit:
            break
    total = await db.products.count_documents(pq)
    return {"items": items, "total": total, "page": page, "limit": limit}


@costs_router.post("")
async def upsert_cost(payload: ProductCostIn, admin=Depends(require_admin)):
    now = _now().isoformat()
    await db.product_costs.update_one(
        {"product_id": payload.product_id},
        {"$set": {
            "product_id": payload.product_id,
            "cost_price": payload.cost_price,
            "currency": payload.currency,
            "updated_by": admin.get("email"),
            "updated_at": now,
        }, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return {"ok": True, "product_id": payload.product_id, "cost_price": payload.cost_price}


class BulkCostIn(BaseModel):
    items: List[ProductCostIn]


@costs_router.post("/bulk")
async def bulk_upsert_costs(payload: BulkCostIn, admin=Depends(require_admin)):
    if not payload.items:
        return {"ok": True, "count": 0}
    now = _now().isoformat()
    from pymongo import UpdateOne
    ops = []
    for it in payload.items:
        ops.append(UpdateOne(
            {"product_id": it.product_id},
            {"$set": {
                "product_id": it.product_id,
                "cost_price": it.cost_price,
                "currency": it.currency,
                "updated_by": admin.get("email"),
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        ))
    if ops:
        await db.product_costs.bulk_write(ops)
    return {"ok": True, "count": len(ops)}
