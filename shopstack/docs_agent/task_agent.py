import json

from django.conf import settings

from docs_agent import llm
from docs_agent.types import Draft


TASK_SYSTEM_PREFIX = (
    "You answer questions about an internal codebase using only the numbered passages.\n"
    "Rules:\n"
    "- Use only facts present in the passages. If they don't contain the answer, say so plainly.\n"
    "- Cite each passage you used by its number (e.g. [1], [3]).\n"
    "- Respond as a single JSON object: "
    '{"answer": "<text>", "citations": [<int>, ...]} '
    "and no other text.\n"
)


def _format_passages(passages):
    lines = []
    for i, p in enumerate(passages, start=1):
        header = f"[{i}] {p.file}"
        if p.heading:
            header += f": {p.heading}"
        lines.append(f"{header}\n{p.text}")
    return "\n---\n".join(lines)


def _build_system(passages):
    return TASK_SYSTEM_PREFIX + "\nPassages:\n" + _format_passages(passages)


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
        return Draft(
            answer=str(data.get('answer', '')),
            citations=[int(c) for c in data.get('citations', []) if isinstance(c, (int, float))],
        )
    except (ValueError, TypeError):
        return Draft(answer=text.strip(), citations=[])


def draft_answer(question, passages, feedback=None):
    user_msg = question
    if feedback:
        user_msg = f"{question}\n\nPrior draft was rejected. Reviewer feedback:\n{feedback}"
    resp = llm.call_claude(
        model=settings.DOCS_AGENT_TASK_MODEL,
        system=_build_system(passages),
        messages=[{'role': 'user', 'content': user_msg}],
        max_tokens=1024,
    )
    return _parse(resp.text)
