from django.contrib import admin

from stackapp.models import Address, Cart, CartItem, Category, Order, OrderItem, Product, ProductVariant, Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'subdomain', 'created_at')
    search_fields = ('subdomain', 'name')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'parent', 'tenant')
    search_fields = ('name',)
    list_filter = ('tenant',)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ('name', 'sku', 'price_modifier', 'stock_qty')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price', 'category', 'is_active', 'tenant')
    search_fields = ('name',)
    list_filter = ('is_active', 'tenant', 'category')
    inlines = [ProductVariantInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'sku', 'product', 'price_modifier', 'stock_qty', 'tenant')
    search_fields = ('name', 'sku')
    list_filter = ('tenant',)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ('product_variant', 'quantity')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'is_active', 'tenant')
    list_filter = ('is_active', 'tenant')
    search_fields = ('user__username',)
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'cart', 'product_variant', 'quantity')
    search_fields = ('cart__user__username', 'product_variant__name')


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'line1', 'city', 'country', 'is_default', 'tenant')
    search_fields = ('user__username', 'city', 'country')
    list_filter = ('country', 'is_default', 'tenant')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ('product_variant', 'quantity', 'unit_price')
    readonly_fields = ('product_variant', 'quantity', 'unit_price')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'cart', 'status', 'total_amount', 'placed_at', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('cart__user__username',)
    readonly_fields = ('cart', 'address', 'total_amount', 'placed_at')
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'product_variant', 'quantity', 'unit_price')
    search_fields = ('order__id', 'product_variant__name')
