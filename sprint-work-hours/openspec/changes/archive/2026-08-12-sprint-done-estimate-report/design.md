## Context

The repository is empty apart from OpenSpec scaffolding, so this change also establishes the project skeleton. The target Jira instance is Jira **Cloud** at `https://dibts3.atlassian.net`, which constrains the design in three ways worth stating up front:

1. `GET/POST /rest/api/3/search` has been **removed** and returns `410 Gone`. The replacement, `POST /rest/api/3/search/jql`, requires an explicit `fields` array (nothing is returned by default) and uses opaque `nextPageToken` cursor pagination with no `total` count. See the [issue search API reference](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/).
2. Sprint membership lives on the **parent** issue. A plain `sprint = X` query does not reliably return subtasks, so subtasks must be fetched via their parents.
3. Sprint and board metadata come from a different API family — Agile `/rest/agile/1.0` — with the older `startAt`/`maxResults`/`isLast` pagination style. The client therefore needs two pagination strategies.

The core requirement — count work that *transitioned into* done during the sprint, not work that is *currently* done — means the current status field is unusable and every candidate issue's changelog must be inspected. That is the dominant cost driver in the design.

## Goals / Non-Goals

**Goals:**
- Produce a repeatable, auditable total original estimate for work completed within a named sprint's window.
- Make the number defensible: every issue that contributes is shown, and every estimate deliberately excluded is shown with the reason.
- Keep Jira access behind one seam so the calculation logic is testable without network access.
- Fail loudly and legibly on misconfiguration rather than silently reporting a wrong number.

**Non-Goals:**
- Story points, remaining estimate, or time-spent reporting. Original estimate only.
- CSV/JSON export, per-assignee breakdowns, or multi-sprint trends. The console report is the whole surface for this change.
- A web UI, a scheduled job, or any persistence. Every run is a fresh read.
- Caching Jira responses across runs.
- Supporting Jira Data Center / Server. Cloud only.

## Decisions

### Python 3.11+ with `httpx`, `typer`, and `rich`

Chosen for a fast-to-run, no-build-step CLI. `httpx` gives a modern client with connection pooling and first-class timeout control; `typer` gives argument parsing and `--help` with minimal boilerplate; `rich` renders the per-issue table and handles truncation and alignment without hand-rolled padding.

*Alternative considered:* stdlib `argparse` + `requests` + manual table formatting. Rejected because the table has enough columns and truncation rules (`cli-report`) that hand-rolling it is a meaningful chunk of the work for no benefit. *Alternative considered:* the `jira` PyPI library. Rejected because it wraps the removed search endpoint in versions still widely pinned, and the surface area used here is small enough that a thin purpose-built client is less risk than a dependency that abstracts exactly the endpoints that changed.

Layout:

```
pyproject.toml            # deps, entry point: jira-sprint-estimates
src/jira_sprint_estimates/
  __init__.py
  cli.py                  # typer app, arg validation, exit codes  -> cli-report
  config.py               # env credential loading                 -> jira-client
  client.py               # HTTP, pagination, retries, errors      -> jira-client
  errors.py               # typed exception hierarchy              -> jira-client
  sprints.py              # name -> sprint, window derivation      -> sprint-scope-resolution
  issues.py               # candidate set incl. subtasks           -> sprint-scope-resolution
  done.py                 # changelog -> qualifying transition     -> done-estimate-calculation
  aggregate.py            # leaf-preferring rollup                 -> done-estimate-calculation
  report.py               # summary + rich table                   -> cli-report
tests/
  fixtures/               # recorded Jira JSON payloads
```

The module boundaries deliberately mirror the four capability specs so each spec has an obvious implementation home.

### Two-phase issue fetch, joined by parent key

Phase 1 runs `sprint = <id>` through `POST /rest/api/3/search/jql` requesting `key,summary,issuetype,status,parent,assignee,timeoriginalestimate,subtasks`. Phase 2 collects the parent keys from phase 1 and runs a second query, `parent in (KEY-1, KEY-2, ...)`, batching keys so no single JQL string grows unreasonable (batch size 50). The union is deduplicated by issue key.

*Alternative considered:* reading the `subtasks` array already present on each parent and fetching each subtask individually. Rejected — that is one request per subtask, where the `parent in (...)` query gets them in batches of 50. The `subtasks` array is still requested and used as a cross-check: if a subtask key appears there but not in the phase-2 results, that discrepancy is surfaced under `--verbose` rather than silently dropped.

*Alternative considered:* `/rest/agile/1.0/sprint/{id}/issue`. Rejected as the primary path because its subtask behaviour varies by board configuration; the JQL path behaves predictably across configurations.

