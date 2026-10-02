## 1. Project Scaffolding

- [x] 1.1 Create `create-release-task/pyproject.toml` targeting Python 3.11+, with `httpx`, `typer`, `rich` as runtime deps, `pytest`, `pytest-asyncio`, `respx` as dev deps, and a `jira-release-task` entry point at `jira_release_task.cli:app`
- [x] 1.2 Create the `src/jira_release_task/` package with modules `cli.py`, `config.py`, `client.py`, `errors.py`, `targets.py`, `checklist.py`, `plan.py`, `execute.py`, `report.py`
- [x] 1.3 Create `tests/conftest.py`, `.gitignore` (Python artifacts, `.venv`, `.env`) and `.env.example` listing the three `JIRA_*` variables with no real values
- [x] 1.4 Verify `pip install -e ".[dev]"` succeeds and `jira-release-task --help` runs

## 2. Errors and Configuration

- [x] 2.1 Copy `errors.py` from `sprint-work-hours`, and add `WriteUncertainError` (a write that failed in a way that means it may have been applied) and `PartialWriteError` (carries the list of issues created before the failure)
- [x] 2.2 Copy `config.py` (`JiraConfig` with `repr=False` token, `load_config`) unchanged
- [x] 2.3 Tests: each variable missing, blank-counts-as-missing, all present, token absent from every error message and `repr`

## 3. Jira Client

- [x] 3.1 Copy the `JiraClient` core (Basic auth, `_classify`, `_request`, backoff, `search_jql` with cursor guards, `_paginate_agile`) from `sprint-work-hours`
- [x] 3.2 Add an `is_write` flag to `_request`: when set, retry only on 429, and raise `WriteUncertainError` right away on network errors and 5xx
- [x] 3.3 Add `list_boards(name)`, `get_board(id)`, `list_board_projects(id)`, and `list_sprints(board_id, state=None)`
- [x] 3.4 Add `get_create_issue_types(project_key)` against `/rest/api/3/issue/createmeta/{key}/issuetypes`, paginated
- [x] 3.5 Add `create_issue(project_key, issue_type_id, summary, parent_key=None)` returning `{key, id}`, and `add_issues_to_sprint(sprint_id, keys)` accepting a 204 response
- [x] 3.6 Add action-specific 403 messages: *Create Issues* for issue create, *Schedule Issues* for add-to-sprint
- [x] 3.7 `respx` tests: create payload shape (with and without parent), 400 field-error text surfaced, 403 messages, write not retried on 500 or timeout, write retried on 429, read retried on 503, sprint `state` param passed, createmeta pagination

## 4. Target Resolution

- [x] 4.1 In `targets.py`, resolve the board from `--board` id or exact `--board-name` (default `VOR board`), with not-found and ambiguous errors
- [x] 4.2 Build the sprint name `reseller {N}` and match open sprints (`active,future`) case-insensitively with whitespace collapsed; reuse the reporter's no-match (≤10 recent names) and ambiguous (id/state/start) messages
- [x] 4.3 When no open sprint matches, do a follow-up lookup with `state=closed`, so a closed-sprint match gets the "sprint is closed" error
- [x] 4.4 Resolve the project: `--project` override, else `location.projectKey`, else the single board project, else an error listing the project keys
- [x] 4.5 Resolve issue types: the parent type by name (default `Task`, case-insensitive, non-subtask); the subtask type as the single `subtask: true` type, preferring `Sub-task`/`Subtask`; errors list the available names
- [x] 4.6 Return a frozen `ReleaseTarget` dataclass (board, sprint id and name, project key, parent type id, subtask type id)
- [x] 4.7 Tests for every scenario in `specs/release-target-resolution/spec.md`, including `--sprint 9` not matching `reseller 97`

## 5. Checklist and Plan

