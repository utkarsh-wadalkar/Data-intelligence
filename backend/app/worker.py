import hashlib
import json
import time
from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import SessionLocal, utcnow
from .models import ExecutionLease, Observation, Record, Run, Source, Workflow
from .providers import (
    ProviderUnavailable,
    ensure_model_ready,
    ensure_search_ready,
    extract,
    public_url,
    scrape,
    search,
)
from .quotas import QuotaExceeded, consume
from .scheduling import enqueue_run, next_due

RATE_LIMIT_DELAYS = (1, 3, 5, 10, 30, 120, 300, 1440)


def is_openrouter_rate_limit(reason: str) -> bool:
    return reason.startswith("OpenRouter rate limit reached") or (
        "openrouter.ai" in reason and "429 Too Many Requests" in reason
    )


def claim(db: Session, run_id: str) -> bool:
    run = db.get(Run, run_id)
    if run is None or run.status != "queued":
        return False
    now = utcnow()
    lease = db.get(ExecutionLease, run.org_id)
    if lease is None:
        try:
            db.add(ExecutionLease(org_id=run.org_id, run_id=None, expires_at=now))
            db.commit()
        except IntegrityError:
            db.rollback()
    result = db.execute(
        update(ExecutionLease)
        .where(
            ExecutionLease.org_id == run.org_id,
            or_(ExecutionLease.run_id.is_(None), ExecutionLease.expires_at < now),
        )
        .values(run_id=run.id, expires_at=now + timedelta(minutes=12))
    )
    if result.rowcount != 1:
        db.rollback()
        return False
    changed = db.execute(
        update(Run)
        .where(Run.id == run.id, Run.status == "queued")
        .values(status="running", stage="searching", started_at=now, next_retry_at=None)
    )
    if changed.rowcount != 1:
        db.rollback()
        return False
    db.commit()
    workflow = db.get(Workflow, run.workflow_id)
    if workflow.first_run_at is None:
        workflow.first_run_at = now
        db.commit()
    return True


def release(db: Session, run: Run) -> None:
    db.execute(
        update(ExecutionLease)
        .where(ExecutionLease.org_id == run.org_id, ExecutionLease.run_id == run.id)
        .values(run_id=None, expires_at=utcnow())
    )
    db.commit()


