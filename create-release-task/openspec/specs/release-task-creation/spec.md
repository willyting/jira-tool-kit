# release-task-creation Specification

## Purpose
TBD - created by archiving change create-release-task. Update Purpose after archive.
## Requirements
### Requirement: Parent summary format
The system SHALL build the parent summary as `release <N> ------- <V> -----------------------------------`: the literal word `release`, one space, the sprint number, one space, exactly 7 hyphens, one space, the version with outer whitespace trimmed, one space, and exactly 35 hyphens.

#### Scenario: Summary for sprint 97, version 2.14.0
- **WHEN** the sprint number is `97` and the version is `2.14.0`
- **THEN** the summary is exactly `release 97 ------- 2.14.0 -----------------------------------`

#### Scenario: Version with surrounding whitespace
- **WHEN** the version is given as `  2.14.0 `
- **THEN** the summary uses `2.14.0`

#### Scenario: Version kept verbatim
- **WHEN** the version is given as `v2.14.0-rc1`
- **THEN** the summary contains `v2.14.0-rc1` unchanged

### Requirement: Fixed subtask checklist
The system SHALL use exactly these nine subtask summaries, in this order: `create portal branch`, `create backend branch`, `check release note`, `test vpp on stage`, `run e2e test on stage`, `check new feature on stage`, `run api test on stage`, `check sap on stage`, `check on prod`.

#### Scenario: Checklist contents
- **WHEN** the checklist is read
- **THEN** it contains those nine summaries in that order, and nothing else

### Requirement: Detect an existing release task
Before any write, the system SHALL search the resolved sprint for issues of the parent issue type and compare each `summary` exactly (case-sensitive, after trimming outer whitespace) against the built parent summary. JQL text search SHALL NOT be used to decide a match.

#### Scenario: No existing task
- **WHEN** no issue in the sprint has the exact summary
- **THEN** the plan says to create the parent

#### Scenario: One existing task
- **WHEN** exactly one issue in the sprint has the exact summary
- **THEN** the plan reuses that issue as the parent, and no new parent is created

#### Scenario: Near miss is not a match
- **WHEN** the sprint contains `release 97 ------ 2.14.0 ---` (different dash counts)
- **THEN** it is not treated as a match, and the plan says to create the parent

#### Scenario: Duplicate existing tasks
- **WHEN** two or more issues in the sprint have the exact summary
- **THEN** the system fails before any write, listing their keys

### Requirement: Create only missing subtasks
The system SHALL compare the parent's existing subtask summaries exactly (trimmed, case-sensitive) against the checklist, and plan to create only the checklist entries that are absent, keeping checklist order. Existing subtasks that are not on the checklist SHALL be left alone.

#### Scenario: Fresh parent
- **WHEN** the parent is being created
- **THEN** all nine subtasks are planned for creation, in checklist order

#### Scenario: Partially complete parent
- **WHEN** the existing parent already has `create portal branch` and `check release note`
- **THEN** only the other seven are planned, in checklist order

#### Scenario: Complete parent
- **WHEN** the existing parent already has all nine
- **THEN** nothing is planned, and the run reports the release task is already complete

#### Scenario: Extra subtasks are ignored
- **WHEN** the existing parent also has a subtask `hotfix follow-up`
- **THEN** it is neither changed nor reported as missing

### Requirement: Execute the plan in order
When executing, the system SHALL: (1) create the parent if planned; (2) add a newly created parent to the resolved sprint immediately, before any subtask is created; (3) create each planned subtask sequentially in checklist order, with `parent` set to the parent key and the resolved subtask issue type. Subtasks SHALL NOT be added to the sprint separately.

#### Scenario: Full creation
- **WHEN** a plan with a new parent and nine subtasks runs successfully
- **THEN** one parent is created and added to the sprint, then nine subtasks are created in checklist order under it

#### Scenario: Reused parent is not moved
- **WHEN** the parent is reused
- **THEN** no add-to-sprint call is made

### Requirement: Stop on first write failure without rollback
If any write fails, the system SHALL stop at once, SHALL NOT attempt the remaining writes, and SHALL NOT delete or modify anything already created. It SHALL report every issue created so far along with the error.

#### Scenario: Subtask creation fails midway
- **WHEN** the fifth subtask's create call fails
- **THEN** the run stops, reports the parent and the four created subtask keys plus the error, and says that re-running the same command will create the rest

#### Scenario: Add-to-sprint fails after the parent is created
- **WHEN** the parent is created but adding it to the sprint fails
- **THEN** no subtasks are created, and the error names the parent key and says it is outside the sprint and must be moved into `reseller <N>` or deleted before re-running

### Requirement: Re-running is idempotent
Running the same command again after a successful run SHALL perform no writes. Running it again after a failed run SHALL create only what is still missing.

#### Scenario: Second successful run
- **WHEN** the command is run twice with the same sprint and version
- **THEN** the second run creates no issues and reports every item as `existing`

#### Scenario: Resume after partial failure
- **WHEN** a run failed after creating the parent and four subtasks, and the command is run again
- **THEN** the second run reuses the parent and creates exactly the five missing subtasks

