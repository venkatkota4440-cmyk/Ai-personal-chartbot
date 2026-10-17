"""Conversations and the chat turn.

One turn: save the user's message, pick relevant approved memories (unless
memory is off), ask the provider, validate its answer, add backend safety
notices, then store the reply with a record of which memories it used.
If the provider fails, the user's message stays saved and no reply is
invented: the client gets an explicit error instead.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory, not_found
from app.db.base import utcnow
from app.db.models import Conversation, Memory, Message, MessageRole, User, UserSettings
from app.db.repository import get_owned, owned_select
from app.schemas.chat import ChatResponse, ConversationOut, ConversationUpdate, MessageOut, UsedMemoryOut
from app.schemas.memory import MemoryOut
from app.services import audit, memory, safety
from app.services.ai import AIErrorKind, AIProviderError, ChatRequest, ChatTurn, MemorySnippet, provider_for

logger = logging.getLogger(__name__)

_ERROR_CATEGORY = {
    AIErrorKind.NOT_CONFIGURED: ErrorCategory.AI_UNAVAILABLE,
    AIErrorKind.UNAVAILABLE: ErrorCategory.AI_UNAVAILABLE,
    AIErrorKind.TIMEOUT: ErrorCategory.AI_UNAVAILABLE,
    AIErrorKind.REFUSED: ErrorCategory.AI_REFUSED,
    AIErrorKind.INVALID_OUTPUT: ErrorCategory.AI_INVALID_OUTPUT,
}


def _title_from(text: str) -> str:
    title = " ".join(text.split())
    return title if len(title) <= 60 else title[:57] + "…"


def purge_expired_messages(db: DbSession, user: User) -> int:
    """Apply the user's retention setting. Runs before reads so expired messages are never shown."""
    prefs = db.get(UserSettings, user.id)
    if prefs is None or prefs.message_retention_days is None:
        return 0
    cutoff = utcnow() - timedelta(days=prefs.message_retention_days)
    result = db.execute(sql_delete(Message).where(Message.user_id == user.id, Message.created_at < cutoff))
    removed = int(getattr(result, "rowcount", 0) or 0)
    if removed:
        audit.record(db, action="retention.purge", result="success", user_id=user.id, metadata={"messages": removed})
    db.commit()
    return removed


def get_conversation(db: DbSession, user: User, conversation_id: str) -> Conversation:
    conversation = get_owned(db, Conversation, conversation_id, user.id)
    if conversation is None:
        raise not_found("Conversation")
    return conversation


def list_conversations(db: DbSession, user: User, limit: int = 50) -> list[Conversation]:
    purge_expired_messages(db, user)
    query = owned_select(Conversation, user.id).order_by(Conversation.updated_at.desc()).limit(limit)
    return list(db.scalars(query))


def messages_for(db: DbSession, user: User, conversation: Conversation) -> list[MessageOut]:
    purge_expired_messages(db, user)
    rows = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id, Message.user_id == user.id)
            .order_by(Message.created_at, Message.id)
        )
    )
    referenced = memory.by_ids(db, user, [mid for m in rows for mid in m.used_memory_ids])
    return [message_out(m, referenced) for m in rows]


def update_conversation(db: DbSession, user: User, conversation_id: str, change: ConversationUpdate) -> Conversation:
    conversation = get_conversation(db, user, conversation_id)
    fields = change.model_fields_set
    if "title" in fields and change.title:
        conversation.title = change.title
    if "memory_enabled" in fields and change.memory_enabled is not None:
        conversation.memory_enabled = change.memory_enabled
    conversation.updated_at = utcnow()
    audit.record(
        db,
        action="conversation.update",
        result="success",
        user_id=user.id,
        target=conversation.id,
        metadata={"fields": sorted(fields), "memory_enabled": conversation.memory_enabled},
    )
    db.commit()
    return conversation


def delete_conversation(db: DbSession, user: User, conversation_id: str) -> None:
    conversation = get_conversation(db, user, conversation_id)
    db.delete(conversation)  # messages cascade at the database level
    audit.record(db, action="conversation.delete", result="success", user_id=user.id, target=conversation_id)
    db.commit()


