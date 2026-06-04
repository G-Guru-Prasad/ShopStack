"""factory_boy fixtures for doc_agent models."""
import factory
from django.contrib.auth.models import User

from doc_agent.models import Conversation, Document, DocumentChunk, Message


EMBEDDING_DIMS = 1024


def _zero_vector():
    return [0.0] * EMBEDDING_DIMS


class DocAgentUserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ('username',)

    username = factory.Sequence(lambda n: f'docagent_user{n}')
    email = factory.LazyAttribute(lambda o: f'{o.username}@example.com')

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop('password', 'TestPass123!')
        manager = cls._get_manager(model_class)
        return manager.create_user(*args, password=password, **kwargs)


class DocumentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Document
        django_get_or_create = ('source_path',)

    source_path = factory.Sequence(lambda n: f'runbooks/doc-{n}.md')
    kind = Document.Kind.RUNBOOK
    content_hash = factory.Sequence(lambda n: f'{n:064d}')


class DocumentChunkFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DocumentChunk

    document = factory.SubFactory(DocumentFactory)
    chunk_index = factory.Sequence(lambda n: n)
    text = factory.Sequence(lambda n: f'Chunk text {n}')
    embedding = factory.LazyFunction(_zero_vector)
    start_line = 1
    end_line = 10


class ConversationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Conversation

    user = factory.SubFactory(DocAgentUserFactory)
    title = factory.Sequence(lambda n: f'Conversation {n}')


class MessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Message

    conversation = factory.SubFactory(ConversationFactory)
    role = Message.Role.USER
    content = factory.Sequence(lambda n: f'Message body {n}')
