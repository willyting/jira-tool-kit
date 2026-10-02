"""Work out what already exists and what needs creating. Read-only.

Matching is exact (outer whitespace trimmed, case-sensitive). JQL's
``summary ~`` is a tokenised text search that ignores punctuation, so it cannot
tell ``-------`` from ``------``; the sprint's issues are fetched and compared
here instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .checklist import SUBTASK_SUMMARIES, build_parent_summary
from .errors import ConfigError
from .targets import ReleaseTarget

SEARCH_FIELDS = ("summary", "subtasks")


@dataclass(frozen=True)
class PlanItem:
    summary: str
    # None means "to be created"; a key means it already exists.
    existing_key: str | None = None

    @property
    def needs_create(self) -> bool:
        return self.existing_key is None


@dataclass(frozen=True)
class Plan:
    target: ReleaseTarget
    parent: PlanItem
    subtasks: tuple[PlanItem, ...]

    @property
    def to_create(self) -> int:
        return int(self.parent.needs_create) + sum(
            1 for s in self.subtasks if s.needs_create
        )


def _summary_of(issue: dict[str, Any]) -> str:
    return str((issue.get("fields") or {}).get("summary") or "").strip()


async def build_plan(
    client: Any, target: ReleaseTarget, *, sprint_number: int, version: str
) -> Plan:
    parent_summary = build_parent_summary(sprint_number, version)

    candidates = await client.search_jql(
        f"sprint = {target.sprint_id} AND issuetype = {target.parent_type_id}",
        SEARCH_FIELDS,
    )
    matches = [c for c in candidates if _summary_of(c) == parent_summary]

    if len(matches) > 1:
        keys = ", ".join(str(m.get("key")) for m in matches)
        raise ConfigError(
            f"{len(matches)} issues in {target.sprint_name!r} are titled "
            f"{parent_summary!r} ({keys}). Remove the duplicates and re-run."
        )

    if not matches:
        return Plan(
            target=target,
            parent=PlanItem(parent_summary),
            subtasks=tuple(PlanItem(s) for s in SUBTASK_SUMMARIES),
        )

    parent = matches[0]
    # The subtasks field embeds each child's summary, so no second query.
    existing: dict[str, str] = {}
    for child in (parent.get("fields") or {}).get("subtasks") or []:
        existing.setdefault(_summary_of(child), str(child.get("key")))

    return Plan(
        target=target,
        parent=PlanItem(parent_summary, existing_key=str(parent["key"])),
        subtasks=tuple(PlanItem(s, existing.get(s)) for s in SUBTASK_SUMMARIES),
    )
