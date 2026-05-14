from django.views.generic import TemplateView, RedirectView


class RootRedirectView(RedirectView):
    url = '/login/'
    permanent = False


class LoginPageView(TemplateView):
    template_name = 'stackapp/login.html'


class DashboardPageView(TemplateView):
    template_name = 'stackapp/dashboard.html'


class ProfilePageView(TemplateView):
    template_name = 'stackapp/profile.html'


class ProductListPageView(TemplateView):
    template_name = 'stackapp/product_list.html'


class ProductCreatePageView(TemplateView):
    template_name = 'stackapp/product_create.html'


class ResetPasswordPageView(TemplateView):
    template_name = 'stackapp/reset_password.html'
