from django.urls import path

from stackapp.page_views import (
    DashboardPageView,
    LoginPageView,
    ProductCreatePageView,
    ProductListPageView,
    ProfilePageView,
    ResetPasswordPageView,
    RootRedirectView,
)

urlpatterns = [
    path('', RootRedirectView.as_view(), name='root'),
    path('login/', LoginPageView.as_view(), name='login'),
    path('dashboard/', DashboardPageView.as_view(), name='dashboard'),
    path('profile/', ProfilePageView.as_view(), name='profile'),
    path('products/', ProductListPageView.as_view(), name='product-list-page'),
    path('products/create/', ProductCreatePageView.as_view(), name='product-create-page'),
    path('reset-password/', ResetPasswordPageView.as_view(), name='reset-password'),
]
