import asyncio
import socket
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import providers
from app.db import Base
from app.models import QuotaUsage
from app.quotas import QuotaExceeded, consume, period_for


def test_free_provider_routing_and_local_crawl(monkeypatch):
    monkeypatch.setattr(
        providers,
        "settings",
        lambda: SimpleNamespace(
            model_provider="openrouter",
            openrouter_api_key="test",
            allow_paid_providers=False,
        ),
    )
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        if url.endswith("chat/completions"):
            data = {"choices": [{"message": {"content": '{"answer":"ok"}'}}]}
        else:
            raise AssertionError(url)
        return httpx.Response(200, json=data, request=httpx.Request("POST", url))

    monkeypatch.setattr(providers.httpx, "post", post)
    assert providers.model_json("system", "user", {"type": "object"}) == {"answer": "ok"}
    assert calls[0][1]["models"] == ["openrouter/free", "qwen/qwen3.8-27b:free"]
    assert calls[0][1]["provider"]["data_collection"] == "deny"
    assert calls[0][1]["provider"]["require_parameters"] is True
    assert calls[0][1]["provider"]["allow_fallbacks"] is True
    assert "response_format" not in calls[0][1]
    assert '"type": "object"' in calls[0][1]["messages"][0]["content"]
    class Search:
        def __init__(self, **kwargs):
            pass

        def text(self, query, **kwargs):
            assert kwargs["max_results"] == 4
            return [{"href": "https://example.com", "title": "Example"}]

    monkeypatch.setattr(providers, "DDGS", Search)
    monkeypatch.setattr(
        providers,
        "_crawl",
        lambda url: __import__("asyncio").sleep(
            0,
            result=SimpleNamespace(
                success=True,
                status_code=200,
                markdown="A public page with enough text.",
                metadata={"title": "Example"},
            ),
        ),
    )
    assert providers.search("example") == [{"url": "https://example.com", "title": "Example"}]
    assert providers.scrape("https://example.com") == (
        "Example",
        "A public page with enough text.",
    )
    assert not providers.public_url("http://127.0.0.1/secrets")


def test_blocked_page_is_skipped(monkeypatch):
    monkeypatch.setattr(
        providers,
        "_crawl",
        lambda url: asyncio.sleep(0, result=SimpleNamespace(status_code=404)),
    )
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


def test_crawl4ai_blocked_page_is_skipped(monkeypatch):
    monkeypatch.setattr(
        providers,
        "_crawl",
        lambda url: __import__("asyncio").sleep(
            0, result=SimpleNamespace(status_code=403, success=False)
        ),
    )
    with pytest.raises(providers.ProviderUnavailable, match="skipped"):
        providers.scrape("https://example.com/jobs")


def test_public_page_with_sign_in_navigation_is_kept(monkeypatch):
    page = "Sign in\n" + ("Public research finding with source details. " * 30)
    monkeypatch.setattr(
        providers,
        "_crawl",
        lambda url: asyncio.sleep(
            0,
            result=SimpleNamespace(
                status_code=200, success=True, markdown=page, metadata={"title": "Research"}
            ),
        ),
    )
    assert providers.scrape("https://example.com/research") == ("Research", page)


def test_search_caps_results_and_reports_failure(monkeypatch):
    class Search:
        def __init__(self, **kwargs):
            pass

        def text(self, query, **kwargs):
            return [{"href": f"https://example.com/{i}"} for i in range(5)]

    monkeypatch.setattr(providers, "DDGS", Search)
    assert len(providers.search("example")) == 4

    def fail(**kwargs):
        raise RuntimeError("search offline")

    monkeypatch.setattr(providers, "DDGS", fail)
    with pytest.raises(providers.ProviderUnavailable, match="Web search unavailable"):
        providers.search("example")


def test_browser_route_blocks_private_redirect_and_subresource(monkeypatch):
    async def resolve(host, port, **kwargs):
        address = "10.0.0.5" if host == "private.example" else "93.184.215.14"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    monkeypatch.setattr(providers, "resolve_host", resolve)

    class Route:
        def __init__(self, url):
            self.request = SimpleNamespace(url=url, is_navigation_request=lambda: True)
            self.action = None

        async def abort(self):
            self.action = "abort"

        async def continue_(self):
            self.action = "continue"

    async def check():
        for url, expected in [
            ("https://public.example/page", "continue"),
            ("http://127.0.0.1/admin", "abort"),
            ("https://private.example/redirect", "abort"),
            ("file:///etc/passwd", "abort"),
        ]:
            route = Route(url)
            await providers.guard_route(route)
            assert route.action == expected

        blocked = []
        route = Route("https://private.example/redirect")
        await providers.guard_route(route, blocked)
        assert blocked == [route.request.url]

    asyncio.run(check())


