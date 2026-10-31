"""Privacy helpers for telephony identifiers."""

from __future__ import annotations

import hashlib
import hmac


def caller_user_id(phone_number: str, secret: str) -> str:
    """Return a stable pseudonymous user id without storing the phone number."""
    digits = "".join(character for character in phone_number if character.isdigit())
    if not digits or not secret:
        return ""
    digest = hmac.new(secret.encode("utf-8"), digits.encode("ascii"), hashlib.sha256).hexdigest()
    return f"caller:{digest}"
