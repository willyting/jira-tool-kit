import pytest
from conftest import FakeClient
from typer.testing import CliRunner

from jira_release_task import cli
from jira_release_task.checklist import build_parent_summary
from jira_release_task.config import BASE_URL_VAR, EMAIL_VAR, TOKEN_VAR
from jira_release_task.errors import AuthError

runner = CliRunner()

TOKEN = "secret-token-value"
ENV = {
    BASE_URL_VAR: "https://jira.example.test",
    EMAIL_VAR: "someone@example.com",
    TOKEN_VAR: TOKEN,
}
ARGS = ["--sprint", "97", "--version", "2.14.0"]


@pytest.fixture
def env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def fake(monkeypatch, env):
    """Install one FakeClient as the client for every CLI run in the test."""
    client = FakeClient()
    monkeypatch.setattr(cli, "client_factory", lambda config: client)
    monkeypatch.setattr(cli, "is_interactive", lambda: True)
    return client


def invoke(*args, input=None):
    return runner.invoke(cli.app, list(args), input=input)


# ----------------------------------------------------------------------
# Happy paths
# ----------------------------------------------------------------------


def test_success_with_yes(fake):
    result = invoke(*ARGS, "--yes")
    assert result.exit_code == 0, result.output
    assert "Created 10 issues in reseller 97." in result.output
    assert build_parent_summary(97, "2.14.0") in result.output
    assert len(fake.create_calls) == 10


def test_dry_run_makes_no_writes(fake):
    result = invoke(*ARGS, "--dry-run")
    assert result.exit_code == 0, result.output
    assert "10 issue(s) would be created" in result.output
    assert fake.write_count == 0


def test_confirmation_accepted(fake):
    result = invoke(*ARGS, input="y\n")
    assert result.exit_code == 0, result.output
    assert len(fake.create_calls) == 10


def test_confirmation_declined(fake):
    result = invoke(*ARGS, input="n\n")
    assert result.exit_code == 0
    assert "Nothing was created." in result.output
    assert fake.write_count == 0


def test_non_tty_without_yes_refuses(fake, monkeypatch):
    monkeypatch.setattr(cli, "is_interactive", lambda: False)
    result = invoke(*ARGS)
    assert result.exit_code == 1
    assert "--yes" in result.output
    assert fake.write_count == 0


def test_second_run_reports_complete_without_prompt(fake):
    invoke(*ARGS, "--yes")
    writes = fake.write_count
    result = invoke(*ARGS)  # no --yes, no input: must not prompt
    assert result.exit_code == 0
    assert "already complete" in result.output
    assert fake.write_count == writes


def test_help_and_no_args():
    assert invoke("--help").exit_code == 0
    result = invoke()
    assert "--sprint" in result.output


# ----------------------------------------------------------------------
# Validation (no network)
# ----------------------------------------------------------------------


@pytest.mark.parametrize("value", ["abc", "0", "-3"])
def test_sprint_must_be_positive_int(value, monkeypatch):
    monkeypatch.setattr(cli, "client_factory", lambda c: pytest.fail("network used"))
    result = invoke("--sprint", value, "--version", "1.0")
    assert result.exit_code == 2
    assert "positive integer" in result.output


def test_blank_version(monkeypatch):
    monkeypatch.setattr(cli, "client_factory", lambda c: pytest.fail("network used"))
    result = invoke("--sprint", "97", "--version", "   ")
    assert result.exit_code == 2
    assert "must not be empty" in result.output


def test_version_with_line_break(monkeypatch):
    monkeypatch.setattr(cli, "client_factory", lambda c: pytest.fail("network used"))
    result = invoke("--sprint", "97", "--version", "1.0\n2")
    assert result.exit_code == 2
    assert "line break" in result.output


def test_board_selectors_conflict(monkeypatch):
    monkeypatch.setattr(cli, "client_factory", lambda c: pytest.fail("network used"))
    result = invoke(*ARGS, "--board", "12", "--board-name", "Other")
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_missing_required_option():
    result = invoke("--sprint", "97")
    assert result.exit_code != 0
    assert "--version" in result.output


# ----------------------------------------------------------------------
# Failures
# ----------------------------------------------------------------------


def test_missing_token(monkeypatch, env):
    monkeypatch.delenv(TOKEN_VAR)
    result = invoke(*ARGS, "--yes")
    assert result.exit_code == 1
    assert "JIRA_API_TOKEN" in result.output
    assert "api-tokens" in result.output
    assert "Traceback" not in result.output


def test_auth_failure_is_one_line_without_traceback(fake, monkeypatch):
    async def boom(*a, **kw):
        raise AuthError("Jira rejected the credentials (401).")

    monkeypatch.setattr(fake, "list_boards", boom)
    result = invoke(*ARGS, "--yes")
    assert result.exit_code == 1
    assert "Error: Jira rejected the credentials (401)." in result.output
    assert "Traceback" not in result.output
    assert TOKEN not in result.output


def test_verbose_failure_shows_traceback(fake, monkeypatch):
    async def boom(*a, **kw):
        raise AuthError("nope")

    monkeypatch.setattr(fake, "list_boards", boom)
    result = invoke(*ARGS, "--yes", "--verbose")
    assert result.exit_code == 1
    assert "Traceback" in result.output


def test_partial_failure_lists_created_then_errors(fake):
    fake._fail_create_on = 5  # parent + 3 subtasks succeed
    result = invoke(*ARGS, "--yes")
    assert result.exit_code == 1
    created_part, _, error_part = result.output.partition("Error:")
    assert created_part.count("/browse/") == 4
    assert "Re-run" in error_part
