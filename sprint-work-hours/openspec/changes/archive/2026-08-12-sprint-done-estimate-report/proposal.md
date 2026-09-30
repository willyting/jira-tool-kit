## Why

Sprint reviews at DIBTS need a defensible number for "how much estimated work actually got finished this sprint," but Jira's built-in sprint reports key off an issue's *current* status and ignore subtask-level estimates, so they misreport work that was completed and later reopened or moved. Pulling this by hand from https://dibts3.atlassian.net/jira/ every sprint is slow and inconsistent between people. A small CLI that reads the changelog directly gives the same answer every time.

## What Changes

- New Python CLI (`jira-sprint-estimates`) that, given a sprint name and board, reports the total original estimate of all work that **transitioned into the Done status category during that sprint's window**.
- Sprint is selected by human-readable name (e.g. `--sprint "Sprint 42"`) resolved against a board; the sprint's `startDate`/`completeDate` define the window.
- Issue scope covers both sprint-assigned parents and **their subtasks**, since Jira stores the sprint field on the parent and subtasks would otherwise be invisible to a plain `sprint = X` query.
- "Done" is determined per-issue from `/changelog` entries — a `status` field change whose target status belongs to the `done` status category, timestamped inside the sprint window. Current status is not used.
- Estimates are aggregated **leaf-preferring**: when a parent has qualifying done subtasks, only the subtasks' own `timeoriginalestimate` values count and the parent's own estimate is skipped, so rolled-up parent estimates never double-count.
- Output is a console summary (total in hours, issue counts) plus a per-issue table showing key, type, summary, assignee, transition timestamp, and estimate.
- Issues with no original estimate are counted and surfaced separately rather than silently treated as zero.
- Authentication via `JIRA_BASE_URL`, `JIRA_EMAIL`, and `JIRA_API_TOKEN` environment variables (Atlassian API token, HTTP Basic).

## Capabilities

### New Capabilities

- `jira-client`: Authenticated HTTP access to Jira Cloud — credential loading, the enhanced JQL search endpoint, Agile board/sprint endpoints, issue changelog retrieval, token/cursor pagination, retry and rate-limit handling, and typed errors for auth/permission/not-found failures.
- `sprint-scope-resolution`: Turning a board identifier plus a human sprint name into exactly one sprint (with its start/end window) and the complete set of candidate issues — sprint members plus all subtasks of those members, deduplicated.
- `done-estimate-calculation`: Deciding, from an issue's changelog, whether it transitioned into the Done status category inside the sprint window, and aggregating original estimates over the qualifying set using leaf-preferring rules.
- `cli-report`: The command-line surface — arguments, validation, exit codes, the console summary and per-issue table, and actionable error messages for misconfiguration.

### Modified Capabilities

None — this is the first change in the project; `openspec/specs/` is empty.

## Impact

- **New codebase.** The repository currently contains only OpenSpec scaffolding, so this change establishes the Python project layout, dependency management, and test setup.
- **External dependency:** Jira Cloud REST APIs at `https://dibts3.atlassian.net`. Two API families are used — platform `/rest/api/3` and Agile `/rest/agile/1.0`. Note that `GET/POST /rest/api/3/search` has been removed by Atlassian and returns `410 Gone`; the tool must use `POST /rest/api/3/search/jql`, which requires an explicit `fields` list and uses `nextPageToken` cursor pagination.
- **Credentials:** requires an Atlassian API token with read access to the relevant project and board. No credentials are committed; they are read from the environment.
- **Accuracy caveat:** results depend on Jira changelog retention and on the sprint having a recorded start date. Active (not yet completed) sprints are windowed from `startDate` to "now".
