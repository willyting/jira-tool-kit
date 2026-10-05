import pytest
from conftest import TARGET, FakeClient

from jira_release_task.checklist import SUBTASK_SUMMARIES, build_parent_summary
from jira_release_task.errors import PartialWriteError
from jira_release_task.execute import execute_plan
from jira_release_task.plan import build_plan

SUMMARY = build_parent_summary(97, "2.14.0")


async def run(client):
    plan = await build_plan(client, TARGET, sprint_number=97, version="2.14.0")
    return await execute_plan(client, plan)


async def test_full_run_order():
    client = FakeClient()
    result = await run(client)

    first, *subs = client.create_calls
    assert first == {"project": "VOR", "type_id": "10002", "summary": SUMMARY, "parent": None}
    assert client.sprint_adds == [(501, [result.parent.key])]
    assert [c["summary"] for c in subs] == list(SUBTASK_SUMMARIES)
    assert subs[0]["summary"] == "check feature toggle SRE request"
    assert all(c["parent"] == result.parent.key and c["type_id"] == "10003" for c in subs)
    assert result.created_count == 11


async def test_sprint_add_happens_before_any_subtask():
    events = []
    client = FakeClient()
    create, add = client.create_issue, client.add_issues_to_sprint

    async def logged_create(*a, **kw):
        events.append("create-sub" if kw.get("parent_key") else "create-parent")
        return await create(*a, **kw)

    async def logged_add(*a, **kw):
        events.append("sprint")
        return await add(*a, **kw)

    client.create_issue, client.add_issues_to_sprint = logged_create, logged_add
    await run(client)
    assert events[:3] == ["create-parent", "sprint", "create-sub"]


async def test_reused_parent_is_not_moved():
    client = FakeClient()
    client.seed(SUMMARY)
    result = await run(client)
    assert client.sprint_adds == []
    assert not result.parent.created
    assert result.created_count == 10


async def test_failure_at_fifth_subtask_stops_and_reports():
    # Call 1 is the parent, so the fifth subtask is call 6.
    client = FakeClient(fail_create_on=6)
    with pytest.raises(PartialWriteError) as info:
        await run(client)

    created = info.value.created
    assert len(created) == 5  # parent + 4 subtasks
    assert [c.summary for c in created[1:]] == list(SUBTASK_SUMMARIES[:4])
    assert len(client.create_calls) == 6  # nothing attempted after the failure
    assert "Re-run" in str(info.value)


async def test_sprint_add_failure_names_orphan_and_stops():
    client = FakeClient(fail_sprint_add=True)
    with pytest.raises(PartialWriteError) as info:
        await run(client)

    parent_key = info.value.created[0].key
    assert len(client.create_calls) == 1
    assert parent_key in str(info.value)
    assert "outside the sprint" in str(info.value)


async def test_parent_create_failure_reports_nothing_created():
    client = FakeClient(fail_create_on=1)
    with pytest.raises(PartialWriteError) as info:
        await run(client)
    assert info.value.created == []


async def test_second_run_makes_no_writes():
    client = FakeClient()
    await run(client)
    writes = client.write_count

    result = await run(client)
    assert client.write_count == writes
    assert result.created_count == 0


async def test_resume_after_partial_failure_creates_exactly_missing():
    client = FakeClient(fail_create_on=6)
    with pytest.raises(PartialWriteError):
        await run(client)

    client._fail_create_on = None
    before = len(client.create_calls)
    result = await run(client)

    new_calls = client.create_calls[before:]
    assert [c["summary"] for c in new_calls] == list(SUBTASK_SUMMARIES[4:])
    assert result.created_count == 6
    assert [s.summary for s in result.subtasks] == list(SUBTASK_SUMMARIES)
