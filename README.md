# Avanan (Legacy) MCP Server

An [MCP](https://modelcontextprotocol.io) server for the legacy **Avanan SmartAPI**
(Check Point Harmony Email & Collaboration), hosted on `smart-api-production-*.avanan.net`.
It covers two areas:

- **MSP portfolio** (MSP API key): customer tenants, licenses and add-ons, monthly and daily
  usage for billing, child MSP partners and MSP portal users.
- **Security operations**: security events, secured entities such as emails, allow / block
  exception rules, and quarantine / restore actions with task tracking.

- Transport: MCP Streamable HTTP at `POST /mcp`, health probe at `GET /health`
- Stateless and multi-tenant: credentials arrive on every request as HTTP headers and are
  never stored; the access token is requested per request and not cached
- Python 3.12, [uv](https://docs.astral.sh/uv/), FastMCP, httpx
- License: Apache-2.0, Copyright 2026 MSPbots.ai

## Authentication headers

| Header | Required | Type | Default | Allowed values | Description | Example |
|---|---|---|---|---|---|---|
| `X-Avanan-App-Id` | Yes | string | none | - | SmartAPI client (application) id | `US:your-app-id` |
| `X-Avanan-Secret` | Yes | string | none | - | Client secret; used only to sign requests, never sent | `your-app-secret` |
| `X-Avanan-Region` | No | string | `us` | `us`, `eu`, `ca`, `ap` (`au`), `euw2` (`uk`), `aps1` (`in`), `mec1` (`uae`) | Region the key belongs to | `eu` |
| `X-Avanan-Token` | No | string | none | - | Pre-issued access token; skips the token request (app id and secret are still needed to sign) | `your-token` |

`X-Avanan-Client-Id` and `X-Avanan-Client-Secret` are accepted as alternative names for the
first two headers.

Where to get them:

- **Client id / secret**: issued by Avanan / Check Point support when the SmartAPI is enabled.
  MSPs use the MSP API key, which also works for every customer tenant in that region.
- **Region**: keys are regional; a key only works against its own region, and you need one key
  per region you manage. MSP management endpoints are not available in the UAE region.

Every request is signed: `x-av-sig` is the SHA-256 hex digest of the Base64 of
request id + app id + date (+ request path and query) + secret. A request to `/mcp` without the
required headers gets HTTP 401 listing them. An unknown region does not block `tools/list`; tool
calls then return an `invalid_argument` error naming the allowed regions.

## Tools

All tools return a JSON string. List tools return `{items, count, total, has_more, scroll_id}`;
pass `scroll_id` back as `scrollId` for the next page. The API has no page size: if a batch is too large for one response, the first records
that fit are returned without `scroll_id` (following it would skip the rest of the batch), and the note
says to narrow the query. Empty values are left out of list records.

MSP portfolio:

| Tool | Purpose | Parameters (required in **bold**) |
|---|---|---|
| `avanan_test_connection` | Check the credentials and region | - |
| `avanan_list_scopes` | farm:tenant scopes the key can access | - |
| `avanan_list_tenants` | Customer tenants | scrollId, MSPId |
| `avanan_get_tenant` | One tenant with license details | **tenant_id** |
| `avanan_create_tenant` | Create a tenant (**write**) | **adminEmail**, **tenantName**, **adminName**, **phone**, **companyName**, **tenantRegion** (`us`, `eu`, `ca`), MSPId |
| `avanan_delete_tenant` | Delete a tenant (**destructive**) | **tenant_id** |
| `avanan_list_licenses` | License packages | - |
| `avanan_list_addons` | Add-ons | - |
| `avanan_assign_license` | Set a tenant's license (**write**) | **tenant_id**, **licenseCodeName**, addonIdList, maxLicensedUsers |
| `avanan_get_monthly_usage` | Billable usage for a month | **year**, **month**, msp_ids, scrollId |
| `avanan_get_daily_usage` | Billable usage for a day | **year**, **month**, **day**, msp_ids, scrollId |
| `avanan_list_msp_partners` | Child MSPs | - |
| `avanan_create_msp_partner` | Create a child MSP (**write**) | **name**, **website**, **country**, **zip**, state |
| `avanan_delete_msp_partner` | Delete a child MSP (**destructive**) | **msp_id** |
| `avanan_list_msp_users` | MSP portal users | scrollId, MSPId |
| `avanan_get_msp_user` | One MSP user | **user_id** |
| `avanan_create_msp_user` | Create an MSP user (**write**) | **firstName**, **lastName**, **email**, **role**, **directLogin**, **samlLogin**, **viewPrivateData**, **sendAlerts**, **receiveWeeklyReports**, MSPId |
| `avanan_update_msp_user` | Replace an MSP user's settings (**write**) | **user_id** plus the same required fields |
| `avanan_delete_msp_user` | Delete an MSP user (**destructive**) | **user_id** |

Security operations:

| Tool | Purpose | Parameters (required in **bold**) |
|---|---|---|
| `avanan_query_events` | Search security events | eventTypes, eventStates, severities, saas, eventIds, confidenceIndicator, startDate, endDate, description, scopes, scrollId |
| `avanan_get_event` | One event | **eventId** |
| `avanan_search_emails` | Search secured entities (emails) | **saas**, **startDate**, saasEntity, endDate, filters (`[{saasAttrName, saasAttrOp, saasAttrValue}]`), scopes, scrollId |
| `avanan_get_email` | One entity | **entityId** |
| `avanan_list_exceptions` | Allow / block rules | **excType** (`whitelist`, `blacklist`) |
| `avanan_get_exception` | One rule | **excType**, **excId** |
| `avanan_add_exception` | Add a rule (**write**) | **excType**, sender / recipient / subject / IP / link fields and matching modes |
| `avanan_update_exception` | Update a rule (**write**) | **excType**, **excId**, same fields |
| `avanan_delete_exception` | Delete a rule (**destructive**) | **excType**, **excId** |
| `avanan_quarantine_events` | Quarantine the emails behind events (**destructive**, reversible) | **eventIds**, scope |
| `avanan_restore_events` | Restore them (**write**) | **eventIds**, scope |
| `avanan_quarantine_emails` | Quarantine emails by entity id (**destructive**, reversible) | **entityIds**, entityType, scope |
| `avanan_restore_emails` | Restore emails (**write**) | **entityIds**, entityType, scope |
| `avanan_get_task_status` | Progress of a quarantine / restore task | **taskId**, scope |

With an MSP key, event and email queries cover all customer scopes by default; action tools
need a single `scope` (from `avanan_list_scopes`).

Errors come back as a JSON envelope instead of an exception:

```json
{"error": {"code": "unauthorized", "message": "Avanan rejected the app id / secret for this region (token request failed)", "retryable": false}}
```

`code` is one of `not_configured`, `unauthorized`, `not_found`, `invalid_argument`,
`rate_limited`, `upstream_error`. An HTTP 200 response whose `responseEnvelope.responseCode` is
not 0 is reported as `invalid_argument` with Avanan's response text.

## Run locally

```bash
uv sync
uv run python -m avanan_legacy_mcp          # listens on 0.0.0.0:8080
```

or with Docker:

```bash
docker build --platform linux/amd64 -t avanan-legacy-mcp:dev .
docker run --rm -p 8080:8080 avanan-legacy-mcp:dev
```

Configuration (environment variables, all optional): `MCP_HTTP_HOST` (default `0.0.0.0`),
`MCP_HTTP_PORT` (default `8080`), `LOG_LEVEL` (default `INFO`). Credentials are never read from
the environment.

## Testing example

```bash
# list tools
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Avanan-App-Id: US:your-app-id" \
  -H "X-Avanan-Secret: your-app-secret" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# phishing events since a date
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Avanan-App-Id: US:your-app-id" \
  -H "X-Avanan-Secret: your-app-secret" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"avanan_query_events","arguments":{"eventTypes":["phishing"],"startDate":"2026-01-01T00:00:00.000Z"}}}'
```

Unit tests (no network access needed):

```bash
uv run pytest
```

## Delivery notes

- **Tool count (33).** Above the suggested 20 because the tool names are an existing contract;
  none were merged or removed.
- **Header names.** The server reads `X-Avanan-App-Id` / `X-Avanan-Secret` / `X-Avanan-Region` /
  `X-Avanan-Token` as registered for this integration, and also accepts `X-Avanan-Client-Id` /
  `X-Avanan-Client-Secret`.
- **Write tools.** 15 tools change data (create, update, delete, license, quarantine, restore).
  They are annotated (`readOnlyHint=false`; delete and quarantine also `destructiveHint=true`)
  and their descriptions tell the agent to act only on an explicit request. The exception list
  and get tools are read-only.

## License

Apache License 2.0 - see [LICENSE](LICENSE) and [NOTICE](NOTICE).
