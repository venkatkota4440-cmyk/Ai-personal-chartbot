from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import DbDep

router = APIRouter(prefix="/api", tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
def health(db: DbDep) -> JSONResponse:
    """Liveness + database readiness. Reports component status only, never configuration values."""
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        logger.exception("Health check database query failed")
        database = "unavailable"
    healthy = database == "ok"
    return JSONResponse(
        {"status": "ok" if healthy else "degraded", "components": {"database": database}},
        status_code=200 if healthy else 503,
    )
