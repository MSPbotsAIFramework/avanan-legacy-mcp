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
"""MSP customer tenants."""

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import AvananClient
from ._common import (
    DESTRUCTIVE,
    READ_ONLY,
    WRITES,
    ClientFactory,
    MspId,
    ScrollId,
    TenantId,
    list_result,
    request_data,
    run_tool,
    single_result,
)


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def avanan_list_tenants(scrollId: ScrollId = None, MSPId: MspId = None) -> str:
        """List the MSP's customer tenants: id, name, domain, region, license and status."""

        async def action(client: AvananClient) -> dict:
            body = request_data({"scrollId": scrollId, "MSPId": MSPId})
            return list_result(await client.request("GET", "/msp/tenants", body=body))

        return await run_tool("avanan_list_tenants", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def avanan_get_tenant(tenant_id: TenantId) -> str:
        """Get one customer tenant's details, including its license and add-ons."""

        async def action(client: AvananClient) -> Any:
            return single_result(await client.request("GET", f"/msp/tenants/{int(tenant_id)}"))

        return await run_tool("avanan_get_tenant", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def avanan_create_tenant(
        adminEmail: Annotated[str, Field(description="Tenant administrator e-mail.")],
        tenantName: Annotated[str, Field(description="Portal name; becomes <tenantName>.avanan.net.")],
        adminName: Annotated[str, Field(description="Administrator's first and last name.")],
        phone: Annotated[str, Field(description="Administrator phone number.")],
        companyName: Annotated[str, Field(description="Customer company name.")],
        tenantRegion: Annotated[Literal["us", "eu", "ca"], Field(description="Data region of the new tenant.")],
        MSPId: MspId = None,
    ) -> str:
        """Create a new customer tenant (portal). Changes data: only when the user explicitly asks."""

        async def action(client: AvananClient) -> Any:
            body = request_data(
                {
                    "adminEmail": adminEmail,
                    "tenantName": tenantName,
                    "adminName": adminName,
                    "phone": phone,
                    "companyName": companyName,
                    "tenantRegion": tenantRegion,
                    "MSPId": MSPId,
                }
            )
            return single_result(await client.request("POST", "/msp/tenants", body=body))

        return await run_tool("avanan_create_tenant", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def avanan_delete_tenant(tenant_id: TenantId) -> str:
        """Delete a customer tenant and its protection. Irreversible.

        Destructive: only when the user explicitly asks to delete that tenant id.
        """

        async def action(client: AvananClient) -> Any:
            result = single_result(await client.request("DELETE", f"/msp/tenants/{int(tenant_id)}"))
            return result if result else {"deleted": True, "tenant_id": tenant_id}

        return await run_tool("avanan_delete_tenant", client_factory, action)
