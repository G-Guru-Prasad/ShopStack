from django.test import SimpleTestCase

from doc_agent.chunker import (
    OVERLAP_CHARS, TARGET_CHARS, Chunk, split_document,
)


class ChunkerTests(SimpleTestCase):
    def test_markdown_splits_on_headings(self):
        text = (
            '# Intro\n'
            'Intro paragraph.\n'
            '## Setup\n'
            'Setup paragraph.\n'
            '## Deploy\n'
            'Deploy paragraph.\n'
        )
        chunks = split_document(text, is_markdown=True)
        self.assertEqual(len(chunks), 3)
        self.assertIn('Intro', chunks[0].text)
        self.assertIn('Setup', chunks[1].text)
        self.assertIn('Deploy', chunks[2].text)

    def test_start_line_is_one_for_first_chunk(self):
        text = '# Heading\nbody text\n## Other\nmore body\n'
        chunks = split_document(text, is_markdown=True)
        self.assertEqual(chunks[0].start_line, 1)

    def test_long_section_falls_back_to_windowed_split(self):
        body = 'a' * (TARGET_CHARS * 2 + 100)
        text = f'# Big\n{body}\n'
        chunks = split_document(text, is_markdown=True)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.text), TARGET_CHARS)

    def test_windowed_chunks_overlap(self):
        body = 'b' * (TARGET_CHARS * 3)
        chunks = split_document(body, is_markdown=False)
        self.assertGreater(len(chunks), 2)
        for first, second in zip(chunks, chunks[1:]):
            self.assertGreaterEqual(OVERLAP_CHARS, 0)
            tail = first.text[-OVERLAP_CHARS:]
            head = second.text[:OVERLAP_CHARS]
            self.assertEqual(tail, head)

    def test_non_markdown_input_uses_windowed_split(self):
        text = 'hello world\nthis is a plain text doc without headings'
        chunks = split_document(text, is_markdown=False)
        self.assertEqual(len(chunks), 1)
        self.assertIsInstance(chunks[0], Chunk)

    def test_empty_input_returns_empty(self):
        self.assertEqual(split_document('', is_markdown=True), [])
        self.assertEqual(split_document('   \n  \n', is_markdown=False), [])
