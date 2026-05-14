# Forgot Password OTP Feature

## Context

ShopStack has token-based password reset endpoints (`/api/auth/password-reset/`) but email sending is stubbed out and there is no OTP flow. This plan adds a tenant-scoped OTP-based "Forgot Password" flow:

1. Login page (2-step): enter email → enter OTP
2. On OTP success: redirect to a dedicated `/reset-password/` page to set the new password

---

## Changes Overview

| Layer | File | Change |
|---|---|---|
| Model | `stackapp/models.py` | Add `PasswordResetOTP` with `reset_token` + `is_otp_verified` fields |
| Migration | `stackapp/migrations/0005_passwordresetotp.py` | New migration |
| Throttle | `stackapp/throttles.py` | New `ForgotPasswordThrottle` class (10/hour) |
| Serializers | `stackapp/auth_serializers.py` | Add 3 serializer classes |
| Views | `stackapp/auth_views.py` | Add 3 view classes |
| URLs (API) | `stackapp/auth_urls.py` | Add 3 API path entries |
| URLs (page) | `shopstack/urls.py` | Add `/reset-password/` page route |
| Settings | `shopstack/settings.py` | Add `EMAIL_BACKEND` + `forgot_password` throttle rate |
| Template | `stackapp/templates/stackapp/login.html` | Add 2-step FP panel + styles |
| Template | `stackapp/templates/stackapp/reset_password.html` | New reset password page |
| JS | `stackapp/static/stackapp/js/login.js` | Add FP email + OTP steps |
| JS | `stackapp/static/stackapp/js/reset_password.js` | New reset password page logic |
| Tests | `stackapp/test_auth.py` | Add `ForgotPasswordOTPTest` class |

---

## Step 1 — Model (`stackapp/models.py`)

Add `PasswordResetOTP` after the `TenantUser` class. Use a plain `models.Model` (NOT `TenantBaseModel`) — auth infrastructure must not be filtered by `TenantBasedManager`.

```python
import uuid

class PasswordResetOTP(models.Model):
    user             = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='password_reset_otps')
    tenant           = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='password_reset_otps')
    otp              = models.CharField(max_length=6)
    reset_token      = models.CharField(max_length=64, null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    expires_at       = models.DateTimeField()
    is_used          = models.BooleanField(default=False)
    is_otp_verified  = models.BooleanField(default=False)
    attempt_count    = models.IntegerField(default=0)

    class Meta:
        db_table = 'password_reset_otps'
        indexes = [
            models.Index(fields=['user', 'tenant', 'is_used']),
            models.Index(fields=['reset_token']),
        ]

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at

    def is_valid(self):
        return not self.is_used and not self.is_expired()
```

- `reset_token`: UUID generated after OTP is verified; passed to the `/reset-password/` page via query string
- `is_otp_verified`: set `True` when OTP is validated; the confirm view checks this before allowing a password reset

---

## Step 2 — Migration

Run `python3 manage.py makemigrations stackapp --name=passwordresetotp` after adding the model. This is a new table — run tests **without** `--keepdb` on first run.

---

## Step 3 — Throttle (`stackapp/throttles.py`) — NEW FILE

Create a new file with a dedicated throttle for the forgot-password endpoints. These endpoints are unauthenticated, so DRF falls back to IP-based throttling, giving 10 requests per hour per IP address.

```python
from rest_framework.throttling import ScopedRateThrottle


class ForgotPasswordThrottle(ScopedRateThrottle):
    scope = 'forgot_password'
```

Add the rate to `DEFAULT_THROTTLE_RATES` (see Step 8). Applying this class directly (instead of relying on `throttle_scope`) keeps the forgot-password rate completely separate from the existing `auth: 10/minute` scope — so these views are NOT double-throttled.

---

## Step 4 — Serializers (`stackapp/auth_serializers.py`)

Append after `PasswordResetConfirmSerializer`:

```python
class ForgotPasswordRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ForgotPasswordVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp   = serializers.CharField(min_length=6, max_length=6)


class ForgotPasswordConfirmSerializer(serializers.Serializer):
    reset_token          = serializers.CharField()
    new_password         = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})
        validate_password(attrs['new_password'])
        return attrs
```

