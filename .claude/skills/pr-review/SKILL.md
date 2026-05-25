---
name: pr-review
description: Review an open GitHub pull request for code quality, structure, and performance, then post categorized inline + summary comments back to the PR (severity tags Critical / Warning / Suggestion). USE WHEN the user asks to review a PR, critique a pull request, post review comments on a PR, give PR feedback, audit a PR, or otherwise evaluate an already-opened GitHub PR — whether they say "/pr-review", name a PR number, or just say "review this PR". Accepts an optional PR number argument; defaults to the open PR for the current branch. SKIP when the user only wants a local diff review without posting to GitHub (use /code-review instead), or when no PR exists yet.
---

# PR Review Skill

Advisory PR reviewer for ShopStack. Diffs an open GitHub PR, evaluates each changed hunk along three axes (code quality, structure, performance), and posts findings back to the PR as line-anchored inline comments plus one summary comment. Severity is one of **Critical**, **Warning**, **Suggestion**. Never blocks merge — always submits the review with `event: "COMMENT"`.

## Invocation

- `/pr-review` — reviews the open PR for the current branch.
- `/pr-review <N>` — reviews PR number `N`.

Also fires automatically when the user asks for a PR review in natural language (per the `description` above).

## Step 1 — Resolve PR number

```bash
PR_NUM="${1:-}"
if [ -z "$PR_NUM" ]; then
  PR_NUM="$(gh pr view --json number -q .number 2>/dev/null || true)"
fi
if [ -z "$PR_NUM" ]; then
  echo "No PR number given and no open PR for the current branch. Aborting." >&2
  exit 1
fi
```

## Step 2 — Collect PR context

```bash
gh pr view "$PR_NUM" --json number,title,body,baseRefName,headRefName,headRefOid,author,files
gh pr diff "$PR_NUM"
```

Also resolve the repo (`gh repo view --json nameWithOwner -q .nameWithOwner`) for the `gh api` call in step 4.

## Step 3 — Analyze the diff

Walk the unified diff hunk-by-hunk. For each issue, produce one finding:

```
{ "severity": "Critical|Warning|Suggestion",
  "dimension": "Quality|Structure|Performance",
  "path": "<repo-relative path>",
  "line": <line number on the RIGHT side of the diff>,
  "body": "[<severity>] (<dimension>) <one-line problem> — <fix suggestion>" }
```

Cross-cutting notes (architecture, missing tests across files, broader concerns) go into a separate `summary_notes: []` list with no path/line.

### Review dimensions

1. **Code quality** — bugs, error handling gaps, dead code, unsafe assumptions, missing edge cases, security risks (injection, auth bypass, secret leakage), **and multi-tenant handling** (every tenant-scoped model access must flow through `TenantBasedManager` / `ThreadVaribales` per CLAUDE.md).
2. **Structure** — separation of concerns, cohesion, naming, public-API docstrings, import order, PEP8. Mirror the rules in `.claude/agents/code-structure-reviewer.md` so the two surfaces don't contradict.
3. **Performance** — N+1 queries (missing `.select_related` / `.prefetch_related`), unnecessary loops over querysets, missing indexes for new filters, large in-memory loads, blocking calls in the request path, **incorrect filters in DB queries** (wrong field, wrong relation, missing tenant scoping).

### Severity rubric

- **Critical** — correctness bug, security hole, data-loss risk, broken multi-tenant isolation, definite N+1 in a request path.
- **Warning** — likely defect, structural smell that will compound, missing tests for a non-trivial branch, performance concern needing measurement.
- **Suggestion** — readability, naming, minor refactor, nit-level style.

Assign exactly one severity and one dimension per finding. If nothing is wrong, post an empty-findings review (still posts the summary).

## Step 4 — Post the review

Build the JSON payload with a heredoc so multi-line bodies survive shell quoting, then POST it as a single review:

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"

cat > /tmp/pr-review-payload.json <<'JSON'
{
  "event": "COMMENT",
  "body": "<summary markdown>",
  "comments": [
    { "path": "...", "line": 42, "side": "RIGHT", "body": "[Critical] (Quality) ..." }
  ]
}
JSON

gh api --method POST \
  "repos/${REPO}/pulls/${PR_NUM}/reviews" \
  --input /tmp/pr-review-payload.json
```

### Summary body format (Markdown)

```
## PR Review — Critical: <c>, Warning: <w>, Suggestion: <s>

<one-paragraph overall verdict>

### Cross-cutting notes
- ...

---
_Commented by Claude-Code_
```

The trailing `_Commented by Claude-Code_` line is required — it marks the review as machine-generated.

## Step 5 — Recap to terminal

After the POST, echo a one-screen recap:

```
PR #<N>: posted review
  Critical:   <c>
  Warning:    <w>
  Suggestion: <s>
  URL: <html_url from the API response>
```

## Guardrails

- Always submit with `event: "COMMENT"`. Never `REQUEST_CHANGES`, never `APPROVE`.
- Do not run tests, lint, or coverage — CI handles those.
- Do not modify code or push commits.
- Only review one PR per invocation.
- If `gh` is not authenticated or the PR is not found, fail loudly and post nothing.
