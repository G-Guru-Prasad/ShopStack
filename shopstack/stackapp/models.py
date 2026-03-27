from django.conf import settings
from django.db import models

from stackapp.utils import TenantBasedManager


class Tenant(models.Model):
    id         = models.CharField(max_length=63, primary_key=True)
    name       = models.CharField(max_length=255)
    subdomain  = models.CharField(max_length=63, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tenants'

    def __str__(self):
        return f"{self.name} ({self.subdomain})"


class TenantBaseModel(models.Model):
    tenant      = models.ForeignKey(Tenant, on_delete=models.PROTECT, db_index=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True, db_index=True)
    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        related_name='+',
        on_delete=models.SET_NULL,
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        related_name='+',
        on_delete=models.SET_NULL,
    )

    objects = TenantBasedManager()

    class Meta:
        abstract = True


class Category(TenantBaseModel):
    name        = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    parent      = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='children',
    )

    class Meta:
        db_table = 'categories'
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Product(TenantBaseModel):
    name        = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    price       = models.DecimalField(max_digits=12, decimal_places=2)
    category    = models.ForeignKey(
        Category,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='products',
    )
    is_active   = models.BooleanField(default=True)

    class Meta:
        db_table = 'products'

    def __str__(self):
        return self.name


class ProductVariant(TenantBaseModel):
    product        = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants',
    )
    name           = models.CharField(max_length=255)
    sku            = models.CharField(max_length=100)
    price_modifier = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Added to the base product price. Can be negative for discounts.",
    )
    stock_qty      = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'product_variants'
        unique_together = [('tenant', 'sku')]

    def __str__(self):
        return f"{self.product.name} — {self.name}"


class Cart(TenantBaseModel):
    user      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'carts'

    def __str__(self):
        return f"Cart({self.id}) for user {self.user_id}"


class CartItem(TenantBaseModel):
    cart            = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='cart_items')
    quantity        = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'cart_items'
        unique_together = [('cart', 'product_variant')]

    def __str__(self):
        return f"{self.quantity}x {self.product_variant} in Cart {self.cart_id}"


class Address(TenantBaseModel):
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_index=True)
    line1      = models.CharField(max_length=255)
    line2      = models.CharField(max_length=255, blank=True, default='')
    city       = models.CharField(max_length=100)
    state      = models.CharField(max_length=100)
    country    = models.CharField(max_length=100)
    pincode    = models.CharField(max_length=20)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = 'addresses'

    def __str__(self):
        return f"{self.line1}, {self.city} ({self.user_id})"


class Order(TenantBaseModel):
    class Status(models.TextChoices):
        PENDING   = 'PENDING',   'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        SHIPPED   = 'SHIPPED',   'Shipped'
        DELIVERED = 'DELIVERED', 'Delivered'
        CANCELLED = 'CANCELLED', 'Cancelled'

    cart         = models.ForeignKey(Cart, on_delete=models.PROTECT, related_name='orders')
    address      = models.ForeignKey(Address, on_delete=models.PROTECT, related_name='orders')
    status       = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True,
    )
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    placed_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'orders'

    def __str__(self):
        return f"Order({self.id}) [{self.status}]"


class OrderItem(TenantBaseModel):
    order           = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name='order_items')
    quantity        = models.PositiveIntegerField()
    unit_price      = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = 'order_items'

    def __str__(self):
        return f"{self.quantity}x variant {self.product_variant_id} @ {self.unit_price}"


class TenantUser(models.Model):
    """Associates a Django User with a Tenant. A user may belong to multiple tenants."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='tenant_users')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tenant_memberships',
    )
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tenant_users'
        unique_together = [('tenant', 'user')]

    def __str__(self):
        return f"{self.user.username} @ {self.tenant_id}"


class Payment(TenantBaseModel):
    class Status(models.TextChoices):
        PENDING  = 'PENDING',  'Pending'
        PAID     = 'PAID',     'Paid'
        FAILED   = 'FAILED',   'Failed'
        REFUNDED = 'REFUNDED', 'Refunded'

    class Method(models.TextChoices):
        CASH          = 'CASH',          'Cash'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
        WALLET        = 'WALLET',        'Wallet'
        CREDIT_NOTE   = 'CREDIT_NOTE',   'Credit Note'

    order        = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='payments', db_index=True)
    amount       = models.DecimalField(max_digits=14, decimal_places=2)
    method       = models.CharField(max_length=20, choices=Method.choices)
    status       = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    reference_id = models.CharField(max_length=255, blank=True, default='', help_text='Internal reference or voucher number.')
    notes        = models.TextField(blank=True, default='')
    paid_at      = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'payments'

    def __str__(self):
        return f"Payment({self.id}) [{self.status}] for Order {self.order_id}"
