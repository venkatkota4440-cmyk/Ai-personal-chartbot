from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.auth import StrictModel
from app.schemas.memory import MemoryOut

MAX_MESSAGE_CHARS = 8000


class ChatRequestIn(StrictModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    # Omit to start a new conversation.
    conversation_id: str | None = Field(default=None, max_length=36)
    # Only used when starting a new conversation; existing ones keep their own setting.
    memory_enabled: bool = True


class UsedMemoryOut(BaseModel):
    id: str
    # None when the memory was edited away or deleted after this reply.
    content: str | None
    status: Literal["current", "edited", "deleted"]


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
    confidence: Literal["high", "medium", "low"] | None = None
    human_review_note: str | None = None
    used_memories: list[UsedMemoryOut] = Field(default_factory=list)
    # How memories were matched, stated by the server so clients never guess (PersonalClaw-style disclosure).
    memory_ranking: Literal["keyword"] | None = None
    model: str | None = None


class ConversationOut(BaseModel):
    id: str
    title: str
    memory_enabled: bool
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    memory_enabled: bool | None = None


class ChatResponse(BaseModel):
    conversation: ConversationOut
    user_message: MessageOut
    assistant_message: MessageOut
    proposed_memories: list[MemoryOut]
