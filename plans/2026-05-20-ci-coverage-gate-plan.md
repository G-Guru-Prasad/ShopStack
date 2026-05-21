# CI Coverage Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Block any PR from merging into `main` if it drops overall Django test coverage below a fixed baseline, enforced via GitHub Actions and branch protection.

**Architecture:** Add `coverage.py` config inside `shopstack/`, refactor `settings.py` to read DB credentials from env vars (CI needs this), add a GitHub Actions workflow that runs the Django test suite under coverage on every PR targeting `main`, and lock `main` behind branch protection. Diff coverage and ratcheting are deferred — this iteration is the overall-floor gate only.

**Tech Stack:** Python 3.12, Django 5.1, PostgreSQL 15, `coverage.py`, GitHub Actions.

**Reference Spec:** `plans/2026-05-20-ci-coverage-gate-design.md`

---

## File Structure

| File | Disposition | Responsibility |
| --- | --- | --- |
| `shopstack/.coveragerc` | Create | Coverage source + omit configuration. Sits next to `manage.py` so `source = .` resolves to the Django project root. |
| `requirements-dev.txt` | Create | Dev/CI-only deps. Initially just `coverage`. |
| `shopstack/shopstack/settings.py` | Modify (DATABASES block) | Read DB creds from env vars with sensible local defaults. |
| `.github/workflows/ci.yml` | Create | The CI job: Postgres service, install deps, run tests under coverage, upload XML, enforce floor. |
| `plans/2026-05-20-ci-baseline.txt` | Create (transient artifact) | Captures the one-time baseline measurement so the chosen integer is traceable. |
| GitHub branch protection rule on `main` | Configure (out-of-tree, via UI or `gh`) | Require PR + passing `ci / test` check; block direct pushes and force pushes. |

---

## Task 1: Add coverage configuration

**Files:**
- Create: `shopstack/.coveragerc`

- [ ] **Step 1: Create `.coveragerc` next to `manage.py`**

Write `shopstack/.coveragerc` with the following content:

```ini
[run]
source = .
branch = False
omit =
    */migrations/*
    */test_*.py
    */tests.py
    */tests_*.py
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

- [ ] **Step 2: Verify the file lives in the right place**

Run: `ls shopstack/.coveragerc && ls shopstack/manage.py`
Expected: both paths print without error (they sit in the same directory).

- [ ] **Step 3: Commit**

```bash
git add shopstack/.coveragerc
git commit -m "Add coverage.py configuration for Django project"
```

---

## Task 2: Add `requirements-dev.txt`

**Files:**
- Create: `requirements-dev.txt`

- [ ] **Step 1: Create dev requirements file**

Write `requirements-dev.txt`:

```
coverage==7.6.1
```

- [ ] **Step 2: Install locally and confirm import**

Run:
```bash
pip install -r requirements-dev.txt
python -c "import coverage; print(coverage.__version__)"
```
Expected: prints `7.6.1`.

- [ ] **Step 3: Commit**

```bash
git add requirements-dev.txt
git commit -m "Add requirements-dev.txt with coverage package"
```

---

## Task 3: Refactor `settings.py` to read DB from env vars

This is required because CI runs against a container Postgres with different credentials than local dev. Keep local defaults so existing `runserver` workflows are not disrupted.

**Files:**
- Modify: `shopstack/shopstack/settings.py` (DATABASES block, around lines 32-42)

- [ ] **Step 1: Write a failing test that asserts env vars are honoured**

Create `shopstack/stackapp/tests_settings.py`:

```python
"""Tests that DB settings honour environment variables."""
import importlib
import os
from unittest import mock

from django.test import SimpleTestCase


