# UI Pages Plan — Login, Dashboard, Profile

## Context

ShopStack is a pure REST API backend with zero frontend code. The JWT auth system (recently added) exposes the endpoints this UI will consume. The goal is to add three UI pages — login, dashboard, profile — served by Django, with all data fetched client-side from the existing DRF endpoints via vanilla JS.

---

## Approach: Django Templates + External JS + Materialize CSS CDN

**Stack:**
- Django `TemplateView` serves HTML shells (no SSR data embedding)
- External `.js` static files (not inline scripts) — required for Content Security Policy
- Materialize CSS + JS loaded from CDN with SRI hash integrity check (Material Design components out of the box)
- `fetch()` calls the existing DRF endpoints with `Authorization: Bearer` header
- JWT tokens stored in `localStorage` (standard for API-first apps)

**Why Materialize over Bootstrap:**
- Material Design language gives a polished, modern look with elevation, ripple effects, and card depth
- Built-in components match the app's needs exactly: cards, navbar, text fields with floating labels, preloaders, toasts, chips for status badges
- Materialize text fields use floating labels — the label rises above the input on focus/fill, eliminating the need for separate `<label>` + placeholder management

---

## Settings Changes (`shopstack/settings.py`)

`APP_DIRS = True` already handles template and static file discovery from `stackapp/templates/` and `stackapp/static/`. **One addition needed:**

```python
# Prevent MIME-type sniffing attacks
SECURE_CONTENT_TYPE_NOSNIFF = True

# Ensure JS can read the CSRF cookie (default False = readable, but be explicit)
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'
```

`X_FRAME_OPTIONS = 'DENY'` is already enforced by `XFrameOptionsMiddleware` (clickjacking protection active).

---

## Security Design

### 1. XSS Prevention — DOM Rendering Rule
**All API data inserted into the DOM must use `el.textContent = value`, never `el.innerHTML = value`.** This prevents stored/reflected XSS from malicious server data appearing in the rendered page.

### 2. Content Security Policy
JS lives in external files (`stackapp/static/stackapp/js/auth.js`) — not inline — enabling a strict CSP. Add response headers via Django middleware or `SecurityMiddleware`:
```
Content-Security-Policy: default-src 'self';
  script-src 'self' https://cdnjs.cloudflare.com;
  style-src 'self' https://cdnjs.cloudflare.com https://fonts.googleapis.com;
  font-src 'self' https://fonts.gstatic.com;
  img-src 'self' data:;
  connect-src 'self';
```
Materialize CSS + JS and the Material Icons font are served from `cdnjs.cloudflare.com` and Google Fonts. CDN links must include **SRI integrity + crossorigin attributes**:
```html
<link rel="stylesheet"
      href="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/css/materialize.min.css"
      integrity="sha512-..." crossorigin="anonymous">
<script src="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/js/materialize.min.js"
        integrity="sha512-..." crossorigin="anonymous"></script>
<!-- Material Icons (Google Fonts CDN) -->
<link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
```
Note: Materialize requires jQuery is **not** needed — it is vanilla JS since v1.0.

### 3. CSRF Handling
DRF uses `JWTAuthentication` — CSRF is **not enforced** on API endpoints (only enforced with `SessionAuthentication`). However, `auth.js` will still include `X-CSRFToken` on every non-GET request (read from the `csrftoken` cookie) as defence-in-depth.

### 4. Token Refresh Race Condition
Multiple concurrent API calls expiring simultaneously would each fire a `/api/auth/token/refresh/` call. Implement a **refresh lock** in `auth.js`:
```javascript
let _refreshPromise = null;
async function refreshAccessToken() {
    if (_refreshPromise) return _refreshPromise;  // queue behind the in-flight refresh
    _refreshPromise = doRefresh().finally(() => { _refreshPromise = null; });
    return _refreshPromise;
}
```

### 5. Rate Limit (429) Feedback
Login and register endpoints return `429` when throttled. Show a user-friendly message: _"Too many attempts. Please wait a minute and try again."_ — never expose raw API error bodies to users.

### 6. Cross-Tab Logout
Listen for `localStorage` `storage` events so if the user logs out in one tab, all other open tabs redirect to `/login/` automatically:
```javascript
window.addEventListener('storage', e => {
    if (e.key === 'shopstack_access' && !e.newValue) window.location = '/login/';
});
```

