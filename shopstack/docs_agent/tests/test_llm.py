from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, override_settings

from docs_agent import llm


def _fake_response():
    return SimpleNamespace(
        content=[SimpleNamespace(type='text', text='hello')],
        usage=SimpleNamespace(input_tokens=3, output_tokens=4),
        stop_reason='end_turn',
    )


@override_settings(ANTHROPIC_API_KEY='x')
class CallClaudeTests(SimpleTestCase):
    def setUp(self):
        llm._client = None

    def tearDown(self):
        llm._client = None

    def test_passes_string_system_as_cached_block(self):
        client = mock.Mock()
        client.messages.create.return_value = _fake_response()
        with mock.patch.object(llm, '_get_client', return_value=client):
            out = llm.call_claude(
                model='m',
                system='SYS',
                messages=[{'role': 'user', 'content': 'hi'}],
                max_tokens=10,
            )
        kwargs = client.messages.create.call_args.kwargs
        self.assertEqual(kwargs['system'], [{
            'type': 'text', 'text': 'SYS', 'cache_control': {'type': 'ephemeral'},
        }])
        self.assertEqual(out.text, 'hello')
        self.assertEqual(out.input_tokens, 3)
        self.assertEqual(out.output_tokens, 4)
        self.assertEqual(out.stop_reason, 'end_turn')

    def test_passes_through_block_list_system(self):
        client = mock.Mock()
        client.messages.create.return_value = _fake_response()
        blocks = [{'type': 'text', 'text': 'A'}]
        with mock.patch.object(llm, '_get_client', return_value=client):
            llm.call_claude(model='m', system=blocks, messages=[], max_tokens=1)
        self.assertEqual(client.messages.create.call_args.kwargs['system'], blocks)

    def test_handles_missing_usage(self):
        client = mock.Mock()
        client.messages.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(type='text', text='ok')],
            usage=None,
            stop_reason=None,
        )
        with mock.patch.object(llm, '_get_client', return_value=client):
            out = llm.call_claude(model='m', system='s', messages=[], max_tokens=1)
        self.assertEqual(out.input_tokens, 0)
        self.assertEqual(out.output_tokens, 0)
        self.assertEqual(out.stop_reason, '')

    def test_get_client_instantiates_once(self):
        fake_module = mock.Mock()
        fake_module.Anthropic.return_value = 'CLIENT'
        with mock.patch.dict('sys.modules', {'anthropic': fake_module}):
            self.assertEqual(llm._get_client(), 'CLIENT')
            self.assertEqual(llm._get_client(), 'CLIENT')
        fake_module.Anthropic.assert_called_once()
