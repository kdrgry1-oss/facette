"""
=============================================================================
integrations_trendyol_qna.py — Trendyol Q&A + Reviews (extracted)
=============================================================================
Iter37 refactor adımı: integrations.py'den Trendyol Q&A (3 endpoint) ve
Reviews (2 endpoint) kısmı ayrı modüle taşındı (~340 satır).

Helper'lar (`get_trendyol_config`, `get_trendyol_headers`, `log_integration_event`)
hâlâ integrations.py'de — circular import önlemek için lazy/relative import.

Endpoints:
- GET  /api/integrations/trendyol/questions/sync
- GET  /api/integrations/trendyol/questions
- POST /api/integrations/trendyol/questions/{id}/answer
- POST /api/integrations/trendyol/reviews/scrape
- POST /api/integrations/trendyol/reviews/scrape-bulk
=============================================================================
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import os
import re
import socket
import httpx

from .deps import db, logger, require_admin, generate_id

router = APIRouter(tags=["Integrations - Trendyol Q&A"])


# ==================== TRENDYOL Q&A ====================

@router.get("/trendyol/questions/sync")
async def sync_trendyol_questions(
    days_back: int = 90,
    status: Optional[str] = None,
    current_user: dict = Depends(require_admin)
):
    """Sync questions from Trendyol and store in DB.

    Trendyol QnA Filter API varsayılan olarak son ~14-30 gün döndürür; geçmiş
    soruları çekebilmek için `startDate`/`endDate` (Unix ms) parametreleri
    geçilmelidir. `days_back` (varsayılan 90) bunu kontrol eder.
    """
    from .integrations import get_trendyol_config, get_trendyol_headers

    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")

    supplier_id = config["supplier_id"]
    headers = await get_trendyol_headers()
    if not headers:
        raise HTTPException(status_code=400, detail="Trendyol kimlik bilgileri eksik")

    base_url = "https://apigw.trendyol.com" if config.get("mode") == "live" else "https://stageapigw.trendyol.com"
    synced = 0
    updated = 0
    total_fetched = 0
    page = 0

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=max(1, min(days_back, 365)))
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{base_url}/integration/qna/sellers/{supplier_id}/questions/filter"

            while True:
                params = {
                    "size": 50,
                    "page": page,
                    "startDate": start_ms,
                    "endDate": end_ms,
                    "orderByField": "CreatedDate",
                    "orderByDirection": "DESC",
                }
                if status:
                    params["status"] = status
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                questions = data.get("content", [])

                if not questions:
                    break

                for q in questions:
                    q_id = str(q.get("id"))
                    existing = await db.trendyol_questions.find_one({"question_id": q_id})
                    c_date = q.get("creationDate")
                    created_date_iso = ""
                    if c_date:
                        try:
                            created_date_iso = datetime.fromtimestamp(c_date / 1000, tz=timezone.utc).isoformat()
                        except Exception:
                            created_date_iso = str(c_date)

                    doc = {
                        "question_id": q_id,
                        "product_id": str(q.get("productId", "")),
                        "product_name": q.get("productName", ""),
                        "question_text": q.get("text", ""),
                        "customer_name": q.get("userName", "") if q.get("showUserName") else "Gizli Kullanıcı",
                        "status": q.get("status", "WAITING_FOR_ANSWER"),
                        "created_date": created_date_iso,
                        "image_url": q.get("imageUrl", ""),
                        "synced_at": datetime.now(timezone.utc).isoformat(),
                    }
                    # Y9: Filter API cogu zaman answers[] DONDURMEZ. Bos cevabi $set ile yazarsak
                    # sync-answers ile geri doldurulmus ya da panelden verilmis cevaplar SILINIYORDU.
                    # Bu yuzden cevap yalnizca API gercekten bir cevap dondurdugunde guncellenir.
                    _ans = ""
                    if q.get("answers"):
                        _ans = (q.get("answers", [{}])[0] or {}).get("text", "") or ""
                    if existing:
                        if _ans:
                            doc["answer"] = _ans
                        await db.trendyol_questions.update_one({"question_id": q_id}, {"$set": doc})
                        updated += 1
                    else:
                        doc["id"] = generate_id()
                        doc["created_at"] = datetime.now(timezone.utc).isoformat()
                        doc["answer"] = _ans
                        await db.trendyol_questions.insert_one(doc)
                        synced += 1

                total_fetched += len(questions)
                total_pages = data.get("totalPages", 1)
                page += 1

                if page >= total_pages or page > 50:
                    break

        return {
            "success": True,
            "synced": synced,
            "updated": updated,
            "total_fetched": total_fetched,
            "days_back": days_back,
            "date_range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"Q&A sync error: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logger.error(f"Q&A sync error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trendyol/questions")
async def get_trendyol_questions(
    status: Optional[str] = None,
    page: int = 0,
    size: int = 20,
    current_user: dict = Depends(require_admin)
):
    """Get questions from local DB"""
    query = {}
    if status:
        query["status"] = status

    skip = page * size
    questions = await db.trendyol_questions.find(query).sort("created_at", -1).skip(skip).limit(size).to_list(size)
    total = await db.trendyol_questions.count_documents(query)

    for q in questions:
        q.pop("_id", None)

    return {"questions": questions, "total": total, "page": page, "size": size}


@router.post("/trendyol/questions/{question_id}/answer")
async def answer_trendyol_question(question_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    """Send an answer to a Trendyol customer question"""
    from .integrations import get_trendyol_config, get_trendyol_headers, log_integration_event

    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")

    answer_text = payload.get("answer", "").strip()
    if not answer_text:
        raise HTTPException(status_code=400, detail="Yanit metni bos olamaz")

    supplier_id = config["supplier_id"]
    headers = await get_trendyol_headers()
    base_url = "https://apigw.trendyol.com" if config.get("mode") == "live" else "https://stageapigw.trendyol.com"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{base_url}/integration/qna/sellers/{supplier_id}/questions/{question_id}/answers"
            body = {"text": answer_text}
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()

        await db.trendyol_questions.update_one(
            {"question_id": question_id},
            {"$set": {"answer": answer_text, "status": "ANSWERED", "answered_at": datetime.now(timezone.utc).isoformat()}}
        )

        await log_integration_event("trendyol", "answer_question", current_user["email"], question_id, "success", "Soru yanitlandi")
        return {"success": True, "message": "Soru basariyla yanitlandi"}
    except httpx.HTTPStatusError as e:
        logger.error(f"Q&A answer error: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logger.error(f"Q&A answer error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== TRENDYOL REVIEWS (public storefront scrape) ====================

@router.post("/trendyol/questions/sync-answers")
async def sync_trendyol_answers(
    payload: Optional[dict] = None,
    current_user: dict = Depends(require_admin),
):
    """ANSWERED status'lu fakat answer alanı boş olan trendyol_questions için
    tek tek /questions/{id} çağrısı atıp answer text'lerini doldur.

    Trendyol filter API'si tasarım gereği `answers[]` döndürmez (performans).
    Bu endpoint detay endpoint'ten çekerek bulk-train için veriyi tamamlar.

    Body: {"max_count": 100, "only_empty_answers": true}
    """
    from .integrations import get_trendyol_config, get_trendyol_headers

    cfg = payload or {}
    max_count = int(cfg.get("max_count") or 100)
    only_empty = bool(cfg.get("only_empty_answers", True))

    config = await get_trendyol_config()
    if not config["is_active"]:
        raise HTTPException(status_code=400, detail="Trendyol entegrasyonu yapılandırılmamış")

    headers = await get_trendyol_headers()
    if not headers:
        raise HTTPException(status_code=400, detail="Trendyol kimlik bilgileri eksik")

    supplier_id = config["supplier_id"]
    base_url = "https://apigw.trendyol.com" if config.get("mode") == "live" else "https://stageapigw.trendyol.com"

    query = {"status": "ANSWERED"}
    if only_empty:
        query["$or"] = [{"answer": ""}, {"answer": {"$exists": False}}, {"answer": None}]

    cur = db.trendyol_questions.find(query, {"_id": 0, "question_id": 1}).limit(max_count)
    targets = await cur.to_list(max_count)

    fetched = 0
    updated = 0
    failed = 0
    errors = []

    async with httpx.AsyncClient(timeout=15) as client:
        for t in targets:
            q_id = t.get("question_id")
            if not q_id:
                continue
            try:
                resp = await client.get(
                    f"{base_url}/integration/qna/sellers/{supplier_id}/questions/{q_id}",
                    headers=headers,
                )
                if resp.status_code != 200:
                    failed += 1
                    if len(errors) < 5:
                        errors.append(f"{q_id}: HTTP {resp.status_code}")
                    continue
                fetched += 1
                data = resp.json()
                # Trendyol detail endpoint single `answer` object döner (filter'daki answers[] DEĞİL)
                ans_obj = data.get("answer") or {}
                # Bazı durumlarda eski format answers[] olabilir — fallback
                if not ans_obj:
                    ans_arr = data.get("answers") or []
                    if ans_arr:
                        ans_obj = ans_arr[0] if isinstance(ans_arr[0], dict) else {}
                ans_text = (ans_obj or {}).get("text", "") if isinstance(ans_obj, dict) else ""
                if ans_text:
                    answered_at_iso = ""
                    cdate = ans_obj.get("creationDate") or ans_obj.get("createdDate")
                    if cdate:
                        try:
                            answered_at_iso = datetime.fromtimestamp(cdate / 1000, tz=timezone.utc).isoformat()
                        except Exception:
                            answered_at_iso = str(cdate)
                    await db.trendyol_questions.update_one(
                        {"question_id": q_id},
                        {"$set": {
                            "answer": ans_text,
                            "answered_at": answered_at_iso or datetime.now(timezone.utc).isoformat(),
                            "answer_synced_at": datetime.now(timezone.utc).isoformat(),
                        }}
                    )
                    updated += 1
            except Exception as e:
                failed += 1
                if len(errors) < 5:
                    errors.append(f"{q_id}: {e}")

    return {
        "success": True,
        "scanned": len(targets),
        "fetched": fetched,
        "updated": updated,
        "failed": failed,
        "errors": errors,
    }


@router.post("/trendyol/reviews/scrape")
async def scrape_trendyol_reviews(
    payload: dict,
    current_user: dict = Depends(require_admin),
):
    """Public Trendyol storefront'tan bir ürünün yorumlarını çeker.

    Body: { "trendyol_url": "...", "product_id": "<local product id>", "min_rating": 4 }
    """
    from .integrations import log_integration_event

    url = (payload or {}).get("trendyol_url", "").strip()
    local_pid = (payload or {}).get("product_id", "").strip()
    min_rating = int((payload or {}).get("min_rating", 4))
    if not url or "trendyol.com" not in url:
        raise HTTPException(status_code=400, detail="Geçerli bir trendyol_url gerekli")

    m = re.search(r"-p-(\d+)", url)
    if not m:
        raise HTTPException(status_code=400, detail="URL'den ürün ID çıkarılamadı")
    content_id = m.group(1)

    api_url = (
        "https://public.trendyol.com/discovery-web-websfxsocialreviewrating-santral/"
        f"api/v1/reviews/{content_id}"
    )
    fetched: List[dict] = []
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            page = 0
            while page < 10:
                params = {"page": page, "size": 30, "order": "DESC", "orderBy": "Score"}
                resp = await client.get(api_url, params=params,
                                        headers={"User-Agent": "Mozilla/5.0",
                                                 "Accept": "application/json"})
                if resp.status_code == 404:
                    break
                resp.raise_for_status()
                data = resp.json()
                reviews = (data.get("result") or {}).get("productReviews", {}).get("content", [])
                if not reviews:
                    break
                fetched.extend(reviews)
                total_pages = (data.get("result") or {}).get("productReviews", {}).get("totalPages", 1)
                page += 1
                if page >= total_pages:
                    break
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code,
                            detail=f"Trendyol public API hatası: {e.response.text[:200]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Yorum çekme hatası: {e}")

    inserted = 0
    skipped_low_rating = 0
    skipped_existing = 0

    for r in fetched:
        rating = int(r.get("rate") or 0)
        if rating < min_rating:
            skipped_low_rating += 1
            continue
        review_id = str(r.get("id") or "")
        if not review_id:
            continue
        existing = await db.product_reviews.find_one(
            {"source": "trendyol_public", "external_id": review_id}, {"_id": 1}
        )
        if existing:
            skipped_existing += 1
            continue

        comment_date = r.get("commentDateISOtype") or r.get("lastModifiedDate") or ""
        doc = {
            "id": generate_id(),
            "external_id": review_id,
            "source": "trendyol_public",
            "product_id": local_pid or None,
            "trendyol_content_id": content_id,
            "rating": rating,
            "title": r.get("commentTitle") or "",
            "comment": r.get("comment") or "",
            "user_name": r.get("userFullName") or "Trendyol Müşterisi",
            "is_verified": bool(r.get("verifiedPurchase")),
            "is_seller_verified": bool(r.get("sellerVerified")),
            "approved": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "comment_date": comment_date,
        }
        await db.product_reviews.insert_one(doc)
        inserted += 1

    if local_pid:
        agg = await db.product_reviews.aggregate([
            {"$match": {"product_id": local_pid, "approved": True}},
            {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "cnt": {"$sum": 1}}}
        ]).to_list(1)
        if agg:
            await db.products.update_one(
                {"id": local_pid},
                {"$set": {
                    "rating": round(agg[0]["avg"], 2),
                    "review_count": agg[0]["cnt"],
                    "reviews_synced_at": datetime.now(timezone.utc).isoformat(),
                }}
            )

    await log_integration_event(
        "trendyol", "review_scrape", "product", local_pid or content_id,
        "success",
        f"Yorum çekildi: contentId={content_id} fetched={len(fetched)} inserted={inserted}",
    )
    return {
        "success": True,
        "content_id": content_id,
        "fetched": len(fetched),
        "inserted": inserted,
        "skipped_low_rating": skipped_low_rating,
        "skipped_existing": skipped_existing,
        "min_rating": min_rating,
    }


@router.post("/trendyol/reviews/scrape-bulk")
async def scrape_trendyol_reviews_bulk(
    payload: dict,
    current_user: dict = Depends(require_admin),
):
    """Birden fazla ürün için toplu yorum çekimi."""
    items = (payload or {}).get("items") or []
    min_rating = int((payload or {}).get("min_rating", 4))
    results = []
    total_inserted = 0
    for it in items[:50]:
        try:
            r = await scrape_trendyol_reviews(
                {"trendyol_url": it.get("trendyol_url", ""),
                 "product_id": it.get("product_id", ""),
                 "min_rating": min_rating},
                current_user=current_user,
            )
            results.append({"product_id": it.get("product_id"), "ok": True, **r})
            total_inserted += r.get("inserted", 0)
        except HTTPException as e:
            results.append({"product_id": it.get("product_id"), "ok": False, "error": e.detail})
        except Exception as e:
            results.append({"product_id": it.get("product_id"), "ok": False, "error": str(e)})
    return {"success": True, "total_inserted": total_inserted, "items": results}


# ============================================================================
# TOPLU YORUM SENKRONU — tüm aktif site ürünleri için Trendyol 4-5★ yorumları
# ============================================================================

_PUBLIC_HOST = "public.trendyol.com"
# _NO_PIN sentinel = hostname'e doğrudan bağlan (pin yok). good=_UNSET → henüz çalışan hedef yok.
_NO_PIN = "__hostname__"
_UNSET = "__unset__"
_pin_state = {"resolved": False, "candidates": [], "good": _UNSET, "ip": None}

# Cloudflare 530/1016 çoğunlukla datacenter IP'sine WAF şüphesiyle döner. Gerçek tarayıcı
# başlıkları (Referer/Origin/Accept-Language/sec-ch-ua) bu şüpheyi büyük ölçüde azaltır.
_BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.trendyol.com/",
    "Origin": "https://www.trendyol.com",
    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}


def _resolve_public_ips_via_doh() -> List[str]:
    """public.trendyol.com'un TÜM A kayıtlarını DNS-over-HTTPS ile çözer (birden fazla IP).
    Cloudflare/Google DoH sabit IP — Railway özel DNS'ine bağımlı değil."""
    ips: List[str] = []
    for doh_ip, sni in (("1.1.1.1", "cloudflare-dns.com"), ("8.8.8.8", "dns.google")):
        try:
            with httpx.Client(timeout=10) as c:
                req = c.build_request(
                    "GET", f"https://{doh_ip}/dns-query",
                    params={"name": _PUBLIC_HOST, "type": "A"},
                    headers={"accept": "application/dns-json"},
                )
                req.extensions["sni_hostname"] = sni.encode("ascii")
                resp = c.send(req)
                resp.raise_for_status()
                for ans in resp.json().get("Answer", []):
                    if ans.get("type") == 1 and ans.get("data") and ans["data"] not in ips:
                        ips.append(ans["data"])
            if ips:
                break
        except Exception:
            continue
    return ips


