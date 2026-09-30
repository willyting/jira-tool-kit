import asyncio
from datetime import datetime, timezone

from conftest import (
    CLOSED_STATUS_ID,
    DONE_STATUS_ID,
    IN_PROGRESS_STATUS_ID,
    RELEASED_STATUS_ID,
    STATUS_CATEGORIES,
    TODO_STATUS_ID,
    FakeClient,
    raw_issue,
    status_change,
)

from jira_sprint_estimates.done import (
    MAX_CONCURRENT_CHANGELOG_REQUESTS,
    classify_changelog,
    detect_completions,
)
from jira_sprint_estimates.errors import PermissionError_
from jira_sprint_estimates.issues import parse_issue
from jira_sprint_estimates.sprints import build_sprint

SPRINT = build_sprint(
    {
        "id": 99,
        "name": "Sprint 42",
        "state": "closed",
        "startDate": "2026-03-01T09:00:00.000+0000",
        "endDate": "2026-03-15T09:00:00.000+0000",
        "completeDate": "2026-03-15T17:30:00.000+0000",
    }
)

BEFORE = "2026-02-20T10:00:00.000+0000"
INSIDE = "2026-03-05T10:00:00.000+0000"
LATER_INSIDE = "2026-03-10T10:00:00.000+0000"
AFTER = "2026-03-20T10:00:00.000+0000"


def classify(changelog):
    return classify_changelog(changelog, STATUS_CATEGORIES, SPRINT)


# ----------------------------------------------------------------------
# Transition classification
# ----------------------------------------------------------------------


def test_transition_into_done_inside_window_qualifies():
    completed_at, reopened = classify(
        [status_change(INSIDE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID)]
    )

    assert completed_at == datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc)
    assert reopened is False


def test_transition_before_the_window_does_not_qualify():
    completed_at, _ = classify(
        [status_change(BEFORE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID)]
    )

    assert completed_at is None


def test_transition_after_the_window_does_not_qualify():
    completed_at, _ = classify(
        [status_change(AFTER, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID)]
    )

    assert completed_at is None


def test_done_now_but_transitioned_before_the_sprint_does_not_qualify():
    # Current status is Done, and it never left. The only entry into done
    # predates the sprint, so no work was completed this sprint.
    completed_at, _ = classify(
        [
            status_change(BEFORE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID),
            status_change(
                INSIDE, from_id=DONE_STATUS_ID, to_id=CLOSED_STATUS_ID
            ),
        ]
    )

    assert completed_at is None


def test_done_to_done_transition_inside_window_does_not_qualify():
    # Entered the done category before the sprint, then moved between two
    # done-category statuses during it.
    completed_at, _ = classify(
        [
            status_change(BEFORE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID),
            status_change(INSIDE, from_id=DONE_STATUS_ID, to_id=RELEASED_STATUS_ID),
        ]
    )

    assert completed_at is None


def test_completed_then_reopened_inside_the_sprint_still_qualifies():
    completed_at, reopened = classify(
        [
            status_change(INSIDE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID),
            status_change(
                LATER_INSIDE, from_id=DONE_STATUS_ID, to_id=IN_PROGRESS_STATUS_ID
            ),
        ]
    )

    assert completed_at == datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc)
    assert reopened is True


def test_multiple_qualifying_transitions_report_the_earliest():
    completed_at, _ = classify(
        [
            status_change(INSIDE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID),
            status_change(
                "2026-03-06T10:00:00.000+0000",
                from_id=DONE_STATUS_ID,
                to_id=IN_PROGRESS_STATUS_ID,
            ),
            status_change(
                LATER_INSIDE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID
            ),
        ]
    )

    assert completed_at == datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc)


def test_custom_done_category_status_qualifies():
    # "Released" is not called Done, but Jira classifies it in the done
    # category, which is what we key on.
    completed_at, _ = classify(
        [status_change(INSIDE, from_id=IN_PROGRESS_STATUS_ID, to_id=RELEASED_STATUS_ID)]
    )

    assert completed_at is not None


def test_non_status_changes_are_ignored():
    completed_at, _ = classify(
        [
            {
                "created": INSIDE,
                "items": [{"field": "assignee", "from": "a", "to": "b"}],
            }
        ]
    )

    assert completed_at is None


def test_unknown_status_id_is_not_treated_as_done():
    completed_at, _ = classify(
        [status_change(INSIDE, from_id=TODO_STATUS_ID, to_id="99999")]
    )

    assert completed_at is None