def test_browser_blocks_cross_host_and_robots_disallowed_redirect(monkeypatch):
    async def allowed(url):
        return not url.endswith("/private")

    monkeypatch.setattr(providers, "robots_allowed", allowed)

    class Route:
        def __init__(self, url, navigation):
            self.request = SimpleNamespace(url=url, is_navigation_request=lambda: navigation)
            self.action = None

        async def abort(self):
            self.action = "abort"

        async def continue_(self):
            self.action = "continue"

    async def check():
        blocked = []
        for url, navigation in [
            ("https://other.example/script.js", False),
            ("https://public.example/private", True),
        ]:
            route = Route(url, navigation)
            await providers.guard_route(route, blocked, allowed_host="public.example")
            assert route.action == "abort"
        assert blocked == ["https://public.example/private"]

    asyncio.run(check())


def test_crawl_pins_approved_host_in_chromium(monkeypatch):
    configs = []

    async def resolve(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))]

    async def allowed(url):
        return True

    class Crawler:
        def __init__(self, config):
            configs.append(config)
            self.crawler_strategy = SimpleNamespace(set_hook=lambda *args: None)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def arun(self, **kwargs):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(providers, "resolve_host", resolve)
    monkeypatch.setattr(providers, "robots_allowed", allowed)
    monkeypatch.setattr(providers, "AsyncWebCrawler", Crawler)
    asyncio.run(providers._crawl("https://public.example/page"))
    assert any(
        "MAP public.example 93.184.215.14, MAP * ~NOTFOUND" in arg
        for arg in configs[0].extra_args
    )


def test_crawl_rejects_private_dns_before_starting_browser(monkeypatch):
    async def private_host(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", port))]

    monkeypatch.setattr(providers, "resolve_host", private_host)

    def browser():
        raise AssertionError("Browser must not start")

    monkeypatch.setattr(providers, "AsyncWebCrawler", browser)
    with pytest.raises(providers.ProviderUnavailable, match="Nonpublic source URL skipped"):
        asyncio.run(providers._crawl("https://private.example"))


def test_robots_rules_block_disallowed_path(monkeypatch):
    class Response:
        status = 200
        headers = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def text(self):
            return "User-agent: *\nDisallow: /private"

        def raise_for_status(self):
            pass

    class Client:
        def __init__(self, connector, **kwargs):
            self.connector = connector

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self.connector.close()

        def get(self, url, **kwargs):
            return Response()

    monkeypatch.setattr(providers.aiohttp, "ClientSession", Client)
    monkeypatch.setattr(providers, "public_request_url", lambda url: asyncio.sleep(0, result=True))
    assert not asyncio.run(providers.robots_allowed("https://example.com/private"))
    assert asyncio.run(providers.robots_allowed("https://example.com/public"))


def test_robots_redirect_to_private_address_is_not_fetched(monkeypatch):
    requested = []

    class Response:
        status = 302
        headers = {"location": "http://127.0.0.1/robots.txt"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class Client:
        def __init__(self, connector, **kwargs):
            self.connector = connector

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self.connector.close()

        def get(self, url, **kwargs):
            requested.append(url)
            return Response()

    monkeypatch.setattr(providers.aiohttp, "ClientSession", Client)
    monkeypatch.setattr(
        providers,
        "public_request_url",
        lambda url: asyncio.sleep(0, result="127.0.0.1" not in url),
    )
    with pytest.raises(providers.ProviderUnavailable, match="Nonpublic robots redirect"):
        asyncio.run(providers.robots_allowed("https://example.com/page"))
    assert requested == ["https://example.com/robots.txt"]


def test_robots_connector_rejects_dns_rebinding(monkeypatch):
    async def private_host(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port))]

    monkeypatch.setattr(providers, "resolve_host", private_host)
    with pytest.raises(OSError, match="Nonpublic"):
        asyncio.run(providers.PublicResolver().resolve("public.example", 443))


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


def test_monthly_web_request_reservation():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(QuotaUsage(org_id="org", kind="web", period=period_for("web"), used=600))
        db.commit()
        try:
            consume(db, "org", "web")
        except QuotaExceeded:
            pass
        else:
            raise AssertionError("Web request should be blocked at 600/600")
