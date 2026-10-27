from fakes import FakeGitHub, FakeReviewer

from review_agent.agent import ReviewAgent
from review_agent.summary import MARKER


def test_full_review_posts_filtered_inline_comments():
    gh, reviewer = FakeGitHub(), FakeReviewer()
    state = ReviewAgent(gh, reviewer)._run_sequential({"owner": "o", "repo": "r", "number": 7})

    assert reviewer.reviewed == ["app/auth.py", "README.md"]
    assert gh.reads == ["app/db.py"]  # read_file results are cached per run

    (posted,) = gh.posted
    assert [(c["path"], c["line"]) for c in posted["comments"]] == [
        ("app/auth.py", 11),
        ("app/auth.py", 13),
    ]
    assert "SQL injection" in posted["comments"][0]["body"]
    assert posted["body"].startswith(MARKER)
    assert "1 critical, 1 high" in posted["body"]
    assert "package-lock.json" in posted["body"]
    assert state["review"]["url"].endswith("review-1")


def test_dry_run_does_not_post():
    gh = FakeGitHub()
    state = ReviewAgent(gh, FakeReviewer(), dry_run=True)._run_sequential(
        {"owner": "o", "repo": "r", "number": 7}
    )
    assert gh.posted == []
    assert state["review"]["dry_run"] is True
    assert len(state["review"]["comments"]) == 2


def test_nothing_to_review_skips_the_model():
    gh = FakeGitHub(
        files=[{"filename": "yarn.lock", "patch": "@@ -1 +1 @@\n-a\n+b", "additions": 1}]
    )
    reviewer = FakeReviewer()
    ReviewAgent(gh, reviewer)._run_sequential({"owner": "o", "repo": "r", "number": 7})
    assert reviewer.reviewed == []
    assert "found nothing worth flagging" in gh.posted[0]["body"]


def test_failed_file_review_is_reported_not_raised():
    class Flaky(FakeReviewer):
        def review_file(self, pr, summary, diff, read_file):
            if diff.path == "README.md":
                raise TimeoutError("model timed out")
            return super().review_file(pr, summary, diff, read_file)

    gh = FakeGitHub()
    ReviewAgent(gh, Flaky())._run_sequential({"owner": "o", "repo": "r", "number": 7})
    assert "README.md: review failed (TimeoutError)" in gh.posted[0]["body"]
    assert len(gh.posted[0]["comments"]) == 2


def test_graph_matches_sequential_run():
    import pytest

    pytest.importorskip("langgraph")
    gh_a, gh_b = FakeGitHub(), FakeGitHub()
    ReviewAgent(gh_a, FakeReviewer()).run("o", "r", 7)
    ReviewAgent(gh_b, FakeReviewer())._run_sequential({"owner": "o", "repo": "r", "number": 7})
    assert gh_a.posted == gh_b.posted
