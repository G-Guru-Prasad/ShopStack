"""Drafting agent. Composes an answer grounded in retrieved chunks."""
import json

from doc_agent import llm


SYSTEM_PROMPT = """You are a documentation assistant. Answer the user question
using ONLY the provided chunks. Cite each chunk you rely on inline using the
marker [chunk:<id>]. If the chunks do not cover the question, reply exactly
"I don't have docs on that." Keep answers short and operational.

Respond ONLY with a JSON object of the form:
{"draft_answer": str, "used_chunk_ids": [int, ...]}
"""


def _format_chunks(chunks):
    return [
        {
            'id': chunk.id,
            'source': chunk.document.source_path,
            'text': chunk.text,
        }
        for chunk in chunks
    ]


class TaskAgent:
    def draft(self, question, chunks, history, verifier_feedback=None):
        user_prompt = json.dumps({
            'question': question,
            'chunks': _format_chunks(chunks),
            'recent_history': history,
            'verifier_feedback': verifier_feedback,
        })
        result = llm.complete_json(SYSTEM_PROMPT, user_prompt, max_tokens=1024)
        return {
            'draft_answer': str(result.get('draft_answer', '')),
            'used_chunk_ids': [int(x) for x in result.get('used_chunk_ids', [])],
        }
