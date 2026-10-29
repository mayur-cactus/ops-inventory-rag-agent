from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.knowledge.knowledge import Knowledge
from agno.vectordb.qdrant import Qdrant
from agno.vectordb.search import SearchType
from qdrant_client import QdrantClient

from app import config


def check_qdrant() -> None:
    try:
        QdrantClient(url=config.QDRANT_URL, timeout=5).get_collections()
    except Exception as exc:
        raise SystemExit(
            f"Cannot reach Qdrant at {config.QDRANT_URL}: {exc}\n"
            "Make sure the Qdrant container is running and publishes port 6333."
        )


def get_knowledge() -> Knowledge:
    vector_db = Qdrant(
        collection=config.COLLECTION,
        url=config.QDRANT_URL,
        # Dense + BM25 (fastembed) fused with RRF: exact service names and acronyms
        # match on keywords, paraphrased questions match on embeddings.
        search_type=SearchType.hybrid,
        embedder=OpenAIEmbedder(
            id=config.EMBED_MODEL,
            dimensions=config.EMBED_DIMENSIONS,
            api_key=config.OPENAI_API_KEY,
        ),
    )
    return Knowledge(name=config.COLLECTION, vector_db=vector_db)