class DatabaseSettingsTests(SimpleTestCase):
    """Verify settings.DATABASES reads from env vars with defaults."""

    def _reload_settings(self):
        from shopstack import settings
        importlib.reload(settings)
        return settings

    def test_defaults_when_env_missing(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('DB_')}
        with mock.patch.dict(os.environ, env, clear=True):
            settings = self._reload_settings()
        db = settings.DATABASES['default']
        self.assertEqual(db['NAME'], 'shopstack_db')
        self.assertEqual(db['HOST'], 'localhost')
        self.assertEqual(db['PORT'], '5432')
        self.assertEqual(db['USER'], 'postgres')
        self.assertEqual(db['PASSWORD'], 'password')

    def test_env_vars_override_defaults(self):
        overrides = {
            'DB_NAME': 'ci_test_db',
            'DB_HOST': 'pg.ci.local',
            'DB_PORT': '6543',
            'DB_USER': 'ciuser',
            'DB_PASSWORD': 'cipass',
        }
        with mock.patch.dict(os.environ, overrides, clear=False):
            settings = self._reload_settings()
        db = settings.DATABASES['default']
        self.assertEqual(db['NAME'], 'ci_test_db')
        self.assertEqual(db['HOST'], 'pg.ci.local')
        self.assertEqual(db['PORT'], '6543')
        self.assertEqual(db['USER'], 'ciuser')
        self.assertEqual(db['PASSWORD'], 'cipass')
```

- [ ] **Step 2: Run the test and confirm it fails**

Run from `shopstack/`:
```bash
python manage.py test stackapp.tests_settings --keepdb
```
Expected: FAIL — current `settings.py` hardcodes the values; env-var overrides will be ignored.

- [ ] **Step 3: Update the DATABASES block in `shopstack/shopstack/settings.py`**

Add this near the top of the file (after `from pathlib import Path`):

```python
import os
```

Replace the existing `DATABASES = { ... }` block with:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'shopstack_db'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'password'),
    }
}
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run from `shopstack/`:
```bash
python manage.py test stackapp.tests_settings --keepdb
```
Expected: both tests PASS.

- [ ] **Step 5: Run the full suite to confirm no regression**

Run from `shopstack/`:
```bash
python manage.py test --keepdb
```
Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add shopstack/shopstack/settings.py shopstack/stackapp/tests_settings.py
git commit -m "Read DB credentials from env vars with local defaults"
```

---

## Task 4: Measure the baseline locally

This task does not modify code — it captures the integer that Task 5 needs.

**Files:**
- Create: `plans/2026-05-20-ci-baseline.txt`

- [ ] **Step 1: Clean any stale coverage data**

Run from `shopstack/`:
```bash
coverage erase
```
Expected: no output, exit 0.

- [ ] **Step 2: Run the suite under coverage**

Run from `shopstack/`:
```bash
coverage run manage.py test --keepdb
```
Expected: Django runs the full test suite; all tests pass; coverage data file `.coverage` is written.

- [ ] **Step 3: Read the TOTAL percentage**

Run from `shopstack/`:
```bash
coverage report
```
Expected: a table with one final `TOTAL` row showing a percentage (e.g., `TOTAL ... 72.4%`). Note the integer **floor** of that number (72.4 → 72).

- [ ] **Step 4: Record the baseline in a tracked file**

Write `plans/2026-05-20-ci-baseline.txt`:

```
Measured: 2026-05-20
Raw TOTAL: <copy the raw percentage here, e.g. 72.4%>
Baseline integer (floor): <integer, e.g. 72>
Command: coverage run manage.py test --keepdb && coverage report
```

This file exists so the chosen number is auditable when reviewers ask "why 72?".

- [ ] **Step 5: Commit**

```bash
git add plans/2026-05-20-ci-baseline.txt
git commit -m "Record initial coverage baseline measurement"
```

---

## Task 5: Add the GitHub Actions workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflow file**

Replace `<BASELINE>` below with the integer from `plans/2026-05-20-ci-baseline.txt`.

Write `.github/workflows/ci.yml`:

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
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    env:
      DB_NAME: shopstack_test_db
      DB_HOST: localhost
      DB_PORT: '5432'
      DB_USER: postgres
      DB_PASSWORD: postgres

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run tests under coverage
        working-directory: shopstack
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

- [ ] **Step 2: Validate the YAML locally**