### 7. No Open Redirect
Login page will **not** accept a `?next=` query parameter. After login, always redirect to `/dashboard/` — no dynamic redirect targets.

---

## UI Design Principles

### Accessibility
- Materialize floating-label text fields include `<label>` linked to each `<input>` by default — no placeholder-only labels
- Error messages use `aria-live="polite"` so screen readers announce them
- Password toggle buttons include `aria-label="Show/hide password"` and use Material Icons (`visibility` / `visibility_off`)
- Focus is moved to the first error field after a failed form submission

### Loading & Error States
- Protected pages show Materialize's **circular preloader** (`<div class="preloader-wrapper active">`) while API calls are in progress
- Errors and success messages use Materialize **toasts** (`M.toast({html: '...', classes: 'red'})`) — non-blocking, auto-dismiss after 4 s
- Empty states: _"No orders yet"_ rendered as a centred grey text row in the table body

### Form UX
- Materialize **text fields with floating labels** — label animates above the field on focus/fill; helper text appears below for errors
- `autocomplete` attributes: `autocomplete="username"`, `autocomplete="current-password"`, `autocomplete="new-password"` (confirm field)
- Password toggle: suffix icon button inside the Materialize input field wrapper using `<i class="material-icons suffix">`
- Client-side required-field check before API call — prevents unnecessary round trips
- **Disable submit button + add `disabled` class** while request is in-flight; re-enable on completion

### Visual Design
- **Materialize teal** (`teal darken-2`) primary colour for navbar, buttons, and active states — clean SaaS aesthetic
- Login page: vertically centred Materialize **card** with `z-depth-3` elevation on a light grey (`grey lighten-4`) full-height background
- Dashboard: Materialize **responsive grid** — `col s12 m8` orders card, `col s12 m4` cart card; collapses to full-width on mobile
- Order status **chips**: `PENDING`→`orange white-text`, `CONFIRMED`→`blue white-text`, `SHIPPED`→`cyan white-text`, `DELIVERED`→`green white-text`, `CANCELLED`→`red white-text`
- Navbar: fixed top, teal background, brand "ShopStack", right-aligned links with Materialize `sidenav` triggered on mobile (hamburger icon)
- Cards use `z-depth-1` for content sections, `z-depth-2` on hover for interactive elements

---

## New Backend Endpoint Required

**`GET /api/auth/me/`** — The JWT payload only carries `user_id` + `username`; email and names need a dedicated endpoint for the profile page.

Add to `stackapp/auth_views.py`:
```python
class MeView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        u = request.user
        return Response({
            'id': u.id, 'username': u.username, 'email': u.email,
            'first_name': u.first_name, 'last_name': u.last_name,
        })
```
Wire in `stackapp/auth_urls.py`: `path('me/', MeView.as_view(), name='auth-me')`

---

## File Structure

### New files to create

| File | Purpose |
|------|---------|
| `stackapp/static/stackapp/js/auth.js` | Shared JS: token helpers, `authFetch`, refresh lock, logout, cross-tab sync |
| `stackapp/templates/stackapp/base.html` | Base layout: Materialize CDN with SRI, fixed teal navbar with sidenav, `{% block %}` areas |
| `stackapp/templates/stackapp/login.html` | Login form page |
| `stackapp/templates/stackapp/dashboard.html` | Dashboard: orders table + cart summary |
| `stackapp/templates/stackapp/profile.html` | Profile info + change password form |
| `stackapp/page_views.py` | Three `TemplateView` subclasses |
| `stackapp/page_urls.py` | URL routes: `/`, `/login/`, `/dashboard/`, `/profile/` |

### Files to modify

| File | Change |
|------|--------|
| `shopstack/settings.py` | Add `SECURE_CONTENT_TYPE_NOSNIFF`, `CSRF_COOKIE_HTTPONLY`, `CSRF_COOKIE_SAMESITE` |
| `shopstack/urls.py` | Include `stackapp.page_urls` at root `''` |
| `stackapp/auth_views.py` | Add `MeView` |
| `stackapp/auth_urls.py` | Add `path('me/', ...)` |

---

## Implementation Steps

