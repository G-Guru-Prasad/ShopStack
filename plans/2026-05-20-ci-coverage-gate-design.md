---
name: ci-coverage-gate-design
description: Design spec for a CI-enforced overall test coverage floor on PRs targeting main
date: 2026-05-20
status: design-approved
---

# CI Coverage Gate — Design

## Problem

Today nothing mechanically verifies that code changes landing in `main` are exercised by tests. The existing `PreToolUse` hook on `git commit` invokes the code-change-reviewer agent to *discuss* test scenarios, but it is advisory and easy to bypass. For a project that aspires to regulated-grade rigor, we need a server-side, unbypassable gate.

## Goal

Block any pull request from merging into `main` if it causes overall test coverage to drop below a fixed baseline.

## Non-Goals (for this iteration)

- **Diff / patch coverage** — not measuring "did the changed lines get hit." Deferred to a follow-up; the workflow will emit `coverage xml` so diff-cover can be layered on without re-architecting.
- **Local pre-commit enforcement** — explicitly out of scope. Enforcement lives in CI only.
- **Mutation testing, branch coverage, per-file thresholds** — deferred.

## Architecture

A single GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every pull request targeting `main`. The job:

1. Spins up Python + PostgreSQL (matches the Postgres requirement in `settings.py`).
2. Installs dependencies plus the `coverage` package.
3. Runs the Django test suite under `coverage run`.
4. Enforces `coverage report --fail-under=<BASELINE>`.
5. Uploads `coverage.xml` as a build artifact (for future diff-coverage work).

Direct pushes to `main` are disabled via GitHub branch protection; all changes must arrive via PR, and the `ci` status check must be green before merge is allowed.

## Components

| Component | Purpose |
| --- | --- |
| `.github/workflows/ci.yml` | The CI job: setup → install → migrate → test under coverage → enforce floor → upload xml artifact. |
| `.coveragerc` (inside `shopstack/`, next to `manage.py`) | Coverage configuration: `source = .` plus omit patterns. Lives beside `manage.py` so `source` resolves correctly when coverage is invoked from that directory. |
| `requirements-dev.txt` (new) | Dev/CI-only dependencies — initially just `coverage`. Keeps production `requirements.txt` lean. |
| GitHub branch protection on `main` | Requires PRs (no direct pushes / force-pushes), requires the `ci` check to pass before merge. |
| This spec | Committed to `plans/` for traceability. |

## Coverage Configuration

`shopstack/.coveragerc` (sits beside `manage.py`):

```ini
[run]
source = .
branch = False
omit =
    */migrations/*
    */tests.py
    */settings.py
    */wsgi.py
    */asgi.py
    */__init__.py
    manage.py

[report]
show_missing = True
skip_covered = False
precision = 1
```

Rationale:

- `source = .` with `.coveragerc` placed inside `shopstack/` means coverage measures everything under the Django project root. Any new app scaffolded under `shopstack/` (e.g. `shopstack/payments/`) is automatically measured without touching config. This satisfies the requirement that future apps be checked.
- Migrations are auto-generated and would swing the number wildly; excluded.
- `tests.py` is excluded so test code itself is not counted as "covered production code."
- `settings.py`, `manage.py`, `wsgi.py`, `asgi.py` are framework/glue code with no meaningful behavior to test.

## Baseline Determination

The baseline is set **once**, before the workflow is merged:

1. On a clean checkout of `main`, run:

   ```bash
   cd shopstack
   coverage run manage.py test
   coverage report
   ```

   (`.coveragerc` is auto-discovered because it sits in the current directory.)

2. Read the **TOTAL** percentage from the report.
3. Round **down** to the nearest whole integer (e.g., `72.4%` → `72`).
4. Hardcode that integer into `.github/workflows/ci.yml` as `--fail-under=72`.

Rounding down provides a small safety margin against float-rounding drift between local and CI runs.

Raising the bar later is a deliberate PR that edits the integer in `ci.yml` — reviewed like any other change.

