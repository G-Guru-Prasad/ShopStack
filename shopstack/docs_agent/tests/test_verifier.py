from unittest import mock

from django.test import SimpleTestCase

from docs_agent import verifier
from docs_agent.types import ClaudeResponse, Draft, Passage


PASSAGES = [Passage(text='body', file='a.md', heading='H')]
DRAFT = Draft(answer='ans', citations=[1])


def _patched(text):
    return mock.patch.object(
        verifier.llm, 'call_claude',
        return_value=ClaudeResponse(text=text),
    )


class VerifierTests(SimpleTestCase):
    def test_parses_grounded(self):
        with _patched('{"grounded": true, "citations_ok": true, "issues": ""}'):
            r = verifier.verify('q', DRAFT, PASSAGES)
        self.assertTrue(r.grounded)
        self.assertTrue(r.citations_ok)
        self.assertEqual(r.issues, '')

    def test_parses_ungrounded(self):
        with _patched('{"grounded": false, "citations_ok": false, "issues": "off-source"}'):
            r = verifier.verify('q', DRAFT, PASSAGES)
        self.assertFalse(r.grounded)
        self.assertFalse(r.citations_ok)
        self.assertEqual(r.issues, 'off-source')

    def test_parses_code_fenced(self):
        with _patched('```json\n{"grounded": true, "citations_ok": true, "issues": ""}\n```'):
            r = verifier.verify('q', DRAFT, PASSAGES)
        self.assertTrue(r.grounded)

    def test_parse_error_marks_ungrounded(self):
        with _patched('garbage'):
            r = verifier.verify('q', DRAFT, PASSAGES)
        self.assertFalse(r.grounded)
        self.assertFalse(r.citations_ok)
        self.assertEqual(r.issues, 'verifier parse error')

    def test_non_object_marks_ungrounded(self):
        with _patched('"a string"'):
            r = verifier.verify('q', DRAFT, PASSAGES)
        self.assertFalse(r.grounded)
        self.assertEqual(r.issues, 'verifier parse error')

    def test_user_message_includes_passages_and_citations(self):
        captured = {}

        def fake(*, model, system, messages, max_tokens, temperature=0):
            captured['user'] = messages[0]['content']
            return ClaudeResponse(text='{"grounded": true, "citations_ok": true, "issues": ""}')

        with mock.patch.object(verifier.llm, 'call_claude', side_effect=fake):
            verifier.verify('Q?', DRAFT, PASSAGES)
        self.assertIn('Q?', captured['user'])
        self.assertIn('[1] a.md: H', captured['user'])
        self.assertIn('ans', captured['user'])