### Step 1: Update `settings.py`
Add `SECURE_CONTENT_TYPE_NOSNIFF = True`, `CSRF_COOKIE_HTTPONLY = False`, `CSRF_COOKIE_SAMESITE = 'Lax'`.

### Step 2: Add `GET /api/auth/me/` endpoint
Add `MeView` to `auth_views.py`, register in `auth_urls.py`. Add test: with token → 200 + fields; without token → 401.

### Step 3: Create `stackapp/static/stackapp/js/auth.js`
Exports (via module pattern):
- `getAccessToken()` / `setTokens(access, refresh)` / `clearTokens()`
- `getCsrfToken()` — reads `csrftoken` cookie
- `authFetch(url, options)` — injects `Authorization` + `X-CSRFToken`, auto-refresh on 401 with race-condition lock, redirects to `/login/` if refresh fails
- `requireAuth()` — redirects if no token
- `logout()` — POSTs `/api/auth/logout/`, clears storage, redirects
- Cross-tab logout via `window.addEventListener('storage', ...)`

### Step 4: Create `stackapp/page_views.py` and `stackapp/page_urls.py`
```
GET  /           → redirect to /login/
GET  /login/     → LoginPageView
GET  /dashboard/ → DashboardPageView
GET  /profile/   → ProfilePageView
```
Wire into `shopstack/urls.py`: `path('', include('stackapp.page_urls'))`.

### Step 5: Create `base.html`
- `<!DOCTYPE html>`, `lang="en"`, `<meta charset>`, `<meta name="viewport" content="width=device-width, initial-scale=1.0">`
- `{% block title %}ShopStack{% endblock %}` in `<title>`
- Materialize CSS + Material Icons (Google Fonts) + Materialize JS — all via CDN with SRI hashes
- `<script src="{% static 'stackapp/js/auth.js' %}">` (via `{% load static %}`)
- **Fixed top navbar** (`class="navbar-fixed"`): teal background, brand "ShopStack", right-side nav links (Dashboard, Profile, Logout icon button); collapses to hamburger `<a class="sidenav-trigger">` on mobile
- `<ul id="mobile-nav" class="sidenav">` mirrors desktop nav links for mobile drawer
- `M.Sidenav.init(document.querySelectorAll('.sidenav'))` initialised in base JS
- `{% block navbar_extra %}{% endblock %}` — lets login page override to hide nav links
- `{% block content %}{% endblock %}` inside `<main class="container" style="padding-top:80px">`

### Step 6: Create `login.html`
**Layout:** Full-height grey background (`grey lighten-4`), vertically centred Materialize card (`z-depth-3`) — `col s12 m6 offset-m3 l4 offset-l4`.

**Form fields** (Materialize `input-field` wrappers with floating labels):
- Username: `<input id="username" type="text" autocomplete="username" required>` + `<label for="username">Username</label>`
- Password: `<input id="password" type="password" autocomplete="current-password" required>` + `<label for="password">Password</label>` + `<i class="material-icons suffix" id="pwd-toggle" aria-label="Show/hide password">visibility</i>`
- Submit: `<button class="btn teal darken-2 waves-effect waves-light btn-block">` — disabled + shows inline preloader while loading
- Error area: `<p id="error-msg" class="red-text" aria-live="polite" style="display:none"></p>`

**JS (page-specific `<script src="{% static 'stackapp/js/login.js' %}">`):**
1. On load: `if (getAccessToken()) window.location = '/dashboard/'`
2. On submit: prevent default → disable button → `POST /api/auth/login/` → `setTokens()` → `/dashboard/`
3. On 401: show `error-msg` with _"Invalid username or password"_ via `textContent`
4. On 429: show _"Too many attempts. Please wait a minute."_ via `textContent`
5. On network error: `M.toast({html: 'Connection error. Please try again.', classes: 'red'})`
6. Password toggle: click `#pwd-toggle` → toggle `type` between `password`/`text`, swap icon text

### Step 7: Create `dashboard.html`
**Layout:** Materialize responsive grid row.

**Welcome header:** `<h5 class="teal-text darken-2">Welcome, <span id="username-display"></span></h5>` — value set via `textContent`.