## Workflow Detail (`.github/workflows/ci.yml`)

```yaml
name: ci

on:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: shopstack_test_db
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.x'
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run tests with coverage
        working-directory: shopstack
        env:
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/shopstack_test_db
        run: coverage run manage.py test

      - name: Emit coverage XML (always)
        if: always()
        working-directory: shopstack
        run: coverage xml -o ../coverage.xml || true

      - name: Upload coverage artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-xml
          path: coverage.xml

      - name: Enforce coverage floor
        working-directory: shopstack
        run: coverage report --fail-under=<BASELINE>
```

Notes:

- `<BASELINE>` is the integer determined in the Baseline Determination step.
- CI does **not** use `--keepdb` — the container is ephemeral. Developers continue to use `--keepdb` locally per `CLAUDE.md`.
- `settings.py` currently hardcodes the dev DB; the CI step will require `settings.py` to read DB config from environment (via `DATABASE_URL` or individual `DB_*` env vars). This settings refactor is in scope for the implementation plan.
- `coverage xml` and the artifact upload both run with `if: always()`, and the floor check is the *last* step — so the xml artifact is uploaded even when the gate fails, useful for debugging "why did this drop?".

## Branch Protection (GitHub Settings)

Configured on the `main` branch:

- Require a pull request before merging.
- Require status check `ci / test` to pass before merging.
- Require branches to be up to date before merging.
- Disallow force pushes.
- Disallow deletions.
- Apply restrictions to administrators.

Configuration is documented in this spec; actual setting must be applied via the GitHub web UI (or `gh api`) since branch protection is not file-based.

## Failure Semantics

| Scenario | Outcome |
| --- | --- |
| Tests fail | Job fails → PR blocked. |
| Coverage drops below baseline | `coverage report --fail-under` exits non-zero → job fails → PR blocked. |
| New app added without tests | Source-by-directory picks it up; uncovered code drags total down → PR blocked. |
| Migrations / settings / wsgi changes only | Excluded from measurement; total unchanged → PR passes (assuming tests pass). |
| Test-only PR raising coverage | Total rises → PR passes. Baseline is not auto-raised in this iteration. |
| Direct push to `main` | Rejected by branch protection. |
| Force push to `main` | Rejected by branch protection. |

## Test Scenarios for the Gate Itself

Once implemented, validate the gate by opening these PRs against `main` (or a throwaway branch with the same protection):

1. **Happy path** — small code change with a matching test; CI passes.
2. **Coverage regression** — add a new view with no test; CI fails with a clear "coverage X% < baseline Y%" message.
3. **New app added** — scaffold an empty app under `shopstack/`; confirm it appears in the coverage report and (if untested) fails the gate.
4. **Migration-only PR** — output of `makemigrations`; coverage number unchanged; PR passes.
5. **Test-only PR** — add tests that exercise previously uncovered code; coverage rises; PR passes.
6. **Direct push to `main`** — confirmed rejected by branch protection.
7. **Force push to `main`** — confirmed rejected by branch protection.
8. **Admin bypass attempt** — confirm "apply to administrators" is on by attempting a merge of a failing PR as admin.

## Open Items for the Implementation Plan

- Refactor `settings.py` to read DB credentials from env vars (required for CI; harmless for local dev with sensible defaults).
- Decide Python version pin for CI (`3.11` vs `3.12`); should match what developers run.
- Confirm whether `requirements.txt` exists at repo root or under `shopstack/`; adjust install step accordingly.
- One-time baseline measurement and substitution of `<BASELINE>` in the workflow.

## Future Iterations (Not in Scope)

- Diff coverage gate via `diff-cover` consuming the uploaded `coverage.xml`.
- Coverage ratchet (baseline auto-raises but never lowers).
- Per-app or per-module thresholds.
- Branch coverage in addition to line coverage.
- Mutation testing (e.g., `mutmut`) on critical modules.
