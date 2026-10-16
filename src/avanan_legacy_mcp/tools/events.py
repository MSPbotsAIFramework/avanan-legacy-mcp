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
"""Security events (phishing, malware, DLP, anomalies, ...)."""

from typing import Annotated, Any, Literal
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import AvananClient
from ._common import READ_ONLY, ClientFactory, ScrollId, list_result, request_data, run_tool, single_result

EventType = Literal[
    "phishing",
    "malware",
    "suspicious malware",
    "dlp",
    "anomaly",
    "shadow_it",
    "malicious_url_click",
    "malicious_url",
    "spam",
    "alert",
]
EventState = Literal["new", "detected", "pending", "remediated", "dismissed", "exception"]
Severity = Literal["lowest", "low", "medium", "high", "critical"]
Saas = Literal[
    "office365_emails",
    "office365_onedrive",
    "office365_sharepoint",
    "sharefile",
    "slack",
    "ms_teams",
    "google_mail",
    "google_drive",
    "box",
    "dropbox",
]
DateTime = Annotated[str | None, Field(description="ISO 8601 date-time, e.g. 2026-01-31T00:00:00.000Z.")]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def avanan_query_events(
        eventTypes: Annotated[list[EventType] | None, Field(description="Event types.")] = None,
        eventStates: Annotated[list[EventState] | None, Field(description="Event states.")] = None,
        severities: Annotated[list[Severity] | None, Field(description="Severities.")] = None,
        saas: Annotated[list[Saas] | None, Field(description="Protected apps.")] = None,
        eventIds: Annotated[list[str] | None, Field(description="Specific event ids.")] = None,
        confidenceIndicator: Annotated[str | None, Field(description="Confidence indicator value.")] = None,
        startDate: DateTime = None,
        endDate: DateTime = None,
        description: Annotated[str | None, Field(description="Text contained in the event description.")] = None,
        scopes: Annotated[
            list[str] | None, Field(description="MSP keys only: limit to these farm:tenant scopes.")
        ] = None,
        scrollId: ScrollId = None,
    ) -> str:
        """Search security events by type, state, severity, app and time window.

        Set startDate to keep results focused. Use avanan_get_event for one event's full detail.
        """

        async def action(client: AvananClient) -> dict:
            body = request_data(
                {
                    "scopes": scopes,
                    "eventTypes": eventTypes,
                    "eventStates": eventStates,
                    "severities": severities,
                    "saas": saas,
                    "eventIds": eventIds,
                    "confidenceIndicator": confidenceIndicator,
                    "startDate": startDate,
                    "endDate": endDate,
                    "description": description,
                    "scrollId": scrollId,
                }
            )
            return list_result(await client.request("POST", "/event/query", body=body))

        return await run_tool("avanan_query_events", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def avanan_get_event(
        eventId: Annotated[str, Field(description="Event id from avanan_query_events.")],
    ) -> str:
        """Get one security event: type, state, severity, affected entity, actions taken and available."""

        async def action(client: AvananClient) -> Any:
            return single_result(await client.request("GET", f"/event/{quote(eventId.strip(), safe='')}"))

        return await run_tool("avanan_get_event", client_factory, action)
