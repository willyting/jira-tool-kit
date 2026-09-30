import json

import httpx
import pytest
import respx

from jira_sprint_estimates.client import (
    BOARD_ENDPOINT,
    ISSUE_CHANGELOG_ENDPOINT,
    SEARCH_JQL_ENDPOINT,
    STATUS_ENDPOINT,
    JiraClient,
    _basic_auth_header,
)
from jira_sprint_estimates.config import JiraConfig
from jira_sprint_estimates.errors import (
    AuthError,
    EndpointGoneError,
    InvalidQueryError,
    JiraApiError,
    NotFoundError,
    PaginationError,
    PermissionError_,
    TransientError,
)

BASE_URL = "https://jira.example.test"
FIELDS = ["key", "summary", "timeoriginalestimate"]

CONFIG = JiraConfig(
    base_url=BASE_URL, email="someone@example.com", api_token="secret-token"
)


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


def issue(key: str) -> dict:
    return {"key": key, "fields": {"summary": key}}


# ----------------------------------------------------------------------
# Auth header
# ----------------------------------------------------------------------


@respx.mock(base_url=BASE_URL)
async def test_requests_carry_basic_auth(respx_mock):
    route = respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"issues": []})
    )

    async with make_client() as client:
        await client.search_jql("sprint = 1", FIELDS)

    sent = route.calls.last.request
    assert sent.headers["Authorization"] == _basic_auth_header(
        "someone@example.com", "secret-token"
    )


# ----------------------------------------------------------------------
# search_jql
# ----------------------------------------------------------------------


@respx.mock(base_url=BASE_URL)
async def test_search_requires_explicit_fields(respx_mock):
    async with make_client() as client:
        with pytest.raises(ValueError, match="explicit fields"):
            await client.search_jql("sprint = 1", [])


@respx.mock(base_url=BASE_URL)
async def test_search_sends_fields_explicitly(respx_mock):
    route = respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"issues": [issue("A-1")]})
    )

    async with make_client() as client:
        await client.search_jql("sprint = 1", FIELDS)

    payload = json.loads(route.calls.last.request.content)
    assert payload["fields"] == FIELDS
    assert payload["jql"] == "sprint = 1"


@respx.mock(base_url=BASE_URL)
async def test_search_single_page(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"issues": [issue("A-1"), issue("A-2")]})
    )

    async with make_client() as client:
        results = await client.search_jql("sprint = 1", FIELDS)

    assert [i["key"] for i in results] == ["A-1", "A-2"]


@respx.mock(base_url=BASE_URL)
async def test_search_follows_cursor_across_pages(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, json={"issues": [issue("A-1")], "nextPageToken": "t1"}),
            httpx.Response(200, json={"issues": [issue("A-2")], "nextPageToken": "t2"}),
            httpx.Response(200, json={"issues": [issue("A-3")]}),
        ]
    )

    async with make_client() as client:
        results = await client.search_jql("sprint = 1", FIELDS)

    keys = [i["key"] for i in results]
    assert keys == ["A-1", "A-2", "A-3"]
    assert len(keys) == len(set(keys))


@respx.mock(base_url=BASE_URL)
async def test_search_stops_on_is_last_even_with_token(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        side_effect=[
            httpx.Response(
                200,
                json={"issues": [issue("A-1")], "nextPageToken": "t1", "isLast": True},
            ),
        ]
    )

    async with make_client() as client:
        results = await client.search_jql("sprint = 1", FIELDS)

    assert [i["key"] for i in results] == ["A-1"]


@respx.mock(base_url=BASE_URL)
async def test_search_raises_on_repeated_cursor(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, json={"issues": [issue("A-1")], "nextPageToken": "t1"}),
            httpx.Response(200, json={"issues": [issue("A-2")], "nextPageToken": "t1"}),
        ]
    )

    async with make_client() as client:
        with pytest.raises(PaginationError, match="repeated nextPageToken"):
            await client.search_jql("sprint = 1", FIELDS)


@respx.mock(base_url=BASE_URL)
async def test_search_raises_on_empty_page_with_cursor(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"issues": [], "nextPageToken": "t1"})
    )

    async with make_client() as client:
        with pytest.raises(PaginationError, match="zero issues"):
            await client.search_jql("sprint = 1", FIELDS)


# ----------------------------------------------------------------------
# Agile pagination
# ----------------------------------------------------------------------


