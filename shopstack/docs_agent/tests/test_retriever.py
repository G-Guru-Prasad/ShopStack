import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from docs_agent import retriever


class RetrieverTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'a.md').write_text(
            '# Tenant Middleware\n\nThe TenantMiddleware reads the subdomain from HTTP_HOST '
            'and stores tenant_id in thread-local storage.\n'
        )
        (self.root / 'b.md').write_text(
            '# Orders\n\nOrder placement snapshots unit_price on each OrderItem.\n'
        )
        (self.root / 'c.md').write_text('plain body without heading content about taxes')
        self.index_path = self.root / 'idx.pkl'
        retriever._CACHE.update({'mtime': None, 'index': None, 'path': None})

    def test_build_index_writes_pickle(self):
        result = retriever.build_index([self.root], index_path=self.index_path)
        self.assertTrue(self.index_path.exists())
        self.assertGreaterEqual(result['chunks'], 3)
        self.assertEqual(result['files'], 3)

    def test_query_ranks_relevant_file_first(self):
        retriever.build_index([self.root], index_path=self.index_path)
        hits = retriever.query('tenant middleware subdomain', k=3, index_path=self.index_path)
        self.assertTrue(hits)
        self.assertIn('a.md', hits[0].file)

    def test_query_empty_string_returns_no_hits(self):
        retriever.build_index([self.root], index_path=self.index_path)
        self.assertEqual(retriever.query('   ', index_path=self.index_path), [])

    def test_build_index_raises_when_no_markdown(self):
        empty = Path(self.tmp.name) / 'empty'
        empty.mkdir()
        with self.assertRaises(RuntimeError):
            retriever.build_index([empty], index_path=self.index_path)

    def test_skips_nonexistent_paths(self):
        result = retriever.build_index(
            [self.root, self.root / 'does-not-exist'],
            index_path=self.index_path,
        )
        self.assertEqual(result['files'], 3)

    def test_load_index_caches_until_mtime_changes(self):
        retriever.build_index([self.root], index_path=self.index_path)
        first = retriever.load_index(self.index_path)
        second = retriever.load_index(self.index_path)
        self.assertIs(first, second)
        (self.root / 'd.md').write_text('# New\n\nfresh content about pricing\n')
        retriever.build_index([self.root], index_path=self.index_path)
        third = retriever.load_index(self.index_path)
        self.assertIsNot(first, third)

    def test_section_splitting_handles_preamble(self):
        f = self.root / 'pre.md'
        f.write_text('preamble text\n\n# Section\n\nbody about widgets\n')
        retriever.build_index([f], index_path=self.index_path)
        data = retriever.load_index(self.index_path)
        headings = {p.heading for p in data['passages']}
        self.assertIn('', headings)
        self.assertIn('Section', headings)

    def test_long_section_is_chunked(self):
        long = 'word ' * 400
        f = self.root / 'long.md'
        f.write_text('# Long\n\n' + long)
        retriever.build_index([f], index_path=self.index_path)
        data = retriever.load_index(self.index_path)
        chunks_for_long = [p for p in data['passages'] if 'long.md' in p.file]
        self.assertGreater(len(chunks_for_long), 1)

    def test_single_md_file_path_is_indexed(self):
        f = self.root / 'a.md'
        retriever.build_index([f], index_path=self.index_path)
        data = retriever.load_index(self.index_path)
        self.assertTrue(all('a.md' in p.file for p in data['passages']))
