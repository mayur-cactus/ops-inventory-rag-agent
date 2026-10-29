# Tech Inventory RAG Agent

Ask questions about the PDFs in `documents/`. An [Agno](https://docs.agno.com) agent
retrieves from a Qdrant vector store (OpenAI embeddings) and answers with the source
file and page.

## Prerequisites

- Docker with Compose v2.
- An OpenAI API key.

Qdrant is part of the compose file and starts automatically with the agent. Its data
lives in the `qdrant_data` Docker volume, so it survives restarts. Everyone running the
project has their own copy of the vectors; the first run ingests the PDFs, which takes a
couple of minutes.

## Setup

```bash
cp .env.example .env        # then set OPENAI_API_KEY in .env
docker compose build agent
```

Put your PDFs in `documents/`. They are mounted read-only into the container.

## Run

Terminal chat (type `exit` to quit):

```bash
docker compose run --rm agent python rag_agent.py
```

AgentOS API on http://localhost:7777. There is no UI at that address (it serves JSON and
an API explorer at `/docs`). The chat UI is Agno's hosted one at https://os.agno.com:
add `http://localhost:7777` there as a local endpoint, then pick the agent. Your browser
must allow that site to call `localhost` (Safari and Brave may block it):

```bash
docker compose run --rm --service-ports agent python rag_agent.py --serve
```

`--service-ports` is required, because `docker compose run` does not publish ports
otherwise. If 7777 is taken, set `AGENT_PORT=8000` in `.env`.

Both commands first ingest any new or changed PDFs, then start. Add `--skip-ingest` to
skip that step.

## Adding documents

Drop new PDFs in `documents/` and run either command above. Unchanged files are skipped
(matched by content hash), a changed file replaces its old vectors. To ingest without
starting the agent:

```bash
docker compose run --rm agent python -m app.ingest
```

## Tests

```bash
docker compose run --rm agent python -m tests.smoke
```

Checks that ingest is idempotent, that three known questions are answered with a
citation, and that an unanswerable question is refused. It calls the OpenAI API.

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | none, required | Chat and embeddings |
| `QDRANT_COLLECTION` | `ops_docs_hybrid` | Collection name (hybrid dense + BM25 vectors) |
| `CHAT_MODEL` | `gpt-4o` | OpenAI chat model |
| `AGENT_PORT` | `7777` | Host port for `--serve` |
| `QDRANT_PORT` | `6339` | Host port for the Qdrant dashboard (`http://localhost:6339/dashboard`) |

The agent talks to Qdrant over the compose network, so `QDRANT_PORT` only moves the
dashboard. Change it if 6339 is taken.

To use an external Qdrant instead of the bundled one, change `QDRANT_URL` under the
`agent` service in `docker-compose.yml` (for example `http://host.docker.internal:6333`).
On Linux, `host.docker.internal` works through the `host-gateway` mapping there.

Reset the index with `docker compose down -v` (this also deletes the Qdrant volume).

## How it works

- `app/readers.py`: PDF reader built on pdfplumber. The inventory PDFs are slide-style
  tables, and the default reader loses the row structure, so this one emits one chunk per
  table row.
- `app/ingest.py`: loads PDFs into Qdrant. If you change the reader's output, bump
  `READER_VERSION` so existing files are re-ingested.
- `app/agent.py`: the agent and its instructions (answer only from documents, cite file
  and page).
- `rag_agent.py`: entrypoint for chat and `--serve`.

## Known limits

- Digital PDFs only. Scanned PDFs need OCR, which is not included.
- Tables on pages with unusual layouts (merged cells) can produce noisy rows. Answers
  about those pages are less reliable.
