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
"""MSP portal users."""

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
    list_result,
    request_data,
    run_tool,
    single_result,
)

UserId = Annotated[int, Field(description="MSP user id (from avanan_list_msp_users).")]
FirstName = Annotated[str, Field(description="First name.")]
LastName = Annotated[str, Field(description="Last name.")]
Email = Annotated[str, Field(description="E-mail address (login).")]
Role = Annotated[Literal["admin", "operations", "user", "read-only"], Field(description="Portal role.")]
DirectLogin = Annotated[bool, Field(description="Allow password login to the MSP portal.")]
SamlLogin = Annotated[bool, Field(description="Allow SAML login to the MSP portal.")]
ViewPrivate = Annotated[bool, Field(description="Allow viewing private data on customer portals.")]
SendAlerts = Annotated[bool, Field(description="Send customer tenant alerts to this user.")]
WeeklyReports = Annotated[bool, Field(description="Send weekly customer reports to this user.")]


def _user_body(**values: Any) -> dict:
    return request_data(values)


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def avanan_list_msp_users(scrollId: ScrollId = None, MSPId: MspId = None) -> str:
        """List the MSP portal users: id, name, e-mail, role and login options."""

        async def action(client: AvananClient) -> dict:
            body = request_data({"MSPId": MSPId, "scrollId": scrollId})
            return list_result(await client.request("GET", "/msp/users", body=body))

        return await run_tool("avanan_list_msp_users", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def avanan_get_msp_user(user_id: UserId) -> str:
        """Get one MSP portal user."""

        async def action(client: AvananClient) -> Any:
            return single_result(await client.request("GET", f"/msp/users/{int(user_id)}"))

        return await run_tool("avanan_get_msp_user", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def avanan_create_msp_user(
        firstName: FirstName,
        lastName: LastName,
        email: Email,
        role: Role,
        directLogin: DirectLogin,
        samlLogin: SamlLogin,
        viewPrivateData: ViewPrivate,
        sendAlerts: SendAlerts,
        receiveWeeklyReports: WeeklyReports,
        MSPId: MspId = None,
    ) -> str:
        """Create an MSP portal user. Grants portal access: only when the user explicitly asks."""

        async def action(client: AvananClient) -> Any:
            body = _user_body(
                MSPId=MSPId,
                firstName=firstName,
                lastName=lastName,
                email=email,
                role=role,
                directLogin=directLogin,
                samlLogin=samlLogin,
                viewPrivateData=viewPrivateData,
                sendAlerts=sendAlerts,
                receiveWeeklyReports=receiveWeeklyReports,
            )
            return single_result(await client.request("POST", "/msp/users", body=body))

        return await run_tool("avanan_create_msp_user", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def avanan_update_msp_user(
        user_id: UserId,
        firstName: FirstName,
        lastName: LastName,
        email: Email,
        role: Role,
        directLogin: DirectLogin,
        samlLogin: SamlLogin,
        viewPrivateData: ViewPrivate,
        sendAlerts: SendAlerts,
        receiveWeeklyReports: WeeklyReports,
    ) -> str:
        """Replace an MSP portal user's settings (all fields required). Only when the user explicitly asks."""

        async def action(client: AvananClient) -> Any:
            body = _user_body(
                firstName=firstName,
                lastName=lastName,
                email=email,
                role=role,
                directLogin=directLogin,
                samlLogin=samlLogin,
                viewPrivateData=viewPrivateData,
                sendAlerts=sendAlerts,
                receiveWeeklyReports=receiveWeeklyReports,
            )
            return single_result(await client.request("PUT", f"/msp/users/{int(user_id)}", body=body))

        return await run_tool("avanan_update_msp_user", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def avanan_delete_msp_user(user_id: UserId) -> str:
        """Delete an MSP portal user. Removes access: only when the user explicitly asks for that user id."""

        async def action(client: AvananClient) -> Any:
            result = single_result(await client.request("DELETE", f"/msp/users/{int(user_id)}"))
            return result if result else {"deleted": True, "user_id": user_id}

        return await run_tool("avanan_delete_msp_user", client_factory, action)
