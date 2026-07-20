"""
=============================================================================
instagram.py — @facette Instagram akışı (etiketli/gönderi feed'i)
=============================================================================
Instagram Graph API token'ı ile @facette hesabının son gönderilerini VEYA
hesabın etiketlendiği gönderileri (tagged) çeker, db.instagram_posts'a yazar;
anasayfadaki InstaShop bileşeni bunları gösterir.

Token yoksa admin gönderileri ELLE de ekleyebilir (görsel URL + gönderi linki).

ENDPOINTS:
  GET  /api/instagram/feed                 — Public (InstaShop için)
  GET  /api/admin/instagram/settings       — Admin (durum)
  PUT  /api/admin/instagram/settings       — Admin (token/ig_user_id/source/auto_sync)
  POST /api/admin/instagram/sync           — Admin (Graph API'den çek)
  POST /api/admin/instagram/posts          — Admin (elle gönderi ekle)
  DELETE /api/admin/instagram/posts/{id}   — Admin (gönderi sil)
=============================================================================
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone

import httpx

from .deps import db, require_admin, generate_id

try:
    from security.crypto import encrypt, decrypt
except Exception:  # pragma: no cover — kripto yoksa düz metin
    def encrypt(x): return x
    def decrypt(x): return x

logger = logging.getLogger("instagram")

public_router = APIRouter(prefix="/instagram", tags=["instagram-public"])
admin_router = APIRouter(prefix="/admin/instagram", tags=["instagram-admin"])

_GRAPH = "https://graph.facebook.com/v19.0"


def _now():
    return datetime.now(timezone.utc)


async def _get_settings():
    return await db.settings.find_one({"id": "instagram"}, {"_id": 0}) or {"id": "instagram"}


def _media_image(item: dict) -> str:
    """Video ise thumbnail, değilse media_url."""
    if (item.get("media_type") or "").upper() == "VIDEO":
        return item.get("thumbnail_url") or item.get("media_url") or ""
    return item.get("media_url") or item.get("thumbnail_url") or ""


async def _fetch_from_graph(token: str, ig_user_id: str, source: str, limit: int) -> list:
    """Graph API'den media (kendi gönderiler) veya tags (etiketli) çeker."""
    edge = "tags" if source == "tags" else "media"
    fields = "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp,username"
    url = f"{_GRAPH}/{ig_user_id}/{edge}"
    params = {"fields": fields, "limit": max(1, min(limit, 50)), "access_token": token}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params)
    if r.status_code != 200:
        detail = ""
        try:
            detail = (r.json().get("error") or {}).get("message") or r.text
        except Exception:
            detail = r.text
        raise HTTPException(status_code=502, detail=f"Instagram API hatası ({r.status_code}): {detail}")
    return (r.json() or {}).get("data", []) or []


# --------------------------------------------------------------------------- #
# Public
# --------------------------------------------------------------------------- #
@public_router.get("/feed")
async def instagram_feed(limit: int = 12):
    """Anasayfa InstaShop için: kayıtlı gönderiler (en yeni önce)."""
    limit = max(1, min(limit, 30))
    rows = await db.instagram_posts.find(
        {"active": {"$ne": False}},
        {"_id": 0, "id": 1, "image": 1, "permalink": 1, "caption": 1,
         "product_link": 1, "timestamp": 1},
    ).sort("timestamp", -1).to_list(length=limit)
    return {"posts": rows}


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #
@admin_router.get("/settings")
async def get_settings(current_user: dict = Depends(require_admin)):
    s = await _get_settings()
    count = await db.instagram_posts.count_documents({})
    return {
        "connected": bool(s.get("access_token")),
        "token_set": bool(s.get("access_token")),
        "ig_user_id": s.get("ig_user_id", ""),
        "source": s.get("source", "media"),
        "auto_sync": bool(s.get("auto_sync", False)),
        "last_sync": s.get("last_sync"),
        "last_error": s.get("last_error", ""),
        "post_count": count,
    }


@admin_router.put("/settings")
async def update_settings(payload: dict, current_user: dict = Depends(require_admin)):
    upd = {"updated_at": _now().isoformat()}
    # Token yalnızca doluysa güncellenir (boş gönderim mevcut token'ı silmez).
    tok = (payload or {}).get("access_token")
    if isinstance(tok, str) and tok.strip():
        upd["access_token"] = encrypt(tok.strip())
    if "ig_user_id" in (payload or {}):
        upd["ig_user_id"] = str(payload.get("ig_user_id") or "").strip()
    if "source" in (payload or {}):
        upd["source"] = "tags" if payload.get("source") == "tags" else "media"
    if "auto_sync" in (payload or {}):
        upd["auto_sync"] = bool(payload.get("auto_sync"))
    await db.settings.update_one(
        {"id": "instagram"}, {"$set": upd, "$setOnInsert": {"id": "instagram"}}, upsert=True)
    return {"success": True}