Password validation is moved entirely to the confirm step — the verify step only validates the OTP.

---

## Step 5 — Views (`stackapp/auth_views.py`)

**Additional imports:**
```python
import random
import uuid
from datetime import timedelta

from django.core.mail import send_mail
from django.utils import timezone

from stackapp.auth_serializers import (
    ForgotPasswordConfirmSerializer,
    ForgotPasswordRequestSerializer,
    ForgotPasswordVerifySerializer,
)
from stackapp.models import PasswordResetOTP, TenantUser
from stackapp.throttles import ForgotPasswordThrottle
from stackapp.utils import ThreadVaribales
```

Add three views after `PasswordResetConfirmView`:

### `ForgotPasswordRequestView`
```
throttle_classes = [ForgotPasswordThrottle]   # 10/hour per IP
permission_classes = [AllowAny]
```
- Deserialize with `ForgotPasswordRequestSerializer`
- Lookup: `TenantUser.objects.get(tenant_id=tenant_id, user__email=email, is_active=True)`
- If not found: silently return 200 (anti-enumeration)
- Invalidate prior unused OTPs: `.filter(user, tenant, is_used=False).update(is_used=True)`
- Generate OTP: `f"{random.SystemRandom().randint(0, 999999):06d}"`
- `expires_at = timezone.now() + timedelta(minutes=10)`
- `PasswordResetOTP.objects.create(user, tenant_id, otp, expires_at)`
- `send_mail(subject, message, from_email, [email], fail_silently=True)`
- Always return `200 {"detail": "If that email address is registered, an OTP has been sent."}`

### `ForgotPasswordVerifyView`
```
throttle_classes = [ForgotPasswordThrottle]   # 10/hour per IP
permission_classes = [AllowAny]
```
- Deserialize with `ForgotPasswordVerifySerializer`
- Look up user via TenantUser (400 if not found)
- Fetch latest unused OTP: `.filter(user, tenant, is_used=False).latest('created_at')`
- Guard order:
  1. `attempt_count >= 3` → 400 "Too many incorrect attempts. Please request a new OTP."
  2. `is_expired()` → 400 "OTP has expired. Please request a new one."
  3. `otp != otp_input` → `attempt_count += 1; save(update_fields=['attempt_count'])` → 400 "Invalid email or OTP."
- On correct OTP:
  - Generate `reset_token = uuid.uuid4().hex`
  - `otp_record.is_otp_verified = True; otp_record.reset_token = reset_token`
  - `otp_record.save(update_fields=['is_otp_verified', 'reset_token'])`
  - Return `200 {"reset_token": reset_token}`

### `ForgotPasswordConfirmView`
```
throttle_classes = [ForgotPasswordThrottle]   # 10/hour per IP
permission_classes = [AllowAny]
```
- Deserialize with `ForgotPasswordConfirmSerializer`
- Look up OTP record: `PasswordResetOTP.objects.get(reset_token=reset_token, is_otp_verified=True, is_used=False)` → 400 "Invalid or expired reset token." if not found
- `is_expired()` → 400 "Reset token has expired. Please start over."
- Reset password: `user.set_password(new_password); user.save()`
- Mark used: `otp_record.is_used = True; otp_record.save(update_fields=['is_used'])`
- Return `200 {"detail": "Password has been reset successfully."}`

---

## Step 6 — URLs

### API (`stackapp/auth_urls.py`)

```python
from stackapp.auth_views import (
    ...,
    ForgotPasswordConfirmView,
    ForgotPasswordRequestView,
    ForgotPasswordVerifyView,
)

path('forgot-password/', ForgotPasswordRequestView.as_view(), name='auth-forgot-password'),
path('forgot-password/verify/', ForgotPasswordVerifyView.as_view(), name='auth-forgot-password-verify'),
path('forgot-password/confirm/', ForgotPasswordConfirmView.as_view(), name='auth-forgot-password-confirm'),
```

### Page (`shopstack/urls.py`)

Add a `TemplateView` route for the reset password page (no auth required):

