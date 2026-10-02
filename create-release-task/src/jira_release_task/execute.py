"""Carry out a Plan: create parent, put it in the sprint, create subtasks.

Stops at the first failure and never deletes anything. Because planning is
idempotent, re-running the same command picks up where this left off.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import JiraToolError, PartialWriteError
from .plan import Plan


@dataclass(frozen=True)
class ResultItem:
    key: str
    summary: str
    created: bool


@dataclass(frozen=True)
class RunResult:
    parent: ResultItem
    subtasks: tuple[ResultItem, ...]

    @property
    def created_count(self) -> int:
        items = (self.parent, *self.subtasks)
        return sum(1 for i in items if i.created)


async def execute_plan(client: Any, plan: Plan) -> RunResult:
    target = plan.target
    created: list[ResultItem] = []

    if plan.parent.existing_key is not None:
        parent = ResultItem(plan.parent.existing_key, plan.parent.summary, False)
    else:
        try:
            made = await client.create_issue(
                target.project_key, target.parent_type_id, plan.parent.summary
            )
        except JiraToolError as exc:
            raise PartialWriteError(str(exc), created=[], cause=exc) from exc
        parent = ResultItem(made["key"], plan.parent.summary, True)
        created.append(parent)

        # Immediately, before any subtask: a parent outside the sprint is
        # invisible to the next run's search, so keep that window small.
        try:
            await client.add_issues_to_sprint(target.sprint_id, [parent.key])
        except JiraToolError as exc:
            raise PartialWriteError(
                f"Created {parent.key} but could not add it to "
                f"{target.sprint_name!r}: {exc} {parent.key} is now outside the "
                f"sprint; move it into {target.sprint_name!r} (or delete it) "
                "before re-running, or a duplicate will be created.",
                created=created,
                cause=exc,
            ) from exc

    subtasks: list[ResultItem] = []
    for item in plan.subtasks:
        if item.existing_key is not None:
            subtasks.append(ResultItem(item.existing_key, item.summary, False))
            continue
        try:
            made = await client.create_issue(
                target.project_key,
                target.subtask_type_id,
                item.summary,
                parent_key=parent.key,
            )
        except JiraToolError as exc:
            raise PartialWriteError(
                f"Failed creating subtask {item.summary!r}: {exc} Re-run the "
                "same command to create the remaining subtasks.",
                created=created,
                cause=exc,
            ) from exc
        result = ResultItem(made["key"], item.summary, True)
        created.append(result)
        subtasks.append(result)

    return RunResult(parent=parent, subtasks=tuple(subtasks))