@admin_router.post("/auto-setup")
async def auto_setup(payload: dict, current_user: dict = Depends(require_admin)):
    """OTOMATİK KURULUM: Graph Explorer'dan alınan KISA ömürlü token + App ID/Secret ile
    her şeyi backend halleder — uzun ömürlü token'a çevirir, bağlı sayfayı ve Instagram
    Business hesabını bulur, ayarları kaydeder, ilk senkronu çalıştırır.
    (Meta alan adları yalnız sunucudan erişilebilir olduğundan bu iş burada yapılır.)"""
    app_id = str((payload or {}).get("app_id") or "").strip()
    app_secret = str((payload or {}).get("app_secret") or "").strip()
    short_token = str((payload or {}).get("short_token") or "").strip()
    if not (app_id and app_secret and short_token):
        raise HTTPException(status_code=400, detail="App ID, App Secret ve kısa token zorunlu")

    async with httpx.AsyncClient(timeout=30) as client:
        # 1) Kısa token → uzun ömürlü (60 gün) kullanıcı token'ı
        r = await client.get(f"{_GRAPH}/oauth/access_token", params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id, "client_secret": app_secret,
            "fb_exchange_token": short_token})
        if r.status_code != 200:
            _err = ((r.json() or {}).get("error") or {}).get("message", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
            raise HTTPException(status_code=502, detail=f"Token uzatılamadı: {_err}")
        long_token = (r.json() or {}).get("access_token") or ""
        if not long_token:
            raise HTTPException(status_code=502, detail="Uzun ömürlü token alınamadı")

        # 2) Bağlı sayfalar → instagram_business_account
        r2 = await client.get(f"{_GRAPH}/me/accounts", params={
            "fields": "id,name,instagram_business_account{id,username}",
            "access_token": long_token})
        if r2.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Sayfalar okunamadı: {r2.text[:300]}")
        pages = (r2.json() or {}).get("data", []) or []
        ig = None
        for p in pages:
            iba = p.get("instagram_business_account")
            if iba and iba.get("id"):
                ig = {"id": iba["id"], "username": iba.get("username", ""), "page": p.get("name", "")}
                break
        if not ig:
            raise HTTPException(status_code=400, detail=(
                "Bağlı Instagram Business hesabı bulunamadı. Instagram hesabınızın 'Profesyonel (İşletme)' "
                "olduğundan ve bir Facebook Sayfasına bağlı olduğundan emin olun; token izinlerinde "
                "instagram_basic + pages_show_list olmalı."))

    # 3) Kaydet (token şifreli) + otomatik senkron aç
    await db.settings.update_one(
        {"id": "instagram"},
        {"$set": {"access_token": encrypt(long_token), "ig_user_id": ig["id"],
                  "auto_sync": True, "source": "media",
                  "app_id": app_id, "app_secret": encrypt(app_secret),
                  "last_error": "", "updated_at": _now().isoformat()},
         "$setOnInsert": {"id": "instagram"}}, upsert=True)

    # 4) İlk senkron (hata olursa kurulum yine başarılı sayılır — mesajda belirtilir)
    synced, sync_err = 0, ""
    try:
        items = await _fetch_from_graph(long_token, ig["id"], "media", 30)
        for it in items:
            img = _media_image(it)
            if not img:
                continue
            await db.instagram_posts.update_one(
                {"ig_id": it.get("id")},
                {"$set": {"ig_id": it.get("id"), "image": img,
                          "permalink": it.get("permalink", ""),
                          "caption": (it.get("caption") or "")[:300],
                          "timestamp": it.get("timestamp", ""), "active": True,
                          "source": "graph", "updated_at": _now().isoformat()},
                 "$setOnInsert": {"id": generate_id()}}, upsert=True)
            synced += 1
        await db.settings.update_one({"id": "instagram"}, {"$set": {"last_sync": _now().isoformat()}})
    except HTTPException as e:
        sync_err = str(e.detail)
    except Exception as e:
        sync_err = str(e)[:200]

    return {"success": True, "ig_username": ig.get("username"), "ig_user_id": ig["id"],
            "page": ig.get("page"), "synced": synced,
            "message": f"@{ig.get('username') or 'hesap'} bağlandı · {synced} gönderi çekildi"
                       + (f" · ilk senkron uyarısı: {sync_err}" if sync_err else "")}


@admin_router.post("/disconnect")
async def disconnect(current_user: dict = Depends(require_admin)):
    """Token'ı temizle (bağlantıyı kes). Gönderiler silinmez."""
    await db.settings.update_one(
        {"id": "instagram"}, {"$unset": {"access_token": ""}, "$set": {"auto_sync": False}})
    return {"success": True}


@admin_router.post("/sync")
async def sync_now(current_user: dict = Depends(require_admin)):
    s = await _get_settings()
    token = decrypt(s.get("access_token")) if s.get("access_token") else ""
    ig_user_id = s.get("ig_user_id", "")
    source = s.get("source", "media")
    if not token or not ig_user_id:
        raise HTTPException(status_code=400, detail="Önce Access Token ve Instagram User ID girin.")
    try:
        items = await _fetch_from_graph(token, ig_user_id, source, 30)
    except HTTPException as e:
        await db.settings.update_one({"id": "instagram"}, {"$set": {"last_error": str(e.detail)}})
        raise
    saved = 0
    for it in items:
        img = _media_image(it)
        if not img:
            continue
        doc = {
            "id": it.get("id") or generate_id(),
            "image": img,
            "permalink": it.get("permalink") or "",
            "caption": (it.get("caption") or "")[:500],
            "media_type": it.get("media_type") or "IMAGE",
            "username": it.get("username") or "",
            "timestamp": it.get("timestamp") or _now().isoformat(),
            "source": source,
            "active": True,
            "synced_at": _now().isoformat(),
        }
        await db.instagram_posts.update_one(
            {"id": doc["id"]},
            {"$set": doc, "$setOnInsert": {"product_link": ""}},
            upsert=True,
        )
        saved += 1
    await db.settings.update_one(
        {"id": "instagram"},
        {"$set": {"last_sync": _now().isoformat(), "last_error": ""}})
    return {"success": True, "fetched": len(items), "saved": saved}


@admin_router.get("/posts")
async def list_posts(limit: int = 60, current_user: dict = Depends(require_admin)):
    limit = max(1, min(limit, 200))
    rows = await db.instagram_posts.find({}, {"_id": 0}).sort("timestamp", -1).to_list(length=limit)
    return {"posts": rows}


@admin_router.post("/posts")
async def add_post(payload: dict, current_user: dict = Depends(require_admin)):
    """Elle gönderi ekle (token yokken). image zorunlu."""
    image = (payload or {}).get("image", "").strip()
    if not image:
        raise HTTPException(status_code=400, detail="Görsel URL'si zorunlu.")
    doc = {
        "id": generate_id(),
        "image": image,
        "permalink": (payload.get("permalink") or "").strip(),
        "product_link": (payload.get("product_link") or "").strip(),
        "caption": (payload.get("caption") or "")[:500],
        "media_type": "IMAGE",
        "source": "manual",
        "active": True,
        "timestamp": _now().isoformat(),
        "created_at": _now().isoformat(),
    }
    await db.instagram_posts.insert_one({**doc})
    return {"success": True, "id": doc["id"]}


@admin_router.put("/posts/{post_id}")
async def update_post(post_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    allowed = {"image", "permalink", "product_link", "caption", "active"}
    upd = {k: v for k, v in (payload or {}).items() if k in allowed}
    if not upd:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")
    res = await db.instagram_posts.update_one({"id": post_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Gönderi bulunamadı")
    return {"success": True}


@admin_router.delete("/posts/{post_id}")
async def delete_post(post_id: str, current_user: dict = Depends(require_admin)):
    await db.instagram_posts.delete_one({"id": post_id})
    return {"success": True}


# --------------------------------------------------------------------------- #
# Scheduler'ın çağırdığı otomatik senkron (auto_sync açıksa)
# --------------------------------------------------------------------------- #
async def auto_sync_instagram():
    """Scheduler: auto_sync açık + token varsa gönderileri tazeler."""
    try:
        s = await _get_settings()
        if not s.get("auto_sync") or not s.get("access_token") or not s.get("ig_user_id"):
            return
        token = decrypt(s.get("access_token"))
        items = await _fetch_from_graph(token, s.get("ig_user_id"), s.get("source", "media"), 30)
        for it in items:
            img = _media_image(it)
            if not img:
                continue
            await db.instagram_posts.update_one(
                {"id": it.get("id")},
                {"$set": {
                    "id": it.get("id"), "image": img, "permalink": it.get("permalink") or "",
                    "caption": (it.get("caption") or "")[:500],
                    "media_type": it.get("media_type") or "IMAGE",
                    "timestamp": it.get("timestamp") or _now().isoformat(),
                    "source": s.get("source", "media"), "active": True,
                    "synced_at": _now().isoformat(),
                }, "$setOnInsert": {"product_link": ""}},
                upsert=True,
            )
        await db.settings.update_one(
            {"id": "instagram"}, {"$set": {"last_sync": _now().isoformat(), "last_error": ""}})
        logger.info("[instagram] auto-sync ok — %d gönderi", len(items))
    except Exception as e:
        logger.warning("[instagram] auto-sync hata: %s", e)
        try:
            await db.settings.update_one({"id": "instagram"}, {"$set": {"last_error": str(e)}})
        except Exception:
            pass
