# UI Pages Execution Results — Login, Dashboard, Profile

**Plan file:** `plans/ui_pages.md`
**Date:** 2026-03-27
**Status:** COMPLETED — 124 tests passing

---

## Summary

Implemented three Materialize CSS UI pages (login, dashboard, profile) served by Django `TemplateView`. All data is fetched client-side via vanilla JS from the existing DRF endpoints. A new `GET /api/auth/me/` backend endpoint was added. All 121 existing tests continue to pass and 3 new `MeViewTest` tests were added.

---

## Steps Executed

### Step 1: Update `settings.py`
- Added `SECURE_CONTENT_TYPE_NOSNIFF = True`
- Added `CSRF_COOKIE_HTTPONLY = False`
- Added `CSRF_COOKIE_SAMESITE = 'Lax'`
- **Result:** OK

### Step 2: Add `GET /api/auth/me/` endpoint
- Added `MeView(APIView)` to `stackapp/auth_views.py` — returns `id`, `username`, `email`, `first_name`, `last_name` for the authenticated user
- Registered `path('me/', MeView.as_view(), name='auth-me')` in `stackapp/auth_urls.py`
- Added 3 new tests in `test_auth.py` (`MeViewTest`): authenticated → 200 + correct fields; unauthenticated → 401; own data only
- **Result:** OK

### Step 3: Create `stackapp/static/stackapp/js/auth.js`
- Token storage helpers: `getAccessToken()`, `getRefreshToken()`, `setTokens()`, `clearTokens()`
- `getCsrfToken()` — reads `csrftoken` cookie via regex
- `authFetch()` — injects `Authorization: Bearer` + `X-CSRFToken`, auto-refreshes on 401 with `_refreshPromise` race-condition lock, redirects to `/login/` if refresh fails
- `requireAuth()` — immediate redirect if no access token
- `logout()` — POSTs `/api/auth/logout/` (best-effort), clears storage, redirects
- Cross-tab logout via `window.addEventListener('storage', ...)`
- **Result:** OK

### Step 4: Create `stackapp/page_views.py` and `stackapp/page_urls.py`
- `page_views.py`: `RootRedirectView` (→ `/login/`), `LoginPageView`, `DashboardPageView`, `ProfilePageView`
- `page_urls.py`: routes `/`, `/login/`, `/dashboard/`, `/profile/`
- Wired into `shopstack/urls.py`: `path('', include('stackapp.page_urls'))`
- **Result:** OK

### Step 5: Create `base.html`
- Materialize CSS 1.0.0 + Material Icons via CDN with SRI integrity hashes
- Fixed top teal navbar with brand "ShopStack", desktop nav links, hamburger trigger
- Mobile `sidenav` drawer mirroring desktop links, initialised with `M.Sidenav.init()`
- Logout buttons wired to `logout()` from `auth.js`
- `{% block content %}`, `{% block nav_links %}`, `{% block extra_js %}` extension points
- **Result:** OK

### Step 6: Create `login.html` + `login.js`
- Standalone page (no navbar), full-height grey background, vertically centred `z-depth-3` card
- Materialize `input-field` floating labels for username and password
- Password visibility toggle using `<i class="material-icons suffix">`
- Error area (`aria-live="polite"`) using `textContent` — never `innerHTML`
- `login.js`: redirects to `/dashboard/` if already logged in; handles 401 ("Invalid username or password"), 429 ("Too many attempts"), network errors via `M.toast`; disables submit while in-flight
- **Result:** OK

### Step 7: Create `dashboard.html` + `dashboard.js`
- Materialize responsive grid: `col s12 m8` orders card, `col s12 m4` cart card
- Circular preloader while data loads; replaced by content on completion
- Orders rendered in `<table class="striped responsive-table">` using `createElement` + `textContent` only (no `innerHTML` with data)
- Status chips: `PENDING`→orange, `CONFIRMED`→blue, `SHIPPED`→cyan, `DELIVERED`→green, `CANCELLED`→red
- Empty state row if no orders
- `dashboard.js`: `requireAuth()`, decodes username from JWT payload via `atob`, `Promise.all` parallel fetch of orders + cart, `M.toast` on error
- **Result:** OK

### Step 8: Create `profile.html` + `profile.js`
- Two stacked `z-depth-1` cards: "My Profile" (read-only `<dl>`) and "Change Password"
- Profile card: circular preloader, `<dt>`/`<dd>` pairs with `textContent` values
- Change password: three `input-field` wrappers with floating labels and eye-toggle icons; `<span class="helper-text red-text">` for per-field errors
- `profile.js`: `requireAuth()`, loads `/api/auth/me/`, populates `<dl>` via `textContent`; client-side confirm-match check; sends `current_password`, `new_password`, `new_password_confirm` to API; maps 400 field errors to helper-text spans; `M.toast` for success/network errors
- **Result:** OK

---

## Issues Encountered and Fixed

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Materialize CSS not loading | SRI integrity hashes in templates were incorrect placeholder values | Recomputed correct hashes using `curl \| openssl dgst -sha512` and updated all templates |
| `new_password_confirm` required error on change-password | `profile.js` sent only `current_password` + `new_password`; `ChangePasswordSerializer` requires `new_password_confirm` for server-side validation | Added `new_password_confirm: confirmPwd` to the POST body in `profile.js` |

---

## Auth Endpoint Added

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/auth/me/` | GET | Yes | Returns authenticated user's id, username, email, first_name, last_name |

## Page Routes Delivered

| Page | Route | Protected | API Calls |
|------|-------|-----------|-----------|
| Root | `/` | No | Redirects to `/login/` |
| Login | `/login/` | No | `POST /api/auth/login/` |
| Dashboard | `/dashboard/` | Yes (client) | `GET /api/orders/`, `GET /api/cart/` |
| Profile | `/profile/` | Yes (client) | `GET /api/auth/me/`, `POST /api/auth/change-password/` |

---

## Test Results

```
Ran 124 tests in 40.019s
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
| `MeViewTest` | 3 | /api/auth/me/ access + data |

---

## Files Created or Modified

| File | Action |
|------|--------|
| `shopstack/shopstack/settings.py` | Modified — security cookie settings |
| `shopstack/shopstack/urls.py` | Modified — included page_urls |
| `shopstack/stackapp/auth_views.py` | Modified — added MeView |
| `shopstack/stackapp/auth_urls.py` | Modified — registered me/ route |
| `shopstack/stackapp/test_auth.py` | Modified — added MeViewTest (3 tests) |
| `shopstack/stackapp/page_views.py` | Created |
| `shopstack/stackapp/page_urls.py` | Created |
| `shopstack/stackapp/static/stackapp/js/auth.js` | Created |
| `shopstack/stackapp/static/stackapp/js/login.js` | Created |
| `shopstack/stackapp/static/stackapp/js/dashboard.js` | Created |
| `shopstack/stackapp/static/stackapp/js/profile.js` | Created |
| `shopstack/stackapp/templates/stackapp/base.html` | Created |
| `shopstack/stackapp/templates/stackapp/login.html` | Created |
| `shopstack/stackapp/templates/stackapp/dashboard.html` | Created |
| `shopstack/stackapp/templates/stackapp/profile.html` | Created |
| `plans/ui_pages.md` | Created |
