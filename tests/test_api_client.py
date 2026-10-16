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
"""Request signing, token flow and tool routing against a mocked SmartAPI."""

import json

import httpx
import pytest

from avanan_legacy_mcp import api_client
from avanan_legacy_mcp.api_client import AvananClient, AvananCredentials, sign
from avanan_legacy_mcp.server import _credentials_var, create_mcp_server

HOST = "smart-api-production-1-us.avanan.net"


def envelope(data, total=None, scroll=None):
    env = {"requestId": "r", "responseCode": 0, "responseText": "Success", "recordsNumber": len(data) if isinstance(data, list) else 1}
    if total is not None:
        env["totalRecordsNumber"] = total
    if scroll is not None:
        env["scrollId"] = scroll
    return {"responseEnvelope": env, "responseData": data}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(api_client.asyncio, "sleep", instant)


def test_signature_matches_vendor_reference_example():
    # Worked example from the vendor's API reference guide (token request).
    assert (
        sign("d290f1ee-6c54-4b01-90e6", "US:myapp29", "2021-04-10T00:00:00.000Z", "my_avanan_secret")
        == "2462b23346ab0642b65d7d094aca5fb4c29fd96d0468deceae2704d258e81497"
    )


class FakeApi:
    def __init__(self, reply=None, auth_status=200):
        self.requests: list[httpx.Request] = []
        self.reply = reply or (lambda r: httpx.Response(200, json=envelope([])))
        self.auth_status = auth_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/v1.0/auth":
            if self.auth_status != 200:
                return httpx.Response(self.auth_status, text="")
            return httpx.Response(200, text="jwt-token-123")
        return self.reply(request)

    def api(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path != "/v1.0/auth"]


async def _call(monkeypatch, fake: FakeApi, tool: str, args: dict, token: str | None = None):
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake))
    monkeypatch.setattr(api_client, "_get_shared_http_client", lambda: http)
    mcp = create_mcp_server()
    ctx = _credentials_var.set(AvananCredentials("app-1", "secret-1", "us", token))
    try:
        content, _ = await mcp.call_tool(tool, args)
    finally:
        _credentials_var.reset(ctx)
    return json.loads(content[0].text)


def _expected_sig(req: httpx.Request, request_string: str) -> str:
    h = req.headers
    return sign(h["x-av-req-id"], h["x-av-app-id"], h["x-av-date"], "secret-1", request_string)


async def test_auth_then_signed_data_request(monkeypatch):
    fake = FakeApi(lambda r: httpx.Response(200, json=envelope([{"id": 1, "name": "Example"}], total=1)))
    result = await _call(monkeypatch, fake, "avanan_list_tenants", {"MSPId": 7})
    auth, req = fake.requests
    assert auth.headers["x-av-token"] == ""
    assert auth.headers["x-av-sig"] == _expected_sig(auth, "")
    assert not auth.headers["x-av-date"].endswith("Z")
    assert (req.method, str(req.url)) == ("GET", f"https://{HOST}/v1.0/msp/tenants")
    assert req.headers["x-av-token"] == "jwt-token-123"
    assert req.headers["x-av-sig"] == _expected_sig(req, "/v1.0/msp/tenants")
    assert json.loads(req.content) == {"requestData": {"MSPId": 7}}
    assert "secret-1" not in str(req.headers)
    assert result["items"] == [{"id": 1, "name": "Example"}] and result["has_more"] is False


async def test_query_string_is_signed_exactly_as_sent(monkeypatch):
    fake = FakeApi()
    await _call(monkeypatch, fake, "avanan_get_monthly_usage", {"year": 2026, "month": 9, "msp_ids": [3, 4]})
    req = fake.api()[0]
    assert req.url.raw_path.decode() == "/v1.0/msp/usage?year=2026&month=9&msp_ids=3&msp_ids=4"
    assert req.headers["x-av-sig"] == _expected_sig(req, "/v1.0/msp/usage?year=2026&month=9&msp_ids=3&msp_ids=4")


