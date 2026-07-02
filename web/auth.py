"""Minimal shared-password auth via a signed cookie (stdlib only)."""

from __future__ import annotations

import base64
import hmac
import time
from hashlib import sha256

COOKIE_NAME = "fre_session"
_MAX_AGE = 7 * 24 * 3600  # 7 days


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def issue_token(secret: bytes, issued_at: int | None = None) -> str:
    issued_at = int(time.time()) if issued_at is None else issued_at
    payload = str(issued_at).encode("ascii")
    sig = hmac.new(secret, payload, sha256).digest()
    return f"{_b64(payload)}.{_b64(sig)}"


def verify_token(token: str, secret: bytes) -> bool:
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = _unb64(payload_b64)
        sig = _unb64(sig_b64)
    except (ValueError, Exception):  # noqa: BLE001 - any malformed token is just invalid
        return False

    expected = hmac.new(secret, payload, sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return False

    try:
        issued_at = int(payload.decode("ascii"))
    except ValueError:
        return False
    return (time.time() - issued_at) <= _MAX_AGE


def check_password(candidate: str, expected: str) -> bool:
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))
