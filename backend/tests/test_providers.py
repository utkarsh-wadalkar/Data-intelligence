from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import providers
from app.db import Base
from app.models import QuotaUsage
from app.quotas import QuotaExceeded, consume, period_for


def test_free_provider_routing_and_basic_firecrawl(monkeypatch):
    monkeypatch.setattr(
        providers,
        "settings",
        lambda: SimpleNamespace(
            model_provider="openrouter",
            openrouter_api_key="test",
            firecrawl_api_key="test",
            allow_paid_providers=False,
        ),
    )
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        if url.endswith("chat/completions"):
            data = {"choices": [{"message": {"content": '{"answer":"ok"}'}}]}
        elif url.endswith("search"):
            data = {"data": {"web": [{"url": "https://example.com"}]}}
        else:
            data = {
                "data": {
                    "markdown": "A public page with enough text.",
                    "metadata": {"title": "Example"},
                }
            }
        return httpx.Response(200, json=data, request=httpx.Request("POST", url))

    monkeypatch.setattr(providers.httpx, "post", post)
    assert providers.model_json("system", "user", {"type": "object"}) == {"answer": "ok"}
    assert calls[0][1]["models"] == ["openrouter/free", "qwen/qwen3.8-27b:free"]
    assert calls[0][1]["provider"]["data_collection"] == "deny"
    assert calls[0][1]["provider"]["require_parameters"] is True
    assert calls[0][1]["provider"]["allow_fallbacks"] is True
    assert "response_format" not in calls[0][1]
    assert '"type": "object"' in calls[0][1]["messages"][0]["content"]
    assert providers.search("example")[0]["url"] == "https://example.com"
    assert providers.scrape("https://example.com") == (
        "Example",
        "A public page with enough text.",
    )
    assert calls[2][1]["proxy"] == "basic"
    assert not providers.public_url("http://127.0.0.1/secrets")


def test_blocked_page_is_skipped(monkeypatch):
    monkeypatch.setattr(providers, "settings", lambda: SimpleNamespace(firecrawl_api_key="test"))

    def blocked(url, **kwargs):
        return httpx.Response(404, text="not found", request=httpx.Request("POST", url))

    monkeypatch.setattr(providers.httpx, "post", blocked)
    with pytest.raises(providers.ProviderUnavailable, match="skipped"):
        providers.scrape("https://example.com/unavailable")


def test_openrouter_rate_limit_is_reported_as_rate_limit(monkeypatch):
    monkeypatch.setattr(
        providers,
        "settings",
        lambda: SimpleNamespace(model_provider="openrouter", openrouter_api_key="test"),
    )

    def limited(url, **kwargs):
        return httpx.Response(
            429,
            json={"error": {"message": "Free tier limit reached"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(providers.httpx, "post", limited)
    with pytest.raises(providers.ProviderUnavailable, match="OpenRouter rate limit reached"):
        providers.model_json("system", "user", {"type": "object"})


def test_openrouter_accepts_fenced_json_from_free_model(monkeypatch):
    monkeypatch.setattr(
        providers,
        "settings",
        lambda: SimpleNamespace(model_provider="openrouter", openrouter_api_key="test"),
    )

    def post(url, **kwargs):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '```json\n{"answer":"ok"}\n```'}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(providers.httpx, "post", post)
    assert providers.model_json("system", "user", {"type": "object"}) == {"answer": "ok"}


def test_firecrawl_forbidden_exposes_provider_reason(monkeypatch):
    monkeypatch.setattr(providers, "settings", lambda: SimpleNamespace(firecrawl_api_key="test"))

    def forbidden(url, **kwargs):
        return httpx.Response(
            403,
            json={"error": "Scrape is unavailable for this API key"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(providers.httpx, "post", forbidden)
    with pytest.raises(
        providers.ProviderUnavailable, match="Scrape is unavailable for this API key"
    ):
        providers.scrape("https://example.com/jobs")


def test_firecrawl_forbidden_without_reason_points_to_key_access(monkeypatch):
    monkeypatch.setattr(providers, "settings", lambda: SimpleNamespace(firecrawl_api_key="test"))

    def forbidden(url, **kwargs):
        return httpx.Response(403, request=httpx.Request("POST", url))

    monkeypatch.setattr(providers.httpx, "post", forbidden)
    with pytest.raises(providers.ProviderUnavailable, match="API key permissions"):
        providers.scrape("https://example.com/jobs")


def test_firecrawl_unsupported_site_is_skipped(monkeypatch):
    monkeypatch.setattr(providers, "settings", lambda: SimpleNamespace(firecrawl_api_key="test"))

    def unsupported(url, **kwargs):
        return httpx.Response(
            403,
            json={"error": "We apologize, but we do not support this site."},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(providers.httpx, "post", unsupported)
    with pytest.raises(providers.ProviderUnavailable, match="skipped"):
        providers.scrape("https://example.com/jobs")


def test_firecrawl_target_forbidden_page_is_skipped(monkeypatch):
    monkeypatch.setattr(providers, "settings", lambda: SimpleNamespace(firecrawl_api_key="test"))

    def forbidden_page(url, **kwargs):
        return httpx.Response(
            200,
            json={"data": {"markdown": "Access denied", "metadata": {"statusCode": 403}}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(providers.httpx, "post", forbidden_page)
    with pytest.raises(providers.ProviderUnavailable, match="skipped"):
        providers.scrape("https://example.com/jobs")


def test_invalid_free_model_draft_is_visible_provider_error(monkeypatch):
    monkeypatch.setattr(
        providers,
        "model_json",
        lambda *args: {
            "title": "Example data",
            "queries": ["example.com"],
            "fields": [
                {"name": "title", "label": "Title", "type": "string", "description": ""}
            ],
            "identity_fields": ["title"],
        },
    )
    with pytest.raises(providers.ProviderUnavailable, match="invalid collection draft"):
        providers.plan_prompt("Collect the public Example Domain page")
    field_type = providers.DRAFT_SCHEMA["properties"]["fields"]["items"]["properties"]["type"]
    assert field_type["enum"] == [
        "text",
        "number",
        "date",
        "url",
        "boolean",
    ]


def test_draft_repairs_unknown_identity_field_for_approval(monkeypatch):
    monkeypatch.setattr(
        providers,
        "model_json",
        lambda *args: {
            "title": "Example data",
            "queries": ["example.com"],
            "fields": [
                {"name": "page_title", "label": "Title", "type": "text", "description": ""}
            ],
            "identity_fields": ["title"],
        },
    )
    assert providers.plan_prompt("Collect the public Example Domain page").identity_fields == [
        "page_title"
    ]


def test_monthly_credit_reservation():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(QuotaUsage(org_id="org", kind="firecrawl", period=period_for("firecrawl"), used=599))
        db.commit()
        try:
            consume(db, "org", "firecrawl", 2)
        except QuotaExceeded:
            pass
        else:
            raise AssertionError("Two-credit search should be blocked at 599/600")