**Orders card** (`col s12 m8`, `class="card z-depth-1"`):
- Card title: `<div class="card-title">Recent Orders</div>`
- Circular preloader while loading
- `<table class="striped responsive-table">` — columns: `#`, Status, Total, Date (most recent first)
- Empty state: single `<tr><td colspan="4" class="center-align grey-text">No orders yet.</td></tr>`
- Status chips: `<span class="chip orange white-text">PENDING</span>` etc.

**Cart card** (`col s12 m4`, `class="card z-depth-1"`):
- Card title: `<div class="card-title">Active Cart</div>`
- Shows item count as `<p><span id="cart-count"></span> item(s)</p>` set via `textContent`
- Empty: `<p class="grey-text">Your cart is empty.</p>`

**JS (`dashboard.js`):**
1. `requireAuth()`
2. Decode `username` from JWT payload (base64 → JSON) → set `textContent` on `#username-display`
3. `Promise.all([authFetch('/api/orders/'), authFetch('/api/cart/')])` — parallel load
4. Render table rows using `createElement` + `textContent` only
5. Status chip class map: `PENDING`→`orange`, `CONFIRMED`→`blue`, `SHIPPED`→`cyan`, `DELIVERED`→`green`, `CANCELLED`→`red`
6. On error: `M.toast({html: 'Failed to load data.', classes: 'red'})`

### Step 8: Create `profile.html`
**Layout:** Two stacked Materialize cards (`class="card z-depth-1"`), each with `card-content` + `card-title`.

**Profile card (`card-title`: "My Profile"):**
- Circular preloader while `GET /api/auth/me/` is in flight
- Read-only `<dl>` definition list: Username, Email, First Name, Last Name — all values set via `textContent`
- Labels styled as `<dt class="grey-text text-darken-1">`, values as `<dd class="teal-text darken-2">`

**Change Password card (`card-title`: "Change Password"):**
- Three Materialize `input-field` wrappers with floating labels:
  - Current Password: `<input id="current-password" type="password" autocomplete="current-password">` + `<label for="current-password">Current Password</label>` + `<i class="material-icons suffix" aria-label="Show/hide password">visibility</i>`
  - New Password: same pattern, `autocomplete="new-password"`
  - Confirm New Password: same pattern, `autocomplete="new-password"`
- Field-level validation errors rendered as `<span class="helper-text red-text" data-error="..." id="...-error"></span>` below each input — set via `textContent`, never `innerHTML`
- Client-side check: new password == confirm before API call; on mismatch set helper text _"Passwords do not match"_ on the confirm field
- Submit: `<button class="btn teal darken-2 waves-effect waves-light">Change Password</button>` — disabled + `disabled` class while request is in-flight
- On success: `M.toast({html: 'Password changed successfully.', classes: 'green'})`, all three fields cleared
- On 400: per-field error text from API response set via `textContent` on the matching helper-text `<span>`
- On 401: redirect to `/login/`

**JS (`profile.js`):**
1. `requireAuth()`
2. `authFetch('/api/auth/me/')` → populate `<dl>` values via `textContent`
3. Eye-toggle on each password field: click suffix icon → toggle `type`, swap icon text
4. On submit: validate client-side → disable button → `POST /api/auth/change-password/` → handle success/error as above

---

## Page-by-Page Summary

| Page | Route | Protected | API Calls | Key Security |
|------|-------|-----------|-----------|-------------|
| Login | `/login/` | No | `POST /api/auth/login/` | Rate limit UX, no open redirect |
| Dashboard | `/dashboard/` | Yes | `GET /api/orders/`, `GET /api/cart/` | `requireAuth()`, textContent only |
| Profile | `/profile/` | Yes | `GET /api/auth/me/`, `POST /api/auth/change-password/` | `requireAuth()`, textContent only |

---

## Verification

1. `cd shopstack && python3 manage.py runserver`
2. `http://acme.localhost:8000/login/` — form renders, nav hidden
3. Login → redirected to `/dashboard/`, welcome name shown
4. Dashboard shows orders table (empty state if none) + cart count
5. Profile page shows user info from `/api/auth/me/`
6. Wrong current password → inline field error (not page reload)
7. Logout → tokens cleared, all tabs redirect to `/login/`
8. Open `/dashboard/` with no token → redirect to `/login/`
9. Open browser DevTools → confirm no `innerHTML` calls with API data in JS source
10. `python3 manage.py test stackapp --keepdb` — all existing tests pass