def _build_candidates() -> List[str]:
    """Denenecek bağlantı hedefleri (sıralı): hostname (Railway çözebiliyorsa) → DoH IP'leri →
    çözülebilen Trendyol anycast IP'leri. Idempotent (bir kez çözer, cache'ler)."""
    if _pin_state["resolved"]:
        return _pin_state["candidates"]
    _pin_state["resolved"] = True
    cands: List[str] = []
    try:
        socket.gethostbyname(_PUBLIC_HOST)
        cands.append(_NO_PIN)   # DNS çözülüyor → doğrudan hostname
    except Exception:
        pass
    for ip in _resolve_public_ips_via_doh():
        if ip not in cands:
            cands.append(ip)
    for alt in ("apigw.trendyol.com", "www.trendyol.com", "api.trendyol.com"):
        try:
            ip = socket.gethostbyname(alt)
            if ip not in cands:
                cands.append(ip)
        except Exception:
            continue
    if not cands:
        cands.append(_NO_PIN)   # son çare
    _pin_state["candidates"] = cands
    _pin_state["ip"] = next((c for c in cands if c != _NO_PIN), None)  # teşhis için
    return cands


def _pin_public_trendyol_if_needed():
    """Geriye dönük uyumluluk — adaylar bir kez çözülür."""
    _build_candidates()


