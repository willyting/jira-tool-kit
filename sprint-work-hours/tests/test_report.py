from datetime import datetime, timezone

from conftest import raw_issue
from rich.console import Console

from jira_sprint_estimates.aggregate import SECONDS_PER_HOUR, aggregate
from jira_sprint_estimates.done import Completion
from jira_sprint_estimates.issues import CandidateSet, parse_issue
from jira_sprint_estimates.report import (
    EXCLUDED_MARKER,
    SUMMARY_TRUNCATE_WIDTH,
    UNASSIGNED,
    build_table,
    group_line_items,
    render,
    truncate,
)
from jira_sprint_estimates.sprints import build_sprint

CLOSED_SPRINT = build_sprint(
    {
        "id": 99,
        "name": "Sprint 42",
        "state": "closed",
        "startDate": "2026-03-01T09:00:00.000+0000",
        "completeDate": "2026-03-15T17:30:00.000+0000",
    }
)

ACTIVE_SPRINT = build_sprint(
    {
        "id": 100,
        "name": "Sprint 43",
        "state": "active",
        "startDate": "2026-03-16T09:00:00.000+0000",
    },
    now=datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc),
)


def at(day, hour=10):
    return datetime(2026, 3, day, hour, 0, tzinfo=timezone.utc)


def completion(
    key,
    *,
    hours=None,
    parent=None,
    subtask=False,
    when=None,
    assignee="Ada Lovelace",
    summary=None,
    reopened=False,
):
    issue = parse_issue(
        raw_issue(
            key,
            summary=summary,
            estimate_seconds=None if hours is None else int(hours * SECONDS_PER_HOUR),
            parent=parent,
            is_subtask=subtask,
            issue_type="Sub-task" if subtask else "Task",
            assignee=assignee,
        )
    )
    return Completion(issue=issue, completed_at=when or at(5), reopened=reopened)


def render_to_text(sprint, result, **kwargs):
    console = Console(width=200, record=True, force_terminal=False)
    render(console, sprint, result, **kwargs)
    return console.export_text()


def table_to_text(result):
    console = Console(width=200, record=True, force_terminal=False)
    console.print(build_table(result))
    return console.export_text()


# ----------------------------------------------------------------------
# Truncation
# ----------------------------------------------------------------------


def test_short_summary_is_untouched():
    assert truncate("Short one") == "Short one"


def test_long_summary_is_truncated_with_an_ellipsis():
    long = "x" * (SUMMARY_TRUNCATE_WIDTH + 40)

    out = truncate(long)

    assert len(out) == SUMMARY_TRUNCATE_WIDTH
    assert out.endswith("…")


def test_truncated_summary_appears_in_the_table():
    long = "Refactor the widget pipeline so that it stops doing the slow thing"
    result = aggregate([completion("A-1", hours=1, summary=long)])

    assert "…" in table_to_text(result)


# ----------------------------------------------------------------------
# Rows
# ----------------------------------------------------------------------


def test_one_row_per_completed_issue():
    result = aggregate(
        [completion("A-1", hours=1), completion("A-2", hours=2), completion("A-3", hours=3)]
    )

    text = table_to_text(result)

    for key in ("A-1", "A-2", "A-3"):
        assert key in text
    assert len(group_line_items(result.line_items)) == 3


def test_unassigned_issue_shows_a_placeholder():
    result = aggregate([completion("A-1", hours=1, assignee=None)])

    assert UNASSIGNED in table_to_text(result)


def test_subtask_column_marks_subtasks():
    result = aggregate(
        [
            completion("A-1", hours=1),
            completion("A-2", hours=1, parent="A-9", subtask=True),
        ]
    )

    text = table_to_text(result)
    a2_row = next(line for line in text.splitlines() if "A-2" in line)
    assert "yes" in a2_row


def test_reopened_issue_is_flagged():
    result = aggregate([completion("A-1", hours=1, reopened=True)])

    assert "reopened" in table_to_text(result)


def test_bracketed_summary_survives_rich_markup():
    # rich would otherwise parse "[URGENT]" as a style tag and drop it.
    result = aggregate([completion("A-1", hours=1, summary="[URGENT] fix login")])

    text = table_to_text(result)

    assert "[URGENT]" in text
    assert "fix login" in text


def test_bracketed_assignee_survives_rich_markup():
    result = aggregate([completion("A-1", hours=1, assignee="[bot] deploy")])

    assert "[bot]" in table_to_text(result)


def test_missing_estimate_renders_as_a_dash():
    result = aggregate([completion("A-1", hours=None)])

    a1_row = next(line for line in table_to_text(result).splitlines() if "A-1" in line)
    assert "-" in a1_row


