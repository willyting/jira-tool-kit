import pytest
from conftest import BOARD, SPRINT_97, STORY_TYPE, SUBTASK_TYPE, TASK_TYPE, FakeClient

from jira_release_task.errors import ConfigError, NotFoundError
from jira_release_task.targets import (
    resolve_board,
    resolve_issue_types,
    resolve_project,
    resolve_sprint,
    resolve_target,
)

# ----------------------------------------------------------------------
# Board
# ----------------------------------------------------------------------


async def test_default_board_name_resolves_exactly():
    # "VOR board v2" also contains the name; only the exact one may match.
    client = FakeClient(boards=[BOARD, {"id": 13, "name": "VOR board v2"}])
    board = await resolve_board(client, board_id=None, board_name="VOR board")
    assert board["id"] == 12


async def test_board_name_not_found():
    with pytest.raises(NotFoundError, match="No board named 'Nope'"):
        await resolve_board(FakeClient(), board_id=None, board_name="Nope")


async def test_board_name_ambiguous_lists_ids():
    client = FakeClient(boards=[BOARD, {**BOARD, "id": 99}])
    with pytest.raises(ConfigError, match=r"id=12, id=99.*--board"):
        await resolve_board(client, board_id=None, board_name="VOR board")


async def test_board_by_id_skips_name_lookup():
    board = await resolve_board(FakeClient(), board_id=12, board_name="ignored")
    assert board["name"] == "VOR board"


# ----------------------------------------------------------------------
# Sprint
# ----------------------------------------------------------------------


async def test_future_sprint_found_ignoring_case_and_spacing():
    sprint = {**SPRINT_97, "name": "Reseller  97"}
    client = FakeClient(sprints=[sprint])
    assert (await resolve_sprint(client, 12, 97))["id"] == 501
    assert client.sprint_state_requests[0] == "active,future"


async def test_active_sprint_found():
    client = FakeClient(sprints=[{**SPRINT_97, "state": "active"}])
    assert (await resolve_sprint(client, 12, 97))["id"] == 501


async def test_closed_sprint_is_rejected_as_closed():
    client = FakeClient(sprints=[{**SPRINT_97, "state": "closed"}])
    with pytest.raises(ConfigError, match="is closed"):
        await resolve_sprint(client, 12, 97)


async def test_missing_sprint_lists_open_sprints():
    others = [{"id": i, "name": f"reseller {i}", "state": "future"} for i in range(80, 95)]
    client = FakeClient(sprints=others)
    with pytest.raises(NotFoundError) as info:
        await resolve_sprint(client, 12, 97)
    message = str(info.value)
    assert "No open sprint named 'reseller 97'" in message
    assert message.count("'reseller ") == 1 + 10  # the wanted name + 10 suggestions


async def test_ambiguous_sprint_lists_candidates():
    client = FakeClient(sprints=[SPRINT_97, {**SPRINT_97, "id": 502, "state": "active"}])
    with pytest.raises(ConfigError, match=r"id=501 state=future.*id=502 state=active"):
        await resolve_sprint(client, 12, 97)


async def test_sprint_number_does_not_partially_match():
    with pytest.raises(NotFoundError):
        await resolve_sprint(FakeClient(sprints=[SPRINT_97]), 12, 9)


# ----------------------------------------------------------------------
# Project
# ----------------------------------------------------------------------


async def test_project_from_board_location():
    assert await resolve_project(FakeClient(), BOARD, override=None) == "VOR"


async def test_project_from_single_board_project():
    board = {"id": 12, "name": "VOR board"}
    client = FakeClient(board_projects=[{"key": "VOR"}])
    assert await resolve_project(client, board, override=None) == "VOR"


async def test_multi_project_board_needs_override():
    board = {"id": 12, "name": "VOR board"}
    client = FakeClient(board_projects=[{"key": "VOR"}, {"key": "RES"}])
    with pytest.raises(ConfigError, match=r"VOR, RES.*--project"):
        await resolve_project(client, board, override=None)


async def test_project_override_wins():
    assert await resolve_project(FakeClient(), BOARD, override="RES") == "RES"


# ----------------------------------------------------------------------
# Issue types
# ----------------------------------------------------------------------


def test_standard_types():
    parent, sub = resolve_issue_types([STORY_TYPE, TASK_TYPE, SUBTASK_TYPE], "VOR", "task")
    assert (parent["id"], sub["id"]) == ("10002", "10003")


def test_parent_type_missing_lists_available():
    with pytest.raises(ConfigError, match=r"Available: Story"):
        resolve_issue_types([STORY_TYPE, SUBTASK_TYPE], "VOR", "Task")


def test_no_subtask_type():
    with pytest.raises(ConfigError, match="does not allow subtasks"):
        resolve_issue_types([TASK_TYPE], "VOR", "Task")


def test_several_subtask_types_prefers_sub_task():
    qa = {"id": "20", "name": "QA Check", "subtask": True}
    _, sub = resolve_issue_types([TASK_TYPE, qa, SUBTASK_TYPE], "VOR", "Task")
    assert sub["id"] == "10003"


def test_ambiguous_subtask_types():
    qa = {"id": "20", "name": "QA Check", "subtask": True}
    dev = {"id": "21", "name": "Dev Step", "subtask": True}
    with pytest.raises(ConfigError, match="QA Check, Dev Step"):
        resolve_issue_types([TASK_TYPE, qa, dev], "VOR", "Task")


# ----------------------------------------------------------------------
# Everything together
# ----------------------------------------------------------------------


async def test_resolve_target_end_to_end():
    target = await resolve_target(
        FakeClient(),
        sprint_number=97,
        board_id=None,
        board_name="VOR board",
        project=None,
        parent_type_name="Task",
    )
    assert (target.board_id, target.sprint_id, target.project_key) == (12, 501, "VOR")
    assert (target.parent_type_id, target.subtask_type_id) == ("10002", "10003")
