"""factory_boy fixtures for stackapp models.

Tenant-scoped factories rely on TenantContext being active so that
TenantBasedManager.create() injects the correct tenant_id and audit
fields. Tests should either wrap factory calls in a `with TenantContext(...)`
block, or use a base test class that enters a context in setUp().
"""
from decimal import Decimal

import factory
from django.contrib.auth.models import User

from stackapp.models import (
    Address, Cart, CartItem, Category, Order, OrderItem, Payment,
    PasswordResetOTP, Product, ProductVariant, Tenant, TenantUser,
)


class TenantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tenant
        django_get_or_create = ('id',)

    id = factory.Sequence(lambda n: f'tenant{n}')
    name = factory.LazyAttribute(lambda o: f'Tenant {o.id}')
    subdomain = factory.LazyAttribute(lambda o: o.id)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f'user{n}')
    email = factory.LazyAttribute(lambda o: f'{o.username}@example.com')

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop('password', 'TestPass123!')
        manager = cls._get_manager(model_class)
        return manager.create_user(*args, password=password, **kwargs)


class TenantUserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TenantUser
        django_get_or_create = ('tenant', 'user')

    tenant = factory.SubFactory(TenantFactory)
    user = factory.SubFactory(UserFactory)
    is_active = True


class PasswordResetOTPFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PasswordResetOTP

    user = factory.SubFactory(UserFactory)
    tenant = factory.SubFactory(TenantFactory)
    otp = factory.Sequence(lambda n: f'{n:06d}')

    @factory.lazy_attribute
    def expires_at(self):
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() + timedelta(minutes=15)


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f'Category {n}')
    description = ''


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    name = factory.Sequence(lambda n: f'Product {n}')
    description = ''
    price = Decimal('100.00')
    is_active = True


class ProductVariantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductVariant

    product = factory.SubFactory(ProductFactory)
    name = factory.Sequence(lambda n: f'Variant {n}')
    sku = factory.Sequence(lambda n: f'SKU-{n}')
    price_modifier = Decimal('0.00')
    stock_qty = 10


class CartFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Cart

    user = factory.SubFactory(UserFactory)
    is_active = True


class CartItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CartItem

    cart = factory.SubFactory(CartFactory)
    product_variant = factory.SubFactory(ProductVariantFactory)
    quantity = 1


class AddressFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Address

    user = factory.SubFactory(UserFactory)
    line1 = factory.Sequence(lambda n: f'{n} Main St')
    city = 'Springfield'
    state = 'IL'
    country = 'US'
    pincode = '62701'


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    cart = factory.SubFactory(CartFactory)
    address = factory.SubFactory(AddressFactory)
    status = Order.Status.PENDING
    total_amount = Decimal('0.00')


class OrderItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    product_variant = factory.SubFactory(ProductVariantFactory)
    quantity = 1
    unit_price = Decimal('100.00')


class PaymentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Payment

    order = factory.SubFactory(OrderFactory)
    amount = Decimal('100.00')
    method = Payment.Method.CASH
    status = Payment.Status.PENDING
