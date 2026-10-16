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
"""License packages, add-ons and tenant licensing."""

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import AvananClient
from ._common import READ_ONLY, WRITES, ClientFactory, TenantId, list_result, request_data, run_tool, single_result


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def avanan_list_licenses() -> str:
        """List the license packages (licenseCodeName) the MSP can assign to tenants."""

        async def action(client: AvananClient) -> dict:
            return list_result(await client.request("GET", "/msp/licenses"))

        return await run_tool("avanan_list_licenses", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def avanan_list_addons() -> str:
        """List the add-ons (with ids) that can be added to a tenant license."""

        async def action(client: AvananClient) -> dict:
            return list_result(await client.request("GET", "/msp/addons"))

        return await run_tool("avanan_list_addons", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def avanan_assign_license(
        tenant_id: TenantId,
        licenseCodeName: Annotated[str, Field(description="License package code from avanan_list_licenses.")],
        addonIdList: Annotated[list[int] | None, Field(description="Add-on ids from avanan_list_addons.")] = None,
        maxLicensedUsers: Annotated[int | None, Field(description="Seat cap for the tenant.", ge=1)] = None,
    ) -> str:
        """Set a tenant's license package, add-ons and seat cap.

        Affects billing: only when the user explicitly asks.
        """

        async def action(client: AvananClient) -> Any:
            body = request_data(
                {"licenseCodeName": licenseCodeName, "addonIdList": addonIdList, "maxLicensedUsers": maxLicensedUsers}
            )
            return single_result(await client.request("POST", f"/msp/tenants/{int(tenant_id)}/license", body=body))

        return await run_tool("avanan_assign_license", client_factory, action)
