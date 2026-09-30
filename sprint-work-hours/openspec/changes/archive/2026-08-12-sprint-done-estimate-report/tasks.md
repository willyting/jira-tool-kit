## 1. Project Scaffolding

- [x] 1.1 Create `pyproject.toml` targeting Python 3.11+, declaring `httpx`, `typer`, `rich` as runtime deps and `pytest`, `pytest-asyncio`, `respx` as dev deps, with a `jira-sprint-estimates` console entry point pointing at `jira_sprint_estimates.cli:app`
- [x] 1.2 Create the `src/jira_sprint_estimates/` package skeleton with empty modules: `cli.py`, `config.py`, `client.py`, `errors.py`, `sprints.py`, `issues.py`, `done.py`, `aggregate.py`, `report.py`
- [x] 1.3 Create `tests/` with `conftest.py` and an empty `tests/fixtures/` directory
- [x] 1.4 Add `.gitignore` (Python artifacts, `.venv`, `.env`) and a `.env.example` listing `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` with no real values
- [x] 1.5 Verify `pip install -e .` succeeds and `jira-sprint-estimates --help` runs

## 2. Errors and Configuration

- [x] 2.1 Define the exception hierarchy in `errors.py`: base `JiraToolError`, plus `ConfigError`, `AuthError`, `PermissionError`, `NotFoundError`, `InvalidQueryError`, `EndpointGoneError`, `TransientError`
- [x] 2.2 Implement `config.py` loading `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, raising `ConfigError` naming the specific missing variable
- [x] 2.3 Write tests covering each-variable-missing and all-present cases, and asserting no error message or repr contains the token value

## 3. Jira HTTP Client

- [x] 3.1 Implement the `JiraClient` base in `client.py`: `httpx.AsyncClient` with Basic auth, base URL, explicit timeouts, and endpoint paths as module constants
- [x] 3.2 Implement HTTP status → typed error classification, including `410` → `EndpointGoneError` naming the called endpoint, and `429`/`5xx` → `TransientError`
- [x] 3.3 Implement retry with exponential backoff honouring `Retry-After`, bounded attempts, and no retry on 4xx other than 429
- [x] 3.4 Implement `search_jql()` against `POST /rest/api/3/search/jql` with a required explicit `fields` argument and `nextPageToken` cursor pagination
- [x] 3.5 Add the pagination-not-advancing guard: raise if a repeated token is returned or zero issues arrive alongside a token
- [x] 3.6 Implement `list_boards()` and `list_sprints(board_id)` against `/rest/agile/1.0` with `startAt`/`maxResults`/`isLast` pagination
- [x] 3.7 Implement `get_changelog(issue_key)` against `GET /rest/api/3/issue/{key}/changelog`, paginating fully and returning entries in chronological order
- [x] 3.8 Implement `get_statuses()` against `GET /rest/api/3/status`, returning a status id → `statusCategory.key` map
- [x] 3.9 Write `respx`-based tests for: multi-page cursor pagination, the non-advancing-cursor guard, Agile `isLast` pagination, empty changelog, 429-with-Retry-After backoff, retry exhaustion, and each error classification

## 4. Sprint Resolution and Window

- [x] 4.1 Implement case-insensitive, whitespace-trimmed sprint name matching in `sprints.py`
- [x] 4.2 Implement the zero-match error listing the board's most recent sprint names, and the multi-match error listing each candidate's id, state, and start date
- [x] 4.3 Implement window derivation: start from `startDate`; end from `completeDate`, else `endDate`, else current time for active sprints; raise when `startDate` is absent
- [x] 4.4 Normalise all sprint dates to timezone-aware UTC datetimes
- [x] 4.5 Write tests for exact/case/padding matches, no match, duplicate names, closed vs active windows, missing start date, and mixed UTC offsets

## 5. Candidate Issue Set

- [x] 5.1 Implement the phase-1 `sprint = <id>` search in `issues.py`, requesting `key,summary,issuetype,status,parent,assignee,timeoriginalestimate,subtasks` explicitly
- [x] 5.2 Implement the phase-2 `parent in (...)` search, batching parent keys at 50 per query
- [x] 5.3 Implement union and deduplication by issue key, retaining issue type, `is_subtask`, and `parent_key` on each record
- [x] 5.4 Implement the cross-check comparing parents' `subtasks` arrays against phase-2 results, reporting any discrepancy under `--verbose`
- [x] 5.5 Handle the empty-sprint case by returning an empty candidate set without raising
- [x] 5.6 Write tests for parent-with-unassigned-subtasks, subtask returned by both phases appearing once, batching across the 50-key boundary, and empty sprint

## 6. Done Transition Detection

- [x] 6.1 Implement status-category classification in `done.py` using the id → category map, treating a transition as entering-done when the destination category is `done` and the source category is not
- [x] 6.2 Implement window matching against transition timestamps in UTC, recording the earliest qualifying transition per issue
- [x] 6.3 Implement reopened detection: flag issues that transitioned out of the done category after a qualifying transition, still inside the window
- [x] 6.4 Implement bounded-concurrency changelog fetching with an `asyncio.Semaphore` capped at 8
- [x] 6.5 Collect issues whose changelog fetch fails into a `skipped` list rather than failing the run or silently dropping them
- [x] 6.6 Write tests for every `done-estimate-calculation` transition scenario: inside window, before window, after window, done-now-but-transitioned-earlier, reopened within sprint, multiple qualifying transitions, custom done-category status, and done-to-done transition

## 7. Estimate Aggregation

- [x] 7.1 Implement the two-pass leaf-preferring rollup in `aggregate.py`, tagging parents with qualifying children as `rolled_up_excluded` while retaining their own estimate for display
- [x] 7.2 Keep all arithmetic in integer seconds; expose an hours conversion helper used only by the report layer
- [x] 7.3 Count and expose qualifying issues with null or absent `timeoriginalestimate` as `unestimated`
- [x] 7.4 Write tests for parent+subtasks both qualifying, parent with no qualifying subtasks, subtask qualifying without its parent, standalone issue, all-unestimated, and sum-in-seconds-before-rounding

## 8. Report Rendering

- [x] 8.1 Implement the console summary in `report.py`: sprint name and id, UTC window, total hours, qualifying counts split by task vs subtask, unestimated count, and skipped count
- [x] 8.2 Add the in-progress label and window-end note for active sprints
- [x] 8.3 Implement the `rich` per-issue table with key, type, is-subtask, summary, assignee, qualifying timestamp, and estimate columns
- [x] 8.4 Implement grouping — each parent immediately followed by its qualifying subtasks, groups ordered by earliest qualifying transition
- [x] 8.5 Implement the rolled-up-excluded row marker showing the excluded amount, `Unassigned` for missing assignees, and ellipsis truncation for long summaries
- [x] 8.6 Implement the no-qualifying-issues path printing `0h` and exiting zero
- [x] 8.7 Write tests asserting table row count, grouping order, exclusion marker, unassigned placeholder, and truncation

## 9. CLI Wiring

- [x] 9.1 Implement the `typer` command in `cli.py` with `--sprint`, `--board`, `--board-name`, `--verbose`, and `--help`
- [x] 9.2 Validate that exactly one board selector is supplied, erroring on both-or-neither before any network request
- [x] 9.3 Wire the full pipeline: config → client → sprint resolution → candidate set → changelog classification → aggregation → report
- [x] 9.4 Implement top-level error handling: exit non-zero with a single-line message, suppressing tracebacks unless `--verbose`
- [x] 9.5 Write end-to-end CLI tests with the client seam stubbed, covering a successful run, missing `--sprint`, both board selectors, neither selector, missing credentials, 401, and a verbose failure showing the traceback

## 10. Verification

- [x] 10.1 Run the full test suite and confirm every scenario in all four spec files has a corresponding passing test
- [x] 10.2 Run `openspec validate sprint-done-estimate-report --strict` and resolve any findings
- [ ] 10.3 Run the tool against a real closed sprint on `https://dibts3.atlassian.net` and manually verify the total against a handful of issues in the Jira UI
- [ ] 10.4 Run the tool against an active sprint and confirm the in-progress labelling and window-end behaviour
- [x] 10.5 Write `README.md` covering setup, API token creation, environment variables, usage examples, and an explanation of the leaf-preferring aggregation rule
