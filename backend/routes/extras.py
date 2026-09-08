"""
Abandoned Cart (Terkedilmiş Sepet) + Product Reviews + SEO Redirects.

Three lightweight modules packed together to save routes:

1. ABANDONED CART
   - Public: POST /api/cart/track     – storefront saves current cart state per session
   - Admin : GET  /api/admin/abandoned-carts  – list pending (>1h old, no order)

2. PRODUCT REVIEWS
   - Public: POST /api/reviews                      – submit (authenticated user)
   - Public: GET  /api/reviews/product/{pid}        – approved reviews for a product
   - Admin : GET  /api/admin/reviews?status=pending|approved|rejected
   - Admin : PUT  /api/admin/reviews/{rid}          – set status

3. SEO REDIRECTS
   - Admin : CRUD /api/admin/redirects (from_path, to_path, status_code 301/302)
   - Public: GET /api/seo/resolve-redirect?path=... – storefront calls on 404
   - Admin : GET /api/admin/seo/meta-overrides / PUT (product/category meta overrides)
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import os
import re as _re

from fastapi import Request
from .deps import db, require_admin, require_auth, logger, safe_str, get_current_user, limiter
from tenant_config import TenantConfig, get_tenant_config, invalidate as invalidate_tenant_config
from seo_runtime import resolve_product, resolve_category


# --------------- ABANDONED CART ---------------

cart_router = APIRouter(prefix="/cart", tags=["cart-tracking"])
admin_cart_router = APIRouter(prefix="/admin/abandoned-carts", tags=["admin-abandoned-carts"])


@cart_router.post("/track")
@(limiter.limit("60/minute") if limiter else (lambda f: f))
async def track_cart(payload: dict, request: Request,
                     current_user: dict = Depends(get_current_user)):
    """Storefront saves live cart. Called on add/remove/update. Anonymous OK.
    Payload: { session_id, items:[{product_id,name,qty,price,image}], total, email?, phone? }
    GÜVENLİK (DENETİM SEC-4 F1): session_id/email/phone artık safe_str ile string'e zorlanır
    ({"$ne":null} gibi NoSQL operatör enjeksiyonu ile başka müşterinin sepetini ezme engellendi);
    user_id İSTEMCİDEN DEĞİL yalnız doğrulanmış JWT'den alınır (rastgele hesaba sepet bağlama engeli)."""
    sid = safe_str(payload.get("session_id") or "", 80) or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    _items = payload.get("items")
    if not isinstance(_items, list):
        _items = []
    doc = {
        "session_id": sid,
        # user_id yalnız token'dan (istemci iddiasına GÜVENİLMEZ)
        "user_id": (current_user or {}).get("id"),
        "email": safe_str(payload.get("email") or "", 200),
        "phone": safe_str(payload.get("phone") or "", 32),
        "items": _items[:100],
        "total": float(payload.get("total", 0) or 0),
        "updated_at": now,
    }
    await db.cart_sessions.update_one(
        {"session_id": sid},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return {"session_id": sid}


@cart_router.post("/mark-ordered")
@(limiter.limit("60/minute") if limiter else (lambda f: f))
async def mark_cart_ordered(payload: dict, request: Request):
    """Remove session from abandoned pool after successful order."""
    sid = safe_str(payload.get("session_id") or "", 80)  # SEC-4 F1: operatör enjeksiyonu engeli
    if sid:
        await db.cart_sessions.delete_one({"session_id": sid})
    return {"success": True}


@admin_cart_router.get("")
async def list_abandoned(
    hours: int = Query(1, ge=1, le=720),
    current_user: dict = Depends(require_admin),
):
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    q = {"updated_at": {"$lte": cutoff}, "total": {"$gt": 0}, "$expr": {"$gt": [{"$size": {"$ifNull": ["$items", []]}}, 0]}}
    rows = await db.cart_sessions.find(q, {"_id": 0}).sort("updated_at", -1).to_list(300)
    # Enrich with user info where possible
    for r in rows:
        if r.get("user_id"):
            u = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "email": 1, "first_name": 1, "last_name": 1, "phone": 1})
            if u:
                r["user"] = u
    total_value = round(sum(r.get("total", 0) for r in rows), 2)
    return {"items": rows, "total": len(rows), "total_value": total_value}


