"""Shared builders and a stub client.

The real JiraClient is exercised over HTTP in test_client.py. Everything above
the transport layer is tested against FakeClient, which keeps an in-memory
Jira so a second run sees what the first one created.
"""

from __future__ import annotations

from typing import Any

from jira_release_task.errors import JiraToolError
from jira_release_task.targets import ReleaseTarget

BOARD = {
    "id": 12,
    "name": "VOR board",
    "type": "scrum",
    "location": {"projectKey": "VOR"},
}
TASK_TYPE = {"id": "10002", "name": "Task", "subtask": False}
SUBTASK_TYPE = {"id": "10003", "name": "Sub-task", "subtask": True}
STORY_TYPE = {"id": "10001", "name": "Story", "subtask": False}
SPRINT_97 = {
    "id": 501,
    "name": "reseller 97",
    "state": "future",
    "startDate": None,
}

TARGET = ReleaseTarget(
    board_id=12,
    board_name="VOR board",
    sprint_id=501,
    sprint_name="reseller 97",
    project_key="VOR",
    parent_type_id="10002",
    parent_type_name="Task",
    subtask_type_id="10003",
    subtask_type_name="Sub-task",
)


class FakeClient:
    """Stands in for JiraClient above the transport layer."""

    base_url = "https://jira.example.test"

    def __init__(
        self,
        *,
        boards: list[dict[str, Any]] | None = None,
        sprints: list[dict[str, Any]] | None = None,
        board_projects: list[dict[str, Any]] | None = None,
        issue_types: list[dict[str, Any]] | None = None,
        fail_create_on: int | None = None,
        fail_sprint_add: bool = False,
    ) -> None:
        self._boards = boards if boards is not None else [BOARD]
        self._sprints = sprints if sprints is not None else [SPRINT_97]
        self._board_projects = board_projects or []
        self._issue_types = (
            issue_types if issue_types is not None else [STORY_TYPE, TASK_TYPE, SUBTASK_TYPE]
        )
        # 1-based index of the create_issue call that should fail.
        self._fail_create_on = fail_create_on
        self._fail_sprint_add = fail_sprint_add

        self._next = 100
        # key -> {summary, type_id, parent, sprint}
        self.issues: dict[str, dict[str, Any]] = {}
        self.create_calls: list[dict[str, Any]] = []
        self.sprint_adds: list[tuple[int, list[str]]] = []
        self.jql_queries: list[str] = []
        self.sprint_state_requests: list[str | None] = []

    # -- seeding -------------------------------------------------------

    def seed(
        self,
        summary: str,
        *,
        type_id: str = "10002",
        parent: str | None = None,
        sprint: int | None = 501,
    ) -> str:
        self._next += 1
        key = f"VOR-{self._next}"
        self.issues[key] = {
            "summary": summary,
            "type_id": type_id,
            "parent": parent,
            "sprint": sprint,
        }
        return key

    # -- reads ---------------------------------------------------------

    async def list_boards(self, *, name: str | None = None) -> list[dict[str, Any]]:
        # Jira's name filter is a substring match; mimic that.
        return [b for b in self._boards if name is None or name in b["name"]]

    async def get_board(self, board_id: int) -> dict[str, Any]:
        for b in self._boards:
            if int(b["id"]) == board_id:
                return dict(b)
        raise JiraToolError(f"board {board_id} not found")

    async def list_board_projects(self, board_id: int) -> list[dict[str, Any]]:
        return list(self._board_projects)

    async def list_sprints(
        self, board_id: int, *, state: str | None = None
    ) -> list[dict[str, Any]]:
        self.sprint_state_requests.append(state)
        wanted = set(state.split(",")) if state else None
        return [s for s in self._sprints if wanted is None or s["state"] in wanted]

    async def get_create_issue_types(self, project_key: str) -> list[dict[str, Any]]:
        return list(self._issue_types)

    async def search_jql(self, jql: str, fields, **kwargs) -> list[dict[str, Any]]:
        assert fields, "fields must always be explicit"
        self.jql_queries.append(jql)
        # Only the plan's query shape is supported.
        sprint_part, type_part = jql.split(" AND ")
        sprint_id = int(sprint_part.split("=")[1])
        type_id = type_part.split("=")[1].strip()
        results = []
        for key, issue in self.issues.items():
            if issue["sprint"] != sprint_id or issue["type_id"] != type_id:
                continue
            children = [
                {"key": k, "fields": {"summary": c["summary"]}}
                for k, c in self.issues.items()
                if c["parent"] == key
            ]
            results.append(
                {"key": key, "fields": {"summary": issue["summary"], "subtasks": children}}
            )
        return results

    # -- writes --------------------------------------------------------

    async def create_issue(
        self,
        project_key: str,
        issue_type_id: str,
        summary: str,
        *,
        parent_key: str | None = None,
    ) -> dict[str, str]:
        self.create_calls.append(
            {
                "project": project_key,
                "type_id": issue_type_id,
                "summary": summary,
                "parent": parent_key,
            }
        )
        if self._fail_create_on == len(self.create_calls):
            raise JiraToolError("boom")
        # Subtasks follow their parent's sprint, as in Jira.
        sprint = self.issues[parent_key]["sprint"] if parent_key else None
        key = self.seed(summary, type_id=issue_type_id, parent=parent_key, sprint=sprint)
        return {"key": key, "id": key.split("-")[1]}

    async def add_issues_to_sprint(self, sprint_id: int, keys) -> None:
        self.sprint_adds.append((sprint_id, list(keys)))
        if self._fail_sprint_add:
            raise JiraToolError("sprint add denied")
        for key in keys:
            self.issues[key]["sprint"] = sprint_id

    @property
    def write_count(self) -> int:
        return len(self.create_calls) + len(self.sprint_adds)

    async def aclose(self) -> None:
        return None
