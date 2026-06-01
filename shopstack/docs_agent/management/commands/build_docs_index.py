from django.conf import settings
from django.core.management.base import BaseCommand

from docs_agent import retriever


class Command(BaseCommand):
    help = 'Build the BM25 index over the configured markdown corpus paths.'

    def add_arguments(self, parser):
        parser.add_argument('--index-path', default=None)

    def handle(self, *args, **options):
        paths = settings.DOCS_AGENT_CORPUS_PATHS
        result = retriever.build_index(paths, index_path=options['index_path'])
        self.stdout.write(
            'Indexed %s chunks across %s files -> %s' % (
                result['chunks'], result['files'], result['path']
            )
        )
