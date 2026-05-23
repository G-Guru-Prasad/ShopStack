# Pre-commit structure reviewer — advisory only (warning, no block)

## Context

An earlier iteration of this plan tried to wire `.claude/agents/code-structure-reviewer.md` into a `type: agent` PreToolUse hook to **hard-fail** commits on structural violations. End-to-end testing showed the hook never blocked the commit. The official Claude Code docs (https://code.claude.com/docs/en/hooks) confirm why:

1. **`type: agent` hooks are experimental.** They are not included in the documented "decision control" table for `PreToolUse`. Any `permissionDecision: "deny"` JSON they emit is ignored by the framework.
2. **`type: agent` hooks cannot use Bash.** Per the docs, agent hooks may only invoke `Read`, `Grep`, `Glob`. They cannot run `git diff --cached`, so they never see the staged diff to review.

The user has accepted that pre-commit blocking is out of scope, and has asked for the reviewer to run **advisory-only** — surfacing warnings about which of the five pillars (naming & cohesion, lint, docstyle, import order, PEP8 spacing) the staged diff fails, and letting the commit proceed regardless.

Goal: when a developer runs `git commit`, a Claude Code hook runs the structure reviewer against the staged diff and prints a concise per-pillar warning in the Claude Code UI (via `systemMessage`). The commit is never blocked. Multi-tenancy safety and test-coverage remain out of scope for this hook.

The existing agent definition at `.claude/agents/code-structure-reviewer.md` and the test fixture at `shopstack/sandbox_untested.py` are reused. The current `type: agent` hook is replaced by a `type: command` hook (well-documented schema, can produce `systemMessage`, can shell out to read the diff and invoke Claude headlessly).

## Files to modify

### 1. New: `.claude/hooks/structure-review.sh`
Shell script invoked by the pre-commit command hook. Responsibilities:

- Read `git diff --cached`. If empty, emit `allow` JSON with `"systemMessage": "Structure review skipped — no staged changes."` and exit 0.
- Invoke Claude headlessly to review the diff against the five pillars in `.claude/agents/code-structure-reviewer.md`. Preferred invocation:
  ```
  claude -p --agent code-structure-reviewer < <(printf '%s' "$diff")
  ```
  If `--agent` is unavailable in the installed `claude` CLI, fall back to:
  ```
  claude -p "Review this staged diff against the five pillars in .claude/agents/code-structure-reviewer.md (naming & cohesion, lint/flake8, docstyle, import order, PEP8 spacing). Reply with a single concise paragraph naming the failing pillars and the specific line/file for each, or 'All pillars pass.' if clean. Plain text only, no JSON.\n\nDIFF:\n$diff"
  ```
- Capture the model's text response into `$review`.
- Emit hook JSON to stdout:
  ```json
  {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"},"systemMessage":"<review text>"}
  ```
  Use `jq -Rs .` (or `python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))"` fallback if `jq` is missing) to JSON-escape `$review` safely.
- Always exit 0. Never block.
- On any failure (Claude CLI missing, timeout, parse error) emit `allow` with a `systemMessage` saying `"Structure review failed: <reason>"` so the developer knows the gate was a no-op rather than silently passing.

### 2. `.claude/settings.json`
Replace the `type: agent` entry under `PreToolUse.Bash.hooks` with a `type: command` entry:

```json
{
  "type": "command",
  "if": "Bash(git commit*)",
  "command": "bash .claude/hooks/structure-review.sh",
  "timeout": 180,
  "statusMessage": "Running advisory structure review..."
}
```

Keep the existing sibling `type: command` logging hook (writes to `.claude/hook-log.txt`) untouched. Drop the previous `type: agent` block entirely, including its long inline prompt — do not leave both in place or we'll double-fire.

### 3. `.claude/agents/code-structure-reviewer.md`
Rewrite the **Output contract** section to produce plain-text instead of JSON. The script wraps the response into the hook JSON envelope. New contract:

> Output a single concise paragraph in plain text. Format: `Pillar status — <pillar>: <pass/fail + 1-line reason>; <pillar>: ...`. Close with a one-line summary verdict. No JSON, no markdown, no preamble.

Leave the five pillars and out-of-scope sections as-is.

### 4. Test fixture
`shopstack/sandbox_untested.py` — no change. Same file is used for the two verification scenarios below.

## Verification

Run from the repo root. **Restart the Claude Code session** before testing — settings.json reloads at session start.

**Sanity checks (no commit):**
- `python3 -c "import json; json.load(open('.claude/settings.json'))"` — valid JSON
- `bash -n .claude/hooks/structure-review.sh` — script parses
- `which claude` — confirm the headless CLI is on PATH
- `claude --help | grep -- --agent` — confirm `--agent` is supported (decide which invocation path the script takes)

**Scenario A — Clean diff: commit allowed, systemMessage says clean**
1. Add a small, well-named, docstringed, lint-clean function to `sandbox_untested.py`.
2. `git add shopstack/sandbox_untested.py`
3. `git commit -m "test: scenario A - clean diff"`
4. **Expect:** commit succeeds. Claude Code surfaces a `systemMessage` like *"Pillar status — naming: pass; lint: pass; docstyle: pass; imports: pass; PEP8: pass. All pillars pass."*
5. Roll back: `git reset --soft HEAD~1 && git restore --staged shopstack/sandbox_untested.py && git checkout shopstack/sandbox_untested.py`

**Scenario B — Bad diff: commit allowed, systemMessage warns about every failing pillar**
1. Add to `sandbox_untested.py`: `from os import *` + an undocumented 60-line `do_thing` function with an unused local `unused_local = 99` and deep nesting.
2. `git add shopstack/sandbox_untested.py`
3. `git commit -m "test: scenario B - bad diff"`
4. **Expect:** commit succeeds (no block — that's intentional). The `systemMessage` names at least these failures:
   - **imports** — wildcard `from os import *`
   - **docstyle** — `do_thing` missing docstring
   - **lint** — F841 unused local `unused_local`
   - **naming & cohesion** — `do_thing` is non-descriptive; deeply nested if-chain
5. Roll back: `git reset --soft HEAD~1 && git restore --staged shopstack/sandbox_untested.py && git checkout shopstack/sandbox_untested.py`

**Failure-mode check**
- Temporarily wrap `PATH` so `claude` is unreachable and re-run Scenario A. Confirm the commit still succeeds and the `systemMessage` reads *"Structure review failed: claude CLI not found"* — i.e. the hook degrades gracefully and never silently passes nor blocks.

## Notes for the executor

- The `type: command` hook is the documented mechanism for surfacing `systemMessage` text from a PreToolUse hook. We are *choosing* not to block (always emit `permissionDecision: allow`), but the same mechanism could block in the future if requirements change.
- `claude -p` (headless mode) starts a fresh session and inherits the project's agents directory, so `--agent code-structure-reviewer` should find `.claude/agents/code-structure-reviewer.md` automatically. Verify with the sanity check above before assuming.
- Keep the script under ~50 lines. If it grows, split logic into a helper Python script — bash JSON escaping gets fragile fast.
- The previous in-repo plan (this file's earlier version, committed in `abbd679`) described the failed blocking approach. This rewrite supersedes it; commit the change in the same commit as the hook/script changes so the documented intent matches the wired behaviour.
