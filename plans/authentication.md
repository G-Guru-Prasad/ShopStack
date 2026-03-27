# Authentication Plan for ShopStack

## Context

ShopStack has **zero authentication** today. DRF is configured with empty `DEFAULT_AUTHENTICATION_CLASSES` and `AllowAny` permissions. The middleware sets `user_id=None` and expects views to set it after auth — but no auth mechanism exists. This means all cart, order, and address endpoints are unprotected and `user_id` is always `None`.

**Goal:** Add JWT-based authentication with tenant-user binding, token lifecycle management, change password, forgot password (email-based reset), and proper permission enforcement.

---

## Approach: JWT via `djangorestframework-simplejwt`

### New Files to Create

| File | Purpose |
|------|---------|
| `stackapp/auth_serializers.py` | RegisterSerializer, TenantTokenObtainPairSerializer, ChangePasswordSerializer, password reset serializers |
| `stackapp/auth_views.py` | Register, Login, Logout, TokenRefresh, ChangePassword, PasswordReset/Confirm views |
| `stackapp/auth_urls.py` | `/api/auth/*` URL routes |
| `stackapp/permissions.py` | `IsTenantMember` permission class |

### Files to Modify

| File | Changes |
|------|---------|
| `shopstack/settings.py` | Add `simplejwt` + `token_blacklist` to INSTALLED_APPS, configure `SIMPLE_JWT` (15min access, 7d refresh, rotation+blacklist), update `REST_FRAMEWORK` defaults to `JWTAuthentication` + `IsAuthenticated`, add rate throttling |
| `stackapp/models.py` | Add `TenantUser` model (tenant FK + user FK, unique_together) |
| `stackapp/middleware.py` | Add `JWTUserMiddleware` that decodes Bearer token and sets `user_id` in `ThreadVaribales`; remove `user_id` handling from `TenantMiddleware` |
| `stackapp/views.py` | Add `permission_classes` per view — `AllowAny` for catalog (products, categories), `IsAuthenticated + IsTenantMember` for user resources (cart, orders, payments) |
| `shopstack/urls.py` | Include `stackapp.auth_urls` at `api/auth/` |
| `stackapp/tests.py` | Update `APITestBase` to use JWT tokens instead of `set_val` patching; add auth test classes |

---

## Implementation Steps

### Step 1: Install dependency
```bash
pip install djangorestframework-simplejwt
```

### Step 2: Update `settings.py`
- Add `rest_framework_simplejwt` and `rest_framework_simplejwt.token_blacklist` to `INSTALLED_APPS`
- Configure `SIMPLE_JWT`: 15min access token, 7-day refresh, rotate + blacklist on refresh, `Bearer` header
- Update `REST_FRAMEWORK`: set `JWTAuthentication` as default auth, `IsAuthenticated` as default permission, add `ScopedRateThrottle` at 10/min for auth endpoints
- Add `JWTUserMiddleware` to `MIDDLEWARE` list after `AuthenticationMiddleware`

### Step 3: Add `TenantUser` model + migration
- `TenantUser(tenant FK, user FK, is_active, joined_at)` with `unique_together`
- Does NOT use `TenantBaseModel` — it defines the tenant-user relationship itself
- Run `makemigrations` + `migrate`

### Step 4: Create `permissions.py`
- `IsTenantMember` — checks authenticated user has active `TenantUser` row for current tenant

### Step 5: Create `auth_serializers.py`
- `RegisterSerializer` — validates username uniqueness, email uniqueness, password match + strength via `validate_password()`, creates User + TenantUser
- `TenantTokenObtainPairSerializer` — extends simplejwt's `TokenObtainPairSerializer`, validates user belongs to current tenant before issuing tokens
- `ChangePasswordSerializer` — requires `current_password`, `new_password`, `new_password_confirm`; validates current password via `user.check_password()`, validates new password via `validate_password()`
- `PasswordResetRequestSerializer` / `PasswordResetConfirmSerializer` — Django's `default_token_generator` for uid+token flow

### Step 6: Create `auth_views.py`
- `RegisterView` — creates user, returns access + refresh tokens (auto-login after signup); `AllowAny`, rate-limited
- `LoginView` — extends `TokenObtainPairView`, uses tenant-aware serializer; `AllowAny`, rate-limited
- `LogoutView` — blacklists refresh token; `IsAuthenticated`
- `CustomTokenRefreshView` — simplejwt refresh with rotation (renamed to avoid shadowing the import); `AllowAny`
- `ChangePasswordView` — authenticated user changes own password (requires current password); `IsAuthenticated`
- `PasswordResetRequestView` — always returns success (prevents email enumeration); `AllowAny`, rate-limited
- `PasswordResetConfirmView` — validates uid+token, sets new password; `AllowAny`, rate-limited