```python
from django.views.generic import TemplateView

path('reset-password/', TemplateView.as_view(template_name='stackapp/reset_password.html'), name='reset-password'),
```

---

## Step 7 — Settings (`shopstack/settings.py`)

```python
# Add to DEFAULT_THROTTLE_RATES:
'forgot_password': '10/hour',

# Add after SIMPLE_JWT block:
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

The `forgot_password` scope is served by `ForgotPasswordThrottle` (scope = `'forgot_password'`). The existing `auth: 10/minute` scope is untouched and does NOT apply to the FP endpoints.

---

## Step 8 — Login Page Template (`stackapp/templates/stackapp/login.html`)

Add CSS inside `<style>`:
```css
#fp-link { cursor: pointer; color: #00695c; font-size: 0.85rem;
           text-decoration: underline; margin-top: 8px; display: inline-block; }
#fp-back-login { cursor: pointer; color: #78909c; font-size: 0.85rem;
                 text-decoration: underline; margin-top: 8px; display: inline-block; }
```

After the closing `</form>` of `#login-form`, add:

```html
<p><a id="fp-link">Forgot Password?</a></p>

<div id="fp-panel" style="display:none;">

  <!-- Step 1: Email -->
  <div id="fp-step-1" style="display:none;">
    <p class="card-title" style="font-size:1.2rem;">Reset Password</p>
    <p class="brand-sub">Enter your account email to receive an OTP.</p>
    <div class="input-field">
      <input id="fp-email" type="email" autocomplete="email">
      <label for="fp-email">Email Address</label>
    </div>
    <p id="fp-step1-error" class="red-text" style="display:none;" aria-live="polite"></p>
    <button id="fp-send-btn" type="button"
            class="btn teal darken-2 waves-effect waves-light btn-login">Send OTP</button>
    <p><a id="fp-back-login">Back to Sign In</a></p>
  </div>

  <!-- Step 2: OTP -->
  <div id="fp-step-2" style="display:none;">
    <p class="card-title" style="font-size:1.2rem;">Enter OTP</p>
    <p class="brand-sub">Check your email for a 6-digit code (valid 10 minutes).</p>
    <div class="input-field">
      <input id="fp-otp" type="text" maxlength="6" inputmode="numeric" autocomplete="one-time-code">
      <label for="fp-otp">6-digit OTP</label>
    </div>
    <p id="fp-step2-error" class="red-text" style="display:none;" aria-live="polite"></p>
    <button id="fp-verify-btn" type="button"
            class="btn teal darken-2 waves-effect waves-light btn-login">Verify OTP</button>
    <p><a id="fp-back-step1">Back</a></p>
  </div>

</div>
```

---

## Step 9 — Login Page JS (`stackapp/static/stackapp/js/login.js`)

Append inside the existing `DOMContentLoaded` callback:

- `showFpStep(n)` — hides `#login-form`, shows `#fp-panel`, shows step n div
- `showLoginForm()` — restores login form, hides FP panel, clears inputs, calls `M.updateTextFields()`
- `fpEmailStored` — closure variable carrying email from step 1 to step 2
- `fpLink` click → `showFpStep(1)`
- `fpBackLogin` / `fpBackStep1` clicks → `showLoginForm()` / `showFpStep(1)`
- `fpSendBtn` click:
  - Validate email input not empty
  - `POST /api/auth/forgot-password/` with `{email}`
  - On `resp.ok` → `fpEmailStored = email; showFpStep(2); M.updateTextFields()`
  - On 429 → show step1 error "Too many attempts. Please wait and try again."
  - On other error → show step1 error "Something went wrong. Please try again."
- `fpVerifyBtn` click:
  - Validate OTP is 6 digits
  - `POST /api/auth/forgot-password/verify/` with `{email: fpEmailStored, otp}`
  - On `resp.ok` → `window.location.href = '/reset-password/?token=' + data.reset_token`
  - On 429 → show step2 error "Too many attempts. Please wait and try again."
  - On 400 → show step2 error from `data.detail`

---

## Step 10 — Reset Password Template (`stackapp/templates/stackapp/reset_password.html`)