Run from repo root:
```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```
Expected: no output, exit 0. Any parse error indicates malformed YAML — fix indentation before continuing.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "Add CI workflow enforcing coverage floor on PRs to main"
```

---

## Task 6: Validate the gate by opening a sandbox PR

This task proves the workflow runs and the floor enforces. Do NOT merge any of these PRs into `main`.

- [ ] **Step 1: Push a branch with the workflow change**

```bash
git push -u origin <current-branch>
```
Expected: branch pushed. No PR opened yet — branch protection is not configured, so CI won't run on push.

- [ ] **Step 2: Open a sandbox PR against `main`**

```bash
gh pr create --title "[sandbox] verify CI coverage gate" \
  --body "Sandbox PR to validate the new CI coverage gate. Do not merge."
```
Expected: PR is created; the `ci / test` check appears within ~30 seconds and runs to completion.

- [ ] **Step 3: Confirm CI passes on the unchanged baseline**

Wait for the CI run, then:
```bash
gh pr checks
```
Expected: `ci / test` status is `pass`.

- [ ] **Step 4: Confirm CI fails on a coverage regression**

On the same PR branch, add an untested file:

Create `shopstack/stackapp/sandbox_untested.py`:
```python
def sandbox_only_for_gate_test():
    """Intentionally untested function used only to validate the CI gate."""
    return 'this should drag coverage down'
```

Then:
```bash
git add shopstack/stackapp/sandbox_untested.py
git commit -m "[sandbox] add untested function to verify gate fails"
git push
```

Wait for CI to re-run, then:
```bash
gh pr checks
```
Expected: `ci / test` status is `fail` with a log line containing `Coverage failure: total of <pct> is less than fail-under=<BASELINE>`.

- [ ] **Step 5: Revert the sandbox change and confirm CI passes again**

```bash
git rm shopstack/stackapp/sandbox_untested.py
git commit -m "[sandbox] revert untested function"
git push
```

Wait for CI to re-run:
```bash
gh pr checks
```
Expected: `ci / test` status returns to `pass`.

- [ ] **Step 6: Close the sandbox PR**

```bash
gh pr close <PR-number> --delete-branch
```
Expected: PR closed, branch deleted. The workflow file change from Task 5 will be re-introduced via a proper PR in the next task.

---

## Task 7: Open the real PR to land the workflow

- [ ] **Step 1: Create a clean branch from `main`**

```bash
git checkout main
git pull
git checkout -b add-ci-coverage-gate
```

- [ ] **Step 2: Cherry-pick or re-apply the commits from Tasks 1–5**

If the previous branch was deleted, re-apply by running through Tasks 1–5 again on this branch. Otherwise:
```bash
git cherry-pick <task-1-sha> <task-2-sha> <task-3-sha> <task-4-sha> <task-5-sha>
```

- [ ] **Step 3: Push and open the PR**

```bash
git push -u origin add-ci-coverage-gate
gh pr create --title "Add CI coverage gate" \
  --body "$(cat <<'EOF'
## Summary
- Introduce a GitHub Actions workflow that runs the Django test suite under coverage on every PR targeting `main`.
- Enforce a fixed coverage floor matching today's measured baseline.
- Refactor `settings.py` to read DB credentials from env vars so CI can use its own Postgres container.

## Test plan
- [x] Validated locally that `coverage run manage.py test` succeeds and reports the recorded baseline.
- [x] Sandbox PR confirmed CI passes at baseline.
- [x] Sandbox PR confirmed CI fails when an untested file is added (coverage regression).
- [x] Sandbox PR confirmed CI returns to pass when the untested file is removed.

Spec: `plans/2026-05-20-ci-coverage-gate-design.md`
Baseline rationale: `plans/2026-05-20-ci-baseline.txt`
EOF
)"
```

- [ ] **Step 4: Wait for CI to pass on the real PR**

```bash
gh pr checks
```
Expected: `ci / test` is `pass`.

- [ ] **Step 5: Merge the PR**

After review, merge via the GitHub UI (or `gh pr merge --squash`). At this point the workflow exists on `main` but branch protection is not yet enforcing it — Task 8 fixes that.

---

## Task 8: Configure branch protection on `main`

This step is a one-time GitHub settings change. It cannot be expressed as a file in the repo for non-Enterprise accounts; use the GitHub UI or `gh` CLI.

- [ ] **Step 1: Apply branch protection via `gh`**

Run from repo root:
```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
gh api -X PUT "repos/${REPO}/branches/main/protection" \
  -H "Accept: application/vnd.github+json" \
  -f required_status_checks.strict=true \
  -f 'required_status_checks.contexts[]=ci / test' \
  -F enforce_admins=true \
  -f required_pull_request_reviews.required_approving_review_count=1 \
  -F required_pull_request_reviews.dismiss_stale_reviews=true \
  -F restrictions= \
  -F allow_force_pushes=false \
  -F allow_deletions=false
