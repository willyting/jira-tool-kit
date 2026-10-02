"""Resolve where a release task goes: board, sprint, project, issue types.

Everything here is read-only. Every ambiguity is an error rather than a guess,
because the next step writes issues that the whole team will see.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import ConfigError, NotFoundError

DEFAULT_BOARD_NAME = "VOR board"
DEFAULT_PARENT_ISSUE_TYPE = "Task"
SPRINT_NAME_TEMPLATE = "reseller {number}"
OPEN_SPRINT_STATES = "active,future"

# Preferred names when a project offers more than one subtask type.
_PREFERRED_SUBTASK_NAMES = ("sub-task", "subtask")

# How many sprint names to show when the requested one is not found.
_SUGGESTION_LIMIT = 10


@dataclass(frozen=True)
class ReleaseTarget:
    """Everything needed to create the release task, resolved and checked."""

    board_id: int
    board_name: str
    sprint_id: int
    sprint_name: str
    project_key: str
    parent_type_id: str
    parent_type_name: str
    subtask_type_id: str
    subtask_type_name: str


def sprint_name_for(number: int) -> str:
    return SPRINT_NAME_TEMPLATE.format(number=number)


def _normalise(name: str) -> str:
    return " ".join(name.split()).casefold()


# ----------------------------------------------------------------------
# Board
# ----------------------------------------------------------------------


async def resolve_board(
    client: Any, *, board_id: int | None, board_name: str
) -> dict[str, Any]:
    """Return the board's full record, by id or by exact name."""
    if board_id is None:
        boards = await client.list_boards(name=board_name)
        # The API's name filter is a substring match; we want exact.
        matches = [b for b in boards if str(b.get("name")) == board_name]
        if not matches:
            raise NotFoundError(f"No board named {board_name!r} was found.")
        if len(matches) > 1:
            listed = ", ".join(f"id={b.get('id')}" for b in matches)
            raise ConfigError(
                f"{len(matches)} boards are named {board_name!r} ({listed}). "
                "Use --board <id> instead."
            )
        board_id = int(matches[0]["id"])

    return await client.get_board(board_id)


# ----------------------------------------------------------------------
# Sprint
# ----------------------------------------------------------------------


def _matching(sprints: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    wanted = _normalise(name)
    return [s for s in sprints if _normalise(str(s.get("name", ""))) == wanted]


async def resolve_sprint(client: Any, board_id: int, number: int) -> dict[str, Any]:
    """Find the single open sprint named ``reseller <number>``."""
    name = sprint_name_for(number)
    open_sprints = await client.list_sprints(board_id, state=OPEN_SPRINT_STATES)
    matches = _matching(open_sprints, name)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        described = "; ".join(
            f"id={m.get('id')} state={m.get('state')} "
            f"start={m.get('startDate') or 'none'}"
            for m in matches
        )
        raise ConfigError(
            f"{len(matches)} open sprints on this board are named {name!r}: "
            f"{described}. Rename the duplicates in Jira and re-run."
        )

    # Only look at closed sprints to explain the failure; they are never used.
    closed = _matching(await client.list_sprints(board_id, state="closed"), name)
    if closed:
        raise ConfigError(
            f"Sprint {name!r} is closed and cannot take new issues."
        )
    raise NotFoundError(_no_match_message(open_sprints, name))


def _no_match_message(sprints: list[dict[str, Any]], name: str) -> str:
    if not sprints:
        return f"No sprint named {name!r} was found; the board has no open sprints."

    # Most recent first; sprints with no start date (future ones) lead, since
    # a release task is usually created ahead of its sprint.
    def sort_key(sprint: dict[str, Any]) -> tuple[int, str]:
        start = sprint.get("startDate") or ""
        return (1 if not start else 0, start)

    recent = sorted(sprints, key=sort_key, reverse=True)[:_SUGGESTION_LIMIT]
    listed = ", ".join(repr(str(s.get("name", ""))) for s in recent)
    return f"No open sprint named {name!r} was found. Open sprints: {listed}"


# ----------------------------------------------------------------------
# Project
# ----------------------------------------------------------------------


async def resolve_project(
    client: Any, board: dict[str, Any], *, override: str | None
) -> str:
    if override:
        return override.strip()

    location_key = (board.get("location") or {}).get("projectKey")
    if location_key:
        return str(location_key)

    projects = await client.list_board_projects(int(board["id"]))
    keys = [str(p.get("key")) for p in projects if p.get("key")]
    if len(keys) == 1:
        return keys[0]
    if not keys:
        raise ConfigError(
            f"Board {board.get('name')!r} is not associated with any project. "
            "Pass --project <KEY>."
        )
    raise ConfigError(
        f"Board {board.get('name')!r} spans several projects: {', '.join(keys)}. "
        "Pass --project <KEY>."
    )


# ----------------------------------------------------------------------
# Issue types
# ----------------------------------------------------------------------


def resolve_issue_types(
    issue_types: list[dict[str, Any]], project_key: str, parent_type_name: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pick (parent type, subtask type) from a project's creatable types."""
    standard = [t for t in issue_types if not t.get("subtask")]
    subtask = [t for t in issue_types if t.get("subtask")]

    wanted = parent_type_name.strip().casefold()
    parents = [t for t in standard if str(t.get("name", "")).casefold() == wanted]
    if not parents:
        available = ", ".join(str(t.get("name")) for t in standard) or "none"
        raise ConfigError(
            f"Project {project_key} has no issue type named {parent_type_name!r}. "
            f"Available: {available}. Use --issue-type."
        )

    if not subtask:
        raise ConfigError(f"Project {project_key} does not allow subtasks.")
    if len(subtask) > 1:
        preferred = [
            t
            for t in subtask
            if str(t.get("name", "")).casefold() in _PREFERRED_SUBTASK_NAMES
        ]
        if len(preferred) != 1:
            listed = ", ".join(str(t.get("name")) for t in subtask)
            raise ConfigError(
                f"Project {project_key} has several subtask types ({listed}) and "
                "none is named 'Sub-task' or 'Subtask'."
            )
        subtask = preferred

    return parents[0], subtask[0]


# ----------------------------------------------------------------------
# All together
# ----------------------------------------------------------------------


async def resolve_target(
    client: Any,
    *,
    sprint_number: int,
    board_id: int | None,
    board_name: str,
    project: str | None,
    parent_type_name: str,
) -> ReleaseTarget:
    board = await resolve_board(client, board_id=board_id, board_name=board_name)
    resolved_board_id = int(board["id"])

    sprint = await resolve_sprint(client, resolved_board_id, sprint_number)
    project_key = await resolve_project(client, board, override=project)

    issue_types = await client.get_create_issue_types(project_key)
    parent_type, subtask_type = resolve_issue_types(
        issue_types, project_key, parent_type_name
    )

    return ReleaseTarget(
        board_id=resolved_board_id,
        board_name=str(board.get("name", "")),
        sprint_id=int(sprint["id"]),
        sprint_name=str(sprint.get("name", "")),
        project_key=project_key,
        parent_type_id=str(parent_type["id"]),
        parent_type_name=str(parent_type.get("name", "")),
        subtask_type_id=str(subtask_type["id"]),
        subtask_type_name=str(subtask_type.get("name", "")),
    )
