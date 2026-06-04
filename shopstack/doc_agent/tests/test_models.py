from django.test import TestCase

from doc_agent.tests.factories import (
    ConversationFactory, DocumentChunkFactory, DocumentFactory, MessageFactory,
)


class ModelStringTests(TestCase):
    def test_document_str(self):
        doc = DocumentFactory(source_path='runbooks/deploy.md')
        self.assertEqual(str(doc), 'runbooks/deploy.md')

    def test_document_chunk_str(self):
        doc = DocumentFactory(source_path='runbooks/x.md')
        chunk = DocumentChunkFactory(document=doc, chunk_index=3)
        self.assertEqual(str(chunk), 'runbooks/x.md#3')

    def test_conversation_str_with_title(self):
        conv = ConversationFactory(title='How to deploy')
        self.assertEqual(str(conv), 'How to deploy')

    def test_conversation_str_without_title(self):
        conv = ConversationFactory(title='')
        self.assertTrue(str(conv).startswith('Conversation'))

    def test_message_str_truncates_content(self):
        long_text = 'x' * 100
        msg = MessageFactory(content=long_text)
        self.assertEqual(str(msg), f'user: {"x" * 40}')
