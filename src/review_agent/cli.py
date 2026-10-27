"""Command line entry point.

review-agent review --repo owner/name --pr 42 [--dry-run]
review-agent from-event            # inside GitHub Actions
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from .agent import ReviewAgent
from .github import GitHubClient
from .policy import ReviewPolicy
from .reviewer import ClaudeReviewer


def _pr_from_event(path: str) -> tuple[str, str, int]:
    with open(path, encoding="utf-8") as f:
        event = json.load(f)
    pr = event.get("pull_request")
    if not pr:
        raise SystemExit("event has no pull_request; run this on pull_request events")
    owner, repo = event["repository"]["full_name"].split("/", 1)
    return owner, repo, int(pr["number"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="review-agent")
    sub = parser.add_subparsers(dest="command", required=True)

    review = sub.add_parser("review", help="review one pull request")
    review.add_argument("--repo", required=True, help="owner/name")
    review.add_argument("--pr", type=int, required=True)

    sub.add_parser("from-event", help="review the PR from $GITHUB_EVENT_PATH")

    for p in sub.choices.values():
        p.add_argument("--dry-run", action="store_true", help="print the review, don't post it")
        p.add_argument("--model", default=os.environ.get("REVIEW_MODEL", "claude-sonnet-5-5"))
        p.add_argument("--min-confidence", type=float, default=0.6)
        p.add_argument("--max-comments", type=int, default=15)
        p.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "from-event":
        owner, repo, number = _pr_from_event(os.environ["GITHUB_EVENT_PATH"])
    else:
        owner, repo = args.repo.split("/", 1)
        number = args.pr

    agent = ReviewAgent(
        github=GitHubClient(),
        reviewer=ClaudeReviewer(model=args.model),
        policy=ReviewPolicy(min_confidence=args.min_confidence, max_comments=args.max_comments),
        dry_run=args.dry_run,
    )
    state = agent.run(owner, repo, number)
    review = state["review"]

    if args.dry_run:
        print(review["body"])
        for c in review["comments"]:
            print(f"\n--- {c['path']}:{c['line']}\n{c['body']}")
    else:
        print(f"posted review with {len(review['comments'])} comment(s): {review.get('url')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
