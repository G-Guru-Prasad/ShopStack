"""Tests for the thin Anthropic SDK wrapper."""
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from doc_agent import llm


def _resp(text):
    block = SimpleNamespace(text=text)
    return SimpleNamespace(content=[block])


class CompleteJsonTests(SimpleTestCase):
    def setUp(self):
        llm._client = None

    def test_parses_plain_json(self):
        client = mock.Mock()
        client.messages.create.return_value = _resp('{"ok": true}')
        with mock.patch.object(llm, '_get_client', return_value=client):
            result = llm.complete_json('system', 'user')
        self.assertEqual(result, {'ok': True})

    def test_strips_code_fences(self):
        client = mock.Mock()
        client.messages.create.return_value = _resp(
            '```json\n{"value": 1}\n```',
        )
        with mock.patch.object(llm, '_get_client', return_value=client):
            result = llm.complete_json('system', 'user')
        self.assertEqual(result, {'value': 1})

    def test_invalid_json_raises(self):
        client = mock.Mock()
        client.messages.create.return_value = _resp('not json')
        with mock.patch.object(llm, '_get_client', return_value=client):
            with self.assertRaises(ValueError):
                llm.complete_json('system', 'user')

    def test_get_client_caches_instance(self):
        fake = object()
        with mock.patch('anthropic.Anthropic', return_value=fake) as ctor:
            self.assertIs(llm._get_client(), fake)
            self.assertIs(llm._get_client(), fake)
            ctor.assert_called_once()
