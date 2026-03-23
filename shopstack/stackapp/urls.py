from django.urls import path

from stackapp import views

urlpatterns = [
    # Catalog
    path('products/', views.ProductListView.as_view(), name='product-list'),
    path('products/<int:pk>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('categories/', views.CategoryListView.as_view(), name='category-list'),

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
