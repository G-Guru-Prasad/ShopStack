---
name: codebase-auditor
description: Use when adding or modifying any code under shopstack/ (new view, new model, new serializer, new endpoint, new test), before suggesting a commit, before opening a PR, or when the user asks to audit/verify the codebase. Catches tenant-safety violations, ORM/perf smells, ShopStack-pattern violations, missing data-integrity asserts, and missing tenant-isolation tests.
---

# Codebase Auditor

## Overview

`tools/audit.py` is a deterministic Python CLI that flags non-optimized code and untested code in ShopStack. It runs on the diff or the whole repo, emits a terminal + markdown report, and exits non-zero on ERROR findings so it blocks pre-commit and CI. This skill teaches Claude *when* and *how* to run it during a session and how to interpret findings.

## When to use

Run the auditor in any of these situations:

- After adding or editing a Django view, model, serializer, manager, or URL under `shopstack/`
- After writing or editing tests under `shopstack/`
- Before suggesting `git commit`
- When the user asks to "audit", "review the diff", or "check for issues"
- When debugging a tenant-leak or N+1 suspicion

Do **not** run for documentation-only changes, markdown edits, or pure formatting changes.

## How to invoke

```bash
python tools/audit.py --diff            # session default: staged + unstaged
python tools/audit.py --all             # whole shopstack/ tree (periodic sweep)
python tools/audit.py --since origin/main   # CI-style diff vs main
```

The CLI exits `0` on a clean run and `1` if any ERROR is present. WARN findings are reported but never block.

Useful flags:

- `--format terminal|markdown|both` (default `both`) — markdown lands in `reports/audit-<timestamp>.md`
- `--skip-coverage` — skip the test-coverage auditor (fast loop during scaffolding only)
- `--coverage-file <path>` — consume an existing `.coverage` artifact instead of re-running the tests
- `--no-block` — exit `0` even with ERRORs; **never use this to make a real ERROR go away**

## How to interpret findings

Findings are grouped by severity. ERRORs block; WARNs do not.

**Tenant-safety ERRORs** — `tenant.bypass_manager`, `tenant.raw_sql_no_tenant`, `tenant.uses_request_user`, `shopstack.missing_tenant_base_model` — treat as load-bearing. A tenant leak is a data breach. Fix before suggesting commit.

**Test-discipline ERRORs** — `test.uncovered_lines`, `test.missing_integrity_assert`, `test.missing_tenant_isolation` — the change is not safe to merge without the missing tests. Write them or surface the gap to the user.

**ORM / DRF ERRORs** — `orm.n_plus_one`, `orm.related_access_no_prefetch`, `drf.list_view_no_prefetch`, `shopstack.missing_atomic` — performance or correctness regressions. Fix before commit.

**WARNs** — `shape.*`, `perf.*`, `orm.unbounded_list`, `orm.count_then_query`, `drf.serializer_method_query`, `audit.stale_suppression` — surface in your summary; do not auto-fix unless the user asks.

After running, read the markdown report and summarize the findings for the user. For each ERROR, either fix it immediately and re-run, or surface it with a concrete proposed fix.

## Suppression policy

Sometimes a finding is a knowing exception. Use suppression with a mandatory reason:

```python
x = Model._default_manager.all()  # audit: ignore tenant.bypass_manager -- management command needs cross-tenant view

# audit: ignore-function orm.n_plus_one -- batch is bounded to <10 by caller
def small_batch_fetch(ids):
    ...

# audit: ignore-file shape.file_too_large -- legacy module slated for split in PROJ-412
```

Missing-reason suppressions trigger `audit.suppression_no_reason` (ERROR). Unused suppressions trigger `audit.stale_suppression` (WARN) — clean them up.

**Never use suppression as a shortcut.** If you would not stand behind the reason in code review, fix the underlying issue instead.

## Red flags -- STOP and reconsider

| Thought | Why it is wrong |
|---|---|
| "I'll add `--no-block` so the commit goes through." | That bypasses the gate; the ERROR will land in CI anyway. Fix the finding. |
| "I'll suppress this ERROR — it is a small change." | A reason like "small change" is not a reason. Fix it. |
| "The test-coverage auditor is slow, I'll just `--skip-coverage`." | Skipping coverage hides untested code. Run it. |
| "There are too many findings, I'll only fix the easy ones." | Fix every ERROR before suggesting commit. WARNs may be deferred with the user's agreement. |
| "I do not see how to write the cross-tenant test, so I will mark it stale." | Surface the gap to the user; ask for guidance. Do not silently skip. |

## Common mistakes

- Running `--skip-coverage` and then declaring the diff "clean". The diff is not clean until the coverage auditor has run.
- Suppressing `audit.suppression_no_reason` by adding "-- ignore" without a real reason. The reason text is checked by humans on review.
- Treating WARN as the same as ERROR. WARNs are advisory.
- Forgetting to delete a suppression when the underlying smell is fixed. The auditor will surface this as `audit.stale_suppression`.
