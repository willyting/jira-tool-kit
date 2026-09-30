import pytest

from jira_sprint_estimates.config import (
    BASE_URL_VAR,
    EMAIL_VAR,
    TOKEN_VAR,
    JiraConfig,
    load_config,
)
from jira_sprint_estimates.errors import ConfigError

TOKEN = "super-secret-token-value"

FULL_ENV = {
    BASE_URL_VAR: "https://dibts3.atlassian.net",
    EMAIL_VAR: "someone@example.com",
    TOKEN_VAR: TOKEN,
}


def test_loads_all_three_credentials():
    config = load_config(FULL_ENV)

    assert config.base_url == "https://dibts3.atlassian.net"
    assert config.email == "someone@example.com"
    assert config.api_token == TOKEN


def test_strips_whitespace_and_trailing_slash():
    config = load_config(
        {
            BASE_URL_VAR: "  https://dibts3.atlassian.net/  ",
            EMAIL_VAR: " someone@example.com ",
            TOKEN_VAR: f"  {TOKEN}  ",
        }
    )

    assert config.base_url == "https://dibts3.atlassian.net"
    assert config.email == "someone@example.com"
    assert config.api_token == TOKEN


@pytest.mark.parametrize("missing", [BASE_URL_VAR, EMAIL_VAR, TOKEN_VAR])
def test_missing_variable_names_that_variable(missing):
    env = {k: v for k, v in FULL_ENV.items() if k != missing}

    with pytest.raises(ConfigError) as excinfo:
        load_config(env)

    assert missing in str(excinfo.value)


@pytest.mark.parametrize("blank", ["", "   "])
@pytest.mark.parametrize("variable", [BASE_URL_VAR, EMAIL_VAR, TOKEN_VAR])
def test_present_but_blank_counts_as_missing(variable, blank):
    env = dict(FULL_ENV, **{variable: blank})

    with pytest.raises(ConfigError) as excinfo:
        load_config(env)

    assert variable in str(excinfo.value)


def test_all_missing_variables_are_listed_together():
    with pytest.raises(ConfigError) as excinfo:
        load_config({})

    message = str(excinfo.value)
    assert BASE_URL_VAR in message
    assert EMAIL_VAR in message
    assert TOKEN_VAR in message


def test_missing_token_includes_how_to_create_one():
    env = {k: v for k, v in FULL_ENV.items() if k != TOKEN_VAR}

    with pytest.raises(ConfigError) as excinfo:
        load_config(env)

    assert "id.atlassian.com" in str(excinfo.value)


def test_error_message_never_contains_the_token():
    # A partially-configured env still holds the real token; the error must not
    # echo it back.
    env = {k: v for k, v in FULL_ENV.items() if k != EMAIL_VAR}

    with pytest.raises(ConfigError) as excinfo:
        load_config(env)

    assert TOKEN not in str(excinfo.value)


def test_repr_and_str_never_contain_the_token():
    config = load_config(FULL_ENV)

    assert TOKEN not in repr(config)
    assert TOKEN not in str(config)
    # The non-secret fields are still visible, so the repr stays useful.
    assert "dibts3.atlassian.net" in repr(config)


def test_config_is_frozen():
    config = load_config(FULL_ENV)

    with pytest.raises(Exception):
        config.api_token = "replaced"  # type: ignore[misc]


def test_load_config_reads_process_env_by_default(monkeypatch):
    for key, value in FULL_ENV.items():
        monkeypatch.setenv(key, value)

    assert load_config() == JiraConfig(
        base_url="https://dibts3.atlassian.net",
        email="someone@example.com",
        api_token=TOKEN,
    )
