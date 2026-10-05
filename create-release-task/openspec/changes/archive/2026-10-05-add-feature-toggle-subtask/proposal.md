## Why

Release prep now has to include checking that any feature toggles the release depends on have an SRE request filed. That step has to happen before branches are cut, so it belongs at the top of the release checklist. Right now it isn't in the generated checklist, so people have to remember to add it by hand on every release.

## What Changes

- Add the subtask `check feature toggle SRE request` as the **first** entry of the fixed release checklist, ahead of `create portal branch`. The checklist goes from nine subtasks to ten.
- New release tasks get ten subtasks, created in checklist order, so the new one gets the lowest subtask key and shows first in Jira.
- Existing release tasks pick up the new subtask when the tool is re-run for them, because missing checklist entries are already created on re-run. Since it is created last, it appears **at the bottom** of their subtask list, not the top. The tool does not reorder existing subtasks.
- Spec scenarios and tests that hardcode "nine subtasks", "ten issues" or `Created 10 issues` are updated to the new counts.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `release-task-creation`: the fixed checklist gains a first entry, and the subtask-count scenarios in "Create only missing subtasks", "Execute the plan in order" and "Re-running is idempotent" change accordingly.
- `cli-release`: the dry-run and result-output scenarios quote issue counts that change from 10 to 11.

## Impact

- **Code:** one-line addition to `SUBTASK_SUMMARIES` in `src/jira_release_task/checklist.py`. Planning, execution and reporting already iterate over the tuple, so no logic changes.
- **Tests:** count assertions in `test_checklist.py`, `test_plan.py`, `test_execute.py`, `test_report.py` and `test_cli.py`.
- **Docs:** the checklist list and sample output in `README.md`.
- **Existing Jira data:** none of it changes until someone re-runs the tool for an existing release. That run creates exactly one issue, the new subtask.
