"""Ingest the curated corpus folder into the vector store."""
import hashlib
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from doc_agent import embeddings
from doc_agent.chunker import split_document
from doc_agent.models import Document, DocumentChunk


SUPPORTED_EXTENSIONS = ('.md', '.txt', '.docx')
EMBED_BATCH_SIZE = 32


def _read_text(path):
    if path.suffix.lower() == '.docx':
        import docx
        document = docx.Document(str(path))
        return '\n'.join(p.text for p in document.paragraphs)
    return path.read_text(encoding='utf-8')


def _sha256_file(path):
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _kind_for(relative_path):
    top = relative_path.parts[0] if relative_path.parts else ''
    mapping = {
        'runbooks': Document.Kind.RUNBOOK,
        'onboarding': Document.Kind.ONBOARDING,
        'architecture': Document.Kind.ARCHITECTURE,
    }
    return mapping.get(top, Document.Kind.OTHER)


def _batched(iterable, size):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


class Command(BaseCommand):
    help = 'Ingest the doc_agent corpus folder into pgvector.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='Re-embed every file even if its hash is unchanged.',
        )

    def handle(self, *args, **options):
        corpus_dir = Path(settings.DOC_AGENT_CORPUS_DIR)
        if not corpus_dir.exists():
            self.stdout.write(self.style.WARNING(
                f'Corpus dir does not exist: {corpus_dir}',
            ))
            return

        force = options['force']
        seen_paths = set()
        added = updated = unchanged = 0

        for path in sorted(corpus_dir.rglob('*')):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            relative = path.relative_to(corpus_dir)
            seen_paths.add(str(relative))
            content_hash = _sha256_file(path)
            existing = Document.objects.filter(source_path=str(relative)).first()
            if existing and existing.content_hash == content_hash and not force:
                unchanged += 1
                continue

            text = _read_text(path)
            is_markdown = path.suffix.lower() == '.md'
            chunks = split_document(text, is_markdown=is_markdown)
            if not chunks:
                continue

            chunk_texts = [c.text for c in chunks]
            vectors = []
            for batch in _batched(chunk_texts, EMBED_BATCH_SIZE):
                vectors.extend(embeddings.embed_texts(batch))

            with transaction.atomic():
                doc, created = Document.objects.update_or_create(
                    source_path=str(relative),
                    defaults={
                        'kind': _kind_for(relative),
                        'content_hash': content_hash,
                    },
                )
                DocumentChunk.objects.filter(document=doc).delete()
                DocumentChunk.objects.bulk_create([
                    DocumentChunk(
                        document=doc,
                        chunk_index=idx,
                        text=chunk.text,
                        embedding=vector,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                    )
                    for idx, (chunk, vector) in enumerate(zip(chunks, vectors))
                ])

            if created:
                added += 1
            else:
                updated += 1

        stale = Document.objects.exclude(source_path__in=seen_paths)
        removed = stale.count()
        stale.delete()

        self.stdout.write(self.style.SUCCESS(
            f'Ingest summary — added: {added}, updated: {updated}, '
            f'unchanged: {unchanged}, removed: {removed}',
        ))
