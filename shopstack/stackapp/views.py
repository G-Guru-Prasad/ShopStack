from django.db import transaction
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from stackapp.models import Cart, CartItem, Category, Order, OrderItem, Payment, Product
from stackapp.serializers import (
    CartItemSerializer,
    CartSerializer,
    CategorySerializer,
    InitiatePaymentSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    PaymentSerializer,
    PlaceOrderSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
)
from stackapp.utils import ThreadVaribales


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    queryset = Category.objects.all()


class ProductListView(generics.ListAPIView):
    serializer_class = ProductListSerializer

    def get_queryset(self):
        qs = Product.objects.filter(is_active=True)
        category_id = self.request.query_params.get('category')
        if category_id:
            qs = qs.filter(category_id=category_id)
        return qs


class ProductDetailView(generics.RetrieveAPIView):
    serializer_class = ProductDetailSerializer

    def get_queryset(self):
        return Product.objects.filter(is_active=True).prefetch_related('variants')


class CartView(APIView):
    def _get_or_create_cart(self, user_id, tenant_id):
        cart = Cart.objects.filter(user_id=user_id, is_active=True).first()
        if not cart:
            cart = Cart.objects.create(user_id=user_id, tenant_id=tenant_id)
        return cart

    def get(self, request):
        user_id   = ThreadVaribales().get_val('user_id')
        tenant_id = ThreadVaribales().get_current_tenant_id()
        cart = self._get_or_create_cart(user_id, tenant_id)
        return Response(CartSerializer(cart).data)

    def post(self, request):
        user_id   = ThreadVaribales().get_val('user_id')
        tenant_id = ThreadVaribales().get_current_tenant_id()
        cart = self._get_or_create_cart(user_id, tenant_id)
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class CartItemCreateView(generics.CreateAPIView):
    serializer_class = CartItemSerializer

    def perform_create(self, serializer):
        user_id   = ThreadVaribales().get_val('user_id')
        tenant_id = ThreadVaribales().get_current_tenant_id()
        cart = Cart.objects.filter(user_id=user_id, is_active=True).first()
        serializer.save(cart=cart, tenant_id=tenant_id)


class CartItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class  = CartItemSerializer
    queryset          = CartItem.objects.all()
    http_method_names = ['patch', 'delete']


class OrderListCreateView(APIView):
    def get(self, request):
        orders = Order.objects.all().order_by('-placed_at')
        return Response(OrderListSerializer(orders, many=True).data)

    def post(self, request):
        serializer = PlaceOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id   = ThreadVaribales().get_val('user_id')
        tenant_id = ThreadVaribales().get_current_tenant_id()

        cart = Cart.objects.filter(user_id=user_id, is_active=True).first()
        if not cart:
            return Response({'detail': 'No active cart found.'}, status=status.HTTP_400_BAD_REQUEST)

        cart_items = CartItem.objects.filter(cart=cart).select_related('product_variant__product')
        if not cart_items.exists():
            return Response({'detail': 'Cart is empty.'}, status=status.HTTP_400_BAD_REQUEST)

        total = 0
        order_items_data = []
        for item in cart_items:
            variant    = item.product_variant
            unit_price = variant.product.price + variant.price_modifier
            total     += unit_price * item.quantity
            order_items_data.append({
                'product_variant': variant,
                'quantity':        item.quantity,
                'unit_price':      unit_price,
                'tenant_id':       tenant_id,
            })

        with transaction.atomic():
            order = Order.objects.create(
                cart_id      = cart.id,
                address_id   = serializer.validated_data['address_id'],
                total_amount = total,
                tenant_id    = tenant_id,
                status       = Order.Status.PENDING,
            )
            OrderItem.objects.bulk_create([
                OrderItem(order=order, **item_data)
                for item_data in order_items_data
            ])
            cart.is_active = False
            cart.save(update_fields=['is_active'])

        return Response(OrderDetailSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderDetailSerializer

    def get_queryset(self):
        return Order.objects.all().prefetch_related('items').select_related('address')


class PaymentListCreateView(APIView):
    def get(self, request):
        qs = Payment.objects.select_related('order').order_by('-created_at')
        order_id = request.query_params.get('order_id')
        if order_id:
            qs = qs.filter(order_id=order_id)
        return Response(PaymentSerializer(qs, many=True).data)

    def post(self, request):
        serializer = InitiatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payment = Payment.objects.create(
            order_id     = data['order_id'],
            amount       = data['amount'],
            method       = data['method'],
            reference_id = data.get('reference_id', ''),
            notes        = data.get('notes', ''),
            status       = Payment.Status.PENDING,
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
