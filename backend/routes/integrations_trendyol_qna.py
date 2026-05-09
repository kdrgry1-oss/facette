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
import re
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
                        "answer": q.get("answers", [{}])[0].get("text", "") if q.get("answers") else "",
                        "image_url": q.get("imageUrl", ""),
                        "synced_at": datetime.now(timezone.utc).isoformat(),
                    }
                    if existing:
                        await db.trendyol_questions.update_one({"question_id": q_id}, {"$set": doc})
                        updated += 1
                    else:
                        doc["id"] = generate_id()
                        doc["created_at"] = datetime.now(timezone.utc).isoformat()
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
