from unittest import mock

from django.test import SimpleTestCase, override_settings

from docs_agent import orchestrator
from docs_agent.types import Draft, GuardrailDecision, Passage, VerifierResult


PASSAGES = [
    Passage(text='alpha body', file='a.md', heading='Alpha'),
    Passage(text='beta body', file='b.md', heading='Beta'),
]


class OrchestratorTests(SimpleTestCase):
    def test_blocked_at_guardrail(self):
        with mock.patch.object(
            orchestrator.guardrails, 'check_question',
            return_value=GuardrailDecision(allowed=False, reason='nope'),
        ):
            out = orchestrator.answer('Q')
        self.assertEqual(out.status, 'blocked')
        self.assertEqual(out.answer, '')
        self.assertEqual(out.reason, 'nope')
        self.assertEqual(out.trace[0]['step'], 'guardrail')

    def test_no_context_when_retriever_empty(self):
        with mock.patch.object(
            orchestrator.guardrails, 'check_question',
            return_value=GuardrailDecision(allowed=True, reason=''),
        ), mock.patch.object(orchestrator.retriever, 'query', return_value=[]):
            out = orchestrator.answer('Q')
        self.assertEqual(out.status, 'no_context')
        self.assertEqual(out.citations, [])

    def test_verified_on_first_draft(self):
        with mock.patch.object(
            orchestrator.guardrails, 'check_question',
            return_value=GuardrailDecision(allowed=True, reason=''),
        ), mock.patch.object(
            orchestrator.retriever, 'query', return_value=PASSAGES,
        ), mock.patch.object(
            orchestrator.task_agent, 'draft_answer',
            return_value=Draft(answer='A', citations=[1]),
        ), mock.patch.object(
            orchestrator.verifier, 'verify',
            return_value=VerifierResult(grounded=True, citations_ok=True, issues=''),
        ):
            out = orchestrator.answer('Q')
        self.assertEqual(out.status, 'ok')
        self.assertEqual(out.answer, 'A')
        self.assertEqual(out.citations, [{'n': 1, 'file': 'a.md', 'heading': 'Alpha'}])
        steps = [t['step'] for t in out.trace]
        self.assertEqual(steps, ['guardrail', 'retrieve', 'draft', 'verify'])

    def test_verified_after_one_revise_loop(self):
        verdicts = [
            VerifierResult(grounded=False, citations_ok=False, issues='cite more'),
            VerifierResult(grounded=True, citations_ok=True, issues=''),
        ]
        drafts = [Draft(answer='A1', citations=[]), Draft(answer='A2', citations=[1])]
        with mock.patch.object(
            orchestrator.guardrails, 'check_question',
            return_value=GuardrailDecision(allowed=True, reason=''),
        ), mock.patch.object(
            orchestrator.retriever, 'query', return_value=PASSAGES,
        ), mock.patch.object(
            orchestrator.task_agent, 'draft_answer', side_effect=drafts,
        ) as draft_mock, mock.patch.object(
            orchestrator.verifier, 'verify', side_effect=verdicts,
        ):
            out = orchestrator.answer('Q')
        self.assertEqual(out.status, 'ok')
        self.assertEqual(out.answer, 'A2')
        # feedback from first failure must be threaded into second draft call
        second_kwargs = draft_mock.call_args_list[1].kwargs
        self.assertEqual(second_kwargs['feedback'], 'cite more')

    def test_unverified_after_max_loops(self):
        verdict = VerifierResult(grounded=False, citations_ok=False, issues='still bad')
        with mock.patch.object(
            orchestrator.guardrails, 'check_question',
            return_value=GuardrailDecision(allowed=True, reason=''),
        ), mock.patch.object(
            orchestrator.retriever, 'query', return_value=PASSAGES,
        ), mock.patch.object(
            orchestrator.task_agent, 'draft_answer',
            return_value=Draft(answer='best effort', citations=[1, 1]),
        ), mock.patch.object(
            orchestrator.verifier, 'verify', return_value=verdict,
        ):
            out = orchestrator.answer('Q')
        self.assertEqual(out.status, 'unverified')
        self.assertEqual(out.answer, 'best effort')
        self.assertEqual(out.reason, 'still bad')
        self.assertEqual(out.citations, [{'n': 1, 'file': 'a.md', 'heading': 'Alpha'}])

    @override_settings(DOCS_AGENT_MAX_REVISE_LOOPS=0)
    def test_loop_budget_respects_setting(self):
        verdict = VerifierResult(grounded=False, citations_ok=False, issues='x')
        with mock.patch.object(
            orchestrator.guardrails, 'check_question',
            return_value=GuardrailDecision(allowed=True, reason=''),
        ), mock.patch.object(
            orchestrator.retriever, 'query', return_value=PASSAGES,
        ), mock.patch.object(
            orchestrator.task_agent, 'draft_answer',
            return_value=Draft(answer='only one', citations=[]),
        ) as dm, mock.patch.object(
            orchestrator.verifier, 'verify', return_value=verdict,
        ):
            out = orchestrator.answer('Q')
        self.assertEqual(out.status, 'unverified')
        self.assertEqual(dm.call_count, 1)

    def test_out_of_range_citations_are_dropped(self):
        with mock.patch.object(
            orchestrator.guardrails, 'check_question',
            return_value=GuardrailDecision(allowed=True, reason=''),
        ), mock.patch.object(
            orchestrator.retriever, 'query', return_value=PASSAGES,
        ), mock.patch.object(
            orchestrator.task_agent, 'draft_answer',
            return_value=Draft(answer='A', citations=[0, 9, 2]),
        ), mock.patch.object(
            orchestrator.verifier, 'verify',
            return_value=VerifierResult(grounded=True, citations_ok=True, issues=''),
        ):
            out = orchestrator.answer('Q')
        self.assertEqual(out.citations, [{'n': 2, 'file': 'b.md', 'heading': 'Beta'}])
