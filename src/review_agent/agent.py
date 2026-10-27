"""The review workflow as a LangGraph state graph.

    fetch -> plan --(files to review?)--> analyze -> critique -> summarize -> post
                   \\------------- no ---------------------------^

Each node reads the shared state and returns the keys it updates.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from .diff import FileDiff, from_github_file
from .findings import Finding
from .github import GitHubClient, PullRequest
from .policy import ReviewPolicy, filter_findings, plan_files
from .reviewer import Reviewer
from .summary import render_summary

log = logging.getLogger(__name__)


class ReviewState(TypedDict, total=False):
    owner: str
    repo: str
    number: int
    pr: PullRequest
    files: list[FileDiff]
    selected: list[FileDiff]
    notes: list[str]
    description: str
    findings: list[Finding]
    inline: list[Finding]
    general: list[Finding]
    body: str
    review: dict


def route_after_plan(state: ReviewState) -> str:
    return "analyze" if state.get("selected") else "summarize"


class ReviewAgent:
    def __init__(
        self,
        github: GitHubClient,
        reviewer: Reviewer,
        policy: ReviewPolicy | None = None,
        dry_run: bool = False,
        workers: int = 4,
    ):
        self.gh = github
        self.reviewer = reviewer
        self.policy = policy or ReviewPolicy()
        self.dry_run = dry_run
        self.workers = workers

    # --- nodes -----------------------------------------------------------

    def fetch(self, state: ReviewState) -> ReviewState:
        pr = self.gh.get_pull(state["owner"], state["repo"], state["number"])
        files = [from_github_file(e) for e in self.gh.list_files(pr.owner, pr.repo, pr.number)]
        log.info("PR #%s %r: %d changed files", pr.number, pr.title, len(files))
        return {"pr": pr, "files": files}

    def plan(self, state: ReviewState) -> ReviewState:
        selected, notes = plan_files(state["files"], self.policy)
        description = self.reviewer.describe(state["pr"], state["files"]) if selected else ""
        log.info("reviewing %d file(s), skipped %d", len(selected), len(notes))
        return {"selected": selected, "notes": notes, "description": description}

    def analyze(self, state: ReviewState) -> ReviewState:
        pr = state["pr"]
        cache: dict[str, str | None] = {}

        def read_file(path: str) -> str | None:
            if path not in cache:
                cache[path] = self.gh.get_file(pr.owner, pr.repo, path, pr.head_sha)
            return cache[path]

        def review(diff: FileDiff) -> tuple[list[Finding], str | None]:
            try:
                found = self.reviewer.review_file(pr, state["description"], diff, read_file)
                return found, None
            except Exception as e:  # one bad file should not sink the whole review
                log.warning("review of %s failed: %s", diff.path, e)
                return [], f"{diff.path}: review failed ({type(e).__name__})"

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            results = list(pool.map(review, state["selected"]))

        findings = [f for found, _ in results for f in found]
        errors = [err for _, err in results if err]
        return {"findings": findings, "notes": state["notes"] + errors}

    def critique(self, state: ReviewState) -> ReviewState:
        diffs = {d.path: d for d in state["selected"]}
        inline, general = filter_findings(state["findings"], diffs, self.policy)
        log.info(
            "%d raw findings -> %d inline, %d general",
            len(state["findings"]),
            len(inline),
            len(general),
        )
        return {"inline": inline, "general": general}

    def summarize(self, state: ReviewState) -> ReviewState:
        body = render_summary(
            state.get("description", ""),
            state.get("inline", []),
            state.get("general", []),
            reviewed=len(state.get("selected", [])),
            notes=state.get("notes", []),
        )
        return {"body": body}

    def post(self, state: ReviewState) -> ReviewState:
        comments = [f.to_comment() for f in state.get("inline", [])]
        payload = {"body": state["body"], "comments": comments}
        if self.dry_run:
            return {"review": {"dry_run": True, **payload}}
        review = self.gh.create_review(state["pr"], state["body"], comments)
        return {"review": {"id": review.get("id"), "url": review.get("html_url"), **payload}}

    # --- wiring ----------------------------------------------------------

    def build_graph(self):
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(ReviewState)
        for name in ("fetch", "plan", "analyze", "critique", "summarize", "post"):
            graph.add_node(name, getattr(self, name))

        graph.add_edge(START, "fetch")
        graph.add_edge("fetch", "plan")
        graph.add_conditional_edges(
            "plan", route_after_plan, {"analyze": "analyze", "summarize": "summarize"}
        )
        graph.add_edge("analyze", "critique")
        graph.add_edge("critique", "summarize")
        graph.add_edge("summarize", "post")
        graph.add_edge("post", END)
        return graph.compile()

    def run(self, owner: str, repo: str, number: int) -> ReviewState:
        state: ReviewState = {"owner": owner, "repo": repo, "number": number}
        try:
            app = self.build_graph()
        except ImportError:
            return self._run_sequential(state)
        return app.invoke(state)

    def _run_sequential(self, state: ReviewState) -> ReviewState:
        """Same flow as the graph, for environments without langgraph installed."""

        def step(name: str) -> None:
            state.update(getattr(self, name)(state))

        step("fetch")
        step("plan")
        if route_after_plan(state) == "analyze":
            step("analyze")
            step("critique")
        step("summarize")
        step("post")
        return state
