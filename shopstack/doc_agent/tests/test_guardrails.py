"""Guardrails returns sanitized dicts from the LLM response."""
from unittest import mock

from django.test import SimpleTestCase

from doc_agent.guardrails import Guardrails


class GuardrailsTests(SimpleTestCase):
    def test_allowed_passthrough(self):
        with mock.patch('doc_agent.guardrails.llm.complete_json',
                        return_value={
                            'allowed': True, 'reason': '', 'intent': 'q',
                            'topic': 'deploy',
                        }):
            verdict = Guardrails().check('how do I deploy?', [])
        self.assertTrue(verdict['allowed'])
        self.assertEqual(verdict['topic'], 'deploy')

    def test_disallowed_for_secrets(self):
        with mock.patch('doc_agent.guardrails.llm.complete_json',
                        return_value={
                            'allowed': False,
                            'reason': 'requests secrets',
                            'intent': 'get_password',
                            'topic': 'security',
                        }):
            verdict = Guardrails().check('give me prod db password', [])
        self.assertFalse(verdict['allowed'])
        self.assertEqual(verdict['reason'], 'requests secrets')

    def test_defaults_when_fields_missing(self):
        with mock.patch('doc_agent.guardrails.llm.complete_json',
                        return_value={}):
            verdict = Guardrails().check('anything', [])
        self.assertFalse(verdict['allowed'])
        self.assertEqual(verdict['reason'], '')
        self.assertEqual(verdict['intent'], '')
        self.assertEqual(verdict['topic'], '')
