"""
=============================================================================
production_plan.py — İmalat Planı (18 Sütunlu Tablo) — FAZ 7
=============================================================================

Kullanıcının istediği tabloya birebir karşılık gelen şemalı CRUD.
Manufacturing modülünden ayrı tutuldu (o modül stage-based süreç takibi,
bu modül ise spreadsheet tarzı "üretim planı" listesi).

Sütunlar:
  1. seq_no              (auto)
  2. manufacturer_id     (vendors koleksiyonundan seçilir)
  3. collection          (product.collection'dan default)
  4. model_no            (manuel)
  5. product_description (product.name'den default)
  6. order_qty           (manuel)
  7. price               (product.purchase_price'dan default)
  8. payment_date        (ISO date)
  9. planned_delivery    (payment_date + 21 gün auto)
 10. color               (product.color'dan default)
 11. ok_date             (ISO date)
 12. sample_ok_date      (ISO date)
 13. cut_qty             (manuel)
 14. wash_barcode_date   (ISO date)
 15. inline_qc           ({date, result: "pass"|"fail", image_url})
 16. final_qc            ({date, result, image_url})
 17. actual_delivery     (ISO date, delay_days otomatik)
 18. delivered_qty       (manuel, +%/-% otomatik)
=============================================================================
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .deps import db, require_admin, generate_id

router = APIRouter(prefix="/production-plan", tags=["production-plan"])


class QCRecord(BaseModel):
    date: Optional[str] = None
    result: Optional[str] = None  # "pass" | "fail"
    image_url: Optional[str] = None
    note: Optional[str] = ""


class PlanRowReq(BaseModel):
    product_id: Optional[str] = None
    manufacturer_id: Optional[str] = None
    manufacturer_name: Optional[str] = ""
    collection: Optional[str] = ""
    model_no: Optional[str] = ""
    product_description: Optional[str] = ""
    order_qty: int = 0
    price: float = 0
    payment_date: Optional[str] = None      # ISO date "YYYY-MM-DD"
    planned_delivery: Optional[str] = None  # hesaplanır
    color: Optional[str] = ""
    ok_date: Optional[str] = None
    sample_ok_date: Optional[str] = None
    cut_qty: int = 0
    wash_barcode_date: Optional[str] = None
    inline_qc: Optional[QCRecord] = None
    final_qc: Optional[QCRecord] = None
    actual_delivery: Optional[str] = None
    delivered_qty: int = 0
    notes: Optional[str] = ""


def _add_days_iso(date_str: Optional[str], days: int) -> Optional[str]:
    if not date_str:
        return None
    try:
        d = datetime.fromisoformat(date_str[:10])
        return (d + timedelta(days=days)).date().isoformat()
    except Exception:
        return None


def _compute_derived(doc: Dict[str, Any]) -> Dict[str, Any]:
    # 9 — planned_delivery = payment_date + 21
    if doc.get("payment_date") and not doc.get("planned_delivery"):
        doc["planned_delivery"] = _add_days_iso(doc["payment_date"], 21)

    # 17 — delay_days
    delay_days = None
    if doc.get("planned_delivery") and doc.get("actual_delivery"):
        try:
            pd = datetime.fromisoformat(doc["planned_delivery"][:10])
            ad = datetime.fromisoformat(doc["actual_delivery"][:10])
            delay_days = (ad - pd).days
        except Exception:
            delay_days = None
    doc["delay_days"] = delay_days

    # 18 — qty_diff_pct (delivered_qty > 0 olduğunda anlamlı)
    pct = None
    try:
        oq = float(doc.get("order_qty") or 0)
        dq = float(doc.get("delivered_qty") or 0)
        if oq > 0 and dq > 0:
            pct = round(((dq - oq) / oq) * 100, 1)
    except Exception:
        pct = None
    doc["qty_diff_pct"] = pct
    return doc


@router.get("")
async def list_plan(
    search: Optional[str] = None,
    manufacturer_id: Optional[str] = None,
    collection: Optional[str] = None,
    limit: int = Query(500, le=2000),
    current_user: dict = Depends(require_admin),
):
    q: Dict[str, Any] = {}
    if manufacturer_id:
        q["manufacturer_id"] = manufacturer_id
    if collection:
        q["collection"] = collection
    if search:
        q["$or"] = [
            {"model_no": {"$regex": search, "$options": "i"}},
            {"product_description": {"$regex": search, "$options": "i"}},
            {"manufacturer_name": {"$regex": search, "$options": "i"}},
        ]
    rows = await db.production_plan.find(q, {"_id": 0}).sort("seq_no", 1).to_list(limit)
    return {"items": rows, "total": len(rows)}


@router.post("")
async def create_plan_row(req: PlanRowReq, current_user: dict = Depends(require_admin)):
    # Ürün kartından otomatik doldur (verilmemiş alanlar için)
    product = None
    if req.product_id:
        product = await db.products.find_one({"id": req.product_id}, {"_id": 0})

    data = req.model_dump()
    if product:
        if not data.get("collection"):
            data["collection"] = product.get("collection", "")
        if not data.get("product_description"):
            data["product_description"] = product.get("name", "")
        if not data.get("price"):
            data["price"] = float(product.get("purchase_price") or 0)
        if not data.get("color"):
            data["color"] = product.get("color", "")

    # Üretici ismi
    if req.manufacturer_id and not data.get("manufacturer_name"):
        vendor = await db.vendors.find_one({"id": req.manufacturer_id}, {"_id": 0, "name": 1})
        if vendor:
            data["manufacturer_name"] = vendor.get("name", "")

    # Seq no
    seq_no = (await db.production_plan.count_documents({})) + 1

    doc = {
        "id": generate_id(),
        "seq_no": seq_no,
        **data,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.get("email", ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    doc = _compute_derived(doc)

    await db.production_plan.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "row": doc}


@router.put("/{row_id}")
async def update_plan_row(row_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    existing = await db.production_plan.find_one({"id": row_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")

    # Güncellenebilir alanlar
    allowed = {
        "manufacturer_id", "manufacturer_name", "collection", "model_no",
        "product_description", "order_qty", "price", "payment_date",
        "planned_delivery", "color", "ok_date", "sample_ok_date", "cut_qty",
        "wash_barcode_date", "inline_qc", "final_qc", "actual_delivery",
        "delivered_qty", "notes", "product_id",
    }
    update = {k: v for k, v in (payload or {}).items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()

    # payment_date değiştiyse ve UI planned_delivery göndermediyse yeniden hesap
    if "payment_date" in update and "planned_delivery" not in update:
        update["planned_delivery"] = _add_days_iso(update["payment_date"], 21)

    # Birleştirilmiş doc üzerinden derived hesapla
    merged = {**existing, **update}
    merged = _compute_derived(merged)
    update["delay_days"] = merged.get("delay_days")
    update["qty_diff_pct"] = merged.get("qty_diff_pct")
    update["planned_delivery"] = merged.get("planned_delivery")

    await db.production_plan.update_one({"id": row_id}, {"$set": update})
    return {"success": True, "delay_days": update["delay_days"], "qty_diff_pct": update["qty_diff_pct"], "planned_delivery": update["planned_delivery"]}


@router.delete("/{row_id}")
async def delete_plan_row(row_id: str, current_user: dict = Depends(require_admin)):
    res = await db.production_plan.delete_one({"id": row_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    return {"success": True}


@router.get("/collections")
async def list_collections(current_user: dict = Depends(require_admin)):
    """Distinct koleksiyon listesi — ürün ve plan kayıtlarından."""
    prod_cols = await db.products.distinct("collection")
    plan_cols = await db.production_plan.distinct("collection")
    merged = sorted({c for c in (prod_cols + plan_cols) if c})
    return {"collections": merged}
