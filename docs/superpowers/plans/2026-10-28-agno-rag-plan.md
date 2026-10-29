# Agno RAG Agent: Implementation Plan

Spec: `docs/superpowers/specs/2026-10-28-agno-rag-design.md`

Agno's import paths and signatures change between releases. Task 1 pins the installed version, and every later task checks its imports against that version before writing code.

## Task 1: Project setup

1. `cd /var/www/agno-rag && uv init --python 3.12 --no-readme`. Create `documents/` and move the PDF into it.
2. `uv add agno openai qdrant-client pypdf python-dotenv fastapi "uvicorn[standard]"` (produces `uv.lock`).
3. Create `.env.example` (`OPENAI_API_KEY=`, `QDRANT_URL=http://host.docker.internal:6333`) and copy it to `.env` for the user to fill in. Add `.gitignore` and `.dockerignore` containing `.env`, `.venv/`, `documents/`, `docs/`.
4. Verify Qdrant from the host: `curl -s http://localhost:6333/collections` returns JSON. If not, stop and ask the user to check the container's port mapping.
5. Record the installed Agno version (`uv pip show agno`). Open the installed package to confirm the import paths used below: `Knowledge`, `Qdrant`, `OpenAIEmbedder`, `PDFReader`, `Agent`, `OpenAIChat`, `AgentOS`.

Done when: `uv run python -c "import agno, qdrant_client"` succeeds and Qdrant answers on 6333.

## Task 1b: Docker image and compose

1. `Dockerfile`: `FROM python:3.12-slim`, copy `uv` from `ghcr.io/astral-sh/uv`, `uv sync --frozen --no-dev` using `pyproject.toml` and `uv.lock`, then copy `app/` and `rag_agent.py`. `WORKDIR /srv`, put the venv on `PATH`.
2. `docker-compose.yml`: service `agent` as described in the spec (env_file, read-only `documents` mount at `/data/documents`, `QDRANT_URL`, `extra_hosts` host-gateway, `stdin_open`/`tty`, port 7777).
3. `docker compose build agent`, then `docker compose run --rm agent python -c "import agno; import urllib.request as u; print(u.urlopen('http://host.docker.internal:6333/collections').read()[:80])"` to prove the container reaches the host's Qdrant.

Done when: the container prints Qdrant's collections JSON.

## Task 2: `app/config.py`

- Load `.env` with `python-dotenv`.
- Expose `OPENAI_API_KEY`, `QDRANT_URL` (default `http://host.docker.internal:6333`), `COLLECTION = "ops_docs"`, `DOCS_DIR` (env `DOCS_DIR`, default `/data/documents`), `EMBED_MODEL = "text-embedding-3-small"`, `CHAT_MODEL`.
- `require_env()` raises a clear `SystemExit` message if `OPENAI_API_KEY` is empty.
- Add `app/__init__.py`.

Done when: running with an empty key prints the message and exits non-zero.

## Task 3: `app/knowledge.py`

- `get_knowledge()` builds `Knowledge(vector_db=Qdrant(collection=COLLECTION, url=QDRANT_URL, embedder=OpenAIEmbedder(id=EMBED_MODEL, dimensions=1536)))`.
- `check_qdrant()` makes a lightweight call with `qdrant_client` and raises `SystemExit` with a readable message when Qdrant is unreachable.
- No other module imports Qdrant.

Done when: `get_knowledge()` returns an object and `check_qdrant()` passes against the running container.

## Task 4: `app/ingest.py`

- Exposes `ingest_all()` for `rag_agent.py` to call, plus a CLI: `docker compose run --rm agent python -m app.ingest`.
- Call `require_env()` and `check_qdrant()`.
- For each `*.pdf` in `DOCS_DIR`: compute a SHA-256 of the bytes, then look up whether points with that `content_hash` metadata already exist (qdrant-client scroll with a payload filter). If they do, print "skipped" and continue. If the same file name exists with a different hash, delete its old points first.
- Otherwise call `knowledge.insert(path=..., reader=PDFReader(), metadata={"source": filename, "content_hash": hash})` (Agno 3.1.11 has `insert`, not `add_content`). To replace a changed file use `knowledge.remove_vectors_by_metadata({"source": filename})` first.
- Wrap each file in try/except so an unreadable PDF is reported and skipped, and the run continues.
- Print a summary: ingested / skipped / failed.

