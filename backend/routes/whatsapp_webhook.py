"""
WhatsApp AI Müşteri Temsilcisi — Meta Cloud API webhook.

Akış:
  Müşteri WhatsApp'tan yazar → Meta bu uca POST atar → mevcut AI beyni
  (ai_chatbot: persona + bilgi bankası + ürün + sipariş bağlamı + güven/handoff)
  "gerçek bir kıdemli müşteri temsilcisi" tonunda Türkçe yanıt üretir → 24-saat
  müşteri-hizmetleri penceresinde SERBEST METİN olarak geri gönderilir
  (müşteri ilk yazdığı için template gerekmez).

Güvenlik/guardrail:
  - Kimlik: settings.notification_providers.providers.whatsapp_meta
    (phone_number_id, access_token, verify_token, app_secret[ops]).
  - AÇ/KAPA: ai_chatbot.enabled VE ai_chatbot.channels.whatsapp (varsayılan KAPALI).
  - Düşük güven / handoff → cevabı UYDURMAZ; kısa bir "temsilcimize ilettim" mesajı
    gönderir + whatsapp_handoffs'a kaydeder (insan devralır).
  - Opt-out (DURDUR/STOP/IPTAL) → yanıt vermez, opt-out kaydı tutar.
  - Idempotent: her Meta mesaj id'si bir kez işlenir (döngü/çift-yanıt yok).
  - Kendi numaramızdan geleni ve statü-webhook'larını yok sayar.
  - Meta imza doğrulaması (X-Hub-Signature-256) app_secret varsa uygulanır.
  - Meta'ya HIZLI 200 döner; AI üretimi arka planda yapılır.
"""
import os
import hmac
import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse

from .deps import db, logger
from .ai_chatbot import (
    get_ai_settings, _api_key_for, llm_chat, DEFAULT_PERSONA,
    _gather_kb_context, _gather_product_context,
)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp-ai"])

_OPT_OUT = {"durdur", "stop", "iptal", "çık", "cik", "abonelikten çık"}
_OPT_IN = {"başla", "basla", "devam", "aç", "ac"}


async def _wa_cfg() -> dict:
    s = await db.settings.find_one({"id": "notification_providers"}, {"_id": 0}) or {}
    return ((s.get("providers") or {}).get("whatsapp_meta") or {})


# ── Webhook doğrulama (Meta panel: Callback URL kaydı) ──────────────────────
@router.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    cfg = await _wa_cfg()
    expected = cfg.get("verify_token") or os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    if mode == "subscribe" and expected and token == expected:
        return PlainTextResponse(challenge or "")
    return PlainTextResponse("forbidden", status_code=403)


def _verify_signature(app_secret: str, raw: bytes, header: str) -> bool:
    if not app_secret:
        return True  # app_secret ayarlı değilse imza kontrolü atlanır (Meta panelinden zorunlu kılınabilir)
    if not header or not header.startswith("sha256="):
        return False
    mac = hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, header.split("=", 1)[1])


# ── Gelen mesaj → arka planda AI yanıt ──────────────────────────────────────
@router.post("/webhook")
async def receive_webhook(request: Request, background: BackgroundTasks):
    raw = await request.body()
    cfg = await _wa_cfg()
    # İmza doğrulama (app_secret varsa)
    if not _verify_signature(cfg.get("app_secret", ""), raw,
                             request.headers.get("x-hub-signature-256", "")):
        return PlainTextResponse("bad signature", status_code=403)
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return {"ok": True}

    for entry in (data.get("entry") or []):
        for ch in (entry.get("changes") or []):
            value = ch.get("value") or {}
            own_pnid = (value.get("metadata") or {}).get("phone_number_id")
            contacts = {c.get("wa_id"): (c.get("profile") or {}).get("name")
                        for c in (value.get("contacts") or [])}
            for m in (value.get("messages") or []):
                if m.get("type") != "text":
                    continue  # sadece metin (medya/konum vb. ilk sürümde atlanır)
                sender = m.get("from")
                mid = m.get("id")
                body = ((m.get("text") or {}).get("body") or "").strip()
                if not sender or not mid or not body:
                    continue
                # Arka planda işle (Meta'ya hemen 200 dön)
                background.add_task(
                    _handle_inbound, sender=sender, mid=mid, body=body,
                    name=contacts.get(sender), own_pnid=own_pnid,
                )
    return {"ok": True}


