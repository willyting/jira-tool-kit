## Context

The checklist is a fixed tuple, `SUBTASK_SUMMARIES`, in `checklist.py`. `plan.py` builds one plan item per entry, in tuple order. `execute.py` creates the missing items sequentially in that order, and `report.py` prints them in that order too. So the position of an entry in the tuple decides both creation order and display order. Subtasks are matched to the checklist by exact summary (trimmed, case-sensitive).

## Goals / Non-Goals

**Goals:**
- `check feature toggle SRE request` is the first subtask on every newly created release task.
- Re-running the tool against an existing release task adds the missing subtask, using the existing idempotent path, with no special handling.

**Non-Goals:**
- Reordering subtasks on release tasks that already exist.
- Making the checklist configurable. It stays a code constant.
- Any other change to summaries, matching or the CLI.

## Decisions

### D1. Insert at index 0 of `SUBTASK_SUMMARIES`
The summary is used exactly as requested, `check feature toggle SRE request`, including the capitalised `SRE`. Matching is case-sensitive, so a hand-made `check feature toggle sre request` would not count as present, and a re-run would create the canonical one. That is consistent with how every other checklist entry behaves.

### D2. No reordering of existing release tasks
On an existing parent, the new subtask is created after the other nine and appears last. Jira Cloud has no supported public REST endpoint for reordering subtasks under a parent in company-managed projects; the drag-and-drop order uses internal endpoints. Team-managed projects use rank, which would need the Agile rank API and a different code path per project style. Neither is worth it for a one-time transition that only affects releases already in flight.
- *Alternative:* rank the new subtask before `create portal branch` with `PUT /rest/agile/1.0/issue/rank`. Rejected: it doesn't work for company-managed subtask ordering and adds a write step that can fail on its own.

### D3. Tests keep deriving from the tuple where they can
Tests that compare against `SUBTASK_SUMMARIES` or slices of it need no change. Only literal counts change (10 → 11 total, 9 → 10 subtasks), plus the exact-contents test in `test_checklist.py`. The failure-and-resume tests in `test_execute.py` are written in terms of slices, so their meaning stays the same: fail at the 5th subtask, then resume with the remaining ones.

## Risks / Trade-offs

- [In-flight releases show the new subtask at the bottom] → Documented in the README. It is cosmetic and goes away as old releases close.
- [Someone added the step by hand with different wording] → Exact match means the tool creates the canonical one too, so there are two similar subtasks. The plan output shows `[create] check feature toggle SRE request` before anything is written, so it can be caught at the prompt.
