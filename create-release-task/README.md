# jira-release-task

Creates a reseller release checklist in Jira in one command. The tool:

1. finds the sprint `reseller <N>` on the `VOR board`;
2. creates the task `[RELEASE] SP<N> ----------------- <version> -----------------------------------` and puts it in that sprint;
3. creates ten subtasks under it, in this order:
   `check feature toggle SRE request`, `create portal branch`, `create backend branch`, `check release note`,
   `test vpp on stage`, `run e2e test on stage`, `check new feature on stage`,
   `run api test on stage`, `check sap on stage`, `check on prod`.

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
<https://id.atlassian.com/manage-profile/security/api-tokens>, then set:

```bash
export JIRA_BASE_URL=https://dibts3.atlassian.net
export JIRA_EMAIL=you@example.com
export JIRA_API_TOKEN=<your token>
```

Copy `.env.example` to `.env` if you prefer a file (`.env` is gitignored). Do
not hardcode the token in a script that could be committed.

Unlike `sprint-work-hours`, this tool **writes** to Jira. The account needs
these permissions on the VOR board's project:

- **Create Issues**, to create the task and subtasks;
- **Schedule Issues**, to move the task into the sprint.

## Usage

Always look at the plan first:

```bash
jira-release-task --sprint 97 --version 2.14.0 --dry-run
```

Then create the issues:

```bash
jira-release-task --sprint 97 --version 2.14.0         # asks before creating
jira-release-task --sprint 97 --version 2.14.0 --yes   # no prompt (scripts)
```

| Option | Default | Meaning |
|---|---|---|
| `--sprint N` | required | Sprint number; the sprint is `reseller N` |
| `--version V` | required | Release version, used verbatim (outer spaces trimmed) |
| `--board-name` | `VOR board` | Board to look the sprint up on |
| `--board ID` | | Board id, instead of `--board-name` |
| `--project KEY` | from board | Needed only if the board spans several projects |
| `--issue-type` | `Task` | Issue type for the parent |
| `--dry-run` | | Print the plan, write nothing |
| `--yes` | | Skip the confirmation prompt (required when not on a terminal) |
| `--verbose` | | Progress detail and full tracebacks |

The sprint must be **active or future**. Closed sprints are refused. Sprint
names are matched ignoring case and extra whitespace.

### Output

```
Board:   VOR board (id 12)
Sprint:  reseller 97 (id 501)
Project: VOR

[create] [RELEASE] SP97 ----------------- 2.14.0 -----------------------------------
    [create] check feature toggle SRE request
    [create] create portal branch
    ...
    [create] check on prod

VOR-101  created   [RELEASE] SP97 ----------------- 2.14.0 -----------------------------------  https://dibts3.atlassian.net/browse/VOR-101
    VOR-102  created   check feature toggle SRE request  https://dibts3.atlassian.net/browse/VOR-102
    VOR-103  created   create portal branch  https://dibts3.atlassian.net/browse/VOR-103
    ...

Created 11 issues in reseller 97.
```

## Re-running is safe

Before writing anything, the tool looks in the sprint for a task with exactly
the same title, comparing the dashes too.

- **Found:** the tool reuses that task and creates only the subtasks it is
  missing. Subtasks you added yourself are left alone.
- **Everything already there:** the tool says `Release task already complete`
  and writes nothing.

So if a run fails partway, run the same command again to finish it.

The same applies when the checklist gains a step. For example, release tasks
created before `check feature toggle SRE request` was added get just that one
subtask when you re-run the tool for them. It is created last, so on those
older tasks it appears at the bottom of the subtask list, not the top. The tool
never reorders existing subtasks.

Release tasks created before the title changed to `[RELEASE] SP<N> ...` are
titled `release <N> ------- <version> ---...`. The tool does not recognise that
old title, so a re-run for such a sprint creates a second task with the new
title. To avoid this, first rename the old task in Jira to the new title; the
tool then reuses it. `--dry-run` shows `[create]` for the task if it would be
created.

### If a run fails

The tool stops at the first failed write. It lists every issue it already
created, then prints the error. It never deletes anything.

One case needs manual action. If the task was created but could not be moved
into the sprint, the error names the task's key. Move that task into
`reseller <N>`, or delete it, before re-running. Otherwise the re-run won't
find it and will create a duplicate.

Creates are not retried after a timeout or a 5xx error, because Jira may have
created the issue anyway. If this happens, check the sprint before re-running.
If the task is there, the re-run will reuse it.

## Development

```bash
pytest
```

The tests cover every scenario in
`openspec/changes/create-release-task/specs/` and need no network access.
HTTP is tested against `respx` mocks. Everything above it runs against an
in-memory fake Jira (`tests/conftest.py`).
