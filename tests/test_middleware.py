# Copyright 2026 MSPbots.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Credential middleware: 401 on missing headers, regions, aliases, isolation."""

import asyncio

import pytest
from starlette.testclient import TestClient

from avanan_legacy_mcp.__main__ import build_http_app
from avanan_legacy_mcp.server import (
    GatewayCredentialsMiddleware,
    _credentials_var,
    create_mcp_server,
    get_client_from_context,
)

MCP_HEADERS = {"Accept": "application/json, text/event-stream"}
CREDS = {"X-Avanan-App-Id": "your-app-id", "X-Avanan-Secret": "your-app-secret"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}


def _client() -> TestClient:
    return TestClient(build_http_app(create_mcp_server()))


def test_health_is_local():
    with _client() as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.parametrize("drop", list(CREDS))
def test_missing_header_returns_401(drop):
    headers = MCP_HEADERS | {k: v for k, v in CREDS.items() if k != drop}
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["required_headers"] == list(CREDS)


def test_unknown_region_returns_400():
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | CREDS | {"X-Avanan-Region": "mars"})
    assert resp.status_code == 400
    assert "euw2" in resp.json()["allowed_values"]


def test_tools_list_over_http():
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | CREDS)
    assert resp.status_code == 200
    assert "avanan_query_events" in resp.text


def _run_middleware(headers: list[tuple[bytes, bytes]]) -> dict:
    seen: dict = {}

    async def app(scope, receive, send):
        seen["credentials"] = _credentials_var.get()
        seen["client"] = get_client_from_context()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    asyncio.run(GatewayCredentialsMiddleware(app)({"type": "http", "path": "/mcp", "headers": headers}, receive, send))
    return seen


BASE = [(b"x-avanan-app-id", b"app"), (b"x-avanan-secret", b"sec")]


@pytest.mark.parametrize(
    "value,host",
    [
        (None, "smart-api-production-1-us.avanan.net"),
        (b"US", "smart-api-production-1-us.avanan.net"),
        (b"eu", "smart-api-production-1-eu.avanan.net"),
        (b"uk", "smart-api-production-1-euw2.avanan.net"),
        (b"au", "smart-api-production-5-ap.avanan.net"),
        (b"in", "smart-api-production-1-aps1.avanan.net"),
        (b"ca", "smart-api-production-1-ca.avanan.net"),
    ],
)
def test_region_selects_host(value, host):
    headers = BASE + ([(b"x-avanan-region", value)] if value is not None else [])
    seen = _run_middleware(headers)
    assert seen["client"].host == host
    assert _credentials_var.get() is None


def test_optional_token_and_alias_headers():
    seen = _run_middleware(
        [(b"x-avanan-client-id", b"old-app"), (b"x-avanan-client-secret", b"old-sec"), (b"x-avanan-token", b"jwt")]
    )
    creds = seen["credentials"]
    assert (creds.app_id, creds.secret, creds.token) == ("old-app", "old-sec", "jwt")


def test_concurrent_requests_do_not_share_credentials():
    observed: list[tuple[str, str]] = []

    async def app(scope, receive, send):
        before = _credentials_var.get().app_id
        await asyncio.sleep(0.01)
        observed.append((before, _credentials_var.get().app_id))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    middleware = GatewayCredentialsMiddleware(app)

    def scope(app_id: bytes) -> dict:
        return {"type": "http", "path": "/mcp", "headers": [(b"x-avanan-app-id", app_id), (b"x-avanan-secret", b"s")]}

    async def both():
        await asyncio.gather(middleware(scope(b"tenant-a"), receive, send), middleware(scope(b"tenant-b"), receive, send))

    asyncio.run(both())
    assert sorted(observed) == [("tenant-a", "tenant-a"), ("tenant-b", "tenant-b")]


def test_credentials_repr_hides_secrets():
    seen = _run_middleware([(b"x-avanan-app-id", b"secret-app"), (b"x-avanan-secret", b"secret-value")])
    text = repr(seen["credentials"])
    assert "secret-app" not in text and "secret-value" not in text
