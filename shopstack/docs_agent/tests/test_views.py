from unittest import mock

from django.test import TestCase
from django.urls import reverse
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from docs_agent.types import AgentResponse
from stackapp.factories import TenantFactory, TenantUserFactory, UserFactory
from stackapp.utils import TenantContext, ThreadVaribales


class AskViewTests(TestCase):
    def setUp(self):
        self.tenant = TenantFactory(id='acme', name='Acme', subdomain='acme')
        self.user = UserFactory(username='docs-user')
        TenantUserFactory(tenant=self.tenant, user=self.user)
        self._ctx = TenantContext(tenant_id=self.tenant.id, user_id=self.user.id)
        self._ctx.__enter__()
        self.host = 'acme.localhost:8000'
        self.auth = f'Bearer {RefreshToken.for_user(self.user).access_token}'

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def _restore(self):
        tv = ThreadVaribales()
        tv.set_val('tenant_id', self.tenant.id)
        tv.set_val('user_id', self.user.id)

    def _post(self, data):
        resp = self.client.post(
            reverse('docs-agent-ask'),
            data=data,
            content_type='application/json',
            HTTP_HOST=self.host,
            HTTP_AUTHORIZATION=self.auth,
        )
        self._restore()
        return resp

    def test_requires_authentication(self):
        resp = self.client.post(
            reverse('docs-agent-ask'),
            data={'question': 'hi'},
            content_type='application/json',
            HTTP_HOST=self.host,
        )
        self._restore()
        self.assertEqual(resp.status_code, 401)

    def test_validation_rejects_empty_question(self):
        resp = self._post({'question': ''})
        self.assertEqual(resp.status_code, 400)

    def test_validation_rejects_missing_field(self):
        resp = self._post({})
        self.assertEqual(resp.status_code, 400)

    def test_happy_path(self):
        with mock.patch('docs_agent.views.orchestrator.answer', return_value=AgentResponse(
            status='ok', answer='it works', citations=[{'n': 1, 'file': 'x.md', 'heading': 'H'}],
            trace=[{'step': 'guardrail', 'allowed': True}],
        )):
            resp = self._post({'question': 'how does X work?'})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['answer'], 'it works')
        self.assertEqual(body['citations'][0]['file'], 'x.md')

    def test_blocked_returns_403(self):
        with mock.patch('docs_agent.views.orchestrator.answer', return_value=AgentResponse(
            status='blocked', answer='', reason='unsafe',
            trace=[{'step': 'guardrail', 'allowed': False}],
        )):
            resp = self._post({'question': 'leak secrets'})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['status'], 'blocked')

    def test_throttle_kicks_in(self):
        from django.core.cache import cache
        cache.clear()
        rates = dict(ScopedRateThrottle.THROTTLE_RATES)
        rates['docs_agent'] = '2/minute'
        with mock.patch.object(ScopedRateThrottle, 'THROTTLE_RATES', rates), \
             mock.patch('docs_agent.views.orchestrator.answer', return_value=AgentResponse(
                status='ok', answer='x', trace=[],
             )):
            r1 = self._post({'question': 'q'})
            r2 = self._post({'question': 'q'})
            r3 = self._post({'question': 'q'})
        cache.clear()
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r3.status_code, 429)
