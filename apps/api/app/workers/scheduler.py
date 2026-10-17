"""Cron scheduler for enabled automations.

Runs as its own process:  python -m app.workers.scheduler

Each minute it finds automations whose cron matches the current minute in the
owner's timezone and queues a run. The idempotency key contains that exact
minute, so a restart, a second scheduler, or a slow tick cannot produce a
duplicate run for the same slot.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.models import Automation, TriggerType, User
from app.db.session import get_sessionmaker
from app.workers import queue

logger = logging.getLogger(__name__)


def _field_matches(field: str, value: int) -> bool:
    """Supports '*', '*/n', 'a,b,c' and 'a-b' — the subset a personal scheduler needs."""
    for part in field.split(","):
        part = part.strip()
        if part in ("*", "?"):
            return True
        if part.startswith("*/"):
            step = int(part[2:]) if part[2:].isdigit() else 0
            if step and value % step == 0:
                return True
        elif "-" in part:
            start, _, end = part.partition("-")
            if start.isdigit() and end.isdigit() and int(start) <= value <= int(end):
                return True
        elif part.isdigit() and int(part) == value:
            return True
    return False


def cron_matches(expression: str, moment: datetime) -> bool:
    """True when a 5-field cron expression fires at `moment` (minute resolution)."""
    fields = expression.split()
    if len(fields) != 5:
        return False
    minute, hour, day, month, weekday = fields
    return (
        _field_matches(minute, moment.minute)
        and _field_matches(hour, moment.hour)
        and _field_matches(day, moment.day)
        and _field_matches(month, moment.month)
        # cron weekdays: 0 and 7 are both Sunday; Python's weekday() has Monday as 0.
        and (_field_matches(weekday, (moment.weekday() + 1) % 7) or _field_matches(weekday, moment.weekday() + 1))
    )


def tick(now_utc: datetime | None = None) -> int:
    """Queue every automation due this minute. Returns how many runs were created."""
    settings = get_settings()
    db = get_sessionmaker()()
    created = 0
    try:
        rows = db.scalars(
            select(Automation).where(
                Automation.enabled.is_(True),
                Automation.trigger_type == TriggerType.SCHEDULE,
                Automation.cron.is_not(None),
            )
        ).all()
        for automation in rows:
            user = db.get(User, automation.user_id)
            if user is None or not automation.cron:
                continue
            try:
                zone = ZoneInfo(user.timezone)
            except Exception:
                zone = ZoneInfo("UTC")
            moment = (now_utc or datetime.now(ZoneInfo("UTC"))).astimezone(zone)
            if not cron_matches(automation.cron, moment):
                continue

            from app.services.automation import enqueue_run

            slot = moment.strftime("%Y-%m-%dT%H:%M")
            run, is_new = enqueue_run(
                db,
                settings,
                user,
                automation,
                trigger=TriggerType.SCHEDULE,
                client_idempotency_key=f"schedule:{slot}",
            )
            if is_new:
                created += 1
                queue.run_or_enqueue(db, settings, run.id)
                logger.info("scheduled run queued", extra={"automation_id": automation.id, "slot": slot})
    finally:
        db.close()
    return created


def main() -> None:  # pragma: no cover - process entry point
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("scheduler started")
    while True:
        try:
            tick()
        except Exception:
            logger.exception("scheduler tick failed")
        # Sleep to the top of the next minute so each slot is evaluated once.
        time.sleep(60 - (time.time() % 60))


if __name__ == "__main__":  # pragma: no cover
    main()
