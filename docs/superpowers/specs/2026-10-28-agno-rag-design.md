# Agno RAG Agent over Local PDFs: Design

Date: 2026-10-28

## Goal

Build a RAG agent that answers questions about the PDF documents in `/var/www/agno-rag`, using Agno for the agent and knowledge layer, OpenAI for chat and embeddings, and the existing Qdrant instance (Docker, `http://localhost:6333`, no API key) for vector storage. The user chats with the agent through the Agno AgentOS web UI.

## Decisions

| Topic | Decision |
|---|---|
| Framework | Agno (`Knowledge`, `Agent`, `AgentOS`) |
| LLM | OpenAI chat model |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims) |
| Vector store | Qdrant at `http://localhost:6333`, collection `ops_docs` |
| Interface | Terminal chat by default; AgentOS UI with `--serve` |
| Documents | PDFs only, in the project folder; more will be added over time |
| Runtime | Docker (Python 3.12 image), shareable with teammates |
| Entrypoint | `docker compose run --rm agent python rag_agent.py` |
| Qdrant link | `http://host.docker.internal:6333` (existing Qdrant container's published port) |

Initial document: `OPS-Tech Inventory across BUs-281026-113924.pdf` (~1.4 MB, likely table-heavy).

## Approach

Use Agno's built-in `Knowledge` + `Qdrant` + `PDFReader`. The reader is isolated in one module so it can be swapped for a table-aware parser (e.g. pdfplumber) if retrieval over table rows proves poor. That swap changes only the ingest path, not the agent or the store.

## Layout

```
/var/www/agno-rag/
  documents/            # PDFs go here (mounted read-only into the container)
  docs/superpowers/     # this spec and the plan
  Dockerfile
  docker-compose.yml    # service `agent`
  .env.example          # committed template; real .env is git-ignored
  .dockerignore
  pyproject.toml / uv.lock
  rag_agent.py          # entrypoint: ingest new PDFs, then chat (default) or --serve
  app/
    config.py           # env loading, collection name, embedder settings
    knowledge.py        # builds Knowledge(Qdrant + OpenAIEmbedder)
    ingest.py           # ingest every PDF in the documents folder
    agent.py            # Agent(OpenAI model, knowledge, search_knowledge=True)
  tests/
    smoke.py
```

The existing PDF moves to `documents/` (a separate folder from `docs/`, which holds the spec and plan) so that only PDFs are mounted into the container.

## Docker and sharing

- **Dockerfile**: `python:3.12-slim`, installs dependencies with `uv` from the lockfile, copies `app/` and `rag_agent.py`. No secrets and no PDFs are baked into the image.
- **docker-compose.yml**: one service `agent` with `env_file: .env`, `./documents:/data/documents:ro`, `QDRANT_URL=http://host.docker.internal:6333`, `extra_hosts: ["host.docker.internal:host-gateway"]` (needed on Linux; harmless on Docker Desktop), `stdin_open` and `tty` for chat, and port `7777:7777` published for `--serve`.
- **Qdrant** is not part of this compose file. Each teammate needs a Qdrant container publishing 6333 on their own machine; the README gives the one-line `docker run` for it.
- **Usage**:
  - Chat: `docker compose run --rm agent python rag_agent.py`
  - UI: `docker compose run --rm --service-ports agent python rag_agent.py --serve`
- `rag_agent.py` ingests any new or changed PDFs on startup (idempotent), so a teammate needs only a filled `.env` and the PDFs.
- Teammates share the Qdrant collection only if they point at the same Qdrant; with a local one each person ingests their own copy.

## Components

- **config.py**: loads `.env`, exposes `OPENAI_API_KEY`, `QDRANT_URL`, `COLLECTION`, `DOCS_DIR`. Fails fast when `OPENAI_API_KEY` is missing.
- **knowledge.py**: the only module that constructs the Qdrant vector DB and embedder. Exposes `get_knowledge()`.
- **rag_agent.py**: parses `--serve`, runs ingest, then starts either `agent.cli_app()` style terminal chat or AgentOS on `0.0.0.0:7777`.
- **ingest.py**: scans `DOCS_DIR` (`/data/documents` in the container) for `*.pdf`. Each file is tagged in metadata with its name and a content hash. A file whose hash is already in the collection is skipped, so re-running only processes new or changed files. A changed file replaces its previous points.
- **agent.py**: Agno agent with an OpenAI chat model and `search_knowledge=True`. The system prompt tells it to answer only from retrieved content, cite source file and page, and say "not found in the documents" when retrieval returns nothing relevant.

## Data flow

Ingest: PDF → `PDFReader` chunks → OpenAI embeddings → Qdrant points with metadata (file name, hash, page).

Query: question → embed → Qdrant top-k → agent composes an answer with citations.

## Error handling

- Ingest and app startup check that Qdrant is reachable and that the API key is set, and exit with a clear message otherwise.
- Unreadable or scanned PDFs are reported and skipped. OCR is out of scope.
- Empty retrieval produces an explicit "not found" answer, not a guess.

## Testing

`tests/smoke.py`:
1. Ingest the PDF and assert the collection point count is above zero.
2. Re-run ingest and assert the point count is unchanged.
3. Ask 2–3 questions whose answers are known from the document and check the answers contain the expected facts and a source citation.

## Out of scope

OCR, non-PDF formats, authentication, multi-user sessions, reranking.

## Open risk

The PDF is a slide-style inventory table. Task 6 confirmed that the default `PDFReader` retrieves poorly on it (the "Subscription" row was not retrieved at all). Resolved with `app/readers.py::TableAwareReader` (pdfplumber): one chunk per table row, with merged-column groups cropped so split words rejoin, plus flat page text on pages with non-standard tables. After re-ingest, all three check questions return the right row at rank 1 (163 chunks instead of 26).

Known limits: service names keep spaces where the PDF's text layer splits them ("Subscrip tion"; a compact variant is appended to help matching), and tables with other column layouts use a generic row crop where wrapped cells can interleave. If answers are wrong on those pages, the next step is vision-based extraction of those pages. Changing the reader requires bumping `READER_VERSION` in `app/ingest.py` so files are re-ingested.
