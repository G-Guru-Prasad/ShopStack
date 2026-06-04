"""Vector retrieval over DocumentChunk via pgvector cosine distance."""
from pgvector.django import CosineDistance

from doc_agent.models import DocumentChunk


def top_k(query_vector, k=6, similarity_floor=0.25):
    """Return up to k chunks ordered by cosine distance to query_vector.

    Chunks with cosine distance greater than (1 - similarity_floor) are
    dropped — cosine distance is in [0, 2] (0 = identical), so a similarity
    floor of 0.25 maps to a distance ceiling of 0.75.
    """
    distance_ceiling = 1.0 - similarity_floor
    qs = (
        DocumentChunk.objects
        .select_related('document')
        .annotate(distance=CosineDistance('embedding', query_vector))
        .filter(distance__lte=distance_ceiling)
        .order_by('distance')[:k]
    )
    return list(qs)
