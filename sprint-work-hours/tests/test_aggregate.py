from datetime import datetime, timezone

from conftest import raw_issue

from jira_sprint_estimates.aggregate import (
    SECONDS_PER_HOUR,
    aggregate,
    format_hours,
    to_hours,
)
from jira_sprint_estimates.done import Completion
from jira_sprint_estimates.issues import parse_issue

AT = datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc)


def completion(key, *, hours=None, seconds=None, parent=None, subtask=False, at=AT):
    if seconds is None:
        seconds = None if hours is None else int(hours * SECONDS_PER_HOUR)
    issue = parse_issue(
        raw_issue(
            key,
            estimate_seconds=seconds,
            parent=parent,
            is_subtask=subtask,
            issue_type="Sub-task" if subtask else "Task",
        )
    )
    return Completion(issue=issue, completed_at=at, reopened=False)


def by_key(result):
    return {item.key: item for item in result.line_items}


# ----------------------------------------------------------------------
# Leaf-preferring rules
# ----------------------------------------------------------------------


def test_parent_estimate_excluded_when_subtasks_also_completed():
    result = aggregate(
        [
            completion("P-1", hours=8),
            completion("P-2", hours=3, parent="P-1", subtask=True),
            completion("P-3", hours=4, parent="P-1", subtask=True),
        ]
    )

    assert result.total_hours == 7.0
    items = by_key(result)
    assert items["P-1"].rolled_up_excluded is True
    assert items["P-1"].counted_seconds == 0
    # The excluded figure is retained so the report can show it.
    assert items["P-1"].own_estimate_seconds == 8 * SECONDS_PER_HOUR
    assert result.excluded_parent_count == 1


def test_parent_with_no_completed_subtasks_contributes_its_own_estimate():
    result = aggregate([completion("P-1", hours=5)])

    assert result.total_hours == 5.0
    assert by_key(result)["P-1"].rolled_up_excluded is False
    assert result.excluded_parent_count == 0


def test_parent_whose_subtasks_did_not_complete_still_counts_itself():
    # The subtask exists in Jira but did not complete this sprint, so it is
    # not in the completed set at all.
    result = aggregate([completion("P-1", hours=5)])

    assert result.total_hours == 5.0


def test_subtask_counts_even_when_its_parent_did_not_complete():
    result = aggregate([completion("P-2", hours=2, parent="P-1", subtask=True)])

    assert result.total_hours == 2.0
    assert result.subtask_count == 1
    assert result.task_count == 0


def test_standalone_issue_contributes_its_own_estimate():
    result = aggregate([completion("SOLO-1", hours=1.5)])

    assert result.total_hours == 1.5


def test_only_the_parent_with_completed_children_is_excluded():
    result = aggregate(
        [
            completion("P-1", hours=8),
            completion("P-2", hours=3, parent="P-1", subtask=True),
            completion("Q-1", hours=6),
        ]
    )

    items = by_key(result)
    assert items["P-1"].rolled_up_excluded is True
    assert items["Q-1"].rolled_up_excluded is False
    assert result.total_hours == 9.0


def test_excluded_parent_without_an_estimate_is_not_counted_as_unestimated():
    result = aggregate(
        [
            completion("P-1", hours=None),
            completion("P-2", hours=3, parent="P-1", subtask=True),
        ]
    )

    assert result.excluded_parent_count == 1
    assert result.unestimated_count == 0
    assert result.total_hours == 3.0


# ----------------------------------------------------------------------
# Missing estimates
# ----------------------------------------------------------------------


def test_unestimated_issue_contributes_zero_and_is_counted():
    result = aggregate(
        [
            completion("A-1", hours=2),
            completion("A-2", hours=3),
            completion("A-3", hours=None),
        ]
    )

    assert result.total_hours == 5.0
    assert result.unestimated_count == 1
    assert by_key(result)["A-3"].is_unestimated is True


def test_all_unestimated_gives_zero_total():
    result = aggregate([completion("A-1"), completion("A-2")])

    assert result.total_seconds == 0
    assert result.total_hours == 0.0
    assert result.unestimated_count == 2


def test_empty_completion_set():
    result = aggregate([])

    assert result.total_seconds == 0
    assert result.line_items == []
    assert result.task_count == 0
    assert result.subtask_count == 0


# ----------------------------------------------------------------------
# Counts and units
# ----------------------------------------------------------------------


def test_counts_split_tasks_from_subtasks():
    result = aggregate(
        [
            completion("P-1", hours=1),
            completion("P-2", hours=1, parent="P-9", subtask=True),
            completion("P-3", hours=1, parent="P-9", subtask=True),
        ]
    )

    assert result.task_count == 1
    assert result.subtask_count == 2


def test_seconds_convert_to_hours_for_display():
    assert to_hours(12600) == 3.5
    assert format_hours(12600) == "3.5h"
    assert format_hours(None) == "-"


def test_total_is_summed_in_seconds_before_rounding():
    # 1000s is 0.28h when rounded individually; 3 x 0.28 = 0.84, but the
    # correct answer from 3000s is 0.83.
    result = aggregate([completion(f"A-{n}", seconds=1000) for n in range(3)])

    assert result.total_seconds == 3000
    assert result.total_hours == 0.83
    assert result.total_hours != round(round(1000 / 3600, 2) * 3, 2)
