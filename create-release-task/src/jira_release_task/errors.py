"""Typed errors so callers can tell configuration problems from data problems.

Every error carries a message that is safe to show a user directly: no
credentials, no tracebacks required to understand what went wrong.
"""

from __future__ import annotations

from typing import Any


class JiraToolError(Exception):
    """Base for every error this tool raises deliberately."""


class ConfigError(JiraToolError):
    """Something about the local environment or arguments is wrong."""


class JiraApiError(JiraToolError):
    """Base for errors originating from a Jira HTTP response."""

    def __init__(self, message: str, *, status_code: int | None = None, endpoint: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.endpoint = endpoint


class AuthError(JiraApiError):
    """401 - Jira rejected the credentials."""


class PermissionError_(JiraApiError):
    """403 - the credentials are valid but lack access.

    Named with a trailing underscore so it cannot shadow the builtin
    ``PermissionError`` for anyone reading this module.
    """


class NotFoundError(JiraApiError):
    """404 - the board, sprint, or issue does not exist."""


class InvalidQueryError(JiraApiError):
    """400 - Jira rejected the JQL or request body."""


class EndpointGoneError(JiraApiError):
    """410 - Atlassian has removed the endpoint we called."""


class TransientError(JiraApiError):
    """429 or 5xx - worth retrying, and reported if retries run out."""


class PaginationError(JiraApiError):
    """A paginated response failed to advance, so we refuse to loop."""


class WriteUncertainError(JiraApiError):
    """A write failed in a way that means it may still have been applied.

    Network failures and 5xx responses on a create are ambiguous: Jira may have
    committed the issue before the connection dropped. These are never retried,
    because a retry could create a duplicate.
    """


class PartialWriteError(JiraToolError):
    """A run stopped partway; ``created`` lists what exists as a result.

    Nothing is rolled back - deleting issues is more dangerous than leaving
    them - so the caller must show ``created`` before the error.
    """

    def __init__(self, message: str, *, created: list[Any], cause: Exception) -> None:
        super().__init__(message)
        self.created = created
        self.cause = cause


# Kept as an alias so callers can write ``except errors.PermissionDenied``.
PermissionDenied = PermissionError_
