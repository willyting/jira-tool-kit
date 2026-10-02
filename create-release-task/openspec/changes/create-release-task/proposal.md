## Why

Every reseller release on the VOR board starts with the same manual chore: open Jira, create a task titled `release <N> ------- <version> -----------------------------------` in the right `reseller <N>` sprint, then add the same nine checklist subtasks one by one. It is slow and it drifts: titles get mistyped, a subtask gets forgotten, or the task lands in the wrong sprint. A small CLI that takes a sprint number and a version and builds the whole structure produces identical release checklists every time.

## What Changes

- New Python CLI (`jira-release-task`) in `create-release-task/`, a sibling of `sprint-work-hours/`, following the same stack (httpx, typer, rich) and credential model.
- Given `--sprint <N>` and `--version <V>`, the tool:
  - resolves the board named `VOR board` (overridable) and, on it, the sprint named `reseller <N>`;
  - creates one parent task with the summary exactly `release <N> ------- <V> -----------------------------------`;
  - adds that task to the resolved sprint;
  - creates nine subtasks under it, in this order: `create portal branch`, `create backend branch`, `check release note`, `test vpp on stage`, `run e2e test on stage`, `check new feature on stage`, `run api test on stage`, `check sap on stage`, `check on prod`.
- The target project comes from the board, so the user never has to supply a project key.
- **Safe re-runs:** if a release task with the same summary already exists in the sprint, the tool reuses it and creates only the subtasks that are missing. Running it twice never makes a duplicate release task, and a run that failed partway can be finished by running it again.
- `--dry-run` resolves the board, sprint, project and issue types, then prints what would be created without writing anything.
- Output lists the parent key and each subtask key with a browse URL. Errors print as one actionable line and a non-zero exit code.

## Capabilities

### New Capabilities

- `jira-client`: Authenticated access to Jira Cloud for a write workflow: credential loading, board lookup, sprint listing, board-to-project resolution, project issue-type discovery, JQL search, issue creation, and adding issues to a sprint. Includes retry, rate-limit handling and typed errors.
- `release-target-resolution`: Turning a board name and a sprint number into exactly one board, one open sprint named `reseller <N>`, the board's project, and that project's standard and subtask issue types.
- `release-task-creation`: Building the parent summary from the sprint number and version, detecting an existing release task, creating or reusing the parent, placing it in the sprint, and creating the missing subtasks from the fixed checklist in order.
- `cli-release`: The command-line surface: arguments, input validation, `--dry-run`, `--verbose`, the result listing, exit codes, and error messages.

### Modified Capabilities

None. This is a new, independent tool, and `create-release-task/openspec/specs/` is empty. `sprint-work-hours` is not changed.

## Impact

- **New codebase** under `create-release-task/`: its own `pyproject.toml`, package, tests and OpenSpec project. There is no shared library with `sprint-work-hours`. The relevant client pieces are copied and extended rather than imported, so each tool stays independently installable.
- **Writes to Jira:** unlike `sprint-work-hours`, this tool creates issues and changes sprint membership on `https://dibts3.atlassian.net`. The API token needs *Create Issues* and *Schedule Issues* (sprint edit) permission on the VOR board's project, not just read access.
- **APIs used:** Agile `/rest/agile/1.0` (boards, sprints, board project, add-to-sprint) and platform `/rest/api/3` (`POST /issue`, `POST /search/jql`, project issue types). The removed `/rest/api/3/search` is not used.
- **Credentials:** the same `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` environment variables. Nothing is written to disk.
- **Irreversibility:** created issues are not rolled back automatically on partial failure (deleting issues is more dangerous than leaving them). The output lists exactly what was created, and re-running finishes the job.
