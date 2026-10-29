import hashlib
from pathlib import Path

from qdrant_client import QdrantClient, models

from app import config
from app.knowledge import check_qdrant, get_knowledge
from app.readers import TableAwareReader

# Bump when the reader's output changes so existing files are re-ingested.
READER_VERSION = "table-aware-v2"


def _file_hash(path: Path) -> str:
    return f"{hashlib.sha256(path.read_bytes()).hexdigest()}:{READER_VERSION}"


def _has_points(client: QdrantClient, key: str, value: str) -> bool:
    if not client.collection_exists(config.COLLECTION):
        return False
    points, _ = client.scroll(
        config.COLLECTION,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key=f"meta_data.{key}", match=models.MatchValue(value=value)
                )
            ]
        ),
        limit=1,
    )
    return bool(points)


def ingest_all() -> dict:
    config.require_env()
    check_qdrant()
    knowledge = get_knowledge()
    client = QdrantClient(url=config.QDRANT_URL)
    summary = {"ingested": [], "skipped": [], "failed": []}

    for pdf in sorted(Path(config.DOCS_DIR).glob("*.pdf")):
        try:
            digest = _file_hash(pdf)
            if _has_points(client, "content_hash", digest):
                summary["skipped"].append(pdf.name)
                continue
            if _has_points(client, "source", pdf.name):
                knowledge.remove_vectors_by_metadata({"source": pdf.name})
            knowledge.insert(
                name=pdf.name,
                path=str(pdf),
                reader=TableAwareReader(),
                metadata={"source": pdf.name, "content_hash": digest},
            )
            summary["ingested"].append(pdf.name)
        except Exception as exc:
            summary["failed"].append(f"{pdf.name}: {exc}")

    print(
        f"ingested={len(summary['ingested'])} "
        f"skipped={len(summary['skipped'])} failed={len(summary['failed'])}"
    )
    for item in summary["failed"]:
        print(f"  FAILED {item}")
    return summary


if __name__ == "__main__":
    ingest_all()
