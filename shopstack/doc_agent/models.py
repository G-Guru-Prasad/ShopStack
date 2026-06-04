from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField


class Document(models.Model):
    class Kind(models.TextChoices):
        RUNBOOK = 'runbook', 'Runbook'
        ONBOARDING = 'onboarding', 'Onboarding'
        ARCHITECTURE = 'architecture', 'Architecture'
        OTHER = 'other', 'Other'

    source_path = models.CharField(max_length=512, unique=True)
    kind = models.CharField(
        max_length=20, choices=Kind.choices, default=Kind.OTHER,
    )
    content_hash = models.CharField(max_length=64)
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'doc_agent_documents'

    def __str__(self):
        return self.source_path


class DocumentChunk(models.Model):
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='chunks',
    )
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    embedding = VectorField(dimensions=settings.DOC_AGENT_EMBEDDING_DIMS)
    start_line = models.PositiveIntegerField(null=True, blank=True)
    end_line = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'doc_agent_document_chunks'
        unique_together = [('document', 'chunk_index')]
        indexes = [
            HnswIndex(
                name='doc_chunk_embedding_hnsw',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
        ]

    def __str__(self):
        return f'{self.document.source_path}#{self.chunk_index}'


class Conversation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='doc_agent_conversations',
    )
    title = models.CharField(max_length=80, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'doc_agent_conversations'
        ordering = ['-updated_at']

    def __str__(self):
        return self.title or f'Conversation {self.pk}'


class Message(models.Model):
    class Role(models.TextChoices):
        USER = 'user', 'User'
        ASSISTANT = 'assistant', 'Assistant'
        SYSTEM = 'system', 'System'

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages',
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    cited_chunks = models.ManyToManyField(
        DocumentChunk, blank=True, related_name='cited_in_messages',
    )
    guardrails_verdict = models.JSONField(null=True, blank=True)
    verifier_verdict = models.JSONField(null=True, blank=True)
    not_fully_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'doc_agent_messages'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.role}: {self.content[:40]}'
