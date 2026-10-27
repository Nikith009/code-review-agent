"""Check the diff parser and GitHub client against real API responses.

Skipped unless GITHUB_TOKEN and GITHUB_REPOSITORY are set (they are in Actions).
Uses the compare API on the last commits of this repository, whose `files`
entries have exactly the same shape as a pull request's changed files.
"""

import os
import subprocess

import pytest

from review_agent.diff import from_github_file
from review_agent.github import GitHubClient


def _live():
    if not (os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPOSITORY")):
        pytest.skip("needs GITHUB_TOKEN and GITHUB_REPOSITORY")
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/")
    return GitHubClient(), owner, repo


def _head_and_base():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    base = subprocess.check_output(["git", "rev-list", "--max-parents=0", "HEAD"], text=True)
    return head, base.split()[0]


def test_parsed_patches_match_github_line_counts():
    gh, owner, repo = _live()
    head, base = _head_and_base()
    data, _ = gh._request("GET", f"/repos/{owner}/{repo}/compare/{base}...{head}")
    files = [f for f in data["files"] if f.get("patch")]
    assert files, "expected text changes between the first and latest commit"

    for entry in files:
        diff = from_github_file(entry)
        added = sum(1 for ln in diff.lines if ln.kind == "+")
        removed = sum(1 for ln in diff.lines if ln.kind == "-")
        assert added == entry["additions"], entry["filename"]
        assert removed == entry["deletions"], entry["filename"]
        assert diff.added_lines <= diff.commentable_lines


def test_get_file_reads_content_at_a_commit():
    gh, owner, repo = _live()
    head, _ = _head_and_base()
    text = gh.get_file(owner, repo, "pyproject.toml", head)
    assert text is not None and 'name = "code-review-agent"' in text
    assert gh.get_file(owner, repo, "does/not/exist.py", head) is None
