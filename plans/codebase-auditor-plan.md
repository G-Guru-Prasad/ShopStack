# ShopStack Codebase Auditor — Implementation Plan

## Context

ShopStack is being expanded and the team needs a guardrail that catches
non-optimized code and untested code before it lands. Today the only
post-coding gates are the 94% coverage floor in CI and an advisory
`code-structure-reviewer` agent. Neither catches tenant-safety
regressions, ORM/perf smells, ShopStack-pattern violations, missing
data-integrity asserts in tests, or missing tenant-isolation tests —
all of which directly threaten the multi-tenant correctness model the
codebase is built around.

The auditor delivered by this plan is a deterministic Python CLI
(`tools/audit.py`) wrapped by a Claude skill
(`.claude/skills/codebase-auditor/SKILL.md`). The CLI runs on a diff
or the whole repo, produces a terminal + markdown report, and exits
non-zero on ERROR findings so it can block in pre-commit and CI. The
skill teaches Claude when to invoke it during a feature build and how
to interpret findings. Migrations are excluded from all checks (CLI
and skill) since they are auto-generated and already omitted from the
coverage gate.

Scope is intentionally self-sufficient: it overlaps slightly with the
existing `code-structure-reviewer` agent (file shape) so that the
auditor remains useful standalone.

## Approach

Two artifacts, built in this order:

1. **`tools/audit.py`** — deterministic Python CLI (the engine)
2. **`.claude/skills/codebase-auditor/SKILL.md`** — Claude wrapper
   that knows when/how to run the CLI

CI and pre-commit wiring follow once both exist.

## CLI design (`tools/audit.py`)

### Layout

```
tools/
  audit.py                    # CLI entry: arg parsing, orchestration, exit code
  auditors/
    __init__.py
    base.py                   # Auditor ABC + Finding dataclass + Severity enum
    orm_smells.py             # N+1, unbounded .all() in loop, missing select_related/prefetch_related
    tenant_smells.py          # _default_manager bypass, raw SQL w/o tenant_id, request.user misuse
    python_perf.py            # work-in-loop, list-vs-generator, list-membership-in-loop
    drf_smells.py             # ListAPIView w/o select/prefetch, SerializerMethodField queries
    file_shape.py             # file size > 400 LOC, function > 50 LOC, nesting > 4, mixed concerns
    shopstack_patterns.py     # TenantBaseModel inheritance, ThreadVaribales over request.user, transaction.atomic on multi-write
    test_coverage.py          # coverage.py integration, data-integrity asserts, tenant-isolation tests
  reporters/
    __init__.py
    terminal.py               # grouped findings, color when TTY
    markdown.py               # full detail to reports/audit-<timestamp>.md
  suppressions.py             # inline / function / file scope; mandatory reason; stale detection
```

### CLI surface

```
python tools/audit.py --diff                       # staged + unstaged vs HEAD (default)
python tools/audit.py --all                        # whole shopstack/ tree
python tools/audit.py --since <ref>                # diff vs git ref (CI)
python tools/audit.py --format terminal|markdown|both   # default: both
python tools/audit.py --report-dir reports/        # default
python tools/audit.py --no-block                   # exit 0 even with ERRORs (local dry run)
python tools/audit.py --no-fail-fast               # always run coverage even if earlier auditors hit ERROR
```

Exit code: `0` if no ERROR findings, `1` otherwise. WARN never blocks.

### File exclusions (all modes)

Hardcoded skip list in `audit.py`:

- `*/migrations/*` (matches `.coveragerc`)
- `*/tests.py`, `*/test_*.py`, `*/tests_*.py`
- `manage.py`, `*/wsgi.py`, `*/asgi.py`, `*/settings.py`, `*/__init__.py`
- Non-`shopstack/` paths outside the project tree

Migration exclusion applies to `--diff`, `--all`, and `--since`.

### Findings: ERROR vs WARN

**ERROR (blocks)**