@admin_cart_router.delete("/{sid}")
async def delete_abandoned(sid: str, current_user: dict = Depends(require_admin)):
    await db.cart_sessions.delete_one({"session_id": sid})
    return {"success": True}


# --------------- PRODUCT REVIEWS ---------------

reviews_public_router = APIRouter(prefix="/reviews", tags=["reviews"])
reviews_admin_router = APIRouter(prefix="/admin/reviews", tags=["admin-reviews"])


@reviews_public_router.post("")
async def submit_review(payload: dict, current_user: dict = Depends(require_auth)):
    pid = payload.get("product_id")
    rating = int(payload.get("rating", 0) or 0)
    if not pid or rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Ürün ID ve 1-5 arası puan gerekli")
    doc = {
        "id": str(uuid.uuid4()),
        "product_id": pid,
        "user_id": current_user.get("id"),
        "user_name": f"{current_user.get('first_name','')} {current_user.get('last_name','')}".strip() or current_user.get("email", ""),
        "rating": rating,
        "title": payload.get("title", "")[:120],
        "comment": payload.get("comment", "")[:2000],
        "status": "pending",  # pending | approved | rejected
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.reviews.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "review": doc, "message": "Yorumunuz moderasyon sonrası yayınlanacaktır"}


@reviews_public_router.get("/product/{pid}")
async def list_approved_reviews(pid: str, limit: int = Query(50, ge=1, le=200)):
    # 1) Müşteri yorumları (db.reviews, onaylı)
    rows = await db.reviews.find(
        {"product_id": pid, "status": "approved"}, {"_id": 0, "user_id": 0}
    ).sort("created_at", -1).to_list(limit)

    # 2) Trendyol'dan çekilen yorumlar (db.product_reviews, approved:True) — aynı listede göster.
    #    Şema normalize edilir: comment/rating/user_name/created_at + source=trendyol rozeti.
    ty = await db.product_reviews.find(
        {"product_id": pid, "approved": True},
        {"_id": 0, "id": 1, "rating": 1, "title": 1, "comment": 1, "user_name": 1,
         "is_verified": 1, "comment_date": 1, "created_at": 1, "source": 1},
    ).sort("comment_date", -1).to_list(limit)
    for r in ty:
        r.setdefault("user_name", "Trendyol Müşterisi")
        r["source"] = "trendyol"
        r["verified"] = bool(r.get("is_verified"))
        # created_at yoksa comment_date'i kullan (sıralama için)
        if not r.get("created_at"):
            r["created_at"] = r.get("comment_date") or ""

    merged = rows + ty
    # En yeni önce; tarih string ISO olduğundan lexicographic sıralama doğru çalışır
    merged.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    merged = merged[:limit]

    total_all = len(rows) + len(ty)
    all_ratings = [r["rating"] for r in rows] + [r.get("rating", 0) for r in ty]
    avg = round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else 0
    return {"items": merged, "total": total_all, "average_rating": avg}


