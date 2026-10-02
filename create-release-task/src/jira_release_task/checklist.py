"""The fixed shape of a release task.

The dash counts in PARENT_SUMMARY are part of the format (7, then 35) and are
pinned by a test. Changing the checklist is a code change on purpose.
"""

from __future__ import annotations

PARENT_SUMMARY = "release {number} ------- {version} -----------------------------------"

SUBTASK_SUMMARIES: tuple[str, ...] = (
    "create portal branch",
    "create backend branch",
    "check release note",
    "test vpp on stage",
    "run e2e test on stage",
    "check new feature on stage",
    "run api test on stage",
    "check sap on stage",
    "check on prod",
)


def build_parent_summary(number: int, version: str) -> str:
    """The version is used verbatim apart from outer whitespace."""
    return PARENT_SUMMARY.format(number=number, version=version.strip())
