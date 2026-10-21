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
"""FastMCP factory and the per-request credential middleware."""

import contextvars
import uuid
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .api_client import AvananClient, AvananCredentials
from .config import DEFAULT_REGION, REGION_HOSTS, Settings, resolve_region

HEADER_APP_ID = "X-Avanan-App-Id"
HEADER_SECRET = "X-Avanan-Secret"
HEADER_REGION = "X-Avanan-Region"
HEADER_TOKEN = "X-Avanan-Token"
REQUIRED_HEADERS = [HEADER_APP_ID, HEADER_SECRET]
OPTIONAL_HEADERS = [HEADER_REGION, HEADER_TOKEN]
# Older spellings, still accepted.
_ALIASES = {HEADER_APP_ID: "X-Avanan-Client-Id", HEADER_SECRET: "X-Avanan-Client-Secret"}

# Per-request isolation: the middleware sets these for the duration of one
# HTTP request and resets them in `finally`. Nothing credential-related is
# ever stored at module level.
_credentials_var: contextvars.ContextVar[AvananCredentials | None] = contextvars.ContextVar(
    "avanan_credentials", default=None
)
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("avanan_request_id", default="-")

INSTRUCTIONS = (
    "Avanan (Check Point Harmony Email & Collaboration, legacy SmartAPI) protects "
    "Microsoft 365 / Google Workspace mail and collaboration apps. This server "
    "covers two areas:\n"
    "1. MSP portfolio (MSP API key): customer tenants, licenses and add-ons, "
    "monthly/daily usage for billing, child MSP partners and MSP portal users.\n"
    "2. Security operations: security events (phishing, malware, DLP...), "
    "secured entities such as emails, allow/block exceptions, and quarantine / "
    "restore actions that run as tasks.\n"
    "Typical flows:\n"
    "- Billing: avanan_list_tenants -> avanan_get_monthly_usage(year, month).\n"
    "- Onboarding: avanan_create_tenant -> avanan_list_licenses -> "
    "avanan_assign_license.\n"
    "- Incident: avanan_query_events(startDate, eventTypes) -> avanan_get_event; "
    "avanan_search_emails -> avanan_get_email; remediate with "
    "avanan_quarantine_emails, then avanan_get_task_status(taskId).\n"
    "With an MSP key, event/search queries span all customer scopes; actions "
    "need one `scope` (farm:tenant) from avanan_list_scopes. Lists return "
    "{items, total, has_more, scroll_id}; pass scroll_id as scrollId. Create, "
    "update, delete, quarantine and restore tools change customer data: use "
    "them only when the user explicitly asks."
)


def get_client_from_context() -> AvananClient | None:
    """The client for the current request, or None outside a request."""
    credentials = _credentials_var.get()
    if credentials is None:
        return None
    return AvananClient(credentials)


def _header(request: Request, name: str) -> str:
    value = request.headers.get(name) or request.headers.get(_ALIASES.get(name, "")) or ""
    return value.strip()


class GatewayCredentialsMiddleware:
    """Reads X-Avanan-* headers on /mcp requests into the request context.

    Missing required headers -> 401 listing them. An unknown region does not block
    the request (tools/list must work with any values); tools report it instead.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        app_id = _header(request, HEADER_APP_ID)
        secret = _header(request, HEADER_SECRET)
        token = _header(request, HEADER_TOKEN) or None
        region = resolve_region(request.headers.get(HEADER_REGION))

        missing = [h for h, v in ((HEADER_APP_ID, app_id), (HEADER_SECRET, secret)) if not v]
        if missing:
            await JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": "Required header(s) missing: " + ", ".join(missing),
                    "required_headers": REQUIRED_HEADERS,
                    "optional_headers": OPTIONAL_HEADERS,
                },
                status_code=401,
            )(scope, receive, send)
            return

        header_error = None
        if region is None:
            header_error = f"{HEADER_REGION} must be one of: {', '.join(REGION_HOSTS)}"
            region = DEFAULT_REGION

        request_id = (request.headers.get("x-request-id") or "").strip()[:64] or uuid.uuid4().hex[:12]
        creds_token = _credentials_var.set(AvananCredentials(app_id, secret, region, token, header_error))
        rid_token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _credentials_var.reset(creds_token)
            request_id_var.reset(rid_token)


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    """Build the FastMCP server and register every tool."""
    mcp = FastMCP(
        name="avanan-legacy-mcp",
        instructions=INSTRUCTIONS,
        # The service sits behind the gateway, so Host is never localhost;
        # DNS-rebinding protection would reject those requests with 421.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
    )

    client_factory: Callable[[], AvananClient | None] = get_client_from_context

    from .tools import actions, diagnostics, events, exceptions, licenses, partners, search, tenants, usage, users

    for module in (diagnostics, tenants, licenses, usage, partners, users, events, search, exceptions, actions):
        module.register(mcp, client_factory)

    return mcp