- `orm.n_plus_one` — `.all()`/`.filter()`/`.get()` inside a `for` loop body
- `orm.related_access_no_prefetch` — FK access in loop without `select_related`/`prefetch_related`
- `tenant.bypass_manager` — `Model._default_manager` / `Model._base_manager` on `TenantBaseModel` subclass outside management commands and migrations
- `tenant.raw_sql_no_tenant` — `connection.cursor()` or `Model.objects.raw(...)` without `tenant_id` token in SQL
- `tenant.uses_request_user` — view reads `request.user.id` for tenant/user context instead of `ThreadVaribales().get_val(...)`
- `drf.list_view_no_prefetch` — `ListAPIView` whose serializer touches FKs without `select_related`/`prefetch_related` on the queryset
- `shopstack.missing_tenant_base_model` — new `models.Model` subclass not inheriting `TenantBaseModel` (allowlist: `Tenant`, Django built-ins)
- `shopstack.missing_atomic` — function with ≥2 mutating ORM calls (`.save`/`.create`/`.delete`) not wrapped in `transaction.atomic`
- `test.uncovered_lines` — changed lines in non-test, non-migration source files not hit by `coverage run manage.py test --keepdb`
- `test.missing_integrity_assert` — test method with a mutating call (`self.client.post/patch/delete`, `.save`, `.create`, `.delete`) and zero DB reads after (`Model.objects.get/filter/count`, `refresh_from_db`)
- `audit.suppression_no_reason` — `# audit: ignore*` comment missing the mandatory `-- <reason>`

**WARN**

- `orm.unbounded_list` — `list(Model.objects.all())`
- `orm.count_then_query` — `.count()` followed by additional query on same queryset
- `perf.work_in_loop` — loop-invariant call (e.g. `re.compile`) inside loop body
- `perf.list_build_loop` — `.append` loop where comprehension/generator fits
- `perf.list_membership_in_loop` — `x in some_list` in loop where `some_list` is loop-invariant
- `drf.serializer_method_query` — `SerializerMethodField` whose body references `.objects`/`.filter`
- `shape.file_too_large` — `.py` file > 400 LOC
- `shape.function_too_long` — function/method > 50 LOC
- `shape.nesting_too_deep` — nesting > 4
- `shape.mixed_concerns` — `models.py` importing `rest_framework`, or `models.Model` subclass in `views.py`
- `audit.stale_suppression` — suppression present but no finding would have been raised

### Suppression mechanism

Three scopes, all require `-- <reason>`:

```python
# audit: ignore <code> -- <reason>                       # next-line / same-line suppression
# audit: ignore-function <code1,code2|all> -- <reason>   # on first line of def or decorator line
# audit: ignore-file <code1,code2|all> -- <reason>       # top of file, above imports
```

Missing reason → `audit.suppression_no_reason` ERROR.
Unused suppression → `audit.stale_suppression` WARN.

### Auditor contract

`auditors/base.py`:

```python
@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    severity: Severity      # ERROR or WARN
    code: str               # e.g. "tenant.bypass_manager"
    message: str
    auditor: str

class Auditor(ABC):
    name: str
    @abstractmethod
    def check(self, files: list[Path], ast_cache: dict[Path, ast.AST]) -> list[Finding]: ...
```

Each auditor is independent and stateless. CLI fans out, collects, applies suppressions, hands to reporters.

### Performance

- AST parsed once per file in `audit.py`, passed to every auditor via `ast_cache`
- Cheap auditors (orm/tenant/perf/drf/shape/shopstack) run first
- `test_coverage` runs last and is skipped under `--fail-fast` (default) if earlier auditors raised any ERROR
- Coverage uses `coverage run --rcfile=shopstack/.coveragerc manage.py test --keepdb`, then parses `.coverage` to map uncovered lines back to changed files

### Report format

Markdown (`reports/audit-<ISO-timestamp>.md`):

```
# Audit Report — 2026-05-25T10:42:11 — diff

## Summary
- 3 ERROR, 5 WARN across 7 files

## Errors (blocking)
### tenant.bypass_manager — stackapp/views.py:142
Direct use of Product._default_manager.all() bypasses TenantBasedManager.
Fix: use Product.objects.all().

## Warnings
...

## Suppressions applied
- stackapp/legacy.py:88 — perf.list_build_loop — "rewrite scheduled in PROJ-412"

## Stale suppressions
- stackapp/util.py:14 — orm.n_plus_one — no matching finding
```

Terminal output: same content, grouped by severity, color when stdout is a TTY.

## Skill design (`.claude/skills/codebase-auditor/SKILL.md`)

Follows the `superpowers:writing-skills` RED → GREEN → REFACTOR discipline.

- **Frontmatter** — `name: codebase-auditor`, third-person `description` starting with "Use when…", listing triggers (after writing a feature, before commit, on user request to audit)
- **Body sections** (kept under ~500 words):
  - Overview — what the auditor checks; tenant safety and test discipline emphasized
  - When to use — symptom list (new view added, new model added, before commit, before opening PR, after touching `models.py`/`views.py`/`serializers.py`/`tests.py`)
  - How to invoke — `python tools/audit.py --diff` for in-session, `--all` for periodic deep sweeps
  - How to interpret — ERROR vs WARN, parse the markdown report at `reports/audit-<timestamp>.md`, never silently ignore ERROR, propose fix or surface to user
  - Suppression policy — only when there is a real reason; reason must be in the comment
  - Common mistakes / red flags — running `--no-block` to bypass a real ERROR; suppressing instead of fixing; treating WARN as actionable when ERROR is unresolved

