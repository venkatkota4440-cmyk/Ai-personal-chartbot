"""Redaction helpers shared by logging and the audit trail.

Anything that might be a credential is removed by key name; free text is
scrubbed for common secret shapes. This is defence in depth: callers should
still avoid passing sensitive data in the first place.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "session",
    "credential",
    "private_key",
    "csrf",
)

_TEXT_PATTERNS = (
    re.compile(r"(?i)bearer\s+[a-z0-9._\-~+/]+=*"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S+"),
)
_EMAIL = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")

_MAX_DEPTH = 5
_MAX_STRING = 500


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def mask_email(email: str) -> str:
    """Keep enough to recognise the account in an audit log without storing the full address."""
    return _EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", email)


def redact_text(text: str) -> str:
    for pattern in _TEXT_PATTERNS:
        text = pattern.sub(REDACTED, text)
    text = mask_email(text)
    return text if len(text) <= _MAX_STRING else text[:_MAX_STRING] + "…"


def redact(value: Any, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return REDACTED
    if isinstance(value, Mapping):
        return {str(k): (REDACTED if is_sensitive_key(str(k)) else redact(v, depth + 1)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, depth + 1) for v in value[:50]]
    if isinstance(value, str):
        return redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(str(value))