async def test_pre_issued_token_skips_auth(monkeypatch):
    fake = FakeApi()
    await _call(monkeypatch, fake, "avanan_list_scopes", {}, token="given-jwt")
    assert [r.url.path for r in fake.requests] == ["/v1.0/scopes"]
    assert fake.requests[0].headers["x-av-token"] == "given-jwt"


async def test_bad_credentials_map_to_unauthorized(monkeypatch):
    result = await _call(monkeypatch, FakeApi(auth_status=401), "avanan_test_connection", {})
    assert result["error"]["code"] == "unauthorized"
    assert "secret-1" not in json.dumps(result)


async def test_non_zero_response_code_is_an_error(monkeypatch):
    bad = {"responseEnvelope": {"responseCode": 3, "responseText": "Invalid tenant"}, "responseData": []}
    result = await _call(monkeypatch, FakeApi(lambda r: httpx.Response(200, json=bad)), "avanan_get_tenant", {"tenant_id": 9})
    assert result["error"]["code"] == "invalid_argument"
    assert "Invalid tenant" in result["error"]["message"]


async def test_retry_regenerates_signature(monkeypatch):
    calls = []

    def reply(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=envelope([]))

    await _call(monkeypatch, FakeApi(reply), "avanan_list_addons", {})
    assert len(calls) == 2
    assert calls[0].headers["x-av-req-id"] != calls[1].headers["x-av-req-id"]
    assert calls[1].headers["x-av-sig"] == _expected_sig(calls[1], "/v1.0/msp/addons")


async def test_scroll_pagination(monkeypatch):
    page = envelope([{"eventId": "e1"}], total=5, scroll="scroll-2")
    result = await _call(monkeypatch, FakeApi(lambda r: httpx.Response(200, json=page)), "avanan_query_events", {
        "eventTypes": ["phishing"], "startDate": "2026-10-01T00:00:00.000Z", "scrollId": "scroll-1",
    })
    assert result["has_more"] is True and result["scroll_id"] == "scroll-2" and result["total"] == 5


async def test_event_query_body(monkeypatch):
    fake = FakeApi()
    await _call(monkeypatch, fake, "avanan_query_events", {"severities": ["high"], "scopes": ["farm1:acme"]})
    req = fake.api()[0]
    assert (req.method, req.url.path) == ("POST", "/v1.0/event/query")
    assert json.loads(req.content) == {"requestData": {"scopes": ["farm1:acme"], "severities": ["high"]}}


async def test_search_body(monkeypatch):
    fake = FakeApi()
    await _call(monkeypatch, fake, "avanan_search_emails", {
        "saas": "office365_emails", "startDate": "2026-10-01T00:00:00.000Z",
        "filters": [{"saasAttrName": "entityPayload.subject", "saasAttrOp": "contains", "saasAttrValue": "invoice"}],
    })
    body = json.loads(fake.api()[0].content)["requestData"]
    assert body["entityFilter"] == {"saas": "office365_emails", "startDate": "2026-10-01T00:00:00.000Z"}
    assert body["entityExtendedFilter"] == [
        {"saasAttrName": "entityPayload.subject", "saasAttrOp": "contains", "saasAttrValue": "invoice"}
    ]


