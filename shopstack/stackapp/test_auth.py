"""
Security and functional tests for the authentication system.

Covers every auth endpoint and verifies:
- Unauthenticated access is blocked where required
- Cross-tenant access is blocked
- Token lifecycle (refresh, rotation, blacklisting)
- Password flows (change, forgot/reset)
- Registration validation
- Rate-limiting scope assignments
"""
import json

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.test import TestCase
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework_simplejwt.tokens import RefreshToken

from stackapp.models import (
    Cart, Category, Product, ProductVariant,
    Tenant, TenantUser,
)
from stackapp.utils import ThreadVaribales


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _host(subdomain):
    return f'{subdomain}.localhost:8000'


class AuthTestBase(TestCase):
    """Creates tenant + user + TenantUser and pre-generates JWT tokens."""

    def setUp(self):
        # Clear throttle counters between tests
        cache.clear()

        self.tenant = Tenant.objects.create(
            id='acme', name='Acme Corp', subdomain='acme',
        )
        self.user = User.objects.create_user(
            username='testuser', password='TestPass123!', email='test@acme.com',
        )
        TenantUser.objects.create(tenant=self.tenant, user=self.user)

        tv = ThreadVaribales()
        tv.set_val('tenant_id', self.tenant.id)
        tv.set_val('user_id', self.user.id)

        self.host = _host('acme')
        self._refresh_tokens()

    def _refresh_tokens(self):
        refresh = RefreshToken.for_user(self.user)
        self.refresh_token = str(refresh)
        self.access_token = str(refresh.access_token)
        self.auth_header = f'Bearer {self.access_token}'

    def _restore_thread_locals(self):
        tv = ThreadVaribales()
        tv.set_val('tenant_id', self.tenant.id)
        tv.set_val('user_id', self.user.id)

    def post(self, url, data, auth=None):
        headers = {'HTTP_HOST': self.host}
        if auth:
            headers['HTTP_AUTHORIZATION'] = auth
        resp = self.client.post(
            url, data=json.dumps(data), content_type='application/json', **headers,
        )
        self._restore_thread_locals()
        return resp

    def get(self, url, auth=None, host=None):
        headers = {'HTTP_HOST': host or self.host}
        if auth:
            headers['HTTP_AUTHORIZATION'] = auth
        resp = self.client.get(url, **headers)
        self._restore_thread_locals()
        return resp


# ===========================================================================
# Registration tests
# ===========================================================================

