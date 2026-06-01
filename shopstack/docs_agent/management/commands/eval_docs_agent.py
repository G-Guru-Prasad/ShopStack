import json
import sys
from pathlib import Path
from unittest import mock

from django.core.management.base import BaseCommand

from docs_agent import orchestrator
from docs_agent.types import ClaudeResponse


DEFAULT_DATASET = Path(__file__).resolve().parent.parent.parent / 'eval' / 'dataset.json'
DEFAULT_FIXTURES = Path(__file__).resolve().parent.parent.parent / 'eval' / 'fixtures'


def _load_fixture_map(fixtures_dir):
    mapping = {}
    fixtures_dir = Path(fixtures_dir)
    if not fixtures_dir.exists():
        return mapping
    for f in sorted(fixtures_dir.glob('*.json')):
        with f.open() as fh:
            mapping[f.stem] = json.load(fh)
    return mapping


def _patched_call_factory(fixture_map, item_id):
    seq = list(fixture_map.get(item_id, []))

    def fake_call_claude(*, model, system, messages, max_tokens, temperature=0):
        if not seq:
            return ClaudeResponse(text='{"allowed": true, "reason": ""}')
        nxt = seq.pop(0)
        return ClaudeResponse(text=nxt)

    return fake_call_claude


def _check(item, result):
    if item.get('category') == 'guardrail-blocked':
        return result.status == 'blocked'
    answer_lower = (result.answer or '').lower()
    for needle in item.get('expected_substr', []):
        if needle.lower() not in answer_lower:
            return False
    return True


class Command(BaseCommand):
    help = 'Run the docs agent eval suite.'

    def add_arguments(self, parser):
        parser.add_argument('--dataset', default=str(DEFAULT_DATASET))
        parser.add_argument('--fixtures', default=str(DEFAULT_FIXTURES))
        parser.add_argument('--live', action='store_true')
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **options):
        with open(options['dataset']) as fh:
            dataset = json.load(fh)
        if options['limit'] is not None:
            dataset = dataset[:options['limit']]

        fixtures = {} if options['live'] else _load_fixture_map(options['fixtures'])
        passed = 0
        for item in dataset:
            if options['live']:
                result = orchestrator.answer(item['question'])
            else:
                fake = _patched_call_factory(fixtures, item['id'])
                with mock.patch('docs_agent.llm.call_claude', side_effect=fake):
                    result = orchestrator.answer(item['question'])
            ok = _check(item, result)
            passed += int(ok)
            self.stdout.write('%s  %s  %s' % ('PASS' if ok else 'FAIL', item['id'], result.status))

        total = len(dataset)
        rate = passed / total if total else 0.0
        self.stdout.write('Pass rate: %d/%d (%.1f%%)' % (passed, total, rate * 100))
        if not options['live'] and rate < 0.8:
            sys.exit(1)
