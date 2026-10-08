## MODIFIED Requirements

### Requirement: Parent summary format
The system SHALL build the parent summary as `[RELEASE] SP<N> ----------------- <V> -----------------------------------`: the literal `[RELEASE] SP`, the sprint number with no space before it, one space, exactly 17 hyphens, one space, the version with outer whitespace trimmed, one space, and exactly 35 hyphens.

#### Scenario: Summary for sprint 97, version 2.14.0
- **WHEN** the sprint number is `97` and the version is `2.14.0`
- **THEN** the summary is exactly `[RELEASE] SP97 ----------------- 2.14.0 -----------------------------------`

#### Scenario: Version with surrounding whitespace
- **WHEN** the version is given as `  2.14.0 `
- **THEN** the summary uses `2.14.0`

#### Scenario: Version kept verbatim
- **WHEN** the version is given as `v2.14.0-rc1`
- **THEN** the summary contains `v2.14.0-rc1` unchanged

### Requirement: Detect an existing release task
Before any write, the system SHALL search the resolved sprint for issues of the parent issue type and compare each `summary` exactly (case-sensitive, after trimming outer whitespace) against the built parent summary. JQL text search SHALL NOT be used to decide a match.

#### Scenario: No existing task
- **WHEN** no issue in the sprint has the exact summary
- **THEN** the plan says to create the parent

#### Scenario: One existing task
- **WHEN** exactly one issue in the sprint has the exact summary
- **THEN** the plan reuses that issue as the parent, and no new parent is created

#### Scenario: Near miss is not a match
- **WHEN** the sprint contains `[RELEASE] SP97 ------ 2.14.0 ---` (different dash counts)
- **THEN** it is not treated as a match, and the plan says to create the parent

#### Scenario: Old title format is not a match
- **WHEN** the sprint contains `release 97 ------- 2.14.0 -----------------------------------`
- **THEN** it is not treated as a match, and the plan says to create the parent

#### Scenario: Duplicate existing tasks
- **WHEN** two or more issues in the sprint have the exact summary
- **THEN** the system fails before any write, listing their keys
