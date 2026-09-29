import csv
import io
import json
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import Principal, get_principal, require_owner
from .config import settings
from .db import get_db, utcnow
from .models import QuotaUsage, Record, Run, Source, Workflow
from .providers import ProviderUnavailable, ensure_model_ready, plan_prompt
from .quotas import LIMITS, QuotaExceeded, consume, period_for
from .scheduling import enqueue_run, next_due
from .schemas import ApproveRequest, DraftRequest, ScheduleRequest
from .worker import drain_queue

app = FastAPI(title="Data Intelligence API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings().frontend_origin],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)


def workflow_or_404(db: Session, principal: Principal, workflow_id: str) -> Workflow:
    workflow = db.scalar(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.org_id == principal.org_id)
    )
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    return workflow


def run_or_404(db: Session, principal: Principal, run_id: str) -> Run:
    run = db.scalar(select(Run).where(Run.id == run_id, Run.org_id == principal.org_id))
    if not run:
        raise HTTPException(404, "Run not found")
    return run


def dispatch(run_id: str, background: BackgroundTasks) -> None:
    if settings().dispatch_mode == "modal":
        import modal

        modal.Function.from_name(settings().modal_app_name, "run_worker").spawn(run_id)
    elif settings().dispatch_mode == "local":
        background.add_task(drain_queue, run_id)
    else:
        raise HTTPException(503, "Run dispatcher is not configured")


def workflow_json(workflow: Workflow) -> dict:
    return jsonable_encoder(
        {
            name: getattr(workflow, name)
            for name in (
                "id",
                "org_id",
                "creator_id",
                "prompt",
                "title",
                "queries",
                "fields",
                "identity_fields",
                "status",
                "cadence",
                "local_hour",
                "week_day",
                "timezone",
                "next_run_at",
                "pause_reason",
                "first_run_at",
                "created_at",
            )
        }
    )