### Changelog fetched per issue, concurrently, with bounded parallelism

The changelog is not available from the search endpoint in a form that is reliably complete for paginated histories, so each candidate issue needs `GET /rest/api/3/issue/{key}/changelog`. This is one request per candidate issue — the design's main cost. `httpx.AsyncClient` with a semaphore capped at 8 concurrent requests keeps wall-clock reasonable for a typical 50–150 issue sprint while staying well clear of rate limits.

*Alternative considered:* `expand=changelog` on the search request. Rejected as the sole mechanism: the expansion truncates long histories without a reliable continuation path, and a truncated history silently produces a *wrong* answer — exactly the failure mode this tool exists to prevent. It may be used as an optimisation later only if the response proves the history is complete.

### Done is classified by status **category**, never by status name

Each changelog `status` item gives `from`/`to` status ids and display strings, but not the category. The tool fetches the project's statuses once via `/rest/api/3/status` and builds an id → `statusCategory.key` map, then classifies each transition's destination id. An issue qualifies when a transition's destination category is `done` **and** the source category is not `done` — this is what makes the "moved between two done statuses mid-sprint" scenario correctly non-qualifying — and the transition timestamp falls inside the window.

*Alternative considered:* matching against a hardcoded name list (`Done`, `Closed`, `Resolved`). Rejected because custom workflows (e.g. `Released`) would be missed, producing a silently low total.

### Estimates are summed in seconds, converted to hours only at render time

`timeoriginalestimate` is seconds. Internal arithmetic stays in integer seconds; `report.py` divides by 3600 and rounds to 2dp for display only. This makes the "sum before rounding" requirement structural rather than something a future edit can accidentally undo.

### Leaf-preferring aggregation as an explicit two-pass over the qualifying set

Pass 1 marks every qualifying issue. Pass 2 walks qualifying non-subtask issues; if any of an issue's qualifying children exist in the set, the parent is tagged `rolled_up_excluded` with its own estimate retained for display but zeroed for the total. The excluded amount stays on the record precisely so the table can show it — an unexplained gap between the visible rows and the total is what makes a report untrustworthy.

### Testing: fixture-driven, no live Jira in the test suite

Recorded JSON payloads under `tests/fixtures/` drive unit tests for `done.py` and `aggregate.py` — the two modules where a logic error produces a plausible-looking wrong number. `client.py` is tested against a mock transport covering pagination, the non-advancing-cursor guard, 429 backoff, and error classification. The CLI is tested end-to-end with the client seam stubbed.

## Risks / Trade-offs

- **Changelog retention or permission gaps produce an undercount.** An issue whose history the token cannot read looks like it never transitioned. → Any issue whose changelog fetch fails is collected and reported as a `skipped` count in the summary, so an undercount is never invisible.
- **One request per candidate issue is slow for large sprints.** A 300-issue sprint means ~300 changelog calls. → Bounded concurrency of 8 plus a progress indicator under `--verbose`. If this proves painful, the `expand=changelog` optimisation with a completeness check is the follow-up.
- **Status category map is fetched globally.** `/rest/api/3/status` returns every status in the instance, which can be large. → Fetched once per run and held in memory; it is a single request and the payload is well under the size where this matters.
- **Leaf-preferring aggregation can undercount deliberately-estimated parents.** If a team estimates the parent at 8h and its subtasks at 3h+4h because subtask estimates are partial, the tool reports 7h, not 8h. → This was an explicit product decision; the excluded parent estimate is always shown in the table so the discrepancy is visible and the user can judge it.
- **Active sprints give a moving answer.** Running the tool twice on an in-progress sprint yields different numbers. → The summary explicitly labels the sprint as in progress and prints the window end timestamp used.
- **Atlassian may change the search API again.** The 410 on `/rest/api/3/search` is recent history. → Endpoint paths are constants in `client.py`, and a `410` is classified into a distinct error that names the dead endpoint rather than surfacing as a generic HTTP failure.

## Migration Plan

Not applicable — greenfield tool with no existing users, no data to migrate, and no deployment target. Rollback is deleting the change.

## Open Questions

- Is there a single board that should be the default, so `--board` could become optional with an env-var fallback (`JIRA_DEFAULT_BOARD`)? Deferred; the current design requires the board to be explicit.
- Should issues moved *out* of the sprint mid-flight but completed within the window count? The current design counts only issues in the sprint at read time, which is what `sprint = <id>` reports. Flagged for review once the tool has run against a real sprint.
