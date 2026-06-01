from django.conf import settings

from docs_agent import guardrails, retriever, task_agent, verifier
from docs_agent.types import AgentResponse


def _citation_payload(draft, passages):
    out = []
    seen = set()
    for c in draft.citations:
        if c in seen:
            continue
        seen.add(c)
        if 1 <= c <= len(passages):
            p = passages[c - 1]
            out.append({'n': c, 'file': p.file, 'heading': p.heading})
    return out


def answer(question):
    trace = []

    decision = guardrails.check_question(question)
    trace.append({
        'step': 'guardrail',
        'allowed': decision.allowed,
        'reason': decision.reason,
    })
    if not decision.allowed:
        return AgentResponse(
            status='blocked',
            answer='',
            citations=[],
            trace=trace,
            reason=decision.reason,
        )

    passages = retriever.query(question, k=5)
    trace.append({'step': 'retrieve', 'count': len(passages)})
    if not passages:
        return AgentResponse(
            status='no_context',
            answer="I couldn't find relevant documentation to answer that.",
            citations=[],
            trace=trace,
        )

    max_loops = getattr(settings, 'DOCS_AGENT_MAX_REVISE_LOOPS', 2)
    feedback = None
    draft = None
    last_verdict = None
    for loop in range(max_loops + 1):
        draft = task_agent.draft_answer(question, passages, feedback=feedback)
        trace.append({'step': 'draft', 'loop': loop, 'citations': list(draft.citations)})
        verdict = verifier.verify(question, draft, passages)
        last_verdict = verdict
        trace.append({
            'step': 'verify',
            'loop': loop,
            'grounded': verdict.grounded,
            'citations_ok': verdict.citations_ok,
            'issues': verdict.issues,
        })
        if verdict.grounded and verdict.citations_ok:
            return AgentResponse(
                status='ok',
                answer=draft.answer,
                citations=_citation_payload(draft, passages),
                trace=trace,
            )
        feedback = verdict.issues or 'Answer was not fully grounded in passages.'

    return AgentResponse(
        status='unverified',
        answer=draft.answer if draft else '',
        citations=_citation_payload(draft, passages) if draft else [],
        trace=trace,
        reason=last_verdict.issues if last_verdict else 'verification failed',
    )
