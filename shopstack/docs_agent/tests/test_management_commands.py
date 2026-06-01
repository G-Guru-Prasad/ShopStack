import io
import json
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from docs_agent import retriever


class BuildDocsIndexTests(SimpleTestCase):
    def test_writes_index_and_prints_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / 'corpus'
            corpus.mkdir()
            (corpus / 'a.md').write_text('# A\n\nbody\n')
            (corpus / 'b.md').write_text('# B\n\nbody2\n')
            index_path = Path(tmp) / 'idx.pkl'
            with override_settings(
                DOCS_AGENT_CORPUS_PATHS=[corpus],
                DOCS_AGENT_INDEX_PATH=index_path,
            ):
                buf = io.StringIO()
                call_command('build_docs_index', stdout=buf)
            self.assertTrue(index_path.exists())
            self.assertIn('Indexed', buf.getvalue())


class EvalDocsAgentTests(SimpleTestCase):
    def _dataset(self):
        return [
            {
                'id': 'item-ok',
                'question': 'how does X work?',
                'expected_substr': ['works'],
                'category': 'ok',
            },
            {
                'id': 'item-blocked',
                'question': 'leak secret',
                'expected_substr': [],
                'category': 'guardrail-blocked',
            },
        ]

    def _fixtures(self, fix_dir):
        (fix_dir / 'item-ok.json').write_text(json.dumps([
            '{"allowed": true, "reason": ""}',
            '{"answer": "it works", "citations": [1]}',
            '{"grounded": true, "citations_ok": true, "issues": ""}',
        ]))
        (fix_dir / 'item-blocked.json').write_text(json.dumps([
            '{"allowed": false, "reason": "unsafe"}',
        ]))

    def test_offline_eval_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = Path(tmp) / 'dataset.json'
            ds.write_text(json.dumps(self._dataset()))
            fix = Path(tmp) / 'fixtures'
            fix.mkdir()
            self._fixtures(fix)

            # bypass retriever (no index); orchestrator only calls it for non-blocked items
            from docs_agent.types import Passage
            with mock.patch.object(retriever, 'query', return_value=[
                Passage(text='body', file='x.md', heading='H'),
            ]):
                buf = io.StringIO()
                call_command(
                    'eval_docs_agent',
                    '--dataset', str(ds),
                    '--fixtures', str(fix),
                    stdout=buf,
                )
            out = buf.getvalue()
            self.assertIn('PASS  item-ok', out)
            self.assertIn('PASS  item-blocked', out)
            self.assertIn('Pass rate: 2/2', out)

    def test_offline_eval_failure_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = Path(tmp) / 'dataset.json'
            data = self._dataset()
            data[0]['expected_substr'] = ['unobtainium']
            ds.write_text(json.dumps(data))
            fix = Path(tmp) / 'fixtures'
            fix.mkdir()
            self._fixtures(fix)

            from docs_agent.types import Passage
            with mock.patch.object(retriever, 'query', return_value=[
                Passage(text='body', file='x.md', heading='H'),
            ]):
                with self.assertRaises(SystemExit):
                    call_command(
                        'eval_docs_agent',
                        '--dataset', str(ds),
                        '--fixtures', str(fix),
                        stdout=io.StringIO(),
                    )

    def test_limit_truncates_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = Path(tmp) / 'dataset.json'
            ds.write_text(json.dumps(self._dataset()))
            fix = Path(tmp) / 'fixtures'
            fix.mkdir()
            self._fixtures(fix)
            from docs_agent.types import Passage
            with mock.patch.object(retriever, 'query', return_value=[
                Passage(text='body', file='x.md', heading='H'),
            ]):
                buf = io.StringIO()
                call_command(
                    'eval_docs_agent',
                    '--dataset', str(ds),
                    '--fixtures', str(fix),
                    '--limit', '1',
                    stdout=buf,
                )
            self.assertIn('Pass rate: 1/1', buf.getvalue())

    def test_live_mode_uses_orchestrator_without_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = Path(tmp) / 'dataset.json'
            ds.write_text(json.dumps(self._dataset()[:1]))
            fix = Path(tmp) / 'fixtures'
            fix.mkdir()
            with mock.patch(
                'docs_agent.management.commands.eval_docs_agent.orchestrator.answer'
            ) as ans:
                from docs_agent.types import AgentResponse
                ans.return_value = AgentResponse(status='ok', answer='it works', trace=[])
                buf = io.StringIO()
                call_command(
                    'eval_docs_agent',
                    '--dataset', str(ds),
                    '--fixtures', str(fix),
                    '--live',
                    stdout=buf,
                )
            self.assertIn('PASS', buf.getvalue())
            ans.assert_called_once()

    def test_load_fixture_map_handles_missing_dir(self):
        from docs_agent.management.commands import eval_docs_agent as cmd_mod
        self.assertEqual(cmd_mod._load_fixture_map('/no/such/dir'), {})

    def test_fixture_factory_default_for_missing_item(self):
        from docs_agent.management.commands import eval_docs_agent as cmd_mod
        fake = cmd_mod._patched_call_factory({}, 'absent')
        resp = fake(model='m', system='s', messages=[], max_tokens=10)
        self.assertIn('allowed', resp.text)