- [x] 5.1 In `checklist.py`, define the `PARENT_SUMMARY` template and the ordered 9-item `SUBTASK_SUMMARIES` tuple, plus `build_parent_summary(number, version)` that trims the version
- [x] 5.2 Test the exact output `release 97 ------- 2.14.0 -----------------------------------`, the dash counts 7 and 35, version trimming, verbatim `v2.14.0-rc1`, and the exact checklist contents and order
- [x] 5.3 In `plan.py`, search `sprint = {id} AND issuetype = {parentTypeId}` with fields `summary,subtasks`, and filter by exact trimmed summary on the client side
- [x] 5.4 Build a `Plan`: parent as `create` or `existing(key)`, and each checklist item as `create` or `existing(key)` by exact match against the reused parent's subtasks; raise before any write when there are duplicate parents
- [x] 5.5 Tests: no match, one match, near-miss dash counts, duplicate parents, fresh/partial/complete subtask sets, extra non-checklist subtasks ignored

## 6. Plan Execution

- [x] 6.1 In `execute.py`, create the parent if planned, then call add-to-sprint immediately, before any subtask
- [x] 6.2 Create the planned subtasks sequentially in checklist order, with `parent_key` and the subtask type id
- [x] 6.3 On the first failure, stop and raise `PartialWriteError` carrying the issues created so far; never delete anything
- [x] 6.4 When add-to-sprint fails after the parent is created, raise an error naming the orphan key and saying to move it into `reseller <N>` or delete it
- [x] 6.5 Skip add-to-sprint when the parent is reused
- [x] 6.6 Tests with a stub client: full run order (parent → sprint → 9 subtasks), reused parent (no sprint call), failure at subtask 5 (4 reported, none after), add-to-sprint failure (no subtasks), second run makes zero writes, resume after partial failure creates exactly the missing ones

## 7. Report Rendering

- [x] 7.1 In `report.py`, render the plan: board, sprint name and id, project, the parent line, and 9 subtask lines marked `create` or `existing KEY`
- [x] 7.2 Render the result: each line with key, summary, `created`/`existing`, and `{base}/browse/{KEY}`, followed by `Created N issues in reseller <N>.` or `Release task already complete.`
- [x] 7.3 Render a partial failure: the created keys, then the single error line
- [x] 7.4 Tests for plan, result, already-complete and partial-failure output

## 8. CLI Wiring

- [x] 8.1 Implement the `typer` command with `--sprint`, `--version`, `--board`, `--board-name`, `--project`, `--issue-type`, `--dry-run`, `--yes`, `--verbose`; `no_args_is_help=True`
- [x] 8.2 Validate before any network call: the sprint is a positive int, the version is non-blank with no line break, and `--board` is not combined with a non-default `--board-name`
- [x] 8.3 Wire the pipeline: config → client → targets → plan → print plan → (dry-run exit | nothing-to-do exit | confirm) → execute → result
- [x] 8.4 Confirmation: prompt `Create these issues? [y/N]` on a TTY; on a non-TTY without `--yes`, fail non-zero; a declined prompt exits 0 with "Nothing was created."
- [x] 8.5 Top-level error handling: a single line on stderr and a non-zero exit, traceback only with `--verbose`, and partial-write output printed before the error
- [x] 8.6 Put `client_factory` behind a seam (as `sprint-work-hours` does) and write end-to-end CLI tests: success with `--yes`, dry run (assert zero POSTs), declined prompt, non-TTY without `--yes`, each validation error, missing token, and partial failure exit code

## 9. Documentation and Verification

- [x] 9.1 Write `create-release-task/README.md`: setup, credentials and the required *Create Issues*/*Schedule Issues* permissions, usage examples (`--dry-run` first), the exact summary format and checklist, re-run behaviour, and what to do with an orphaned parent
- [x] 9.2 Run the full test suite and confirm each scenario in all four spec files has a passing test
- [ ] 9.3 Manually run `--dry-run` against a real upcoming `reseller <N>` sprint on the VOR board and confirm the resolved project and issue types look right
