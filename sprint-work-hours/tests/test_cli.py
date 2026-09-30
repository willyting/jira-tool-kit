import pytest
from conftest import (
    DONE_STATUS_ID,
    IN_PROGRESS_STATUS_ID,
    FakeClient,
    raw_issue,
    status_change,
)
from typer.testing import CliRunner

from jira_sprint_estimates import cli
from jira_sprint_estimates.config import BASE_URL_VAR, EMAIL_VAR, TOKEN_VAR
from jira_sprint_estimates.errors import AuthError

runner = CliRunner()

TOKEN = "secret-token-value"
ENV = {
    BASE_URL_VAR: "https://jira.example.test",
    EMAIL_VAR: "someone@example.com",
    TOKEN_VAR: TOKEN,
}

SPRINT = {
    "id": 99,
    "name": "Sprint 42",
    "state": "closed",
    "startDate": "2026-03-01T09:00:00.000+0000",
    "completeDate": "2026-03-15T17:30:00.000+0000",
}

INSIDE = "2026-03-05T10:00:00.000+0000"


def done_inside():
    return [status_change(INSIDE, from_id=IN_PROGRESS_STATUS_ID, to_id=DONE_STATUS_ID)]


@pytest.fixture
def env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    return ENV


@pytest.fixture
def stub_client(monkeypatch):
    """Install a FakeClient factory in place of the real JiraClient."""
    holder = {}

    def install(client_class=FakeClient, **kwargs):
        kwargs.setdefault("sprints", [SPRINT])
        kwargs.setdefault("boards", [{"id": 7, "name": "Delivery"}])
        client = client_class(**kwargs)
        holder["client"] = client
        monkeypatch.setattr(cli, "client_factory", lambda config: client)
        return client

    install.holder = holder
    return install


# ----------------------------------------------------------------------
# Argument validation (no network)
# ----------------------------------------------------------------------


def test_missing_sprint_is_a_usage_error(env):
    result = runner.invoke(cli.app, ["--board", "7"])

    assert result.exit_code != 0
    assert "sprint" in result.output.lower()


def test_both_board_selectors_is_an_error(env):
    result = runner.invoke(
        cli.app, ["--sprint", "Sprint 42", "--board", "7", "--board-name", "Delivery"]
    )

    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_neither_board_selector_is_an_error(env):
    result = runner.invoke(cli.app, ["--sprint", "Sprint 42"])

    assert result.exit_code == 2
    assert "--board" in result.output
    assert "--board-name" in result.output


def test_board_validation_happens_before_any_request(env, stub_client):
    client = stub_client()

    runner.invoke(cli.app, ["--sprint", "Sprint 42"])

    assert client.jql_queries == []


# ----------------------------------------------------------------------
# Successful runs
# ----------------------------------------------------------------------


def test_successful_run_reports_the_total(env, stub_client):
    stub_client(
        sprint_issues=[
            raw_issue("PROJ-1", estimate_seconds=7200),
            raw_issue("PROJ-2", estimate_seconds=3600),
        ],
        changelogs={"PROJ-1": done_inside(), "PROJ-2": done_inside()},
    )

    result = runner.invoke(cli.app, ["--sprint", "Sprint 42", "--board", "7"])

    assert result.exit_code == 0
    assert "Sprint 42" in result.output
    assert "Total original estimate: 3.0h" in result.output


def test_leaf_preferring_rule_applies_end_to_end(env, stub_client):
    parent = raw_issue("PROJ-1", estimate_seconds=8 * 3600, subtasks=["PROJ-2", "PROJ-3"])
    children = [
        raw_issue("PROJ-2", estimate_seconds=3 * 3600, is_subtask=True, parent="PROJ-1"),
        raw_issue("PROJ-3", estimate_seconds=4 * 3600, is_subtask=True, parent="PROJ-1"),
    ]
    stub_client(
        sprint_issues=[parent],
        child_issues={"PROJ-1": children},
        changelogs={
            "PROJ-1": done_inside(),
            "PROJ-2": done_inside(),
            "PROJ-3": done_inside(),
        },
    )

    result = runner.invoke(cli.app, ["--sprint", "Sprint 42", "--board", "7"])

    assert result.exit_code == 0
    # 3h + 4h, with the parent's 8h excluded as a roll-up.
    assert "Total original estimate: 7.0h" in result.output
    assert "rolled up" in result.output


