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
"""Billing usage (parent and standalone MSPs)."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import AvananClient
from ._common import READ_ONLY, ClientFactory, ScrollId, list_result, request_data, run_tool

Year = Annotated[int, Field(description="Year, e.g. 2026.", ge=2015, le=2100)]
Month = Annotated[int, Field(description="Month 1-12.", ge=1, le=12)]
MspIds = Annotated[list[int] | None, Field(description="Only these child MSP ids.")]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def avanan_get_monthly_usage(
        year: Year, month: Month, msp_ids: MspIds = None, scrollId: ScrollId = None
    ) -> str:
        """Get per-tenant billable usage (protected users per license) for one month."""

        async def action(client: AvananClient) -> dict:
            params = {"year": year, "month": month, "msp_ids": msp_ids or None}
            return list_result(
                await client.request("GET", "/msp/usage", params=params, body=request_data({"scrollId": scrollId}))
            )

        return await run_tool("avanan_get_monthly_usage", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def avanan_get_daily_usage(
        year: Year,
        month: Month,
        day: Annotated[int, Field(description="Day 1-31.", ge=1, le=31)],
        msp_ids: MspIds = None,
        scrollId: ScrollId = None,
    ) -> str:
        """Get per-tenant billable usage for one day."""

        async def action(client: AvananClient) -> dict:
            params = {"year": year, "month": month, "day": day, "msp_ids": msp_ids or None}
            return list_result(
                await client.request("GET", "/msp/usage/day", params=params, body=request_data({"scrollId": scrollId}))
            )

        return await run_tool("avanan_get_daily_usage", client_factory, action)
