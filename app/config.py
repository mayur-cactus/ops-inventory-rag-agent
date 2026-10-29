import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
QDRANT_URL = os.getenv("QDRANT_URL", "http://host.docker.internal:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "ops_docs_hybrid")
DOCS_DIR = os.getenv("DOCS_DIR", "/data/documents")
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIMENSIONS = 1536
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o")


def require_env() -> None:
    if not OPENAI_API_KEY.strip():
        raise SystemExit(
            "OPENAI_API_KEY is empty. Copy .env.example to .env and set your key."
        )