Per `writing-skills`: pressure scenarios run with subagents *before* writing the SKILL.md, baseline behavior captured, skill written to address observed rationalizations, then re-tested until compliant.

## Wiring

### Pre-commit

Add `.pre-commit-config.yaml` at repo root (does not exist today) with a local hook:

```yaml
repos:
  - repo: local
    hooks:
      - id: shopstack-audit
        name: ShopStack codebase auditor
        entry: python tools/audit.py --diff --format both
        language: system
        pass_filenames: false
        stages: [commit]
```

### CI

Extend `.github/workflows/ci.yml` with a new job `Code-Audit` that runs alongside (not inside) `Coverage-CI`:

- Same Python 3.12 setup, same Postgres service
- Runs `python tools/audit.py --since origin/main --format both`
- Uploads the markdown report as an artifact
- Required check on PRs to `main`
- Make sure the coverage run doesn't happen in both `Code-Audit` and `Coverage-CI` to avoid doubling test time

The existing 94% coverage floor stays as-is; this auditor adds independent gates.

## Critical files

- `tools/audit.py` *(new)* — CLI entry
- `tools/auditors/*.py` *(new)* — one file per auditor, contract in `base.py`
- `tools/reporters/{terminal,markdown}.py` *(new)*
- `tools/suppressions.py` *(new)*
- `tests/audit/test_<auditor>.py` *(new)* — one test module per auditor, plus an end-to-end CLI test that runs the auditor against fixture files and asserts exit code + findings (Django stock test runner via `manage.py test`)
- `.claude/skills/codebase-auditor/SKILL.md` *(new)*
- `.pre-commit-config.yaml` *(new)*
- `.github/workflows/ci.yml` *(modify: add `Code-Audit` job)*
- `shopstack/.coveragerc` — read-only reference for omit patterns; auditor mirrors thema

## Reused project conventions

- `TenantBaseModel`, `TenantBasedManager` (`shopstack/stackapp/utils.py`, `shopstack/stackapp/models.py`) — the auditor's tenant-pattern checks key off these class names
- `ThreadVaribales` (`shopstack/stackapp/utils.py`) — pattern checks look for this vs `request.user`
- `coverage.py` + `shopstack/.coveragerc` — auditor calls `coverage run ... manage.py test --keepdb` and parses the existing `.coverage` file; does not re-define exclusions
- `manage.py test --keepdb` — per `CLAUDE.md` "TESTS" section if tests are running in local

## Verification

End-to-end checks before merging:

1. **Unit tests per auditor:** `cd shopstack && python manage.py test tests.audit --keepdb` — each auditor module has at least one positive fixture (smell present → finding) and one negative fixture (clean code → no finding); suppression scopes have dedicated tests.
2. **Migration exclusion regression:** craft a fixture migration file with an obvious smell, run `python tools/audit.py --all`, assert it is not reported.
3. **Diff vs whole-repo parity:** run `python tools/audit.py --all` then `python tools/audit.py --diff` against the same set of staged changes; assert the diff results are a subset of `--all`.
4. **Coverage integration:** introduce a deliberately uncovered function in `stackapp`, run `python tools/audit.py --diff`, assert `test.uncovered_lines` fires and exit code is `1`.
5. **Tenant-isolation gap:** add a new view to `stackapp` that queries a `TenantBaseModel` subclass without a corresponding cross-tenant test; assert `test.missing_tenant_isolation` fires.
6. **Suppression mechanics:** apply each of `# audit: ignore`, `# audit: ignore-function`, `# audit: ignore-file` with and without `-- <reason>`; assert reason-less variants emit `audit.suppression_no_reason` ERROR.
7. **Exit code:** run with `--no-block` against the same broken fixture and assert exit `0`; run without it and assert exit `1`.
8. **Pre-commit:** `pre-commit run --all-files` after installing the hook; assert it blocks on a seeded smell and passes on a clean tree.
9. **CI dry run:** push a branch with a seeded ERROR; assert the new `audit` job fails the PR; fix the smell; assert it passes.
10. **Skill scenarios:** run the `writing-skills` pressure scenarios with a subagent — feature additions where the agent is tempted to skip auditing or rationalize an ERROR away — and confirm the SKILL.md causes compliance.
11. **Documentation:** confirm the SKILL.md is clear and actionable for a developer who has never used the auditor before, based on the scenarios above.
12. **Tests:** Once the feature is written make sure to write unit tests for each auditor and the CLI, with asserts to confirm data integrity.
