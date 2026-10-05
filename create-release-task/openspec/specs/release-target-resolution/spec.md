# release-target-resolution Specification

## Purpose
TBD - created by archiving change create-release-task. Update Purpose after archive.
## Requirements
### Requirement: Board resolution
The system SHALL resolve the target board from `--board <id>` when given, and otherwise from `--board-name`, which defaults to `VOR board`. A board name SHALL match exactly one board by exact name.

#### Scenario: Default board name
- **WHEN** neither `--board` nor `--board-name` is supplied
- **THEN** the system looks up the board named `VOR board`

#### Scenario: Board name not found
- **WHEN** no board has the given name
- **THEN** the system fails with a not-found error naming the board

#### Scenario: Board name ambiguous
- **WHEN** more than one board has the given name
- **THEN** the system fails listing each matching board id, and tells the user to pass `--board <id>`

### Requirement: Sprint resolution by number
The system SHALL derive the sprint name `reseller <N>` from `--sprint <N>` and resolve it to exactly one sprint on the board among sprints in state `active` or `future`. Name matching SHALL ignore case and collapse whitespace.

#### Scenario: Future sprint found
- **WHEN** `--sprint 97` is given and the board has a future sprint named `Reseller  97`
- **THEN** that sprint is resolved

#### Scenario: Active sprint found
- **WHEN** `--sprint 97` is given and `reseller 97` is the board's active sprint
- **THEN** that sprint is resolved

#### Scenario: Sprint is closed
- **WHEN** `reseller 97` exists on the board only in state `closed`
- **THEN** the system fails saying the sprint is closed and cannot take new issues

#### Scenario: Sprint does not exist
- **WHEN** no sprint named `reseller 97` exists in any state
- **THEN** the system fails with a not-found error listing up to 10 of the board's most recent open sprint names

#### Scenario: Sprint name ambiguous
- **WHEN** more than one open sprint is named `reseller 97`
- **THEN** the system fails listing each candidate's id, state, and start date

#### Scenario: Numbers do not partially match
- **WHEN** `--sprint 9` is given and only `reseller 97` exists
- **THEN** no sprint matches

### Requirement: Project resolution
The system SHALL use `--project <KEY>` when given. Otherwise it SHALL use the board's `location.projectKey`, or else the single project returned for the board. If the board spans several projects and `--project` is not given, it SHALL fail.

#### Scenario: Project-located board
- **WHEN** the board's location is project `VOR`
- **THEN** `VOR` is the target project

#### Scenario: Multi-project board without override
- **WHEN** the board is associated with projects `VOR` and `RES`, and `--project` is not given
- **THEN** the system fails listing `VOR, RES` and tells the user to pass `--project`

#### Scenario: Explicit override
- **WHEN** `--project RES` is given
- **THEN** `RES` is the target project, whatever the board location says

### Requirement: Issue type resolution
The system SHALL resolve the parent issue type as the non-subtask type in the target project whose name equals `--issue-type` (default `Task`), ignoring case. It SHALL resolve the subtask type as the project's single type with `subtask: true`. If there are several, it SHALL prefer the one named `Sub-task` or `Subtask`, ignoring case.

#### Scenario: Standard types
- **WHEN** the project offers `Task` (subtask=false) and `Sub-task` (subtask=true)
- **THEN** the parent type is `Task` and the subtask type is `Sub-task`, each by id

#### Scenario: Parent type missing
- **WHEN** the project has no non-subtask type named `Task`
- **THEN** the system fails listing the project's available non-subtask type names

#### Scenario: No subtask type
- **WHEN** the project has no type with `subtask: true`
- **THEN** the system fails saying the project does not allow subtasks

#### Scenario: Ambiguous subtask type
- **WHEN** the project has subtask types `QA Check` and `Dev Step`, and neither is named `Sub-task` or `Subtask`
- **THEN** the system fails listing both names

