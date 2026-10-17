"""Password hashing, session tokens, and CSRF tokens.

Session tokens are random and only their SHA-256 hash is stored, so a database
leak does not reveal usable session cookies.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

SESSION_COOKIE = "paa_session"
CSRF_COOKIE = "paa_csrf"
CSRF_HEADER = "X-CSRF-Token"

# argon2-cffi defaults to argon2id with OWASP-recommended parameters.
_hasher = PasswordHasher()

# Verifying against a fixed dummy hash keeps login timing similar whether or not the email exists.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing-equalisation")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_csrf_token(secret: str) -> str:
    """Signed double-submit token: a subdomain that can plant cookies still cannot forge the signature."""
    nonce = secrets.token_urlsafe(24)
    return f"{nonce}.{_sign(secret, nonce)}"


def csrf_token_is_valid(secret: str, cookie_value: str | None, header_value: str | None) -> bool:
    if not cookie_value or not header_value:
        return False
    if not hmac.compare_digest(cookie_value, header_value):
        return False
    nonce, _, signature = cookie_value.partition(".")
    return bool(nonce) and hmac.compare_digest(signature, _sign(secret, nonce))


def _sign(secret: str, value: str) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
