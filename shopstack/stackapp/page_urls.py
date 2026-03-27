from django.urls import path

from stackapp.page_views import (
    DashboardPageView,
    LoginPageView,
    ProfilePageView,
    RootRedirectView,
)

urlpatterns = [
    path('', RootRedirectView.as_view(), name='root'),
    path('login/', LoginPageView.as_view(), name='login'),
    path('dashboard/', DashboardPageView.as_view(), name='dashboard'),
    path('profile/', ProfilePageView.as_view(), name='profile'),
]
