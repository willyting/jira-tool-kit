## Why

The team's release tasks follow the title format `[RELEASE] SP<N> ----------------- <version> -----------------------------------`. The tool still creates `release <N> ------- <version> -----------------------------------`, so its tasks look different from the rest of the board, and every one has to be renamed by hand.

## What Changes

- The parent summary changes from `release <N> ------- <V> -----------------------------------` to `[RELEASE] SP<N> ----------------- <V> -----------------------------------`: the literal `[RELEASE] SP`, the sprint number with no space before it, one space, exactly 17 hyphens, one space, the trimmed version, one space, and exactly 35 hyphens.
- The existing-task check matches the exact summary, so it now matches only the new format. **BREAKING**: if a sprint already has a release task with the old title, a re-run no longer reuses it and creates a second parent with the new title.
- The README examples and the pinned tests change to the new format.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `release-task-creation`: the "Parent summary format" requirement changes to the new title, and the near-miss scenario in "Detect an existing release task" uses the new prefix.

## Impact

- Code: `src/jira_release_task/checklist.py` (the `PARENT_SUMMARY` constant and its module docstring).
- Tests: `tests/test_checklist.py` (exact summary, dash counts `[17, 35]`), `tests/test_plan.py` (near-miss seed).
- Docs: `README.md` (step 2 and the sample output).
- Jira: no API or config changes. Release tasks already created with the old title are not renamed.