def test_no_qualifying_issues_still_exits_zero(env, stub_client):
    stub_client(
        sprint_issues=[raw_issue("PROJ-1")],
        changelogs={"PROJ-1": []},
    )

    result = runner.invoke(cli.app, ["--sprint", "Sprint 42", "--board", "7"])

    assert result.exit_code == 0
    assert "Total original estimate: 0h" in result.output


def test_board_can_be_resolved_by_name(env, stub_client):
    client = stub_client(
        boards=[{"id": 7, "name": "Delivery"}],
        sprint_issues=[raw_issue("PROJ-1", estimate_seconds=3600)],
        changelogs={"PROJ-1": done_inside()},
    )

    result = runner.invoke(
        cli.app, ["--sprint", "Sprint 42", "--board-name", "Delivery"]
    )

    assert result.exit_code == 0
    assert "Total original estimate: 1.0h" in result.output


def test_unknown_board_name_is_reported(env, stub_client):
    stub_client(boards=[{"id": 7, "name": "Delivery"}])

    result = runner.invoke(cli.app, ["--sprint", "Sprint 42", "--board-name", "Nope"])

    assert result.exit_code == 1
    assert "No board named" in result.output


def test_unknown_sprint_name_lists_alternatives(env, stub_client):
    stub_client()

    result = runner.invoke(cli.app, ["--sprint", "Sprint 99", "--board", "7"])

    assert result.exit_code == 1
    assert "Sprint 42" in result.output


# ----------------------------------------------------------------------
# Failure reporting
# ----------------------------------------------------------------------


def test_missing_credentials_reports_the_variable_without_a_traceback(monkeypatch):
    for key in ENV:
        monkeypatch.delenv(key, raising=False)

    result = runner.invoke(cli.app, ["--sprint", "Sprint 42", "--board", "7"])

    assert result.exit_code == 1
    assert TOKEN_VAR in result.output
    assert "Traceback" not in result.output


def test_auth_failure_points_at_the_env_vars(env, stub_client):
    class Failing(FakeClient):
        async def search_jql(self, jql, fields, **kwargs):
            raise AuthError(
                "Jira rejected the credentials (401). Verify JIRA_EMAIL and "
                "JIRA_API_TOKEN."
            )

    stub_client(client_class=Failing)

    result = runner.invoke(cli.app, ["--sprint", "Sprint 42", "--board", "7"])

    assert result.exit_code == 1
    assert "JIRA_API_TOKEN" in result.output
    assert TOKEN not in result.output
    assert "Traceback" not in result.output


def test_verbose_failure_shows_the_traceback(monkeypatch):
    for key in ENV:
        monkeypatch.delenv(key, raising=False)

    result = runner.invoke(
        cli.app, ["--sprint", "Sprint 42", "--board", "7", "--verbose"]
    )

    assert result.exit_code == 1
    assert "Traceback" in result.output


def test_verbose_prints_progress(env, stub_client):
    stub_client(
        sprint_issues=[raw_issue("PROJ-1", estimate_seconds=3600)],
        changelogs={"PROJ-1": done_inside()},
    )

    result = runner.invoke(
        cli.app, ["--sprint", "Sprint 42", "--board", "7", "--verbose"]
    )

    assert result.exit_code == 0
    assert "Resolving sprint" in result.output
    assert "Reading changelogs" in result.output


def test_skipped_changelog_is_surfaced(env, stub_client):
    from jira_sprint_estimates.errors import PermissionError_

    stub_client(
        sprint_issues=[
            raw_issue("PROJ-1", estimate_seconds=3600),
            raw_issue("PROJ-2", estimate_seconds=3600),
        ],
        changelogs={"PROJ-1": done_inside()},
        changelog_errors={"PROJ-2": PermissionError_("no access")},
    )

    result = runner.invoke(cli.app, ["--sprint", "Sprint 42", "--board", "7"])

    assert result.exit_code == 0
    assert "Skipped: 1" in result.output
    assert "PROJ-2" in result.output
