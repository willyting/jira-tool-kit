import pytest
from conftest import TARGET, FakeClient

from jira_release_task.checklist import SUBTASK_SUMMARIES, build_parent_summary
from jira_release_task.errors import ConfigError
from jira_release_task.plan import build_plan

SUMMARY = build_parent_summary(97, "2.14.0")


async def plan_for(client):
    return await build_plan(client, TARGET, sprint_number=97, version="2.14.0")


async def test_query_shape():
    client = FakeClient()
    await plan_for(client)
    assert client.jql_queries == ["sprint = 501 AND issuetype = 10002"]


async def test_no_existing_task_plans_everything():
    plan = await plan_for(FakeClient())
    assert plan.parent.needs_create and plan.parent.summary == SUMMARY
    assert [s.summary for s in plan.subtasks] == list(SUBTASK_SUMMARIES)
    assert plan.to_create == 10


async def test_existing_task_is_reused():
    client = FakeClient()
    key = client.seed(SUMMARY)
    plan = await plan_for(client)
    assert plan.parent.existing_key == key
    assert plan.to_create == 9


async def test_existing_summary_compared_after_trim():
    client = FakeClient()
    key = client.seed(f"  {SUMMARY} ")
    assert (await plan_for(client)).parent.existing_key == key


async def test_near_miss_is_not_a_match():
    client = FakeClient()
    client.seed("release 97 ------ 2.14.0 ---")
    assert (await plan_for(client)).parent.needs_create


async def test_task_in_other_sprint_is_not_a_match():
    client = FakeClient()
    client.seed(SUMMARY, sprint=400)
    assert (await plan_for(client)).parent.needs_create


async def test_duplicate_tasks_fail_listing_keys():
    client = FakeClient()
    a = client.seed(SUMMARY)
    b = client.seed(SUMMARY)
    with pytest.raises(ConfigError, match=f"{a}, {b}"):
        await plan_for(client)


async def test_partial_subtasks_plan_only_missing_in_order():
    client = FakeClient()
    parent = client.seed(SUMMARY)
    client.seed("check release note", type_id="10003", parent=parent)
    client.seed("create portal branch", type_id="10003", parent=parent)

    plan = await plan_for(client)
    missing = [s.summary for s in plan.subtasks if s.needs_create]
    assert missing == [s for s in SUBTASK_SUMMARIES if s not in {"check release note", "create portal branch"}]
    assert plan.to_create == 7


async def test_complete_parent_plans_nothing():
    client = FakeClient()
    parent = client.seed(SUMMARY)
    for s in SUBTASK_SUMMARIES:
        client.seed(s, type_id="10003", parent=parent)
    assert (await plan_for(client)).to_create == 0


async def test_extra_subtasks_are_ignored():
    client = FakeClient()
    parent = client.seed(SUMMARY)
    client.seed("hotfix follow-up", type_id="10003", parent=parent)
    plan = await plan_for(client)
    assert "hotfix follow-up" not in [s.summary for s in plan.subtasks]
    assert plan.to_create == 9


async def test_subtask_match_is_case_sensitive():
    client = FakeClient()
    parent = client.seed(SUMMARY)
    client.seed("Check On Prod", type_id="10003", parent=parent)
    plan = await plan_for(client)
    assert plan.subtasks[-1].needs_create