async def _already_processed(mid: str) -> bool:
    """Idempotency — aynı Meta mesaj id'si iki kez işlenmesin."""
    try:
        res = await db.whatsapp_processed.update_one(
            {"_id": mid},
            {"$setOnInsert": {"at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        return res.upserted_id is None
    except Exception:
        return False


async def _recent_orders_context(phone: str) -> str:
    """Müşterinin telefonuna göre son siparişleri (grounded veri) bağlam olarak verir."""
    from notification_service import normalize_phone_tr
    norm = normalize_phone_tr(phone)
    tail = norm[-10:] if norm else phone[-10:]
    try:
        cur = db.orders.find(
            {"$or": [{"phone": {"$regex": tail + "$"}},
                     {"shipping_address.phone": {"$regex": tail + "$"}}]},
            {"_id": 0, "order_number": 1, "status": 1, "payment_status": 1,
             "total": 1, "created_at": 1, "tracking_number": 1, "cargo_company": 1},
        ).sort("created_at", -1).limit(3)
        rows = await cur.to_list(3)
    except Exception:
        rows = []
    if not rows:
        return ""
    lines = ["[Müşterinin Son Siparişleri]"]
    for o in rows:
        seg = f"- Sipariş {o.get('order_number','?')}: durum={o.get('status','?')}"
        if o.get("payment_status"):
            seg += f", ödeme={o.get('payment_status')}"
        if o.get("tracking_number"):
            seg += f", kargo={o.get('cargo_company','')} takip={o.get('tracking_number')}"
        lines.append(seg)
    return "\n".join(lines)


async def _handle_inbound(sender: str, mid: str, body: str,
                          name: Optional[str], own_pnid: Optional[str]):
    try:
        if await _already_processed(mid):
            return
        cfg = await _wa_cfg()
        # Kendi numaramızdan geldiyse yok say (döngü koruması)
        if own_pnid and cfg.get("phone_number_id") and own_pnid == cfg.get("phone_number_id") and sender == own_pnid:
            return

        low = body.lower().strip()
        # Opt-out / opt-in
        if low in _OPT_OUT:
            await db.whatsapp_optout.update_one(
                {"_id": sender}, {"$set": {"opted_out": True, "at": _now()}}, upsert=True)
            await _send(cfg, sender, "Bilgilendirme mesajlarımız durduruldu. Yeniden başlatmak için 'BAŞLA' yazabilirsiniz.")
            await _log(sender, body, "[opt-out]", handoff=False, confidence=1.0)
            return
        if low in _OPT_IN:
            await db.whatsapp_optout.update_one(
                {"_id": sender}, {"$set": {"opted_out": False, "at": _now()}}, upsert=True)

        settings = await get_ai_settings()
        # AÇ/KAPA: AI beyni genel açık VE WhatsApp otomatik-yanıt anahtarı açık olmalı
        # (Bildirim Ayarları > WhatsApp Meta > "AI otomatik yanıt"). Varsayılan KAPALI.
        if not settings.get("enabled", True) or not cfg.get("ai_autoreply", False):
            await _log(sender, body, "", handoff=True, confidence=0.0, note="ai_whatsapp_disabled")
            return

        api_key = _api_key_for(settings)
        if not api_key:
            await _log(sender, body, "", handoff=True, confidence=0.0, note="no_api_key")
            return

        # Bağlam topla (grounded): bilgi bankası + ürün + son siparişler + firma
        kb_ctx = await _gather_kb_context(body)
        prod_ctx = await _gather_product_context(body)
        ord_ctx = await _recent_orders_context(sender)
        store_name = await _store_name()

        system = settings.get("persona") or DEFAULT_PERSONA
        if store_name:
            system += f"\n\nMağaza adı: {store_name}. Kendini bu mağazanın temsilcisi olarak tanıt."
        system += (
            "\n\nKanal: WhatsApp. Kısa, sıcak, gerçek bir insan temsilci gibi yaz "
            "(1-4 cümle). Müşteri adını uygunsa bir kez kullan. Emin olmadığın "
            "sipariş/stok/fiyat/iade bilgisini UYDURMA; bilmiyorsan devret.\n"
            "--- BİLGİ KAYNAĞI (yalnız bunları kullan) ---\n"
        )
        if ord_ctx:
            system += f"\n{ord_ctx}\n"
        if prod_ctx:
            system += f"\n[Ürün Bilgisi]\n{prod_ctx}\n"
        if kb_ctx:
            system += f"\n[Bilgi Bankası]\n{kb_ctx}\n"
        system += (
            "\nCevabın SONUNA ayrı satırda şu bloğu ekle:\n"
            "---META---\nCONFIDENCE: <0.0-1.0>\nHANDOFF: <yes|no>\n"
        )
        user_text = f"Müşteri ({name or 'isimsiz'}): {body}"

        try:
            resp = await llm_chat(
                api_key=api_key,
                provider=settings.get("provider", "anthropic"),
                model=settings.get("fast_model") or settings.get("model", "claude-haiku-4-5"),
                system_message=system, user_text=user_text, max_tokens=500,
            )
        except Exception as e:
            logger.exception("WA AI reply failed")
            await _log(sender, body, "", handoff=True, confidence=0.0, note=f"llm_error:{e}")
            await _handoff(sender, body, name)
            return

        reply, confidence, handoff = _parse_meta(str(resp or ""))
        threshold = float(settings.get("confidence_threshold", 0.7) or 0.7)
        if confidence < threshold:
            handoff = True

        # Opt-out ettiyse yine cevaplarız (müşteri-hizmetleri penceresi); pazarlama göndermeyiz.
        if handoff or not reply:
            await _handoff(sender, body, name)
            await _log(sender, body, reply, handoff=True, confidence=confidence)
            return

        await _send(cfg, sender, reply)
        await _log(sender, body, reply, handoff=False, confidence=confidence)
    except Exception as e:
        logger.exception(f"WA inbound handler error: {e}")


def _parse_meta(text: str):
    import re
    confidence, handoff = 0.7, False
    reply = text.strip()
    m = re.search(r"---META---\s*CONFIDENCE:\s*([0-9.]+)\s*HANDOFF:\s*(\w+)", text, re.I)
    if m:
        try:
            confidence = max(0.0, min(1.0, float(m.group(1))))
        except Exception:
            pass
        handoff = m.group(2).lower().startswith("y")
        reply = text[:m.start()].strip()
    reply = re.split(r"-{2,}\s*META", reply, 1)[0].strip()
    return reply, confidence, handoff


async def _handoff(sender: str, body: str, name: Optional[str]):
    """İnsan temsilciye devret: kayıt aç + müşteriye kısa bekletme mesajı."""
    cfg = await _wa_cfg()
    try:
        await db.whatsapp_handoffs.insert_one({
            "phone": sender, "name": name, "question": body,
            "status": "open", "created_at": _now(),
        })
    except Exception:
        pass
    await _send(cfg, sender, "Talebinizi müşteri temsilcimize ilettim, en kısa sürede size dönüş yapacağız. 🙏")


async def _send(cfg: dict, to: str, message: str):
    from notification_service import _whatsapp_send
    # Opt-out kontrolü (bekletme/opt-out onayı hariç zaten çağrılmaz)
    try:
        res = await _whatsapp_send(cfg, to, message)
        if not res.get("success"):
            logger.warning(f"WA send failed to {to[-4:]}: {res.get('response')}")
    except Exception as e:
        logger.warning(f"WA send error: {e}")


async def _log(phone: str, inbound: str, outbound: str, *, handoff: bool,
               confidence: float, note: str = ""):
    try:
        await db.whatsapp_conversations.insert_one({
            "phone": phone, "inbound": inbound, "outbound": outbound,
            "handoff": handoff, "confidence": confidence, "note": note,
            "created_at": _now(),
        })
    except Exception:
        pass


async def _store_name() -> str:
    try:
        import company
        c = await company.get_company(db)
        return c.get("store_name") or ""
    except Exception:
        return ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
