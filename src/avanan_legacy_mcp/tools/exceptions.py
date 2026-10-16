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
"""Allow (whitelist) and block (blacklist) exception rules."""

from typing import Annotated, Any, Literal
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import AvananClient
from ._common import DESTRUCTIVE, READ_ONLY, WRITES, ClientFactory, list_result, request_data, run_tool, single_result

ExcType = Annotated[Literal["whitelist", "blacklist"], Field(description="Exception list: whitelist (allow) or blacklist (block).")]
ExcId = Annotated[str, Field(description="Exception id from avanan_list_exceptions.")]
Opt = Annotated[str | None, Field(description="Optional.")]
Match2 = Literal["matching", "contains"]


def _fields(**values: Any) -> dict:
    body = request_data(values)
    if not body["requestData"]:
        raise ValueError("Give at least one exception field (for example senderEmail or senderDomain)")
    return body


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def avanan_list_exceptions(excType: ExcType) -> str:
        """List the allow (whitelist) or block (blacklist) exception rules."""

        async def action(client: AvananClient) -> dict:
            return list_result(await client.request("GET", f"/exceptions/{excType}"))

        return await run_tool("avanan_list_exceptions", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def avanan_get_exception(excType: ExcType, excId: ExcId) -> str:
        """Get one exception rule."""

        async def action(client: AvananClient) -> Any:
            return single_result(await client.request("GET", f"/exceptions/{excType}/{quote(excId.strip(), safe='')}"))

        return await run_tool("avanan_get_exception", client_factory, action)

    async def _write(client: AvananClient, method: str, path: str, body: dict) -> Any:
        return single_result(await client.request(method, path, body=body))

    @mcp.tool(annotations=WRITES)
    async def avanan_add_exception(
        excType: ExcType,
        senderEmail: Annotated[str | None, Field(description="Sender e-mail address.")] = None,
        senderDomain: Annotated[str | None, Field(description="Sender domain.")] = None,
        senderName: Annotated[str | None, Field(description="Sender display name.")] = None,
        recipient: Annotated[str | None, Field(description="Recipient e-mail address.")] = None,
        subject: Annotated[str | None, Field(description="E-mail subject.")] = None,
        attachmentMd5: Annotated[str | None, Field(description="Attachment MD5 hash.")] = None,
        linkDomains: Annotated[str | None, Field(description="Link domain(s) in the body.")] = None,
        senderIp: Annotated[str | None, Field(description="Sender IP address.")] = None,
        senderClientIp: Annotated[str | None, Field(description="Sender client IP address.")] = None,
        comment: Annotated[str | None, Field(description="Why the rule exists.")] = None,
        actionNeeded: Opt = None,
        matchOnlyFuture: Opt = None,
        quarantineAll: Opt = None,
        ignoringSpfCheck: Annotated[bool | None, Field(description="Ignore the SPF check.")] = None,
        senderEmailMatching: Match2 | None = None,
        senderDomainMatching: Literal["contains", "endswith"] | None = None,
        senderNameMatching: Match2 | None = None,
        recipientMatching: Match2 | None = None,
        subjectMatching: Match2 | None = None,
        linkDomainMatching: Match2 | None = None,
    ) -> str:
        """Add an allow or block rule. Changes how mail is filtered: only when the user explicitly asks."""

        async def action(client: AvananClient) -> Any:
            body = _fields(
                senderEmail=senderEmail, senderDomain=senderDomain, senderName=senderName, recipient=recipient,
                subject=subject, attachmentMd5=attachmentMd5, linkDomains=linkDomains, senderIp=senderIp,
                senderClientIp=senderClientIp, comment=comment, actionNeeded=actionNeeded,
                matchOnlyFuture=matchOnlyFuture, quarantineAll=quarantineAll, ignoringSpfCheck=ignoringSpfCheck,
                senderEmailMatching=senderEmailMatching, senderDomainMatching=senderDomainMatching,
                senderNameMatching=senderNameMatching, recipientMatching=recipientMatching,
                subjectMatching=subjectMatching, linkDomainMatching=linkDomainMatching,
            )
            return await _write(client, "POST", f"/exceptions/{excType}", body)

        return await run_tool("avanan_add_exception", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def avanan_update_exception(
        excType: ExcType,
        excId: ExcId,
        senderEmail: Annotated[str | None, Field(description="Sender e-mail address.")] = None,
        senderDomain: Annotated[str | None, Field(description="Sender domain.")] = None,
        senderName: Annotated[str | None, Field(description="Sender display name.")] = None,
        recipient: Annotated[str | None, Field(description="Recipient e-mail address.")] = None,
        subject: Annotated[str | None, Field(description="E-mail subject.")] = None,
        attachmentMd5: Annotated[str | None, Field(description="Attachment MD5 hash.")] = None,
        linkDomains: Annotated[str | None, Field(description="Link domain(s) in the body.")] = None,
        senderIp: Annotated[str | None, Field(description="Sender IP address.")] = None,
        senderClientIp: Annotated[str | None, Field(description="Sender client IP address.")] = None,
        comment: Annotated[str | None, Field(description="Why the rule exists.")] = None,
        actionNeeded: Opt = None,
        matchOnlyFuture: Opt = None,
        quarantineAll: Opt = None,
        ignoringSpfCheck: Annotated[bool | None, Field(description="Ignore the SPF check.")] = None,
        senderEmailMatching: Match2 | None = None,
        senderDomainMatching: Literal["contains", "endswith"] | None = None,
        senderNameMatching: Match2 | None = None,
        recipientMatching: Match2 | None = None,
        subjectMatching: Match2 | None = None,
        linkDomainMatching: Match2 | None = None,
    ) -> str:
        """Update an allow or block rule. Changes how mail is filtered: only when the user explicitly asks."""

        async def action(client: AvananClient) -> Any:
            body = _fields(
                senderEmail=senderEmail, senderDomain=senderDomain, senderName=senderName, recipient=recipient,
                subject=subject, attachmentMd5=attachmentMd5, linkDomains=linkDomains, senderIp=senderIp,
                senderClientIp=senderClientIp, comment=comment, actionNeeded=actionNeeded,
                matchOnlyFuture=matchOnlyFuture, quarantineAll=quarantineAll, ignoringSpfCheck=ignoringSpfCheck,
                senderEmailMatching=senderEmailMatching, senderDomainMatching=senderDomainMatching,
                senderNameMatching=senderNameMatching, recipientMatching=recipientMatching,
                subjectMatching=subjectMatching, linkDomainMatching=linkDomainMatching,
            )
            return await _write(client, "PUT", f"/exceptions/{excType}/{quote(excId.strip(), safe='')}", body)

        return await run_tool("avanan_update_exception", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def avanan_delete_exception(excType: ExcType, excId: ExcId) -> str:
        """Delete an allow or block rule. Irreversible: only when the user explicitly asks for that rule id."""

        async def action(client: AvananClient) -> Any:
            result = single_result(
                await client.request("POST", f"/exceptions/{excType}/delete/{quote(excId.strip(), safe='')}")
            )
            return result if result else {"deleted": True, "excType": excType, "excId": excId}

        return await run_tool("avanan_delete_exception", client_factory, action)
