"""Credential loading. Environment only - nothing is read from the repo."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .errors import ConfigError

BASE_URL_VAR = "JIRA_BASE_URL"
EMAIL_VAR = "JIRA_EMAIL"
TOKEN_VAR = "JIRA_API_TOKEN"

_TOKEN_HELP = (
    "Create one at https://id.atlassian.com/manage-profile/security/api-tokens"
)


@dataclass(frozen=True)
class JiraConfig:
    """Everything needed to authenticate against a Jira Cloud site."""

    base_url: str
    email: str
    # repr=False so the token cannot leak through an accidental repr() of a
    # config object in a log line or traceback frame.
    api_token: str = field(repr=False)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"JiraConfig(base_url={self.base_url!r}, email={self.email!r})"


def load_config(env: dict[str, str] | None = None) -> JiraConfig:
    """Read credentials from the environment.

    Raises ConfigError naming the specific missing variable. Values that are
    present but empty or whitespace-only count as missing - an exported-but-blank
    variable is a mistake, not a choice.
    """
    source = os.environ if env is None else env

    missing = [
        name
        for name in (BASE_URL_VAR, EMAIL_VAR, TOKEN_VAR)
        if not (source.get(name) or "").strip()
    ]
    if missing:
        listed = ", ".join(missing)
        hint = f" {_TOKEN_HELP}" if TOKEN_VAR in missing else ""
        plural = "s" if len(missing) > 1 else ""
        raise ConfigError(
            f"Missing required environment variable{plural}: {listed}.{hint}"
        )

    return JiraConfig(
        base_url=source[BASE_URL_VAR].strip().rstrip("/"),
        email=source[EMAIL_VAR].strip(),
        api_token=source[TOKEN_VAR].strip(),
    )
