"""
Customer account routes - Profile, addresses, orders
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from datetime import datetime, timezone

from .deps import db, logger, get_current_user, require_auth, generate_id

router = APIRouter(tags=["Customer Account"])

def _orders_match_query(current_user: dict) -> dict:
    """Üyenin siparişlerini bulmak için eşleştirme sorgusu.

    SADECE user_id ile eşleştirmek yetmiyor: müşteri siparişi MİSAFİR olarak
    verdiyse (ya da hesabını sonradan açtıysa) siparişin user_id'si boştur ve
    üye panelinde HİÇ görünmez (örn. W10053). Bu yüzden user_id'ye ek olarak
    üyenin KENDİ e-postası ve telefonu ile de eşleştiriyoruz:
      - shipping_address.email  (büyük/küçük harf duyarsız, tam eşleşme)
      - shipping_address.phone  (ayraçlara duyarsız, son 10 hane)
    Böylece misafir verilen siparişler de üyenin panelinde listelenir.
    """
    import re as _re
    uid = current_user.get("id")
    email = (current_user.get("email") or "").strip()
    ors = []
    if uid:
        ors.append({"user_id": uid})
    if email:
        _esc = _re.escape(email)
        ors.append({"shipping_address.email": {"$regex": f"^{_esc}$", "$options": "i"}})
        ors.append({"billing_address.email": {"$regex": f"^{_esc}$", "$options": "i"}})
    # Telefon: kayıttaki numara 905xxxxxxxxx; sipariş adresindeki numara
    # "0 555 123 45 67" gibi ayraçlı olabilir → her hane arasına \D* koyup eşleştir.
    try:
        from notification_service import normalize_phone_tr
        last10 = normalize_phone_tr(current_user.get("phone") or "")[-10:]
        if len(last10) == 10 and last10.isdigit():
            tol = r"\D*".join(list(last10))
            ors.append({"shipping_address.phone": {"$regex": tol}})
    except Exception:
        pass
    if not ors:
        # Güvenlik: hiçbir eşleştirme alanı yoksa yalnız user_id (boş sonuç dönsün,
        # asla tüm siparişleri açma)
        return {"user_id": uid or "__none__"}
    return {"$or": ors} if len(ors) > 1 else ors[0]


async def _link_guest_orders(current_user: dict):
    """Üyenin e-postasıyla MİSAFİR verilmiş (user_id boş) siparişleri kalıcı olarak
    bu üyeye bağla. Yalnız E-POSTA eşleşmesinde yapılır (güçlü kimlik); yalnız
    telefonla eşleşenler bağlanmaz. İdempotent ve best-effort — okuma akışını
    asla kırmaz."""
    try:
        uid = current_user.get("id")
        email = (current_user.get("email") or "").strip()
        if not (uid and email):
            return
        import re as _re
        _esc = _re.escape(email)
        rgx = {"$regex": f"^{_esc}$", "$options": "i"}
        await db.orders.update_many(
            {
                "user_id": {"$in": [None, ""]},
                "$or": [
                    {"shipping_address.email": rgx},
                    {"billing_address.email": rgx},
                ],
            },
            {"$set": {"user_id": uid, "linked_to_member_at": datetime.now(timezone.utc).isoformat()}},
        )
    except Exception as _e:
        logger.warning(f"[my-orders link guest] {_e}")


@router.get("/my-orders")
async def get_my_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(require_auth)
):
    """Get current user's orders — user_id VEYA üyenin e-posta/telefonu ile eşleşenler."""
    # Misafir siparişleri (aynı e-posta) bu üyeye bağla — sonraki sorgular user_id ile de bulur.
    await _link_guest_orders(current_user)

    skip = (page - 1) * limit
    query = _orders_match_query(current_user)

    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.orders.count_documents(query)

    return {
        "orders": orders,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }


