## ADDED Requirements

### Requirement: Credential loading from environment
The client SHALL read `JIRA_BASE_URL`, `JIRA_EMAIL`, and `JIRA_API_TOKEN` from the process environment and authenticate every request with HTTP Basic auth, using the email as username and the API token as password. Credentials SHALL NOT be read from, or written to, any file.

#### Scenario: All credentials present
- **WHEN** all three environment variables are set and the client is constructed
- **THEN** every outgoing request carries an `Authorization: Basic` header derived from `JIRA_EMAIL` and `JIRA_API_TOKEN`

#### Scenario: A credential is missing
- **WHEN** any of the three variables is unset, empty, or whitespace-only
- **THEN** construction fails with a configuration error naming each missing variable, and no HTTP request is made

#### Scenario: Token is never echoed
- **WHEN** any error is raised or any output is printed, including under `--verbose`
- **THEN** no part of `JIRA_API_TOKEN` appears in it

### Requirement: Board, sprint and project lookup
The client SHALL list boards (optionally filtered by name) via `GET /rest/agile/1.0/board`, fetch one board via `GET /rest/agile/1.0/board/{boardId}`, list a board's projects via `GET /rest/agile/1.0/board/{boardId}/project`, and list a board's sprints via `GET /rest/agile/1.0/board/{boardId}/sprint` with an optional `state` filter. All of these SHALL follow the Agile `startAt`/`maxResults`/`isLast` pagination to the end.

#### Scenario: Sprints across multiple pages
- **WHEN** a board has more sprints than one page holds
- **THEN** the client returns every sprint from every page

#### Scenario: Filtering sprints by state
- **WHEN** sprints are requested with `state=active,future`
- **THEN** the request carries that `state` parameter, and only the returned sprints are passed on

### Requirement: Project issue-type discovery
The client SHALL return the issue types available for creation in a project via `GET /rest/api/3/issue/createmeta/{projectIdOrKey}/issuetypes`, paginating fully, with each type's `id`, `name`, and `subtask` flag.

#### Scenario: Project with standard and subtask types
- **WHEN** issue types are requested for a project
- **THEN** the client returns every type with its `id`, `name`, and boolean `subtask`

### Requirement: Enhanced JQL issue search
The client SHALL search issues only via `POST /rest/api/3/search/jql`, MUST send an explicit `fields` list, MUST follow `nextPageToken` cursors to the end, and MUST NOT call the removed `/rest/api/3/search` endpoint.

#### Scenario: Multi-page results
- **WHEN** a response includes a `nextPageToken`
- **THEN** the client requests the next page with that token and returns the concatenation of all pages

#### Scenario: Pagination fails to advance
- **WHEN** a response repeats a previously seen `nextPageToken`, or returns zero issues together with a token
- **THEN** the client raises a pagination error instead of looping

### Requirement: Issue creation
The client SHALL create an issue via `POST /rest/api/3/issue` given a project key, an issue type id, a summary, and optionally a parent key. It SHALL return the created issue's `key` and `id`.

#### Scenario: Create a standard task
- **WHEN** an issue is created with project `VOR`, the task type id, and a summary
- **THEN** the request body carries `fields.project.key`, `fields.issuetype.id`, and `fields.summary` exactly as given, and the client returns the new key

#### Scenario: Create a subtask
- **WHEN** an issue is created with a parent key
- **THEN** the request body also carries `fields.parent.key` set to that parent

### Requirement: Adding issues to a sprint
The client SHALL move issues into a sprint via `POST /rest/agile/1.0/sprint/{sprintId}/issue` with body `{"issues": [<keys>]}`, treating the `204 No Content` success response as success.

#### Scenario: Issue added
- **WHEN** an issue key is added to a sprint id and Jira responds `204`
- **THEN** the call completes without error

### Requirement: Retry policy distinguishes reads from writes
The client SHALL retry read requests on network errors, HTTP 429, and 5xx, using exponential backoff that honours a numeric `Retry-After`, up to a bounded number of attempts. Write requests (issue create, add-to-sprint) SHALL be retried only on HTTP 429, and SHALL NOT be retried on network errors or 5xx, because the write may already have taken effect.

#### Scenario: Read rate-limited with Retry-After
- **WHEN** a read request gets `429` with `Retry-After: 5`
- **THEN** the client waits at least 5 seconds and retries

#### Scenario: Write times out
- **WHEN** an issue-create request fails with a network timeout
- **THEN** the client raises an error immediately, after exactly one attempt, and the message says the issue may or may not have been created

#### Scenario: Write rate-limited
- **WHEN** an issue-create request gets `429`
- **THEN** the client retries it under the same backoff rules as a read

#### Scenario: Retries exhausted
- **WHEN** every allowed attempt fails transiently
- **THEN** the client raises an error naming the final status code and the number of attempts made

### Requirement: Typed errors
The client SHALL map `401` to an authentication error, `403` to a permission error, `404` to a not-found error, `400` to an invalid-request error that includes Jira's `errorMessages` and `errors` text, and `410` to an endpoint-gone error. Each message SHALL name the endpoint called.

#### Scenario: Create rejected with field errors
- **WHEN** issue creation returns `400` with `{"errors": {"summary": "Summary is required"}}`
- **THEN** the raised error message contains `summary: Summary is required`

#### Scenario: Permission denied on create
- **WHEN** issue creation returns `403`
- **THEN** the raised error says the account lacks the *Create Issues* permission on the project

#### Scenario: Permission denied on add-to-sprint
- **WHEN** add-to-sprint returns `403`
- **THEN** the raised error says the account lacks the *Schedule Issues* permission
