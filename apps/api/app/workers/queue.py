"""Job queue with an in-process fallback.

WORKER_MODE=redis  : runs are handed to an RQ worker (docker compose, production).
WORKER_MODE=inline : runs execute in the calling process. Keeps local demos and
                     tests working with no Redis, which the brief asks for.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session as DbSession

from app.core.config import Settings
from app.services.automation import RunOutcome, execute_run

logger = logging.getLogger(__name__)


def run_or_enqueue(db: DbSession, settings: Settings, run_id: str) -> RunOutcome:
    if settings.worker_mode == "inline":
        return execute_run(db, run_id)

    try:
        import redis
        from rq import Queue

        queue = Queue("default", connection=redis.Redis.from_url(settings.redis_url, socket_timeout=2))
        queue.enqueue("app.workers.tasks.run_automation", run_id, job_timeout=600)
    except Exception:
        # Never lose the run because the queue is unreachable: fall back to running it here.
        logger.exception("could not enqueue run; executing inline instead", extra={"run_id": run_id})
        return execute_run(db, run_id)

    from app.db.models import AutomationRun

    run = db.get(AutomationRun, run_id)
    return RunOutcome(run_id, run.status if run else None)  # type: ignore[arg-type]
