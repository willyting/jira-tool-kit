from conftest import TARGET

from rich.console import Console

from jira_release_task.checklist import SUBTASK_SUMMARIES, build_parent_summary
from jira_release_task.execute import ResultItem, RunResult
from jira_release_task.plan import Plan, PlanItem
from jira_release_task.report import render_created, render_plan, render_result

BASE = "https://jira.example.test"
SUMMARY = build_parent_summary(97, "2.14.0")


def capture(fn, *args) -> str:
    console = Console(record=True, width=200)
    fn(console, *args)
    return console.export_text()


def test_plan_shows_target_and_marks_each_item():
    plan = Plan(
        target=TARGET,
        parent=PlanItem(SUMMARY, existing_key="VOR-1"),
        subtasks=tuple(
            PlanItem(s, "VOR-2" if s == "check on prod" else None) for s in SUBTASK_SUMMARIES
        ),
    )
    out = capture(render_plan, plan)

    assert "Sprint:  reseller 97 (id 501)" in out
    assert "Project: VOR" in out
    # Square brackets must survive: no Rich markup interpretation.
    assert f"[existing VOR-1] {SUMMARY}" in out
    assert "[create] create portal branch" in out
    assert "[existing VOR-2] check on prod" in out


def test_result_lists_keys_status_and_urls():
    result = RunResult(
        parent=ResultItem("VOR-1", SUMMARY, True),
        subtasks=tuple(ResultItem(f"VOR-{i + 2}", s, True) for i, s in enumerate(SUBTASK_SUMMARIES)),
    )
    out = capture(render_result, result, BASE, "reseller 97")

    lines = [l for l in out.splitlines() if "/browse/" in l]
    assert len(lines) == 10
    assert all("created" in l for l in lines)
    assert f"{BASE}/browse/VOR-1" in lines[0]
    assert "Created 10 issues in reseller 97." in out


def test_partial_failure_lists_created():
    out = capture(render_created, [ResultItem("VOR-1", SUMMARY, True)], BASE)
    assert "Created before the failure" in out
    assert f"{BASE}/browse/VOR-1" in out


def test_partial_failure_with_nothing_created():
    assert "No issues were created." in capture(render_created, [], BASE)
