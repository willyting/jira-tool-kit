from jira_release_task.checklist import (
    PARENT_SUMMARY,
    SUBTASK_SUMMARIES,
    build_parent_summary,
)


def test_exact_summary():
    assert (
        build_parent_summary(97, "2.14.0")
        == "[RELEASE] SP97 ----------------- 2.14.0 -----------------------------------"
    )


def test_dash_counts_are_pinned():
    dash_runs = [len(part) for part in PARENT_SUMMARY.split(" ") if set(part) == {"-"}]
    assert dash_runs == [17, 35]


def test_version_outer_whitespace_trimmed():
    assert " 2.14.0 " in build_parent_summary(97, "  2.14.0 ")


def test_version_kept_verbatim():
    assert " v2.14.0-rc1 " in build_parent_summary(97, "v2.14.0-rc1")


def test_checklist_contents_and_order():
    assert SUBTASK_SUMMARIES == (
        "check feature toggle SRE request",
        "create portal branch",
        "create backend branch",
        "check release note",
        "test vpp on stage",
        "run e2e test on stage",
        "check new feature on stage",
        "run api test on stage",
        "check sap on stage",
        "check on prod",
    )


def test_feature_toggle_check_comes_first():
    assert SUBTASK_SUMMARIES[0] == "check feature toggle SRE request"
