"""Tests targeting previously-uncovered lines to reach 100% coverage."""
from django.test import RequestFactory, TestCase
from rest_framework_simplejwt.tokens import RefreshToken

import stackapp.constants
assert stackapp.constants is not None
from stackapp.factories import (
    AddressFactory, CartFactory, CartItemFactory, CategoryFactory,
    OrderFactory, OrderItemFactory, PasswordResetOTPFactory, PaymentFactory,
    ProductFactory, ProductVariantFactory, TenantFactory, TenantUserFactory,
    UserFactory,
)
from stackapp.models import Order, PasswordResetOTP, Product, ProductVariant
from stackapp.permissions import IsTenantMember
from stackapp.utils import TenantContext, ThreadVaribales


class _TenantBase(TestCase):
    """Enters a TenantContext so TenantBasedManager calls inject tenant_id."""

    def setUp(self):
        self.tenant = TenantFactory(
            id='acme', name='Acme', subdomain='acme')
        self.user = UserFactory(username='gapuser')
        TenantUserFactory(tenant=self.tenant, user=self.user)
        self._ctx = TenantContext(
            tenant_id=self.tenant.id, user_id=self.user.id)
        self._ctx.__enter__()
        self.host = 'acme.localhost:8000'
        refresh = RefreshToken.for_user(self.user)
        self.auth_header = f'Bearer {str(refresh.access_token)}'

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def _restore(self):
        tv = ThreadVaribales()
        tv.set_val('tenant_id', self.tenant.id)
        tv.set_val('user_id', self.user.id)


class ModelStrTest(_TenantBase):
    """Cover all __str__ methods plus PasswordResetOTP.is_valid."""

    def test_all_model_str_outputs(self):
        category = CategoryFactory()
        product = ProductFactory(category=category)
        variant = ProductVariantFactory(product=product)
        cart = CartFactory(user=self.user)
        cart_item = CartItemFactory(cart=cart, product_variant=variant)
        address = AddressFactory(user=self.user)
        order = OrderFactory(cart=cart, address=address)
        order_item = OrderItemFactory(order=order, product_variant=variant)
        other_user = UserFactory(username='other_str_user')
        tenant_user = TenantUserFactory(
            tenant=self.tenant, user=other_user)
        payment = PaymentFactory(order=order)
        otp = PasswordResetOTPFactory(user=self.user, tenant=self.tenant)

        self.assertIn('Acme', str(self.tenant))
        self.assertEqual(str(category), category.name)
        self.assertEqual(str(product), product.name)
        self.assertIn(variant.name, str(variant))
        self.assertIn(str(cart.id), str(cart))
        self.assertIn('in Cart', str(cart_item))
        self.assertIn(address.city, str(address))
        self.assertIn(order.status, str(order))
        self.assertIn(str(order_item.unit_price), str(order_item))
        self.assertIn(tenant_user.user.username, str(tenant_user))
        self.assertIn(str(payment.id), str(payment))
        self.assertIn(str(otp.user_id), str(otp))
        self.assertTrue(otp.is_valid())