def message_out(message: Message, referenced: dict[str, Memory]) -> MessageOut:
    flags: dict[str, Any] = message.flags or {}
    used: list[UsedMemoryOut] = []
    for memory_id in message.used_memory_ids or []:
        current = referenced.get(memory_id)
        if current is None or current.deleted_at is not None:
            used.append(UsedMemoryOut(id=memory_id, content=None, status="deleted"))
        else:
            edited = current.updated_at > message.created_at
            used.append(UsedMemoryOut(id=memory_id, content=current.content, status="edited" if edited else "current"))
    return MessageOut(
        id=message.id,
        role=message.role.value,
        content=message.content,
        created_at=message.created_at,
        confidence=flags.get("confidence"),
        human_review_note=flags.get("human_review_note"),
        used_memories=used,
        memory_ranking="keyword" if message.role == MessageRole.ASSISTANT and flags.get("memory_enabled") else None,
        model=flags.get("model"),
    )


def send(
    db: DbSession,
    settings: Settings,
    user: User,
    *,
    text: str,
    conversation_id: str | None,
    memory_enabled: bool,
) -> ChatResponse:
    purge_expired_messages(db, user)
    if conversation_id:
        conversation = get_conversation(db, user, conversation_id)
    else:
        conversation = Conversation(user_id=user.id, title=_title_from(text), memory_enabled=memory_enabled)
        db.add(conversation)
        db.flush()

    history_rows = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id, Message.role != MessageRole.SYSTEM)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(settings.chat_history_messages)
        )
    )[::-1]

    user_message = Message(conversation_id=conversation.id, user_id=user.id, role=MessageRole.USER, content=text)
    db.add(user_message)
    conversation.updated_at = utcnow()
    # Commit now: the user's words are kept even if the provider call below fails.
    db.commit()

    prefs = db.get(UserSettings, user.id)
    model = prefs.default_model if prefs else settings.allowed_model_list[0]
    used = memory.relevant_for(db, user, text) if conversation.memory_enabled else []
    request = ChatRequest(
        model=model,
        user_message=text,
        history=[ChatTurn(role=m.role.value, content=m.content) for m in history_rows],  # type: ignore[arg-type]
        memories=[MemorySnippet(id=m.id, content=m.content) for m in used],
        allow_memory_proposals=conversation.memory_enabled,
        timezone=user.timezone,
    )

    try:
        reply = provider_for(model, settings).generate(request)
    except AIProviderError as exc:
        audit.record(
            db,
            action="chat.reply",
            result=f"failed:{exc.kind.value}",
            user_id=user.id,
            actor="assistant",
            target=conversation.id,
            metadata={"model": model},
        )
        db.commit()
        raise AppError(_ERROR_CATEGORY[exc.kind], exc.user_message) from None

    topics = safety.review_topics(text, reply.reply)
    assistant_message = Message(
        conversation_id=conversation.id,
        user_id=user.id,
        role=MessageRole.ASSISTANT,
        content=reply.reply,
        used_memory_ids=[m.id for m in used],
        flags={
            "confidence": reply.confidence,
            "human_review_topics": topics,
            "human_review_note": safety.review_note(topics),
            "model": model,
            "memory_enabled": conversation.memory_enabled,
        },
    )
    db.add(assistant_message)
    # Memory-off means off both ways: nothing read above, nothing proposed here, whatever the model said.
    proposed = (
        memory.propose(db, user, reply.proposed_memories, conversation_id=conversation.id)
        if conversation.memory_enabled
        else []
    )
    conversation.updated_at = utcnow()
    audit.record(
        db,
        action="chat.reply",
        result="success",
        user_id=user.id,
        actor="assistant",
        target=conversation.id,
        metadata={"model": model, "memories_used": len(used), "memories_proposed": len(proposed)},
    )
    db.commit()

    referenced = {m.id: m for m in used}
    return ChatResponse(
        conversation=ConversationOut.model_validate(conversation, from_attributes=True),
        user_message=message_out(user_message, {}),
        assistant_message=message_out(assistant_message, referenced),
        proposed_memories=[MemoryOut.model_validate(m) for m in proposed],
    )
