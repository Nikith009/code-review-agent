from __future__ import annotations

from collections import Counter

from .findings import SEVERITIES, Finding

MARKER = "<!-- review-agent -->"


def render_summary(
    description: str,
    inline: list[Finding],
    general: list[Finding],
    reviewed: int,
    notes: list[str],
) -> str:
    counts = Counter(f.severity for f in inline + general)
    lines = [MARKER, "## Automated review", ""]
    if description:
        lines += [f"**What this PR does:** {description}", ""]

    if not inline and not general:
        lines.append(f"Reviewed {reviewed} file(s) and found nothing worth flagging.")
    else:
        tally = ", ".join(f"{counts[s]} {s}" for s in SEVERITIES if counts[s])
        lines.append(f"Reviewed {reviewed} file(s): {tally}. Details are in the inline comments.")

    if general:
        lines += ["", "**Outside the changed lines:**"]
        lines += [f"- `{f.path}:{f.line}` [{f.severity}] {f.title}: {f.body}" for f in general]

    if notes:
        lines += ["", "<details><summary>Skipped files</summary>", ""]
        lines += [f"- {n}" for n in notes]
        lines += ["", "</details>"]
    return "\n".join(lines)