async def _one_review_page(client, target: str, content_id: str, page: int):
    """Tek sayfa istek. target=_NO_PIN → hostname; aksi halde IP'ye bağlan, Host+SNI korunur."""
    pin = None if target == _NO_PIN else target
    base = f"https://{pin}" if pin else f"https://{_PUBLIC_HOST}"
    api_url = (f"{base}/discovery-web-websfxsocialreviewrating-santral/"
               f"api/v1/reviews/{content_id}")
    params = {"page": page, "size": 30, "order": "DESC", "orderBy": "Score"}
    headers = dict(_BROWSER_HEADERS)
    if pin:
        headers["Host"] = _PUBLIC_HOST
    req = client.build_request("GET", api_url, params=params, headers=headers)
    if pin:
        req.extensions["sni_hostname"] = _PUBLIC_HOST.encode("ascii")  # TLS SNI + cert = public.trendyol.com
    return await client.send(req)


def _review_proxy() -> str:
    """Yorum çekimi için opsiyonel proxy. Trendyol Cloudflare'i datacenter/Railway IP'lerini 530
    ile engellerse, buraya girilen proxy (residential/datacenter) üzerinden çekilir.
    Sıra: env TRENDYOL_REVIEW_PROXY → db.settings(id=trendyol).review_proxy (sync okunamaz;
    scrape_all onu _pin_state'e koyar)."""
    return os.environ.get("TRENDYOL_REVIEW_PROXY") or _pin_state.get("proxy") or ""


