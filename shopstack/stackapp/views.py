from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from stackapp.models import Cart, CartItem, Category, Order, OrderItem, Payment, Product, ProductVariant
from stackapp.permissions import IsTenantMember
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
    ProductVariantSerializer,
)
from stackapp.utils import ThreadVaribales


class CategoryListCreateView(generics.ListCreateAPIView):
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated(), IsTenantMember()]

    def get_queryset(self):
        return Category.objects.all()

    def perform_create(self, serializer):
        tenant_id = ThreadVaribales().get_current_tenant_id()
        user_id = ThreadVaribales().get_val('user_id')
        serializer.save(tenant_id=tenant_id, created_by_id=user_id)


class ProductListCreateView(generics.ListCreateAPIView):
    serializer_class = ProductListSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated(), IsTenantMember()]

    def get_queryset(self):
        qs = Product.objects.all()
        if not self.request.query_params.get('all'):
            qs = qs.filter(is_active=True)
        category_id = self.request.query_params.get('category')
        if category_id:
            qs = qs.filter(category_id=category_id)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    def perform_create(self, serializer):
        tenant_id = ThreadVaribales().get_current_tenant_id()
        user_id = ThreadVaribales().get_val('user_id')
        serializer.save(tenant_id=tenant_id, created_by_id=user_id)


class ProductDetailUpdateView(generics.RetrieveUpdateAPIView):
    serializer_class = ProductDetailSerializer
    http_method_names = ['get', 'patch']

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated(), IsTenantMember()]

    def get_queryset(self):
        qs = Product.objects.all().prefetch_related('variants')
        if self.request.method == 'GET' and not self.request.query_params.get('all'):
            qs = qs.filter(is_active=True)
        return qs

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return ProductListSerializer
        return ProductDetailSerializer

    def perform_update(self, serializer):
        user_id = ThreadVaribales().get_val('user_id')
        serializer.save(modified_by_id=user_id)


class ProductVariantListCreateView(generics.ListCreateAPIView):
    serializer_class = ProductVariantSerializer
    permission_classes = [IsAuthenticated, IsTenantMember]

    def get_queryset(self):
        return ProductVariant.objects.filter(product_id=self.kwargs['product_pk'])

    def perform_create(self, serializer):
        tenant_id = ThreadVaribales().get_current_tenant_id()
        user_id = ThreadVaribales().get_val('user_id')
        serializer.save(
            product_id=self.kwargs['product_pk'],
            tenant_id=tenant_id,
            created_by_id=user_id,
        )


class ProductVariantUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductVariantSerializer
    http_method_names = ['patch', 'delete']
    permission_classes = [IsAuthenticated, IsTenantMember]

    def get_queryset(self):
        return ProductVariant.objects.filter(product_id=self.kwargs['product_pk'])

    def perform_destroy(self, instance):
        instance.deleted_at = timezone.now()
        instance.save(update_fields=['deleted_at'])


class CartView(APIView):
    permission_classes = [IsAuthenticated, IsTenantMember]

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
    permission_classes = [IsAuthenticated, IsTenantMember]

    def perform_create(self, serializer):
        user_id   = ThreadVaribales().get_val('user_id')
        tenant_id = ThreadVaribales().get_current_tenant_id()
        cart = Cart.objects.filter(user_id=user_id, is_active=True).first()
        serializer.save(cart=cart, tenant_id=tenant_id)


class CartItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class  = CartItemSerializer
    http_method_names = ['patch', 'delete']
    permission_classes = [IsAuthenticated, IsTenantMember]

    def get_queryset(self):
        return CartItem.objects.all()


class OrderListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsTenantMember]

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
    permission_classes = [IsAuthenticated, IsTenantMember]

    def get_queryset(self):
        return Order.objects.all().prefetch_related('items').select_related('address')


class PaymentListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsTenantMember]

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
