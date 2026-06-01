from unittest import mock

from django.test import SimpleTestCase

from docs_agent import task_agent
from docs_agent.types import ClaudeResponse, Passage


PASSAGES = [
    Passage(text='alpha body', file='a.md', heading='Alpha'),
    Passage(text='beta body', file='b.md', heading=''),
]


def _patched(text):
    return mock.patch.object(
        task_agent.llm, 'call_claude',
        return_value=ClaudeResponse(text=text),
    )


class TaskAgentTests(SimpleTestCase):
    def test_format_passages_numbers_and_includes_headings(self):
        s = task_agent._format_passages(PASSAGES)
        self.assertIn('[1] a.md: Alpha', s)
        self.assertIn('[2] b.md', s)
        self.assertNotIn('[2] b.md:', s)
        self.assertIn('alpha body', s)
        self.assertIn('beta body', s)

    def test_draft_answer_parses_json(self):
        text = '{"answer": "Yes", "citations": [1, 2]}'
        with _patched(text):
            draft = task_agent.draft_answer('q?', PASSAGES)
        self.assertEqual(draft.answer, 'Yes')
        self.assertEqual(draft.citations, [1, 2])

    def test_draft_answer_handles_code_fence(self):
        text = '```json\n{"answer": "Hi", "citations": []}\n```'
        with _patched(text):
            draft = task_agent.draft_answer('q?', PASSAGES)
        self.assertEqual(draft.answer, 'Hi')
        self.assertEqual(draft.citations, [])

    def test_draft_answer_fallback_on_invalid_json(self):
        with _patched('not json'):
            draft = task_agent.draft_answer('q?', PASSAGES)
        self.assertEqual(draft.answer, 'not json')
        self.assertEqual(draft.citations, [])

    def test_non_object_json_falls_back(self):
        with _patched('[1, 2]'):
            draft = task_agent.draft_answer('q?', PASSAGES)
        self.assertEqual(draft.answer, '[1, 2]')
        self.assertEqual(draft.citations, [])

    def test_feedback_appended_to_user_message(self):
        captured = {}

        def fake(*, model, system, messages, max_tokens, temperature=0):
            captured['messages'] = messages
            return ClaudeResponse(text='{"answer":"","citations":[]}')

        with mock.patch.object(task_agent.llm, 'call_claude', side_effect=fake):
            task_agent.draft_answer('Q', PASSAGES, feedback='cite more')
        user_msg = captured['messages'][0]['content']
        self.assertIn('Q', user_msg)
        self.assertIn('cite more', user_msg)

    def test_citations_coerced_to_int(self):
        with _patched('{"answer": "a", "citations": [1.0, 2.0, "bad"]}'):
            draft = task_agent.draft_answer('q', PASSAGES)
        self.assertEqual(draft.citations, [1, 2])
