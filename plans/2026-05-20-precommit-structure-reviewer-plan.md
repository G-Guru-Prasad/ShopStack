# Replace pre-commit reviewer with a structure-only reviewer

## Context

ShopStack currently has a pre-commit `PreToolUse` hook (in `.claude/settings.json`) that dispatches an inline agent referencing `.claude/agents/code-change-reviewer.md`. That reviewer enforces six pillars — multi-tenancy safety, structure, PEP8, docstyle, import order, flake8 — and mandates test-scenario discussion. The user wants to **replace** it with a narrower agent that only enforces code structure and lint hygiene (naming & cohesion, lint, docstyle, flake8, import order). The new hook must **hard-fail** the commit on any finding.

**Explicit user decision (recorded):** the multi-tenancy safety gate and test-coverage gate are being **removed from pre-commit**. Tenant-leakage detection will no longer block local commits. This is a deliberate scope narrowing the user confirmed in planning, despite the regulated-banking / P0 tenant-leakage context noted in org instructions. Anyone reviewing this plan should flag if that assumption changes — those checks will need to move to CI or a separate gate to remain enforced anywhere.

No project linter config exists (no `.flake8`, `pyproject.toml`, `setup.cfg`, etc.) — the agent enforces standards directly from its prompt, same as today.

## Files to modify

### 1. Rename and rewrite the agent
`.claude/agents/code-change-reviewer.md` → **rename to** `.claude/agents/code-structure-reviewer.md`

Rewrite the agent definition with:

- **Frontmatter**
  - `name: code-structure-reviewer`
  - `description: Reviews ShopStack code changes for structural quality — naming, cohesion, lint, docstyle, flake8, import order. Runs automatically before git commit and blocks on any violation. Does not gate on multi-tenancy or test coverage (those live elsewhere).`
  - `model: sonnet`
  - `color: blue`

- **System prompt body** organized as 5 pillars in priority order:
  1. **Naming & cohesion** — descriptive identifiers, single-responsibility per function/class/module, related code grouped together, no orphaned helpers
  2. **Lint (flake8 ruleset)** — F401 unused imports, F841 unused locals, F811 redefinition, F821 undefined name, C901 complexity, E/W spacing & indentation
  3. **Docstyle** — module/class/public-function docstrings present, imperative mood, first line summary, no stale references
  4. **Import order** — stdlib → third-party → first-party (`stackapp`, `shopstack`), absolute imports, alphabetical within groups, no wildcard imports
  5. **PEP8 spacing carryover** — preserve the one rule from `CLAUDE.md`: exactly one space around `=` (`x = 1`, not `x  = 1`)

- **Explicitly out of scope** (state this in the prompt so the agent doesn't drift): multi-tenancy safety, ORM tenant-filtering correctness, transactional integrity, test coverage. These are not pre-commit concerns under the new policy.

- **Output contract** — agent must emit only the JSON the hook expects (see below), nothing else.

### 2. Update the hook prompt
`.claude/settings.json` → in the `PreToolUse` → `Bash` → `if: Bash(git commit*)` agent entry, replace the inline `prompt` so it:

- References `.claude/agents/code-structure-reviewer.md` (new path)
- Drops the phrase *"multi-tenancy safety"* and *"discussing test scenarios"*
- Lists the five pillars above
- Keeps the same JSON response shape (`hookSpecificOutput.permissionDecision: deny` on findings, `allow` otherwise) so the hook keeps hard-failing the commit
- Keeps `timeout: 180` and the `statusMessage`

The sibling logging hook (writes to `.claude/hook-log.txt`) stays untouched.

### 3. Keep the test fixture
`shopstack/sandbox_untested.py` — leave in place; it's the dry-run target for verification below.

## Verification

Run from `/home/guru/gspace/ShopStack`. Both scenarios use the existing `sandbox_untested.py` so no real code is touched.

**Scenario A — Clean diff allows commit**
1. Edit `sandbox_untested.py`: add a small, well-named, docstringed, lint-clean function with proper import order.
2. `git add shopstack/sandbox_untested.py`
3. `git commit -m "test: clean structure should pass"`
4. **Expect:** hook emits `permissionDecision: allow`, commit succeeds, `.claude/hook-log.txt` gets a new line.
5. Roll back: `git reset --soft HEAD~1 && git restore --staged shopstack/sandbox_untested.py && git checkout shopstack/sandbox_untested.py`.

**Scenario B — Structural violation blocks commit**
1. Edit `sandbox_untested.py`: introduce one obvious structural violation — e.g. `from os import *` (wildcard import) plus a 60-line function named `do_thing` with no docstring and an unused local.
2. `git add shopstack/sandbox_untested.py`
3. `git commit -m "test: bad structure should fail"`
4. **Expect:** hook emits `permissionDecision: deny` with a `permissionDecisionReason` naming the wildcard import / missing docstring / unused local; commit is rejected; nothing appears in `git log`.
5. Roll back: `git restore --staged shopstack/sandbox_untested.py && git checkout shopstack/sandbox_untested.py`.

**Inspection check (no commit needed)**
- `cat .claude/agents/code-structure-reviewer.md` — confirm rewrite landed
- `ls .claude/agents/` — confirm `code-change-reviewer.md` is gone
- `python3 -c "import json; json.load(open('.claude/settings.json'))"` — confirm settings still parses
- `grep -n "code-structure-reviewer" .claude/settings.json` — confirm the prompt points at the new file

## Notes for the executor

- Renaming the agent file is just `git mv` + rewrite. The hook does not invoke the agent by `name` (it uses an inline `type: agent` prompt), so the rename only requires updating the path inside that prompt string.
- If you want to discover hook reload behavior: per Claude Code docs, settings reload at session start. After the change, restart the session before running Scenario A/B, otherwise the old hook config may still be cached.
- The org policy on discussing test scenarios is satisfied here by Scenarios A & B above — they are the contract this hook must meet.
