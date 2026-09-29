from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import utcnow
from .models import Run, Workflow


def next_due(
    cadence: str,
    zone_name: str,
    hour: int,
    week_day: int,
    after: datetime | None = None,
) -> datetime | None:
    if cadence == "none":
        return None
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(422, "Unknown timezone") from exc
    now = (after or utcnow()).replace(tzinfo=timezone.utc).astimezone(zone)
    for days in range(8):
        date = now.date() + timedelta(days=days)
        if cadence == "weekly" and date.weekday() != week_day:
            continue
        candidate = datetime(date.year, date.month, date.day, hour, tzinfo=zone)
        # A spring-forward gap maps to a different local hour; skip that date.
        round_trip = candidate.astimezone(timezone.utc).astimezone(zone)
        if round_trip.hour == hour and candidate > now:
            return candidate.astimezone(timezone.utc).replace(tzinfo=None)
    raise HTTPException(422, "Unable to compute next schedule")


def enqueue_run(db: Session, workflow: Workflow, trigger: str, run_key: str) -> Run:
    run = Run(
        workflow_id=workflow.id,
        org_id=workflow.org_id,
        trigger=trigger,
        run_key=run_key,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(Run).where(Run.workflow_id == workflow.id, Run.run_key == run_key)
        )
        if existing is None:
            raise
        return existing
    db.refresh(run)
    return run
