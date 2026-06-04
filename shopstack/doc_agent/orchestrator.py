"""Pipeline coordinator. Wires Guardrails + Retriever + TaskAgent + Verifier."""
from dataclasses import dataclass

from django.db import transaction

from doc_agent import embeddings, retriever
from doc_agent.guardrails import Guardrails
from doc_agent.models import Conversation, DocumentChunk, Message
from doc_agent.task_agent import TaskAgent
from doc_agent.verifier import Verifier


MAX_REVISIONS = 2
HISTORY_WINDOW = 4
RETRIEVAL_TOP_K = 6
SIMILARITY_FLOOR = 0.25
REFUSAL_TEMPLATE = (
    'I can\'t help with that request. Reason: {reason}'
)
NO_DOCS_MESSAGE = "I don't have docs on that."


@dataclass
class Citation:
    chunk_id: int
    source_path: str
    start_line: int
    end_line: int
    snippet: str


@dataclass
class AssistantResponse:
    message_id: int
    conversation_id: int
    answer: str
    citations: list
    not_fully_verified: bool


def _serialize_history(conversation):
    if conversation is None:
        return []
    qs = conversation.messages.order_by('-created_at')[:HISTORY_WINDOW]
    items = [{'role': m.role, 'content': m.content} for m in qs]
    items.reverse()
    return items


def _build_citations(chunks):
    return [
        Citation(
            chunk_id=chunk.id,
            source_path=chunk.document.source_path,
            start_line=chunk.start_line or 0,
            end_line=chunk.end_line or 0,
            snippet=chunk.text[:200],
        )
        for chunk in chunks
    ]


class Orchestrator:
    def __init__(self, guardrails=None, task_agent=None, verifier=None):
        self.guardrails = guardrails or Guardrails()
        self.task_agent = task_agent or TaskAgent()
        self.verifier = verifier or Verifier()

    def _load_conversation(self, user, conversation_id):
        if conversation_id:
            return Conversation.objects.filter(
                pk=conversation_id, user=user,
            ).first()
        return None

    def _persist_assistant(self, conversation, answer, chunks=None,
                           guardrails_verdict=None, verifier_verdict=None,
                           not_fully_verified=False):
        with transaction.atomic():
            msg = Message.objects.create(
                conversation=conversation,
                role=Message.Role.ASSISTANT,
                content=answer,
                guardrails_verdict=guardrails_verdict,
                verifier_verdict=verifier_verdict,
                not_fully_verified=not_fully_verified,
            )
            if chunks:
                msg.cited_chunks.set(chunks)
            conversation.save(update_fields=['updated_at'])
        return msg

    def run(self, user, question, conversation_id=None):
        conversation = self._load_conversation(user, conversation_id)
        if conversation is None:
            conversation = Conversation.objects.create(
                user=user, title=question[:80],
            )

        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content=question,
        )

        history = _serialize_history(conversation)
        guard_verdict = self.guardrails.check(question, history)
        if not guard_verdict['allowed']:
            answer = REFUSAL_TEMPLATE.format(
                reason=guard_verdict['reason'] or 'request blocked by policy',
            )
            msg = self._persist_assistant(
                conversation, answer,
                guardrails_verdict=guard_verdict,
            )
            return AssistantResponse(
                message_id=msg.id,
                conversation_id=conversation.id,
                answer=answer,
                citations=[],
                not_fully_verified=False,
            )

        query_vec = embeddings.embed_query(question)
        chunks = retriever.top_k(
            query_vec, k=RETRIEVAL_TOP_K, similarity_floor=SIMILARITY_FLOOR,
        )
        if not chunks:
            msg = self._persist_assistant(
                conversation, NO_DOCS_MESSAGE,
                guardrails_verdict=guard_verdict,
            )
            return AssistantResponse(
                message_id=msg.id,
                conversation_id=conversation.id,
                answer=NO_DOCS_MESSAGE,
                citations=[],
                not_fully_verified=False,
            )

        verifier_feedback = None
        draft = None
        verify_verdict = None
        used_chunks = []
        not_fully_verified = False
        for attempt in range(MAX_REVISIONS + 1):
            draft = self.task_agent.draft(
                question, chunks, history,
                verifier_feedback=verifier_feedback,
            )
            used_ids = draft['used_chunk_ids']
            used_chunks = [c for c in chunks if c.id in used_ids] or chunks
            verify_verdict = self.verifier.check(
                draft['draft_answer'], used_chunks,
            )
            if verify_verdict['grounded']:
                break
            if verify_verdict['revised_answer']:
                draft['draft_answer'] = verify_verdict['revised_answer']
                break
            verifier_feedback = verify_verdict['issues']
        else:
            not_fully_verified = True

        if not verify_verdict['grounded'] and not verify_verdict['revised_answer']:
            not_fully_verified = True

        answer = draft['draft_answer']
        msg = self._persist_assistant(
            conversation, answer,
            chunks=used_chunks,
            guardrails_verdict=guard_verdict,
            verifier_verdict=verify_verdict,
            not_fully_verified=not_fully_verified,
        )
        citations = _build_citations(used_chunks)
        return AssistantResponse(
            message_id=msg.id,
            conversation_id=conversation.id,
            answer=answer,
            citations=citations,
            not_fully_verified=not_fully_verified,
        )