def run_json(run: Run) -> dict:
    return jsonable_encoder(
        {
            name: getattr(run, name)
            for name in (
                "id",
                "workflow_id",
                "trigger",
                "status",
                "stage",
                "pause_reason",
                "error",
                "searched",
                "scraped",
                "observations",
                "cancel_requested",
                "created_at",
                "started_at",
                "finished_at",
            )
        }
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/usage")
def usage(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict:
    result = {}
    for kind, limit in LIMITS.items():
        period = period_for(kind)
        row = db.scalar(
            select(QuotaUsage).where(
                QuotaUsage.org_id == principal.org_id,
                QuotaUsage.kind == kind,
                QuotaUsage.period == period,
            )
        )
        result[kind] = {
            "used": row.used if row else 0,
            "limit": limit,
            "period": period,
        }
    return result


@app.post("/api/drafts", status_code=201)
def create_draft(
    body: DraftRequest,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    try:
        ensure_model_ready()
        consume(db, principal.org_id, "model")
        proposal = plan_prompt(body.prompt)
    except (QuotaExceeded, ProviderUnavailable) as exc:
        raise HTTPException(503, str(exc)) from exc
    workflow = Workflow(
        org_id=principal.org_id,
        creator_id=principal.user_id,
        prompt=body.prompt,
        title=proposal.title,
        queries=proposal.queries,
        fields=[field.model_dump() for field in proposal.fields],
        identity_fields=proposal.identity_fields,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow_json(workflow)


@app.get("/api/workflows")
def list_workflows(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> list[dict]:
    rows = db.scalars(
        select(Workflow)
        .where(Workflow.org_id == principal.org_id)
        .order_by(Workflow.created_at.desc())
    ).all()
    return [workflow_json(row) for row in rows]


@app.get("/api/workflows/{workflow_id}")
def get_workflow(
    workflow_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    return workflow_json(workflow_or_404(db, principal, workflow_id))


@app.post("/api/workflows/{workflow_id}/approve")
def approve(
    workflow_id: str,
    body: ApproveRequest,
    background: BackgroundTasks,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    workflow = workflow_or_404(db, principal, workflow_id)
    require_owner(principal, workflow.creator_id)
    if workflow.status != "draft" or workflow.first_run_at:
        raise HTTPException(409, "Schema is locked; clone this workflow to change fields")
    workflow.title = body.title
    workflow.queries = body.queries
    workflow.fields = [field.model_dump() for field in body.fields]
    workflow.identity_fields = body.identity_fields
    workflow.status = "active"
    db.commit()
    run = enqueue_run(db, workflow, "approval", "approval")
    dispatch(run.id, background)
    return {"workflow": workflow_json(workflow), "run": run_json(run)}


@app.post("/api/workflows/{workflow_id}/clone", status_code=201)
def clone(
    workflow_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    original = workflow_or_404(db, principal, workflow_id)
    require_owner(principal, original.creator_id)
    copy = Workflow(
        org_id=principal.org_id,
        creator_id=principal.user_id,
        prompt=original.prompt,
        title=f"{original.title} (copy)"[:160],
        queries=original.queries,
        fields=original.fields,
        identity_fields=original.identity_fields,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return workflow_json(copy)


@app.patch("/api/workflows/{workflow_id}/schedule")
def set_schedule(
    workflow_id: str,
    body: ScheduleRequest,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    workflow = workflow_or_404(db, principal, workflow_id)
    require_owner(principal, workflow.creator_id)
    if workflow.status != "active":
        raise HTTPException(409, "Approve fields before scheduling")
    workflow.cadence = body.cadence
    workflow.timezone = body.timezone
    workflow.local_hour = body.local_hour
    workflow.week_day = body.week_day
    workflow.next_run_at = next_due(body.cadence, body.timezone, body.local_hour, body.week_day)
    db.commit()
    return workflow_json(workflow)


@app.post("/api/workflows/{workflow_id}/runs", status_code=201)
def rerun(
    workflow_id: str,
    background: BackgroundTasks,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    workflow = workflow_or_404(db, principal, workflow_id)
    require_owner(principal, workflow.creator_id)
    if workflow.status != "active":
        raise HTTPException(409, "Approve fields before running")
    run = enqueue_run(db, workflow, "manual", f"manual:{uuid4()}")
    dispatch(run.id, background)
    return run_json(run)


@app.get("/api/workflows/{workflow_id}/runs")
def list_runs(
    workflow_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    workflow_or_404(db, principal, workflow_id)
    return [
        run_json(row)
        for row in db.scalars(
            select(Run)
            .where(Run.workflow_id == workflow_id, Run.org_id == principal.org_id)
            .order_by(Run.created_at.desc())
        ).all()
    ]


@app.get("/api/runs/{run_id}")
def get_run(
    run_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    return run_json(run_or_404(db, principal, run_id))


@app.post("/api/runs/{run_id}/cancel")
def cancel(
    run_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    run = run_or_404(db, principal, run_id)
    workflow = workflow_or_404(db, principal, run.workflow_id)
    require_owner(principal, workflow.creator_id)
    if run.status in {"completed", "cancelled", "failed"}:
        raise HTTPException(409, "Run is already finished")
    run.cancel_requested = True
    if run.status in {"queued", "paused"}:
        run.status = "cancelled"
        run.stage = "cancelled"
        run.finished_at = utcnow()
    db.commit()
    return run_json(run)


@app.post("/api/runs/{run_id}/retry", status_code=201)
def retry(
    run_id: str,
    background: BackgroundTasks,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    previous = run_or_404(db, principal, run_id)
    workflow = workflow_or_404(db, principal, previous.workflow_id)
    require_owner(principal, workflow.creator_id)
    if previous.status not in {"failed", "cancelled", "paused"}:
        raise HTTPException(409, "Only failed, cancelled, or paused runs can be retried")
    run = enqueue_run(db, workflow, "retry", f"retry:{uuid4()}")
    dispatch(run.id, background)
    return run_json(run)


@app.get("/api/workflows/{workflow_id}/records")
def list_records(
    workflow_id: str,
    q: str = Query(default="", max_length=200),
    field: str | None = None,
    value: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    workflow = workflow_or_404(db, principal, workflow_id)
    names = {item["name"] for item in workflow.fields}
    if field and field not in names:
        raise HTTPException(422, "Unknown filter field")
    rows = db.scalars(
        select(Record)
        .where(Record.workflow_id == workflow_id, Record.org_id == principal.org_id)
        .order_by(Record.last_seen_at.desc())
    ).all()
    filtered = [
        row
        for row in rows
        if (not q or q.casefold() in json.dumps(row.data, ensure_ascii=False).casefold())
        and (
            not field
            or value is None
            or value.casefold() in str(row.data.get(field, "")).casefold()
        )
    ]
    page = filtered[offset : offset + limit]
    sources = (
        {
            source.id: source
            for source in db.scalars(
                select(Source).where(
                    Source.org_id == principal.org_id,
                    Source.id.in_([row.source_id for row in page]),
                )
            ).all()
        }
        if page
        else {}
    )
    return [
        jsonable_encoder(
            {
                "id": row.id,
                "data": row.data,
                "source_id": row.source_id,
                "source_url": sources[row.source_id].url,
                "fetched_at": sources[row.source_id].fetched_at,
                "evidence": row.evidence,
                "first_seen_at": row.first_seen_at,
                "last_seen_at": row.last_seen_at,
                "observation_count": row.observation_count,
            }
        )
        for row in page
    ]


@app.get("/api/sources/{source_id}")
def get_source(
    source_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    source = db.scalar(
        select(Source).where(Source.id == source_id, Source.org_id == principal.org_id)
    )
    if not source:
        raise HTTPException(404, "Source not found")
    return jsonable_encoder(
        {
            "id": source.id,
            "url": source.url,
            "title": source.title,
            "excerpt": source.excerpt,
            "fetched_at": source.fetched_at,
            "run_id": source.run_id,
        }
    )


@app.get("/api/workflows/{workflow_id}/export")
def export(
    workflow_id: str,
    format: str = Query(pattern="^(csv|json)$"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Response:
    workflow = workflow_or_404(db, principal, workflow_id)
    rows = db.scalars(
        select(Record)
        .where(Record.workflow_id == workflow.id, Record.org_id == principal.org_id)
        .order_by(Record.first_seen_at)
    ).all()
    sources = (
        {
            source.id: source
            for source in db.scalars(
                select(Source).where(
                    Source.org_id == principal.org_id,
                    Source.id.in_([row.source_id for row in rows]),
                )
            ).all()
        }
        if rows
        else {}
    )
    data = [
        {
            **row.data,
            "source_url": sources[row.source_id].url,
            "evidence": row.evidence,
            "fetched_at": sources[row.source_id].fetched_at.isoformat(),
            "first_seen_at": row.first_seen_at.isoformat(),
            "last_seen_at": row.last_seen_at.isoformat(),
        }
        for row in rows
    ]
    headers = {"Content-Disposition": f'attachment; filename="{workflow.id}.{format}"'}
    if format == "json":
        return Response(
            json.dumps(data, ensure_ascii=False),
            media_type="application/json",
            headers=headers,
        )
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[field["name"] for field in workflow.fields]
        + ["source_url", "evidence", "fetched_at", "first_seen_at", "last_seen_at"],
    )
    writer.writeheader()
    writer.writerows(
        {
            key: f"'{value}"
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
            else value
            for key, value in row.items()
        }
        for row in data
    )
    return Response(output.getvalue(), media_type="text/csv", headers=headers)
