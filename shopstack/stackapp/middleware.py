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

        tv.set_val('user_id', None)  # Views set this after authentication

        response = self.get_response(request)

        # Clean up thread-local — critical for thread-pool servers (gunicorn, uWSGI)
        tv.set_val('tenant_id', None)
        tv.set_val('user_id', None)

        return response
