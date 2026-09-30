"""Build the candidate issue set for a sprint.

Jira stores sprint membership on the *parent*, so ``sprint = <id>`` does not
reliably return subtasks. The set is therefore assembled in two phases:

1. ``sprint = <id>``           - the sprint's own members.
2. ``parent in (K1, K2, ...)`` - every subtask of those members, batched.

The union is deduplicated by issue key. Fetching subtasks by parent in batches
of 50 costs a handful of requests, where walking each parent's ``subtasks``
array one issue at a time would cost one request per subtask.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .client import JiraClient

# The enhanced JQL endpoint returns nothing unless fields are named explicitly.
ISSUE_FIELDS = [
    "summary",
    "issuetype",
    "status",
    "parent",
    "assignee",
    "timeoriginalestimate",
    "subtasks",
]

PARENT_BATCH_SIZE = 50


@dataclass(frozen=True)
class Issue:
    """One candidate issue, flattened out of Jira's nested field shape."""

    key: str
    summary: str
    issue_type: str
    is_subtask: bool
    parent_key: str | None
    assignee: str | None
    original_estimate_seconds: int | None
    status_name: str
    status_id: str | None


@dataclass
class CandidateSet:
    """The deduplicated candidate issues, plus anything that looked off."""

    issues: list[Issue] = field(default_factory=list)
    # Subtask keys a parent declared that the parent query did not return.
    # Surfaced under --verbose rather than dropped silently.
    discrepancies: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.issues)

    @property
    def keys(self) -> list[str]:
        return [issue.key for issue in self.issues]


def parse_issue(raw: dict[str, Any]) -> Issue:
    fields = raw.get("fields") or {}
    issue_type = fields.get("issuetype") or {}
    parent = fields.get("parent") or {}
    assignee = fields.get("assignee") or {}
    status = fields.get("status") or {}

    estimate = fields.get("timeoriginalestimate")
    estimate_seconds = int(estimate) if isinstance(estimate, (int, float)) else None

    return Issue(
        key=str(raw.get("key", "")),
        summary=str(fields.get("summary") or ""),
        issue_type=str(issue_type.get("name") or "Unknown"),
        is_subtask=bool(issue_type.get("subtask", False)),
        parent_key=str(parent["key"]) if parent.get("key") else None,
        assignee=assignee.get("displayName") or None,
        original_estimate_seconds=estimate_seconds,
        status_name=str(status.get("name") or "Unknown"),
        status_id=str(status["id"]) if status.get("id") else None,
    )


def _declared_subtask_keys(raw_issues: list[dict[str, Any]]) -> set[str]:
    declared: set[str] = set()
    for raw in raw_issues:
        for subtask in (raw.get("fields") or {}).get("subtasks") or []:
            key = subtask.get("key")
            if key:
                declared.add(str(key))
    return declared


def _batched(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def fetch_candidate_issues(
    client: JiraClient, sprint_id: int
) -> CandidateSet:
    """Return every issue that could plausibly have been completed this sprint."""
    sprint_issues = await client.search_jql(
        f"sprint = {sprint_id}", ISSUE_FIELDS
    )

    if not sprint_issues:
        # An empty sprint is a legitimate answer, not an error.
        return CandidateSet()

    by_key: dict[str, dict[str, Any]] = {
        str(raw.get("key")): raw for raw in sprint_issues if raw.get("key")
    }

    # Only non-subtasks can have children worth querying for.
    parent_keys = [
        key
        for key, raw in by_key.items()
        if not ((raw.get("fields") or {}).get("issuetype") or {}).get("subtask", False)
    ]

    for batch in _batched(parent_keys, PARENT_BATCH_SIZE):
        listed = ", ".join(batch)
        children = await client.search_jql(
            f"parent in ({listed})", ISSUE_FIELDS
        )
        for raw in children:
            key = raw.get("key")
            if key:
                # Dedup: an issue that is both a sprint member and a child of
                # another member appears once.
                by_key.setdefault(str(key), raw)

    declared = _declared_subtask_keys(sprint_issues)
    discrepancies = sorted(declared - set(by_key))

    return CandidateSet(
        issues=[parse_issue(raw) for raw in by_key.values()],
        discrepancies=discrepancies,
    )
