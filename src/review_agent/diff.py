"""Parse the unified-diff `patch` GitHub returns for each changed file.

GitHub only accepts inline review comments on lines that appear in the diff,
so we track which new-file line numbers are commentable, and render the
patch with those numbers so the model can reference lines precisely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class DiffLine:
    kind: str  # "+", "-" or " "
    text: str
    new_line: int | None  # None for removed lines
    old_line: int | None  # None for added lines


@dataclass
class FileDiff:
    path: str
    status: str = "modified"
    additions: int = 0
    deletions: int = 0
    patch: str | None = None
    lines: list[DiffLine] = field(default_factory=list)

    @property
    def added_lines(self) -> set[int]:
        return {ln.new_line for ln in self.lines if ln.kind == "+" and ln.new_line}

    @property
    def commentable_lines(self) -> set[int]:
        """Lines on the RIGHT side of the diff (added or context)."""
        return {ln.new_line for ln in self.lines if ln.new_line is not None}

    def render(self) -> str:
        """Diff with new-file line numbers in a gutter, e.g. `  42 + x = 1`."""
        out = []
        for ln in self.lines:
            if ln.kind == "@":
                out.append(ln.text)
                continue
            num = f"{ln.new_line:>5}" if ln.new_line is not None else "     "
            out.append(f"{num} {ln.kind} {ln.text}")
        return "\n".join(out)


def parse_patch(patch: str) -> list[DiffLine]:
    lines: list[DiffLine] = []
    old = new = 0
    for raw in patch.splitlines():
        header = HUNK_HEADER.match(raw)
        if header:
            old, new = int(header.group(1)), int(header.group(3))
            lines.append(DiffLine("@", raw, None, None))
            continue
        if raw.startswith("\\"):  # "\ No newline at end of file"
            continue
        kind, text = (raw[:1] or " "), raw[1:]
        if kind == "+":
            lines.append(DiffLine("+", text, new, None))
            new += 1
        elif kind == "-":
            lines.append(DiffLine("-", text, None, old))
            old += 1
        else:
            lines.append(DiffLine(" ", text, new, old))
            old += 1
            new += 1
    return lines


def from_github_file(entry: dict) -> FileDiff:
    """Build a FileDiff from one item of GET /repos/{o}/{r}/pulls/{n}/files."""
    patch = entry.get("patch")
    return FileDiff(
        path=entry["filename"],
        status=entry.get("status", "modified"),
        additions=entry.get("additions", 0),
        deletions=entry.get("deletions", 0),
        patch=patch,
        lines=parse_patch(patch) if patch else [],
    )
