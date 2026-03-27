from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError

from stackapp.utils import ThreadVaribales


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        hostname = request.META.get('HTTP_HOST', '').split(':')[0]
        parts = hostname.split('.')
        tv = ThreadVaribales()

        if len(parts) >= 2:
            from stackapp.models import Tenant
            try:
                tenant = Tenant.objects.get(subdomain=parts[0])
                tv.set_val('tenant_id', tenant.id)
            except Tenant.DoesNotExist:
                tv.set_val('tenant_id', None)
        else:
            tv.set_val('tenant_id', None)

        response = self.get_response(request)

        # Clean up thread-local — critical for thread-pool servers (gunicorn, uWSGI)
        tv.set_val('tenant_id', None)

        return response


class JWTUserMiddleware:
    """Decodes Bearer JWT and sets user_id in ThreadVaribales before the view runs.
    Must be positioned after AuthenticationMiddleware in the middleware stack."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._jwt_auth = JWTAuthentication()

    def __call__(self, request):
        tv = ThreadVaribales()
        user_id = None

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            raw_token = auth_header.split(' ', 1)[1].strip()
            try:
                validated_token = self._jwt_auth.get_validated_token(raw_token)
                user = self._jwt_auth.get_user(validated_token)
                user_id = user.id
                request.user = user
            except (InvalidToken, TokenError, AuthenticationFailed):
                pass  # user_id stays None; DRF will return 401 on protected views

        tv.set_val('user_id', user_id)
        response = self.get_response(request)
        tv.set_val('user_id', None)

        return response
