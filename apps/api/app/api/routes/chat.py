from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbDep, LimiterDep, SettingsDep
from app.core.rate_limit import enforce
from app.schemas.chat import (
    ChatRequestIn,
    ChatResponse,
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
)
from app.services import chat

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def send_message(
    body: ChatRequestIn, user: CurrentUser, db: DbDep, settings: SettingsDep, limiter: LimiterDep
) -> ChatResponse:
    # Per user, not per IP: each turn may cost money at the AI provider.
    enforce(limiter, f"chat:user:{user.id}", settings.chat_rate_limit_per_minute, 60)
    return chat.send(
        db,
        settings,
        user,
        text=body.message,
        conversation_id=body.conversation_id,
        memory_enabled=body.memory_enabled,
    )


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    user: CurrentUser, db: DbDep, limit: int = Query(default=50, ge=1, le=200)
) -> list[ConversationOut]:
    return [ConversationOut.model_validate(c, from_attributes=True) for c in chat.list_conversations(db, user, limit)]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, user: CurrentUser, db: DbDep) -> ConversationDetail:
    conversation = chat.get_conversation(db, user, conversation_id)
    base = ConversationOut.model_validate(conversation, from_attributes=True)
    return ConversationDetail(**base.model_dump(), messages=chat.messages_for(db, user, conversation))


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def update_conversation(
    conversation_id: str, body: ConversationUpdate, user: CurrentUser, db: DbDep
) -> ConversationOut:
    conversation = chat.update_conversation(db, user, conversation_id, body)
    return ConversationOut.model_validate(conversation, from_attributes=True)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, user: CurrentUser, db: DbDep) -> Response:
    chat.delete_conversation(db, user, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
