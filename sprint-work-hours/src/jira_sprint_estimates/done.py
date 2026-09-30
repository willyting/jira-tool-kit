"""Decide, from an issue's changelog, whether it was completed this sprint.

An issue qualifies when its history contains a status transition that *enters*
the done category inside the sprint window. Two consequences worth stating,
because they are the whole point of reading the changelog rather than the
current status:

* An issue that currently reads ``Done`` does not qualify if it got there
  before the sprint started.
* An issue that was completed mid-sprint and later reopened still qualifies -
  the work happened - and is flagged so the number can be judged.

"Done" is decided by Jira's status *category*, never by status name, so custom
workflow statuses like ``Released`` are handled without a hardcoded name list.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .errors import JiraToolError
from .issues import Issue
from .sprints import Sprint, in_window, parse_jira_datetime

DONE_CATEGORY = "done"
MAX_CONCURRENT_CHANGELOG_REQUESTS = 8


class SupportsChangelog(Protocol):
    async def get_changelog(self, issue_key: str) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class Completion:
    """An issue that entered the done category during the sprint window."""

    issue: Issue
    completed_at: datetime
    reopened: bool


@dataclass
class DetectionResult:
    completions: list[Completion]
    # Issues whose changelog could not be read. Reported, never silently
    # dropped: an unreadable history looks exactly like "never completed".
    skipped: list[tuple[str, str]]


def _status_items(entry: dict[str, Any]) -> list[dict[str, Any]]:
    items = entry.get("items") or []
    return [
        item
        for item in items
        if isinstance(item, dict)
        and str(item.get("field") or item.get("fieldId") or "").lower() == "status"
    ]


def _category_of(status_id: Any, categories: dict[str, str]) -> str | None:
    if status_id is None:
        return None
    return categories.get(str(status_id))


def classify_changelog(
    changelog: list[dict[str, Any]],
    categories: dict[str, str],
    sprint: Sprint,
) -> tuple[datetime | None, bool]:
    """Return (earliest qualifying completion, whether it was later reopened).

    A qualifying transition has a destination in the done category, a source
    that is *not* in the done category, and a timestamp inside the window.
    Requiring the source to be outside done is what stops a done-to-done move
    (say ``Done`` -> ``Released``) from counting as fresh completion.
    """
    start, end = sprint.window
    completed_at: datetime | None = None
    reopened = False

    for entry in sorted(changelog, key=lambda e: str(e.get("created") or "")):
        moment = parse_jira_datetime(entry.get("created"))
        if moment is None:
            continue

        for item in _status_items(entry):
            to_category = _category_of(item.get("to"), categories)
            from_category = _category_of(item.get("from"), categories)

            entering_done = (
                to_category == DONE_CATEGORY and from_category != DONE_CATEGORY
            )
            leaving_done = (
                from_category == DONE_CATEGORY and to_category != DONE_CATEGORY
            )

            if entering_done and in_window(moment, start, end):
                if completed_at is None:
                    # Earliest qualifying transition wins; a second pass into
                    # done does not count the issue twice.
                    completed_at = moment
                    reopened = False
            elif leaving_done and completed_at is not None and in_window(moment, start, end):
                reopened = True

    return completed_at, reopened


async def detect_completions(
    client: SupportsChangelog,
    issues: list[Issue],
    categories: dict[str, str],
    sprint: Sprint,
    *,
    max_concurrency: int = MAX_CONCURRENT_CHANGELOG_REQUESTS,
    on_progress: Any = None,
) -> DetectionResult:
    """Fetch every candidate's changelog and keep the ones that qualify."""
    if not issues:
        return DetectionResult(completions=[], skipped=[])

    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def inspect(issue: Issue) -> tuple[Issue, Completion | None, str | None]:
        async with semaphore:
            try:
                changelog = await client.get_changelog(issue.key)
            except (JiraToolError, OSError) as exc:
                return issue, None, str(exc)

        if on_progress is not None:
            on_progress(issue.key)

        completed_at, reopened = classify_changelog(changelog, categories, sprint)
        if completed_at is None:
            return issue, None, None
        return (
            issue,
            Completion(issue=issue, completed_at=completed_at, reopened=reopened),
            None,
        )

    outcomes = await asyncio.gather(*(inspect(issue) for issue in issues))

    completions = [c for _, c, _ in outcomes if c is not None]
    skipped = [(i.key, reason) for i, _, reason in outcomes if reason is not None]

    completions.sort(key=lambda c: (c.completed_at, c.issue.key))
    skipped.sort()

    return DetectionResult(completions=completions, skipped=skipped)
