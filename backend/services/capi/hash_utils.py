"""
PII Hashing utilities for CAPI (Conversions API) integrations.
All advertising platforms (Meta, Google, TikTok, Pinterest, Snapchat) require
user PII to be hashed with SHA-256 in lowercase form before being sent.
"""
import hashlib
import re
from typing import Optional


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def hash_email(email: Optional[str]) -> Optional[str]:
    """Hash email (trimmed + lowercased)."""
    e = _norm(email)
    if not e or "@" not in e:
        return None
    return _sha256(e)


def hash_phone(phone: Optional[str], default_country: str = "90") -> Optional[str]:
    """Hash phone in E.164 format (digits only, country code prefixed).

    Examples:
      '0532 123 4567'  → '905321234567' → sha256
      '+905321234567'  → '905321234567' → sha256
    """
    if not phone:
        return None
    digits = re.sub(r"\D+", "", str(phone))
    if not digits:
        return None
    # Drop leading 0 if Turkish formatted
    if digits.startswith("0") and not digits.startswith("00"):
        digits = digits[1:]
    if not digits.startswith(default_country) and len(digits) == 10:
        digits = default_country + digits
    return _sha256(digits)


def hash_name(name: Optional[str]) -> Optional[str]:
    """Hash first/last name (trimmed + lowercased)."""
    n = _norm(name)
    if not n:
        return None
    return _sha256(n)


def hash_city(city: Optional[str]) -> Optional[str]:
    n = re.sub(r"\s+", "", _norm(city))
    return _sha256(n) if n else None


def hash_country(country_code: Optional[str]) -> Optional[str]:
    """ISO 3166-1 alpha-2 lowercase (tr, us, …)."""
    n = _norm(country_code)
    if len(n) != 2:
        return None
    return _sha256(n)


def hash_zip(zipcode: Optional[str]) -> Optional[str]:
    z = re.sub(r"\s+", "", _norm(zipcode))
    return _sha256(z) if z else None


def build_user_data(
    *,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    city: Optional[str] = None,
    country: Optional[str] = "TR",
    zipcode: Optional[str] = None,
    external_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    fbp: Optional[str] = None,                 # Meta browser cookie
    fbc: Optional[str] = None,                 # Meta click ID cookie
    gclid: Optional[str] = None,               # Google click ID
    ttclid: Optional[str] = None,              # TikTok click ID
    epik: Optional[str] = None,                # Pinterest click ID
    sc_click_id: Optional[str] = None,         # Snapchat click ID
) -> dict:
    """Return a normalized user_data dict with raw + hashed values.

    Each provider's adapter pulls the fields it needs.
    """
    return {
        # Hashed
        "em": hash_email(email),
        "ph": hash_phone(phone),
        "fn": hash_name(first_name),
        "ln": hash_name(last_name),
        "ct": hash_city(city),
        "country": hash_country(country or "TR"),
        "zp": hash_zip(zipcode),
        "external_id": _sha256(external_id) if external_id else None,
        # Raw (server-side context)
        "client_ip_address": client_ip,
        "client_user_agent": user_agent,
        # Click IDs (sent raw)
        "fbp": fbp,
        "fbc": fbc,
        "gclid": gclid,
        "ttclid": ttclid,
        "epik": epik,
        "sc_click_id": sc_click_id,
    }
