import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from doc_agent.models import Document, DocumentChunk


def _fake_embed(texts, input_type='document'):
    return [[0.1] * 1024 for _ in texts]


class IngestDocsCommandTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.corpus = Path(self.tmp.name)
        (self.corpus / 'runbooks').mkdir()
        (self.corpus / 'runbooks' / 'deploy.md').write_text(
            '# Deploy\n\nRun `./deploy.sh staging`.\n',
        )
        (self.corpus / 'onboarding').mkdir()
        (self.corpus / 'onboarding' / 'welcome.txt').write_text(
            'Welcome aboard.\n',
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, **kwargs):
        with override_settings(DOC_AGENT_CORPUS_DIR=self.corpus):
            with mock.patch(
                'doc_agent.management.commands.ingest_docs.embeddings.embed_texts',
                side_effect=_fake_embed,
            ):
                call_command('ingest_docs', **kwargs)

    def test_fresh_ingest_creates_documents(self):
        self._run()
        self.assertEqual(Document.objects.count(), 2)
        deploy = Document.objects.get(source_path='runbooks/deploy.md')
        self.assertEqual(deploy.kind, Document.Kind.RUNBOOK)
        self.assertGreater(deploy.chunks.count(), 0)
        welcome = Document.objects.get(source_path='onboarding/welcome.txt')
        self.assertEqual(welcome.kind, Document.Kind.ONBOARDING)

    def test_unchanged_file_skipped(self):
        self._run()
        hash_before = Document.objects.get(
            source_path='runbooks/deploy.md',
        ).content_hash
        self._run()
        hash_after = Document.objects.get(
            source_path='runbooks/deploy.md',
        ).content_hash
        self.assertEqual(hash_before, hash_after)
        self.assertEqual(Document.objects.count(), 2)

    def test_modified_file_re_chunks(self):
        self._run()
        original_chunk_count = DocumentChunk.objects.count()
        (self.corpus / 'runbooks' / 'deploy.md').write_text(
            '# Deploy\n\nUpdated body with more lines.\nLine 2.\nLine 3.\n',
        )
        self._run()
        deploy = Document.objects.get(source_path='runbooks/deploy.md')
        self.assertGreater(deploy.chunks.count(), 0)
        self.assertGreaterEqual(
            DocumentChunk.objects.count(), original_chunk_count,
        )

    def test_deleted_file_purged(self):
        self._run()
        (self.corpus / 'onboarding' / 'welcome.txt').unlink()
        self._run()
        self.assertFalse(
            Document.objects.filter(
                source_path='onboarding/welcome.txt',
            ).exists(),
        )

    def test_force_reingests(self):
        self._run()
        with override_settings(DOC_AGENT_CORPUS_DIR=self.corpus):
            with mock.patch(
                'doc_agent.management.commands.ingest_docs.embeddings.embed_texts',
                side_effect=_fake_embed,
            ) as embed:
                call_command('ingest_docs', force=True)
                self.assertGreater(embed.call_count, 0)

    def test_missing_corpus_dir_warns(self):
        with override_settings(DOC_AGENT_CORPUS_DIR=Path('/nonexistent/path')):
            call_command('ingest_docs')
        self.assertEqual(Document.objects.count(), 0)

    def test_unsupported_extension_skipped(self):
        (self.corpus / 'runbooks' / 'image.png').write_bytes(b'\x89PNG\r\n')
        self._run()
        self.assertFalse(
            Document.objects.filter(
                source_path='runbooks/image.png',
            ).exists(),
        )

    def test_empty_file_skipped(self):
        (self.corpus / 'runbooks' / 'blank.md').write_text('   \n\n  \n')
        self._run()
        self.assertFalse(
            Document.objects.filter(
                source_path='runbooks/blank.md',
            ).exists(),
        )

    def test_docx_file_extracted(self):
        fake_paragraphs = [
            mock.Mock(text='First paragraph from docx.'),
            mock.Mock(text='Second paragraph with more body content.'),
        ]
        fake_doc = mock.Mock(paragraphs=fake_paragraphs)
        (self.corpus / 'architecture').mkdir()
        (self.corpus / 'architecture' / 'spec.docx').write_bytes(b'PK\x03\x04')
        with override_settings(DOC_AGENT_CORPUS_DIR=self.corpus):
            with mock.patch(
                'doc_agent.management.commands.ingest_docs.embeddings.embed_texts',
                side_effect=_fake_embed,
            ), mock.patch(
                'docx.Document', return_value=fake_doc,
            ):
                call_command('ingest_docs')
        doc = Document.objects.get(source_path='architecture/spec.docx')
        self.assertEqual(doc.kind, Document.Kind.ARCHITECTURE)
        self.assertGreater(doc.chunks.count(), 0)
        chunk_text = doc.chunks.first().text
        self.assertIn('First paragraph', chunk_text)

    def test_batches_embedding_calls_for_many_chunks(self):
        from doc_agent.management.commands import ingest_docs as cmd_module

        big_body = '\n\n'.join(
            f'# Section {i}\n' + ('content body. ' * 200)
            for i in range(40)
        )
        (self.corpus / 'runbooks' / 'big.md').write_text(big_body)
        with override_settings(DOC_AGENT_CORPUS_DIR=self.corpus):
            with mock.patch.object(
                cmd_module, 'EMBED_BATCH_SIZE', 5,
            ), mock.patch(
                'doc_agent.management.commands.ingest_docs.embeddings.embed_texts',
                side_effect=_fake_embed,
            ) as embed:
                call_command('ingest_docs')
        self.assertGreater(embed.call_count, 1)
