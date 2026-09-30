## ADDED Requirements

### Requirement: Done is determined from status-category transitions in the changelog
An issue SHALL qualify as done-in-sprint if and only if its changelog contains at least one `status` field change whose destination status belongs to the `done` status category and whose timestamp falls inside the sprint window. The issue's current status SHALL NOT be used to make this determination.

#### Scenario: Transitioned to Done inside the window
- **WHEN** an issue moved from `In Progress` to `Done` at a timestamp within the sprint window
- **THEN** the issue qualifies, and the qualifying timestamp is recorded for the report

#### Scenario: Transitioned to Done before the sprint started
- **WHEN** an issue's only transition into a done-category status predates the window start
- **THEN** the issue does not qualify

#### Scenario: Transitioned to Done after the window closed
- **WHEN** an issue's only transition into a done-category status falls after the window end
- **THEN** the issue does not qualify

#### Scenario: Done now, but transitioned earlier
- **WHEN** an issue's current status is `Done` but no transition into a done-category status occurred inside the window
- **THEN** the issue does not qualify, even though it currently reads as done

#### Scenario: Completed then reopened within the sprint
- **WHEN** an issue transitioned into `Done` inside the window and later transitioned back to `In Progress`, still inside the window
- **THEN** the issue qualifies, and the report flags it as reopened after completion

#### Scenario: Multiple qualifying transitions
- **WHEN** an issue entered a done-category status more than once inside the window
- **THEN** the issue is counted exactly once, and the earliest qualifying transition timestamp is reported

#### Scenario: Custom done-category status
- **WHEN** a workflow uses a custom status name such as `Released` that Jira classifies in the `done` status category
- **THEN** a transition into that status qualifies, because classification is by status category and not by status name

#### Scenario: Transition between two done statuses
- **WHEN** an issue moves from one done-category status directly to another done-category status inside the window, having entered the done category before the window
- **THEN** the issue does not qualify, because it did not enter the done category during the window

### Requirement: Leaf-preferring estimate aggregation
The system SHALL aggregate `timeoriginalestimate` over qualifying issues such that a qualifying parent's own estimate is excluded when that parent has one or more qualifying subtasks. A qualifying parent with no qualifying subtasks SHALL contribute its own estimate. Qualifying subtasks SHALL always contribute their own estimates.

#### Scenario: Parent and its subtasks both qualify
- **WHEN** a parent with an 8h estimate qualifies and two of its subtasks qualify with 3h and 4h
- **THEN** the total contribution is 7h, and the parent's own 8h is excluded from the total

#### Scenario: Parent qualifies with no qualifying subtasks
- **WHEN** a parent with a 5h estimate qualifies and none of its subtasks qualify
- **THEN** the parent contributes its full 5h

#### Scenario: Subtask qualifies but its parent does not
- **WHEN** a subtask with a 2h estimate qualifies while its parent did not transition to done in the window
- **THEN** the subtask contributes 2h and the parent contributes nothing

#### Scenario: Excluded parent estimate is visible
- **WHEN** a parent's own estimate is excluded by the leaf-preferring rule
- **THEN** the per-issue output marks that parent as rolled-up-excluded and shows the excluded amount, so the number can be audited

#### Scenario: Standalone issue with no parent and no subtasks
- **WHEN** a qualifying task has neither a parent nor subtasks
- **THEN** it contributes its own estimate

### Requirement: Missing estimates are surfaced, not silently zeroed
Issues that qualify but have a null or absent `timeoriginalestimate` SHALL contribute zero to the total AND SHALL be counted and reported separately as unestimated.

#### Scenario: Qualifying issue without an estimate
- **WHEN** three issues qualify and one has no original estimate
- **THEN** the total sums the two estimated issues, and the summary reports that one qualifying issue was unestimated

#### Scenario: All qualifying issues are unestimated
- **WHEN** every qualifying issue lacks an original estimate
- **THEN** the total is zero hours and the summary states that all qualifying issues were unestimated

### Requirement: Estimate unit conversion
Jira returns `timeoriginalestimate` in seconds. The system SHALL keep seconds as the internal unit and convert to hours only for display, rounding to two decimal places. Summing SHALL occur in seconds so that repeated rounding cannot drift the total.

#### Scenario: Seconds converted for display
- **WHEN** an issue has `timeoriginalestimate` of 12600 seconds
- **THEN** it displays as `3.5h`

#### Scenario: Total is summed before rounding
- **WHEN** three issues each have an estimate of 1000 seconds
- **THEN** the reported total is derived from 3000 seconds, not from the sum of three individually rounded hour values
