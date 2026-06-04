"""Grounding verifier. Checks whether the draft is supported by chunks."""
import json

from doc_agent import llm


SYSTEM_PROMPT = """You are a grounding verifier. You receive a draft answer
and the chunks the drafter relied on. Decide whether every factual claim in
the draft is supported by the chunks.

List unsupported claims in `issues`. If you can produce a corrected answer
using only the chunks, set `revised_answer` to that corrected text;
otherwise leave it null.

Respond ONLY with a JSON object of the form:
{"grounded": bool, "issues": [str, ...], "revised_answer": str | null}
"""


def _format_chunks(chunks):
    return [
        {'id': chunk.id, 'source': chunk.document.source_path, 'text': chunk.text}
        for chunk in chunks
    ]


class Verifier:
    def check(self, draft_answer, used_chunks):
        user_prompt = json.dumps({
            'draft_answer': draft_answer,
            'chunks': _format_chunks(used_chunks),
        })
        result = llm.complete_json(SYSTEM_PROMPT, user_prompt, max_tokens=1024)
        revised = result.get('revised_answer')
        return {
            'grounded': bool(result.get('grounded', False)),
            'issues': [str(x) for x in result.get('issues', [])],
            'revised_answer': str(revised) if revised else None,
        }
