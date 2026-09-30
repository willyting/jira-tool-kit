"""Shared builders and a stub client.

The real JiraClient is exercised over HTTP in test_client.py. Everything above
the transport layer is tested against this stub so the logic under test is the
only thing that can fail.
"""

from __future__ import annotations

from typing import Any

DONE_STATUS_ID = "10001"
DONE_STATUS_NAME = "Done"
IN_PROGRESS_STATUS_ID = "3"
IN_PROGRESS_STATUS_NAME = "In Progress"
TODO_STATUS_ID = "10000"
TODO_STATUS_NAME = "To Do"
RELEASED_STATUS_ID = "10005"
RELEASED_STATUS_NAME = "Released"
CLOSED_STATUS_ID = "6"
CLOSED_STATUS_NAME = "Closed"

STATUS_CATEGORIES = {
    TODO_STATUS_ID: "new",
    IN_PROGRESS_STATUS_ID: "indeterminate",
    DONE_STATUS_ID: "done",
    RELEASED_STATUS_ID: "done",
    CLOSED_STATUS_ID: "done",
}


def raw_issue(
    key: str,
    *,
    summary: str | None = None,
    issue_type: str = "Task",
    is_subtask: bool = False,
    parent: str | None = None,
    assignee: str | None = "Ada Lovelace",
    estimate_seconds: int | None = 3600,
    status_id: str = TODO_STATUS_ID,
    status_name: str = TODO_STATUS_NAME,
    subtasks: list[str] | None = None,
) -> dict[str, Any]:
    """Build a Jira search result in the shape the API actually returns."""
    fields: dict[str, Any] = {
        "summary": summary if summary is not None else f"Summary for {key}",
        "issuetype": {"name": issue_type, "subtask": is_subtask},
        "status": {"id": status_id, "name": status_name},
        "timeoriginalestimate": estimate_seconds,
        "subtasks": [{"key": k} for k in (subtasks or [])],
    }
    if parent:
        fields["parent"] = {"key": parent}
    if assignee:
        fields["assignee"] = {"displayName": assignee}
    else:
        fields["assignee"] = None

    return {"key": key, "fields": fields}


def changelog_entry(created: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"created": created, "items": items}


def status_change(
    created: str,
    *,
    from_id: str,
    to_id: str,
    from_name: str = "",
    to_name: str = "",
) -> dict[str, Any]:
    return changelog_entry(
        created,
        [
            {
                "field": "status",
                "fieldId": "status",
                "from": from_id,
                "fromString": from_name,
                "to": to_id,
                "toString": to_name,
            }
        ],
    )


class FakeClient:
    """Stands in for JiraClient above the transport layer."""

    def __init__(
        self,
        *,
        sprint_issues: list[dict[str, Any]] | None = None,
        child_issues: dict[str, list[dict[str, Any]]] | None = None,
        changelogs: dict[str, list[dict[str, Any]]] | None = None,
        statuses: dict[str, str] | None = None,
        sprints: list[dict[str, Any]] | None = None,
        boards: list[dict[str, Any]] | None = None,
        changelog_errors: dict[str, Exception] | None = None,
    ) -> None:
        self._sprint_issues = sprint_issues or []
        # Maps a single parent key -> its children, so a batched query can be
        # answered by unioning the keys it names.
        self._child_issues = child_issues or {}
        self._changelogs = changelogs or {}
        self._statuses = statuses if statuses is not None else dict(STATUS_CATEGORIES)
        self._sprints = sprints or []
        self._boards = boards or []
        self._changelog_errors = changelog_errors or {}

        self.jql_queries: list[str] = []
        self.changelog_requests: list[str] = []

    async def search_jql(self, jql: str, fields, **kwargs) -> list[dict[str, Any]]:
        assert fields, "fields must always be explicit"
        self.jql_queries.append(jql)

        if jql.startswith("sprint ="):
            return list(self._sprint_issues)

        if jql.startswith("parent in ("):
            listed = jql[len("parent in (") : -1]
            keys = [k.strip() for k in listed.split(",") if k.strip()]
            results: list[dict[str, Any]] = []
            for key in keys:
                results.extend(self._child_issues.get(key, []))
            return results

        raise AssertionError(f"unexpected JQL: {jql}")

    async def get_changelog(self, issue_key: str) -> list[dict[str, Any]]:
        self.changelog_requests.append(issue_key)
        if issue_key in self._changelog_errors:
            raise self._changelog_errors[issue_key]
        return list(self._changelogs.get(issue_key, []))

    async def get_statuses(self) -> dict[str, str]:
        return dict(self._statuses)

    async def list_sprints(self, board_id: int) -> list[dict[str, Any]]:
        return list(self._sprints)

    async def list_boards(self, *, name: str | None = None) -> list[dict[str, Any]]:
        if name is None:
            return list(self._boards)
        return [b for b in self._boards if b.get("name") == name]

    async def aclose(self) -> None:
        return None

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None