@pytest.mark.parametrize(
    "tool,args,path,expected",
    [
        ("avanan_quarantine_events", {"eventIds": ["e1"], "scope": "f:t"}, "/v1.0/action/event",
         {"scope": "f:t", "eventIds": ["e1"], "eventActionName": "quarantine"}),
        ("avanan_restore_emails", {"entityIds": ["x1", "x2"]}, "/v1.0/action/entity",
         {"entityIds": ["x1", "x2"], "entityType": "email", "entityActionName": "restore"}),
        ("avanan_assign_license", {"tenant_id": 120, "licenseCodeName": "pkg", "addonIdList": [1], "maxLicensedUsers": 50},
         "/v1.0/msp/tenants/120/license", {"licenseCodeName": "pkg", "addonIdList": [1], "maxLicensedUsers": 50}),
        ("avanan_create_msp_partner", {"name": "Child", "website": "https://example.com", "country": "US", "zip": "10001"},
         "/v1.0/msp/msp-partners-extended", {"name": "Child", "website": "https://example.com", "country": "US", "zip": "10001"}),
        ("avanan_add_exception", {"excType": "whitelist", "senderDomain": "example.com", "senderDomainMatching": "endswith"},
         "/v1.0/exceptions/whitelist", {"senderDomain": "example.com", "senderDomainMatching": "endswith"}),
    ],
)
async def test_write_bodies(monkeypatch, tool, args, path, expected):
    fake = FakeApi()
    await _call(monkeypatch, fake, tool, args)
    req = fake.api()[0]
    assert (req.method, req.url.path) == ("POST", path)
    assert json.loads(req.content) == {"requestData": expected}


@pytest.mark.parametrize(
    "tool,args,method,path",
    [
        ("avanan_get_tenant", {"tenant_id": 120}, "GET", "/v1.0/msp/tenants/120"),
        ("avanan_delete_tenant", {"tenant_id": 120}, "DELETE", "/v1.0/msp/tenants/120"),
        ("avanan_delete_msp_partner", {"msp_id": 5}, "DELETE", "/v1.0/msp/msp-partners/5"),
        ("avanan_get_msp_user", {"user_id": 3}, "GET", "/v1.0/msp/users/3"),
        ("avanan_delete_msp_user", {"user_id": 3}, "DELETE", "/v1.0/msp/users/3"),
        ("avanan_get_event", {"eventId": "abc"}, "GET", "/v1.0/event/abc"),
        ("avanan_get_email", {"entityId": "ent"}, "GET", "/v1.0/search/entity/ent"),
        ("avanan_list_exceptions", {"excType": "blacklist"}, "GET", "/v1.0/exceptions/blacklist"),
        ("avanan_get_exception", {"excType": "whitelist", "excId": "12"}, "GET", "/v1.0/exceptions/whitelist/12"),
        ("avanan_delete_exception", {"excType": "whitelist", "excId": "12"}, "POST", "/v1.0/exceptions/whitelist/delete/12"),
        ("avanan_get_task_status", {"taskId": "t9"}, "GET", "/v1.0/task/t9"),
        ("avanan_list_msp_partners", {}, "GET", "/v1.0/msp/msp-partners"),
        ("avanan_get_daily_usage", {"year": 2026, "month": 9, "day": 1}, "GET", "/v1.0/msp/usage/day"),
    ],
)
async def test_routing(monkeypatch, tool, args, method, path):
    fake = FakeApi()
    result = await _call(monkeypatch, fake, tool, args)
    req = fake.api()[0]
    assert (req.method, req.url.path) == (method, path)
    assert "error" not in result


async def test_update_user_uses_put_with_full_body(monkeypatch):
    fake = FakeApi()
    args = {
        "user_id": 3, "firstName": "Ada", "lastName": "Example", "email": "ada@example.com", "role": "read-only",
        "directLogin": True, "samlLogin": False, "viewPrivateData": False, "sendAlerts": True, "receiveWeeklyReports": False,
    }
    await _call(monkeypatch, fake, "avanan_update_msp_user", args)
    req = fake.api()[0]
    assert (req.method, req.url.path) == ("PUT", "/v1.0/msp/users/3")
    assert json.loads(req.content)["requestData"]["role"] == "read-only"


async def test_add_exception_without_fields_is_rejected(monkeypatch):
    fake = FakeApi()
    result = await _call(monkeypatch, fake, "avanan_add_exception", {"excType": "whitelist"})
    assert result["error"]["code"] == "invalid_argument"
    assert fake.api() == []


def test_client_never_holds_token_across_instances():
    a = AvananClient(AvananCredentials("a", "s"))
    b = AvananClient(AvananCredentials("a", "s"))
    a._token = "only-a"
    assert b._token is None
