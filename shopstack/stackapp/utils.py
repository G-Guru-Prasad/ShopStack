from django.db import models
from threading import current_thread


class ThreadVaribales:
    """
    A class to hold thread-local variables.
    This is used to store the current tenant ID for each thread.
    """

    def __init__(self):
        self.thread = current_thread()

    def get_current_tenant_id(self):
        """
        Retrieve the current tenant ID from the thread-local storage.
        """
        tenant_id = self.get_val('tenant_id')
        return tenant_id

    def get_val(self, key):
        """
        Get a value from the thread-local storage.
        """
        return getattr(self.thread, key, None)

    def set_val(self, key, value):
        """
        Set a value in the thread-local storage.
        """
        setattr(self.thread, key, value)


class TenantBasedManager(models.Manager):
    """
    A custom manager to filter objects based on the current tenant.
    """
    def __init__(self, *args, **kwargs):
        self.tenant_id = ThreadVaribales().get_current_tenant_id()
        super().__init__(*args, **kwargs)

    def add_tenant_id(self, objs):
        """
        Override the default queryset to filter by the current tenant ID.
        """
        for obj in objs:
            obj.tenant_id = self.tenant_id
            if hasattr(obj, 'modified_by'):
                obj.modified_by_id = ThreadVaribales().get_val('user_id')
                obj.created_by_id = ThreadVaribales().get_val('user_id')
            yield obj

    def bulk_create(self, objs, *args, **kwargs):
        """Bulk Create method override."""
        return super().bulk_create(
            self.add_tenant_id(objs), *args, **kwargs
        )
    
    def create(self, **kwargs):
        """Single-object create with automatic tenant and audit field injection."""
        kwargs.setdefault('tenant_id', ThreadVaribales().get_current_tenant_id())
        kwargs.setdefault('created_by_id', ThreadVaribales().get_val('user_id'))
        return super().create(**kwargs)

    def get_queryset(self, *args, **kwargs):
        """Override get queryset method."""

        return super().get_queryset(*args, **kwargs).filter(
            tenant_id=ThreadVaribales().get_current_tenant_id(),
            deleted_at__isnull=True,
        )


class TenantContext:
    """Context manager that scopes thread-local tenant_id/user_id for tests.

    Also refreshes the cached `tenant_id` on every TenantBasedManager so
    bulk_create and other manager-cached paths see the active tenant.
    """

    def __init__(self, tenant_id, user_id=None):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._prev_tenant_id = None
        self._prev_user_id = None
        self._prev_manager_tenants = {}

    def _tenant_managers(self):
        from django.apps import apps
        for model in apps.get_models():
            manager = getattr(model, 'objects', None)
            if isinstance(manager, TenantBasedManager):
                yield model, manager

    def __enter__(self):
        tv = ThreadVaribales()
        self._prev_tenant_id = tv.get_val('tenant_id')
        self._prev_user_id = tv.get_val('user_id')
        tv.set_val('tenant_id', self.tenant_id)
        tv.set_val('user_id', self.user_id)
        for model, manager in self._tenant_managers():
            self._prev_manager_tenants[model] = manager.tenant_id
            manager.tenant_id = self.tenant_id
        return self

    def __exit__(self, exc_type, exc, tb):
        tv = ThreadVaribales()
        tv.set_val('tenant_id', self._prev_tenant_id)
        tv.set_val('user_id', self._prev_user_id)
        for model, prev in self._prev_manager_tenants.items():
            model.objects.tenant_id = prev
        return False
