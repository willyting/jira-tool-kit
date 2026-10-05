## Context

`jira-tool-kit` holds small, independent Jira CLIs. The only existing one, `sprint-work-hours/`, is a read-only reporter built on Python 3.11+, `httpx` (async), `typer` and `rich`. It authenticates with `JIRA_BASE_URL` / `JIRA_EMAIL` / `JIRA_API_TOKEN` and already solves board lookup, sprint listing, sprint-name matching, JQL search, retries and typed errors.

This tool is the first one that **writes** to Jira. It creates one parent task and nine subtasks per release on `https://dibts3.atlassian.net`, in the `reseller <N>` sprint of the `VOR board`. Writes are visible to the whole team and are not trivially undone. That shapes most of the decisions below: be idempotent, confirm before writing, and never delete automatically.

## Goals / Non-Goals

**Goals:**
- One command, `jira-release-task --sprint 97 --version 2.14.0`, produces the full release checklist in the right sprint.
- Exact, byte-for-byte summaries every time. The dash counts are part of the format (7 dashes between number and version, 35 trailing).
- Safe to re-run. A second run creates nothing new, and a run that failed partway is completed by running it again.
- `--dry-run` shows the exact plan with zero writes.
- Same install, credential and error-reporting experience as `sprint-work-hours`.

**Non-Goals:**
- Setting assignees, descriptions, fix versions, labels, estimates or due dates on created issues.
- Creating the sprint if it does not exist, or creating a Jira *version* object.
- Transitioning, updating or deleting issues, including rolling back after a partial failure.
- A configurable subtask list. The nine subtasks are a fixed constant; changing them is a code change.
- Sharing a library with `sprint-work-hours`.

## Decisions

### D1. Standalone package, client copied rather than shared
`create-release-task/` gets its own `pyproject.toml` and package, `jira_release_task`. The config, errors, retrying `_request`, JQL search and Agile pagination pieces are copied from `sprint-work-hours`, then extended with write endpoints.
- *Alternative:* extract a shared `jira-common` package. That is cleaner long-term, but it would couple the release cadence of two small tools and turn a new-tool change into a refactor of a working one. Revisit if a third tool appears.

### D2. Summary built from a single template constant
```python
PARENT_SUMMARY = "release {number} ------- {version} -----------------------------------"
SUBTASK_SUMMARIES = (
    "create portal branch", "create backend branch", "check release note",
    "test vpp on stage", "run e2e test on stage", "check new feature on stage",
    "run api test on stage", "check sap on stage", "check on prod",
)
```
A unit test asserts the exact dash counts (7 and 35), so a stray edit fails CI instead of changing ticket titles. The version is inserted verbatim after trimming outer whitespace. No `v` prefix is added or stripped.

### D3. Put the parent in the sprint via the Agile API after creation, not via the create payload
Create the parent with `POST /rest/api/3/issue`, then call `POST /rest/agile/1.0/sprint/{sprintId}/issue` with `{"issues": [key]}`.
- *Alternative:* set the Sprint custom field in the create payload. That needs discovering the site-specific `customfield_XXXXX` id, and it fails obscurely if the field is not on the create screen.
- Subtasks are not added explicitly: Jira keeps subtasks in their parent's sprint automatically.

### D4. Project comes from the board
Use `GET /rest/agile/1.0/board/{id}` and take `location.projectKey` when the board is project-located. Otherwise call `GET /rest/agile/1.0/board/{id}/project`. Exactly one project is used as is. More than one is an error that tells the user to pass `--project <KEY>`, and `--project` always overrides.

### D5. Issue types discovered per project, not hardcoded ids
Use `GET /rest/api/3/issue/createmeta/{projectKey}/issuetypes`.
- Parent type: the non-subtask type named `Task` (case-insensitive), overridable with `--issue-type`.
- Subtask type: the one type with `subtask: true`. If there are several, prefer the name `Sub-task` or `Subtask`. If it is still ambiguous, raise an error listing the candidates.
Issue type *ids* are then used in the create payloads. Team-managed and company-managed projects name the subtask type differently, and ids never collide.

### D6. Sprint resolution reuses the reporter's matching rules
The sprint name is `reseller {N}` and is matched case-insensitively with whitespace collapsed, the same way `sprint-work-hours` does it. Sprints are listed with `state=active,future`, so a closed sprint does not match. If a closed sprint *does* carry the name, the error says it is closed instead of "not found". Zero or several matches raise the same kind of errors the reporter raises, listing nearby sprint names or the ambiguous ids.

