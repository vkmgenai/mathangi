"""Portfolio and market document retrieval plus question analysis."""

import os
from typing import Any, Dict, List, Optional

from agent_common import AgentConfig, invokeCommonLLM

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH = os.path.join(PROJECT_DIR, "chroma_db")
EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
COLLECTIONS = {"portfolio": "user_documents", "market": "market_information"}
SOURCE_LABELS = {"portfolio": "Portfolio documents", "market": "Market documents"}
_EMBEDDINGS = None
TOP_K = 4


def retrieve_context(query: str, limit: int = TOP_K) -> Dict[str, str]:
    """Retrieve independently cited context from both local Chroma collections."""
    if not os.path.isdir(CHROMA_PATH):
        missing = "Local Chroma database unavailable; run sync_market_docs.py."
        return {"portfolio_context": missing, "market_context": missing}
    try:
        from langchain_chroma import Chroma
        global _EMBEDDINGS
        if _EMBEDDINGS is None:
            from langchain_community.embeddings import HuggingFaceEmbeddings
            _EMBEDDINGS = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        results = {}
        for key, collection in COLLECTIONS.items():
            store = Chroma(
                persist_directory=CHROMA_PATH,
                collection_name=collection,
                embedding_function=_EMBEDDINGS,
                collection_metadata={"hnsw:space": "cosine"},
            )
            sections = []
            for document in store.similarity_search(query, k=limit):
                metadata = document.metadata or {}
                citations = [metadata.get("source_label", SOURCE_LABELS[key])]
                for field in ("file_name", "published_at", "indexed_at", "url"):
                    if metadata.get(field):
                        citations.append("{}: {}".format(field, metadata[field]))
                sections.append("[{}]\n{}".format("; ".join(citations), document.page_content))
            results[key + "_context"] = "\n\n---\n\n".join(sections) if sections else "No matching indexed evidence found."
        return results
    except Exception as error:
        message = "RAG retrieval failed: {}".format(error)
        return {"portfolio_context": message, "market_context": message}

class AnalysisAgent:
    """Turns the user request and retrieved evidence into a concise research brief."""

    def __init__(self, config: Optional[AgentConfig] = None, session: Any = None):
        self.config, self.session = config, session

    def run(self, user_input: str, chat_history: Optional[List[Dict[str, str]]] = None,
            portfolio_context: str = "", market_context: str = "", mode: str = "basic") -> str:
        history = "\n".join(
            "{}: {}".format(item.get("role"), item.get("content", "")[:2000])
            for item in (chat_history or [])[-8:]
            if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str)
        ) or "No prior conversation."
        return invokeCommonLLM(
            "You are the analysis agent in an investment research workflow. Extract the user's actual question, identify relevant portfolio facts and market evidence, list important gaps, and distinguish dated document snapshots from live data. In Basic mode, make a compact brief. In Advanced mode, provide a more thorough evidence comparison, assumptions, and gaps. If the user question is unrelated to investment research, politely decline to answer. Do not reveal hidden chain of thought, recommend or execute trades. Do not keep repeating sentences. Limit your answer to 2000 words. If evidence is insufficient, say what is missing. Do not ramble. Clearly state your sources and cite them in brackets. ",
            "Response mode: {}\n\nUser request:\n{}\n\nRecent conversation:\n{}\n\nPortfolio RAG context:\n{}\n\nMarket RAG context:\n{}".format(
                mode, user_input, history, portfolio_context, market_context
            ), self.config, self.session,
        )


# def analyze_request(user_input: str, chat_history=None) -> Dict[str, str]:
#     """Convenience entry point for callers that need the full analyst result."""
#     context = retrieve_context(user_input)
#     context["analysis"] = AnalysisAgent().run(user_input, chat_history, **context)
#     return context