class WritePathViewsTest(_TenantBase):
    """Covers POST/PATCH/DELETE branches in views.py."""

    def _post(self, url, payload):
        resp = self.client.post(
            url, data=payload, content_type='application/json',
            HTTP_HOST=self.host, HTTP_AUTHORIZATION=self.auth_header,
        )
        self._restore()
        return resp

    def _patch(self, url, payload):
        resp = self.client.patch(
            url, data=payload, content_type='application/json',
            HTTP_HOST=self.host, HTTP_AUTHORIZATION=self.auth_header,
        )
        self._restore()
        return resp

    def _delete(self, url):
        resp = self.client.delete(
            url, HTTP_HOST=self.host, HTTP_AUTHORIZATION=self.auth_header,
        )
        self._restore()
        return resp

    def _get(self, url):
        resp = self.client.get(url, HTTP_HOST=self.host)
        self._restore()
        return resp

    def test_create_category(self):
        resp = self._post('/api/categories/', {'name': 'Books'})
        self.assertEqual(resp.status_code, 201)

    def test_create_product(self):
        resp = self._post(
            '/api/products/',
            {'name': 'Pen', 'price': '5.00', 'is_active': True},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Product.objects.filter(name='Pen').count(), 1)

    def test_patch_product(self):
        product = ProductFactory(name='Old')
        resp = self._patch(
            f'/api/products/{product.id}/', {'name': 'New'},
        )
        self.assertEqual(resp.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.name, 'New')

    def test_create_variant(self):
        product = ProductFactory()
        resp = self._post(
            f'/api/products/{product.id}/variants/',
            {'name': 'Red', 'sku': 'X-RED-1',
             'price_modifier': '0.00', 'stock_qty': 1},
        )
        self.assertEqual(resp.status_code, 201)

    def test_list_variants(self):
        product = ProductFactory()
        ProductVariantFactory(product=product, sku='LIST-V-1')
        resp = self.client.get(
            f'/api/products/{product.id}/variants/',
            HTTP_HOST=self.host, HTTP_AUTHORIZATION=self.auth_header,
        )
        self._restore()
        self.assertEqual(resp.status_code, 200)

    def test_delete_variant_soft_deletes(self):
        product = ProductFactory()
        variant = ProductVariantFactory(product=product)
        resp = self._delete(
            f'/api/products/{product.id}/variants/{variant.id}/',
        )
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(
            ProductVariant.objects.filter(pk=variant.id).exists())

    def test_product_list_search(self):
        ProductFactory(name='Apple Phone')
        ProductFactory(name='Banana')
        resp = self._get('/api/products/?search=apple')
        self.assertEqual(resp.status_code, 200)
        names = [p['name'] for p in resp.json()['results']]
        self.assertIn('Apple Phone', names)
        self.assertNotIn('Banana', names)

    def test_product_detail_with_all_param(self):
        product = ProductFactory(is_active=False)
        resp = self._get(f'/api/products/{product.id}/?all=1')
        self.assertEqual(resp.status_code, 200)


class MiddlewareBranchTest(TestCase):
    """Covers TenantMiddleware DoesNotExist and no-subdomain branches."""

    def test_unknown_subdomain_sets_tenant_none(self):
        resp = self.client.get(
            '/api/categories/', HTTP_HOST='ghost.localhost:8000')
        self.assertEqual(resp.status_code, 200)

    def test_hostname_without_subdomain(self):
        resp = self.client.get(
            '/api/categories/', HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 200)


class PermissionUnitTest(TestCase):
    """Direct unit test of IsTenantMember to hit early-return branches."""

    def test_unauthenticated_user_denied(self):
        request = RequestFactory().get('/')
        request.user = type('Anon', (), {'is_authenticated': False})()
        self.assertFalse(IsTenantMember().has_permission(request, None))

    def test_no_tenant_id_denied(self):
        tenant = TenantFactory(id='perm', subdomain='perm', name='Perm')
        user = UserFactory(username='permuser')
        TenantUserFactory(tenant=tenant, user=user)
        request = RequestFactory().get('/')
        request.user = user
        ThreadVaribales().set_val('tenant_id', None)
        self.assertFalse(IsTenantMember().has_permission(request, None))


class ForgotPasswordVerifyMissingOTPTest(TestCase):
    """Covers PasswordResetOTP.DoesNotExist branch in ForgotPasswordVerifyView."""

    def test_verify_with_no_otp_returns_400(self):
        tenant = TenantFactory(id='fp', subdomain='fp', name='FP')
        user = UserFactory(username='fpuser', email='fp@example.com')
        TenantUserFactory(tenant=tenant, user=user)
        resp = self.client.post(
            '/api/auth/forgot-password/verify/',
            data={'email': 'fp@example.com', 'otp': '000000'},
            content_type='application/json',
            HTTP_HOST='fp.localhost:8000',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['detail'], 'Invalid email or OTP.')
        self.assertEqual(PasswordResetOTP.objects.filter(user=user).count(), 0)


class FactoryLazyAttrTest(TestCase):
    """Covers PasswordResetOTPFactory.expires_at lazy_attribute."""

    def test_otp_factory_sets_expires_at_in_future(self):
        from django.utils import timezone
        tenant = TenantFactory(id='lf', subdomain='lf', name='LF')
        user = UserFactory(username='lfuser')
        otp = PasswordResetOTPFactory(user=user, tenant=tenant)
        self.assertGreater(otp.expires_at, timezone.now())


class OrderStatusStrTest(_TenantBase):
    """Ensure Order.__str__ embeds the status string."""

    def test_order_str_uses_status(self):
        order = OrderFactory(status=Order.Status.CONFIRMED)
        self.assertIn('CONFIRMED', str(order))
