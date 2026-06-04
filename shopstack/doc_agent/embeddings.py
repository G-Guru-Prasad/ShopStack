"""Voyage embedding client wrapper."""
from django.conf import settings


_client = None


def _get_client():
    global _client
    if _client is None:
        import voyageai
        _client = voyageai.Client(api_key=settings.VOYAGE_API_KEY)
    return _client


def embed_texts(texts, input_type='document'):
    """Return a list of embedding vectors for the given texts."""
    if not texts:
        return []
    client = _get_client()
    result = client.embed(
        texts,
        model=settings.DOC_AGENT_EMBEDDING_MODEL,
        input_type=input_type,
    )
    return result.embeddings


def embed_query(text):
    """Embed a single query string and return its vector."""
    vectors = embed_texts([text], input_type='query')
    return vectors[0]