# ----------------------------------------------------------------------
# Grouping and ordering
# ----------------------------------------------------------------------


def test_parent_is_followed_immediately_by_its_subtasks():
    result = aggregate(
        [
            completion("P-1", hours=8, when=at(3)),
            completion("Q-1", hours=1, when=at(4)),
            completion("P-2", hours=3, parent="P-1", subtask=True, when=at(6)),
            completion("P-3", hours=4, parent="P-1", subtask=True, when=at(7)),
        ]
    )

    ordered = [item.key for item in group_line_items(result.line_items)]

    assert ordered == ["P-1", "P-2", "P-3", "Q-1"]


def test_groups_are_ordered_by_earliest_completion_in_the_group():
    # Q-1 completes on day 4; the P group's earliest member is day 2.
    result = aggregate(
        [
            completion("Q-1", hours=1, when=at(4)),
            completion("P-1", hours=8, when=at(9)),
            completion("P-2", hours=3, parent="P-1", subtask=True, when=at(2)),
        ]
    )

    ordered = [item.key for item in group_line_items(result.line_items)]

    assert ordered == ["P-1", "P-2", "Q-1"]


def test_orphan_subtask_heads_its_own_group():
    # The parent did not complete, so the subtask stands alone.
    result = aggregate([completion("P-2", hours=3, parent="P-1", subtask=True)])

    assert [i.key for i in group_line_items(result.line_items)] == ["P-2"]


# ----------------------------------------------------------------------
# Exclusion marker
# ----------------------------------------------------------------------


def test_excluded_parent_shows_its_estimate_and_the_marker():
    result = aggregate(
        [
            completion("P-1", hours=8),
            completion("P-2", hours=3, parent="P-1", subtask=True),
        ]
    )

    p1_row = next(line for line in table_to_text(result).splitlines() if "P-1" in line)

    assert EXCLUDED_MARKER in p1_row
    assert "8.0h" in p1_row


# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------


def test_summary_reports_sprint_window_total_and_counts():
    result = aggregate(
        [
            completion("A-1", hours=2),
            completion("A-2", hours=3, parent="A-9", subtask=True),
        ]
    )

    text = render_to_text(CLOSED_SPRINT, result)

    assert "Sprint 42" in text
    assert "id 99" in text
    assert "2026-03-01 09:00" in text
    assert "2026-03-15 17:30" in text
    assert "Total original estimate: 5.0h" in text
    assert "1 tasks, 1 subtasks" in text


def test_summary_reports_unestimated_count():
    result = aggregate([completion("A-1", hours=2), completion("A-2", hours=None)])

    text = render_to_text(CLOSED_SPRINT, result)

    assert "Total original estimate: 2.0h" in text
    assert "Unestimated: 1" in text


def test_summary_reports_excluded_parent_count():
    result = aggregate(
        [
            completion("P-1", hours=8),
            completion("P-2", hours=3, parent="P-1", subtask=True),
        ]
    )

    assert "Excluded from the total: 1 parent" in render_to_text(CLOSED_SPRINT, result)


def test_active_sprint_is_labelled_in_progress():
    result = aggregate([completion("A-1", hours=1)])

    text = render_to_text(ACTIVE_SPRINT, result)

    assert "still in progress" in text
    assert "2026-03-20 12:00" in text


def test_closed_sprint_is_not_labelled_in_progress():
    result = aggregate([completion("A-1", hours=1)])

    assert "still in progress" not in render_to_text(CLOSED_SPRINT, result)


def test_no_qualifying_issues_prints_zero_and_says_so():
    text = render_to_text(CLOSED_SPRINT, aggregate([]))

    assert "Total original estimate: 0h" in text
    assert "No issues transitioned to Done" in text


def test_skipped_issues_are_reported_with_a_caveat():
    result = aggregate([completion("A-1", hours=1)])

    text = render_to_text(
        CLOSED_SPRINT, result, skipped=[("A-9", "permission denied")]
    )

    assert "Skipped: 1" in text
    assert "understated" in text
    assert "A-9" in text


def test_discrepancies_only_surface_under_verbose():
    result = aggregate([completion("A-1", hours=1)])
    candidates = CandidateSet(issues=[], discrepancies=["A-77"])

    quiet = render_to_text(CLOSED_SPRINT, result, candidates=candidates)
    loud = render_to_text(CLOSED_SPRINT, result, candidates=candidates, verbose=True)

    assert "A-77" not in quiet
    assert "A-77" in loud
