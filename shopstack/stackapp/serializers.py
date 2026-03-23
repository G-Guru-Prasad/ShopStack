from rest_framework import serializers

from stackapp.models import Address, Cart, CartItem, Category, Order, OrderItem, Payment, Product, ProductVariant


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'parent']


class ProductVariantSerializer(serializers.ModelSerializer):
    effective_price = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = ['id', 'name', 'sku', 'price_modifier', 'stock_qty', 'effective_price']

    def get_effective_price(self, obj):
        return obj.product.price + obj.price_modifier


class ProductListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'price', 'category', 'is_active']


class ProductDetailSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'price', 'category', 'is_active', 'variants']


class CartItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = ['id', 'product_variant', 'quantity']


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'user_id', 'is_active', 'items']


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ['id', 'user_id', 'line1', 'line2', 'city', 'state', 'country', 'pincode', 'is_default']


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'product_variant', 'quantity', 'unit_price']


class OrderListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['id', 'status', 'total_amount', 'placed_at']


class OrderDetailSerializer(serializers.ModelSerializer):
    items   = OrderItemSerializer(many=True, read_only=True)
    address = AddressSerializer(read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'cart', 'address', 'status', 'total_amount', 'placed_at', 'items']


class PlaceOrderSerializer(serializers.Serializer):
    address_id = serializers.IntegerField()

    def validate_address_id(self, value):
        if not Address.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Address not found.")
        return value


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'order', 'amount', 'method', 'status', 'reference_id', 'notes', 'paid_at', 'created_at']


class InitiatePaymentSerializer(serializers.Serializer):
    order_id     = serializers.IntegerField()
    amount       = serializers.DecimalField(max_digits=14, decimal_places=2)
    method       = serializers.ChoiceField(choices=Payment.Method.choices)
    reference_id = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    notes        = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_order_id(self, value):
        if not Order.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Order not found.")
        return value

    def validate(self, attrs):
        order = Order.objects.get(pk=attrs['order_id'])
        if order.status == Order.Status.CANCELLED:
            raise serializers.ValidationError("Cannot initiate payment for a cancelled order.")
        if Payment.objects.filter(order_id=attrs['order_id'], status=Payment.Status.PAID).exists():
            raise serializers.ValidationError("A confirmed payment already exists for this order.")
        return attrs
