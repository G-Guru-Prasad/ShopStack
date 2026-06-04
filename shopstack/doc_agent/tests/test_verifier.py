from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from doc_agent.verifier import Verifier


def _chunk(chunk_id):
    return SimpleNamespace(
        id=chunk_id,
        document=SimpleNamespace(source_path='runbooks/x.md'),
        text='source text',
    )


class VerifierTests(SimpleTestCase):
    def test_grounded_pass(self):
        with mock.patch('doc_agent.verifier.llm.complete_json',
                        return_value={
                            'grounded': True, 'issues': [],
                            'revised_answer': None,
                        }):
            verdict = Verifier().check('answer', [_chunk(1)])
        self.assertTrue(verdict['grounded'])
        self.assertIsNone(verdict['revised_answer'])

    def test_not_grounded_with_revision(self):
        with mock.patch('doc_agent.verifier.llm.complete_json',
                        return_value={
                            'grounded': False,
                            'issues': ['claim X'],
                            'revised_answer': 'corrected answer',
                        }):
            verdict = Verifier().check('draft', [_chunk(1)])
        self.assertFalse(verdict['grounded'])
        self.assertEqual(verdict['issues'], ['claim X'])
        self.assertEqual(verdict['revised_answer'], 'corrected answer')

    def test_not_grounded_no_revision(self):
        with mock.patch('doc_agent.verifier.llm.complete_json',
                        return_value={
                            'grounded': False,
                            'issues': ['claim X'],
                            'revised_answer': None,
                        }):
            verdict = Verifier().check('draft', [_chunk(1)])
        self.assertFalse(verdict['grounded'])
        self.assertIsNone(verdict['revised_answer'])
