"""RAG agent entrypoint.

    docker compose run --rm agent python rag_agent.py            # terminal chat
    docker compose run --rm --service-ports agent python rag_agent.py --serve
"""

import argparse

from agno.os import AgentOS

from app import config
from app.agent import build_agent
from app.ingest import ingest_all
from app.knowledge import check_qdrant


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with the tech inventory documents.")
    parser.add_argument(
        "--serve", action="store_true", help="serve the AgentOS UI on port 7777 instead of terminal chat"
    )
    parser.add_argument("--skip-ingest", action="store_true", help="do not ingest new PDFs on startup")
    args = parser.parse_args()

    config.require_env()
    check_qdrant()
    if not args.skip_ingest:
        ingest_all()

    agent = build_agent()
    if args.serve:
        agent_os = AgentOS(agents=[agent])
        agent_os.serve(app=agent_os.get_app(), host="0.0.0.0", port=7777)
    else:
        print("Ask about the documents. Type 'exit' to quit.")
        agent.cli_app(stream=True, markdown=True, exit_on=["exit", "quit"])


if __name__ == "__main__":
    main()
