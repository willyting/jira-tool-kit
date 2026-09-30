## ADDED Requirements

### Requirement: Resolve a sprint by name
The system SHALL resolve a human-readable sprint name against a specified board to exactly one sprint. Matching SHALL be case-insensitive and whitespace-trimmed.

#### Scenario: Exactly one sprint matches
- **WHEN** the board has one sprint whose name matches the supplied name
- **THEN** that sprint is selected and its id, name, state, and dates are used for the rest of the run

#### Scenario: No sprint matches
- **WHEN** no sprint on the board matches the supplied name
- **THEN** the run fails with an error that lists the names of the board's most recent sprints so the user can correct the spelling

#### Scenario: Multiple sprints share the name
- **WHEN** more than one sprint on the board matches the supplied name
- **THEN** the run fails with an error listing each matching sprint's id, state, and start date, and instructs the user to disambiguate by sprint id

#### Scenario: Case and padding differences
- **WHEN** the user supplies `"  sprint 42 "` and the board has a sprint named `"Sprint 42"`
- **THEN** the sprint is matched successfully

### Requirement: Sprint time window derivation
The system SHALL derive an inclusive-start, inclusive-end time window from the resolved sprint. The window start SHALL be the sprint's `startDate`. The window end SHALL be `completeDate` when the sprint is closed, `endDate` when the sprint is closed without a complete date, and the current time when the sprint is active. All comparisons SHALL be performed in UTC.

#### Scenario: Closed sprint
- **WHEN** the resolved sprint is closed and has a `completeDate`
- **THEN** the window runs from `startDate` to `completeDate`

#### Scenario: Active sprint
- **WHEN** the resolved sprint state is `active`
- **THEN** the window runs from `startDate` to the current UTC time, and the report notes that the sprint is still in progress

#### Scenario: Future sprint with no start date
- **WHEN** the resolved sprint has no `startDate`
- **THEN** the run fails with an error stating that a sprint that has not started cannot be reported on

#### Scenario: Mixed timezone offsets
- **WHEN** sprint dates and changelog timestamps arrive with differing UTC offsets
- **THEN** all values are normalised to UTC before any comparison

### Requirement: Candidate issue set includes subtasks of sprint members
The system SHALL build the candidate issue set as the union of (a) all issues returned by `sprint = <sprintId>` and (b) all subtasks of those issues, deduplicated by issue key. Subtasks SHALL be included regardless of whether they themselves carry the sprint field.

#### Scenario: Parent in sprint with unassigned subtasks
- **WHEN** a story is a sprint member and has three subtasks, none of which carry the sprint field
- **THEN** all three subtasks appear in the candidate set alongside the story

#### Scenario: Subtask already returned by the sprint query
- **WHEN** a subtask is both a sprint member and a child of another sprint member
- **THEN** it appears exactly once in the candidate set

#### Scenario: Parent-child relationships are retained
- **WHEN** the candidate set is built
- **THEN** each issue records its issue type, whether it is a subtask, and its parent key when it has one, so aggregation can apply parent/child rules

#### Scenario: Sprint contains no issues
- **WHEN** the sprint query returns zero issues
- **THEN** the candidate set is empty and the run proceeds to produce a zero-total report rather than failing

### Requirement: Field selection for candidate issues
The system SHALL request, for every candidate issue, at minimum: issue key, summary, issue type, status, parent, assignee, and `timeoriginalestimate`.

#### Scenario: Required fields are requested explicitly
- **WHEN** candidate issues are fetched
- **THEN** the search request names each required field explicitly, because the enhanced JQL endpoint returns no fields by default