New page matching the login card style (same Materialize CSS, teal theme, centered card). Contains:
- Card title "Set New Password"
- `new_password` and `new_password_confirm` input fields with visibility toggle on new_password
- Error `<p>` element with `aria-live="polite"`
- "Set Password" submit button
- On success: show success message + "Back to Sign In" link to `/login/`
- On page load: read `?token=` from query string; if missing, show error and disable form

---

## Step 11 — Reset Password JS (`stackapp/static/stackapp/js/reset_password.js`)

- On `DOMContentLoaded`: parse `token` from `URLSearchParams`; if absent, show "Invalid or expired link." and disable submit
- On submit:
  - Validate passwords not empty + match (client-side)
  - `POST /api/auth/forgot-password/confirm/` with `{reset_token: token, new_password, new_password_confirm}`
  - On `resp.ok` → hide form, show success message with link to `/login/`
  - On 400 → show `data.detail`
  - On 429 → show "Too many attempts. Please wait and try again."

---

## Step 12 — Tests (`stackapp/test_auth.py`)

**Additional imports:**
```python
from datetime import timedelta
from django.utils import timezone
from stackapp.models import PasswordResetOTP
```

Add `ForgotPasswordOTPTest(AuthTestBase)` — 20 test methods:

| Test | Asserts |
|---|---|
| `test_request_returns_200_for_valid_email` | status 200 |
| `test_request_returns_200_for_unknown_email` | status 200 (anti-enumeration) |
| `test_request_creates_otp_record` | 1 unused OTP in DB |
| `test_request_otp_expires_at_10_minutes` | `expires_at - created_at ≈ 600s` |
| `test_request_invalidates_previous_otp` | prior OTP marked `is_used=True` |
| `test_verify_returns_reset_token_on_correct_otp` | status 200, `reset_token` in response |
| `test_verify_sets_is_otp_verified` | `otp_record.is_otp_verified == True` |
| `test_verify_wrong_otp_returns_400` | status 400 |
| `test_verify_wrong_otp_increments_attempt_count` | `attempt_count == 1` |
| `test_verify_locked_after_3_wrong_attempts` | correct OTP rejected with "Too many" message |
| `test_verify_expired_otp_returns_400` | status 400, "expired" in detail |
| `test_verify_unknown_email_returns_400` | status 400 |
| `test_confirm_resets_password` | status 200, `check_password` passes |
| `test_confirm_marks_otp_as_used` | `otp_record.is_used == True` |
| `test_confirm_token_cannot_be_reused` | second confirm returns 400 |
| `test_confirm_invalid_token_returns_400` | status 400 |
| `test_confirm_expired_token_returns_400` | manually expire OTP, status 400 |
| `test_confirm_password_mismatch_returns_400` | status 400 |
| `test_confirm_weak_password_returns_400` | status 400 |
| `test_request_scoped_to_tenant` | cross-tenant email creates no OTP |

Helper method `_request_otp()` → triggers request, returns OTP record from DB.
Helper method `_verify_otp(record)` → posts verify, returns `reset_token` string.

---

## Verification

```bash
cd shopstack

# 1. Create migration (no --keepdb — new table)
python3 manage.py makemigrations stackapp --name=passwordresetotp
python3 manage.py migrate

# 2. Run new OTP tests only
python3 manage.py test stackapp.test_auth.ForgotPasswordOTPTest

# 3. Full auth regression
python3 manage.py test stackapp.test_auth

# 4. Full suite
python3 manage.py test stackapp

# 5. Manual end-to-end (dev server)
# python3 manage.py runserver
# Navigate to acme.localhost:8000/login/
# Click "Forgot Password?" → enter email → copy 6-digit OTP from terminal
# Enter OTP → redirected to /reset-password/?token=<uuid>
# Enter new password → success → sign in with new password

# 6. Verify throttle (11th request returns 429)
# for i in $(seq 1 11); do curl -s -o /dev/null -w "%{http_code}\n" -X POST http://acme.localhost:8000/api/auth/forgot-password/ -H "Content-Type: application/json" -d '{"email":"test@acme.com"}'; done
```
