from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from doc_agent.task_agent import TaskAgent


def _chunk(chunk_id, source_path='runbooks/deploy.md', text='content'):
    document = SimpleNamespace(source_path=source_path)
    return SimpleNamespace(id=chunk_id, document=document, text=text)


class TaskAgentTests(SimpleTestCase):
    def test_returns_draft_and_used_ids(self):
        with mock.patch('doc_agent.task_agent.llm.complete_json',
                        return_value={
                            'draft_answer': 'Run ./deploy.sh [chunk:1]',
                            'used_chunk_ids': [1, 2],
                        }):
            result = TaskAgent().draft(
                'how do I deploy?',
                [_chunk(1), _chunk(2)],
                history=[],
            )
        self.assertEqual(result['draft_answer'], 'Run ./deploy.sh [chunk:1]')
        self.assertEqual(result['used_chunk_ids'], [1, 2])

    def test_handles_missing_fields(self):
        with mock.patch('doc_agent.task_agent.llm.complete_json',
                        return_value={}):
            result = TaskAgent().draft('q', [], history=[])
        self.assertEqual(result['draft_answer'], '')
        self.assertEqual(result['used_chunk_ids'], [])

    def test_passes_verifier_feedback_through(self):
        captured = {}

        def fake(system, user, **kw):
            captured['user'] = user
            return {'draft_answer': 'x', 'used_chunk_ids': []}

        with mock.patch('doc_agent.task_agent.llm.complete_json',
                        side_effect=fake):
            TaskAgent().draft(
                'q', [_chunk(1)], history=[],
                verifier_feedback=['claim X unsupported'],
            )
        self.assertIn('claim X unsupported', captured['user'])
