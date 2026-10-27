# code-review-agent

[![ci](https://github.com/Nikith009/code-review-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Nikith009/code-review-agent/actions/workflows/ci.yml) [![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/Nikith009/code-review-agent)

A LangGraph agent that reviews GitHub pull requests the way a senior engineer would: it reads the diff, pulls in surrounding code when it needs context, reasons about what the change actually does, and posts inline comments on security problems, bugs and risky patterns. It is not a linter; there are no hard-coded rules about what counts as a problem.

It runs from the command line or as a GitHub Action on every pull request.

## Try it

- **Run the tests:** [CI workflow](https://github.com/Nikith009/code-review-agent/actions/workflows/ci.yml) → *Run workflow*. Includes tests against the live GitHub API.
- **Watch it review a PR:** add an `ANTHROPIC_API_KEY` repository secret, then [open the demo pull request](https://github.com/Nikith009/code-review-agent/compare/main...demo/unsafe-login?expand=1). The branch rewrites [`examples/demo_app/auth.py`](examples/demo_app/auth.py) with an SQL injection, a logged password and a weakened password check; the review workflow posts inline comments on it within a minute or two.
- **In the browser:** [open a Codespace](https://codespaces.new/Nikith009/code-review-agent), then `pytest -q` or `review-agent review --repo owner/name --pr N --dry-run`.

## How it works

```
fetch ─► plan ──(anything to review?)──► analyze ─► critique ─► summarize ─► post
              └──────────── no ─────────────────────────────────┘
```

| Node | What it does |
|---|---|
| `fetch` | Loads the PR and its changed files from the GitHub API and parses each patch, keeping track of new-file line numbers. |
| `plan` | Skips lockfiles, generated, vendored and binary files and oversized diffs; orders the rest by risk (size of change, with a boost for paths like `auth`, `payment`, `sql`, `webhook`); writes a two-sentence description of the PR that every file review gets as context. |
| `analyze` | Reviews files in parallel. Each review is a Claude tool-use loop: the model sees the annotated diff, may call `read_file` to load code at the PR's head commit, and finishes by calling `report_findings` with structured results (line, severity, category, confidence, optional suggested fix). |
| `critique` | Deterministic filter: drops findings below the confidence threshold, de-duplicates, checks that each line really is part of the diff (GitHub rejects comments elsewhere), caps comments per file and per PR, and sorts by severity. Confident findings outside the diff are moved to the summary instead of being lost. |
| `summarize` | Builds the review body: what the PR does, a tally by severity, out-of-diff findings and the list of skipped files. |
| `post` | Submits one review with all inline comments via `POST /pulls/{n}/reviews`, or prints it with `--dry-run`. |

Design choices worth calling out:

- **One review, not many comments.** Everything goes into a single review, so the PR author gets one notification.
- **Precise line numbers.** The diff is rendered with a gutter of new-file line numbers (`   42 + query = ...`) so the model references lines it can see, and the critique step still verifies every line.
- **Bounded agent loop.** At most `max_steps` model calls per file; on the last step `tool_choice` forces `report_findings`, so a review always terminates with structured output.
- **Prompt injection.** Diffs and file contents are untrusted input. The system prompt tells the model to treat them strictly as code under review, the model can only *read* files, and the only write the agent ever makes is the review itself. The Action runs with `contents: read` and `pull-requests: write`.
- **Failure isolation.** If one file's review errors out, the rest still post and the failure is listed in the summary.

## Usage

```bash
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=...
export GITHUB_TOKEN=...          # needs pull request write access to post

review-agent review --repo owner/name --pr 42 --dry-run -v   # print the review
review-agent review --repo owner/name --pr 42                # post it
```

Options: `--model` (default `claude-sonnet-5-5`, or `REVIEW_MODEL`), `--min-confidence` (default 0.6), `--max-comments` (default 15).

### As a GitHub Action

[`.github/workflows/review.yml`](.github/workflows/review.yml) reviews this repository's own PRs. To use it on another repository, copy that file there and add an `ANTHROPIC_API_KEY` repository secret. It runs on opened, updated and ready-for-review PRs, skips drafts, and cancels an in-progress review when new commits arrive.

## Example output

For a change that swaps a parameterized query for an f-string and logs the password:

> **[critical] SQL injection in login query** (security)
>
> `user` comes straight from the form and is interpolated into the SQL string, so a username like `' OR '1'='1` bypasses the lookup. Keep the parameterized form: `db.execute("SELECT * FROM users WHERE name = ?", (user,))`.

> **[high] Password written to logs** (security)
>
> The plaintext password is logged on every login attempt. Remove it from the log line.

## Development

```bash
pytest -q
ruff check . && ruff format --check .
```

The tests run fully offline: GitHub and the model are replaced with fakes, including a scripted Anthropic client that exercises the tool-use loop.

## Layout

```
src/review_agent/
  agent.py      LangGraph state graph and its nodes
  reviewer.py   Claude prompts and the tool-use loop
  policy.py     file selection and finding filters
  diff.py       unified diff parsing and line mapping
  github.py     small GitHub REST client (stdlib only)
  findings.py   Finding model and comment formatting
  summary.py    review body
  cli.py        `review-agent` command
```