async def _fetch_reviews_for_content_id(content_id: str, min_rating: int, max_pages: int = 10) -> List[dict]:
    """Trendyol public storefront'tan bir contentId'nin yorumlarını çeker (sayfalı).
    PROXY varsa: proxy üzerinden normal hostname ile çekilir (datacenter-IP 530 engelini aşar).
    Proxy yoksa: Railway DNS çözemezse DoH IP'lerine bağlanır; her hedef 530/403 dönerse
    bir sonraki denenir; çalışan hedef cache'lenir."""
    proxy = _review_proxy()
    if proxy:
        # Proxy DNS'i kendi çözer; IP pin/SNI gerekmez, düz hostname yeterli.
        api_url = (f"https://{_PUBLIC_HOST}/discovery-web-websfxsocialreviewrating-santral/"
                   f"api/v1/reviews/{content_id}")
        fetched: List[dict] = []
        async with httpx.AsyncClient(timeout=25, follow_redirects=True, proxy=proxy) as client:
            page = 0
            while page < max_pages:
                resp = await client.get(api_url, params={"page": page, "size": 30, "order": "DESC", "orderBy": "Score"},
                                        headers=_BROWSER_HEADERS)
                if resp.status_code == 404:
                    break
                resp.raise_for_status()
                rv = (resp.json().get("result") or {}).get("productReviews", {}).get("content", [])
                if not rv:
                    break
                fetched.extend(rv)
                total_pages = (resp.json().get("result") or {}).get("productReviews", {}).get("totalPages", 1) or 1
                page += 1
                if page >= total_pages:
                    break
        _pin_state["good"] = "proxy"
        return fetched

    cands = _build_candidates()
    good = _pin_state["good"]
    order = ([good] if good != _UNSET and good in cands else []) + \
            [c for c in cands if c != good]

    last_err = None
    _BAD = {403, 429, 500, 502, 503, 520, 521, 522, 523, 524, 525, 526, 530}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for target in order:
            try:
                resp = await _one_review_page(client, target, content_id, 0)
                if resp.status_code in _BAD:
                    last_err = f"HTTP {resp.status_code} @ {target}"
                    continue
                if resp.status_code == 404:
                    _pin_state["good"] = target   # bu hedef çalışıyor (ürünün yorumu yok sadece)
                    return []
                resp.raise_for_status()
                _pin_state["good"] = target        # çalışan hedefi sabitle
                data = resp.json()
                fetched: List[dict] = list((data.get("result") or {}).get("productReviews", {}).get("content", []))
                total_pages = (data.get("result") or {}).get("productReviews", {}).get("totalPages", 1) or 1
                page = 1
                while page < min(max_pages, total_pages):
                    r2 = await _one_review_page(client, target, content_id, page)
                    if r2.status_code != 200:
                        break
                    rv2 = (r2.json().get("result") or {}).get("productReviews", {}).get("content", [])
                    if not rv2:
                        break
                    fetched.extend(rv2)
                    page += 1
                return fetched
            except Exception as e:
                last_err = str(e)[:140]
                continue
    # Hiçbir hedef çalışmadı — çağıran (sync_all) hatayı özet errors'a yazar.
    raise Exception(f"tum hedefler basarisiz ({len(order)} denendi): {last_err}")


