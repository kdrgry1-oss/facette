"""Security-safe admin mutation audit helpers.

This module appends schema-v2 records to the existing ``audit_logs`` collection.
It never changes or rewrites legacy audit/auth/order/stock records.
"""
from datetime import datetime, timezone
import hashlib
import logging
import re
from typing import Optional
from urllib.parse import urlsplit, urlunsplit


_SECRET_KEY = re.compile(
    r"password|passwd|token|secret|api.?key|private.?key|authorization|cookie|session.?id|"
    r"client.?secret|access.?key|refresh.?key|cvv|cvc|card|pan|iban",
    re.I,
)
_PII_KEY = re.compile(
    r"(^|_)(email|phone|mobile|address|first.?name|last.?name|full.?name|sender.?name|"
    r"tax.?(?:number|no)|identity|tckn|vkn|recipient|customer)(_|$)",
    re.I,
)
_BULKY_KEY = re.compile(r"content|html|description|body|image|video|template", re.I)
_EMAIL = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
_PHONE = re.compile(r"(?<!\d)(?:\+?90\s*)?(?:\(?0?5\d{2}\)?[\s.-]*)?\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]+)?\b")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def _safe_text(value: str) -> str:
    text = str(value or "")
    if _JWT.search(text) or _CARD.search(text):
        return "[REDACTED]"
    if _EMAIL.search(text) or _PHONE.search(text):
        return "[REDACTED_PII]"
    if text.startswith(("http://", "https://")):
        parts = urlsplit(text)
        text = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return text[:500] + ("…" if len(text) > 500 else "")


def redact_value(value, *, key: str = "", depth: int = 0):
    """Return a bounded, JSON-safe representation with secrets and PII removed."""
    if _SECRET_KEY.search(key or ""):
        return "[REDACTED]"
    if _PII_KEY.search(key or ""):
        return "[REDACTED_PII]"
    if _BULKY_KEY.search(key or ""):
        if isinstance(value, (list, tuple, dict)):
            return f"[{type(value).__name__} {len(value)}]"
        return f"[text {len(str(value or ''))} chars]"
    if depth >= 4:
        return "[nested]"
    if isinstance(value, dict):
        return {str(k)[:80]: redact_value(v, key=str(k), depth=depth + 1)
                for k, v in list(value.items())[:80]}
    if isinstance(value, (list, tuple)):
        return [redact_value(v, depth=depth + 1) for v in list(value)[:30]]
    if isinstance(value, str):
        return _safe_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _safe_text(str(value))


def redacted_diff(before: Optional[dict], after: Optional[dict]) -> dict:
    before, after = before or {}, after or {}
    changed = sorted(k for k in set(before) | set(after)
                     if k not in {"_id", "updated_at"} and before.get(k) != after.get(k))
    return {
        str(k)[:80]: {
            "old": redact_value(before.get(k), key=str(k)),
            "new": redact_value(after.get(k), key=str(k)),
        }
        for k in changed[:100]
    }


def audit_actor(current_user: Optional[dict], request=None) -> tuple[dict, dict]:
    user = current_user or {}
    email = str(user.get("email") or user.get("username") or "").strip().lower()
    actor = {
        "id": str(user.get("id") or user.get("user_id") or ""),
        # Identity remains joinable by internal user id. Email is not duplicated
        # into the audit collection; its hash supports correlation if an account
        # is later deleted.
        "email_hash": hashlib.sha256(email.encode()).hexdigest()[:16] if email else "",
        "role": str(user.get("role") or ("admin" if user.get("is_admin") else "")),
        "login_method": str(user.get("login_method") or user.get("auth_provider") or user.get("provider") or ""),
    }
    auth, ua, ip = "", "", ""
    if request is not None:
        auth = str(request.headers.get("authorization") or "")
        ua = str(request.headers.get("user-agent") or "")[:300]
        forwarded = str(request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        ip = forwarded or str(getattr(getattr(request, "client", None), "host", "") or "")
    return actor, {
        "session_hash": hashlib.sha256(auth.encode()).hexdigest()[:12] if auth else "",
        "ip": ip[:64], "user_agent": ua,
    }


async def record_admin_audit(db, *, action: str, entity_type: str, entity_id: str,
                             before: Optional[dict] = None, after: Optional[dict] = None,
                             current_user: Optional[dict] = None, request=None,
                             source: str = "admin", success: bool = True,
                             metadata: Optional[dict] = None) -> bool:
    """Best-effort append. It cannot turn an applied mutation into a retryable error."""
    actor, context = audit_actor(current_user, request)
    now = datetime.now(timezone.utc).isoformat()
    seed = f"{now}|{actor.get('id')}|{action}|{entity_type}|{entity_id}"
    try:
        await db.audit_logs.insert_one({
            "id": hashlib.sha256(seed.encode()).hexdigest()[:32],
            "schema_version": 2, "category": "admin_mutation", "action": str(action)[:120],
            "entity": {"type": str(entity_type)[:80], "id": str(entity_id)[:160]},
            "actor": actor, "context": context, "source": str(source)[:120],
            "success": bool(success), "diff": redacted_diff(before, after),
            "metadata": redact_value(metadata or {}), "created_at": now,
        })
        return True
    except Exception:
        logging.getLogger(__name__).exception("admin audit insert failed action=%s entity=%s", action, entity_id)
        return False
