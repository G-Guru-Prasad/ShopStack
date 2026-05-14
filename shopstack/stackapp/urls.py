from django.urls import path

from stackapp import views

urlpatterns = [
    # Catalog
    path('products/', views.ProductListCreateView.as_view(), name='product-list-create'),
    path('products/<int:pk>/', views.ProductDetailUpdateView.as_view(), name='product-detail-update'),
    path('categories/', views.CategoryListCreateView.as_view(), name='category-list-create'),
    path('products/<int:product_pk>/variants/', views.ProductVariantListCreateView.as_view(), name='product-variant-list-create'),
    path('products/<int:product_pk>/variants/<int:pk>/', views.ProductVariantUpdateDeleteView.as_view(), name='product-variant-detail'),

    # Cart
    path('cart/', views.CartView.as_view(), name='cart'),
    path('cart/items/', views.CartItemCreateView.as_view(), name='cart-item-create'),
    path('cart/items/<int:pk>/', views.CartItemDetailView.as_view(), name='cart-item-detail'),

    # Orders
    path('orders/', views.OrderListCreateView.as_view(), name='order-list-create'),
    path('orders/<int:pk>/', views.OrderDetailView.as_view(), name='order-detail'),

    # Payments
    path('payments/', views.PaymentListCreateView.as_view(), name='payment-list-create'),
]
