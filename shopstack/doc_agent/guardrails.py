"""Input safety gate. Classifies a user question before retrieval/drafting."""
import json

from doc_agent import llm


SYSTEM_PROMPT = """You are a safety classifier for an internal developer
documentation assistant. Given a user question, decide whether it is safe to
answer using internal runbooks.

Refuse (allowed=false) when the question asks for:
- Secrets, credentials, passwords, API keys, or production database access.
- Destructive operations (deleting data, dropping tables, force-pushing).
- Personal or off-topic content unrelated to engineering documentation.

Approve (allowed=true) for engineering questions about deployment, rollback,
onboarding, architecture, runbooks, and similar operational topics.

Respond ONLY with a JSON object of the form:
{"allowed": bool, "reason": str, "intent": str, "topic": str}
"""


class Guardrails:
    def check(self, question, history):
        user_prompt = json.dumps({
            'question': question,
            'recent_history': history,
        })
        verdict = llm.complete_json(SYSTEM_PROMPT, user_prompt, max_tokens=512)
        return {
            'allowed': bool(verdict.get('allowed', False)),
            'reason': str(verdict.get('reason', '')),
            'intent': str(verdict.get('intent', '')),
            'topic': str(verdict.get('topic', '')),
        }