@respx.mock(base_url=BASE_URL)
async def test_agile_pagination_follows_is_last(respx_mock):
    respx_mock.get(BOARD_ENDPOINT).mock(
        side_effect=[
            httpx.Response(
                200, json={"values": [{"id": 1}, {"id": 2}], "isLast": False}
            ),
            httpx.Response(200, json={"values": [{"id": 3}], "isLast": True}),
        ]
    )

    async with make_client() as client:
        boards = await client.list_boards()

    assert [b["id"] for b in boards] == [1, 2, 3]


@respx.mock(base_url=BASE_URL)
async def test_agile_pagination_advances_start_at(respx_mock):
    route = respx_mock.get(BOARD_ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, json={"values": [{"id": 1}, {"id": 2}], "isLast": False}),
            httpx.Response(200, json={"values": [{"id": 3}], "isLast": True}),
        ]
    )

    async with make_client() as client:
        await client.list_boards()

    assert route.calls[0].request.url.params["startAt"] == "0"
    assert route.calls[1].request.url.params["startAt"] == "2"


@respx.mock(base_url=BASE_URL)
async def test_agile_pagination_stops_on_total(respx_mock):
    respx_mock.get(BOARD_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"values": [{"id": 1}], "total": 1})
    )

    async with make_client() as client:
        boards = await client.list_boards()

    assert boards == [{"id": 1}]


@respx.mock(base_url=BASE_URL)
async def test_list_sprints_returns_full_sprint_records(respx_mock):
    route = respx_mock.get("/rest/agile/1.0/board/7/sprint").mock(
        return_value=httpx.Response(
            200,
            json={
                "values": [
                    {
                        "id": 99,
                        "name": "Sprint 42",
                        "state": "closed",
                        "startDate": "2026-03-01T09:00:00.000+0000",
                        "endDate": "2026-03-15T09:00:00.000+0000",
                        "completeDate": "2026-03-15T17:30:00.000+0000",
                    }
                ],
                "isLast": True,
            },
        )
    )

    async with make_client() as client:
        sprints = await client.list_sprints(7)

    assert route.called
    sprint = sprints[0]
    for field in ("id", "name", "state", "startDate", "endDate", "completeDate"):
        assert field in sprint


@pytest.mark.parametrize(
    ("status", "expected"), [(404, NotFoundError), (403, PermissionError_)]
)
@respx.mock(base_url=BASE_URL)
async def test_inaccessible_board_names_the_board_id(respx_mock, status, expected):
    respx_mock.get("/rest/agile/1.0/board/7/sprint").mock(
        return_value=httpx.Response(status, json={})
    )

    async with make_client() as client:
        with pytest.raises(expected) as excinfo:
            await client.list_sprints(7)

    # The endpoint path carries the board id, so the message identifies which
    # board was refused.
    assert "board/7" in str(excinfo.value)


# ----------------------------------------------------------------------
# Changelog
# ----------------------------------------------------------------------


@respx.mock(base_url=BASE_URL)
async def test_changelog_paginates_and_sorts_chronologically(respx_mock):
    endpoint = ISSUE_CHANGELOG_ENDPOINT.format(issue_key="A-1")
    respx_mock.get(endpoint).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "values": [{"created": "2026-03-05T10:00:00.000+0000", "id": "2"}],
                    "isLast": False,
                },
            ),
            httpx.Response(
                200,
                json={
                    "values": [{"created": "2026-03-01T10:00:00.000+0000", "id": "1"}],
                    "isLast": True,
                },
            ),
        ]
    )

    async with make_client() as client:
        entries = await client.get_changelog("A-1")

    assert [e["id"] for e in entries] == ["1", "2"]


@respx.mock(base_url=BASE_URL)
async def test_empty_changelog_is_not_an_error(respx_mock):
    endpoint = ISSUE_CHANGELOG_ENDPOINT.format(issue_key="A-1")
    respx_mock.get(endpoint).mock(
        return_value=httpx.Response(200, json={"values": [], "isLast": True})
    )

    async with make_client() as client:
        assert await client.get_changelog("A-1") == []


# ----------------------------------------------------------------------
# Statuses
# ----------------------------------------------------------------------


