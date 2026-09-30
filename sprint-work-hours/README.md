# jira-sprint-estimates

Totals the original estimates of all tasks and subtasks that **transitioned into
the Done status category during a given sprint's window**.

This is deliberately not the same question Jira's built-in sprint report
answers. Jira keys off an issue's *current* status; this tool reads each
issue's changelog. An issue that was finished last sprint and merely closed
this one does not count, and an issue that was finished this sprint and later
reopened does.

## Setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.13
uv pip install -e ".[dev]"
```

## Credentials

Create an API token at
<https://id.atlassian.com/manage-profile/security/api-tokens>, then set three
environment variables:

```bash
export JIRA_BASE_URL=https://dibts3.atlassian.net
export JIRA_EMAIL=you@example.com
export JIRA_API_TOKEN=<your token>
```

Copy `.env.example` if you prefer to keep them in a file — `.env` is
gitignored. The token is never written to disk by the tool and never appears in
its error output.

The token needs read access to the project and board you are reporting on.

## Usage

```bash
# By board id
jira-sprint-estimates --sprint "Sprint 42" --board 7

# By board name
jira-sprint-estimates --sprint "Sprint 42" --board-name "Delivery"

# With progress detail and full tracebacks on failure
jira-sprint-estimates --sprint "Sprint 42" --board 7 --verbose
```

Sprint names are matched case-insensitively and ignore extra whitespace. If the
name matches nothing, the error lists the board's recent sprints; if it matches
more than one, the error lists each candidate's id and start date.

### Output

```
Sprint: Sprint 42 (id 99)
Window: 2026-03-01 09:00 to 2026-03-15 17:30 UTC

Completed during sprint
┏━━━━━━━━┳━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┓
┃ Key    ┃ Type     ┃ Sub? ┃ Summary           ┃ Assignee     ┃ Completed (UTC)  ┃        Estimate ┃
┡━━━━━━━━╇━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━┩
│ PROJ-1 │ Story    │      │ Checkout redesign │ Ada Lovelace │ 2026-03-05 10:00 │ (8.0h rolled u… │
│ PROJ-2 │ Sub-task │ yes  │ Cart summary      │ Ada Lovelace │ 2026-03-05 10:00 │            3.0h │
│ PROJ-3 │ Sub-task │ yes  │ Payment step      │ Alan Turing  │ 2026-03-06 14:20 │            4.0h │
└────────┴──────────┴──────┴───────────────────┴──────────────┴──────────────────┴─────────────────┘

Total original estimate: 7.0h
Completed: 3 issues (1 tasks, 2 subtasks)
Excluded from the total: 1 parent estimate(s) superseded by completed subtasks (rolled up).
```

## How the total is calculated

**An issue counts when** its changelog shows a status change whose destination
is in the `done` status category, whose source is not, and whose timestamp
falls inside the sprint window. Classification is by status *category*, so
custom workflow statuses like `Released` are handled without configuration.

**The window** starts at the sprint's `startDate` and ends at its
`completeDate` (or `endDate` if there is no complete date). For an active
sprint the window ends at the current time, and the output says so — running
the tool twice on an in-progress sprint will give different answers.

**Subtasks** are found via their parents. Jira stores sprint membership on the
parent, so `sprint = X` alone would miss most subtasks. The tool queries the
sprint's members, then queries `parent in (...)` for their children.

**Estimates roll up leaf-first.** If a completed parent has completed subtasks,
only the subtasks' estimates count and the parent's own estimate is excluded.
Without this, a team that estimates both the parent and its children would see
the sprint total roughly doubled.

The excluded parent estimate is still shown in the table, marked `rolled up`,
so the total always reconciles against the visible rows. Note the consequence:
if your parent estimates are *not* pure roll-ups — say the parent is 8h but its
subtasks only cover 7h of that — the reported total will read low. The marked
rows are there so you can spot that.

**Issues with no original estimate** contribute 0h and are counted separately
in the summary rather than silently ignored.

**Issues whose changelog cannot be read** (usually permissions) are listed as
skipped, with a warning that the total may be understated. An unreadable
history is indistinguishable from "never completed", so it is never hidden.

## Development

```bash
pytest
```

The test suite covers every scenario in
`openspec/changes/sprint-done-estimate-report/specs/` and needs no network
access — the HTTP layer is exercised against a mock transport and everything
above it against a stub client.

## Notes on the Jira API

Atlassian removed `GET/POST /rest/api/3/search`; it now returns `410 Gone`.
This tool uses `POST /rest/api/3/search/jql`, which requires an explicit
`fields` list and paginates with opaque `nextPageToken` cursors. Board and
sprint metadata come from the Agile API (`/rest/agile/1.0`), which still uses
`startAt`/`maxResults`/`isLast`.
