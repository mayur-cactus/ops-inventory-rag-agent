"""End-to-end smoke test. Run: docker compose run --rm agent python -m tests.smoke"""

from qdrant_client import QdrantClient

from app import config
from app.agent import NOT_FOUND, build_agent
from app.ingest import ingest_all

# (question, substrings that must all appear in the answer)
QUESTIONS = [
    ("Which PHP and Laravel version does the Discovery App backend use?", ["8.3.23", "12.62.0"]),
    ("What Postgres version does the Subscription service use?", ["17.5"]),
    ("Which AgentOS version does the ai-chat service use?", ["2.6.17"]),
]
UNANSWERABLE = "What is the CEO's favourite colour?"


def count_points(client: QdrantClient) -> int:
    return client.count(config.COLLECTION, exact=True).count


def test_ingest(client: QdrantClient) -> None:
    ingest_all()
    first = count_points(client)
    assert first > 0, "no points in the collection after ingest"
    ingest_all()
    second = count_points(client)
    assert second == first, f"re-ingest changed point count: {first} -> {second}"

    points, _ = client.scroll(config.COLLECTION, limit=1, with_payload=True)
    meta = points[0].payload["meta_data"]
    assert meta.get("source") and meta.get("page"), f"missing source/page: {meta}"
    print(f"ingest ok: {first} points, idempotent, payload has source+page")


def test_answers() -> None:
    agent = build_agent()
    failures = []
    for question, expected in QUESTIONS:
        answer = agent.run(question).content or ""
        missing = [e for e in expected if e not in answer]
        cited = ".pdf" in answer or "page" in answer.lower()
        status = "ok" if not missing and cited else "FAIL"
        print(f"[{status}] {question}\n    missing={missing} cited={cited}")
        if status == "FAIL":
            failures.append(question)
            print("    answer:", answer[:300].replace("\n", " "))

    answer = agent.run(UNANSWERABLE).content or ""
    if "couldn't find" in answer.lower() or "could not find" in answer.lower():
        print(f"[ok] unanswerable question refused: {NOT_FOUND}")
    else:
        failures.append(UNANSWERABLE)
        print("[FAIL] unanswerable question not refused:", answer[:300])

    assert not failures, f"{len(failures)} answer check(s) failed: {failures}"


if __name__ == "__main__":
    config.require_env()
    test_ingest(QdrantClient(url=config.QDRANT_URL))
    test_answers()
    print("smoke test passed")
