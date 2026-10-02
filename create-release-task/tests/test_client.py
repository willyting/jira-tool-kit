import json

import httpx
import pytest
import respx

from jira_release_task.client import (
    BOARD_SPRINT_ENDPOINT,
    CREATEMETA_ISSUETYPES_ENDPOINT,
    ISSUE_ENDPOINT,
    SEARCH_JQL_ENDPOINT,
    SPRINT_ISSUE_ENDPOINT,
    JiraClient,
    _basic_auth_header,
)
from jira_release_task.config import JiraConfig
from jira_release_task.errors import (
    AuthError,
    EndpointGoneError,
    InvalidQueryError,
    NotFoundError,
    PaginationError,
    PermissionError_,
    TransientError,
    WriteUncertainError,
)

BASE_URL = "https://jira.example.test"
TOKEN = "secret-token"
CONFIG = JiraConfig(base_url=BASE_URL, email="someone@example.com", api_token=TOKEN)


class RecordingSleep:
    """Stands in for asyncio.sleep so retry tests do not actually wait."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def make_client(**kwargs) -> JiraClient:
    kwargs.setdefault("sleep", RecordingSleep())
    kwargs.setdefault("backoff_base_seconds", 0.01)
    return JiraClient(CONFIG, **kwargs)


def body_of(call) -> dict:
    return json.loads(call.request.content)


# ----------------------------------------------------------------------
# Auth and search
# ----------------------------------------------------------------------


@respx.mock(base_url=BASE_URL)
async def test_requests_carry_basic_auth(respx_mock):
    route = respx_mock.get("/rest/agile/1.0/board/12").mock(
        return_value=httpx.Response(200, json={"id": 12})
    )
    async with make_client() as client:
        await client.get_board(12)

    assert route.calls.last.request.headers["Authorization"] == _basic_auth_header(
        "someone@example.com", TOKEN
    )


async def test_search_requires_explicit_fields():
    async with make_client() as client:
        with pytest.raises(ValueError):
            await client.search_jql("sprint = 1", [])


@respx.mock(base_url=BASE_URL)
async def test_search_follows_cursor_and_sends_fields(respx_mock):
    route = respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, json={"issues": [{"key": "A-1"}], "nextPageToken": "t1"}),
            httpx.Response(200, json={"issues": [{"key": "A-2"}]}),
        ]
    )
    async with make_client() as client:
        issues = await client.search_jql("sprint = 1", ["summary"])

    assert [i["key"] for i in issues] == ["A-1", "A-2"]
    assert body_of(route.calls[0])["fields"] == ["summary"]
    assert body_of(route.calls[1])["nextPageToken"] == "t1"


@respx.mock(base_url=BASE_URL)
async def test_search_refuses_repeated_cursor(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"issues": [{"key": "A-1"}], "nextPageToken": "same"})
    )
    async with make_client() as client:
        with pytest.raises(PaginationError):
            await client.search_jql("sprint = 1", ["summary"])


@respx.mock(base_url=BASE_URL)
async def test_search_refuses_empty_page_with_cursor(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"issues": [], "nextPageToken": "t"})
    )
    async with make_client() as client:
        with pytest.raises(PaginationError):
            await client.search_jql("sprint = 1", ["summary"])


# ----------------------------------------------------------------------
# Agile reads
# ----------------------------------------------------------------------


@respx.mock(base_url=BASE_URL)
async def test_sprints_span_pages_and_pass_state(respx_mock):
    route = respx_mock.get(BOARD_SPRINT_ENDPOINT.format(board_id=12)).mock(
        side_effect=[
            httpx.Response(200, json={"values": [{"id": 1}], "isLast": False}),
            httpx.Response(200, json={"values": [{"id": 2}], "isLast": True}),
        ]
    )
    async with make_client() as client:
        sprints = await client.list_sprints(12, state="active,future")

    assert [s["id"] for s in sprints] == [1, 2]
    assert route.calls[0].request.url.params["state"] == "active,future"
    assert route.calls[1].request.url.params["startAt"] == "1"


@respx.mock(base_url=BASE_URL)
async def test_createmeta_reads_issue_types_key_and_paginates(respx_mock):
    route = respx_mock.get(CREATEMETA_ISSUETYPES_ENDPOINT.format(project="VOR")).mock(
        side_effect=[
            httpx.Response(
                200,
                json={"issueTypes": [{"id": "1", "name": "Task", "subtask": False}], "total": 2},
            ),
            httpx.Response(
                200,
                json={"issueTypes": [{"id": "2", "name": "Sub-task", "subtask": True}], "total": 2},
            ),
        ]
    )
    async with make_client() as client:
        types = await client.get_create_issue_types("VOR")

    assert [(t["name"], t["subtask"]) for t in types] == [("Task", False), ("Sub-task", True)]
    assert route.call_count == 2


# ----------------------------------------------------------------------
# Writes
# ----------------------------------------------------------------------


@respx.mock(base_url=BASE_URL)
async def test_create_task_payload(respx_mock):
    route = respx_mock.post(ISSUE_ENDPOINT).mock(
        return_value=httpx.Response(201, json={"id": "10500", "key": "VOR-500"})
    )
    async with make_client() as client:
        made = await client.create_issue("VOR", "10002", "release 97 ------- 1.0 ---")

    assert made == {"key": "VOR-500", "id": "10500"}
    assert body_of(route.calls.last) == {
        "fields": {
            "project": {"key": "VOR"},
            "issuetype": {"id": "10002"},
            "summary": "release 97 ------- 1.0 ---",
        }
    }


@respx.mock(base_url=BASE_URL)
async def test_create_subtask_carries_parent(respx_mock):
    route = respx_mock.post(ISSUE_ENDPOINT).mock(
        return_value=httpx.Response(201, json={"id": "1", "key": "VOR-501"})
    )
    async with make_client() as client:
        await client.create_issue("VOR", "10003", "check on prod", parent_key="VOR-500")

    assert body_of(route.calls.last)["fields"]["parent"] == {"key": "VOR-500"}


@respx.mock(base_url=BASE_URL)
async def test_add_to_sprint_accepts_204(respx_mock):
    route = respx_mock.post(SPRINT_ISSUE_ENDPOINT.format(sprint_id=501)).mock(
        return_value=httpx.Response(204)
    )
    async with make_client() as client:
        await client.add_issues_to_sprint(501, ["VOR-500"])

    assert body_of(route.calls.last) == {"issues": ["VOR-500"]}


@respx.mock(base_url=BASE_URL)
async def test_write_not_retried_on_500(respx_mock):
    route = respx_mock.post(ISSUE_ENDPOINT).mock(return_value=httpx.Response(500))
    async with make_client() as client:
        with pytest.raises(WriteUncertainError, match="may or may not"):
            await client.create_issue("VOR", "1", "x")
    assert route.call_count == 1


@respx.mock(base_url=BASE_URL)
async def test_write_not_retried_on_timeout(respx_mock):
    route = respx_mock.post(ISSUE_ENDPOINT).mock(side_effect=httpx.ReadTimeout("slow"))
    async with make_client() as client:
        with pytest.raises(WriteUncertainError, match="may or may not"):
            await client.create_issue("VOR", "1", "x")
    assert route.call_count == 1


@respx.mock(base_url=BASE_URL)
async def test_write_retried_on_429(respx_mock):
    sleep = RecordingSleep()
    route = respx_mock.post(ISSUE_ENDPOINT).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "5"}),
            httpx.Response(201, json={"id": "1", "key": "VOR-1"}),
        ]
    )
    async with make_client(sleep=sleep) as client:
        made = await client.create_issue("VOR", "1", "x")

    assert made["key"] == "VOR-1"
    assert route.call_count == 2
    assert sleep.delays[0] >= 5


@respx.mock(base_url=BASE_URL)
async def test_read_retried_on_503(respx_mock):
    route = respx_mock.get("/rest/agile/1.0/board/12").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"id": 12})]
    )
    async with make_client() as client:
        board = await client.get_board(12)
    assert board == {"id": 12}
    assert route.call_count == 2


@respx.mock(base_url=BASE_URL)
async def test_read_retries_exhausted_reports_status_and_attempts(respx_mock):
    respx_mock.get("/rest/agile/1.0/board/12").mock(return_value=httpx.Response(502))
    async with make_client(max_attempts=3) as client:
        with pytest.raises(TransientError, match=r"502.*after 3 attempts"):
            await client.get_board(12)


# ----------------------------------------------------------------------
# Error classification
# ----------------------------------------------------------------------


@respx.mock(base_url=BASE_URL)
async def test_400_field_errors_surfaced(respx_mock):
    respx_mock.post(ISSUE_ENDPOINT).mock(
        return_value=httpx.Response(400, json={"errors": {"summary": "Summary is required"}})
    )
    async with make_client() as client:
        with pytest.raises(InvalidQueryError, match="summary: Summary is required"):
            await client.create_issue("VOR", "1", "")


@respx.mock(base_url=BASE_URL)
async def test_403_on_create_names_create_permission(respx_mock):
    respx_mock.post(ISSUE_ENDPOINT).mock(return_value=httpx.Response(403))
    async with make_client() as client:
        with pytest.raises(PermissionError_, match="Create Issues"):
            await client.create_issue("VOR", "1", "x")


@respx.mock(base_url=BASE_URL)
async def test_403_on_sprint_add_names_schedule_permission(respx_mock):
    respx_mock.post(SPRINT_ISSUE_ENDPOINT.format(sprint_id=501)).mock(
        return_value=httpx.Response(403)
    )
    async with make_client() as client:
        with pytest.raises(PermissionError_, match="Schedule Issues"):
            await client.add_issues_to_sprint(501, ["VOR-1"])


@pytest.mark.parametrize(
    "status, expected",
    [(401, AuthError), (404, NotFoundError), (410, EndpointGoneError)],
)
@respx.mock(base_url=BASE_URL)
async def test_error_classification_names_endpoint(respx_mock, status, expected):
    respx_mock.get("/rest/agile/1.0/board/12").mock(return_value=httpx.Response(status))
    async with make_client() as client:
        with pytest.raises(expected) as info:
            await client.get_board(12)
    assert info.value.endpoint == "/rest/agile/1.0/board/12"
    assert TOKEN not in str(info.value)
