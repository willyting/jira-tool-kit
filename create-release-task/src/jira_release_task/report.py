"""Console output: the plan before writing, the result after."""

from __future__ import annotations

from collections.abc import Sequence

from rich.console import Console
from rich.markup import escape

from .execute import ResultItem, RunResult
from .plan import Plan, PlanItem


def _plan_status(item: PlanItem) -> str:
    return "create" if item.needs_create else f"existing {item.existing_key}"


def render_plan(console: Console, plan: Plan) -> None:
    t = plan.target
    console.print(f"Board:   {escape(t.board_name)} (id {t.board_id})")
    console.print(f"Sprint:  {escape(t.sprint_name)} (id {t.sprint_id})")
    console.print(f"Project: {t.project_key}")
    console.print()
    console.print(
        f"[{_plan_status(plan.parent)}] {plan.parent.summary}",
        markup=False,
    )
    for item in plan.subtasks:
        console.print(f"    [{_plan_status(item)}] {item.summary}", markup=False)
    console.print()


def browse_url(base_url: str, key: str) -> str:
    return f"{base_url.rstrip('/')}/browse/{key}"


def _result_line(item: ResultItem, base_url: str, indent: str) -> str:
    status = "created" if item.created else "existing"
    return (
        f"{indent}{item.key}  {status:<8}  {item.summary}  "
        f"{browse_url(base_url, item.key)}"
    )


def render_result(
    console: Console, result: RunResult, base_url: str, sprint_name: str
) -> None:
    console.print(_result_line(result.parent, base_url, ""), markup=False, soft_wrap=True)
    for item in result.subtasks:
        console.print(_result_line(item, base_url, "    "), markup=False, soft_wrap=True)
    console.print()
    console.print(f"Created {result.created_count} issues in {sprint_name}.", markup=False)


def render_created(
    console: Console, created: Sequence[ResultItem], base_url: str
) -> None:
    """What exists after a partial failure, shown before the error line."""
    if not created:
        console.print("No issues were created.")
        return
    console.print("Created before the failure:")
    for item in created:
        console.print(_result_line(item, base_url, "    "), markup=False, soft_wrap=True)
