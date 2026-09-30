# jira-client Specification

## Purpose
TBD - created by archiving change sprint-done-estimate-report. Update Purpose after archive.
## Requirements
### Requirement: Credential loading from environment
The client SHALL read `JIRA_BASE_URL`, `JIRA_EMAIL`, and `JIRA_API_TOKEN` from the process environment and authenticate every request using HTTP Basic auth with the email as username and the API token as password. Credentials SHALL NOT be read from, or written to, any file in the repository.

#### Scenario: All credentials present
- **WHEN** all three environment variables are set and the client is constructed
- **THEN** the client is created and every outgoing request carries an `Authorization: Basic` header derived from `JIRA_EMAIL` and `JIRA_API_TOKEN`

#### Scenario: A credential is missing
- **WHEN** any of the three environment variables is unset or empty
- **THEN** construction fails with a configuration error naming the specific missing variable, and no HTTP request is made

#### Scenario: Token is never echoed
- **WHEN** any client error is raised or any log line is emitted
- **THEN** the message contains no part of `JIRA_API_TOKEN`

### Requirement: Enhanced JQL issue search
The client SHALL search issues via `POST /rest/api/3/search/jql`. It MUST send an explicit `fields` list on every request, and MUST NOT call the removed `/rest/api/3/search` endpoint.

#### Scenario: Single page of results
- **WHEN** a JQL query is executed and the response contains no `nextPageToken`
- **THEN** the client returns exactly the issues in that response

#### Scenario: Cursor pagination across multiple pages
- **WHEN** a response contains a `nextPageToken`
- **THEN** the client issues a follow-up request carrying that token and continues until a response omits `nextPageToken`, returning the concatenation of all pages with no duplicated issue keys

#### Scenario: Pagination fails to advance
- **WHEN** a response returns a `nextPageToken` identical to the one just sent, or returns zero issues while still supplying a token
- **THEN** the client stops paginating and raises an error rather than looping indefinitely

### Requirement: Agile board and sprint access
The client SHALL expose board lookup and sprint listing through the Agile API — boards via `/rest/agile/1.0/board`, sprints via `/rest/agile/1.0/board/{boardId}/sprint` — following the Agile API's `startAt`/`maxResults`/`isLast` pagination.

#### Scenario: Listing sprints for a board
- **WHEN** sprints are requested for a board id
- **THEN** the client returns every sprint across all pages, each carrying at minimum `id`, `name`, `state`, `startDate`, `endDate`, and `completeDate` when present

#### Scenario: Board is not accessible
- **WHEN** the board id does not exist or the token lacks permission for it
- **THEN** the client raises a not-found or permission error that names the board id

### Requirement: Issue changelog retrieval
The client SHALL retrieve an issue's full status history via `GET /rest/api/3/issue/{issueIdOrKey}/changelog`, paginating until all entries are collected.

#### Scenario: Changelog spanning multiple pages
- **WHEN** an issue has more changelog entries than a single page holds
- **THEN** the client returns all entries in chronological order across every page

#### Scenario: Issue has no changelog
- **WHEN** an issue has never been modified
- **THEN** the client returns an empty history without raising an error

### Requirement: Retry and rate-limit handling
The client SHALL retry transient failures — HTTP 429 and 5xx — with exponential backoff, honouring a `Retry-After` header when present, up to a bounded number of attempts. Non-transient responses SHALL NOT be retried.

#### Scenario: Rate limited with Retry-After
- **WHEN** Jira responds `429` with `Retry-After: 5`
- **THEN** the client waits at least 5 seconds and retries the same request

#### Scenario: Retries exhausted
- **WHEN** every attempt for a request fails transiently
- **THEN** the client raises an error reporting the final status code and the number of attempts made

#### Scenario: Client error is not retried
- **WHEN** Jira responds `400` or `404`
- **THEN** the client raises immediately without further attempts

### Requirement: Typed error classification
The client SHALL translate HTTP failures into distinct error types so callers can distinguish configuration problems from data problems: authentication failure (`401`), permission denied (`403`), not found (`404`), invalid query (`400`), and transient/unknown failures.

#### Scenario: Bad credentials
- **WHEN** Jira responds `401`
- **THEN** an authentication error is raised whose message tells the user to check `JIRA_EMAIL` and `JIRA_API_TOKEN`

#### Scenario: Removed search endpoint
- **WHEN** any request returns `410 Gone`
- **THEN** the error message states that the endpoint has been removed by Atlassian and names the endpoint that was called

