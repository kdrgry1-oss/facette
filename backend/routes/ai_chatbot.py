"""
AI Chatbot (Customer Service Assistant) module.

Architecture:
  - One orchestrator agent (LlmChat) driven by persona + RAG-style knowledge.
  - Tools are not delegated to the LLM via function-calling here (keeps it simple
    and reliable); instead we pre-fetch product/order/policy data and inject as
    context before the model generates a Turkish reply.
  - Draft generation returns the suggested answer + confidence score.
  - If confidence < threshold, we hint the panel to hand off to a human.
  - Each approved Q&A pair is added to `ai_knowledge_base` as a reusable FAQ.

Settings live in `db.settings` under id="ai_chatbot".
Conversations per marketplace live in their own collections; `ai_suggestions`
tracks draft answers attached to a specific question_id.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import Optional
import os
import uuid
import re

from emergentintegrations.llm.chat import LlmChat, UserMessage

from .deps import db, require_admin, logger

router = APIRouter(prefix="/ai", tags=["ai-chatbot"])

DEFAULT_PERSONA = (
    "Sen Facette marka moda mağazasının kıdemli müşteri temsilcisisin. "
    "Kısa, sıcak, samimi ve profesyonel bir tonla Türkçe konuşursun. "
    "Emin olmadığın bilgiyi kesinlikle uydurmazsın; 'kontrol edip yazayım' dersin. "
    "Gereksiz emoji kullanma, müşterinin adını uygunsa bir kez kullan, tekrara düşme. "
    "Stok/fiyat/sipariş bilgisini sadece sana sağlanan verilerden cevapla. "
    "Gerekirse müşteriyi hafif bir CTA ile satışa yönlendir."
)


async def get_ai_settings() -> dict:
    s = await db.settings.find_one({"id": "ai_chatbot"}, {"_id": 0})
    if not s:
        return {
            "id": "ai_chatbot",
            "enabled": True,
            "provider": "openai",
            "model": "gpt-5.2",
            "fast_model": "gpt-5-mini",
            "persona": DEFAULT_PERSONA,
            "confidence_threshold": 0.7,
            "use_emergent_key": True,
            "custom_api_key": "",
            "channels": {
                "trendyol": True, "hepsiburada": True, "temu": True,
                "whatsapp": False, "instagram": False, "messenger": False, "site": True,
            },
        }
    return s


def _api_key_for(settings: dict) -> str:
    if settings.get("use_emergent_key", True):
        return os.environ.get("EMERGENT_LLM_KEY", "")
    return settings.get("custom_api_key") or ""


# -------------------- Settings endpoints --------------------

@router.get("/settings")
async def get_ai_chatbot_settings(current_user: dict = Depends(require_admin)):
    s = await get_ai_settings()
    # Mask sensitive
    if s.get("custom_api_key"):
        s["custom_api_key"] = "********"
    return s


@router.post("/settings")
async def save_ai_chatbot_settings(payload: dict, current_user: dict = Depends(require_admin)):
    update = {
        "id": "ai_chatbot",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    for f in (
        "enabled", "provider", "model", "fast_model", "persona",
        "confidence_threshold", "use_emergent_key", "channels",
    ):
        if f in payload:
            update[f] = payload[f]
    if payload.get("custom_api_key") and payload["custom_api_key"] != "********":
        update["custom_api_key"] = payload["custom_api_key"]
    await db.settings.update_one({"id": "ai_chatbot"}, {"$set": update}, upsert=True)
    return {"success": True}


# -------------------- Knowledge Base endpoints --------------------

@router.get("/kb")
async def list_kb_entries(
    q: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    query = {}
    if q:
        query["$or"] = [
            {"question": {"$regex": q, "$options": "i"}},
            {"answer": {"$regex": q, "$options": "i"}},
        ]
    items = await db.ai_knowledge_base.find(query, {"_id": 0}).sort("usage_count", -1).limit(500).to_list(500)
    total = await db.ai_knowledge_base.count_documents({})
    return {"items": items, "total": total}


@router.post("/kb")
async def add_kb_entry(payload: dict, current_user: dict = Depends(require_admin)):
    question = (payload or {}).get("question", "").strip()
    answer = (payload or {}).get("answer", "").strip()
    if not question or not answer:
        raise HTTPException(status_code=400, detail="Soru ve cevap boş olamaz")
    doc = {
        "id": str(uuid.uuid4()),
        "question": question,
        "answer": answer,
        "tags": payload.get("tags", []),
        "channel": payload.get("channel", "all"),
        "source_question_id": payload.get("source_question_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.get("email", ""),
        "usage_count": 0,
    }
    await db.ai_knowledge_base.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "entry": doc}


@router.delete("/kb/{entry_id}")
async def delete_kb_entry(entry_id: str, current_user: dict = Depends(require_admin)):
    res = await db.ai_knowledge_base.delete_one({"id": entry_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    return {"success": True}


# -------------------- Draft generation --------------------

MARKETPLACE_TO_COLL = {
    "trendyol": "trendyol_questions",
    "hepsiburada": "hepsiburada_questions",
    "temu": "temu_questions",
    "whatsapp": "whatsapp_messages",
    "instagram": "instagram_messages",
    "messenger": "messenger_messages",
    "site": "site_messages",
}


async def _gather_kb_context(question_text: str) -> str:
    """Return top 5 KB entries loosely matching the question (keyword-based MVP)."""
    words = [w for w in re.split(r"\W+", question_text.lower()) if len(w) > 3]
    if not words:
        return ""
    or_clauses = [{"question": {"$regex": w, "$options": "i"}} for w in words[:5]]
    items = await db.ai_knowledge_base.find(
        {"$or": or_clauses}, {"_id": 0, "question": 1, "answer": 1}
    ).limit(5).to_list(5)
    if not items:
        return ""
    return "\n".join(f"- S: {i['question']}\n  C: {i['answer']}" for i in items)


async def _gather_product_context(product_name: str) -> str:
    if not product_name:
        return ""
    prods = await db.products.find(
        {"name": {"$regex": re.escape(product_name[:40]), "$options": "i"}},
        {"_id": 0, "name": 1, "price": 1, "stock": 1, "variants": 1, "description": 1}
    ).limit(3).to_list(3)
    if not prods:
        return ""
    lines = []
    for p in prods:
        sv = [f"{v.get('size')}:{v.get('stock', 0)}" for v in (p.get("variants") or [])][:10]
        lines.append(
            f"- Ürün: {p.get('name')} | Fiyat: {p.get('price', '—')} TL | "
            f"Toplam Stok: {p.get('stock', 0)} | Bedenler: {', '.join(sv) if sv else 'tek beden'}"
        )
    return "\n".join(lines)


@router.post("/draft/{marketplace}/{question_id}")
async def generate_draft_answer(
    marketplace: str,
    question_id: str,
    payload: Optional[dict] = None,
    current_user: dict = Depends(require_admin),
):
    if marketplace not in MARKETPLACE_TO_COLL:
        raise HTTPException(status_code=404, detail="Bilinmeyen kanal")
    coll = db[MARKETPLACE_TO_COLL[marketplace]]
    q = await coll.find_one({"question_id": question_id}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Soru bulunamadı")

    settings = await get_ai_settings()
    if not settings.get("enabled", True):
        raise HTTPException(status_code=400, detail="AI Chatbot devre dışı")

    api_key = _api_key_for(settings)
    if not api_key:
        raise HTTPException(status_code=400, detail="AI anahtarı yapılandırılmamış")

    kb_ctx = await _gather_kb_context(q.get("question_text", ""))
    prod_ctx = await _gather_product_context(q.get("product_name", ""))

    system = settings.get("persona") or DEFAULT_PERSONA
    system += (
        "\n\n--- BİLGİ KAYNAĞI ---\n"
        "Aşağıdaki bilgileri kullan. Bilgi yoksa uydurma.\n"
    )
    if prod_ctx:
        system += f"\n[Ürün Bilgisi]\n{prod_ctx}\n"
    if kb_ctx:
        system += f"\n[Bilgi Bankası - Önceki Onaylı Yanıtlar]\n{kb_ctx}\n"
    system += (
        "\nCevabın sonuna yeni bir satıra ÖZEL bir blok ekle:\n"
        "---META---\n"
        "CONFIDENCE: <0.0-1.0 arası bir değer>\n"
        "HANDOFF: <yes veya no – insan temsilciye devredilmeli mi?>\n"
    )

    session_id = f"q-{marketplace}-{question_id}"
    chat = LlmChat(
        api_key=api_key,
        session_id=session_id,
        system_message=system,
    ).with_model(settings.get("provider", "openai"), settings.get("model", "gpt-5.2"))

    user_text = (
        f"[{marketplace.upper()} Kanalı]\n"
        f"Ürün: {q.get('product_name', '—')}\n"
        f"Müşteri: {q.get('customer_name', '—')}\n"
        f"Soru: {q.get('question_text', '')}"
    )

    try:
        response = await chat.send_message(UserMessage(text=user_text))
    except Exception as e:
        logger.exception("AI draft failed")
        raise HTTPException(status_code=500, detail=f"AI cevap üretemedi: {e}")

    text = str(response or "").strip()
    confidence = 0.75
    handoff = False
    # Parse META block
    m = re.search(r"---META---\s*CONFIDENCE:\s*([0-9.]+)\s*HANDOFF:\s*(\w+)", text, re.IGNORECASE)
    draft_text = text
    if m:
        try:
            confidence = float(m.group(1))
        except Exception:
            pass
        handoff = m.group(2).lower().startswith("y")
        draft_text = text[: m.start()].strip()

    threshold = float(settings.get("confidence_threshold", 0.7) or 0.7)
    if confidence < threshold:
        handoff = True

    suggestion_doc = {
        "id": str(uuid.uuid4()),
        "marketplace": marketplace,
        "question_id": question_id,
        "draft": draft_text,
        "confidence": confidence,
        "handoff": handoff,
        "model": settings.get("model", "gpt-5.2"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.get("email", ""),
    }
    await db.ai_suggestions.insert_one(suggestion_doc)

    return {
        "success": True,
        "draft": draft_text,
        "confidence": confidence,
        "handoff": handoff,
        "threshold": threshold,
    }


@router.post("/train-from-question")
async def train_from_question(payload: dict, current_user: dict = Depends(require_admin)):
    """Add an approved Q+A to the knowledge base (called from 'AI'yı Eğit' button)."""
    question = (payload or {}).get("question", "").strip()
    answer = (payload or {}).get("answer", "").strip()
    if not question or not answer:
        raise HTTPException(status_code=400, detail="Soru ve cevap gerekli")
    doc = {
        "id": str(uuid.uuid4()),
        "question": question,
        "answer": answer,
        "channel": payload.get("channel", "all"),
        "source_question_id": payload.get("question_id"),
        "tags": payload.get("tags", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.get("email", ""),
        "usage_count": 0,
    }
    await db.ai_knowledge_base.insert_one(doc)
    return {"success": True}
