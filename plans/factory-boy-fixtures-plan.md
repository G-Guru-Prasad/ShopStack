# Plan: factory_boy test fixture setup for ShopStack

## Context

Every test class in `shopstack/stackapp/` today re-creates a `Tenant` + `User` + `TenantUser`, sets `tenant_id` / `user_id` in `ThreadVaribales`, patches the cached `tenant_id` on each tenant-scoped model's manager, and then calls `.objects.create(...)` with hand-written kwargs for each domain object. The boilerplate is duplicated across `tests.py` and `test_auth.py` and the manager-patch step is easy to forget — which silently corrupts tenant isolation in tests.

Adding `factory_boy` gives us declarative, reusable model factories. Wrapping them with a small `TenantContext` helper centralizes the thread-local setup so new tests can build a tenant-scoped object graph in one or two lines and existing base classes shrink considerably. This is purely a test-infrastructure change — no production code is modified.

## Approach

### 1. Add the dependency

- `factory_boy==3.3.1` appended to `requirements.txt`.

### 2. `TenantContext` helper

Added to `shopstack/stackapp/utils.py`. Context manager that:
- On `__enter__`: stashes previous thread-local `tenant_id` / `user_id`, sets new values, and refreshes the cached `tenant_id` on every model whose default manager is a `TenantBasedManager` (discovered via `django.apps.apps.get_models()`).
- On `__exit__`: restores prior thread-local values and prior manager-cached `tenant_id`s.

Solves the "stale cached tenant_id on the manager" footgun centrally.

### 3. `shopstack/stackapp/factories.py`

One module with twelve factories: `TenantFactory`, `UserFactory`, `TenantUserFactory`, `PasswordResetOTPFactory`, `CategoryFactory`, `ProductFactory`, `ProductVariantFactory`, `CartFactory`, `CartItemFactory`, `AddressFactory`, `OrderFactory`, `OrderItemFactory`, `PaymentFactory`.

Conventions:
- `factory.Sequence` for unique slugs / SKUs / usernames.
- `factory.SubFactory` for FKs.
- `UserFactory._create` overridden to call `User.objects.create_user` so passwords are hashed correctly.
- `TenantUserFactory` uses `django_get_or_create=('tenant', 'user')` (unique-together).
- `CartItemFactory` uses `django_get_or_create=('cart', 'product_variant')`.
- `OrderFactory.total_amount` defaults to `0.00` — tests that need a real total pass it explicitly. The factory does not run the placement code path; tests exercising placement still go through the API.

### 4. Refactor base test classes

`APITestBase` (in `tests.py`) and `AuthTestBase` (in `test_auth.py`) now build their tenant/user/TenantUser via factories and enter a `TenantContext` in `setUp` / exit it in `tearDown`. The manual `model.objects.tenant_id = ...` patch loop and the `_restore_thread_locals` helper-on-every-request remain only as no-op compatibility (thread-local restore for API helpers, since `TenantMiddleware` still wipes thread-local at response end).

### 5. Smoke test

`FactorySmokeTest` in `tests.py` builds the full graph (Category → Product → Variant → Cart → CartItem → Address → Order → OrderItem → Payment) via factories and asserts every row has the active `tenant_id` and `created_by_id`.

## Files changed

- `requirements.txt`
- `shopstack/stackapp/utils.py`
- `shopstack/stackapp/factories.py` *(new)*
- `shopstack/stackapp/tests.py`
- `shopstack/stackapp/test_auth.py`
- `plans/factory-boy-fixtures-plan.md` *(this file)*

## Verification

```bash
source ~/genv/bin/activate
pip install -r requirements.txt
cd shopstack
python3 manage.py test stackapp --keepdb
coverage run --rcfile=.coveragerc manage.py test stackapp --keepdb && coverage report
```

All tests must pass and coverage must stay at or above 94%.