```
Expected: HTTP 200 response with the protection config printed.

If the call fails (private repo on a free plan that does not allow API-based branch protection), apply the equivalent settings in the GitHub web UI: **Settings → Branches → Add rule → `main`**:
- Require a pull request before merging (1 approval)
- Require status checks to pass before merging → require `ci / test`
- Require branches to be up to date before merging
- Do not allow bypassing the above settings (apply to administrators)
- Disallow force pushes
- Disallow deletions

- [ ] **Step 2: Verify protection is active**

```bash
gh api "repos/${REPO}/branches/main/protection" \
  -H "Accept: application/vnd.github+json" | jq '.required_status_checks.contexts, .enforce_admins.enabled'
```
Expected: output lists `"ci / test"` and `true`.

- [ ] **Step 3: Attempt a direct push to `main` (should be rejected)**

```bash
git checkout main
git commit --allow-empty -m "[verify] direct push must be rejected"
git push origin main
```
Expected: push is rejected by GitHub with a `protected branch` error. If accepted, branch protection is misconfigured — revisit Step 1.

- [ ] **Step 4: Undo the empty local commit**

```bash
git reset --hard origin/main
```
Expected: working tree clean and aligned with origin.

---

## Task 9: Document the gate in `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md` (append to the `### TESTS` section)

- [ ] **Step 1: Append CI gate notes to `CLAUDE.md`**

Append the following block to the existing `### TESTS` section in `CLAUDE.md`:

```markdown

### CI Coverage Gate

- Every PR to `main` runs `.github/workflows/ci.yml` which executes the Django test suite under `coverage.py` and enforces a fixed coverage floor.
- The floor is hardcoded as the `--fail-under` argument in the workflow file. To raise it, open a PR that edits the integer — reviewed like any other change.
- The current baseline rationale is recorded in `plans/2026-05-20-ci-baseline.txt`.
- Coverage configuration lives in `shopstack/.coveragerc`. Migrations, settings, wsgi/asgi/manage entry points, and `tests.py` files are excluded.
- New apps added under `shopstack/` are picked up automatically (the coverage source is the directory, not a file list).
```

- [ ] **Step 2: Commit and PR**

```bash
git checkout -b document-ci-gate
git add CLAUDE.md
git commit -m "Document CI coverage gate in CLAUDE.md"
git push -u origin document-ci-gate
gh pr create --title "Document CI coverage gate" \
  --body "Adds a short section to CLAUDE.md describing the new CI coverage gate, the location of the baseline rationale, and the process for raising the floor."
```
Expected: PR opens, the now-active CI gate runs and passes (this is a docs-only change so coverage is unaffected), and after approval the PR can be merged.

---

## Manual Validation Checklist (post-merge)

These are the test scenarios from the spec, applied after Tasks 1–9 are merged. They should be exercised once and never again unless the workflow changes.

- [ ] **Happy path** — PR with a small code change + matching test → CI `pass`.
- [ ] **Coverage regression** — PR adds a new view with no test → CI `fail`, log shows `coverage X% < BASELINE`.
- [ ] **New app added** — scaffold an empty app under `shopstack/`; PR fails the gate because the new app's untested code drags the total down.
- [ ] **Migration-only PR** — `makemigrations` output only → CI `pass` (migrations are omitted).
- [ ] **Test-only PR** — add tests that exercise previously uncovered code → CI `pass`; baseline is *not* auto-raised (deliberate, per spec).
- [ ] **Direct push to `main`** — rejected by branch protection.
- [ ] **Force push to `main`** — rejected by branch protection.
- [ ] **Admin bypass attempt** — admin tries to merge a failing PR → blocked (because `enforce_admins=true`).