def test_entries_out_of_order_are_still_classified_correctly():
    # Jira sometimes returns newest-first; the reopen must not be mistaken for
    # the completion just because it arrived first.
    completed_at, reopened = classify(
        [
            status_change(
                LATER_INSIDE, from_id=DONE_STATUS_ID, to_id=IN_PROGRESS_STATUS_ID
            ),
            status_change(INSIDE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID),
        ]
    )

    assert completed_at == datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc)
    assert reopened is True


def test_empty_changelog_does_not_qualify():
    assert classify([]) == (None, False)


def test_transition_exactly_on_the_window_boundary_qualifies():
    completed_at, _ = classify(
        [
            status_change(
                "2026-03-15T17:30:00.000+0000",
                from_id=IN_PROGRESS_STATUS_ID,
                to_id=DONE_STATUS_ID,
            )
        ]
    )

    assert completed_at is not None


def test_transition_timestamp_in_another_offset_is_compared_in_utc():
    # 2026-03-05T18:00+08:00 is 10:00 UTC, inside the window.
    completed_at, _ = classify(
        [
            status_change(
                "2026-03-05T18:00:00.000+0800",
                from_id=IN_PROGRESS_STATUS_ID,
                to_id=DONE_STATUS_ID,
            )
        ]
    )

    assert completed_at == datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc)


# ----------------------------------------------------------------------
# detect_completions
# ----------------------------------------------------------------------


def issue(key, **kwargs):
    return parse_issue(raw_issue(key, **kwargs))


async def test_detect_keeps_only_qualifying_issues():
    issues = [issue("PROJ-1"), issue("PROJ-2"), issue("PROJ-3")]
    client = FakeClient(
        changelogs={
            "PROJ-1": [
                status_change(INSIDE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID)
            ],
            "PROJ-2": [
                status_change(BEFORE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID)
            ],
            "PROJ-3": [],
        }
    )

    result = await detect_completions(client, issues, STATUS_CATEGORIES, SPRINT)

    assert [c.issue.key for c in result.completions] == ["PROJ-1"]
    assert result.skipped == []


async def test_completions_are_ordered_by_completion_time():
    issues = [issue("PROJ-1"), issue("PROJ-2")]
    client = FakeClient(
        changelogs={
            "PROJ-1": [
                status_change(
                    LATER_INSIDE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID
                )
            ],
            "PROJ-2": [
                status_change(INSIDE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID)
            ],
        }
    )

    result = await detect_completions(client, issues, STATUS_CATEGORIES, SPRINT)

    assert [c.issue.key for c in result.completions] == ["PROJ-2", "PROJ-1"]


async def test_changelog_failure_is_recorded_as_skipped_not_fatal():
    issues = [issue("PROJ-1"), issue("PROJ-2")]
    client = FakeClient(
        changelogs={
            "PROJ-1": [
                status_change(INSIDE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID)
            ]
        },
        changelog_errors={"PROJ-2": PermissionError_("no access to PROJ-2")},
    )

    result = await detect_completions(client, issues, STATUS_CATEGORIES, SPRINT)

    assert [c.issue.key for c in result.completions] == ["PROJ-1"]
    assert [key for key, _ in result.skipped] == ["PROJ-2"]
    assert "no access" in result.skipped[0][1]


async def test_no_issues_makes_no_requests():
    client = FakeClient()

    result = await detect_completions(client, [], STATUS_CATEGORIES, SPRINT)

    assert result.completions == []
    assert client.changelog_requests == []


async def test_changelog_concurrency_is_bounded():
    peak = 0
    live = 0

    class CountingClient(FakeClient):
        async def get_changelog(self, issue_key):
            nonlocal peak, live
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0)
            live -= 1
            return []

    issues = [issue(f"PROJ-{n}") for n in range(40)]

    await detect_completions(CountingClient(), issues, STATUS_CATEGORIES, SPRINT)

    # Equality, not <=: this proves the fetches really do run concurrently
    # (a serial implementation would peak at 1) *and* that the cap holds.
    assert peak == MAX_CONCURRENT_CHANGELOG_REQUESTS


async def test_every_candidate_changelog_is_requested():
    issues = [issue("PROJ-1"), issue("PROJ-2"), issue("PROJ-3")]
    client = FakeClient()

    await detect_completions(client, issues, STATUS_CATEGORIES, SPRINT)

    assert sorted(client.changelog_requests) == ["PROJ-1", "PROJ-2", "PROJ-3"]
