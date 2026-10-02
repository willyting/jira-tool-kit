"""Thin async Jira Cloud client.

Two API families are in play and they paginate differently:

* Platform ``/rest/api/3`` - issue search uses opaque ``nextPageToken`` cursors
  and returns no total. The older ``/rest/api/3/search`` endpoint has been
  removed by Atlassian and answers ``410 Gone``, so we only ever call
  ``/rest/api/3/search/jql``, which returns no fields unless asked explicitly.
* Agile ``/rest/agile/1.0`` - boards and sprints still use
  ``startAt``/``maxResults``/``isLast``.

Reads and writes are retried differently. A read can always be repeated. A
write that failed on a network error or 5xx may still have been committed, so
repeating it risks a duplicate issue; only 429 (which Jira guarantees was not
processed) is retried for writes.

Endpoint paths live here as constants so a future Atlassian change is a
one-line edit rather than a search across the codebase.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable, Sequence
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
    WriteUncertainError,
)

SEARCH_JQL_ENDPOINT = "/rest/api/3/search/jql"
ISSUE_ENDPOINT = "/rest/api/3/issue"
CREATEMETA_ISSUETYPES_ENDPOINT = "/rest/api/3/issue/createmeta/{project}/issuetypes"
BOARD_ENDPOINT = "/rest/agile/1.0/board"
BOARD_DETAIL_ENDPOINT = "/rest/agile/1.0/board/{board_id}"
BOARD_PROJECT_ENDPOINT = "/rest/agile/1.0/board/{board_id}/project"
BOARD_SPRINT_ENDPOINT = "/rest/agile/1.0/board/{board_id}/sprint"
SPRINT_ISSUE_ENDPOINT = "/rest/agile/1.0/sprint/{sprint_id}/issue"

DEFAULT_PAGE_SIZE = 50
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BACKOFF_BASE_SECONDS = 0.5
DEFAULT_TIMEOUT_SECONDS = 30.0

CREATE_PERMISSION_HINT = (
    "The account lacks the 'Create Issues' permission on the project."
)
SCHEDULE_PERMISSION_HINT = (
    "The account lacks the 'Schedule Issues' permission needed to move issues "
    "into a sprint."
)

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

    @property
    def base_url(self) -> str:
        return self._config.base_url

    async def __aenter__(self) -> JiraClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _classify(
        self,
        response: httpx.Response,
        endpoint: str,
        *,
        permission_hint: str | None = None,
    ) -> JiraApiError:
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
            hint = permission_hint or "The account is authenticated but lacks access."
            return PermissionError_(
                f"Permission denied by Jira (403) for {endpoint}. {hint}{suffix}",
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
            parts: list[str] = []
            messages = body.get("errorMessages")
            if isinstance(messages, list):
                parts.extend(str(m) for m in messages)
            errors = body.get("errors")
            if isinstance(errors, dict):
                parts.extend(f"{k}: {v}" for k, v in errors.items())
            return "; ".join(parts)
        return ""

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        is_write: bool = False,
        permission_hint: str | None = None,
    ) -> Any:
        last_error: JiraApiError | None = None

        for attempt in range(self._max_attempts):
            try:
                response = await self._http.request(
                    method, endpoint, params=params, json=json
                )
            except httpx.HTTPError as exc:
                if is_write:
                    raise WriteUncertainError(
                        f"Network failure calling {endpoint}: {exc}. The change "
                        "may or may not have been applied in Jira; check before "
                        "re-running.",
                        endpoint=endpoint,
                    ) from exc
                last_error = TransientError(
                    f"Network failure calling {endpoint}: {exc}", endpoint=endpoint
                )
                await self._backoff(attempt, None)
                continue

            if response.is_success:
                if not response.content:
                    return {}
                return response.json()

            error = self._classify(
                response, endpoint, permission_hint=permission_hint
            )
            if not isinstance(error, TransientError):
                raise error

            if is_write and response.status_code != 429:
                raise WriteUncertainError(
                    f"{error} The change may or may not have been applied in "
                    "Jira; check before re-running.",
                    status_code=response.status_code,
                    endpoint=endpoint,
                )

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
    # startAt / maxResults pagination (Agile API and createmeta)
    # ------------------------------------------------------------------

    async def _paginate(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        items_key: str = "values",
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        start_at = 0

        while True:
            page_params = dict(params or {})
            page_params.update({"startAt": start_at, "maxResults": page_size})
            body = await self._request("GET", endpoint, params=page_params)

            page = body.get(items_key) or []
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
        return await self._paginate(BOARD_ENDPOINT, params=params)

    async def get_board(self, board_id: int) -> dict[str, Any]:
        return await self._request(
            "GET", BOARD_DETAIL_ENDPOINT.format(board_id=board_id)
        )

    async def list_board_projects(self, board_id: int) -> list[dict[str, Any]]:
        return await self._paginate(BOARD_PROJECT_ENDPOINT.format(board_id=board_id))

    async def list_sprints(
        self, board_id: int, *, state: str | None = None
    ) -> list[dict[str, Any]]:
        params = {"state": state} if state else None
        return await self._paginate(
            BOARD_SPRINT_ENDPOINT.format(board_id=board_id), params=params
        )

    async def get_create_issue_types(self, project_key: str) -> list[dict[str, Any]]:
        """Issue types creatable in a project, each with ``id``/``name``/``subtask``."""
        return await self._paginate(
            CREATEMETA_ISSUETYPES_ENDPOINT.format(project=project_key),
            items_key="issueTypes",
        )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def create_issue(
        self,
        project_key: str,
        issue_type_id: str,
        summary: str,
        *,
        parent_key: str | None = None,
    ) -> dict[str, str]:
        """Create one issue and return its ``key`` and ``id``."""
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "issuetype": {"id": issue_type_id},
            "summary": summary,
        }
        if parent_key is not None:
            fields["parent"] = {"key": parent_key}

        body = await self._request(
            "POST",
            ISSUE_ENDPOINT,
            json={"fields": fields},
            is_write=True,
            permission_hint=CREATE_PERMISSION_HINT,
        )
        return {"key": str(body["key"]), "id": str(body["id"])}

    async def add_issues_to_sprint(self, sprint_id: int, keys: Sequence[str]) -> None:
        """Move issues into a sprint. Jira answers 204 No Content on success."""
        await self._request(
            "POST",
            SPRINT_ISSUE_ENDPOINT.format(sprint_id=sprint_id),
            json={"issues": list(keys)},
            is_write=True,
            permission_hint=SCHEDULE_PERMISSION_HINT,
        )
