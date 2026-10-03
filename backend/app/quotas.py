from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import QuotaUsage

LIMITS = {"model": 20, "web": 600}


class QuotaExceeded(Exception):
    pass


def period_for(kind: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d" if kind == "model" else "%Y-%m")


def consume(db: Session, org_id: str, kind: str, amount: int = 1) -> None:
    if kind not in LIMITS or amount < 1:
        raise ValueError("Invalid quota request")
    period = period_for(kind)
    result = db.execute(
        update(QuotaUsage)
        .where(
            QuotaUsage.org_id == org_id,
            QuotaUsage.kind == kind,
            QuotaUsage.period == period,
            QuotaUsage.used <= LIMITS[kind] - amount,
        )
        .values(used=QuotaUsage.used + amount)
    )
    if result.rowcount == 1:
        db.commit()
        return
    db.rollback()
    try:
        db.add(QuotaUsage(org_id=org_id, kind=kind, period=period, used=amount))
        db.commit()
        return
    except IntegrityError:
        db.rollback()
    result = db.execute(
        update(QuotaUsage)
        .where(
            QuotaUsage.org_id == org_id,
            QuotaUsage.kind == kind,
            QuotaUsage.period == period,
            QuotaUsage.used <= LIMITS[kind] - amount,
        )
        .values(used=QuotaUsage.used + amount)
    )
    if result.rowcount != 1:
        db.rollback()
        raise QuotaExceeded(f"{kind} quota exhausted for {period}")
    db.commit()