async def _store_reviews(fetched: List[dict], local_pid: Optional[str], content_id: str, min_rating: int) -> dict:
    """Çekilen ham yorumlardan >= min_rating olanları product_reviews'a yazar (external_id ile dedup)."""
    inserted = skipped_low = skipped_existing = 0
    for r in fetched:
        rating = int(r.get("rate") or 0)
        if rating < min_rating:
            skipped_low += 1
            continue
        review_id = str(r.get("id") or "")
        if not review_id:
            continue
        existing = await db.product_reviews.find_one(
            {"source": "trendyol_public", "external_id": review_id}, {"_id": 1}
        )
        if existing:
            skipped_existing += 1
            continue
        doc = {
            "id": generate_id(),
            "external_id": review_id,
            "source": "trendyol_public",
            "product_id": local_pid or None,
            "trendyol_content_id": content_id,
            "rating": rating,
            "title": r.get("commentTitle") or "",
            "comment": r.get("comment") or "",
            "user_name": r.get("userFullName") or "Trendyol Müşterisi",
            "is_verified": bool(r.get("verifiedPurchase")),
            "is_seller_verified": bool(r.get("sellerVerified")),
            "approved": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "comment_date": r.get("commentDateISOtype") or r.get("lastModifiedDate") or "",
        }
        await db.product_reviews.insert_one(doc)
        inserted += 1
    return {"inserted": inserted, "skipped_low_rating": skipped_low, "skipped_existing": skipped_existing}


