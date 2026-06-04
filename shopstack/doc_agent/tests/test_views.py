from unittest import mock

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from doc_agent.orchestrator import AssistantResponse
from doc_agent.tests.factories import (
    ConversationFactory, DocAgentUserFactory, MessageFactory,
)


class AskAPITests(TestCase):
    def setUp(self):
        self.user = DocAgentUserFactory()
        self.client = APIClient()
        token = str(RefreshToken.for_user(self.user).access_token)
        self.auth_header = f'Bearer {token}'

    def test_unauthenticated_request_rejected(self):
        client = APIClient()
        resp = client.post('/api/agent/ask/', {'question': 'hi'}, format='json')
        self.assertEqual(resp.status_code, 401)

    def test_authenticated_request_runs_orchestrator(self):
        fake_response = AssistantResponse(
            message_id=1,
            conversation_id=2,
            answer='deploy with ./deploy.sh',
            citations=[],
            not_fully_verified=False,
        )
        with mock.patch(
            'doc_agent.views.Orchestrator',
        ) as orch_cls:
            orch_cls.return_value.run.return_value = fake_response
            resp = self.client.post(
                '/api/agent/ask/',
                {'question': 'how do I deploy?'},
                format='json',
                HTTP_AUTHORIZATION=self.auth_header,
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['answer'], 'deploy with ./deploy.sh')
        self.assertEqual(resp.json()['conversation_id'], 2)

    def test_invalid_payload_rejected(self):
        resp = self.client.post(
            '/api/agent/ask/', {}, format='json',
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self.assertEqual(resp.status_code, 400)

    def test_malformed_llm_response_returns_502(self):
        with mock.patch(
            'doc_agent.views.Orchestrator',
        ) as orch_cls:
            orch_cls.return_value.run.side_effect = ValueError('bad json')
            resp = self.client.post(
                '/api/agent/ask/',
                {'question': 'how do I deploy?'},
                format='json',
                HTTP_AUTHORIZATION=self.auth_header,
            )
        self.assertEqual(resp.status_code, 502)
        self.assertIn('detail', resp.json())


class ConversationAPITests(TestCase):
    def setUp(self):
        self.user = DocAgentUserFactory()
        self.other = DocAgentUserFactory()
        self.client = APIClient()
        token = str(RefreshToken.for_user(self.user).access_token)
        self.auth_header = f'Bearer {token}'

    def test_list_scoped_to_current_user(self):
        ConversationFactory(user=self.user, title='Mine')
        ConversationFactory(user=self.other, title='Not mine')
        resp = self.client.get(
            '/api/agent/conversations/',
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self.assertEqual(resp.status_code, 200)
        titles = [c['title'] for c in resp.json()['results']]
        self.assertIn('Mine', titles)
        self.assertNotIn('Not mine', titles)

    def test_detail_returns_messages(self):
        conv = ConversationFactory(user=self.user, title='Mine')
        MessageFactory(conversation=conv, role='user', content='hello')
        resp = self.client.get(
            f'/api/agent/conversations/{conv.id}/',
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['title'], 'Mine')
        self.assertEqual(len(body['messages']), 1)
        self.assertEqual(body['messages'][0]['content'], 'hello')

    def test_detail_for_other_user_404(self):
        conv = ConversationFactory(user=self.other, title='Other')
        resp = self.client.get(
            f'/api/agent/conversations/{conv.id}/',
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self.assertEqual(resp.status_code, 404)


class ChatPageViewTests(TestCase):
    def setUp(self):
        self.user = DocAgentUserFactory()

    def test_unauthenticated_redirects(self):
        resp = self.client.get('/agent/')
        self.assertEqual(resp.status_code, 302)

    def test_authenticated_renders_template(self):
        self.client.force_login(self.user)
        ConversationFactory(user=self.user, title='Hello')
        resp = self.client.get('/agent/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Hello')

    def test_csrf_cookie_set_on_chat_page(self):
        self.client.force_login(self.user)
        resp = self.client.get('/agent/')
        self.assertIn('csrftoken', resp.cookies)
