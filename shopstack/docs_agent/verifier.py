import json

from django.conf import settings

from docs_agent import llm
from docs_agent.types import VerifierResult


VERIFIER_SYSTEM = (
    "You are a grounding verifier for an internal docs Q&A agent.\n"
    "Given the question, a draft answer with citation numbers, and the numbered passages,\n"
    "check two things:\n"
    "- grounded: every factual claim in the answer is supported by at least one passage.\n"
    "- citations_ok: each citation number refers to a passage that actually supports the claim it cites.\n"
    "Respond with a single JSON object: "
    '{"grounded": true|false, "citations_ok": true|false, "issues": "<short text>"} '
    "and no other text."
)


def _format_passages(passages):
    lines = []
    for i, p in enumerate(passages, start=1):
        header = f"[{i}] {p.file}"
        if p.heading:
            header += f": {p.heading}"
        lines.append(f"{header}\n{p.text}")
    return "\n---\n".join(lines)


def _parse(text):
    raw = text.strip()
    if raw.startswith('```'):
        raw = raw.strip('`')
        if raw.startswith('json'):
            raw = raw[4:]
        raw = raw.strip()
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError('not an object')
    except (ValueError, TypeError):
        return VerifierResult(grounded=False, citations_ok=False, issues='verifier parse error')
    return VerifierResult(
        grounded=bool(data.get('grounded')),
        citations_ok=bool(data.get('citations_ok')),
        issues=str(data.get('issues', '')),
    )


def verify(question, draft, passages):
    user_msg = (
        f"Question:\n{question}\n\n"
        f"Draft answer:\n{draft.answer}\n\n"
        f"Citations claimed: {draft.citations}\n\n"
        f"Passages:\n{_format_passages(passages)}"
    )
    resp = llm.call_claude(
        model=settings.DOCS_AGENT_CLASSIFIER_MODEL,
        system=VERIFIER_SYSTEM,
        messages=[{'role': 'user', 'content': user_msg}],
        max_tokens=400,
    )
    return _parse(resp.text)
