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
"""tools/list snapshot and error-envelope mapping. No network access."""

import asyncio
import json

import pytest

from avanan_legacy_mcp.api_client import AvananError
from avanan_legacy_mcp.server import INSTRUCTIONS, create_mcp_server

USER_FIELDS = {
    "firstName", "lastName", "email", "role", "directLogin", "samlLogin",
    "viewPrivateData", "sendAlerts", "receiveWeeklyReports",
}

# Tool names are a public contract: existing agents and tenant connections
# depend on them. Changing this snapshot is a breaking change.
EXPECTED_TOOLS: dict[str, set[str]] = {
    "avanan_test_connection": set(),
    "avanan_list_scopes": set(),
    "avanan_list_tenants": set(),
    "avanan_get_tenant": {"tenant_id"},
    "avanan_create_tenant": {"adminEmail", "tenantName", "adminName", "phone", "companyName", "tenantRegion"},
    "avanan_delete_tenant": {"tenant_id"},
    "avanan_list_licenses": set(),
    "avanan_list_addons": set(),
    "avanan_assign_license": {"tenant_id", "licenseCodeName"},
    "avanan_get_monthly_usage": {"year", "month"},
    "avanan_get_daily_usage": {"year", "month", "day"},
    "avanan_list_msp_partners": set(),
    "avanan_create_msp_partner": {"name", "website", "country", "zip"},
    "avanan_delete_msp_partner": {"msp_id"},
    "avanan_list_msp_users": set(),
    "avanan_get_msp_user": {"user_id"},
    "avanan_create_msp_user": USER_FIELDS,
    "avanan_update_msp_user": USER_FIELDS | {"user_id"},
    "avanan_delete_msp_user": {"user_id"},
    "avanan_query_events": set(),
    "avanan_get_event": {"eventId"},
    "avanan_search_emails": {"saas", "startDate"},
    "avanan_get_email": {"entityId"},
    "avanan_list_exceptions": {"excType"},
    "avanan_get_exception": {"excType", "excId"},
    "avanan_add_exception": {"excType"},
    "avanan_update_exception": {"excType", "excId"},
    "avanan_delete_exception": {"excType", "excId"},
    "avanan_quarantine_events": {"eventIds"},
    "avanan_restore_events": {"eventIds"},
    "avanan_quarantine_emails": {"entityIds"},
    "avanan_restore_emails": {"entityIds"},
    "avanan_get_task_status": {"taskId"},
}

DESTRUCTIVE_TOOLS = {
    "avanan_delete_tenant",
    "avanan_delete_msp_partner",
    "avanan_delete_msp_user",
    "avanan_delete_exception",
    "avanan_quarantine_events",
    "avanan_quarantine_emails",
}
WRITE_TOOLS = DESTRUCTIVE_TOOLS | {
    "avanan_create_tenant",
    "avanan_assign_license",
    "avanan_create_msp_partner",
    "avanan_create_msp_user",
    "avanan_update_msp_user",
    "avanan_add_exception",
    "avanan_update_exception",
    "avanan_restore_events",
    "avanan_restore_emails",
}


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in asyncio.run(create_mcp_server().list_tools())}


def test_tool_names_snapshot(tools):
    assert set(tools) == set(EXPECTED_TOOLS)


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_required_params(tools, name):
    assert set(tools[name].inputSchema.get("required", [])) == EXPECTED_TOOLS[name]


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_description_budget(tools, name):
    description = (tools[name].description or "").strip()
    assert description, f"{name} has no description"
    assert len(description) <= 500
    assert len(description.splitlines()[0]) <= 100
    assert "API:" not in description


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_every_param_is_documented(tools, name):
    for param, schema in tools[name].inputSchema.get("properties", {}).items():
        assert schema.get("description") or "enum" in json.dumps(schema), f"{name}.{param}"


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_annotations(tools, name):
    annotations = tools[name].annotations
    assert annotations is not None
    assert annotations.readOnlyHint is (name not in WRITE_TOOLS)
    assert bool(annotations.destructiveHint) is (name in DESTRUCTIVE_TOOLS)
    if name in WRITE_TOOLS:
        assert "explicitly ask" in tools[name].description


def test_instructions_present_and_bounded():
    assert INSTRUCTIONS and len(INSTRUCTIONS) <= 1500
    for name in ("avanan_list_tenants", "avanan_query_events", "avanan_get_task_status"):
        assert name in INSTRUCTIONS


@pytest.mark.parametrize(
    "status_code,expected_code,expected_retryable",
    [
        (0, "upstream_error", True),
        (400, "invalid_argument", False),
        (401, "unauthorized", False),
        (403, "unauthorized", False),
        (404, "not_found", False),
        (422, "invalid_argument", False),
        (429, "rate_limited", True),
        (500, "upstream_error", True),
        (503, "upstream_error", True),
    ],
)
def test_error_envelope_mapping(status_code, expected_code, expected_retryable):
    envelope = json.loads(AvananError(status_code, "boom").to_envelope())
    assert envelope == {
        "error": {"code": expected_code, "message": "boom", "retryable": expected_retryable}
    }
