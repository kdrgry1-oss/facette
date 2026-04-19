"""
İmalat Takip (Manufacturing) module.

Tracks manufacturing orders end-to-end:
- anlaşma → numune → kumaş → kesim → dikim → kalite → teslim → fatura
- Suppliers, cost lines (F8), purchase orders (F11), fire/waste (F10)
- Stage history per record with user + timestamp
- On "teslim alındı" (delivered/stocked) the product stock is incremented
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone
from typing import Optional
import uuid

from .deps import db, require_admin, logger

router = APIRouter(prefix="/manufacturing", tags=["manufacturing"])


# Canonical stage order
STAGES = [
    "anlasma",               # Anlaşma imzalandı
    "numune_hazirlaniyor",   # Numune hazırlanıyor
    "numune_onaylandi",      # Numune onaylandı
    "kumas_siparisi",        # Kumaş siparişi verildi
    "kumas_teslim",          # Kumaş teslim alındı
    "aksesuar",              # Aksesuar/Tela/İplik
    "kesim",                 # Kesim başladı
    "dikim",                 # Dikim başladı
    "utu_paketleme",         # Ütü/Paketleme
    "kalite_kontrol",        # Kalite Kontrol
    "teslim_alindi",         # Teslim Alındı (Depoya Girdi)
    "fatura_kesildi",        # Fatura Kesildi
]

STAGE_LABELS = {
    "anlasma": "Anlaşma İmzalandı",
    "numune_hazirlaniyor": "Numune Hazırlanıyor",
    "numune_onaylandi": "Numune Onaylandı",
    "kumas_siparisi": "Kumaş Siparişi Verildi",
    "kumas_teslim": "Kumaş Teslim Alındı",
    "aksesuar": "Aksesuar/Tela/İplik",
    "kesim": "Kesim Başladı",
    "dikim": "Dikim Başladı",
    "utu_paketleme": "Ütü / Paketleme",
    "kalite_kontrol": "Kalite Kontrol",
    "teslim_alindi": "Teslim Alındı (Depoya Girdi)",
    "fatura_kesildi": "Fatura Kesildi",
}


@router.get("/stages")
async def get_stages(current_user: dict = Depends(require_admin)):
    return {"stages": [{"key": k, "label": STAGE_LABELS[k]} for k in STAGES]}


@router.get("")
async def list_manufacturing(
    stage: Optional[str] = None,
    search: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    query = {}
    if stage:
        query["current_stage"] = stage
    if search:
        query["$or"] = [
            {"product_name": {"$regex": search, "$options": "i"}},
            {"partner_name": {"$regex": search, "$options": "i"}},
            {"code": {"$regex": search, "$options": "i"}},
        ]
    items = await db.manufacturing.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    # Summary counts per stage
    pipeline = [{"$group": {"_id": "$current_stage", "count": {"$sum": 1}}}]
    counts = {}
    async for row in db.manufacturing.aggregate(pipeline):
        counts[row["_id"] or ""] = row["count"]
    return {"items": items, "counts_by_stage": counts, "total": len(items)}


@router.get("/{record_id}")
async def get_manufacturing(record_id: str, current_user: dict = Depends(require_admin)):
    rec = await db.manufacturing.find_one({"id": record_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    return rec


@router.post("")
async def create_manufacturing(payload: dict, current_user: dict = Depends(require_admin)):
    now_iso = datetime.now(timezone.utc).isoformat()
    # Code: IMLT-yyyy-### incremental
    year = datetime.now(timezone.utc).year
    cnt = await db.manufacturing.count_documents({"code": {"$regex": f"^IMLT-{year}-"}})
    code = f"IMLT-{year}-{cnt + 1:04d}"

    doc = {
        "id": str(uuid.uuid4()),
        "code": code,
        "product_id": payload.get("product_id", ""),
        "product_name": payload.get("product_name", ""),
        "partner_name": payload.get("partner_name", "FACETTE İç Stok"),
        "partner_contact": payload.get("partner_contact", ""),
        "responsible_user": payload.get("responsible_user", current_user.get("email", "")),
        "agreement_date": payload.get("agreement_date", now_iso),
        "expected_delivery_date": payload.get("expected_delivery_date"),
        "size_distribution": payload.get("size_distribution", {}),  # e.g. {"S":10,"M":20}
        "total_units": sum((payload.get("size_distribution") or {}).values()) if payload.get("size_distribution") else payload.get("total_units", 0),
        "unit_price": float(payload.get("unit_price", 0) or 0),
        "agreed_total": float(payload.get("agreed_total", 0) or 0),
        "payments": payload.get("payments", []),
        "cost_lines": payload.get("cost_lines", []),  # F8 – maliyet kalemleri
        "purchase_orders": payload.get("purchase_orders", []),  # F11
        "waste_meters": float(payload.get("waste_meters", 0) or 0),  # F10 – fire
        "supplier_id": payload.get("supplier_id", ""),  # F7
        "current_stage": payload.get("current_stage", STAGES[0]),
        "stage_history": [{
            "stage": payload.get("current_stage", STAGES[0]),
            "label": STAGE_LABELS.get(payload.get("current_stage", STAGES[0]), ""),
            "by": current_user.get("email", ""),
            "at": now_iso,
            "note": "Kayıt oluşturuldu",
        }],
        "files": [],  # F5 – ek dosyalar (base64/url list)
        "notes": payload.get("notes", ""),
        "created_at": now_iso,
        "created_by": current_user.get("email", ""),
        "updated_at": now_iso,
    }

    # Paid/remaining helpers
    doc["paid_total"] = float(sum(p.get("amount", 0) for p in doc["payments"]))
    doc["remaining"] = doc["agreed_total"] - doc["paid_total"]

    await db.manufacturing.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "record": doc}


@router.put("/{record_id}")
async def update_manufacturing(record_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    existing = await db.manufacturing.find_one({"id": record_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for f in (
        "product_id", "product_name", "partner_name", "partner_contact",
        "responsible_user", "expected_delivery_date", "size_distribution",
        "unit_price", "agreed_total", "payments", "cost_lines",
        "purchase_orders", "waste_meters", "supplier_id", "notes",
    ):
        if f in payload:
            update[f] = payload[f]
    if "size_distribution" in payload:
        update["total_units"] = sum((payload.get("size_distribution") or {}).values())
    if "payments" in payload:
        pt = float(sum(p.get("amount", 0) for p in (payload.get("payments") or [])))
        update["paid_total"] = pt
        update["remaining"] = float(payload.get("agreed_total", existing.get("agreed_total", 0)) or existing.get("agreed_total", 0)) - pt
    await db.manufacturing.update_one({"id": record_id}, {"$set": update})
    return {"success": True}


@router.post("/{record_id}/advance")
async def advance_stage(record_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    rec = await db.manufacturing.find_one({"id": record_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    new_stage = payload.get("stage")
    if new_stage not in STAGES:
        raise HTTPException(status_code=400, detail="Geçersiz aşama")

    history = rec.get("stage_history") or []
    history.append({
        "stage": new_stage,
        "label": STAGE_LABELS[new_stage],
        "by": current_user.get("email", ""),
        "at": datetime.now(timezone.utc).isoformat(),
        "note": payload.get("note", ""),
    })
    update = {
        "current_stage": new_stage,
        "stage_history": history,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # F11: On "teslim_alindi" increment stock per size distribution
    if new_stage == "teslim_alindi" and rec.get("product_id"):
        try:
            product = await db.products.find_one({"id": rec["product_id"]}, {"_id": 0, "id": 1, "variants": 1, "stock": 1})
            if product:
                variants = product.get("variants") or []
                size_dist = rec.get("size_distribution") or {}
                total_increment = 0
                for v in variants:
                    size_name = (v.get("size") or v.get("name") or "").strip()
                    qty = int(size_dist.get(size_name, 0) or 0)
                    if qty > 0:
                        v["stock"] = int(v.get("stock", 0) or 0) + qty
                        total_increment += qty
                if not variants and size_dist:
                    # Product-level stock fallback
                    total_increment = sum(int(v or 0) for v in size_dist.values())
                    await db.products.update_one(
                        {"id": product["id"]},
                        {"$inc": {"stock": total_increment}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
                    )
                else:
                    new_total = sum(int(v.get("stock", 0) or 0) for v in variants)
                    await db.products.update_one(
                        {"id": product["id"]},
                        {"$set": {"variants": variants, "stock": new_total, "updated_at": datetime.now(timezone.utc).isoformat()}}
                    )
                await db.stock_movements.insert_one({
                    "id": str(uuid.uuid4()),
                    "type": "manufacturing_delivered",
                    "record_id": record_id,
                    "code": rec.get("code"),
                    "product_id": product["id"],
                    "total_increment": total_increment,
                    "size_distribution": size_dist,
                    "created_by": current_user.get("email", ""),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            logger.error(f"Stock increment on manufacturing delivery failed: {e}")

    await db.manufacturing.update_one({"id": record_id}, {"$set": update})
    return {"success": True, "new_stage": new_stage}


@router.post("/{record_id}/files")
async def add_file(record_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    rec = await db.manufacturing.find_one({"id": record_id}, {"_id": 0, "files": 1})
    if not rec:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    files = rec.get("files") or []
    files.append({
        "id": str(uuid.uuid4()),
        "name": payload.get("name", "dosya"),
        "url": payload.get("url", ""),
        "stage": payload.get("stage", ""),
        "note": payload.get("note", ""),
        "uploaded_by": current_user.get("email", ""),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.manufacturing.update_one({"id": record_id}, {"$set": {"files": files}})
    return {"success": True, "files": files}


@router.delete("/{record_id}")
async def delete_manufacturing(record_id: str, current_user: dict = Depends(require_admin)):
    res = await db.manufacturing.delete_one({"id": record_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    return {"success": True}


# ----- Suppliers (F7) -----
suppliers_router = APIRouter(prefix="/manufacturing-suppliers", tags=["manufacturing-suppliers"])


@suppliers_router.get("")
async def list_suppliers(current_user: dict = Depends(require_admin)):
    items = await db.manufacturing_suppliers.find({}, {"_id": 0}).sort("name", 1).to_list(500)
    return {"items": items}


@suppliers_router.post("")
async def create_supplier(payload: dict, current_user: dict = Depends(require_admin)):
    name = (payload or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tedarikçi adı gerekli")
    doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "type": payload.get("type", "atolye"),  # atolye/kumasci/aksesuarci
        "contact": payload.get("contact", ""),
        "phone": payload.get("phone", ""),
        "address": payload.get("address", ""),
        "quality_rating": int(payload.get("quality_rating", 5) or 5),
        "notes": payload.get("notes", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.get("email", ""),
    }
    await db.manufacturing_suppliers.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "supplier": doc}


@suppliers_router.put("/{sid}")
async def update_supplier(sid: str, payload: dict, current_user: dict = Depends(require_admin)):
    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for f in ("name", "type", "contact", "phone", "address", "quality_rating", "notes"):
        if f in payload:
            update[f] = payload[f]
    res = await db.manufacturing_suppliers.update_one({"id": sid}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tedarikçi bulunamadı")
    return {"success": True}


@suppliers_router.delete("/{sid}")
async def delete_supplier(sid: str, current_user: dict = Depends(require_admin)):
    res = await db.manufacturing_suppliers.delete_one({"id": sid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tedarikçi bulunamadı")
    return {"success": True}
