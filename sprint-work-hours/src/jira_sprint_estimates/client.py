"""Thin async Jira Cloud client.

Two API families are in play and they paginate differently:

* Platform ``/rest/api/3`` - issue search uses opaque ``nextPageToken`` cursors
  and returns no total. The older ``/rest/api/3/search`` endpoint has been
  removed by Atlassian and answers ``410 Gone``, so we only ever call
  ``/rest/api/3/search/jql``, which returns no fields unless asked explicitly.
* Agile ``/rest/agile/1.0`` - boards and sprints still use
  ``startAt``/``maxResults``/``isLast``.

Endpoint paths live here as constants so a future Atlassian change is a
one-line edit rather than a search across the codebase.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import Any

import httpx

from .config import JiraConfig
from .errors import (
    AuthError,
    EndpointGoneError,
    InvalidQueryError,
    JiraApiError,
    NotFoundError,
    PaginationError,
    PermissionError_,
    TransientError,
)

SEARCH_JQL_ENDPOINT = "/rest/api/3/search/jql"
BOARD_ENDPOINT = "/rest/agile/1.0/board"
BOARD_SPRINT_ENDPOINT = "/rest/agile/1.0/board/{board_id}/sprint"
ISSUE_CHANGELOG_ENDPOINT = "/rest/api/3/issue/{issue_key}/changelog"
STATUS_ENDPOINT = "/rest/api/3/status"

DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BACKOFF_BASE_SECONDS = 0.5
DEFAULT_TIMEOUT_SECONDS = 30.0

SleepFn = Callable[[float], Awaitable[None]]


def _basic_auth_header(email: str, api_token: str) -> str:
    raw = f"{email}:{api_token}".encode()
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Parse Retry-After when it is a plain seconds count.

    HTTP-date form is ignored deliberately: falling back to our own backoff is
    safer than mis-parsing a date and hammering a rate-limited endpoint.
    """
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        seconds = float(raw.strip())
    except ValueError:
        return None
    return max(seconds, 0.0)