@router.get("/track/{code}")
async def track_order_public(code: str):
    """Herkese açık sipariş/kargo takibi.

    Müşteri footer'daki 'Sipariş Takibi' kutusuna SİPARİŞ NUMARASI (W10053) veya
    KARGO TAKİP NUMARASI yazar. İkisini de destekler. TrackOrder.jsx'in beklediği
    şekli döner: order_number, status, status_text, timeline[], shipping_address,
    item_count, total.
    """
    code = (code or "").strip()
    if not code:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    import re as _re
    _esc = _re.escape(code)
    ci = {"$regex": f"^{_esc}$", "$options": "i"}
    order = await db.orders.find_one(
        {"$or": [
            {"order_number": ci},
            {"cargo_tracking_number": ci},
            {"cargo_gonderi_no": ci},
            {"cargo.tracking_number": ci},
            {"cargo.mng_gonderi_no": ci},
        ]},
        {"_id": 0},
    )
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    try:
        from order_statuses import customer_label_for as _clf
    except Exception:
        def _clf(k):  # type: ignore
            return k

    raw_status = (order.get("status") or "pending")
    cargo = order.get("cargo") or {}
    tn = (str(order.get("cargo_tracking_number") or "").strip()
          or str(cargo.get("tracking_number") or "").strip()
          or str(order.get("cargo_gonderi_no") or "").strip())
    track_link = (order.get("cargo_tracking_link") or cargo.get("tracking_link")
                  or (f"https://kargotakip.dhlecommerce.com.tr/?takipNo={tn}" if tn else ""))
    carrier = (order.get("cargo_provider_name") or cargo.get("provider_name")
               or order.get("cargo_company") or "Kargo")

    # Sipariş durumunu 5 aşamalı görünür çizelgeye indir.
    stage_map = {
        "pending": 0, "awaiting_payment": 0, "payment_notified": 0,
        "confirmed": 1,
        "preparing": 2, "processing": 2, "ready_to_ship": 2,
        "shipped": 3, "in_transit": 3, "out_for_delivery": 3, "undelivered": 3,
        "delivered": 4,
    }
    is_cancelled = raw_status in ("cancelled",)
    is_returnish = raw_status in (
        "return_requested", "return_approved", "return_rejected",
        "return_in_transit", "returned", "refunded", "partial_refunded",
    )
    stage = 4 if is_returnish else stage_map.get(raw_status, 0)

    created = order.get("created_at")
    shipped_at = order.get("shipped_at") or order.get("cargo_query_at")
    delivered_at = (cargo.get("teslim_tarihi") or order.get("delivered_at"))

    timeline = [
        {"status": "placed", "title": "Siparişiniz Alındı", "date": created, "completed": True},
        {"status": "confirmed", "title": "Siparişiniz Onaylandı", "date": None, "completed": stage >= 1},
        {"status": "processing", "title": "Hazırlanıyor", "date": None, "completed": stage >= 2},
        {"status": "shipped", "title": "Kargoya Verildi", "date": shipped_at if stage >= 3 else None,
         "completed": stage >= 3,
         **({"tracking_number": tn, "carrier": carrier, "tracking_url": track_link} if (stage >= 3 and tn) else {})},
        {"status": "delivered", "title": "Teslim Edildi", "date": delivered_at if stage >= 4 and not is_returnish else None,
         "completed": stage >= 4 and not is_returnish},
    ]

    if is_cancelled:
        timeline = [
            {"status": "placed", "title": "Siparişiniz Alındı", "date": created, "completed": True},
            {"status": "cancelled", "title": "İptal Edildi",
             "date": order.get("cancelled_at"), "completed": True},
        ]
        top_status = "cancelled"
    elif raw_status == "delivered":
        top_status = "delivered"
    elif stage >= 3:
        top_status = "shipped"
    else:
        top_status = raw_status  # frontend sarı rozet

    ship = order.get("shipping_address") or {}
    return {
        "order_number": order.get("order_number", ""),
        "status": top_status,
        "status_text": _clf(raw_status),
        "timeline": timeline,
        "shipping_address": {
            "first_name": ship.get("first_name", ""),
            "last_name": ship.get("last_name", ""),
            "district": ship.get("district", ""),
            "city": ship.get("city", ""),
        },
        "item_count": sum(int(it.get("quantity", it.get("qty", 1)) or 1) for it in (order.get("items") or [])),
        "total": float(order.get("total") or 0),
    }


# Müşterinin kendi siparişini iptal edebileceği durumlar = "Hazırlanıyor" ÖNCESİ.
# Bu set, frontend butonunun görünürlüğüyle birebir aynı tutulmalıdır.
_CUSTOMER_CANCELLABLE = {"pending", "awaiting_payment", "payment_notified", "confirmed"}


