## MODIFIED Requirements

### Requirement: Dry run
With `--dry-run`, the CLI SHALL perform all reads (board, sprint, project, issue types, existing-task search), print the plan, and exit 0 without prompting and without making any write request.

#### Scenario: Dry run makes no writes
- **WHEN** `--dry-run` is given and the plan would create eleven issues
- **THEN** the plan is printed, zero `POST /rest/api/3/issue` or add-to-sprint requests are made, and the exit code is 0

### Requirement: Result output
After a run with writes, the CLI SHALL print the parent and each checklist subtask with its key, its summary, whether it was `created` or `existing`, and a browse URL of the form `<JIRA_BASE_URL>/browse/<KEY>`.

#### Scenario: Successful creation output
- **WHEN** a parent and ten subtasks are created
- **THEN** eleven lines are printed, all marked `created`, each with a browse URL, followed by a summary line `Created 11 issues in reseller 97.`
