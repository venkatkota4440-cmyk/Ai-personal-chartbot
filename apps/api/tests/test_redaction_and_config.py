from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.redaction import REDACTED, mask_email, redact


def test_redact_removes_sensitive_keys_recursively() -> None:
    data = {
        "password": "p",
        "nested": {"api_key": "k", "Authorization": "Bearer abc", "ok": "visible"},
        "list": [{"session_token": "t"}],
    }
    result = redact(data)
    assert result["password"] == REDACTED
    assert result["nested"]["api_key"] == REDACTED
    assert result["nested"]["Authorization"] == REDACTED
    assert result["nested"]["ok"] == "visible"
    assert result["list"][0]["session_token"] == REDACTED


def test_redact_scrubs_secret_shapes_in_free_text() -> None:
    text = redact("call failed with Bearer abc.def and key sk-ABCDEFGHIJKLMNOP for jane.doe@example.com")
    assert "abc.def" not in text
    assert "sk-ABCDEFGHIJKLMNOP" not in text
    assert "jane.doe@example.com" not in text
    assert "j***@example.com" in text


def test_mask_email() -> None:
    assert mask_email("owner@example.com") == "o***@example.com"


def test_production_requires_real_session_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", session_secret="replace_with_long_random_secret")
    with pytest.raises(ValidationError):
        Settings(app_env="production", session_secret="too-short")
    ok = Settings(app_env="production", session_secret="s" * 48)
    assert ok.secure_cookies is True


def test_development_generates_ephemeral_secret() -> None:
    settings = Settings(app_env="development", session_secret="")
    assert len(settings.session_secret) >= 32
    assert settings.secure_cookies is False
