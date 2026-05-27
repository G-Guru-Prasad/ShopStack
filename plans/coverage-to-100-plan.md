# Plan: Push coverage from 95.2% → 100%

## Current state (baseline)

Run on 2026-05-27 with `coverage run --rcfile=.coveragerc manage.py test --keepdb`:

```
TOTAL  955 stmts, 46 missing, 95.2%
```

Missing lines by file:

| File | Missing | Lines |
| --- | ---: | --- |
| stackapp/auth_views.py | 2 | 235-236 |
| stackapp/constants.py | 3 | 1-3 |
| stackapp/factories.py | 3 | 63-65 |
| stackapp/middleware.py | 3 | 21-24 |
| stackapp/models.py | 13 | 17, 59, 78, 100, 112, 127, 145, 170, 185, 205, 239, 242, 273 |
| stackapp/permissions.py | 2 | 13, 16 |
| stackapp/views.py | 20 | 32, 38-40, 49, 60, 64-66, 76, 86, 90-91, 99, 102-104, 117, 120-121 |

## What each gap is

- **models.py** — `__str__` methods on every model. Never called.
- **views.py** — POST/PATCH/DELETE permission branches and `perform_create`/`perform_update` paths for Category, Product, ProductVariant; `search` query param; `?all=1` toggle.
- **middleware.py** — `Tenant.DoesNotExist` branch + hostname with <2 parts (no subdomain).
- **permissions.py** — unauthenticated request + missing tenant_id.
- **factories.py** — `PasswordResetOTPFactory.expires_at` lazy attribute. Hit by building an OTP via factory.
- **auth_views.py 235-236** — `PasswordResetOTP.DoesNotExist` branch in OTP-verify view (valid user, no OTPs).
- **constants.py** — module is never imported. Just import it in a test.

## Implementation

Add a new test module `shopstack/stackapp/test_coverage_gaps.py` using `factory_boy` factories (per user choice) and the existing `APITestBase` pattern. Group:

1. `ModelStrTest` — instantiate one of every model and call `str(...)`.
2. `ViewWritePathTest` — POST a Category, POST a Product, PATCH a Product, POST a Variant, DELETE a Variant; GET products with `search=` and `all=1`.
3. `MiddlewareTest` — hit any URL with HTTP_HOST=`unknownsub.localhost` (DoesNotExist) and HTTP_HOST=`localhost` (single-part).
4. `PermissionTest` — unauth request to a protected endpoint; auth request with no tenant subdomain.
5. `FactoriesTest` — build `PasswordResetOTPFactory()` and assert `expires_at` populated.
6. `OTPNotFoundTest` — call OTP-verify for a user that has no OTP rows.
7. `ConstantsImportTest` — `import stackapp.constants`.

## Acceptance

- `coverage report --rcfile=.coveragerc` shows 100% (or whatever the residual is documented as unreachable).
- All existing 147 tests still pass.
- Raise `--fail-under` in `.github/workflows/ci.yml` to 100 in the same PR.


## Test Directory Restructure

- As part of the coverage, restructure the test files into one single directory `stackapp/tests/` (currently they are in `stackapp/` with names like `test_*.py`). This is a more conventional structure and will make it easier to find tests in the future. Update imports accordingly.
