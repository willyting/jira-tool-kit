## Context

The parent title comes from one constant, `PARENT_SUMMARY` in `src/jira_release_task/checklist.py`, which `build_parent_summary()` formats. `plan.py` uses the same built string to find an existing release task by exact summary match, so creating and detecting always use the same format. A test pins the dash runs (`[7, 35]` today).

## Goals / Non-Goals

**Goals:**
- New release tasks are titled `[RELEASE] SP<N> ----------------- <V> -----------------------------------`.
- Re-runs stay idempotent for tasks created in the new format.

**Non-Goals:**
- Renaming release tasks already in Jira with the old title.
- Recognising the old title as an existing release task.
- Making the title configurable.

## Decisions

- **Change only the constant.** Creating and detecting both read `build_parent_summary()`, so editing `PARENT_SUMMARY` changes both together. The dash counts stay fixed in code and pinned by the test, now `[17, 35]`.
- **Exact match only; no fallback to the old title.** Matching the old title as well would mean reusing a parent whose title disagrees with the spec and adding branches to `plan.py` for a short transition. The tool runs once per sprint, so the transition window is about one sprint.
  - Alternative considered: also match the old title and rename it in place. Rejected: it needs an issue-update call the client does not have, for a case that fixes itself after one sprint.

## Risks / Trade-offs

- [A sprint already has an old-format release task, and someone re-runs the tool for it] → A second parent with the new title and a full set of subtasks gets created. Mitigation: the README notes this, and the `--dry-run` output shows `[create]` for the parent before anything is written. The user can rename the old task to the new title in Jira first; the tool then reuses it.
