# Authentication Setup — Execution Results

**Plan file:** `plans/authentication.md`
**Date:** 2026-03-27
**Status:** COMPLETED — All 121 tests passing

---

## Summary

Implemented full JWT-based authentication for the ShopStack multi-tenant platform using `djangorestframework-simplejwt`. All 7 auth endpoints are live, all existing tests continue to pass, and 57 new security tests were added.

---

## Steps Executed

### Step 1: Install dependency
- Installed `djangorestframework-simplejwt`
- Updated `requirements.txt` with `djangorestframework-simplejwt==5.5.0`
- **Result:** OK

### Step 2: Update `settings.py`
- Added `rest_framework_simplejwt` and `rest_framework_simplejwt.token_blacklist` to `INSTALLED_APPS`
- Configured `SIMPLE_JWT`: 15min access token, 7-day refresh with rotation + blacklisting, `Bearer` header
- Updated `REST_FRAMEWORK`: `JWTAuthentication` as default auth, `IsAuthenticated` as default permission, `ScopedRateThrottle` at 10/min for auth endpoints
- Added `stackapp.middleware.JWTUserMiddleware` after `AuthenticationMiddleware` in `MIDDLEWARE`
- **Result:** OK

### Step 3: Add `TenantUser` model + migrations
- Added `TenantUser(tenant FK, user FK, is_active, joined_at)` to `stackapp/models.py`
- Created migration `stackapp/migrations/0004_tenantuser.py`
- Applied all migrations including 12 `token_blacklist` migrations
- **Result:** OK

### Step 4: Create auth files
- **`stackapp/permissions.py`** — `IsTenantMember` permission class
- **`stackapp/auth_serializers.py`** — `RegisterSerializer`, `TenantTokenObtainPairSerializer`, `ChangePasswordSerializer`, `PasswordResetRequestSerializer`, `PasswordResetConfirmSerializer`
- **`stackapp/auth_views.py`** — `RegisterView`, `LoginView`, `CustomTokenRefreshView`, `LogoutView`, `ChangePasswordView`, `PasswordResetRequestView`, `PasswordResetConfirmView`
- **`stackapp/auth_urls.py`** — 7 URL routes under `/api/auth/`
- **Result:** OK

### Step 5: Update middleware, views, and root URLs
- **`middleware.py`** — Added `JWTUserMiddleware`; removed `user_id` lifecycle from `TenantMiddleware` (now owned by `JWTUserMiddleware`)
- **`views.py`** — Added `permission_classes` to all 8 views: `AllowAny` for catalog (categories, product list, product detail); `[IsAuthenticated, IsTenantMember]` for user-scoped resources (cart, cart items, orders, order detail, payments)
- **`shopstack/urls.py`** — Wired `path('api/auth/', include('stackapp.auth_urls'))`
- **Result:** OK

### Step 6: Update `tests.py` + create `test_auth.py`
- **`tests.py`** — Removed `set_val` patching workaround; `APITestBase` now creates `TenantUser`, generates a real JWT via `RefreshToken.for_user()`, and passes `HTTP_AUTHORIZATION` header on every test request
- **`test_auth.py`** — Created 57 new security tests across 7 test classes
- **Result:** OK

---

## Issues Encountered and Fixed

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| 429 Too Many Requests in tests | `ScopedRateThrottle` shares Django cache across test methods — 10/min limit hit | Added `cache.clear()` in `AuthTestBase.setUp()` to reset throttle counters between tests |
| Middleware crash on deleted user | `JWTUserMiddleware` caught `InvalidToken`/`TokenError` but not `AuthenticationFailed` raised when `get_user()` finds no matching user | Added `AuthenticationFailed` to the except clause in `JWTUserMiddleware` |
| `TokenRefreshView` naming conflict | Plan named the view `TokenRefreshView` which shadowed the simplejwt import | Renamed to `CustomTokenRefreshView` in `auth_views.py` |

---

## Auth Endpoints Delivered

| Endpoint | Method | Auth | Rate Limited | Purpose |
|----------|--------|------|-------------|---------|
| `/api/auth/register/` | POST | No | Yes (10/min) | Create account, returns tokens |
| `/api/auth/login/` | POST | No | Yes (10/min) | Returns access + refresh tokens |
| `/api/auth/token/refresh/` | POST | No | No | Refresh access token (rotation) |
| `/api/auth/logout/` | POST | Yes | No | Blacklists refresh token |
| `/api/auth/change-password/` | POST | Yes | No | Change password (requires current) |
| `/api/auth/password-reset/` | POST | No | Yes (10/min) | Forgot password — request reset |
| `/api/auth/password-reset/confirm/` | POST | No | Yes (10/min) | Forgot password — set new password |

---

## Test Results

```
Ran 121 tests in 40.258s
OK
```

| Test class | Tests | Description |
|------------|-------|-------------|
| `CategoryAPITest` | 4 | Category listing |
| `ProductAPITest` | 10 | Product list + detail |
| `CartAPITest` | 4 | Cart get/create |
| `CartItemAPITest` | 6 | Cart item CRUD |
| `OrderAPITest` | 11 | Order placement + listing |
| `OrderMultipleItemsTest` | 3 | Multi-item order total |
| `PaymentAPITest` | 11 | Payment creation + listing |
| `CreatedByAuditTest` | 11 | Audit field population |
| `RegistrationTest` | 7 | Register validation + success |
| `LoginTest` | 5 | Login flows + tenant checks |
| `TokenRefreshTest` | 5 | Refresh rotation + blacklist |
| `LogoutTest` | 5 | Logout + blacklist enforcement |
| `ChangePasswordTest` | 6 | Password change flows |
| `PasswordResetTest` | 7 | Forgot password flows |
| `EndpointProtectionTest` | 9 | Auth enforcement per endpoint |
| `CrossTenantSecurityTest` | 4 | Cross-tenant access blocked |
| `TenantMembershipTest` | 2 | Deactivated/deleted user blocked |

---

## Files Created or Modified

| File | Action |
|------|--------|
| `requirements.txt` | Modified — added simplejwt |
| `shopstack/settings.py` | Modified — simplejwt config, REST_FRAMEWORK, middleware |
| `shopstack/urls.py` | Modified — added auth URL include |
| `stackapp/models.py` | Modified — added `TenantUser` model |
| `stackapp/migrations/0004_tenantuser.py` | Created — migration for TenantUser |
| `stackapp/middleware.py` | Modified — added `JWTUserMiddleware`, cleaned `TenantMiddleware` |
| `stackapp/views.py` | Modified — added `permission_classes` to all views |
| `stackapp/tests.py` | Modified — replaced set_val patching with JWT auth |
| `stackapp/permissions.py` | Created |
| `stackapp/auth_serializers.py` | Created |
| `stackapp/auth_views.py` | Created |
| `stackapp/auth_urls.py` | Created |
| `stackapp/test_auth.py` | Created — 57 security tests |
