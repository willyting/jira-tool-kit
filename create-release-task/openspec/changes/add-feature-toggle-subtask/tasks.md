## 1. Checklist

- [x] 1.1 Insert `"check feature toggle SRE request"` as the first entry of `SUBTASK_SUMMARIES` in `src/jira_release_task/checklist.py`
- [x] 1.2 Update `test_checklist_contents_and_order` in `tests/test_checklist.py` to the ten-entry tuple, and add a test that the first entry is exactly `check feature toggle SRE request`

## 2. Count-dependent tests

- [x] 2.1 `tests/test_plan.py`: fresh plan `to_create` 10 → 11, reused-parent and extra-subtask cases 9 → 10, partial case 7 → 8
- [x] 2.2 `tests/test_plan.py`: add a test where the existing parent has the nine original subtasks, asserting only `check feature toggle SRE request` is planned
- [x] 2.3 `tests/test_execute.py`: full-run `created_count` 10 → 11, reused-parent 9 → 10, resume-after-failure `created_count` 5 → 6; assert the first subtask create call is `check feature toggle SRE request`
- [x] 2.4 `tests/test_report.py`: result line count 10 → 11 and `Created 11 issues in reseller 97.`
- [x] 2.5 `tests/test_cli.py`: `Created 11 issues`, `11 issue(s) would be created`, and `create_calls` length 10 → 11

## 3. Docs and verification

- [x] 3.1 `README.md`: list ten subtasks with the new one first, update sample output to `Created 11 issues`, and note that existing release tasks get the new subtask at the bottom when re-run
- [x] 3.2 Run the full test suite and confirm it passes
- [x] 3.3 Run `openspec validate add-feature-toggle-subtask --strict`
