from __future__ import annotations

from dataclasses import asdict, dataclass

SEVERITIES = ["critical", "high", "medium", "low"]
CATEGORIES = ["security", "bug", "performance", "maintainability", "style"]


@dataclass
class Finding:
    path: str
    line: int
    severity: str
    category: str
    title: str
    body: str
    confidence: float
    suggestion: str | None = None

    @classmethod
    def from_dict(cls, path: str, raw: dict) -> Finding:
        severity = str(raw.get("severity", "low")).lower()
        category = str(raw.get("category", "maintainability")).lower()
        return cls(
            path=path,
            line=int(raw["line"]),
            severity=severity if severity in SEVERITIES else "low",
            category=category if category in CATEGORIES else "maintainability",
            title=str(raw.get("title", "")).strip(),
            body=str(raw.get("body", "")).strip(),
            confidence=min(max(float(raw.get("confidence", 0.5)), 0.0), 1.0),
            suggestion=(raw.get("suggestion") or None),
        )

    @property
    def rank(self) -> int:
        return SEVERITIES.index(self.severity)

    def to_comment(self) -> dict:
        """Payload for one inline comment in POST /pulls/{n}/reviews."""
        text = f"**[{self.severity}] {self.title}** ({self.category})\n\n{self.body}"
        if self.suggestion:
            text += f"\n\n```suggestion\n{self.suggestion}\n```"
        return {"path": self.path, "line": self.line, "side": "RIGHT", "body": text}

    def to_dict(self) -> dict:
        return asdict(self)