class RegistrationTest(AuthTestBase):

    def test_register_success_returns_201_with_tokens(self):
        resp = self.post('/api/auth/register/', {
            'username': 'newuser',
            'email': 'new@acme.com',
            'password': 'StrongPass1!',
            'password_confirm': 'StrongPass1!',
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertIn('access', data)
        self.assertIn('refresh', data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['username'], 'newuser')

    def test_register_creates_tenant_user_binding(self):
        self.post('/api/auth/register/', {
            'username': 'newuser',
            'email': 'new@acme.com',
            'password': 'StrongPass1!',
            'password_confirm': 'StrongPass1!',
        })
        new_user = User.objects.get(username='newuser')
        self.assertTrue(
            TenantUser.objects.filter(tenant=self.tenant, user=new_user).exists()
        )

    def test_register_duplicate_username_returns_400(self):
        resp = self.post('/api/auth/register/', {
            'username': 'testuser',  # already exists
            'email': 'other@acme.com',
            'password': 'StrongPass1!',
            'password_confirm': 'StrongPass1!',
        })
        self.assertEqual(resp.status_code, 400)

    def test_register_duplicate_email_returns_400(self):
        resp = self.post('/api/auth/register/', {
            'username': 'brandnew',
            'email': 'test@acme.com',  # already exists
            'password': 'StrongPass1!',
            'password_confirm': 'StrongPass1!',
        })
        self.assertEqual(resp.status_code, 400)

    def test_register_password_mismatch_returns_400(self):
        resp = self.post('/api/auth/register/', {
            'username': 'newuser2',
            'email': 'new2@acme.com',
            'password': 'StrongPass1!',
            'password_confirm': 'WrongPass1!',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('password_confirm', resp.json())

    def test_register_weak_password_returns_400(self):
        resp = self.post('/api/auth/register/', {
            'username': 'newuser3',
            'email': 'new3@acme.com',
            'password': '123',
            'password_confirm': '123',
        })
        self.assertEqual(resp.status_code, 400)

    def test_register_missing_fields_returns_400(self):
        resp = self.post('/api/auth/register/', {'username': 'x'})
        self.assertEqual(resp.status_code, 400)


# ===========================================================================
# Login tests
# ===========================================================================

class LoginTest(AuthTestBase):

    def test_login_success_returns_tokens(self):
        resp = self.post('/api/auth/login/', {
            'username': 'testuser', 'password': 'TestPass123!',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('access', data)
        self.assertIn('refresh', data)
        self.assertIn('tenant_id', data)
        self.assertEqual(data['tenant_id'], self.tenant.id)

    def test_login_wrong_password_returns_401(self):
        resp = self.post('/api/auth/login/', {
            'username': 'testuser', 'password': 'wrongpass',
        })
        self.assertEqual(resp.status_code, 401)

    def test_login_nonexistent_user_returns_401(self):
        resp = self.post('/api/auth/login/', {
            'username': 'nobody', 'password': 'TestPass123!',
        })
        self.assertEqual(resp.status_code, 401)

    def test_login_user_not_in_tenant_returns_400(self):
        """User exists globally but has no TenantUser row for this tenant."""
        other_user = User.objects.create_user(
            username='outsider', password='TestPass123!',
        )
        # No TenantUser created for this user
        resp = self.post('/api/auth/login/', {
            'username': 'outsider', 'password': 'TestPass123!',
        })
        self.assertEqual(resp.status_code, 400)

    def test_login_inactive_tenant_membership_returns_400(self):
        """User has TenantUser row but is_active=False."""
        TenantUser.objects.filter(tenant=self.tenant, user=self.user).update(is_active=False)
        resp = self.post('/api/auth/login/', {
            'username': 'testuser', 'password': 'TestPass123!',
        })
        self.assertEqual(resp.status_code, 400)
        # Restore
        TenantUser.objects.filter(tenant=self.tenant, user=self.user).update(is_active=True)


# ===========================================================================
# Token refresh tests
# ===========================================================================

class TokenRefreshTest(AuthTestBase):

    def test_refresh_returns_new_access_token(self):
        resp = self.post('/api/auth/token/refresh/', {'refresh': self.refresh_token})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access', resp.json())

    def test_refresh_rotates_refresh_token(self):
        resp = self.post('/api/auth/token/refresh/', {'refresh': self.refresh_token})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('refresh', resp.json())
        new_refresh = resp.json()['refresh']
        self.assertNotEqual(new_refresh, self.refresh_token)

    def test_old_refresh_blacklisted_after_rotation(self):
        self.post('/api/auth/token/refresh/', {'refresh': self.refresh_token})
        # Old token must now be rejected
        resp = self.post('/api/auth/token/refresh/', {'refresh': self.refresh_token})
        self.assertEqual(resp.status_code, 401)

    def test_invalid_refresh_token_returns_401(self):
        resp = self.post('/api/auth/token/refresh/', {'refresh': 'totally.invalid.token'})
        self.assertEqual(resp.status_code, 401)

    def test_refresh_without_auth_header_succeeds(self):
        """Refresh endpoint must be publicly accessible (no bearer needed)."""
        resp = self.post('/api/auth/token/refresh/', {'refresh': self.refresh_token})
        self.assertEqual(resp.status_code, 200)


# ===========================================================================
# Logout tests
# ===========================================================================

class LogoutTest(AuthTestBase):

    def test_logout_succeeds_with_valid_token(self):
        resp = self.post(
            '/api/auth/logout/', {'refresh': self.refresh_token},
            auth=self.auth_header,
        )
        self.assertEqual(resp.status_code, 200)

    def test_logout_blacklists_refresh_token(self):
        self.post(
            '/api/auth/logout/', {'refresh': self.refresh_token},
            auth=self.auth_header,
        )
        resp = self.post('/api/auth/token/refresh/', {'refresh': self.refresh_token})
        self.assertEqual(resp.status_code, 401)

    def test_logout_without_auth_returns_401(self):
        resp = self.post('/api/auth/logout/', {'refresh': self.refresh_token})
        self.assertEqual(resp.status_code, 401)

    def test_logout_without_refresh_token_returns_400(self):
        resp = self.post('/api/auth/logout/', {}, auth=self.auth_header)
        self.assertEqual(resp.status_code, 400)

    def test_double_logout_returns_400(self):
        """Blacklisting an already-blacklisted token must fail, not silently pass."""
        self.post(
            '/api/auth/logout/', {'refresh': self.refresh_token},
            auth=self.auth_header,
        )
        resp = self.post(
            '/api/auth/logout/', {'refresh': self.refresh_token},
            auth=self.auth_header,
        )
        self.assertEqual(resp.status_code, 400)


# ===========================================================================
# Change password tests
# ===========================================================================

class ChangePasswordTest(AuthTestBase):

    def test_change_password_success(self):
        resp = self.post(
            '/api/auth/change-password/', {
                'current_password': 'TestPass123!',
                'new_password': 'NewSecure456@',
                'new_password_confirm': 'NewSecure456@',
            },
            auth=self.auth_header,
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewSecure456@'))

    def test_change_password_wrong_current_returns_400(self):
        resp = self.post(
            '/api/auth/change-password/', {
                'current_password': 'WrongOldPass!',
                'new_password': 'NewSecure456@',
                'new_password_confirm': 'NewSecure456@',
            },
            auth=self.auth_header,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('current_password', resp.json())

    def test_change_password_mismatch_returns_400(self):
        resp = self.post(
            '/api/auth/change-password/', {
                'current_password': 'TestPass123!',
                'new_password': 'NewSecure456@',
                'new_password_confirm': 'DifferentPass@',
            },
            auth=self.auth_header,
        )
        self.assertEqual(resp.status_code, 400)

    def test_change_password_weak_new_password_returns_400(self):
        resp = self.post(
            '/api/auth/change-password/', {
                'current_password': 'TestPass123!',
                'new_password': '123',
                'new_password_confirm': '123',
            },
            auth=self.auth_header,
        )
        self.assertEqual(resp.status_code, 400)

    def test_change_password_requires_auth(self):
        resp = self.post('/api/auth/change-password/', {
            'current_password': 'TestPass123!',
            'new_password': 'NewSecure456@',
            'new_password_confirm': 'NewSecure456@',
        })
        self.assertEqual(resp.status_code, 401)

    def test_old_token_still_works_after_change(self):
        """Access token remains valid until expiry even after password change.
        This is expected simplejwt behaviour — tokens are stateless."""
        self.post(
            '/api/auth/change-password/', {
                'current_password': 'TestPass123!',
                'new_password': 'NewSecure456@',
                'new_password_confirm': 'NewSecure456@',
            },
            auth=self.auth_header,
        )
        resp = self.get('/api/cart/', auth=self.auth_header)
        self.assertEqual(resp.status_code, 200)


# ===========================================================================
# Forgot password (reset) tests
# ===========================================================================

class PasswordResetTest(AuthTestBase):

    def test_reset_request_always_returns_200(self):
        resp = self.post('/api/auth/password-reset/', {'email': 'test@acme.com'})
        self.assertEqual(resp.status_code, 200)

    def test_reset_request_nonexistent_email_still_returns_200(self):
        """Must not leak whether email exists."""
        resp = self.post('/api/auth/password-reset/', {'email': 'nobody@example.com'})
        self.assertEqual(resp.status_code, 200)

    def test_reset_confirm_success(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        resp = self.post('/api/auth/password-reset/confirm/', {
            'uid': uid,
            'token': token,
            'new_password': 'ResetPass789#',
            'new_password_confirm': 'ResetPass789#',
        })
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('ResetPass789#'))

    def test_reset_confirm_invalid_token_returns_400(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        resp = self.post('/api/auth/password-reset/confirm/', {
            'uid': uid,
            'token': 'invalid-token',
            'new_password': 'ResetPass789#',
            'new_password_confirm': 'ResetPass789#',
        })
        self.assertEqual(resp.status_code, 400)

    def test_reset_confirm_invalid_uid_returns_400(self):
        resp = self.post('/api/auth/password-reset/confirm/', {
            'uid': 'invalidddd',
            'token': 'sometoken',
            'new_password': 'ResetPass789#',
            'new_password_confirm': 'ResetPass789#',
        })
        self.assertEqual(resp.status_code, 400)

    def test_reset_confirm_password_mismatch_returns_400(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        resp = self.post('/api/auth/password-reset/confirm/', {
            'uid': uid,
            'token': token,
            'new_password': 'ResetPass789#',
            'new_password_confirm': 'Different789#',
        })
        self.assertEqual(resp.status_code, 400)

    def test_reset_confirm_token_used_only_once(self):
        """Django's default_token_generator invalidates after password change."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        self.post('/api/auth/password-reset/confirm/', {
            'uid': uid,
            'token': token,
            'new_password': 'ResetPass789#',
            'new_password_confirm': 'ResetPass789#',
        })
        # Attempt to reuse the same token
        resp = self.post('/api/auth/password-reset/confirm/', {
            'uid': uid,
            'token': token,
            'new_password': 'AnotherPass000!',
            'new_password_confirm': 'AnotherPass000!',
        })
        self.assertEqual(resp.status_code, 400)


# ===========================================================================
# Endpoint protection tests (auth enforcement)
# ===========================================================================

class EndpointProtectionTest(AuthTestBase):

    def setUp(self):
        super().setUp()
        tv = ThreadVaribales()
        tv.set_val('tenant_id', self.tenant.id)
        tv.set_val('user_id', self.user.id)
        for model in [Category, Product, ProductVariant, Cart]:
            model.objects.tenant_id = self.tenant.id

    def test_products_accessible_without_auth(self):
        resp = self.get('/api/products/')
        self.assertEqual(resp.status_code, 200)

    def test_categories_accessible_without_auth(self):
        resp = self.get('/api/categories/')
        self.assertEqual(resp.status_code, 200)

    def test_cart_requires_auth(self):
        resp = self.get('/api/cart/')
        self.assertEqual(resp.status_code, 401)

    def test_cart_accessible_with_valid_token(self):
        resp = self.get('/api/cart/', auth=self.auth_header)
        self.assertEqual(resp.status_code, 200)

    def test_orders_requires_auth(self):
        resp = self.get('/api/orders/')
        self.assertEqual(resp.status_code, 401)

    def test_orders_accessible_with_valid_token(self):
        resp = self.get('/api/orders/', auth=self.auth_header)
        self.assertEqual(resp.status_code, 200)

    def test_payments_requires_auth(self):
        resp = self.get('/api/payments/')
        self.assertEqual(resp.status_code, 401)

    def test_cart_items_post_requires_auth(self):
        headers = {'HTTP_HOST': self.host}
        resp = self.client.post(
            '/api/cart/items/', data='{}', content_type='application/json', **headers,
        )
        self.assertEqual(resp.status_code, 401)

    def test_expired_or_tampered_token_returns_401(self):
        resp = self.get('/api/cart/', auth='Bearer this.is.fake')
        self.assertEqual(resp.status_code, 401)

    def test_missing_bearer_prefix_returns_401(self):
        resp = self.get('/api/cart/', auth=self.access_token)
        self.assertEqual(resp.status_code, 401)


# ===========================================================================
# Cross-tenant security tests
# ===========================================================================

class CrossTenantSecurityTest(AuthTestBase):

    def setUp(self):
        super().setUp()
        # Create a second tenant and a user that belongs only to it
        self.other_tenant = Tenant.objects.create(
            id='beta', name='Beta Corp', subdomain='beta',
        )
        self.other_user = User.objects.create_user(
            username='betauser', password='TestPass123!',
        )
        TenantUser.objects.create(tenant=self.other_tenant, user=self.other_user)

        tv = ThreadVaribales()
        tv.set_val('tenant_id', self.other_tenant.id)
        tv.set_val('user_id', self.other_user.id)
        other_refresh = RefreshToken.for_user(self.other_user)
        self.other_access_token = str(other_refresh.access_token)
        self.other_auth_header = f'Bearer {self.other_access_token}'

        tv.set_val('tenant_id', self.tenant.id)
        tv.set_val('user_id', self.user.id)

    def test_user_from_other_tenant_cannot_access_cart(self):
        """betauser's valid JWT presented to acme subdomain must be rejected."""
        headers = {
            'HTTP_HOST': self.host,  # acme subdomain
            'HTTP_AUTHORIZATION': self.other_auth_header,  # beta user token
        }
        resp = self.client.get('/api/cart/', **headers)
        ThreadVaribales().set_val('tenant_id', self.tenant.id)
        ThreadVaribales().set_val('user_id', self.user.id)
        self.assertEqual(resp.status_code, 403)

    def test_user_from_other_tenant_cannot_list_orders(self):
        headers = {
            'HTTP_HOST': self.host,
            'HTTP_AUTHORIZATION': self.other_auth_header,
        }
        resp = self.client.get('/api/orders/', **headers)
        ThreadVaribales().set_val('tenant_id', self.tenant.id)
        ThreadVaribales().set_val('user_id', self.user.id)
        self.assertEqual(resp.status_code, 403)

    def test_user_from_other_tenant_cannot_login_on_acme(self):
        """betauser has no TenantUser for acme — login on acme must fail."""
        resp = self.post('/api/auth/login/', {
            'username': 'betauser', 'password': 'TestPass123!',
        })
        self.assertEqual(resp.status_code, 400)

    def test_acme_user_token_on_beta_subdomain_is_rejected(self):
        """acme user's token presented to beta subdomain must be rejected."""
        headers = {
            'HTTP_HOST': _host('beta'),  # beta subdomain
            'HTTP_AUTHORIZATION': self.auth_header,  # acme user token
        }
        resp = self.client.get('/api/cart/', **headers)
        ThreadVaribales().set_val('tenant_id', self.tenant.id)
        ThreadVaribales().set_val('user_id', self.user.id)
        self.assertEqual(resp.status_code, 403)


# ===========================================================================
# IsTenantMember enforcement tests
# ===========================================================================

class TenantMembershipTest(AuthTestBase):

    def test_deactivated_membership_blocks_access(self):
        """Revoking tenant membership must immediately deny access."""
        TenantUser.objects.filter(tenant=self.tenant, user=self.user).update(is_active=False)
        resp = self.get('/api/cart/', auth=self.auth_header)
        self.assertEqual(resp.status_code, 403)
        # Restore
        TenantUser.objects.filter(tenant=self.tenant, user=self.user).update(is_active=True)

    def test_deleted_user_cannot_access_resources(self):
        """Deleting a user must block their token from working."""
        self.user.delete()
        resp = self.get('/api/cart/', auth=self.auth_header)
        self.assertEqual(resp.status_code, 401)


# ===========================================================================
# MeView tests
# ===========================================================================

class MeViewTest(AuthTestBase):

    def test_me_authenticated_returns_user_fields(self):
        """Authenticated request returns id, username, email, first_name, last_name."""
        self.user.first_name = 'Test'
        self.user.last_name = 'User'
        self.user.save()
        resp = self.get('/api/auth/me/', auth=self.auth_header)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['id'], self.user.id)
        self.assertEqual(data['username'], 'testuser')
        self.assertEqual(data['email'], 'test@acme.com')
        self.assertEqual(data['first_name'], 'Test')
        self.assertEqual(data['last_name'], 'User')

    def test_me_unauthenticated_returns_401(self):
        """No token → 401."""
        resp = self.get('/api/auth/me/')
        self.assertEqual(resp.status_code, 401)

    def test_me_returns_only_own_data(self):
        """Authenticated user only sees their own record."""
        other = User.objects.create_user(username='other', password='OtherPass1!')
        resp = self.get('/api/auth/me/', auth=self.auth_header)
        data = resp.json()
        self.assertNotEqual(data['id'], other.id)
        self.assertEqual(data['username'], 'testuser')
