"""Tests that DB settings honour environment variables."""
import importlib
import os
from unittest import mock

from django.test import SimpleTestCase


class DatabaseSettingsTests(SimpleTestCase):
    """Verify settings.DATABASES reads from env vars with defaults."""

    def _reload_settings(self):
        from shopstack import settings
        importlib.reload(settings)
        return settings

    def test_defaults_when_env_missing(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('DB_')}
        with mock.patch.dict(os.environ, env, clear=True):
            settings = self._reload_settings()
        db = settings.DATABASES['default']
        self.assertEqual(db['NAME'], 'shopstack_db')
        self.assertEqual(db['HOST'], 'localhost')
        self.assertEqual(db['PORT'], '5432')
        self.assertEqual(db['USER'], 'postgres')
        self.assertEqual(db['PASSWORD'], 'password')

    def test_env_vars_override_defaults(self):
        overrides = {
            'DB_NAME': 'ci_test_db',
            'DB_HOST': 'pg.ci.local',
            'DB_PORT': '6543',
            'DB_USER': 'ciuser',
            'DB_PASSWORD': 'cipass',
        }
        with mock.patch.dict(os.environ, overrides, clear=False):
            settings = self._reload_settings()
        db = settings.DATABASES['default']
        self.assertEqual(db['NAME'], 'ci_test_db')
        self.assertEqual(db['HOST'], 'pg.ci.local')
        self.assertEqual(db['PORT'], '6543')
        self.assertEqual(db['USER'], 'ciuser')
        self.assertEqual(db['PASSWORD'], 'cipass')
