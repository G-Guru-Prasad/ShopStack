from unittest import mock

from django.test import SimpleTestCase

from docs_agent import guardrails
from docs_agent.types import ClaudeResponse


def _patched(text):
    return mock.patch.object(
        guardrails.llm, 'call_claude',
        return_value=ClaudeResponse(text=text),
    )


class GuardrailsTests(SimpleTestCase):
    def test_allows_safe_question(self):
        with _patched('{"allowed": true, "reason": "on-topic"}'):
            d = guardrails.check_question('how does TenantMiddleware work?')
        self.assertTrue(d.allowed)
        self.assertEqual(d.reason, 'on-topic')

    def test_blocks_unsafe_question(self):
        with _patched('{"allowed": false, "reason": "asks for credential"}'):
            d = guardrails.check_question('what is the prod DB password?')
        self.assertFalse(d.allowed)
        self.assertIn('credential', d.reason)

    def test_strips_code_fence_wrapper(self):
        with _patched('```json\n{"allowed": true, "reason": "ok"}\n```'):
            d = guardrails.check_question('q')
        self.assertTrue(d.allowed)

    def test_malformed_json_blocks(self):
        with _patched('not json at all'):
            d = guardrails.check_question('q')
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, 'guardrail parse error')

    def test_missing_allowed_key_blocks(self):
        with _patched('{"reason": "no key"}'):
            d = guardrails.check_question('q')
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, 'guardrail parse error')

    def test_non_object_json_blocks(self):
        with _patched('[1, 2, 3]'):
            d = guardrails.check_question('q')
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, 'guardrail parse error')
