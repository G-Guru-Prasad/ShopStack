"""Tests for the Voyage embedding wrapper."""
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from doc_agent import embeddings


class EmbedTextsTests(SimpleTestCase):
    def setUp(self):
        embeddings._client = None

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(embeddings.embed_texts([]), [])

    def test_embed_texts_calls_client(self):
        client = mock.Mock()
        client.embed.return_value = SimpleNamespace(
            embeddings=[[0.1] * 4, [0.2] * 4],
        )
        with mock.patch.object(embeddings, '_get_client', return_value=client):
            result = embeddings.embed_texts(['a', 'b'])
        self.assertEqual(len(result), 2)
        client.embed.assert_called_once()

    def test_embed_query_returns_single_vector(self):
        client = mock.Mock()
        client.embed.return_value = SimpleNamespace(
            embeddings=[[0.5] * 4],
        )
        with mock.patch.object(embeddings, '_get_client', return_value=client):
            vector = embeddings.embed_query('hello')
        self.assertEqual(vector, [0.5] * 4)

    def test_get_client_caches(self):
        fake = object()
        with mock.patch('voyageai.Client', return_value=fake) as ctor:
            self.assertIs(embeddings._get_client(), fake)
            self.assertIs(embeddings._get_client(), fake)
            ctor.assert_called_once()