### Step 7: Create `auth_urls.py` and update `shopstack/urls.py`
```
POST /api/auth/register/                  # signup, returns tokens
POST /api/auth/login/                     # returns access + refresh
POST /api/auth/token/refresh/             # refresh access token
POST /api/auth/logout/                    # blacklist refresh token
POST /api/auth/change-password/           # authenticated, requires current password
POST /api/auth/password-reset/            # forgot password — request reset email
POST /api/auth/password-reset/confirm/    # forgot password — confirm with uid+token+new password
```

### Step 8: Update `middleware.py`
- Add `JWTUserMiddleware`: extracts Bearer token, decodes JWT, sets `user_id` in `ThreadVaribales`, clears on response
- Remove `user_id` handling from `TenantMiddleware` (owned by `JWTUserMiddleware` now)

### Step 9: Update `views.py` with permission classes
- Catalog views (products, categories): `AllowAny`
- User-scoped views (cart, orders, payments): `[IsAuthenticated, IsTenantMember]`

### Step 10: Update tests
- Update `APITestBase.setUp()` to create `TenantUser` and generate JWT token via `RefreshToken.for_user()`
- Replace `set_val` patching with `HTTP_AUTHORIZATION=Bearer <token>` on all test requests
- Add test classes: `AuthRegistrationTest`, `AuthLoginTest`, `AuthLogoutTest`, `AuthChangePasswordTest`, `AuthProtectedEndpointTest`

---

## Auth Endpoint Summary

| Endpoint | Method | Auth Required | Rate Limited | Purpose |
|----------|--------|--------------|-------------|---------|
| `/api/auth/register/` | POST | No | Yes (10/min) | Create account + auto-login |
| `/api/auth/login/` | POST | No | Yes (10/min) | Get access + refresh tokens |
| `/api/auth/token/refresh/` | POST | No | No | Refresh access token |
| `/api/auth/logout/` | POST | Yes | No | Blacklist refresh token |
| `/api/auth/change-password/` | POST | Yes | No | Change password (knows current) |
| `/api/auth/password-reset/` | POST | No | Yes (10/min) | Forgot password — request reset |
| `/api/auth/password-reset/confirm/` | POST | No | Yes (10/min) | Forgot password — set new password |

---

## Security Properties

| Mechanism | Detail |
|-----------|--------|
| **Short-lived access tokens** | 15 minutes — limits damage from token theft |
| **Refresh rotation + blacklist** | Each refresh token is single-use; old ones are blacklisted |
| **Tenant binding at login** | `TenantTokenObtainPairSerializer` verifies `TenantUser` membership |
| **Tenant binding at request** | `IsTenantMember` permission re-checks on every request |
| **Rate limiting** | 10 req/min on auth endpoints (login, register, password reset) |
| **Password validation** | Django's built-in validators + confirm field on all password changes |
| **Current password required** | Change-password requires `current_password` to prevent session hijack abuse |
| **No email enumeration** | Password reset always returns success regardless of email existence |
| **No sensitive data in JWT** | Only `user_id`, `username`, `exp`, `token_type` |

---

## Middleware Execution Order

```
Request → SecurityMiddleware
        → SessionMiddleware
        → TenantMiddleware          (sets tenant_id from subdomain)
        → CommonMiddleware
        → CsrfViewMiddleware
        → AuthenticationMiddleware  (Django session auth for admin)
        → JWTUserMiddleware         (decodes Bearer JWT, sets user_id in ThreadVaribales)
        → MessageMiddleware
        → XFrameOptionsMiddleware
        → View executes (DRF permission checks happen here)

Response ← JWTUserMiddleware cleanup  (clears user_id)
         ← TenantMiddleware cleanup   (clears tenant_id)
```

---

## Verification

1. Run migrations: `python3 manage.py migrate`
2. Run full test suite: `python3 manage.py test stackapp --keepdb`
3. Manual smoke test:
   - `POST /api/auth/register/` — creates user, returns tokens
   - `POST /api/auth/login/` — returns access + refresh
   - `GET /api/products/` without token — 200 (public)
   - `GET /api/cart/` without token — 401 (protected)
   - `GET /api/cart/` with Bearer token — 200
   - `POST /api/auth/change-password/` with valid current password — 200
   - `POST /api/auth/change-password/` with wrong current password — 400
   - `POST /api/auth/password-reset/` with any email — 200 (always succeeds)
   - `POST /api/auth/password-reset/confirm/` with valid uid+token — 200
   - `POST /api/auth/logout/` — blacklists refresh
   - `POST /api/auth/token/refresh/` with blacklisted token — 401
