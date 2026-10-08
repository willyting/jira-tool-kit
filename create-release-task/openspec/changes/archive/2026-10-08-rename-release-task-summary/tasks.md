## 1. Tests first

- [x] 1.1 In `tests/test_checklist.py`, expect `build_parent_summary(97, "2.14.0")` to equal `[RELEASE] SP97 ----------------- 2.14.0 -----------------------------------`, and expect the dash runs to be `[17, 35]`
- [x] 1.2 In `tests/test_plan.py`, change the near-miss seed to `[RELEASE] SP97 ------ 2.14.0 ---`
- [x] 1.3 In `tests/test_plan.py`, add a test that a sprint holding the old title `release 97 ------- 2.14.0 -----------------------------------` still plans to create the parent
- [x] 1.4 Run the tests and confirm the summary and dash-count tests fail

## 2. Implementation

- [x] 2.1 In `src/jira_release_task/checklist.py`, set `PARENT_SUMMARY` to `"[RELEASE] SP{number} ----------------- {version} -----------------------------------"` and change the docstring's dash counts to 17 and 35
- [x] 2.2 Run the full test suite and confirm it passes

## 3. Docs

- [x] 3.1 In `README.md`, update step 2 and the sample `[create]` and `created` output lines to the new title
- [x] 3.2 In `README.md`, note that a sprint with an old-format release task gets a second parent on re-run, unless the old task is first renamed to the new title in Jira
