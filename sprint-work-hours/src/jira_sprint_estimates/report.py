"""Render the summary and the per-issue table.

Rows are grouped so each parent sits directly above its completed subtasks -
that is the shape in which the leaf-preferring rule makes sense to a reader,
because the excluded parent estimate appears immediately above the children
that replaced it.
"""

from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from .aggregate import Aggregate, LineItem, format_hours
from .issues import CandidateSet
from .sprints import Sprint

SUMMARY_TRUNCATE_WIDTH = 48
UNASSIGNED = "Unassigned"
EXCLUDED_MARKER = "rolled up"


def truncate(text: str, width: int = SUMMARY_TRUNCATE_WIDTH) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1].rstrip() + "…"


def format_timestamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M")


def group_line_items(line_items: list[LineItem]) -> list[LineItem]:
    """Order as parent-then-children, groups by earliest completion."""
    by_key = {item.key: item for item in line_items}

    # A row's group is its parent when that parent also completed; otherwise
    # the row heads its own group.
    def group_of(item: LineItem) -> str:
        parent = item.completion.issue.parent_key
        if parent and parent in by_key:
            return parent
        return item.key

    groups: dict[str, list[LineItem]] = {}
    for item in line_items:
        groups.setdefault(group_of(item), []).append(item)

    def group_sort_key(entry: tuple[str, list[LineItem]]) -> tuple[datetime, str]:
        key, members = entry
        earliest = min(m.completion.completed_at for m in members)
        return earliest, key

    ordered: list[LineItem] = []
    for key, members in sorted(groups.items(), key=group_sort_key):
        head = [m for m in members if m.key == key]
        children = sorted(
            (m for m in members if m.key != key),
            key=lambda m: (m.completion.completed_at, m.key),
        )
        ordered.extend(head + children)
    return ordered


def build_table(result: Aggregate) -> Table:
    table = Table(title="Completed during sprint", title_justify="left")
    table.add_column("Key", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Sub?", justify="center", no_wrap=True)
    table.add_column("Summary")
    table.add_column("Assignee", no_wrap=True)
    table.add_column("Completed (UTC)", no_wrap=True)
    table.add_column("Estimate", justify="right", no_wrap=True)

    for item in group_line_items(result.line_items):
        issue = item.completion.issue

        if item.rolled_up_excluded:
            estimate = f"({format_hours(item.own_estimate_seconds)} {EXCLUDED_MARKER})"
        else:
            estimate = format_hours(item.own_estimate_seconds)

        # Jira text is escaped before it reaches rich: a summary like
        # "[URGENT] fix login" would otherwise be parsed as console markup and
        # the bracketed part silently dropped.
        summary = escape(truncate(issue.summary))
        if item.completion.reopened:
            summary = f"{summary} (reopened)"

        table.add_row(
            escape(issue.key),
            escape(issue.issue_type),
            "yes" if issue.is_subtask else "",
            summary,
            escape(issue.assignee or UNASSIGNED),
            format_timestamp(item.completion.completed_at),
            estimate,
        )

    return table


def render(
    console: Console,
    sprint: Sprint,
    result: Aggregate,
    *,
    candidates: CandidateSet | None = None,
    skipped: list[tuple[str, str]] | None = None,
    verbose: bool = False,
) -> None:
    skipped = skipped or []

    console.print(f"Sprint: {escape(sprint.name)} (id {sprint.id})")
    console.print(
        f"Window: {format_timestamp(sprint.start)} to "
        f"{format_timestamp(sprint.end)} UTC"
    )
    if sprint.is_active:
        console.print(
            "Sprint is still in progress; the window ends at the current time, "
            "so this total will change."
        )

    if not result.line_items:
        console.print("")
        console.print("Total original estimate: 0h")
        console.print("No issues transitioned to Done during this sprint window.")
        _print_skipped(console, skipped)
        return

    console.print("")
    console.print(build_table(result))
    console.print("")
    console.print(f"Total original estimate: {format_hours(result.total_seconds)}")
    console.print(
        f"Completed: {len(result.line_items)} issues "
        f"({result.task_count} tasks, {result.subtask_count} subtasks)"
    )

    if result.excluded_parent_count:
        console.print(
            f"Excluded from the total: {result.excluded_parent_count} parent "
            f"estimate(s) superseded by completed subtasks ({EXCLUDED_MARKER})."
        )
    if result.unestimated_count:
        console.print(
            f"Unestimated: {result.unestimated_count} completed issue(s) had no "
            "original estimate and contributed 0h."
        )

    _print_skipped(console, skipped)

    if verbose and candidates is not None and candidates.discrepancies:
        console.print(
            "Declared subtasks never returned by the parent query: "
            + escape(", ".join(candidates.discrepancies))
        )


def _print_skipped(console: Console, skipped: list[tuple[str, str]]) -> None:
    if not skipped:
        return
    console.print(
        f"Skipped: {len(skipped)} issue(s) whose changelog could not be read, "
        "so the total may be understated."
    )
    for key, reason in skipped:
        console.print(f"  {escape(key)}: {escape(reason)}")