@reviews_admin_router.get("")
async def admin_list_reviews(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_admin),
):
    q: dict = {}
    if status:
        q["status"] = status
    total = await db.reviews.count_documents(q)
    skip = (page - 1) * limit
    rows = await db.reviews.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    # attach product name
    for r in rows:
        p = await db.products.find_one({"id": r.get("product_id")}, {"_id": 0, "name": 1})
        r["product_name"] = p.get("name") if p else "—"
    return {"items": rows, "total": total, "page": page, "pages": (total + limit - 1) // limit}


@reviews_admin_router.put("/{rid}")
async def update_review(rid: str, payload: dict, current_user: dict = Depends(require_admin)):
    allowed_status = {"pending", "approved", "rejected"}
    new_status = payload.get("status")
    if new_status and new_status not in allowed_status:
        raise HTTPException(status_code=400, detail="Geçersiz durum")
    update = {}
    if new_status:
        update["status"] = new_status
        update["moderated_at"] = datetime.now(timezone.utc).isoformat()
        update["moderated_by"] = current_user.get("email", "")
    if "admin_reply" in payload:
        update["admin_reply"] = payload["admin_reply"][:2000]
    res = await db.reviews.update_one({"id": rid}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Yorum bulunamadı")
    return {"success": True}


@reviews_admin_router.delete("/{rid}")
async def delete_review(rid: str, current_user: dict = Depends(require_admin)):
    res = await db.reviews.delete_one({"id": rid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Yorum bulunamadı")
    return {"success": True}


# --------------- SEO: 301 REDIRECTS + META OVERRIDES ---------------

seo_public_router = APIRouter(prefix="/seo", tags=["seo"])
seo_admin_router = APIRouter(prefix="/admin/seo", tags=["admin-seo"])


@seo_admin_router.get("/redirects")
async def list_redirects(current_user: dict = Depends(require_admin)):
    items = await db.seo_redirects.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"items": items}


@seo_admin_router.post("/redirects")
async def create_redirect(payload: dict, current_user: dict = Depends(require_admin)):
    from_path = (payload.get("from_path") or "").strip()
    to_path = (payload.get("to_path") or "").strip()
    if not from_path or not to_path:
        raise HTTPException(status_code=400, detail="from_path ve to_path gerekli")
    if not from_path.startswith("/"):
        from_path = "/" + from_path
    if not to_path.startswith("/") and not to_path.startswith("http"):
        to_path = "/" + to_path
    code = int(payload.get("status_code", 301))
    if code not in (301, 302):
        code = 301
    doc = {
        "id": str(uuid.uuid4()),
        "from_path": from_path.lower(),
        "to_path": to_path,
        "status_code": code,
        "hits": 0,
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.seo_redirects.update_one({"from_path": doc["from_path"]}, {"$set": doc}, upsert=True)
    return {"success": True, "redirect": doc}


@seo_admin_router.delete("/redirects/{rid}")
async def delete_redirect(rid: str, current_user: dict = Depends(require_admin)):
    res = await db.seo_redirects.delete_one({"id": rid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Yönlendirme bulunamadı")
    return {"success": True}


@seo_public_router.get("/resolve-redirect")
async def resolve_redirect(path: str = Query(..., min_length=1)):
    """Storefront calls this on 404 to see if a 301/302 applies."""
    p = path.lower()
    if not p.startswith("/"):
        p = "/" + p
    r = await db.seo_redirects.find_one({"from_path": p, "is_active": True}, {"_id": 0})
    if not r:
        return {"found": False}
    # Increment hit counter async
    try:
        await db.seo_redirects.update_one({"id": r["id"]}, {"$inc": {"hits": 1}})
    except Exception:
        pass
    return {"found": True, "to": r["to_path"], "status_code": r["status_code"]}


@seo_admin_router.get("/meta")
async def get_meta_list(current_user: dict = Depends(require_admin)):
    items = await db.seo_meta.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"items": items}


@seo_admin_router.post("/meta")
async def upsert_meta(payload: dict, current_user: dict = Depends(require_admin)):
    """Per-path meta override. { path, title, description, og_image, noindex }"""
    path = (payload.get("path") or "").strip().lower()
    if not path:
        raise HTTPException(status_code=400, detail="path gerekli")
    if not path.startswith("/"):
        path = "/" + path
    doc = {
        "id": str(uuid.uuid4()),
        "path": path,
        "title": payload.get("title", "")[:200],
        "description": payload.get("description", "")[:400],
        "og_image": payload.get("og_image", ""),
        "noindex": bool(payload.get("noindex", False)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.seo_meta.update_one({"path": path}, {"$set": doc, "$setOnInsert": {"created_at": doc["updated_at"]}}, upsert=True)
    return {"success": True}


@seo_admin_router.delete("/meta/{mid}")
async def delete_meta(mid: str, current_user: dict = Depends(require_admin)):
    res = await db.seo_meta.delete_one({"id": mid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Meta bulunamadı")
    return {"success": True}


@seo_public_router.get("/meta")
async def get_public_meta(path: str):
    p = path.lower()
    if not p.startswith("/"):
        p = "/" + p
    doc = await db.seo_meta.find_one({"path": p}, {"_id": 0})
    return {"found": bool(doc), "meta": doc}


@seo_public_router.get("/runtime-config")
async def seo_runtime_config():
    """Public, non-secret company/SEO values used by SPA navigation."""
    cfg = await get_tenant_config(db)
    # Explicit projection: banking/tax identifiers and secret_refs must never
    # become public merely because the canonical schema later grows.
    return {
        "brand": {k: cfg["brand"].get(k) for k in ("store_name", "logo_url", "favicon_url")},
        "company": {k: cfg["company"].get(k) for k in
                    ("legal_name", "address", "city", "district", "country")},
        "contact": {k: cfg["contact"].get(k) for k in
                    ("email", "support_email", "phone", "whatsapp", "instagram", "facebook", "x", "tiktok")},
        "domains": {k: cfg["domains"].get(k) for k in ("storefront_url", "cdn_url")},
        "commerce": {k: cfg["commerce"].get(k) for k in
                     ("currency_code", "currency_symbol", "locale", "prices_include_vat")},
        "seo_geo": cfg["seo_geo"],
    }


@seo_admin_router.get("/config")
async def get_seo_config(current_user: dict = Depends(require_admin)):
    cfg = await get_tenant_config(db, use_cache=False)
    return cfg["seo_geo"]


@seo_admin_router.put("/config")
async def save_seo_config(payload: dict, current_user: dict = Depends(require_admin)):
    cfg = await get_tenant_config(db, use_cache=False)
    merged = {**cfg.get("seo_geo", {}), **(payload or {})}
    candidate = TenantConfig.model_validate({**cfg, "seo_geo": merged}).model_dump()
    await db.settings.update_one({"id": "tenant_config"}, {"$set": candidate}, upsert=True)
    invalidate_tenant_config(db)
    return {"success": True, "seo_geo": candidate["seo_geo"]}


async def _seo_preview_rows(kind: str, limit: int = 100):
    cfg = await get_tenant_config(db)
    rows = []
    if kind in ("product", "all"):
        async for item in db.products.find(
            {"is_active": {"$ne": False}, "is_deleted": {"$ne": True}},
            {"_id": 0, "id": 1, "name": 1, "slug": 1, "description": 1,
             "seo_description": 1, "meta_title": 1, "meta_description": 1,
             "images": 1, "image": 1, "price": 1, "sale_price": 1, "stock": 1,
             "variants": 1, "brand": 1, "barcode": 1, "stock_code": 1,
             "category_name": 1, "category_slug": 1},
        ).limit(limit):
            resolved = resolve_product(item, cfg)
            rows.append({"kind": "product", "id": item.get("id"), "name": item.get("name"),
                         "current": {"title": item.get("meta_title") or "",
                                     "description": item.get("meta_description") or ""},
                         "generated": {k: resolved.get(k) for k in ("title", "description", "canonical", "og_image", "robots", "sources")},
                         "would_change": bool((not item.get("meta_title") and resolved.get("title")) or
                                              (not item.get("meta_description") and resolved.get("description")))})
    if kind in ("category", "all"):
        async for item in db.categories.find(
            {"is_active": {"$ne": False}, "members_only": {"$ne": True}},
            {"_id": 0, "id": 1, "name": 1, "slug": 1, "description": 1,
             "meta_title": 1, "meta_description": 1, "image": 1},
        ).limit(limit):
            resolved = resolve_category(item, cfg)
            rows.append({"kind": "category", "id": item.get("id"), "name": item.get("name"),
                         "current": {"title": item.get("meta_title") or "",
                                     "description": item.get("meta_description") or ""},
                         "generated": {k: resolved.get(k) for k in ("title", "description", "canonical", "og_image", "robots", "sources")},
                         "would_change": bool((not item.get("meta_title") and resolved.get("title")) or
                                              (not item.get("meta_description") and resolved.get("description")))})
    return rows


@seo_admin_router.get("/bulk-preview")
async def seo_bulk_preview(kind: str = Query("all"),
                           limit: int = Query(100, ge=1, le=1000),
                           current_user: dict = Depends(require_admin)):
    if kind not in ("all", "product", "category"):
        raise HTTPException(status_code=400, detail="kind geçersiz")
    rows = await _seo_preview_rows(kind, limit)
    return {"dry_run": True, "apply_executed": False, "count": len(rows), "items": rows}


@seo_admin_router.post("/bulk-apply")
async def seo_bulk_apply(payload: dict, current_user: dict = Depends(require_admin)):
    """Explicit snapshot apply; never overwrites manual title/description."""
    if (payload or {}).get("confirmation") != "APPLY_GENERATED_SEO":
        raise HTTPException(status_code=400, detail="confirmation=APPLY_GENERATED_SEO gerekli")
    kind = (payload or {}).get("kind", "all")
    if kind not in ("all", "product", "category"):
        raise HTTPException(status_code=400, detail="kind geçersiz")
    try:
        limit = int((payload or {}).get("limit") or 100)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="limit geçersiz")
    if not 1 <= limit <= 1000:
        raise HTTPException(status_code=400, detail="limit 1-1000 arasında olmalı")
    rows = await _seo_preview_rows(kind, limit)
    updated = 0
    for row in rows:
        if row.get("id") is None:
            continue
        generated = row["generated"]
        collection = db.products if row["kind"] == "product" else db.categories
        # Separate conditional writes prevent a concurrent manual edit in one
        # field being overwritten while the other field is still empty.
        changed = False
        if not row["current"]["title"] and generated.get("title"):
            result = await collection.update_one(
                {"id": row["id"], "meta_title": {"$in": [None, ""]}},
                {"$set": {"meta_title": generated["title"]}},
            )
            changed = changed or bool(result.modified_count)
        if not row["current"]["description"] and generated.get("description"):
            result = await collection.update_one(
                {"id": row["id"], "meta_description": {"$in": [None, ""]}},
                {"$set": {"meta_description": generated["description"]}},
            )
            changed = changed or bool(result.modified_count)
        updated += int(changed)
    return {"success": True, "updated": updated, "manual_overrides_preserved": True}


# =============================================================================
# EDGE SEO — per-sayfa meta çözümleyici (functions/_middleware.js buradan okur)
# =============================================================================
_FRONT_URL = (os.environ.get("FRONTEND_PUBLIC_URL") or "").rstrip("/")
# Ürün/kategori OLMAYAN, indekslenmeyen veya statik kök yollar → soft-404 taraması yapma.
_SEO_NONINDEX_PREFIXES = ("/sepet", "/odeme", "/checkout", "/hesabim", "/account", "/admin",
                          "/giris", "/login", "/kayit", "/register", "/order-success",
                          "/siparis", "/sifremi", "/reset", "/iade", "/return")
_SEO_KNOWN_STATIC = {"/", "/hakkimizda", "/iletisim", "/sss", "/kvkk", "/gizlilik"}


@seo_public_router.get("/page-meta")
async def seo_page_meta(path: str = Query("/", max_length=512)):
    """Bir storefront yolu için title/description/canonical/OG + (ürün) JSON-LD döndürür.
    Cloudflare Pages edge middleware (functions/_middleware.js) her HTML isteğinde çağırır
    ve dönen meta'yı ilk HTML'e enjekte eder → ürün/kategori sayfaları Google'da doğru
    başlık/açıklama/canonical ile indekslenir (eskiden HEPSİ ana sayfaya canonical'lıydı).
    Savunmacı: her hata found:false döner (middleware ilk HTML'i olduğu gibi bırakır)."""
    try:
        raw = path or "/"
        # yalnız path kısmı, query/fragment at
        raw = raw.split("?", 1)[0].split("#", 1)[0]
        if not raw.startswith("/"):
            raw = "/" + raw
        p = raw.rstrip("/") or "/"
        low = p.lower()
        cfg = await get_tenant_config(db)
        site = (cfg["domains"].get("storefront_url") or _FRONT_URL).rstrip("/")

        # Admin override varsa öncelik (mevcut seo_meta)
        override = await db.seo_meta.find_one({"path": low}, {"_id": 0})

        # İndekslenmeyen/panel yolları → noindex (soft-404 + özel alan koruması)
        if any(low == pre or low.startswith(pre + "/") or low.startswith(pre) for pre in _SEO_NONINDEX_PREFIXES):
            return {"found": True, "robots": "noindex,follow", "canonical": f"{site}{p}"}

        # Ana sayfa / bilinen statikler use canonical global settings at runtime.
        if low in _SEO_KNOWN_STATIC:
            seo = cfg["seo_geo"]
            canonical = f"{site}/" if low == "/" else f"{site}{p}"
            m = {"found": True, "robots": seo.get("default_robots") or "index,follow",
                 "canonical": canonical, "title": seo.get("default_title") or "",
                 "description": seo.get("default_description") or "",
                 "og_title": seo.get("default_title") or "",
                 "og_description": seo.get("default_description") or "",
                 "og_url": canonical, "og_image": seo.get("default_og_image_url") or "",
                 "og_type": "website", "og_site_name": cfg["brand"].get("store_name") or "",
                 "og_locale": seo.get("locale") or ""}
            if low == "/":
                address = {"@type": "PostalAddress",
                           "streetAddress": cfg["company"].get("address") or None,
                           "addressLocality": cfg["company"].get("district") or cfg["company"].get("city") or None,
                           "addressRegion": cfg["company"].get("city") or None,
                           "addressCountry": cfg["company"].get("country") or None}
                address = {k: v for k, v in address.items() if v not in (None, "")}
                same_as = [cfg["contact"].get(key) for key in
                           ("instagram", "facebook", "x", "tiktok") if cfg["contact"].get(key)]
                org = {"@context": "https://schema.org", "@type": "Organization",
                       "name": cfg["brand"].get("store_name"), "url": site,
                       "legalName": cfg["company"].get("legal_name") or None,
                       "logo": cfg["brand"].get("logo_url") or None,
                       "description": seo.get("organization_description") or None,
                       "email": cfg["contact"].get("email") or None,
                       "telephone": cfg["contact"].get("phone") or None,
                       "address": address if len(address) > 1 else None,
                       "sameAs": same_as or None}
                m["jsonld"] = [{k: v for k, v in org.items() if v not in (None, "")}]
            if override:
                if override.get("title"):
                    m["title"] = m["og_title"] = override["title"]
                if override.get("description"):
                    m["description"] = m["og_description"] = override["description"]
                if override.get("og_image"):
                    m["og_image"] = override["og_image"]
                if override.get("noindex"):
                    m["robots"] = "noindex,nofollow"
            return m

        # Slug çöz: /urun/{slug} veya /{slug}
        slug = None
        mprod = _re.match(r"^/urun/([^/]+)$", p)
        mcat = _re.match(r"^/kategori/([^/]+)$", p)
        if mprod:
            slug = mprod.group(1)
        elif mcat:
            slug = p.split("/", 2)[2]
        elif _re.match(r"^/[^/]+$", p):
            slug = p[1:]
        if not slug:
            # çok segmentli bilinmeyen yol → noindex
            return {"found": True, "robots": "noindex,follow", "canonical": f"{site}{p}"}

        slug_l = slug.lower()

        # 1) ÜRÜN dene (aktif + silinmemiş; üyeye-özel değil)
        prod = None
        if not mcat:
            cands = await db.products.find(
                {"$or": [{"slug": slug_l}, {"slug": slug}, {"slug_aliases": slug_l}, {"id": slug}]},
                {"_id": 0, "name": 1, "slug": 1, "id": 1, "description": 1, "seo_description": 1,
                 "meta_description": 1, "meta_title": 1, "images": 1, "image": 1, "price": 1,
                 "sale_price": 1, "brand": 1, "barcode": 1, "stock_code": 1, "variants": 1,
                 "category_name": 1, "category_slug": 1, "stock": 1, "is_active": 1, "is_deleted": 1,
                 "members_only": 1, "category_id": 1, "category_ids": 1}).to_list(10)
            prod = (next((c for c in cands if c.get("is_active") is not False and not c.get("is_deleted")), None)
                    or None)
        if prod and not prod.get("members_only"):
            return resolve_product(prod, cfg, override=override)

        # 2) KATEGORİ dene
        cat = await db.categories.find_one(
            {"$or": [{"slug": slug_l}, {"slug": slug}, {"slug_aliases": slug_l}]},
            {"_id": 0, "name": 1, "slug": 1, "description": 1, "meta_title": 1,
             "meta_description": 1, "image": 1, "members_only": 1})
        if cat and not cat.get("members_only"):
            return resolve_category(cat, cfg, override=override)

        # 3) Ne ürün ne kategori → soft-404: noindex (Google indeks bütçesi boşa gitmesin)
        return {"found": True, "robots": "noindex,follow", "canonical": f"{site}{p}"}
    except Exception as e:
        logger.warning(f"[seo] page-meta çözümlenemedi path={path}: {e}")
        return {"found": False}
