## ADDED Requirements

### Requirement: Command arguments
The CLI `jira-release-task` SHALL accept the required `--sprint <N>` and `--version <V>`, and the optional `--board <id>`, `--board-name <name>` (default `VOR board`), `--project <KEY>`, `--issue-type <name>` (default `Task`), `--dry-run`, `--yes`, `--verbose`, and `--help`.

#### Scenario: Help
- **WHEN** the command is run with `--help` or with no arguments
- **THEN** usage is printed listing every option, and the exit code is 0

#### Scenario: Missing required argument
- **WHEN** `--sprint` or `--version` is omitted
- **THEN** the CLI exits non-zero naming the missing option, and makes no network request

### Requirement: Input validation before network access
The CLI SHALL reject, before any network request, a `--sprint` value that is not a positive integer, a `--version` that is empty or whitespace-only after trimming or that contains a line break, and the combination of `--board` with a non-default `--board-name`.

#### Scenario: Non-numeric sprint
- **WHEN** `--sprint abc` is given
- **THEN** the CLI exits non-zero with a message that the sprint must be a positive integer

#### Scenario: Zero sprint
- **WHEN** `--sprint 0` is given
- **THEN** the CLI exits non-zero with the same message

#### Scenario: Blank version
- **WHEN** `--version "   "` is given
- **THEN** the CLI exits non-zero with a message that the version must not be empty

#### Scenario: Conflicting board selectors
- **WHEN** both `--board 12` and `--board-name "Other"` are given
- **THEN** the CLI exits non-zero telling the user to pick one

### Requirement: Plan preview and confirmation
After resolving targets and detecting existing issues, the CLI SHALL print a plan showing the board, sprint (name and id), project key, the parent summary marked `create` or `existing <KEY>`, and each checklist subtask marked `create` or `existing <KEY>`. It SHALL then ask for confirmation before writing, unless `--yes` is given. If nothing needs creating, it SHALL skip the prompt.

#### Scenario: Interactive confirmation accepted
- **WHEN** the plan contains writes and the user answers `y`
- **THEN** the plan is executed

#### Scenario: Interactive confirmation declined
- **WHEN** the user answers anything other than `y`/`yes`
- **THEN** no write is made, a line says nothing was created, and the exit code is 0

#### Scenario: Non-interactive with --yes
- **WHEN** `--yes` is given
- **THEN** the plan is printed and executed without a prompt

#### Scenario: Non-TTY without --yes
- **WHEN** stdin is not a terminal, the plan contains writes, and `--yes` is not given
- **THEN** the CLI makes no write, and exits non-zero telling the user to pass `--yes`

### Requirement: Dry run
With `--dry-run`, the CLI SHALL perform all reads (board, sprint, project, issue types, existing-task search), print the plan, and exit 0 without prompting and without making any write request.

#### Scenario: Dry run makes no writes
- **WHEN** `--dry-run` is given and the plan would create ten issues
- **THEN** the plan is printed, zero `POST /rest/api/3/issue` or add-to-sprint requests are made, and the exit code is 0

### Requirement: Result output
After a run with writes, the CLI SHALL print the parent and each checklist subtask with its key, its summary, whether it was `created` or `existing`, and a browse URL of the form `<JIRA_BASE_URL>/browse/<KEY>`.

#### Scenario: Successful creation output
- **WHEN** a parent and nine subtasks are created
- **THEN** ten lines are printed, all marked `created`, each with a browse URL, followed by a summary line `Created 10 issues in reseller 97.`

### Requirement: Error reporting and exit codes
The CLI SHALL exit 0 on success, on declined confirmation, on dry run, and when nothing needed creating. For any other failure it SHALL exit non-zero and print a single-line, actionable error to stderr, with no traceback unless `--verbose` is given. When a failure happens after some writes, the CLI SHALL list what was created before the error line.

#### Scenario: Missing credentials
- **WHEN** `JIRA_API_TOKEN` is unset
- **THEN** the CLI exits non-zero with a message naming `JIRA_API_TOKEN` and the URL to create a token, with no traceback

#### Scenario: Verbose failure
- **WHEN** a failure occurs and `--verbose` is given
- **THEN** the full traceback is printed after the error line

#### Scenario: Partial failure
- **WHEN** a failure occurs after the parent and three subtasks are created
- **THEN** those four keys are printed as `created`, followed by the error line, and the exit code is non-zero
