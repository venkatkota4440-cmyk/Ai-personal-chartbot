from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbDep
from app.db.base import utcnow
from app.db.models import MemoryStatus
from app.schemas.memory import MemoryCreate, MemoryExport, MemoryOut, MemoryStatusLiteral, MemoryUpdate
from app.services import audit, memory

router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("", response_model=list[MemoryOut])
def list_memories(
    user: CurrentUser, db: DbDep, status_filter: Annotated[MemoryStatusLiteral | None, Query(alias="status")] = None
) -> list[MemoryOut]:
    rows = memory.list_memories(db, user, MemoryStatus(status_filter) if status_filter else None)
    return [MemoryOut.model_validate(m) for m in rows]


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def create_memory(body: MemoryCreate, user: CurrentUser, db: DbDep) -> MemoryOut:
    return MemoryOut.model_validate(memory.create_by_user(db, user, body.content))


# Declared before /{memory_id} so "export" is not captured as an ID.
@router.get("/export")
def export_memories(user: CurrentUser, db: DbDep) -> JSONResponse:
    payload = MemoryExport(
        exported_at=utcnow(), memories=[MemoryOut.model_validate(m) for m in memory.list_memories(db, user)]
    )
    audit.record(
        db, action="memory.export", result="success", user_id=user.id, metadata={"count": len(payload.memories)}
    )
    db.commit()
    return JSONResponse(
        payload.model_dump(mode="json"),
        headers={"Content-Disposition": 'attachment; filename="memories-export.json"'},
    )


@router.patch("/{memory_id}", response_model=MemoryOut)
def update_memory(memory_id: str, body: MemoryUpdate, user: CurrentUser, db: DbDep) -> MemoryOut:
    return MemoryOut.model_validate(memory.update(db, user, memory_id, body))


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(memory_id: str, user: CurrentUser, db: DbDep) -> Response:
    memory.delete(db, user, memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
