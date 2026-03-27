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
