## MODIFIED Requirements

### Requirement: Fixed subtask checklist
The system SHALL use exactly these ten subtask summaries, in this order: `check feature toggle SRE request`, `create portal branch`, `create backend branch`, `check release note`, `test vpp on stage`, `run e2e test on stage`, `check new feature on stage`, `run api test on stage`, `check sap on stage`, `check on prod`.

#### Scenario: Checklist contents
- **WHEN** the checklist is read
- **THEN** it contains those ten summaries in that order, and nothing else

#### Scenario: Feature toggle check comes first
- **WHEN** the checklist is read
- **THEN** its first entry is exactly `check feature toggle SRE request`, with `SRE` in capitals

### Requirement: Create only missing subtasks
The system SHALL compare the parent's existing subtask summaries exactly (trimmed, case-sensitive) against the checklist, and plan to create only the checklist entries that are absent, keeping checklist order. Existing subtasks that are not on the checklist SHALL be left alone.

#### Scenario: Fresh parent
- **WHEN** the parent is being created
- **THEN** all ten subtasks are planned for creation, in checklist order

#### Scenario: Partially complete parent
- **WHEN** the existing parent already has `create portal branch` and `check release note`
- **THEN** only the other eight are planned, in checklist order

#### Scenario: Release task created before the checklist grew
- **WHEN** the existing parent has the nine original subtasks but not `check feature toggle SRE request`
- **THEN** only `check feature toggle SRE request` is planned, and existing subtasks are not reordered

#### Scenario: Complete parent
- **WHEN** the existing parent already has all ten
- **THEN** nothing is planned, and the run reports the release task is already complete

#### Scenario: Extra subtasks are ignored
- **WHEN** the existing parent also has a subtask `hotfix follow-up`
- **THEN** it is neither changed nor reported as missing

### Requirement: Execute the plan in order
When executing, the system SHALL: (1) create the parent if planned; (2) add a newly created parent to the resolved sprint immediately, before any subtask is created; (3) create each planned subtask sequentially in checklist order, with `parent` set to the parent key and the resolved subtask issue type. Subtasks SHALL NOT be added to the sprint separately.

#### Scenario: Full creation
- **WHEN** a plan with a new parent and ten subtasks runs successfully
- **THEN** one parent is created and added to the sprint, then ten subtasks are created in checklist order under it, the first being `check feature toggle SRE request`

#### Scenario: Reused parent is not moved
- **WHEN** the parent is reused
- **THEN** no add-to-sprint call is made

### Requirement: Re-running is idempotent
Running the same command again after a successful run SHALL perform no writes. Running it again after a failed run SHALL create only what is still missing.

#### Scenario: Second successful run
- **WHEN** the command is run twice with the same sprint and version
- **THEN** the second run creates no issues and reports every item as `existing`

#### Scenario: Resume after partial failure
- **WHEN** a run failed after creating the parent and four subtasks, and the command is run again
- **THEN** the second run reuses the parent and creates exactly the six missing subtasks
