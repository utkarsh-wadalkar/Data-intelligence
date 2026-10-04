from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main, worker
from app.auth import Principal, get_principal
from app.db import Base, get_db, utcnow
from app.models import Observation, Record, Run, Workflow
from app.providers import ProviderUnavailable
from app.quotas import QuotaExceeded, consume
from app.scheduling import enqueue_run, next_due
from app.schemas import ApproveRequest


@pytest.fixture
def context(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def db_override():
        with sessions() as db:
            yield db

    main.app.dependency_overrides[get_db] = db_override
    main.app.dependency_overrides[get_principal] = lambda: Principal("creator", "org_test", False)
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    monkeypatch.setattr(worker, "ensure_search_ready", lambda: None)
    monkeypatch.setattr(worker, "ensure_model_ready", lambda: None)
    dispatched = []
    monkeypatch.setattr(main, "dispatch", lambda run_id, background: dispatched.append(run_id))
    monkeypatch.setattr(
        main,
        "plan_prompt",
        lambda prompt: ApproveRequest(
            title="Hiring leads",
            queries=["design jobs berlin"],
            fields=[
                {
                    "name": "company",
                    "label": "Company",
                    "type": "text",
                    "description": "",
                },
                {"name": "role", "label": "Role", "type": "text", "description": ""},
            ],
            identity_fields=["company", "role"],
        ),
    )
    monkeypatch.setattr(main, "ensure_model_ready", lambda: None)
    yield TestClient(main.app), sessions, dispatched
    main.app.dependency_overrides.clear()
    engine.dispose()


def make_approved(client):
    draft = client.post("/api/drafts", json={"prompt": "Find public design jobs in Berlin"})
    assert draft.status_code == 201, draft.text
    data = draft.json()
    approved = client.post(
        f"/api/workflows/{data['id']}/approve",
        json={key: data[key] for key in ["title", "queries", "fields", "identity_fields"]},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["run"] is None
    started = client.post(f"/api/workflows/{data['id']}/runs")
    assert started.status_code == 201, started.text
    return data["id"], started.json()["id"]


def test_approval_waits_for_manual_first_run(context):
    client, _, dispatched = context
    draft = client.post("/api/drafts", json={"prompt": "Find public design jobs in Berlin"}).json()
    approved = client.post(
        f"/api/workflows/{draft['id']}/approve",
        json={key: draft[key] for key in ["title", "queries", "fields", "identity_fields"]},
    )
    assert approved.status_code == 200
    assert approved.json()["run"] is None
    assert client.get(f"/api/workflows/{draft['id']}/runs").json() == []
    assert dispatched == []

    first = client.post(f"/api/workflows/{draft['id']}/runs")
    assert first.status_code == 201
    assert first.json()["trigger"] == "manual"
    assert dispatched == [first.json()["id"]]
    assert client.post(f"/api/workflows/{draft['id']}/runs").status_code == 409


def test_prompt_approval_collection_dedup_evidence_export(context, monkeypatch):
    client, sessions, dispatched = context
    workflow_id, run_id = make_approved(client)
    assert dispatched == [run_id]
    page = "Northstar is hiring a Product Designer in Berlin."
    monkeypatch.setattr(worker, "search", lambda query: [{"url": "https://example.com/jobs"}])
    monkeypatch.setattr(worker, "scrape", lambda url: ("Northstar jobs", page))
    monkeypatch.setattr(
        worker,
        "extract",
        lambda page, fields: [
            {
                "data": {"company": "Northstar", "role": "Product Designer"},
                "evidence": "Northstar is hiring a Product Designer in Berlin.",
            }
        ],
    )
    worker.process_run(run_id)
    usage = client.get("/api/usage").json()
    assert usage["web"]["used"] == 2
    assert usage["web"]["limit"] == 600
    assert "firecrawl" not in usage
    result = client.get(f"/api/workflows/{workflow_id}/records").json()
    assert len(result) == 1
    assert result[0]["evidence"] in page
    assert result[0]["source_url"] == "https://example.com/jobs"
    assert result[0]["fetched_at"]
    source = client.get(f"/api/sources/{result[0]['source_id']}").json()
    assert source["url"] == "https://example.com/jobs"
    rerun = client.post(f"/api/workflows/{workflow_id}/runs").json()
    worker.process_run(rerun["id"])
    with sessions() as db:
        assert (
            db.scalar(select(Record.observation_count).where(Record.workflow_id == workflow_id))
            == 2
        )
        assert (
            len(db.scalars(select(Observation).where(Observation.workflow_id == workflow_id)).all())
            == 2
        )
    assert len(client.get(f"/api/workflows/{workflow_id}/records").json()) == 1
    csv_data = client.get(f"/api/workflows/{workflow_id}/export?format=csv").text
    json_data = client.get(f"/api/workflows/{workflow_id}/export?format=json").json()
    assert "source_url" in csv_data and "https://example.com/jobs" in csv_data
    assert len(json_data) == 1 and json_data[0]["evidence"] in page
    assert client.get(f"/api/workflows/{workflow_id}/records?q=missing").json() == []


def test_empty_search_advances_to_next_query(context, monkeypatch):
    client, sessions, _ = context
    workflow_id, run_id = make_approved(client)
    with sessions() as db:
        workflow = db.get(Workflow, workflow_id)
        workflow.queries = ["empty query", "useful query"]
        db.commit()
    queries = []

    def search(query):
        queries.append(query)
        return [] if query == "empty query" else [{"url": "https://example.com/jobs"}]

    monkeypatch.setattr(worker, "search", search)
    monkeypatch.setattr(worker, "scrape", lambda url: ("Jobs", "Public job listing"))
    monkeypatch.setattr(worker, "extract", lambda page, fields: [])
    worker.process_run(run_id)
    assert queries == ["empty query", "useful query"]
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "completed"


def test_direct_public_url_bypasses_search(context, monkeypatch):
    client, sessions, _ = context
    workflow_id, run_id = make_approved(client)
    with sessions() as db:
        db.get(Workflow, workflow_id).queries = ["https://example.com/unindexed"]
        db.commit()
    monkeypatch.setattr(
        worker, "search", lambda query: (_ for _ in ()).throw(AssertionError("Search called"))
    )
    monkeypatch.setattr(worker, "scrape", lambda url: ("Unindexed", "Public research page."))
    monkeypatch.setattr(worker, "extract", lambda page, fields: [])

    worker.process_run(run_id)
    result = client.get(f"/api/runs/{run_id}").json()
    assert result["status"] == "completed"
    assert result["searched"] == 0
    assert result["scraped"] == 1
    assert client.get("/api/usage").json()["web"]["used"] == 1


def test_run_can_scrape_sixteen_pages(context, monkeypatch):
    client, sessions, _ = context
    workflow_id, run_id = make_approved(client)
    with sessions() as db:
        db.get(Workflow, workflow_id).queries = ["first", "second"]
        db.commit()
    monkeypatch.setattr(
        worker,
        "search",
        lambda query: [{"url": f"https://example.com/{query}/{i}"} for i in range(8)],
    )
    monkeypatch.setattr(worker, "scrape", lambda url: ("Results", "Public research page."))
    monkeypatch.setattr(worker, "extract", lambda page, fields: [])
    worker.process_run(run_id)
    result = client.get(f"/api/runs/{run_id}").json()
    assert result["status"] == "completed"
    assert result["scraped"] == 16


def test_time_slice_saves_checkpoint_for_resume(context, monkeypatch):
    client, _, _ = context
    _, run_id = make_approved(client)
    monkeypatch.setattr(worker, "WORK_SLICE_SECONDS", 0)
    worker.process_run(run_id)
    result = client.get(f"/api/runs/{run_id}").json()
    assert result["status"] == "paused"
    assert result["next_retry_at"] is not None
    monkeypatch.setattr(worker, "WORK_SLICE_SECONDS", 480)
    monkeypatch.setattr(worker, "search", lambda query: [])
    with worker.SessionLocal() as db:
        db.get(Run, run_id).next_retry_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert run_id in worker.tick()
    worker.process_run(run_id)
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "completed"


def test_unsupported_source_does_not_pause_collection(context, monkeypatch):
    client, _, _ = context
    workflow_id, run_id = make_approved(client)
    page = "Northstar is hiring a Product Designer in Berlin."
    monkeypatch.setattr(
        worker,
        "search",
        lambda query: [
            {"url": "https://unsupported.example/jobs"},
            {"url": "https://example.com/jobs"},
        ],
    )

    def scrape(url):
        if "unsupported.example" in url:
            raise ProviderUnavailable("Blocked or unavailable page skipped")
        return "Northstar jobs", page

    monkeypatch.setattr(worker, "scrape", scrape)
    monkeypatch.setattr(
        worker,
        "extract",
        lambda page, fields: [
            {
                "data": {"company": "Northstar", "role": "Product Designer"},
                "evidence": page,
            }
        ],
    )
    worker.process_run(run_id)
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "completed"
    assert len(client.get(f"/api/workflows/{workflow_id}/records").json()) == 1


def test_creator_admin_and_org_scope(context):
    client, _, _ = context
    workflow_id, run_id = make_approved(client)
    main.app.dependency_overrides[get_principal] = lambda: Principal("member", "org_test", False)
    assert client.get(f"/api/workflows/{workflow_id}").status_code == 200
    assert client.get(f"/api/workflows/{workflow_id}/export?format=json").status_code == 200
    assert (
        client.patch(
            f"/api/workflows/{workflow_id}/schedule",
            json={
                "cadence": "daily",
                "timezone": "UTC",
                "local_hour": 9,
                "week_day": 0,
            },
        ).status_code
        == 403
    )
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 403
    main.app.dependency_overrides[get_principal] = lambda: Principal("admin", "org_test", True)
    assert (
        client.patch(
            f"/api/workflows/{workflow_id}/schedule",
            json={
                "cadence": "daily",
                "timezone": "UTC",
                "local_hour": 9,
                "week_day": 0,
            },
        ).status_code
        == 200
    )
    main.app.dependency_overrides[get_principal] = lambda: Principal("outsider", "org_other", True)
    assert client.get(f"/api/workflows/{workflow_id}").status_code == 404


def test_schedule_claim_duplicate_and_recovery(context):
    client, sessions, _ = context
    workflow_id, run_id = make_approved(client)
    with sessions() as db:
        workflow = db.get(Workflow, workflow_id)
        first_run = db.get(Run, run_id)
        duplicate = enqueue_run(db, workflow, first_run.trigger, first_run.run_key)
        assert duplicate.id == run_id
        second = enqueue_run(db, workflow, "manual", "manual:second")
        assert worker.claim(db, run_id)
        assert not worker.claim(db, second.id)
        db.get(Run, run_id).status = "completed"
        worker.release(db, db.get(Run, run_id))
        assert worker.claim(db, second.id)
        lease = db.get(worker.ExecutionLease, "org_test")
        lease.expires_at = utcnow() - timedelta(minutes=1)
        workflow.cadence = "daily"
        workflow.timezone = "Asia/Kolkata"
        workflow.local_hour = 9
        workflow.next_run_at = utcnow() - timedelta(hours=1)
        db.commit()
    queued = worker.tick()
    assert second.id in queued
    with sessions() as db:
        assert db.get(Run, second.id).status == "queued"
        db.get(Run, second.id).status = "completed"
        db.commit()
    worker.tick()
    with sessions() as db:
        assert db.get(Workflow, workflow_id).next_run_at > utcnow()
    assert next_due("weekly", "Asia/Kolkata", 9, 0) is not None
    assert next_due("none", "UTC", 9, 0) is None


def test_quota_pause_and_resume(context, monkeypatch):
    client, sessions, _ = context
    workflow_id, run_id = make_approved(client)
    monkeypatch.setattr(
        worker,
        "search",
        lambda query: (_ for _ in ()).throw(ProviderUnavailable("Free search unavailable")),
    )
    worker.process_run(run_id)
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "paused"
    assert "unavailable" in client.get(f"/api/workflows/{workflow_id}").json()["pause_reason"]
    monkeypatch.setattr(worker, "search", lambda query: [])
    with sessions() as db:
        db.get(Run, run_id).next_retry_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert run_id in worker.tick()
    worker.process_run(run_id)
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "completed"
    assert client.get(f"/api/workflows/{workflow_id}").json()["pause_reason"] is None
    with sessions() as db:
        for _ in range(20):
            consume(db, "org_other", "model")
        with pytest.raises(QuotaExceeded):
            consume(db, "org_other", "model")


@pytest.mark.parametrize(
    "reason",
    [
        "OpenRouter rate limit reached: Free tier limit reached",
        "No eligible free structured-output model: Client error '429 Too Many Requests' "
        "for url 'https://openrouter.ai/api/v1/chat/completions'",
    ],
)
def test_openrouter_rate_limit_starts_with_one_minute_delay(context, reason):
    client, sessions, _ = context
    _, run_id = make_approved(client)
    with sessions() as db:
        run = db.get(Run, run_id)
        run.status = "paused"
        run.pause_reason = reason
        db.commit()

    assert run_id not in worker.tick()
    with sessions() as db:
        run = db.get(Run, run_id)
        assert run.status == "paused"
        assert run.retry_attempt == 1
        assert timedelta(seconds=50) < run.next_retry_at - utcnow() < timedelta(seconds=70)
        run.next_retry_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert run_id in worker.tick()


def test_rate_limit_phases_resume_saved_page_and_notify_recovery(context, monkeypatch):
    client, sessions, _ = context
    _, run_id = make_approved(client)
    calls = {"search": 0, "scrape": 0, "extract": 0}

    def search_once(query):
        calls["search"] += 1
        return [{"url": "https://example.com/jobs"}]

    def scrape_once(url):
        calls["scrape"] += 1
        return "Jobs", "Northstar is hiring in Berlin."

    def rate_limited(page, fields):
        calls["extract"] += 1
        if calls["extract"] <= len(worker.RATE_LIMIT_DELAYS):
            raise ProviderUnavailable("OpenRouter rate limit reached: 429")
        return []

    monkeypatch.setattr(worker, "search", search_once)
    monkeypatch.setattr(worker, "scrape", scrape_once)
    monkeypatch.setattr(worker, "extract", rate_limited)

    for attempt, delay in enumerate(worker.RATE_LIMIT_DELAYS, 1):
        if attempt > 1:
            with sessions() as db:
                db.get(Run, run_id).next_retry_at = utcnow() - timedelta(seconds=1)
                db.commit()
            assert run_id in worker.tick()
        worker.process_run(run_id)
        with sessions() as db:
            run = db.get(Run, run_id)
            assert run.status == "paused"
            assert run.retry_attempt == attempt
            assert timedelta(minutes=delay) - timedelta(seconds=10) < run.next_retry_at - utcnow()
            assert run.next_retry_at - utcnow() < timedelta(minutes=delay) + timedelta(seconds=10)

    with sessions() as db:
        db.get(Run, run_id).next_retry_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert run_id in worker.tick()
    worker.process_run(run_id)
    result = client.get(f"/api/runs/{run_id}").json()
    assert result["status"] == "completed"
    assert result["recovery_count"] == 1
    assert result["retry_attempt"] == 0
    assert calls == {"search": 1, "scrape": 1, "extract": 9}


def test_search_attempt_limit_survives_retries(context, monkeypatch):
    client, sessions, _ = context
    workflow_id, run_id = make_approved(client)
    calls = []

    def unavailable(query):
        calls.append(query)
        raise ProviderUnavailable("Free search unavailable")

    monkeypatch.setattr(worker, "search", unavailable)
    for attempt in range(3):
        if attempt:
            with sessions() as db:
                db.get(Run, run_id).next_retry_at = utcnow() - timedelta(seconds=1)
                db.commit()
            assert run_id in worker.tick()
        worker.process_run(run_id)
        assert client.get(f"/api/runs/{run_id}").json()["searched"] == attempt + 1

    with sessions() as db:
        db.get(Run, run_id).next_retry_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert run_id in worker.tick()
    worker.process_run(run_id)
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "paused"
    assert "three searches" in run["pause_reason"]
    assert "three searches" in client.get(f"/api/workflows/{workflow_id}").json()["pause_reason"]
    assert run["searched"] == len(calls) == 3
    assert run_id not in worker.tick()