async def _recalc_product_rating(local_pid: str) -> None:
    """Bir ürünün onaylı yorumlarından ortalama puan + adet hesaplayıp products dokümanına yazar."""
    agg = await db.product_reviews.aggregate([
        {"$match": {"product_id": local_pid, "approved": True}},
        {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "cnt": {"$sum": 1}}},
    ]).to_list(1)
    if agg:
        await db.products.update_one(
            {"id": local_pid},
            {"$set": {
                "rating": round(agg[0]["avg"], 2),
                "review_count": agg[0]["cnt"],
                "reviews_synced_at": datetime.now(timezone.utc).isoformat(),
            }},
        )


async def sync_all_trendyol_reviews_core(min_rating: int = 4, limit: int = 0, dry_run: bool = False) -> dict:
    """
    TÜM aktif site ürünleri için Trendyol public yorumlarını (>= min_rating) çeker.

    Eşleştirme akışı:
      1) Trendyol getProducts (approved) → barcode→contentId haritası kurulur.
      2) Her site ürününün barcode'ları (ana + varyant) bu haritada aranır.
      3) Bulunan her contentId için public yorumlar çekilip product_reviews'a yazılır,
         ürünün rating/review_count alanları yeniden hesaplanır.
    """
    from trendyol_client import TrendyolClient

    # Config: çalışan fiyat script'iyle birebir aynı kaynak (db.settings id=trendyol).
    # NOT: get_trendyol_config() mode varsayılanı "sandbox" — bu stage API'ye düşüp
    # boş ürün listesi döndürüyordu (indexed=0). Burada mode varsayılanı "live".
    settings = await db.settings.find_one({"id": "trendyol"}) or {}
    supplier_id = settings.get("supplier_id") or os.environ.get("TRENDYOL_SUPPLIER_ID", "")
    api_key = settings.get("api_key") or os.environ.get("TRENDYOL_API_KEY", "")
    api_secret = settings.get("api_secret") or os.environ.get("TRENDYOL_API_SECRET", "")
    mode = settings.get("mode") or os.environ.get("TRENDYOL_MODE") or "live"
    if not (supplier_id and api_key and api_secret):
        raise HTTPException(status_code=400, detail="Trendyol kimlik bilgileri eksik")
    # Opsiyonel yorum-proxy'si: Trendyol Cloudflare Railway IP'sini 530 ile engellerse, buradaki
    # proxy üzerinden çekilir. Ayar: db.settings(id=trendyol).review_proxy VEYA env TRENDYOL_REVIEW_PROXY.
    _pin_state["proxy"] = settings.get("review_proxy") or os.environ.get("TRENDYOL_REVIEW_PROXY") or ""

    # 1) barcode -> contentId haritası (Trendyol ürünleri; approved filtresi yok = en geniş)
    client = TrendyolClient(supplier_id=str(supplier_id), api_key=api_key, api_secret=api_secret, mode=mode)
    _pin_public_trendyol_if_needed()
    bc_to_cid: dict = {}
    debug = {"mode": mode, "ty_total_elements": None, "ty_total_pages": None,
             "ty_first_page_count": 0, "ty_sample_keys": None, "ty_with_contentid": 0,
             "public_pin_ip": _pin_state["ip"]}
    page = 0
    while page < 300:
        try:
            data = await client.get_filtered_products(page=page, size=200)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Trendyol ürün listesi hatası: {e}")
        content = (data or {}).get("content", []) or []
        if page == 0:
            debug["ty_total_elements"] = (data or {}).get("totalElements")
            debug["ty_total_pages"] = (data or {}).get("totalPages")
            debug["ty_first_page_count"] = len(content)
            if content:
                debug["ty_sample_keys"] = sorted(list(content[0].keys()))
        if not content:
            break
        for p in content:
            bc = (p.get("barcode") or "").strip()
            cid = p.get("productContentId") or p.get("contentId")
            if not cid:
                m = re.search(r"-p-(\d+)", p.get("productUrl") or "")
                if m:
                    cid = m.group(1)
            if bc and cid:
                bc_to_cid[bc] = str(cid)
                debug["ty_with_contentid"] += 1
        total_pages = (data or {}).get("totalPages", 1) or 1
        page += 1
        if page >= total_pages:
            break

    # 2) aktif site ürünleri
    products = await db.products.find(
        {"is_active": True, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "barcode": 1, "variants": 1},
    ).to_list(100000)
    if limit and limit > 0:
        products = products[:limit]

    summary = {
        "trendyol_products_indexed": len(bc_to_cid),
        "site_products": len(products),
        "matched_products": 0,
        "unmatched_products": 0,
        "content_ids_scraped": 0,
        "total_fetched": 0,
        "total_inserted": 0,
        "skipped_low_rating": 0,
        "skipped_existing": 0,
        "errors": [],
        "dry_run": dry_run,
        "min_rating": min_rating,
        "_debug": debug,
    }

    # 3) her ürün için contentId'leri bul, yorumları çek
    for p in products:
        pid = p.get("id")
        barcodes = set()
        if (p.get("barcode") or "").strip():
            barcodes.add(p["barcode"].strip())
        for v in (p.get("variants") or []):
            if (v.get("barcode") or "").strip():
                barcodes.add(v["barcode"].strip())
        cids = []
        for bc in barcodes:
            cid = bc_to_cid.get(bc)
            if cid and cid not in cids:
                cids.append(cid)
        if not cids:
            summary["unmatched_products"] += 1
            continue
        summary["matched_products"] += 1
        for cid in cids:
            try:
                fetched = await _fetch_reviews_for_content_id(cid, min_rating)
            except Exception as e:
                summary["errors"].append({"product_id": pid, "content_id": cid, "error": str(e)[:160]})
                continue
            summary["content_ids_scraped"] += 1
            summary["total_fetched"] += len(fetched)
            if dry_run:
                summary["total_inserted"] += sum(1 for r in fetched if int(r.get("rate") or 0) >= min_rating)
                continue
            res = await _store_reviews(fetched, pid, cid, min_rating)
            summary["total_inserted"] += res["inserted"]
            summary["skipped_low_rating"] += res["skipped_low_rating"]
            summary["skipped_existing"] += res["skipped_existing"]
        if not dry_run:
            await _recalc_product_rating(pid)

    # Teşhis: hangi bağlantı hedefi çalıştı / kaç aday denendi (530 sorunu için).
    debug["public_candidates"] = _pin_state.get("candidates")
    debug["public_good_target"] = None if _pin_state.get("good") in (_UNSET, None) else _pin_state.get("good")
    debug["review_proxy_set"] = bool(_pin_state.get("proxy"))
    return summary


@router.post("/trendyol/reviews/sync-all")
async def sync_all_trendyol_reviews(
    payload: dict,
    current_user: dict = Depends(require_admin),
):
    """
    TÜM aktif site ürünleri için Trendyol 4-5 yıldız yorumlarını toplu çeker.

    Body: { "min_rating": 4, "limit": 0, "dry_run": false }
      - min_rating: alt yıldız sınırı (varsayılan 4 → 4 ve 5 yıldız)
      - limit: yalnızca ilk N ürün (0 = hepsi)
      - dry_run: true → yalnızca sayım, DB'ye yazmaz
    """
    from .integrations import log_integration_event

    payload = payload or {}
    min_rating = int(payload.get("min_rating", 4))
    limit = int(payload.get("limit", 0) or 0)
    dry_run = bool(payload.get("dry_run", False))

    summary = await sync_all_trendyol_reviews_core(min_rating=min_rating, limit=limit, dry_run=dry_run)
    try:
        await log_integration_event(
            "trendyol", "review_sync_all", "bulk", "all", "success",
            f"matched={summary['matched_products']} inserted={summary['total_inserted']} dry_run={dry_run}",
        )
    except Exception:
        pass
    return {"success": True, **summary}
