from conftest import DONE_STATUS_ID, DONE_STATUS_NAME, FakeClient, raw_issue

from jira_sprint_estimates.issues import (
    ISSUE_FIELDS,
    PARENT_BATCH_SIZE,
    fetch_candidate_issues,
    parse_issue,
)


# ----------------------------------------------------------------------
# Field flattening
# ----------------------------------------------------------------------


def test_parse_issue_flattens_nested_fields():
    parsed = parse_issue(
        raw_issue(
            "PROJ-1",
            summary="Do the thing",
            issue_type="Sub-task",
            is_subtask=True,
            parent="PROJ-9",
            assignee="Grace Hopper",
            estimate_seconds=7200,
            status_id=DONE_STATUS_ID,
            status_name=DONE_STATUS_NAME,
        )
    )

    assert parsed.key == "PROJ-1"
    assert parsed.summary == "Do the thing"
    assert parsed.issue_type == "Sub-task"
    assert parsed.is_subtask is True
    assert parsed.parent_key == "PROJ-9"
    assert parsed.assignee == "Grace Hopper"
    assert parsed.original_estimate_seconds == 7200
    assert parsed.status_id == DONE_STATUS_ID


def test_parse_issue_tolerates_missing_optional_fields():
    parsed = parse_issue(
        raw_issue("PROJ-2", assignee=None, estimate_seconds=None, parent=None)
    )

    assert parsed.assignee is None
    assert parsed.original_estimate_seconds is None
    assert parsed.parent_key is None
    assert parsed.is_subtask is False


# ----------------------------------------------------------------------
# Two-phase fetch
# ----------------------------------------------------------------------


async def test_subtasks_are_fetched_via_their_parent():
    parent = raw_issue("PROJ-1", subtasks=["PROJ-2", "PROJ-3", "PROJ-4"])
    children = [
        raw_issue("PROJ-2", is_subtask=True, parent="PROJ-1"),
        raw_issue("PROJ-3", is_subtask=True, parent="PROJ-1"),
        raw_issue("PROJ-4", is_subtask=True, parent="PROJ-1"),
    ]
    client = FakeClient(sprint_issues=[parent], child_issues={"PROJ-1": children})

    result = await fetch_candidate_issues(client, 99)

    assert sorted(result.keys) == ["PROJ-1", "PROJ-2", "PROJ-3", "PROJ-4"]
    assert result.discrepancies == []


async def test_issue_in_both_phases_appears_once():
    parent = raw_issue("PROJ-1", subtasks=["PROJ-2"])
    subtask = raw_issue("PROJ-2", is_subtask=True, parent="PROJ-1")
    client = FakeClient(
        # The subtask is itself a sprint member AND a child of PROJ-1.
        sprint_issues=[parent, subtask],
        child_issues={"PROJ-1": [subtask]},
    )

    result = await fetch_candidate_issues(client, 99)

    assert result.keys.count("PROJ-2") == 1
    assert len(result) == 2


async def test_subtasks_are_not_queried_for_children():
    subtask = raw_issue("PROJ-2", is_subtask=True, parent="PROJ-1")
    client = FakeClient(sprint_issues=[subtask])

    await fetch_candidate_issues(client, 99)

    parent_queries = [q for q in client.jql_queries if q.startswith("parent in")]
    assert parent_queries == []


async def test_parent_keys_are_batched_at_fifty():
    parents = [raw_issue(f"PROJ-{n}") for n in range(1, PARENT_BATCH_SIZE + 6)]
    client = FakeClient(sprint_issues=parents)

    await fetch_candidate_issues(client, 99)

    parent_queries = [q for q in client.jql_queries if q.startswith("parent in")]
    assert len(parent_queries) == 2

    first_batch = parent_queries[0][len("parent in (") : -1].split(", ")
    second_batch = parent_queries[1][len("parent in (") : -1].split(", ")
    assert len(first_batch) == PARENT_BATCH_SIZE
    assert len(second_batch) == 5


async def test_empty_sprint_returns_empty_set_without_child_query():
    client = FakeClient(sprint_issues=[])

    result = await fetch_candidate_issues(client, 99)

    assert len(result) == 0
    assert result.issues == []
    assert [q for q in client.jql_queries if q.startswith("parent in")] == []


async def test_declared_subtask_never_returned_is_reported_as_a_discrepancy():
    # PROJ-1 says it has two subtasks, but the parent query only returns one.
    parent = raw_issue("PROJ-1", subtasks=["PROJ-2", "PROJ-3"])
    client = FakeClient(
        sprint_issues=[parent],
        child_issues={"PROJ-1": [raw_issue("PROJ-2", is_subtask=True, parent="PROJ-1")]},
    )

    result = await fetch_candidate_issues(client, 99)

    assert result.discrepancies == ["PROJ-3"]
    assert "PROJ-3" not in result.keys


async def test_search_requests_every_required_field():
    captured: list[list[str]] = []

    class RecordingClient(FakeClient):
        async def search_jql(self, jql, fields, **kwargs):
            captured.append(list(fields))
            return await super().search_jql(jql, fields, **kwargs)

    client = RecordingClient(sprint_issues=[raw_issue("PROJ-1")])
    await fetch_candidate_issues(client, 99)

    for requested in captured:
        for required in (
            "summary",
            "issuetype",
            "status",
            "parent",
            "assignee",
            "timeoriginalestimate",
        ):
            assert required in requested
    assert set(ISSUE_FIELDS) >= {"summary", "timeoriginalestimate", "parent"}


async def test_candidate_set_retains_parent_child_relationships():
    parent = raw_issue("PROJ-1", issue_type="Story", subtasks=["PROJ-2"])
    child = raw_issue(
        "PROJ-2", issue_type="Sub-task", is_subtask=True, parent="PROJ-1"
    )
    client = FakeClient(sprint_issues=[parent], child_issues={"PROJ-1": [child]})

    result = await fetch_candidate_issues(client, 99)
    by_key = {issue.key: issue for issue in result.issues}

    assert by_key["PROJ-1"].is_subtask is False
    assert by_key["PROJ-1"].parent_key is None
    assert by_key["PROJ-1"].issue_type == "Story"
    assert by_key["PROJ-2"].is_subtask is True
    assert by_key["PROJ-2"].parent_key == "PROJ-1"
    assert by_key["PROJ-2"].issue_type == "Sub-task"


async def test_sprint_query_uses_the_sprint_id():
    client = FakeClient(sprint_issues=[])

    await fetch_candidate_issues(client, 1234)

    assert client.jql_queries[0] == "sprint = 1234"
