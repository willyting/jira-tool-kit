"""Resolve a human sprint name to one sprint, and derive its time window.

Every timestamp in this tool is compared in UTC. Jira returns sprint dates with
assorted offsets, so normalisation happens here, once, at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .errors import ConfigError, NotFoundError

# How many sprint names to show when the requested one is not found.
_SUGGESTION_LIMIT = 10


@dataclass(frozen=True)
class Sprint:
    """A resolved sprint and the window used to judge completion."""

    id: int
    name: str
    state: str
    start: datetime
    end: datetime
    is_active: bool

    @property
    def window(self) -> tuple[datetime, datetime]:
        return self.start, self.end


def parse_jira_datetime(raw: str | None) -> datetime | None:
    """Parse a Jira timestamp into an aware UTC datetime.

    Jira Cloud emits ISO-8601 with a compact offset (``+0000``) that
    ``fromisoformat`` did not accept before 3.11 and still does not accept in
    every shape, so the offset is normalised first. A naive timestamp is
    assumed to be UTC rather than silently taking the local zone.
    """
    if not raw:
        return None

    text = raw.strip().replace("Z", "+00:00")
    # "+0000" -> "+00:00", leaving already-colonised offsets alone.
    if len(text) >= 5 and text[-5] in "+-" and text[-3] != ":":
        text = f"{text[:-2]}:{text[-2:]}"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalise(name: str) -> str:
    return " ".join(name.split()).casefold()


def find_sprint_by_name(sprints: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Pick exactly one sprint whose name matches, ignoring case and padding."""
    wanted = _normalise(name)
    matches = [s for s in sprints if _normalise(str(s.get("name", ""))) == wanted]

    if not matches:
        raise NotFoundError(_no_match_message(sprints, name))
    if len(matches) > 1:
        raise ConfigError(_ambiguous_message(matches, name))

    return matches[0]


def _no_match_message(sprints: list[dict[str, Any]], name: str) -> str:
    if not sprints:
        return f"No sprint named {name!r} was found; the board has no sprints."

    # Most recent first, so the suggestions are the ones a user is likely to
    # have meant. Sprints without a start date sort last.
    def sort_key(sprint: dict[str, Any]) -> tuple[int, str]:
        start = sprint.get("startDate") or ""
        return (0 if start else 1, start)

    recent = sorted(sprints, key=sort_key, reverse=True)[:_SUGGESTION_LIMIT]
    listed = ", ".join(repr(str(s.get("name", ""))) for s in recent)
    return (
        f"No sprint named {name!r} was found on this board. "
        f"Recent sprints: {listed}"
    )


def _ambiguous_message(matches: list[dict[str, Any]], name: str) -> str:
    described = "; ".join(
        f"id={m.get('id')} state={m.get('state')} start={m.get('startDate') or 'none'}"
        for m in matches
    )
    return (
        f"{len(matches)} sprints on this board are named {name!r}: {described}. "
        "Disambiguate by sprint id."
    )


def resolve_sprint(
    sprints: list[dict[str, Any]],
    name: str,
    *,
    now: datetime | None = None,
) -> Sprint:
    """Resolve a sprint by name and derive its UTC completion window.

    Window start is the sprint's ``startDate``. Window end is ``completeDate``
    when present, else ``endDate``, else - for an active sprint - now.
    """
    raw = find_sprint_by_name(sprints, name)
    return build_sprint(raw, now=now)


def build_sprint(raw: dict[str, Any], *, now: datetime | None = None) -> Sprint:
    sprint_name = str(raw.get("name", ""))
    state = str(raw.get("state", "") or "").lower()

    start = parse_jira_datetime(raw.get("startDate"))
    if start is None:
        raise ConfigError(
            f"Sprint {sprint_name!r} has no start date, so it has not started "
            "and cannot be reported on."
        )

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    complete = parse_jira_datetime(raw.get("completeDate"))
    scheduled_end = parse_jira_datetime(raw.get("endDate"))

    is_active = state == "active"
    if is_active:
        # An in-progress sprint has no completion time yet; "so far" is now.
        end = current
    elif complete is not None:
        end = complete
    elif scheduled_end is not None:
        end = scheduled_end
    else:
        end = current

    return Sprint(
        id=int(raw["id"]),
        name=sprint_name,
        state=state,
        start=start,
        end=end,
        is_active=is_active,
    )


def in_window(moment: datetime, start: datetime, end: datetime) -> bool:
    """Inclusive on both ends, compared in UTC."""
    point = moment.astimezone(timezone.utc)
    return start <= point <= end
