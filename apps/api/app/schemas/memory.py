from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import StrictModel

MemoryStatusLiteral = Literal["proposed", "approved", "rejected"]


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    content: str
    source: str
    status: MemoryStatusLiteral
    conversation_id: str | None
    created_at: datetime
    updated_at: datetime


class MemoryCreate(StrictModel):
    content: str = Field(min_length=1, max_length=1000)


class MemoryUpdate(StrictModel):
    content: str | None = Field(default=None, min_length=1, max_length=1000)
    # Users decide; "proposed" is only ever set by the system.
    status: Literal["approved", "rejected"] | None = None


class MemoryExport(BaseModel):
    exported_at: datetime
    memories: list[MemoryOut]
