from unittest import mock

from django.test import TestCase

from doc_agent import orchestrator as orch_module
from doc_agent.models import Conversation, Message
from doc_agent.orchestrator import Orchestrator
from doc_agent.tests.factories import (
    DocAgentUserFactory, DocumentChunkFactory, DocumentFactory,
)


class StubGuard:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = 0

    def check(self, question, history):
        self.calls += 1
        return self.verdict


class StubTaskAgent:
    def __init__(self, drafts):
        self.drafts = list(drafts)
        self.calls = []

    def draft(self, question, chunks, history, verifier_feedback=None):
        self.calls.append({
            'question': question, 'feedback': verifier_feedback,
        })
        return self.drafts.pop(0)


class StubVerifier:
    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.calls = 0

    def check(self, draft, used_chunks):
        self.calls += 1
        return self.verdicts.pop(0)


def _seed_chunks(user):
    doc = DocumentFactory(source_path='runbooks/deploy.md')
    return [
        DocumentChunkFactory(document=doc, chunk_index=0, text='use ./deploy.sh'),
        DocumentChunkFactory(document=doc, chunk_index=1, text='verify health'),
    ]


class OrchestratorTests(TestCase):
    def setUp(self):
        self.user = DocAgentUserFactory()

    def _stub_retrieval(self, chunks):
        return mock.patch.object(
            orch_module.retriever, 'top_k', return_value=chunks,
        )

    def _stub_embed(self):
        return mock.patch.object(
            orch_module.embeddings, 'embed_query', return_value=[0.0] * 1024,
        )

    def test_guardrails_refusal_short_circuits(self):
        guard = StubGuard({
            'allowed': False, 'reason': 'secrets',
            'intent': '', 'topic': '',
        })
        orch = Orchestrator(
            guardrails=guard,
            task_agent=StubTaskAgent([]),
            verifier=StubVerifier([]),
        )
        with self._stub_embed(), self._stub_retrieval([]):
            response = orch.run(self.user, 'give prod db password')
        self.assertIn('secrets', response.answer)
        self.assertEqual(response.citations, [])
        self.assertFalse(response.not_fully_verified)
        msg = Message.objects.get(pk=response.message_id)
        self.assertEqual(msg.guardrails_verdict['allowed'], False)
        self.assertIsNone(msg.verifier_verdict)

    def test_no_chunks_returns_no_docs(self):
        guard = StubGuard({
            'allowed': True, 'reason': '', 'intent': '', 'topic': '',
        })
        orch = Orchestrator(
            guardrails=guard,
            task_agent=StubTaskAgent([]),
            verifier=StubVerifier([]),
        )
        with self._stub_embed(), self._stub_retrieval([]):
            response = orch.run(self.user, 'how do I deploy?')
        self.assertEqual(response.answer, "I don't have docs on that.")
        self.assertEqual(response.citations, [])

    def test_happy_path_persists_message_with_verdicts(self):
        chunks = _seed_chunks(self.user)
        guard = StubGuard({
            'allowed': True, 'reason': '', 'intent': '', 'topic': '',
        })
        task = StubTaskAgent([{
            'draft_answer': 'Run ./deploy.sh [chunk:1]',
            'used_chunk_ids': [chunks[0].id],
        }])
        verifier = StubVerifier([{
            'grounded': True, 'issues': [], 'revised_answer': None,
        }])
        orch = Orchestrator(
            guardrails=guard, task_agent=task, verifier=verifier,
        )
        with self._stub_embed(), self._stub_retrieval(chunks):
            response = orch.run(self.user, 'how do I deploy?')
        self.assertIn('deploy.sh', response.answer)
        self.assertEqual(len(response.citations), 1)
        msg = Message.objects.get(pk=response.message_id)
        self.assertEqual(msg.cited_chunks.count(), 1)
        self.assertEqual(msg.verifier_verdict['grounded'], True)
        self.assertFalse(msg.not_fully_verified)

    def test_one_revision_loop_when_verifier_returns_revised_answer(self):
        chunks = _seed_chunks(self.user)
        task = StubTaskAgent([{
            'draft_answer': 'wrong', 'used_chunk_ids': [chunks[0].id],
        }])
        verifier = StubVerifier([{
            'grounded': False,
            'issues': ['claim'],
            'revised_answer': 'corrected answer',
        }])
        orch = Orchestrator(
            guardrails=StubGuard({
                'allowed': True, 'reason': '', 'intent': '', 'topic': '',
            }),
            task_agent=task, verifier=verifier,
        )
        with self._stub_embed(), self._stub_retrieval(chunks):
            response = orch.run(self.user, 'q')
        self.assertEqual(response.answer, 'corrected answer')
        self.assertFalse(response.not_fully_verified)

    def test_revision_loop_marks_not_fully_verified_after_cap(self):
        chunks = _seed_chunks(self.user)
        task = StubTaskAgent([
            {'draft_answer': f'draft-{i}', 'used_chunk_ids': [chunks[0].id]}
            for i in range(3)
        ])
        verifier = StubVerifier([
            {'grounded': False, 'issues': ['x'], 'revised_answer': None}
            for _ in range(3)
        ])
        orch = Orchestrator(
            guardrails=StubGuard({
                'allowed': True, 'reason': '', 'intent': '', 'topic': '',
            }),
            task_agent=task, verifier=verifier,
        )
        with self._stub_embed(), self._stub_retrieval(chunks):
            response = orch.run(self.user, 'q')
        self.assertTrue(response.not_fully_verified)
        self.assertEqual(task.calls.__len__(), 3)

    def test_existing_conversation_reused(self):
        chunks = _seed_chunks(self.user)
        guard = StubGuard({
            'allowed': True, 'reason': '', 'intent': '', 'topic': '',
        })
        task = StubTaskAgent([{
            'draft_answer': 'ans', 'used_chunk_ids': [chunks[0].id],
        }])
        verifier = StubVerifier([{
            'grounded': True, 'issues': [], 'revised_answer': None,
        }])
        orch = Orchestrator(
            guardrails=guard, task_agent=task, verifier=verifier,
        )
        conversation = Conversation.objects.create(
            user=self.user, title='Existing',
        )
        with self._stub_embed(), self._stub_retrieval(chunks):
            response = orch.run(
                self.user, 'follow-up',
                conversation_id=conversation.id,
            )
        self.assertEqual(response.conversation_id, conversation.id)
        self.assertEqual(
            Message.objects.filter(conversation=conversation).count(), 2,
        )
