"""Deterministic rules around the model: which files to review, which findings to keep."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

from .diff import FileDiff
from .findings import Finding

SKIP_PATTERNS = [
    "*.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "go.sum",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.svg",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.pdf",
    "*.woff*",
    "*_pb2.py",
    "*.pb.go",
    "*.generated.*",
    "dist/*",
    "build/*",
    "vendor/*",
    "node_modules/*",
    "*/migrations/*.sql",
]
RISKY_HINTS = [
    "auth",
    "login",
    "session",
    "token",
    "secret",
    "crypto",
    "payment",
    "billing",
    "sql",
    "query",
    "upload",
    "admin",
    "permission",
    "webhook",
]


@dataclass
class ReviewPolicy:
    max_files: int = 20
    max_patch_lines: int = 1200
    min_confidence: float = 0.6
    max_comments_per_file: int = 5
    max_comments: int = 15
    skip_patterns: list[str] = field(default_factory=lambda: list(SKIP_PATTERNS))


def _skipped(path: str, patterns: list[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(name, p) for p in patterns)


def risk_score(diff: FileDiff) -> float:
    path = diff.path.lower()
    boost = 2.0 if any(h in path for h in RISKY_HINTS) else 1.0
    if "test" in path:
        boost *= 0.5
    return boost * (diff.additions + 0.25 * diff.deletions)


def plan_files(files: list[FileDiff], policy: ReviewPolicy) -> tuple[list[FileDiff], list[str]]:
    """Pick the files worth reviewing, riskiest first. Returns (selected, skip notes)."""
    candidates, notes = [], []
    for f in files:
        if f.status == "removed":
            continue
        if f.patch is None:
            notes.append(f"{f.path}: no text diff (binary or too large)")
        elif _skipped(f.path, policy.skip_patterns):
            notes.append(f"{f.path}: generated or vendored, skipped")
        elif len(f.lines) > policy.max_patch_lines:
            notes.append(f"{f.path}: diff too large ({len(f.lines)} lines), skipped")
        elif not f.added_lines:
            continue  # deletions only
        else:
            candidates.append(f)

    candidates.sort(key=risk_score, reverse=True)
    for f in candidates[policy.max_files :]:
        notes.append(f"{f.path}: over the {policy.max_files}-file limit, skipped")
    return candidates[: policy.max_files], notes


def filter_findings(
    findings: list[Finding], diffs: dict[str, FileDiff], policy: ReviewPolicy
) -> tuple[list[Finding], list[Finding]]:
    """Drop weak or duplicate findings.

    Returns (inline, general): inline findings sit on a commentable line;
    confident findings whose line is outside the diff go into the summary.
    """
    seen: set[tuple] = set()
    inline: list[Finding] = []
    general: list[Finding] = []
    per_file: dict[str, int] = {}

    ordered = sorted(findings, key=lambda f: (f.rank, -f.confidence))
    for f in ordered:
        if f.confidence < policy.min_confidence or not f.title:
            continue
        key = (f.path, f.line, f.title.lower())
        if key in seen:
            continue
        seen.add(key)

        diff = diffs.get(f.path)
        if diff is None or f.line not in diff.commentable_lines:
            general.append(f)
            continue
        if per_file.get(f.path, 0) >= policy.max_comments_per_file:
            continue
        if len(inline) >= policy.max_comments:
            continue
        per_file[f.path] = per_file.get(f.path, 0) + 1
        inline.append(f)
    return inline, general[:5]
