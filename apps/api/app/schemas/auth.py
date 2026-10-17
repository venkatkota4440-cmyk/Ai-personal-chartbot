from __future__ import annotations

from datetime import datetime
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_TIMEZONES = frozenset(available_timezones())


def validate_timezone(value: str) -> str:
    if value not in _TIMEZONES:
        raise ValueError("Unknown timezone; use an IANA name such as 'Asia/Kolkata' or 'UTC'")
    return value


class StrictModel(BaseModel):
    # Unknown fields are rejected so typos and injected fields fail loudly instead of being ignored.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RegisterRequest(StrictModel):
    email: EmailStr = Field(max_length=320)
    # Upper bound stops very long inputs from making hashing expensive.
    password: str = Field(min_length=1, max_length=256)
    timezone: str = Field(default="UTC", max_length=64)

    _tz = field_validator("timezone")(validate_timezone)


class LoginRequest(StrictModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    timezone: str
    created_at: datetime


class CsrfOut(BaseModel):
    csrf_token: str
