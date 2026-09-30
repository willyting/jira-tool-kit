from datetime import datetime, timedelta, timezone

import pytest

from jira_sprint_estimates.errors import ConfigError, NotFoundError
from jira_sprint_estimates.sprints import (
    in_window,
    parse_jira_datetime,
    resolve_sprint,
)

NOW = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)


def sprint(
    id=1,
    name="Sprint 42",
    state="closed",
    startDate="2026-03-01T09:00:00.000+0000",
    endDate="2026-03-15T09:00:00.000+0000",
    completeDate="2026-03-15T17:30:00.000+0000",
):
    raw = {"id": id, "name": name, "state": state}
    for key, value in (
        ("startDate", startDate),
        ("endDate", endDate),
        ("completeDate", completeDate),
    ):
        if value is not None:
            raw[key] = value
    return raw


# ----------------------------------------------------------------------
# Timestamp parsing
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "2026-03-01T09:00:00.000+0000",
        "2026-03-01T09:00:00.000+00:00",
        "2026-03-01T09:00:00Z",
        "2026-03-01T09:00:00",
    ],
)
def test_parses_jira_timestamp_shapes_to_utc(raw):
    assert parse_jira_datetime(raw) == datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)


def test_non_utc_offset_is_converted():
    # 09:00+08:00 is 01:00 UTC.
    assert parse_jira_datetime("2026-03-01T09:00:00.000+0800") == datetime(
        2026, 3, 1, 1, 0, tzinfo=timezone.utc
    )


def test_missing_or_unparseable_timestamp_is_none():
    assert parse_jira_datetime(None) is None
    assert parse_jira_datetime("") is None
    assert parse_jira_datetime("not a date") is None


# ----------------------------------------------------------------------
# Name matching
# ----------------------------------------------------------------------


def test_exact_name_match():
    resolved = resolve_sprint([sprint(id=7)], "Sprint 42", now=NOW)
    assert resolved.id == 7
    assert resolved.name == "Sprint 42"


@pytest.mark.parametrize("query", ["sprint 42", "SPRINT 42", "  sprint 42 ", "Sprint  42"])
def test_matching_ignores_case_and_padding(query):
    assert resolve_sprint([sprint()], query, now=NOW).id == 1


def test_no_match_lists_recent_sprint_names():
    board = [
        sprint(id=1, name="Sprint 40", startDate="2026-01-01T09:00:00.000+0000"),
        sprint(id=2, name="Sprint 41", startDate="2026-02-01T09:00:00.000+0000"),
    ]

    with pytest.raises(NotFoundError) as excinfo:
        resolve_sprint(board, "Sprint 99", now=NOW)

    message = str(excinfo.value)
    assert "Sprint 99" in message
    assert "Sprint 41" in message
    assert "Sprint 40" in message


def test_no_match_on_empty_board():
    with pytest.raises(NotFoundError, match="no sprints"):
        resolve_sprint([], "Sprint 42", now=NOW)


def test_duplicate_names_report_id_state_and_start():
    board = [
        sprint(id=11, state="closed", startDate="2026-01-01T09:00:00.000+0000"),
        sprint(id=12, state="active", startDate="2026-03-01T09:00:00.000+0000"),
    ]

    with pytest.raises(ConfigError) as excinfo:
        resolve_sprint(board, "Sprint 42", now=NOW)

    message = str(excinfo.value)
    assert "id=11" in message
    assert "id=12" in message
    assert "active" in message
    assert "2026-03-01" in message
    assert "sprint id" in message


# ----------------------------------------------------------------------
# Window derivation
# ----------------------------------------------------------------------


def test_closed_sprint_window_uses_complete_date():
    resolved = resolve_sprint([sprint()], "Sprint 42", now=NOW)

    assert resolved.start == datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
    assert resolved.end == datetime(2026, 3, 15, 17, 30, tzinfo=timezone.utc)
    assert resolved.is_active is False


def test_closed_sprint_without_complete_date_falls_back_to_end_date():
    resolved = resolve_sprint([sprint(completeDate=None)], "Sprint 42", now=NOW)

    assert resolved.end == datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)


def test_active_sprint_window_ends_now():
    board = [sprint(state="active", completeDate=None, endDate="2026-04-15T09:00:00.000+0000")]

    resolved = resolve_sprint(board, "Sprint 42", now=NOW)

    assert resolved.end == NOW
    assert resolved.is_active is True


def test_active_sprint_ignores_a_stale_complete_date():
    # An active sprint should be windowed to now even if Jira carries a
    # completeDate from a previous close/reopen.
    board = [sprint(state="active")]

    assert resolve_sprint(board, "Sprint 42", now=NOW).end == NOW


def test_sprint_without_start_date_is_rejected():
    with pytest.raises(ConfigError, match="has not started"):
        resolve_sprint([sprint(state="future", startDate=None)], "Sprint 42", now=NOW)


def test_window_is_normalised_to_utc_from_mixed_offsets():
    board = [
        sprint(
            startDate="2026-03-01T17:00:00.000+0800",
            completeDate="2026-03-15T12:30:00.000-0500",
        )
    ]

    resolved = resolve_sprint(board, "Sprint 42", now=NOW)

    assert resolved.start == datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
    assert resolved.end == datetime(2026, 3, 15, 17, 30, tzinfo=timezone.utc)
    assert resolved.start.tzinfo is timezone.utc
    assert resolved.end.tzinfo is timezone.utc


# ----------------------------------------------------------------------
# Window membership
# ----------------------------------------------------------------------


def test_in_window_is_inclusive_at_both_ends():
    start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    end = datetime(2026, 3, 15, tzinfo=timezone.utc)

    assert in_window(start, start, end)
    assert in_window(end, start, end)
    assert in_window(start + timedelta(days=1), start, end)
    assert not in_window(start - timedelta(seconds=1), start, end)
    assert not in_window(end + timedelta(seconds=1), start, end)


def test_in_window_compares_across_timezones():
    start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    end = datetime(2026, 3, 15, tzinfo=timezone.utc)
    # 2026-03-02 08:00+08:00 is 2026-03-02 00:00 UTC, inside the window.
    moment = datetime(2026, 3, 2, 8, 0, tzinfo=timezone(timedelta(hours=8)))

    assert in_window(moment, start, end)