def record_key(data: dict, identity_fields: list[str]) -> str | None:
    parts = [str(data.get(name, "")).strip().casefold() for name in identity_fields]
    if any(not part or part == "none" for part in parts):
        return None
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def store_observation(
    db: Session, workflow: Workflow, run: Run, source: Source, item: dict, page: str
) -> bool:
    data, evidence = item.get("data"), item.get("evidence")
    if not isinstance(data, dict) or not isinstance(evidence, str):
        return False
    evidence = " ".join(evidence.split())[:400]
    if len(evidence) < 12 or evidence.casefold() not in " ".join(page.split()).casefold():
        return False
    names = {field["name"] for field in workflow.fields}
    if set(data) != names:
        return False
    for field in workflow.fields:
        value = data[field["name"]]
        if value is None:
            continue
        expected = field["type"]
        if expected in {"text", "date", "url"} and not isinstance(value, str):
            return False
        if expected == "number" and (
            not isinstance(value, (float, int)) or isinstance(value, bool)
        ):
            return False
        if expected == "boolean" and not isinstance(value, bool):
            return False
        if expected == "url" and value and not public_url(value):
            return False
    key = record_key(data, workflow.identity_fields)
    if key is None or db.scalar(
        select(Observation.id).where(Observation.run_id == run.id, Observation.record_key == key)
    ):
        return False
    now = utcnow()
    db.add(
        Observation(
            org_id=run.org_id,
            workflow_id=workflow.id,
            run_id=run.id,
            source_id=source.id,
            record_key=key,
            data=data,
            evidence=evidence,
            observed_at=now,
        )
    )
    existing = db.scalar(
        select(Record).where(Record.workflow_id == workflow.id, Record.record_key == key)
    )
    if existing:
        existing.data = data
        existing.source_id = source.id
        existing.evidence = evidence
        existing.last_seen_at = now
        existing.observation_count += 1
    else:
        db.add(
            Record(
                org_id=run.org_id,
                workflow_id=workflow.id,
                record_key=key,
                data=data,
                source_id=source.id,
                evidence=evidence,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
    db.commit()
    return True


def process_run(run_id: str) -> None:
    with SessionLocal() as db:
        if not claim(db, run_id):
            return
        run = db.get(Run, run_id)
        workflow = db.get(Workflow, run.workflow_id)
        deadline = time.monotonic() + 600
        try:
            ensure_search_ready()
            ensure_model_ready()
            checkpoint = run.checkpoint or {
                "query_index": max(0, run.searched - 1) if run.searched else 0,
                "hits": [],
                "hit_index": 0,
                "seen_urls": [],
                "page": None,
                "source_id": None,
            }
            if run.checkpoint is None:
                run.checkpoint = dict(checkpoint)
                db.commit()
            while checkpoint["query_index"] < min(3, len(workflow.queries)):
                db.refresh(run)
                if time.monotonic() >= deadline or run.cancel_requested:
                    break
                if not checkpoint["hits"] and checkpoint["hit_index"] == 0:
                    if run.searched >= 3:
                        raise QuotaExceeded("Per-run limit of three searches reached")
                    # Count the search before calling the provider, including failed calls.
                    consume(db, run.org_id, "web")
                    run.searched += 1
                    db.commit()
                    found = search(workflow.queries[checkpoint["query_index"]])
                    checkpoint["hits"] = found
                    run.checkpoint = dict(checkpoint)
                    db.commit()
                run.stage = "scraping"
                db.commit()
                while checkpoint["hit_index"] < len(checkpoint["hits"]):
                    db.refresh(run)
                    if (
                        (run.scraped >= 12 and not checkpoint["page"])
                        or run.observations >= 100
                        or time.monotonic() >= deadline
                        or run.cancel_requested
                    ):
                        break
                    hit = checkpoint["hits"][checkpoint["hit_index"]]
                    url = hit.get("url", "") if isinstance(hit, dict) else ""
                    if not checkpoint["page"]:
                        if not public_url(url) or url in checkpoint["seen_urls"]:
                            checkpoint["hit_index"] += 1
                            run.checkpoint = dict(checkpoint)
                            db.commit()
                            continue
                        consume(db, run.org_id, "web")
                        try:
                            title, page = scrape(url)
                        except ProviderUnavailable as exc:
                            if "skipped" in str(exc):
                                checkpoint["seen_urls"].append(url)
                                checkpoint["hit_index"] += 1
                                run.checkpoint = dict(checkpoint)
                                db.commit()
                                continue
                            raise
                        source = Source(
                            org_id=run.org_id,
                            run_id=run.id,
                            url=url,
                            title=title,
                            excerpt=" ".join(page.split())[:400],
                            fetched_at=utcnow(),
                        )
                        db.add(source)
                        db.flush()
                        checkpoint["page"] = page
                        checkpoint["source_id"] = source.id
                        checkpoint["seen_urls"].append(url)
                        run.scraped += 1
                        run.checkpoint = dict(checkpoint)
                        db.commit()
                    page = checkpoint["page"]
                    source = db.get(Source, checkpoint["source_id"])
                    run.stage = "extracting"
                    db.commit()
                    consume(db, run.org_id, "model")
                    items = extract(page, workflow.fields)
                    if run.retry_attempt:
                        run.recovery_count += 1
                        run.retry_attempt = 0
                        db.commit()
                    for item in items:
                        if run.observations >= 100 or run.cancel_requested:
                            break
                        if store_observation(db, workflow, run, source, item, page):
                            run.observations += 1
                            db.commit()
                    checkpoint["page"] = None
                    checkpoint["source_id"] = None
                    checkpoint["hit_index"] += 1
                    run.checkpoint = dict(checkpoint)
                    db.commit()
                if (
                    checkpoint["hit_index"] < len(checkpoint["hits"])
                    or run.scraped >= 12
                    or run.observations >= 100
                    or run.cancel_requested
                    or time.monotonic() >= deadline
                ):
                    break
                checkpoint["query_index"] += 1
                checkpoint["hits"] = []
                checkpoint["hit_index"] = 0
                run.checkpoint = dict(checkpoint)
                run.stage = "searching"
                db.commit()
            db.refresh(run)
            run.status = "cancelled" if run.cancel_requested else "completed"
            run.stage = run.status
            run.finished_at = utcnow()
            workflow.pause_reason = None
            run.checkpoint = None
        except (QuotaExceeded, ProviderUnavailable) as exc:
            db.rollback()
            run = db.get(Run, run_id)
            workflow = db.get(Workflow, run.workflow_id)
            run.status = "paused"
            run.stage = "paused"
            run.pause_reason = str(exc)
            workflow.pause_reason = str(exc)
            if is_openrouter_rate_limit(run.pause_reason):
                run.retry_attempt += 1
                delay = RATE_LIMIT_DELAYS[min(run.retry_attempt - 1, len(RATE_LIMIT_DELAYS) - 1)]
                run.next_retry_at = utcnow() + timedelta(minutes=delay)
            elif run.pause_reason != "Per-run limit of three searches reached":
                run.next_retry_at = utcnow() + timedelta(hours=1)
        except Exception as exc:
            db.rollback()
            run = db.get(Run, run_id)
            run.status = "failed"
            run.stage = "failed"
            run.error = str(exc)[:500]
            run.finished_at = utcnow()
        finally:
            db.commit()
            release(db, run)


def tick() -> list[str]:
    """Minute scheduler and recovery pass. Dispatch is performed after the transaction."""
    created: list[str] = []
    with SessionLocal() as db:
        now = utcnow()
        expired = db.scalars(
            select(ExecutionLease).where(
                ExecutionLease.run_id.is_not(None), ExecutionLease.expires_at < now
            )
        ).all()
        for lease in expired:
            db.execute(
                update(Run)
                .where(Run.id == lease.run_id, Run.status == "running")
                .values(
                    status="queued",
                    stage="recovered",
                    error="Worker lease expired; resuming collection",
                )
            )
            lease.run_id = None
        db.commit()
        workflows = db.scalars(
            select(Workflow).where(
                Workflow.status == "active",
                Workflow.next_run_at.is_not(None),
                Workflow.next_run_at <= now,
            )
        ).all()
        for workflow in workflows:
            blocked = db.scalar(
                select(Run.id).where(
                    Run.workflow_id == workflow.id,
                    Run.status.in_(["queued", "running", "paused"]),
                )
            )
            if blocked:
                continue
            due = workflow.next_run_at
            run = enqueue_run(db, workflow, "scheduled", f"scheduled:{due.isoformat()}")
            workflow.next_run_at = next_due(
                workflow.cadence,
                workflow.timezone,
                workflow.local_hour,
                workflow.week_day,
                now,
            )
            db.commit()
            created.append(run.id)
        # Paused runs retain their identifiers and checkpointed provider work.
        for run in db.scalars(select(Run).where(Run.status == "paused")).all():
            if run.pause_reason == "Per-run limit of three searches reached":
                continue
            if is_openrouter_rate_limit(run.pause_reason or "") and run.retry_attempt == 0:
                # Count the pre-migration 429 as the first failed attempt.
                run.retry_attempt = 1
            if run.next_retry_at is None:
                # Existing paused runs predate the staged-retry migration.
                delay = 1 if is_openrouter_rate_limit(run.pause_reason or "") else 60
                run.next_retry_at = now + timedelta(minutes=delay)
                continue
            if run.next_retry_at > now:
                continue
            run.status = "queued"
            run.stage = "retrying"
            run.pause_reason = None
            run.next_retry_at = None
        db.commit()
        created.extend(db.scalars(select(Run.id).where(Run.status == "queued")).all())
    return list(dict.fromkeys(created))


def drain_queue(first_run_id: str | None = None) -> None:
    candidate = first_run_id
    for _ in range(100):
        if candidate is None:
            with SessionLocal() as db:
                candidate = db.scalar(
                    select(Run.id).where(Run.status == "queued").order_by(Run.created_at)
                )
        if candidate is None:
            return
        process_run(candidate)
        with SessionLocal() as db:
            # Another worker holds the lease; leave this run queued for its drain pass.
            if db.scalar(select(Run.id).where(Run.id == candidate, Run.status == "queued")):
                return
        candidate = None
