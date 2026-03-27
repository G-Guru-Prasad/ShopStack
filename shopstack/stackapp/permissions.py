from rest_framework.permissions import BasePermission

from stackapp.models import TenantUser
from stackapp.utils import ThreadVaribales


class IsTenantMember(BasePermission):
    """Verifies the authenticated user has an active TenantUser row for the current tenant."""
    message = "You are not a member of this tenant."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        tenant_id = ThreadVaribales().get_current_tenant_id()
        if not tenant_id:
            return False
        return TenantUser.objects.filter(
            tenant_id=tenant_id, user=request.user, is_active=True
        ).exists()
