from __future__ import annotations

from types import SimpleNamespace

from review_agent.findings import Finding
from review_agent.github import PullRequest

PATCH_AUTH = """@@ -10,6 +10,9 @@ def login(request):
     user = request.form["user"]
-    row = db.execute("SELECT * FROM users WHERE name = ?", (user,))
+    query = f"SELECT * FROM users WHERE name = '{user}'"
+    row = db.execute(query)
+    log.info("login %s %s", user, request.form["password"])
     if row is None:
         return deny()
     return allow(row)"""

PATCH_README = """@@ -1,2 +1,3 @@
 # Project
+More docs.
 End"""


class FakeGitHub:
    def __init__(self, files: list[dict] | None = None):
        self.files = (
            files
            if files is not None
            else [
                {
                    "filename": "app/auth.py",
                    "status": "modified",
                    "additions": 3,
                    "deletions": 1,
                    "patch": PATCH_AUTH,
                },
                {
                    "filename": "README.md",
                    "status": "modified",
                    "additions": 1,
                    "deletions": 0,
                    "patch": PATCH_README,
                },
                {
                    "filename": "package-lock.json",
                    "status": "modified",
                    "additions": 400,
                    "deletions": 380,
                    "patch": "@@ -1 +1 @@\n-a\n+b",
                },
                {"filename": "logo.png", "status": "added", "additions": 0, "deletions": 0},
            ]
        )
        self.posted: list[dict] = []
        self.reads: list[str] = []

    def get_pull(self, owner, repo, number):
        return PullRequest(
            owner, repo, number, "Speed up login", "Uses a raw query.", "abc123", "main", "dev"
        )

    def list_files(self, owner, repo, number):
        return self.files

    def get_file(self, owner, repo, path, ref):
        self.reads.append(path)
        return "line one\nline two" if path == "app/db.py" else None

    def create_review(self, pr, body, comments, event="COMMENT"):
        self.posted.append({"body": body, "comments": comments, "event": event})
        return {"id": 1, "html_url": "https://github.com/o/r/pull/7#review-1"}


class FakeReviewer:
    def __init__(self, findings_by_path: dict[str, list[dict]] | None = None):
        self.findings_by_path = findings_by_path or {
            "app/auth.py": [
                {
                    "line": 11,
                    "severity": "critical",
                    "category": "security",
                    "title": "SQL injection in login query",
                    "body": "User input is interpolated into SQL. Use a parameterized query.",
                    "confidence": 0.95,
                },
                {
                    "line": 13,
                    "severity": "high",
                    "category": "security",
                    "title": "Password written to logs",
                    "body": "Remove the password from the log.",
                    "confidence": 0.9,
                },
                {
                    "line": 14,
                    "severity": "low",
                    "category": "style",
                    "title": "Maybe rename",
                    "body": "Speculative.",
                    "confidence": 0.3,
                },
            ]
        }
        self.reviewed: list[str] = []

    def describe(self, pr, files):
        return "Replaces the parameterized login query with a formatted string."

    def review_file(self, pr, summary, diff, read_file):
        self.reviewed.append(diff.path)
        read_file("app/db.py")
        return [
            Finding.from_dict(diff.path, raw) for raw in self.findings_by_path.get(diff.path, [])
        ]


def block(**kw):
    return SimpleNamespace(**kw)


class ScriptedAnthropic:
    """Mimics client.messages.create, returning queued responses in order."""

    def __init__(self, responses: list[list[SimpleNamespace]]):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=self.responses.pop(0))