@respx.mock(base_url=BASE_URL)
async def test_get_statuses_maps_id_to_category(respx_mock):
    respx_mock.get(STATUS_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "10000", "name": "To Do", "statusCategory": {"key": "new"}},
                {"id": "3", "name": "In Progress", "statusCategory": {"key": "indeterminate"}},
                {"id": "10001", "name": "Released", "statusCategory": {"key": "done"}},
                {"id": "10002", "name": "Broken"},
            ],
        )
    )

    async with make_client() as client:
        mapping = await client.get_statuses()

    assert mapping == {"10000": "new", "3": "indeterminate", "10001": "done"}


# ----------------------------------------------------------------------
# Retries and error classification
# ----------------------------------------------------------------------


@respx.mock(base_url=BASE_URL)
async def test_429_retries_and_honours_retry_after(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "5"}, json={}),
            httpx.Response(200, json={"issues": [issue("A-1")]}),
        ]
    )
    sleep = RecordingSleep()

    async with make_client(sleep=sleep) as client:
        results = await client.search_jql("sprint = 1", FIELDS)

    assert [i["key"] for i in results] == ["A-1"]
    assert sleep.delays == [5.0]


@respx.mock(base_url=BASE_URL)
async def test_backoff_is_exponential_without_retry_after(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        side_effect=[
            httpx.Response(503, json={}),
            httpx.Response(503, json={}),
            httpx.Response(200, json={"issues": []}),
        ]
    )
    sleep = RecordingSleep()

    async with make_client(sleep=sleep, backoff_base_seconds=1.0) as client:
        await client.search_jql("sprint = 1", FIELDS)

    assert sleep.delays == [1.0, 2.0]


@respx.mock(base_url=BASE_URL)
async def test_retries_exhausted_reports_status_and_attempts(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        return_value=httpx.Response(503, json={})
    )
    sleep = RecordingSleep()

    async with make_client(sleep=sleep, max_attempts=3) as client:
        with pytest.raises(TransientError) as excinfo:
            await client.search_jql("sprint = 1", FIELDS)

    message = str(excinfo.value)
    assert "503" in message
    assert "3 attempts" in message
    # Three attempts means two waits: no sleep after the final failure.
    assert len(sleep.delays) == 2


@respx.mock(base_url=BASE_URL)
async def test_network_failure_is_retried(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        side_effect=[
            httpx.ConnectError("boom"),
            httpx.Response(200, json={"issues": [issue("A-1")]}),
        ]
    )

    async with make_client() as client:
        results = await client.search_jql("sprint = 1", FIELDS)

    assert [i["key"] for i in results] == ["A-1"]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, InvalidQueryError),
        (401, AuthError),
        (403, PermissionError_),
        (404, NotFoundError),
        (410, EndpointGoneError),
        (418, JiraApiError),
    ],
)
@respx.mock(base_url=BASE_URL)
async def test_error_classification(respx_mock, status, expected):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        return_value=httpx.Response(status, json={})
    )
    sleep = RecordingSleep()

    async with make_client(sleep=sleep) as client:
        with pytest.raises(expected):
            await client.search_jql("sprint = 1", FIELDS)

    # Non-transient failures must not be retried.
    assert sleep.delays == []


@respx.mock(base_url=BASE_URL)
async def test_410_names_the_dead_endpoint(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        return_value=httpx.Response(410, json={})
    )

    async with make_client() as client:
        with pytest.raises(EndpointGoneError) as excinfo:
            await client.search_jql("sprint = 1", FIELDS)

    message = str(excinfo.value)
    assert SEARCH_JQL_ENDPOINT in message
    assert "removed by Atlassian" in message


@respx.mock(base_url=BASE_URL)
async def test_401_message_points_at_the_env_vars(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        return_value=httpx.Response(401, json={})
    )

    async with make_client() as client:
        with pytest.raises(AuthError) as excinfo:
            await client.search_jql("sprint = 1", FIELDS)

    message = str(excinfo.value)
    assert "JIRA_EMAIL" in message
    assert "JIRA_API_TOKEN" in message
    assert "secret-token" not in message


@respx.mock(base_url=BASE_URL)
async def test_jira_error_messages_are_surfaced(respx_mock):
    respx_mock.post(SEARCH_JQL_ENDPOINT).mock(
        return_value=httpx.Response(
            400, json={"errorMessages": ["Field 'sprint' does not exist."]}
        )
    )

    async with make_client() as client:
        with pytest.raises(InvalidQueryError) as excinfo:
            await client.search_jql("sprint = 1", FIELDS)

    assert "does not exist" in str(excinfo.value)
