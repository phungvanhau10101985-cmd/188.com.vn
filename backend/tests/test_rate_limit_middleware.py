from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.middleware.rate_limit import (
    _client_ip_from_scope,
    _is_internal_exempt,
    _peer_trusted,
    RateLimitMiddleware,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_scope(
    path: str = "/api/v1/test",
    method: str = "GET",
    headers: dict[str, str] | None = None,
    client_host: str = "127.0.0.1",
) -> dict:
    raw_headers: list[tuple[bytes, bytes]] = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("utf-8")))
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": raw_headers,
        "client": (client_host, 12345),
    }


def test_client_ip_trusted_peer_reads_cf_connecting_ip():
    scope = _make_scope(headers={"cf-connecting-ip": "203.0.113.10"})
    assert _client_ip_from_scope(scope) == "203.0.113.10"


def test_client_ip_trusted_peer_reads_x_forwarded_for():
    scope = _make_scope(headers={"x-forwarded-for": "198.51.100.2, 10.0.0.1"})
    assert _client_ip_from_scope(scope) == "198.51.100.2"


def test_client_ip_untrusted_peer_ignores_xff():
    scope = _make_scope(
        headers={"x-forwarded-for": "198.51.100.99"},
        client_host="8.8.8.8",
    )
    assert _client_ip_from_scope(scope) == "8.8.8.8"


def test_internal_exempt_loopback():
    assert _is_internal_exempt("127.0.0.1")
    assert not _is_internal_exempt("203.0.113.1")


def test_peer_trusted_loopback_and_private():
    assert _peer_trusted("127.0.0.1")
    assert _peer_trusted("10.0.0.5")
    assert not _peer_trusted("8.8.8.8")


@pytest.fixture
def rate_limit_app():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/v1/test")
    def test_endpoint():
        return {"ok": True}

    @app.options("/api/v1/test")
    def test_options():
        return {"ok": True}

    @app.get("/health")
    def health_endpoint():
        return {"status": "ok"}

    @app.get("/static/test.png")
    def static_endpoint():
        return {"static": True}

    return app


@pytest.mark.anyio
async def test_rate_limit_middleware(rate_limit_app):
    transport = ASGITransport(app=rate_limit_app)
    with patch.object(settings, "RATE_LIMIT_ENABLED", True), patch.object(
        settings, "RATE_LIMIT_REQUESTS_PER_MINUTE", 5
    ):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            for _ in range(5):
                res = await client.get("/api/v1/test", headers={"cf-connecting-ip": "1.2.3.4"})
                assert res.status_code == 200
                assert res.json() == {"ok": True}

            res = await client.get("/api/v1/test", headers={"cf-connecting-ip": "1.2.3.4"})
            assert res.status_code == 429
            assert "Bạn đang thao tác quá nhanh" in res.json()["detail"]

            res = await client.get("/api/v1/test", headers={"cf-connecting-ip": "1.2.3.5"})
            assert res.status_code == 200

            for _ in range(10):
                res = await client.get("/health", headers={"cf-connecting-ip": "1.2.3.4"})
                assert res.status_code == 200

            for _ in range(10):
                res = await client.get("/static/test.png", headers={"cf-connecting-ip": "1.2.3.4"})
                assert res.status_code == 200

            for _ in range(10):
                res = await client.options("/api/v1/test", headers={"cf-connecting-ip": "1.2.3.4"})
                assert res.status_code == 200

            for _ in range(10):
                res = await client.get("/api/v1/test", headers={"cf-connecting-ip": "127.0.0.1"})
                assert res.status_code == 200

            for _ in range(5):
                res = await client.get(
                    "/api/v1/test",
                    headers={"x-forwarded-for": "5.6.7.8, 127.0.0.1"},
                )
                assert res.status_code == 200

            res = await client.get(
                "/api/v1/test",
                headers={"x-forwarded-for": "5.6.7.8, 127.0.0.1"},
            )
            assert res.status_code == 429


@pytest.mark.anyio
async def test_rate_limit_disabled(rate_limit_app):
    transport = ASGITransport(app=rate_limit_app)
    with patch.object(settings, "RATE_LIMIT_ENABLED", False), patch.object(
        settings, "RATE_LIMIT_REQUESTS_PER_MINUTE", 1
    ):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            for _ in range(5):
                res = await client.get("/api/v1/test", headers={"cf-connecting-ip": "9.9.9.9"})
                assert res.status_code == 200