class JiraClient:
    """Authenticated access to the Jira Cloud REST APIs."""

    def __init__(
        self,
        config: JiraConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        sleep: SleepFn | None = None,
    ) -> None:
        self._config = config
        self._max_attempts = max(1, max_attempts)
        self._backoff_base = backoff_base_seconds
        self._sleep: SleepFn = sleep or asyncio.sleep
        self._http = httpx.AsyncClient(
            base_url=config.base_url,
            transport=transport,
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "Authorization": _basic_auth_header(config.email, config.api_token),
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    async def __aenter__(self) -> JiraClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _classify(self, response: httpx.Response, endpoint: str) -> JiraApiError:
        status = response.status_code
        detail = self._error_detail(response)
        suffix = f" ({detail})" if detail else ""

        if status == 401:
            return AuthError(
                "Jira rejected the credentials (401). Verify JIRA_EMAIL and "
                f"JIRA_API_TOKEN.{suffix}",
                status_code=status,
                endpoint=endpoint,
            )
        if status == 403:
            return PermissionError_(
                f"Permission denied by Jira (403) for {endpoint}. The account is "
                f"authenticated but lacks access.{suffix}",
                status_code=status,
                endpoint=endpoint,
            )
        if status == 404:
            return NotFoundError(
                f"Jira returned 404 for {endpoint}.{suffix}",
                status_code=status,
                endpoint=endpoint,
            )
        if status == 400:
            return InvalidQueryError(
                f"Jira rejected the request (400) to {endpoint}.{suffix}",
                status_code=status,
                endpoint=endpoint,
            )
        if status == 410:
            return EndpointGoneError(
                f"Jira responded 410 Gone: the endpoint {endpoint} has been "
                "removed by Atlassian and is no longer available."
                f"{suffix}",
                status_code=status,
                endpoint=endpoint,
            )
        if status == 429 or status >= 500:
            return TransientError(
                f"Jira returned {status} for {endpoint}.{suffix}",
                status_code=status,
                endpoint=endpoint,
            )
        return JiraApiError(
            f"Jira returned an unexpected {status} for {endpoint}.{suffix}",
            status_code=status,
            endpoint=endpoint,
        )

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        """Pull Jira's own error text out of the body, when there is one."""
        try:
            body = response.json()
        except Exception:
            return ""
        if isinstance(body, dict):
            messages = body.get("errorMessages")
            if isinstance(messages, list) and messages:
                return "; ".join(str(m) for m in messages)
            errors = body.get("errors")
            if isinstance(errors, dict) and errors:
                return "; ".join(f"{k}: {v}" for k, v in errors.items())
        return ""

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        last_error: JiraApiError | None = None

        for attempt in range(self._max_attempts):
            try:
                response = await self._http.request(
                    method, endpoint, params=params, json=json
                )
            except httpx.HTTPError as exc:
                last_error = TransientError(
                    f"Network failure calling {endpoint}: {exc}", endpoint=endpoint
                )
                await self._backoff(attempt, None)
                continue

            if response.is_success:
                if not response.content:
                    return {}
                return response.json()

            error = self._classify(response, endpoint)
            if not isinstance(error, TransientError):
                raise error

            last_error = error
            await self._backoff(attempt, _retry_after_seconds(response))

        assert last_error is not None
        raise TransientError(
            f"{last_error} Giving up after {self._max_attempts} attempts.",
            status_code=last_error.status_code,
            endpoint=endpoint,
        )

    async def _backoff(self, attempt: int, retry_after: float | None) -> None:
        """Wait before the next attempt, unless this was the final one."""
        if attempt >= self._max_attempts - 1:
            return
        delay = self._backoff_base * (2**attempt)
        if retry_after is not None:
            delay = max(delay, retry_after)
        await self._sleep(delay)

    # ------------------------------------------------------------------
    # Issue search (platform API, cursor pagination)
    # ------------------------------------------------------------------

    async def search_jql(
        self,
        jql: str,
        fields: Sequence[str],
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        """Run a JQL search, following ``nextPageToken`` to the end.

        ``fields`` is required, not optional: the enhanced search endpoint
        returns no fields at all unless they are named.
        """
        if not fields:
            raise ValueError(
                "search_jql requires an explicit fields list; the enhanced JQL "
                "endpoint returns no fields by default."
            )

        issues: list[dict[str, Any]] = []
        seen_tokens: set[str] = set()
        token: str | None = None

        while True:
            payload: dict[str, Any] = {
                "jql": jql,
                "fields": list(fields),
                "maxResults": page_size,
            }
            if token is not None:
                payload["nextPageToken"] = token

            body = await self._request("POST", SEARCH_JQL_ENDPOINT, json=payload)
            page = body.get("issues") or []
            issues.extend(page)

            next_token = body.get("nextPageToken")
            if not next_token or body.get("isLast") is True:
                return issues

            # Two ways Jira can hand back a cursor that never terminates. Both
            # would silently loop forever, so we refuse rather than spin.
            if next_token in seen_tokens:
                raise PaginationError(
                    "Jira issue search returned a repeated nextPageToken; "
                    "refusing to loop. Query: " + jql,
                    endpoint=SEARCH_JQL_ENDPOINT,
                )
            if not page:
                raise PaginationError(
                    "Jira issue search returned zero issues alongside a "
                    "nextPageToken; refusing to loop. Query: " + jql,
                    endpoint=SEARCH_JQL_ENDPOINT,
                )

            seen_tokens.add(next_token)
            token = next_token

    # ------------------------------------------------------------------
    # Agile API (startAt / maxResults / isLast pagination)
    # ------------------------------------------------------------------

    async def _paginate_agile(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        start_at = 0

        while True:
            page_params = dict(params or {})
            page_params.update({"startAt": start_at, "maxResults": page_size})
            body = await self._request("GET", endpoint, params=page_params)

            page = body.get("values") or []
            values.extend(page)

            if body.get("isLast") is True:
                return values

            total = body.get("total")
            if isinstance(total, int) and len(values) >= total:
                return values

            if not page:
                # No isLast, no total, and nothing came back - we are done.
                return values

            start_at += len(page)

    async def list_boards(self, *, name: str | None = None) -> list[dict[str, Any]]:
        params = {"name": name} if name else None
        return await self._paginate_agile(BOARD_ENDPOINT, params=params)

    async def list_sprints(self, board_id: int) -> list[dict[str, Any]]:
        return await self._paginate_agile(
            BOARD_SPRINT_ENDPOINT.format(board_id=board_id)
        )

    # ------------------------------------------------------------------
    # Changelog and statuses
    # ------------------------------------------------------------------

    async def get_changelog(self, issue_key: str) -> list[dict[str, Any]]:
        """Return an issue's full change history, oldest entry first."""
        endpoint = ISSUE_CHANGELOG_ENDPOINT.format(issue_key=issue_key)
        entries = await self._paginate_agile(endpoint)
        # Jira returns newest-first on some pages; sort so callers can rely on
        # order regardless. Entries without a timestamp sort to the front.
        return sorted(entries, key=lambda entry: entry.get("created") or "")

    async def get_statuses(self) -> dict[str, str]:
        """Map status id -> statusCategory key (``new``/``indeterminate``/``done``)."""
        body = await self._request("GET", STATUS_ENDPOINT)
        statuses: Iterable[Any] = body if isinstance(body, list) else body.get("values") or []

        mapping: dict[str, str] = {}
        for status in statuses:
            if not isinstance(status, dict):
                continue
            status_id = status.get("id")
            category = (status.get("statusCategory") or {}).get("key")
            if status_id is not None and category:
                mapping[str(status_id)] = str(category)
        return mapping
