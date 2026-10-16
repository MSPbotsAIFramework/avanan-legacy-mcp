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
"""Child MSP partners (parent MSPs only)."""

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import AvananClient
from ._common import DESTRUCTIVE, READ_ONLY, WRITES, ClientFactory, list_result, request_data, run_tool, single_result


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def avanan_list_msp_partners() -> str:
        """List the child MSPs managed by this parent MSP (id and name)."""

        async def action(client: AvananClient) -> dict:
            return list_result(await client.request("GET", "/msp/msp-partners"))

        return await run_tool("avanan_list_msp_partners", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def avanan_create_msp_partner(
        name: Annotated[str, Field(description="Child MSP name.")],
        website: Annotated[str, Field(description="Child MSP website.")],
        country: Annotated[str, Field(description="Country.")],
        zip: Annotated[str, Field(description="Postal code.")],
        state: Annotated[str | None, Field(description="State or province.")] = None,
    ) -> str:
        """Create a child MSP under this parent MSP. Only when the user explicitly asks."""

        async def action(client: AvananClient) -> Any:
            body = request_data({"name": name, "website": website, "country": country, "state": state, "zip": zip})
            return single_result(await client.request("POST", "/msp/msp-partners-extended", body=body))

        return await run_tool("avanan_create_msp_partner", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def avanan_delete_msp_partner(
        msp_id: Annotated[int, Field(description="Child MSP id from avanan_list_msp_partners.")],
    ) -> str:
        """Delete a child MSP. Irreversible: only when the user explicitly asks to delete that MSP id."""

        async def action(client: AvananClient) -> Any:
            result = single_result(await client.request("DELETE", f"/msp/msp-partners/{int(msp_id)}"))
            return result if result else {"deleted": True, "msp_id": msp_id}

        return await run_tool("avanan_delete_msp_partner", client_factory, action)
