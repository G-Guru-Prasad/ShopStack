from django.test import TestCase

from doc_agent import retriever
from doc_agent.tests.factories import DocumentChunkFactory, DocumentFactory


def _vec(first, second=0.0):
    return [first, second] + [0.0] * 1022


class RetrieverTests(TestCase):
    def setUp(self):
        self.doc = DocumentFactory(source_path='runbooks/deploy.md')
        self.near = DocumentChunkFactory(
            document=self.doc, chunk_index=0,
            embedding=_vec(1.0, 0.0), text='near',
        )
        self.middle = DocumentChunkFactory(
            document=self.doc, chunk_index=1,
            embedding=_vec(0.7, 0.7), text='middle',
        )
        self.far = DocumentChunkFactory(
            document=self.doc, chunk_index=2,
            embedding=_vec(-1.0, 0.0), text='far',
        )

    def test_top_k_orders_by_cosine_distance(self):
        results = retriever.top_k(_vec(1.0), k=3, similarity_floor=-1.0)
        self.assertGreaterEqual(len(results), 2)
        self.assertEqual(results[0].id, self.near.id)
        self.assertEqual(results[1].id, self.middle.id)

    def test_similarity_floor_drops_distant_chunks(self):
        results = retriever.top_k(_vec(1.0), k=3, similarity_floor=0.5)
        ids = [r.id for r in results]
        self.assertIn(self.near.id, ids)
        self.assertNotIn(self.far.id, ids)

    def test_no_chunks_returns_empty(self):
        from doc_agent.models import DocumentChunk
        DocumentChunk.objects.all().delete()
        self.assertEqual(retriever.top_k(_vec(1.0)), [])
