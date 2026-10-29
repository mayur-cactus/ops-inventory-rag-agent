from agno.agent import Agent
from agno.models.openai import OpenAIChat

from app import config
from app.knowledge import get_knowledge

NOT_FOUND = "I couldn't find that in the documents."

INSTRUCTIONS = [
    "You answer questions about the company's technology inventory documents. "
    "Always search the knowledge base before answering.",
    "Answer only from the retrieved content. Do not use outside knowledge.",
    "The documents are tables. Each retrieved chunk is usually one row: a service "
    "or product with its technology, framework, DB, status and comments. "
    "Match the service name carefully; names may contain stray spaces "
    "(for example 'Subscrip tion' means 'Subscription').",
    "If a question spans several services, search more than once and list each "
    "service separately.",
    "Cite the source file name and page number for every fact, for example "
    "(OPS-Tech Inventory ... .pdf, page 3). Chunk metadata carries both.",
    f"If the retrieved content does not answer the question, reply exactly: {NOT_FOUND}",
]


def build_agent() -> Agent:
    return Agent(
        name="Tech Inventory Agent",
        model=OpenAIChat(id=config.CHAT_MODEL, api_key=config.OPENAI_API_KEY),
        knowledge=get_knowledge(),
        search_knowledge=True,
        add_knowledge_to_context=False,
        instructions=INSTRUCTIONS,
        markdown=True,
    )
