"""Minimal GitHub REST client (stdlib only) covering what the agent needs."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


@dataclass
class PullRequest:
    owner: str
    repo: str
    number: int
    title: str
    body: str
    head_sha: str
    base_ref: str
    author: str


class GitHubClient:
    def __init__(self, token: str | None = None, api_url: str = API):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise GitHubError("GITHUB_TOKEN is not set")
        self.api_url = api_url.rstrip("/")

    def _request(self, method: str, path: str, payload: dict | None = None):
        url = path if path.startswith("http") else f"{self.api_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                return json.loads(body) if body else None, resp.headers
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            raise GitHubError(f"{method} {path} -> {e.code}: {detail}") from e

    def get_pull(self, owner: str, repo: str, number: int) -> PullRequest:
        data, _ = self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}")
        return PullRequest(
            owner=owner,
            repo=repo,
            number=number,
            title=data["title"],
            body=data.get("body") or "",
            head_sha=data["head"]["sha"],
            base_ref=data["base"]["ref"],
            author=data["user"]["login"],
        )

    def list_files(self, owner: str, repo: str, number: int) -> list[dict]:
        files: list[dict] = []
        page = 1
        while True:
            data, _ = self._request(
                "GET", f"/repos/{owner}/{repo}/pulls/{number}/files?per_page=100&page={page}"
            )
            files.extend(data)
            if len(data) < 100 or page >= 30:  # API caps at 3000 files
                return files
            page += 1

    def get_file(self, owner: str, repo: str, path: str, ref: str) -> str | None:
        quoted = urllib.parse.quote(path)
        try:
            data, _ = self._request("GET", f"/repos/{owner}/{repo}/contents/{quoted}?ref={ref}")
        except GitHubError:
            return None
        if not isinstance(data, dict) or data.get("encoding") != "base64":
            return None
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")

    def create_review(
        self, pr: PullRequest, body: str, comments: list[dict], event: str = "COMMENT"
    ) -> dict:
        payload = {"commit_id": pr.head_sha, "body": body, "event": event, "comments": comments}
        data, _ = self._request(
            "POST", f"/repos/{pr.owner}/{pr.repo}/pulls/{pr.number}/reviews", payload
        )
        return data
