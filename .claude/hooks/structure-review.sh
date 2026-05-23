#!/usr/bin/env bash
# Advisory pre-commit structure review for ShopStack.
# Invokes the code-structure-reviewer agent on the staged diff and emits a
# PreToolUse hook JSON envelope with the review as a systemMessage. Always
# emits permissionDecision=allow — this hook never blocks the commit.

set -uo pipefail

emit() {
    # $1 = review text (plain). Wraps into hook JSON via python3 for safe
    # escaping, then prints to stdout for Claude Code to consume.
    python3 -c '
import json, sys
review = sys.argv[1]
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
    },
    "systemMessage": review,
}))
' "$1"
    exit 0
}

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || emit "Structure review skipped — not inside a git repo."
cd "$REPO_ROOT" || emit "Structure review skipped — could not cd to repo root."

# Prefer the staged diff. If empty, fall back to the working-tree diff vs HEAD
# — covers compound commands like `git add X && git commit ...` where the
# PreToolUse hook fires before `git add` has run, so nothing is staged yet.
DIFF="$(git diff --cached 2>/dev/null)" || emit "Structure review failed: git diff --cached errored."
if [ -z "$DIFF" ]; then
    DIFF="$(git diff HEAD 2>/dev/null)" || true
fi
[ -z "$DIFF" ] && emit "Structure review skipped — no staged or unstaged changes vs HEAD."

command -v claude >/dev/null 2>&1 || emit "Structure review failed: claude CLI not found on PATH."

REVIEW="$(printf '%s' "$DIFF" | claude -p --agent code-structure-reviewer 2>/dev/null)"
RC=$?
if [ $RC -ne 0 ] || [ -z "$REVIEW" ]; then
    emit "Structure review failed: claude -p exited $RC with no output."
fi

emit "$REVIEW"
