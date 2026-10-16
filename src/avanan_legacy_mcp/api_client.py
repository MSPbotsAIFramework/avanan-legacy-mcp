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
"""Async client for the Avanan SmartAPI (signed requests, per-request token)."""

import asyncio
import base64
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from ._json import error_envelope
from .config import API_VERSION, DEFAULT_REGION, REGION_HOSTS

logger = logging.getLogger("avanan_legacy_mcp.api")

_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 2
_MAX_BACKOFF_SECONDS = 20.0
_CALL_BUDGET_SECONDS = 100.0

# One connection pool for the process. It never holds credentials: every
# request carries its own signed headers.
_shared_http_client: httpx.AsyncClient | None = None


def _get_shared_http_client() -> httpx.AsyncClient:
    global _shared_http_client
    if _shared_http_client is None:
        _shared_http_client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _shared_http_client


_STATUS_TO_CODE: dict[int, tuple[str, bool]] = {
    0: ("upstream_error", True),
    400: ("invalid_argument", False),
    401: ("unauthorized", False),
    403: ("unauthorized", False),
    404: ("not_found", False),
    422: ("invalid_argument", False),
    429: ("rate_limited", True),
}


def classify_status(status_code: int) -> tuple[str, bool]:
    if status_code in _STATUS_TO_CODE:
        return _STATUS_TO_CODE[status_code]
    if status_code >= 500:
        return "upstream_error", True
    if status_code >= 400:
        return "invalid_argument", False
    return "upstream_error", True


class AvananError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Avanan API error {status_code}: {message}")

    def to_envelope(self) -> str:
        code, retryable = classify_status(self.status_code)
        return error_envelope(code, self.message, retryable)


@dataclass(frozen=True)
class AvananCredentials:
    app_id: str
    secret: str
    region: str = DEFAULT_REGION
    token: str | None = None  # optional pre-issued access token

    def __repr__(self) -> str:  # never leak secrets into logs or tracebacks
        return f"AvananCredentials(app_id=<redacted>, secret=<redacted>, region={self.region!r})"


def sign(request_id: str, app_id: str, date: str, secret: str, request_string: str = "") -> str:
    """x-av-sig: sha256 hex of base64(req-id + app-id + date [+ request string] + secret)."""
    raw = f"{request_id}{app_id}{date}{request_string}{secret}".encode()
    return hashlib.sha256(base64.b64encode(raw)).hexdigest()


def request_date() -> str:
    """x-av-date: UTC ISO-8601 without a time-zone suffix."""
    return datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="milliseconds")


class AvananClient:
    """SmartAPI wrapper for one caller's credentials.

    The access token is requested lazily and kept only on this instance, which
    lives for a single MCP request; it is never cached across requests.
    """

    def __init__(self, credentials: AvananCredentials, http_client: httpx.AsyncClient | None = None):
        self._credentials = credentials
        self._http = http_client
        self._token: str | None = credentials.token
        self.host = REGION_HOSTS[credentials.region]
        self.base_url = f"https://{self.host}/{API_VERSION}"

    @property
    def region(self) -> str:
        return self._credentials.region

    def _signed_headers(self, token: str, request_string: str = "") -> dict[str, str]:
        request_id = str(uuid.uuid4())
        date = request_date()
        creds = self._credentials
        return {
            "x-av-req-id": request_id,
            "x-av-app-id": creds.app_id,
            "x-av-date": date,
            "x-av-sig": sign(request_id, creds.app_id, date, creds.secret, request_string),
            "x-av-token": token,
            "Accept": "application/json",
        }

    async def _access_token(self) -> str:
        if self._token is None:
            http = self._http or _get_shared_http_client()
            try:
                resp = await http.get(f"{self.base_url}/auth", headers=self._signed_headers(""))
            except httpx.RequestError as e:
                raise AvananError(0, f"Network error requesting an access token: {type(e).__name__}") from e
            logger.info("avanan_api method=GET path=/auth status=%s", resp.status_code)
            if resp.status_code in (400, 401, 403):
                raise AvananError(401, "Avanan rejected the app id / secret for this region (token request failed)")
            if resp.status_code >= 400:
                raise AvananError(resp.status_code, f"Avanan returned HTTP {resp.status_code} on token request")
            token = resp.text.strip().strip('"')
            if not token:
                raise AvananError(502, "Token response was empty")
            self._token = token
        return self._token

    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: Any = None,
    ) -> Any:
        """Send a signed request; ``path`` is relative to /v1.0, e.g. ``/msp/tenants``."""
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
        request_string = f"/{API_VERSION}{path}" + (f"?{query}" if query else "")
        url = f"https://{self.host}{request_string}"
        token = await self._access_token()
        http = self._http or _get_shared_http_client()

        started = time.monotonic()
        attempt = 0
        while True:
            # Fresh request id, date and signature on every attempt.
            headers = self._signed_headers(token, request_string)
            t0 = time.monotonic()
            resp = None
            error: AvananError | None = None
            try:
                resp = await http.request(method, url, headers=headers, json=body)
                status = resp.status_code
            except httpx.TimeoutException:
                status, error = 0, AvananError(0, f"Timed out calling Avanan ({method} {path})")
            except httpx.RequestError as e:
                status = 0
                error = AvananError(0, f"Network error calling Avanan ({method} {path}): {type(e).__name__}")

            logger.info(
                "avanan_api method=%s path=%s status=%s ms=%d attempt=%d",
                method,
                path,
                status,
                (time.monotonic() - t0) * 1000,
                attempt,
            )

            if (status == 0 or status in _RETRYABLE_STATUS) and attempt < _MAX_RETRIES:
                delay = _retry_delay(resp, attempt)
                if time.monotonic() - started + delay < _CALL_BUDGET_SECONDS:
                    attempt += 1
                    await asyncio.sleep(delay)
                    continue

            if error is not None:
                raise error
            assert resp is not None
            payload = _parse_body(resp)
            if resp.status_code >= 400:
                raise AvananError(resp.status_code, _error_message(resp.status_code, payload))
            _raise_for_envelope(payload)
            return payload


def _retry_delay(resp: httpx.Response | None, attempt: int) -> float:
    if resp is not None:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), _MAX_BACKOFF_SECONDS))
            except ValueError:
                pass
    return min(float(2**attempt), _MAX_BACKOFF_SECONDS)


def _parse_body(resp: httpx.Response) -> Any:
    if not resp.content:
        return None
    try:
        return resp.json()
    except ValueError:
        return {"raw_response": resp.text[:2000]}


def _envelope(payload: Any) -> dict:
    if isinstance(payload, dict) and isinstance(payload.get("responseEnvelope"), dict):
        return payload["responseEnvelope"]
    return {}


def _error_message(status_code: int, payload: Any) -> str:
    fallback = f"Avanan returned HTTP {status_code}"
    env = _envelope(payload)
    text = " ".join(str(env.get(k)) for k in ("responseText", "additionalText") if env.get(k))
    if not text and isinstance(payload, dict):
        text = str(payload.get("message") or payload.get("error") or "")
    return f"{fallback}: {text[:500]}" if text else fallback


def _raise_for_envelope(payload: Any) -> None:
    """HTTP 200 with a non-zero responseCode is still a failed request."""
    env = _envelope(payload)
    code = env.get("responseCode")
    if code not in (None, 0, "0"):
        text = " ".join(str(env.get(k)) for k in ("responseText", "additionalText") if env.get(k))
        raise AvananError(400, f"Avanan responseCode {code}: {text[:500]}" if text else f"Avanan responseCode {code}")