Done when: the first run ingests the PDF and the second run reports it skipped.

## Task 5: Smoke test for ingest (`tests/smoke.py`, part 1)

- Run ingest, then count points with `qdrant_client.count(COLLECTION)`. Assert count > 0.
- Run ingest again, assert the count is unchanged.
- Inspect one point payload and confirm it has `source` and a page reference. If page metadata is missing, adjust metadata in Task 4 so citations can include a page.

Done when: both assertions pass.

## Task 6: Look at the retrieval quality (table risk check)

Before building the agent, query Qdrant directly through `knowledge.search("<a fact you know from the PDF>")` for 3 questions the user supplies or that we read off the PDF. If rows are split badly (partial rows, headers detached from values):

1. Add a table-aware reader in `app/readers.py` (pdfplumber extracting tables into row-per-chunk text with the header repeated).
2. Make `ingest.py` use it instead of `PDFReader`.
3. Re-run the check.

Skip step 1 onward if results are already good. Record the outcome in the spec's "Open risk" section.

Done when: the 3 sample questions each return a chunk containing the answer.

## Task 7: `app/agent.py`

- `build_agent()` returns `Agent(model=OpenAIChat(id=CHAT_MODEL), knowledge=get_knowledge(), search_knowledge=True, instructions=[...], markdown=True)`.
- Instructions: answer only from retrieved content; cite source file and page; if nothing relevant is retrieved, say "I couldn't find that in the documents."

Done when: `build_agent().print_response("<known question>")` returns the right fact with a citation.

## Task 8: Smoke test for answers (`tests/smoke.py`, part 2)

- Ask 2–3 questions with known answers and assert the response contains the expected substrings and the source file name.
- Ask one question not covered by the document and assert the response contains the "couldn't find" wording.

Done when: all assertions pass.

## Task 9: `rag_agent.py` entrypoint

- Calls `require_env()` and `check_qdrant()`, then `ingest_all()` (skips unchanged PDFs, so startup is fast after the first run).
- Default: terminal chat loop with `agent.cli_app(stream=True)` (or the installed Agno's equivalent). Needs `stdin_open`/`tty`, which `docker compose run` provides.
- `--serve`: builds `AgentOS(agents=[agent])`, gets the app, and serves it on `0.0.0.0:7777` (binding to 0.0.0.0 is required inside the container).
- Verify both commands:
  - `docker compose run --rm agent python rag_agent.py` answers a cited question.
  - `docker compose run --rm --service-ports agent python rag_agent.py --serve` is reachable at `http://localhost:7777`, and the AgentOS UI connects to it.

Done when: chat answers a question with a citation and the UI lists the agent and answers one too.

## Task 10: README and sharing

`README.md` with:
- Prerequisites: Docker, a Qdrant container publishing 6333 (`docker run -d -p 6333:6333 -v qdrant_data:/qdrant/storage qdrant/qdrant`), an OpenAI key.
- Setup: `cp .env.example .env`, fill the key, drop PDFs in `documents/`.
- Commands: build, chat, `--serve`, standalone ingest, smoke test (`docker compose run --rm agent python tests/smoke.py`).
- Notes: Linux uses the `host-gateway` mapping already in compose; a local Qdrant means each person has their own copy of the vectors.

Confirm a clean clone works: remove the local image and `.venv`, follow the README from scratch.

## Order and checkpoints

Tasks 1–1b–5 get the container and ingestion working. All Python runs go through `docker compose run --rm agent ...` once Task 1b is done, so host Python versions don't matter. Task 6 is the decision point on the reader. Tasks 7–9 deliver the agent and UI. Pause for the user after Task 6 if a reader change is needed, and after Task 9 for a UI demo.

## Needs from the user

- An `OPENAI_API_KEY` in `.env` (before Task 4).
- 2–3 questions with known answers from the PDF (for Tasks 6 and 8). If none are provided, I'll derive them from the PDF text and confirm them with the user.