@router.post("/my-orders/{order_id}/cancel")
async def cancel_my_order(order_id: str, current_user: dict = Depends(require_auth)):
    """Üye, kendi siparişini YALNIZCA 'Hazırlanıyor' durumuna geçmeden iptal edebilir.
    Sunucu tarafı guard zorunludur — frontend'in butonu gizlemesine güvenilmez."""
    order = await db.orders.find_one(
        {"$or": [{"id": order_id}, {"order_number": order_id}], "user_id": current_user.get("id")},
        {"_id": 0},
    )
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    cur = order.get("status") or "pending"
    if cur == "cancelled":
        return {"success": True, "status": "cancelled", "message": "Sipariş zaten iptal edilmiş."}
    if cur not in _CUSTOMER_CANCELLABLE:
        raise HTTPException(
            status_code=409,
            detail="Siparişiniz hazırlanmaya başladığı için artık iptal edilemiyor. "
                   "Lütfen bizimle iletişime geçin.",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.orders.update_one(
        {"id": order.get("id")},
        {"$set": {
            "status": "cancelled",
            "updated_at": now_iso,
            "cancelled_at": now_iso,
            "cancel_source": "customer",
            "cancel_reason": "Müşteri iptali (üye paneli)",
        }},
    )

    # Stok geri ekleme — panel/Trendyol iptal akışıyla AYNI idempotent guard (order_cancelled)
    try:
        already = await db.stock_movements.find_one(
            {"order_id": order.get("id"), "type": "order_cancelled"}, {"_id": 1}
        )
        if not already:
            from routes.orders import _stock_delta_for_order
            moves = await _stock_delta_for_order(order, +1)
            await db.stock_movements.insert_one({
                "id": generate_id(),
                "type": "order_cancelled",
                "order_id": order.get("id"),
                "order_number": order.get("order_number", ""),
                "items": moves,
                "source": "customer_cancel",
                "created_at": now_iso,
            })
    except Exception as _e:
        logger.error(f"[customer cancel restock {order_id}] {_e}")

    # Sipariş olay günlüğü (admin tarafında görünür)
    try:
        await db.order_events.insert_one({
            "id": generate_id(),
            "order_id": order.get("id"),
            "order_number": order.get("order_number", ""),
            "event_type": "status",
            "description": "Müşteri siparişi iptal etti (üye paneli)",
            "actor": current_user.get("email", "") or "müşteri",
            "created_at": now_iso,
        })
    except Exception:
        pass

    return {"success": True, "status": "cancelled", "message": "Siparişiniz iptal edildi."}


@router.put("/users/me")
async def update_my_profile(
    profile_data: dict,
    current_user: dict = Depends(require_auth)
):
    """Update current user's profile"""
    allowed_fields = ["first_name", "last_name", "phone"]
    update_data = {k: v for k, v in profile_data.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.users.update_one(
        {"id": current_user.get("id")},
        {"$set": update_data}
    )
    
    return {"success": True, "message": "Profil güncellendi"}

@router.get("/my-addresses")
async def get_my_addresses(current_user: dict = Depends(require_auth)):
    """Get current user's addresses"""
    addresses = await db.addresses.find(
        {"user_id": current_user.get("id")}, 
        {"_id": 0}
    ).to_list(20)
    
    return {"addresses": addresses}

@router.post("/addresses")
async def create_address(
    address_data: dict,
    current_user: dict = Depends(require_auth)
):
    """Create new address"""
    address = {
        "id": generate_id(),
        "user_id": current_user.get("id"),
        "title": address_data.get("title", ""),
        "first_name": address_data.get("first_name", ""),
        "last_name": address_data.get("last_name", ""),
        "phone": address_data.get("phone", ""),
        "address": address_data.get("address", ""),
        "city": address_data.get("city", ""),
        "district": address_data.get("district", ""),
        "postal_code": address_data.get("postal_code", ""),
        "is_default": address_data.get("is_default", False),
        # Kurumsal (Şirket) Fatura Bilgileri
        "is_corporate": bool(address_data.get("is_corporate", False)),
        "company_name": address_data.get("company_name", ""),
        "tax_no": address_data.get("tax_no", ""),
        "tax_office": address_data.get("tax_office", ""),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # If setting as default, unset others
    if address["is_default"]:
        await db.addresses.update_many(
            {"user_id": current_user.get("id")},
            {"$set": {"is_default": False}}
        )
    
    await db.addresses.insert_one(address)
    
    return {"success": True, "address_id": address["id"]}

@router.put("/addresses/{address_id}")
async def update_address(
    address_id: str,
    address_data: dict,
    current_user: dict = Depends(require_auth)
):
    """Update address"""
    # Verify ownership
    address = await db.addresses.find_one({
        "id": address_id, 
        "user_id": current_user.get("id")
    })
    
    if not address:
        raise HTTPException(status_code=404, detail="Adres bulunamadı")
    
    # If setting as default, unset others
    if address_data.get("is_default"):
        await db.addresses.update_many(
            {"user_id": current_user.get("id"), "id": {"$ne": address_id}},
            {"$set": {"is_default": False}}
        )
    
    allowed_fields = ["title", "first_name", "last_name", "phone", "address", "city", "district",
                      "postal_code", "is_default",
                      "is_corporate", "company_name", "tax_no", "tax_office"]
    update_data = {k: v for k, v in address_data.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.addresses.update_one({"id": address_id}, {"$set": update_data})
    
    return {"success": True}

@router.delete("/addresses/{address_id}")
async def delete_address(
    address_id: str,
    current_user: dict = Depends(require_auth)
):
    """Delete address"""
    result = await db.addresses.delete_one({
        "id": address_id,
        "user_id": current_user.get("id")
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Adres bulunamadı")
    
    return {"success": True}


# ==================== FAVORITES (WISHLIST) ====================

@router.get("/favorites/ids")
async def get_my_favorite_ids(current_user: dict = Depends(require_auth)):
    """Sadece favori ürün ID'lerini döndürür (UI kalp durumu için hızlı)."""
    docs = await db.favorites.find(
        {"user_id": current_user.get("id")}, {"_id": 0, "product_id": 1}
    ).to_list(1000)
    return {"product_ids": [d["product_id"] for d in docs]}


@router.get("/favorites")
async def get_my_favorites(current_user: dict = Depends(require_auth)):
    """Favori ürünlerin tam objelerini döndürür."""
    docs = await db.favorites.find(
        {"user_id": current_user.get("id")}, {"_id": 0}
    ).sort("created_at", -1).to_list(1000)
    product_ids = [d["product_id"] for d in docs]
    if not product_ids:
        return {"favorites": []}
    products = await db.products.find(
        {"id": {"$in": product_ids}}, {"_id": 0}
    ).to_list(1000)
    by_id = {p["id"]: p for p in products}
    # favorilerin eklenme sırasını koru
    ordered = [by_id[pid] for pid in product_ids if pid in by_id]
    return {"favorites": ordered}


@router.post("/favorites/merge")
async def merge_favorites(payload: dict, current_user: dict = Depends(require_auth)):
    """Misafir (localStorage) favorilerini login sonrası hesaba taşır.
    NOT: Bu literal route, /favorites/{product_id} parametre route'undan ÖNCE
    tanımlanmalı yoksa FastAPI 'merge'i product_id olarak yakalar."""
    ids = (payload.get("product_ids") or [])[:200]
    added = 0
    for pid in ids:
        if not pid:
            continue
        res = await db.favorites.update_one(
            {"user_id": current_user.get("id"), "product_id": pid},
            {"$setOnInsert": {
                "id": generate_id(),
                "user_id": current_user.get("id"),
                "product_id": pid,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        if res.upserted_id is not None:
            added += 1
    return {"success": True, "merged": added}


@router.post("/favorites/{product_id}")
async def add_favorite(product_id: str, current_user: dict = Depends(require_auth)):
    """Ürünü favorilere ekler (idempotent)."""
    product = await db.products.find_one({"id": product_id}, {"_id": 0, "id": 1})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    await db.favorites.update_one(
        {"user_id": current_user.get("id"), "product_id": product_id},
        {"$setOnInsert": {
            "id": generate_id(),
            "user_id": current_user.get("id"),
            "product_id": product_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {"success": True, "is_favorite": True}


@router.delete("/favorites/{product_id}")
async def remove_favorite(product_id: str, current_user: dict = Depends(require_auth)):
    """Ürünü favorilerden çıkarır."""
    await db.favorites.delete_one({
        "user_id": current_user.get("id"),
        "product_id": product_id,
    })
    return {"success": True, "is_favorite": False}
