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
"""Connectivity check and scope discovery."""

from mcp.server.fastmcp import FastMCP

from ..api_client import AvananClient
from ._common import READ_ONLY, ClientFactory, data, run_tool


async def _scopes(client: AvananClient) -> list:
    value = data(await client.request("GET", "/scopes"))
    return value if isinstance(value, list) else ([] if value is None else [value])


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def avanan_test_connection() -> str:
        """Check that the app id / secret work in the selected region and how many scopes the key covers."""

        async def action(client: AvananClient) -> dict:
            scopes = await _scopes(client)
            return {"authenticated": True, "region": client.region, "host": client.host, "scope_count": len(scopes)}

        return await run_tool("avanan_test_connection", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def avanan_list_scopes() -> str:
        """List the farm:tenant scopes this API key can access.

        An MSP key sees one scope per customer tenant; pass one as `scope` to action tools.
        """

        async def action(client: AvananClient) -> dict:
            scopes = await _scopes(client)
            return {"items": scopes, "count": len(scopes)}

        return await run_tool("avanan_list_scopes", client_factory, action)
