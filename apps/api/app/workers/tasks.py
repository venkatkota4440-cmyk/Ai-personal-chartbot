"""Background job entry points for the RQ worker.

Jobs receive IDs only, never payloads, and load everything else from the
database under the owning user's scope.

Start a worker with:  rq worker --url "$REDIS_URL" default
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.db.session import get_sessionmaker
from app.services.automation import execute_run

logger = logging.getLogger(__name__)


def heartbeat() -> str:
    return datetime.now(UTC).isoformat()


def run_automation(run_id: str) -> str:
    """Execute or resume one automation run. Idempotent: a repeat is a no-op once finished."""
    db = get_sessionmaker()()
    try:
        outcome = execute_run(db, run_id)
        logger.info("run finished", extra={"run_id": run_id, "status": outcome.status.value})
        return outcome.status.value
    finally:
        db.close()
