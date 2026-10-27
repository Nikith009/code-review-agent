from fakes import FakeGitHub

from review_agent.diff import from_github_file
from review_agent.findings import Finding
from review_agent.policy import ReviewPolicy, filter_findings, plan_files


def diffs():
    return [from_github_file(e) for e in FakeGitHub().files]


def test_plan_skips_lockfiles_and_binaries_and_puts_risky_files_first():
    selected, notes = plan_files(diffs(), ReviewPolicy())
    assert [d.path for d in selected] == ["app/auth.py", "README.md"]
    assert any("package-lock.json" in n for n in notes)
    assert any("logo.png" in n for n in notes)


def test_plan_respects_file_limit():
    selected, notes = plan_files(diffs(), ReviewPolicy(max_files=1))
    assert [d.path for d in selected] == ["app/auth.py"]
    assert any("README.md" in n and "limit" in n for n in notes)


def make(line, severity="high", title="t", confidence=0.9, path="app/auth.py"):
    return Finding(path, line, severity, "bug", title, "b", confidence)


def test_filter_drops_low_confidence_duplicates_and_sorts_by_severity():
    d = {x.path: x for x in diffs()}
    found = [
        make(12, "medium", "a"),
        make(11, "critical", "b"),
        make(11, "critical", "b"),
        make(13, "high", "c", confidence=0.2),
    ]
    inline, general = filter_findings(found, d, ReviewPolicy())
    assert [(f.line, f.severity) for f in inline] == [(11, "critical"), (12, "medium")]
    assert general == []


def test_finding_outside_diff_goes_to_general():
    d = {x.path: x for x in diffs()}
    inline, general = filter_findings([make(200)], d, ReviewPolicy())
    assert inline == [] and [f.line for f in general] == [200]


def test_per_file_cap():
    d = {x.path: x for x in diffs()}
    found = [make(line, title=f"t{line}") for line in range(10, 17)]
    inline, _ = filter_findings(found, d, ReviewPolicy(max_comments_per_file=3))
    assert len(inline) == 3


def test_finding_from_dict_normalizes_values():
    f = Finding.from_dict(
        "x.py",
        {
            "line": "5",
            "severity": "BLOCKER",
            "category": "Security",
            "title": " Leak ",
            "body": "b",
            "confidence": 3,
        },
    )
    assert (f.line, f.severity, f.category, f.title, f.confidence) == (
        5,
        "low",
        "security",
        "Leak",
        1.0,
    )
    comment = f.to_comment()
    assert comment["side"] == "RIGHT" and comment["line"] == 5
