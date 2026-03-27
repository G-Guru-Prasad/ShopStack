from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from stackapp.models import (
    Address, Cart, CartItem, Category, Order, OrderItem,
    Payment, Product, ProductVariant, Tenant, TenantUser,
)
from stackapp.utils import ThreadVaribales


class APITestBase(TestCase):
    """Base class with common tenant / user / JWT / thread-local setup."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            id='acme', name='Acme Corp', subdomain='acme',
        )
        self.user = User.objects.create_user(
            username='testuser', password='testpass',
        )
        TenantUser.objects.create(tenant=self.tenant, user=self.user)

        # Set thread-local so TenantBasedManager works during data setup
        tv = ThreadVaribales()
        tv.set_val('tenant_id', self.tenant.id)
        tv.set_val('user_id', self.user.id)

        self.host = 'acme.localhost:8000'

        # TenantBasedManager caches tenant_id at class-definition time
        # (in __init__), so bulk_create's add_tenant_id uses a stale
        # value. Patch it for all tenant-scoped models used in tests.
        for model in [Category, Product, ProductVariant, Cart, CartItem,
                      Address, Order, OrderItem, Payment]:
            model.objects.tenant_id = self.tenant.id

        # Generate JWT access token for authenticated requests
        refresh = RefreshToken.for_user(self.user)
        self.access_token = str(refresh.access_token)
        self.auth_header = f'Bearer {self.access_token}'

    # ------------------------------------------------------------------
    # Helpers that inject HTTP_HOST and Authorization header.
    # Thread-local values are restored after each call because middleware
    # cleanup wipes them at the end of the request.
    # ------------------------------------------------------------------
    def _restore_thread_locals(self):
        tv = ThreadVaribales()
        tv.set_val('tenant_id', self.tenant.id)
        tv.set_val('user_id', self.user.id)

    def api_get(self, url, data=None):
        resp = self.client.get(
            url, data=data, HTTP_HOST=self.host,
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self._restore_thread_locals()
        return resp

    def api_post(self, url, data=None, fmt='json'):
        resp = self.client.post(
            url, data=data, content_type='application/json',
            HTTP_HOST=self.host,
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self._restore_thread_locals()
        return resp

    def api_patch(self, url, data=None):
        resp = self.client.patch(
            url, data=data, content_type='application/json',
            HTTP_HOST=self.host,
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self._restore_thread_locals()
        return resp

    def api_delete(self, url):
        resp = self.client.delete(
            url, HTTP_HOST=self.host,
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self._restore_thread_locals()
        return resp


# ======================================================================
# Category API
# ======================================================================
class CategoryAPITest(APITestBase):

    def setUp(self):
        super().setUp()
        self.cat_parent = Category.objects.create(
            name='Electronics', description='Electronic gadgets',
        )
        self.cat_child = Category.objects.create(
            name='Phones', description='Mobile phones',
            parent=self.cat_parent,
        )

    def test_list_categories_status(self):
        resp = self.api_get('/api/categories/')
        self.assertEqual(resp.status_code, 200)

    def test_list_categories_paginated_format(self):
        resp = self.api_get('/api/categories/')
        data = resp.json()
        self.assertIn('count', data)
        self.assertIn('results', data)
        self.assertEqual(data['count'], 2)

    def test_list_categories_fields(self):
        resp = self.api_get('/api/categories/')
        item = resp.json()['results'][0]
        expected_keys = {'id', 'name', 'description', 'parent'}
        self.assertEqual(set(item.keys()), expected_keys)

    def test_list_categories_parent_child(self):
        resp = self.api_get('/api/categories/')
        results = resp.json()['results']
        by_id = {c['id']: c for c in results}
        self.assertIsNone(by_id[self.cat_parent.id]['parent'])
        self.assertEqual(
            by_id[self.cat_child.id]['parent'], self.cat_parent.id,
        )


# ======================================================================
# Product API
# ======================================================================
class ProductAPITest(APITestBase):

    def setUp(self):
        super().setUp()
        self.category = Category.objects.create(name='Gadgets')
        self.product_active = Product.objects.create(
            name='Widget', description='A fine widget',
            price=Decimal('99.99'), category=self.category,
            is_active=True,
        )
        self.product_inactive = Product.objects.create(
            name='Old Widget', price=Decimal('49.99'), is_active=False,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product_active, name='Red',
            sku='WGT-RED', price_modifier=Decimal('10.00'),
            stock_qty=50,
        )

    # -- Product list --------------------------------------------------

    def test_product_list_status(self):
        resp = self.api_get('/api/products/')
        self.assertEqual(resp.status_code, 200)

    def test_product_list_excludes_inactive(self):
        resp = self.api_get('/api/products/')
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['id'], self.product_active.id)

    def test_product_list_fields(self):
        resp = self.api_get('/api/products/')
        item = resp.json()['results'][0]
        expected_keys = {'id', 'name', 'description', 'price',
                         'category', 'is_active'}
        self.assertEqual(set(item.keys()), expected_keys)

    def test_product_list_values(self):
        resp = self.api_get('/api/products/')
        item = resp.json()['results'][0]
        self.assertEqual(item['name'], 'Widget')
        self.assertEqual(item['price'], '99.99')
        self.assertEqual(item['category'], self.category.id)
        self.assertTrue(item['is_active'])

    def test_product_list_filter_by_category(self):
        resp = self.api_get('/api/products/',
                            data={'category': self.category.id})
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['id'], self.product_active.id)

    def test_product_list_filter_by_nonexistent_category(self):
        resp = self.api_get('/api/products/', data={'category': 99999})
        data = resp.json()
        self.assertEqual(data['count'], 0)

    # -- Product detail ------------------------------------------------

    def test_product_detail_status(self):
        resp = self.api_get(f'/api/products/{self.product_active.id}/')
        self.assertEqual(resp.status_code, 200)

    def test_product_detail_fields(self):
        resp = self.api_get(f'/api/products/{self.product_active.id}/')
        data = resp.json()
        expected_keys = {'id', 'name', 'description', 'price',
                         'category', 'is_active', 'variants'}
        self.assertEqual(set(data.keys()), expected_keys)

    def test_product_detail_variants(self):
        resp = self.api_get(f'/api/products/{self.product_active.id}/')
        data = resp.json()
        self.assertEqual(len(data['variants']), 1)
        v = data['variants'][0]
        expected_variant_keys = {'id', 'name', 'sku', 'price_modifier',
                                 'stock_qty', 'effective_price'}
        self.assertEqual(set(v.keys()), expected_variant_keys)
        self.assertEqual(v['name'], 'Red')
        self.assertEqual(v['sku'], 'WGT-RED')
        self.assertEqual(v['price_modifier'], '10.00')
        self.assertEqual(v['stock_qty'], 50)
        # effective_price = product.price + price_modifier = 99.99 + 10.00
        self.assertEqual(Decimal(str(v['effective_price'])),
                         Decimal('109.99'))

    def test_product_detail_inactive_returns_404(self):
        resp = self.api_get(f'/api/products/{self.product_inactive.id}/')
        self.assertEqual(resp.status_code, 404)

    def test_product_detail_nonexistent_returns_404(self):
        resp = self.api_get('/api/products/99999/')
        self.assertEqual(resp.status_code, 404)


# ======================================================================
# Cart API
# ======================================================================
class CartAPITest(APITestBase):

    def test_get_cart_creates_new(self):
        resp = self.api_get('/api/cart/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        expected_keys = {'id', 'user_id', 'is_active', 'items'}
        self.assertEqual(set(data.keys()), expected_keys)
        self.assertEqual(data['user_id'], self.user.id)
        self.assertTrue(data['is_active'])
        self.assertEqual(data['items'], [])

    def test_get_cart_returns_existing(self):
        cart = Cart.objects.create(user=self.user, is_active=True)
        resp = self.api_get('/api/cart/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], cart.id)

    def test_post_cart_creates_or_returns(self):
        resp = self.api_post('/api/cart/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        expected_keys = {'id', 'user_id', 'is_active', 'items'}
        self.assertEqual(set(data.keys()), expected_keys)
        self.assertTrue(data['is_active'])

    def test_post_cart_returns_existing(self):
        cart = Cart.objects.create(user=self.user, is_active=True)
        resp = self.api_post('/api/cart/')
        self.assertEqual(resp.json()['id'], cart.id)


# ======================================================================
# CartItem API
# ======================================================================
class CartItemAPITest(APITestBase):

    def setUp(self):
        super().setUp()
        self.product = Product.objects.create(
            name='Gadget', price=Decimal('50.00'), is_active=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, name='Default',
            sku='GDG-DEF', price_modifier=Decimal('0.00'),
            stock_qty=100,
        )
        self.cart = Cart.objects.create(user=self.user, is_active=True)

    # -- Add item ------------------------------------------------------

    def test_add_cart_item_status(self):
        resp = self.api_post('/api/cart/items/', {
            'product_variant': self.variant.id,
            'quantity': 2,
        })
        self.assertEqual(resp.status_code, 201)

    def test_add_cart_item_fields(self):
        resp = self.api_post('/api/cart/items/', {
            'product_variant': self.variant.id,
            'quantity': 3,
        })
        data = resp.json()
        expected_keys = {'id', 'product_variant', 'quantity'}
        self.assertEqual(set(data.keys()), expected_keys)
        self.assertEqual(data['product_variant'], self.variant.id)
        self.assertEqual(data['quantity'], 3)

    def test_add_cart_item_shows_in_cart(self):
        self.api_post('/api/cart/items/', {
            'product_variant': self.variant.id,
            'quantity': 1,
        })
        resp = self.api_get('/api/cart/')
        items = resp.json()['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['product_variant'], self.variant.id)

    # -- Update item ---------------------------------------------------

    def test_update_cart_item_quantity(self):
        item = CartItem.objects.create(
            cart=self.cart, product_variant=self.variant, quantity=1,
        )
        resp = self.api_patch(f'/api/cart/items/{item.id}/', {
            'quantity': 5,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['quantity'], 5)
        self.assertEqual(data['product_variant'], self.variant.id)

    # -- Delete item ---------------------------------------------------

    def test_delete_cart_item(self):
        item = CartItem.objects.create(
            cart=self.cart, product_variant=self.variant, quantity=1,
        )
        resp = self.api_delete(f'/api/cart/items/{item.id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(CartItem.objects.filter(pk=item.id).exists())

    # -- Disallowed methods --------------------------------------------

    def test_get_cart_item_not_allowed(self):
        item = CartItem.objects.create(
            cart=self.cart, product_variant=self.variant, quantity=1,
        )
        resp = self.api_get(f'/api/cart/items/{item.id}/')
        self.assertEqual(resp.status_code, 405)

    def test_delete_nonexistent_cart_item(self):
        resp = self.api_delete('/api/cart/items/99999/')
        self.assertEqual(resp.status_code, 404)


# ======================================================================
# Order API
# ======================================================================
class OrderAPITest(APITestBase):

    def setUp(self):
        super().setUp()
        self.product = Product.objects.create(
            name='Widget', price=Decimal('100.00'), is_active=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, name='Blue',
            sku='WGT-BLU', price_modifier=Decimal('5.00'),
            stock_qty=20,
        )
        self.address = Address.objects.create(
            user=self.user, line1='123 Main St', city='Springfield',
            state='IL', country='US', pincode='62701',
        )
        self.cart = Cart.objects.create(user=self.user, is_active=True)
        self.cart_item = CartItem.objects.create(
            cart=self.cart, product_variant=self.variant, quantity=2,
        )

    # -- Place order ---------------------------------------------------

    def test_place_order_status(self):
        resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        self.assertEqual(resp.status_code, 201)

    def test_place_order_response_format(self):
        resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        data = resp.json()
        expected_keys = {'id', 'cart', 'address', 'status',
                         'total_amount', 'placed_at', 'items'}
        self.assertEqual(set(data.keys()), expected_keys)

    def test_place_order_values(self):
        resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        data = resp.json()
        self.assertEqual(data['status'], 'PENDING')
        # total = (100 + 5) * 2 = 210
        self.assertEqual(data['total_amount'], '210.00')
        self.assertEqual(data['cart'], self.cart.id)

    def test_place_order_items(self):
        resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        items = resp.json()['items']
        self.assertEqual(len(items), 1)
        item = items[0]
        expected_item_keys = {'id', 'product_variant', 'quantity',
                              'unit_price'}
        self.assertEqual(set(item.keys()), expected_item_keys)
        self.assertEqual(item['product_variant'], self.variant.id)
        self.assertEqual(item['quantity'], 2)
        self.assertEqual(item['unit_price'], '105.00')

    def test_place_order_address_nested(self):
        resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        addr = resp.json()['address']
        expected_addr_keys = {'id', 'user_id', 'line1', 'line2', 'city',
                              'state', 'country', 'pincode', 'is_default'}
        self.assertEqual(set(addr.keys()), expected_addr_keys)
        self.assertEqual(addr['line1'], '123 Main St')
        self.assertEqual(addr['city'], 'Springfield')

    def test_place_order_deactivates_cart(self):
        self.api_post('/api/orders/', {'address_id': self.address.id})
        self.cart.refresh_from_db()
        self.assertFalse(self.cart.is_active)

    def test_place_order_no_active_cart(self):
        self.cart.is_active = False
        self.cart.save(update_fields=['is_active'])
        resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('detail', resp.json())

    def test_place_order_empty_cart(self):
        self.cart_item.delete()
        resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('detail', resp.json())

    def test_place_order_invalid_address(self):
        resp = self.api_post('/api/orders/', {
            'address_id': 99999,
        })
        self.assertEqual(resp.status_code, 400)

    def test_place_order_missing_address(self):
        resp = self.api_post('/api/orders/', {})
        self.assertEqual(resp.status_code, 400)

    # -- List orders ---------------------------------------------------

    def test_list_orders_empty(self):
        resp = self.api_get('/api/orders/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_list_orders_format(self):
        self.api_post('/api/orders/', {'address_id': self.address.id})
        resp = self.api_get('/api/orders/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        expected_keys = {'id', 'status', 'total_amount', 'placed_at'}
        self.assertEqual(set(data[0].keys()), expected_keys)

    def test_list_orders_values(self):
        self.api_post('/api/orders/', {'address_id': self.address.id})
        resp = self.api_get('/api/orders/')
        order = resp.json()[0]
        self.assertEqual(order['status'], 'PENDING')
        self.assertEqual(order['total_amount'], '210.00')
        self.assertIsNotNone(order['placed_at'])

    # -- Order detail --------------------------------------------------

    def test_order_detail_status(self):
        create_resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        order_id = create_resp.json()['id']
        resp = self.api_get(f'/api/orders/{order_id}/')
        self.assertEqual(resp.status_code, 200)

    def test_order_detail_format(self):
        create_resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        order_id = create_resp.json()['id']
        resp = self.api_get(f'/api/orders/{order_id}/')
        data = resp.json()
        expected_keys = {'id', 'cart', 'address', 'status',
                         'total_amount', 'placed_at', 'items'}
        self.assertEqual(set(data.keys()), expected_keys)
        self.assertIsInstance(data['items'], list)
        self.assertIsInstance(data['address'], dict)

    def test_order_detail_nonexistent(self):
        resp = self.api_get('/api/orders/99999/')
        self.assertEqual(resp.status_code, 404)


# ======================================================================
# Payment API
# ======================================================================
class PaymentAPITest(APITestBase):

    def setUp(self):
        super().setUp()
        self.product = Product.objects.create(
            name='Item', price=Decimal('200.00'), is_active=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, name='Std',
            sku='ITM-STD', price_modifier=Decimal('0.00'),
            stock_qty=10,
        )
        self.address = Address.objects.create(
            user=self.user, line1='456 Oak Ave', city='Shelbyville',
            state='IL', country='US', pincode='62565',
        )
        # Create a placed order
        self.cart = Cart.objects.create(user=self.user, is_active=True)
        CartItem.objects.create(
            cart=self.cart, product_variant=self.variant, quantity=1,
        )
        resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        self.order_id = resp.json()['id']

    # -- Create payment ------------------------------------------------

    def test_create_payment_status(self):
        resp = self.api_post('/api/payments/', {
            'order_id': self.order_id,
            'amount': '200.00',
            'method': 'CASH',
        })
        self.assertEqual(resp.status_code, 201)

    def test_create_payment_response_format(self):
        resp = self.api_post('/api/payments/', {
            'order_id': self.order_id,
            'amount': '200.00',
            'method': 'CASH',
        })
        data = resp.json()
        expected_keys = {'id', 'order', 'amount', 'method', 'status',
                         'reference_id', 'notes', 'paid_at', 'created_at'}
        self.assertEqual(set(data.keys()), expected_keys)

    def test_create_payment_values(self):
        resp = self.api_post('/api/payments/', {
            'order_id': self.order_id,
            'amount': '200.00',
            'method': 'BANK_TRANSFER',
            'reference_id': 'REF-001',
            'notes': 'Test note',
        })
        data = resp.json()
        self.assertEqual(data['order'], self.order_id)
        self.assertEqual(data['amount'], '200.00')
        self.assertEqual(data['method'], 'BANK_TRANSFER')
        self.assertEqual(data['status'], 'PENDING')
        self.assertEqual(data['reference_id'], 'REF-001')
        self.assertEqual(data['notes'], 'Test note')
        self.assertIsNone(data['paid_at'])
        self.assertIsNotNone(data['created_at'])

    def test_create_payment_wallet_method(self):
        resp = self.api_post('/api/payments/', {
            'order_id': self.order_id,
            'amount': '100.00',
            'method': 'WALLET',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['method'], 'WALLET')

    def test_create_payment_credit_note_method(self):
        resp = self.api_post('/api/payments/', {
            'order_id': self.order_id,
            'amount': '50.00',
            'method': 'CREDIT_NOTE',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['method'], 'CREDIT_NOTE')

    def test_create_payment_invalid_order(self):
        resp = self.api_post('/api/payments/', {
            'order_id': 99999,
            'amount': '100.00',
            'method': 'CASH',
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_payment_invalid_method(self):
        resp = self.api_post('/api/payments/', {
            'order_id': self.order_id,
            'amount': '100.00',
            'method': 'BITCOIN',
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_payment_missing_fields(self):
        resp = self.api_post('/api/payments/', {})
        self.assertEqual(resp.status_code, 400)

    def test_create_payment_cancelled_order(self):
        order = Order.objects.get(pk=self.order_id)
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status'])
        resp = self.api_post('/api/payments/', {
            'order_id': self.order_id,
            'amount': '200.00',
            'method': 'CASH',
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_payment_duplicate_paid(self):
        Payment.objects.create(
            order_id=self.order_id,
            amount=Decimal('200.00'),
            method=Payment.Method.CASH,
            status=Payment.Status.PAID,
        )
        resp = self.api_post('/api/payments/', {
            'order_id': self.order_id,
            'amount': '200.00',
            'method': 'CASH',
        })
        self.assertEqual(resp.status_code, 400)

    # -- List payments -------------------------------------------------

    def test_list_payments_empty(self):
        resp = self.api_get('/api/payments/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_list_payments_format(self):
        self.api_post('/api/payments/', {
            'order_id': self.order_id,
            'amount': '200.00',
            'method': 'CASH',
        })
        resp = self.api_get('/api/payments/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        expected_keys = {'id', 'order', 'amount', 'method', 'status',
                         'reference_id', 'notes', 'paid_at', 'created_at'}
        self.assertEqual(set(data[0].keys()), expected_keys)

    def test_list_payments_filter_by_order(self):
        self.api_post('/api/payments/', {
            'order_id': self.order_id,
            'amount': '200.00',
            'method': 'CASH',
        })
        resp = self.api_get('/api/payments/',
                            data={'order_id': self.order_id})
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['order'], self.order_id)

    def test_list_payments_filter_nonexistent_order(self):
        self.api_post('/api/payments/', {
            'order_id': self.order_id,
            'amount': '200.00',
            'method': 'CASH',
        })
        resp = self.api_get('/api/payments/', data={'order_id': 99999})
        self.assertEqual(resp.json(), [])


# ======================================================================
# Order with multiple items
# ======================================================================
class OrderMultipleItemsTest(APITestBase):
    """Verify order placement with multiple cart items and correct
    total calculation."""

    def setUp(self):
        super().setUp()
        self.product = Product.objects.create(
            name='Shoe', price=Decimal('80.00'), is_active=True,
        )
        self.variant_a = ProductVariant.objects.create(
            product=self.product, name='Size 10',
            sku='SHOE-10', price_modifier=Decimal('0.00'),
            stock_qty=10,
        )
        self.variant_b = ProductVariant.objects.create(
            product=self.product, name='Size 12',
            sku='SHOE-12', price_modifier=Decimal('5.00'),
            stock_qty=10,
        )
        self.address = Address.objects.create(
            user=self.user, line1='789 Elm St', city='Capital City',
            state='IL', country='US', pincode='62700',
        )
        self.cart = Cart.objects.create(user=self.user, is_active=True)
        CartItem.objects.create(
            cart=self.cart, product_variant=self.variant_a, quantity=1,
        )
        CartItem.objects.create(
            cart=self.cart, product_variant=self.variant_b, quantity=3,
        )

    def test_order_total_multiple_items(self):
        resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        self.assertEqual(resp.status_code, 201)
        # variant_a: (80 + 0) * 1  = 80
        # variant_b: (80 + 5) * 3  = 255
        # total = 335
        self.assertEqual(resp.json()['total_amount'], '335.00')

    def test_order_items_count(self):
        resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        self.assertEqual(len(resp.json()['items']), 2)

    def test_order_unit_prices_snapshot(self):
        resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        items = resp.json()['items']
        prices = {i['product_variant']: i['unit_price'] for i in items}
        self.assertEqual(prices[self.variant_a.id], '80.00')
        self.assertEqual(prices[self.variant_b.id], '85.00')


# ======================================================================
# created_by audit field
# ======================================================================
class CreatedByAuditTest(APITestBase):
    """Verify that created_by is populated for every tenant-scoped model."""

    def setUp(self):
        super().setUp()
        self.category = Category.objects.create(name='Audit Cat')
        self.product = Product.objects.create(
            name='Audit Prod', price=Decimal('10.00'), is_active=True,
            category=self.category,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, name='V1',
            sku='AUD-V1', price_modifier=Decimal('0.00'),
            stock_qty=5,
        )
        self.address = Address.objects.create(
            user=self.user, line1='1 Audit Ln', city='AuditCity',
            state='ST', country='US', pincode='00000',
        )
        self.cart = Cart.objects.create(user=self.user, is_active=True)
        self.cart_item = CartItem.objects.create(
            cart=self.cart, product_variant=self.variant, quantity=1,
        )

    # -- ORM-created objects (via TenantBasedManager.create) -----------

    def test_category_created_by(self):
        self.assertIsNotNone(self.category.created_by)
        self.assertEqual(self.category.created_by_id, self.user.id)

    def test_product_created_by(self):
        self.assertIsNotNone(self.product.created_by)
        self.assertEqual(self.product.created_by_id, self.user.id)

    def test_product_variant_created_by(self):
        self.assertIsNotNone(self.variant.created_by)
        self.assertEqual(self.variant.created_by_id, self.user.id)

    def test_address_created_by(self):
        self.assertIsNotNone(self.address.created_by)
        self.assertEqual(self.address.created_by_id, self.user.id)

    def test_cart_created_by(self):
        self.assertIsNotNone(self.cart.created_by)
        self.assertEqual(self.cart.created_by_id, self.user.id)

    def test_cart_item_created_by(self):
        self.assertIsNotNone(self.cart_item.created_by)
        self.assertEqual(self.cart_item.created_by_id, self.user.id)

    # -- API-created objects -------------------------------------------

    def test_cart_created_by_via_api(self):
        Cart.objects.filter(user=self.user).delete()
        self.api_get('/api/cart/')
        cart = Cart.objects.get(user=self.user, is_active=True)
        self.assertIsNotNone(cart.created_by)
        self.assertEqual(cart.created_by_id, self.user.id)

    def test_cart_item_created_by_via_api(self):
        variant2 = ProductVariant.objects.create(
            product=self.product, name='V2',
            sku='AUD-V2', price_modifier=Decimal('1.00'),
            stock_qty=10,
        )
        self.api_post('/api/cart/items/', {
            'product_variant': variant2.id,
            'quantity': 1,
        })
        item = CartItem.objects.get(product_variant=variant2)
        self.assertIsNotNone(item.created_by)
        self.assertEqual(item.created_by_id, self.user.id)

    def test_order_created_by_via_api(self):
        resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        order = Order.objects.get(pk=resp.json()['id'])
        self.assertIsNotNone(order.created_by)
        self.assertEqual(order.created_by_id, self.user.id)

    def test_order_item_created_by_via_api(self):
        resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        order_items = OrderItem.objects.filter(order_id=resp.json()['id'])
        for oi in order_items:
            self.assertIsNotNone(oi.created_by,
                                 f'OrderItem {oi.id} has null created_by')
            self.assertEqual(oi.created_by_id, self.user.id)

    def test_payment_created_by_via_api(self):
        order_resp = self.api_post('/api/orders/', {
            'address_id': self.address.id,
        })
        order_id = order_resp.json()['id']
        pay_resp = self.api_post('/api/payments/', {
            'order_id': order_id,
            'amount': '10.00',
            'method': 'CASH',
        })
        payment = Payment.objects.get(pk=pay_resp.json()['id'])
        self.assertIsNotNone(payment.created_by)
        self.assertEqual(payment.created_by_id, self.user.id)
