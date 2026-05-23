# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Plan Mode

Whenever a plan is derived, the detailed plan should be written/updated to respective files under plans folder inside the repository. For example, the plan for the pre-commit hook update described above should be written to `plans/precommit-structure-reviewer-plan.md`.


## Git Commits

Whenever a git commit command is issued, the commit message should have only the summary line (no description or bullet points or co-authored by).  No special characters should be used in the commit message. The commit message should be concise and descriptive of the change being made. For example:

```git commit -m "Fix bug in order placement logic that caused incorrect total_amount calculation"
```


## Development Commands

All commands run from the `shopstack/` directory (where `manage.py` lives):

```bash
cd shopstack

# Run development server
python3 manage.py runserver

# Run all tests
python3 manage.py test

# Run tests for a specific app
python3 manage.py test stackapp

# Run a single test case
python3 manage.py test stackapp.tests.MyTestCase.test_method

# Create and apply migrations
python3 manage.py makemigrations
python3 manage.py migrate
```

All code changes must follow PEP8. Space between variable and operator must always be one (e.g. `x = 1`, not `x  = 1`).

## Architecture

ShopStack is a multi-tenant SaaS e-commerce platform built with Django + Django REST Framework. All API endpoints are under `/api/` and return JSON.

### Multi-Tenant Pattern

Tenant isolation is the core architectural concept. Three components work together:

**`ThreadVaribales` (`stackapp/utils.py`)** — stores per-request context (`tenant_id`, `user_id`) in thread-local storage via `set_val`/`get_val`.

**`TenantMiddleware` (`stackapp/middleware.py`)** — runs on every request. Parses the subdomain from `HTTP_HOST` (e.g. `acme.localhost:8000` → `tenant_id='acme'`), looks up the `Tenant` row, and sets `tenant_id` in thread-local. Clears thread-local after the response — critical for thread-pool servers.

**`TenantBasedManager` (`stackapp/utils.py`)** — custom Django ORM manager assigned to all tenant-scoped models via `TenantBaseModel`. It automatically:
- Filters all `get_queryset()` calls to the current tenant and excludes soft-deleted records (`deleted_at__isnull=True`)
- Injects `tenant_id` and `created_by_id` on `create()`
- Injects `tenant_id`, `created_by_id`, and `modified_by_id` on `bulk_create()`

### Model Hierarchy

**`Tenant`** — root entity, uses Django's default manager (not `TenantBasedManager`). PK is a `CharField` slug matching the subdomain.

**`TenantBaseModel`** — abstract base class for all tenant-scoped models. Provides `tenant FK`, `created_at`, `updated_at`, `deleted_at`, `created_by FK`, `modified_by FK`, and `objects = TenantBasedManager()`. All domain models inherit from this.

Domain models and their key relationships:
- `Category` — self-referencing FK (`parent`) for nested categories
- `Product` → `Category`; `ProductVariant` → `Product` (effective price = `product.price + price_modifier`; SKU unique per tenant)
- `Cart` → `auth.User`; `CartItem` → `Cart` + `ProductVariant` (unique together)
- `Address` → `auth.User`
- `Order` → `Cart` + `Address` (both `PROTECT`); stores denormalized `total_amount`
- `OrderItem` → `Order` + `ProductVariant` (`PROTECT`); snapshots `unit_price` at order placement time

### API & Views

Views use DRF generic views (`ListAPIView`, `RetrieveAPIView`, `CreateAPIView`, etc.) for simple CRUD. Complex business logic (order placement) uses `APIView` directly.

Order placement (`POST /api/orders/`) is the most complex view: validates input, fetches active cart, snapshots prices, and creates `Order` + `OrderItems` + deactivates cart inside a single `transaction.atomic()`.

Views read `user_id` and `tenant_id` directly from `ThreadVaribales()` — they do not use `request.user` for tenant/user resolution. Views must call `ThreadVaribales().set_val('user_id', ...)` manually after authentication since `TenantMiddleware` runs before `AuthenticationMiddleware`.

### URL Structure

```
/admin/                    Django admin
/api/products/             Product list (GET); filter: ?category=<id>
/api/products/<id>/        Product detail with variants (GET)
/api/categories/           Category list (GET)
/api/cart/                 Get or create active cart (GET/POST)
/api/cart/items/           Add cart item (POST)
/api/cart/items/<id>/      Update quantity or remove item (PATCH/DELETE)
/api/orders/               List orders / place order from cart (GET/POST)
/api/orders/<id>/          Order detail with items and address (GET)
```

### Settings

- Database: PostgreSQL, `shopstack_db`, localhost:5432
- Tenant identification: subdomain — `ALLOWED_HOSTS` includes `.localhost` wildcard for local dev
- `DEBUG=True` and hardcoded `SECRET_KEY` — development only
- DRF configured with `AllowAny` permissions and `PageNumberPagination` (20 per page)


### TESTS

- Make sure all the test cases running uses a different test database
- All test cases should have asserts to make sure data integrity
- All test case running command should use keepdb always unless, there's model field change

### CI Coverage Gate

- Every PR to `main` runs `.github/workflows/ci.yml`, which executes the Django test suite under `coverage.py` and enforces a fixed coverage floor (currently `--fail-under=94`).
- The floor is hardcoded in the workflow file. To raise it, open a PR that edits the integer — reviewed like any other change.
- The current baseline rationale (raw percentage, command, per-file numbers at measurement time) is recorded in `plans/2026-05-20-ci-baseline.txt`.
- Coverage configuration lives in `shopstack/.coveragerc`. Migrations, settings, wsgi/asgi/manage entry points, and `test*.py` files are excluded so they neither help nor hurt the percentage.
- New apps added under `shopstack/` are picked up automatically — `source = .` in the rcfile is a directory, not a file list.
- Direct pushes / force pushes to `main` are blocked by branch protection; all changes must arrive via PR with a passing `ci / test` check.