### D7. Idempotency: find by exact summary inside the sprint
Before creating, search with `sprint = {sprintId} AND issuetype = {parentTypeId}`, requesting fields `summary,subtasks`, and compare summaries **exactly** on the client side.
- JQL `summary ~` is a tokenised text search that drops punctuation, so it cannot express "exactly these dashes". It is used only to narrow results, never to decide a match.
- 0 matches → create the parent. 1 match → reuse it. Several matches → error listing the keys. The tool refuses to guess which one is real.
- When the parent is reused, its existing subtask summaries are compared exactly (trimmed, case-sensitive) against the checklist, and only the missing ones are created, in checklist order.
- A release task that was moved to another sprint is not detected, and a new one is created. This is accepted: the sprint is the unit of the release.

### D8. Sequential writes, fail fast, no rollback
Subtasks are created one at a time in checklist order. `POST /rest/api/3/issue/bulk` exists, but its partial-success semantics are awkward, and creating sequentially keeps keys in checklist order, so Jira's default subtask ordering matches the checklist. That is ten or eleven calls, which is fast enough.

On the first failed write, the tool stops. It prints everything created so far plus the error, and exits non-zero. It never deletes. Because of D7, running the same command again completes the job.

Writes (POST create, POST add-to-sprint) are **not** retried on network errors or 5xx. A timed-out create may have succeeded server-side, and retrying would create a duplicate. Reads keep the reporter's retry policy. A 429 is retried for writes too, because Jira guarantees nothing was processed.

### D9. CLI shape
```
jira-release-task --sprint 97 --version 2.14.0
                  [--board-name "VOR board"] [--board <id>] [--project KEY]
                  [--issue-type Task] [--dry-run] [--yes] [--verbose]
```
- `--sprint` must be a positive integer. `--version` must be non-empty after trimming and contain no newline.
- By default the tool resolves everything, prints the plan (parent summary; create or reuse; which subtasks will be created), and asks for confirmation. `--yes` skips the prompt. `--dry-run` prints the plan and exits 0 without asking.
- The result lists the parent key and each subtask key, marked `created` or `existing`, with `{base}/browse/{KEY}` links.

### D10. Async kept for consistency
The flow is essentially sequential, but keeping `httpx.AsyncClient` means the copied client code, the `respx` test setup and the retry and sleep seams from `sprint-work-hours` carry over unchanged.

## Risks / Trade-offs

- [Token lacks create or schedule permission] → Map 403 on create to a message naming *Create Issues*, and on add-to-sprint to *Schedule Issues*, so the user knows which permission to request. Dry-run doesn't need write permission, so it can't catch this.
- [Parent created but add-to-sprint fails] → The parent exists outside the sprint, and a re-run would not find it (D7). Mitigation: the error prints the orphan key and a direct instruction to move it into the sprint or delete it. The add-to-sprint call happens immediately after the create, before any subtask, to keep that window small.
- [Timed-out create that actually succeeded] → Not retried (D8). The user re-runs, and D7 finds it if the add-to-sprint also happened. If the add-to-sprint did not happen, the previous risk applies.
- [Someone renames a subtask manually] → The renamed one no longer matches exactly, so a re-run recreates the original. That is acceptable and visible in the output as `created`.
- [Summary template drift] → Guarded by the exact-string unit test (D2).
- [Copy-paste divergence from `sprint-work-hours`] → Accepted cost of D1. The copied modules keep the same names so a later extraction is mechanical.

## Migration Plan

This is a new tool with no existing data, so there is nothing to migrate. Rollout:
1. Install with `pip install -e create-release-task`.
2. Run `--dry-run` against a real upcoming sprint and check the plan.
3. Run it for real once and check the result in Jira.

There is no rollback beyond uninstalling. Any issues it created are ordinary Jira issues.

## Open Questions

- Should `--version` be validated against a pattern (for example `^\d+\.\d+\.\d+$`), or accepted free-form? This design accepts it free-form.
- Is the parent issue type on the VOR project really `Task`? The `--issue-type` override covers it if not.
- Should the parent task get an assignee (for example the person running the tool)? Out of scope for now.
