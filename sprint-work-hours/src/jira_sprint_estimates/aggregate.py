"""Roll completed issues up into a total, without double-counting.

Teams commonly estimate a parent *and* its subtasks, where the parent's figure
is a roll-up of the children. Summing both inflates the sprint total, so the
rule here is leaf-preferring: when a completed parent has completed children,
only the children count.

The parent's own estimate is not discarded - it is kept on the record and
marked excluded, so the report can show the gap. A total that silently differs
from the sum of its visible rows is a total nobody trusts.

All arithmetic stays in integer seconds. Hours exist only for display, which is
why the conversion helper lives here but is called from the report layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from .done import Completion

SECONDS_PER_HOUR = 3600


@dataclass(frozen=True)
class LineItem:
    """One completed issue as it will appear in the report."""

    completion: Completion
    # The issue's own estimate, whether or not it counts toward the total.
    own_estimate_seconds: int | None
    # What this row actually contributes. Zero when excluded or unestimated.
    counted_seconds: int
    rolled_up_excluded: bool

    @property
    def key(self) -> str:
        return self.completion.issue.key

    @property
    def is_unestimated(self) -> bool:
        return self.own_estimate_seconds is None


@dataclass
class Aggregate:
    line_items: list[LineItem]
    total_seconds: int
    task_count: int
    subtask_count: int
    unestimated_count: int
    excluded_parent_count: int

    @property
    def total_hours(self) -> float:
        return to_hours(self.total_seconds)


def to_hours(seconds: int) -> float:
    """Convert to hours for display, rounded to two decimal places.

    Callers sum in seconds and convert once, so repeated rounding cannot drift
    the total.
    """
    return round(seconds / SECONDS_PER_HOUR, 2)


def format_hours(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    return f"{to_hours(seconds)}h"


def aggregate(completions: list[Completion]) -> Aggregate:
    """Apply leaf-preferring rules over the completed set."""
    completed_keys = {c.issue.key for c in completions}

    # Pass 1: which completed parents have at least one completed child?
    parents_with_completed_children = {
        c.issue.parent_key
        for c in completions
        if c.issue.parent_key and c.issue.parent_key in completed_keys
    }

    # Pass 2: build one line item per completion, zeroing excluded parents.
    line_items: list[LineItem] = []
    for completion in completions:
        issue = completion.issue
        own = issue.original_estimate_seconds
        excluded = issue.key in parents_with_completed_children

        line_items.append(
            LineItem(
                completion=completion,
                own_estimate_seconds=own,
                counted_seconds=0 if excluded or own is None else own,
                rolled_up_excluded=excluded,
            )
        )

    return Aggregate(
        line_items=line_items,
        total_seconds=sum(item.counted_seconds for item in line_items),
        task_count=sum(1 for i in line_items if not i.completion.issue.is_subtask),
        subtask_count=sum(1 for i in line_items if i.completion.issue.is_subtask),
        # An excluded parent is not "unestimated" - it had an estimate, we
        # chose not to count it. Counting it here would double-report it.
        unestimated_count=sum(
            1 for i in line_items if i.is_unestimated and not i.rolled_up_excluded
        ),
        excluded_parent_count=sum(1 for i in line_items if i.rolled_up_excluded),
    )
