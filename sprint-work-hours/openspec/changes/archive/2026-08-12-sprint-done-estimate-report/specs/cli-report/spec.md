## ADDED Requirements

### Requirement: Command-line interface
The tool SHALL expose a single command accepting `--sprint <name>` (required) and a board selector (`--board <id>` or `--board-name <name>`, exactly one required). It SHALL support `--verbose` for progress detail and `--help` for usage.

#### Scenario: Minimal valid invocation
- **WHEN** the user runs the command with `--sprint "Sprint 42" --board 7`
- **THEN** the tool resolves that sprint on board 7 and prints the report

#### Scenario: Sprint argument omitted
- **WHEN** `--sprint` is not supplied
- **THEN** the tool exits non-zero with a usage message and makes no network request

#### Scenario: Both board selectors supplied
- **WHEN** both `--board` and `--board-name` are supplied
- **THEN** the tool exits non-zero with an error stating that the selectors are mutually exclusive

#### Scenario: No board selector supplied
- **WHEN** neither `--board` nor `--board-name` is supplied
- **THEN** the tool exits non-zero with an error naming both options

### Requirement: Console summary
The tool SHALL print a summary containing the resolved sprint name and id, the sprint window in UTC, the total original estimate in hours, the count of qualifying issues split into tasks and subtasks, and the count of qualifying issues lacking an estimate.

#### Scenario: Standard summary
- **WHEN** a run completes with qualifying issues
- **THEN** the summary shows sprint name and id, window start and end, total hours, qualifying counts by kind, and the unestimated count

#### Scenario: Active sprint is labelled
- **WHEN** the resolved sprint is still active
- **THEN** the summary states that the sprint is in progress and that the window end is the current time

#### Scenario: No qualifying issues
- **WHEN** no issue transitioned to done inside the window
- **THEN** the tool prints a total of `0h`, states that no issues qualified, and exits zero

### Requirement: Per-issue table
The tool SHALL print a table of qualifying issues showing issue key, type, whether it is a subtask, summary, assignee, the qualifying transition timestamp, and the original estimate in hours. Rows whose estimate was excluded by the leaf-preferring rule SHALL be visibly marked.

#### Scenario: Table contents
- **WHEN** the report is printed
- **THEN** each qualifying issue occupies exactly one row with all listed columns populated, using an explicit placeholder where a value is absent

#### Scenario: Ordering
- **WHEN** the table is printed
- **THEN** rows are grouped so each parent is immediately followed by its qualifying subtasks, and groups are ordered by earliest qualifying transition timestamp

#### Scenario: Rolled-up parent is marked
- **WHEN** a parent's estimate was excluded because its subtasks qualified
- **THEN** its row shows the excluded estimate with an explicit exclusion marker and contributes nothing to the total column

#### Scenario: Unassigned issue
- **WHEN** a qualifying issue has no assignee
- **THEN** the assignee column reads `Unassigned` rather than being blank

#### Scenario: Long summaries
- **WHEN** an issue summary is longer than the column width
- **THEN** it is truncated with an ellipsis so the table stays aligned

### Requirement: Actionable error reporting and exit codes
The tool SHALL exit `0` on success, and non-zero with a single-line, human-readable message on failure. Configuration, authentication, and not-found failures SHALL be reported without a Python traceback unless `--verbose` is supplied.

#### Scenario: Missing credentials
- **WHEN** `JIRA_API_TOKEN` is unset
- **THEN** the tool exits non-zero with a message naming the variable and how to create an Atlassian API token, and prints no traceback

#### Scenario: Authentication rejected
- **WHEN** Jira responds `401`
- **THEN** the tool exits non-zero telling the user to verify `JIRA_EMAIL` and `JIRA_API_TOKEN`

#### Scenario: Verbose failure
- **WHEN** a failure occurs and `--verbose` was supplied
- **THEN** the tool prints the full traceback in addition to the human-readable message

#### Scenario: Successful run
- **WHEN** the report prints without error
- **THEN** the process exits `0`
