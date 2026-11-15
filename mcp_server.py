# mcp_server.py
import os
from mcp.server.fastmcp import FastMCP
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH = os.path.join(PROJECT_DIR, "chroma_db")
COLLECTIONS = {
    "user_documents": "user_documents",
    "market_information": "market_information",
}
SOURCE_LABELS = {
    "user_documents": "User documents",
    "market_information": "Market information",
}
mcp = FastMCP("InvestmentResearchRAG")

def _query_collection(source: str, query: str, limit: int = 5) -> str:
    if not os.path.isdir(CHROMA_PATH):
        return "Chroma database is unavailable. Run sync_market_docs.py first."

    collection_name = COLLECTIONS[source]
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")
    store = Chroma(
        persist_directory=CHROMA_PATH,
        collection_name=collection_name,
        embedding_function=embeddings,
        collection_metadata={"hnsw:space": "cosine"},
    )
    documents = store.similarity_search(query, k=limit)
    if not documents:
        return f"No relevant {SOURCE_LABELS[source]} documents matched the query."

    results = []
    for document in documents:
        metadata = document.metadata or {}
        citation = [metadata.get("source_label", SOURCE_LABELS[source])]
        for field in ("file_name", "published_at", "indexed_at", "url"):
            if metadata.get(field):
                citation.append(f"{field}: {metadata[field]}")
        results.append(f"[{'; '.join(citation)}]\n{document.page_content}")
    return "\n\n---\n\n".join(results)

@mcp.tool()
def query_user_documents(query: str) -> str:
    """Search the private RAG collection containing user-uploaded portfolio statements."""
    return _query_collection("user_documents", query)

@mcp.tool()
def query_market_information(query: str) -> str:
    """Search the public market RAG collection containing Zerodha and Moneycontrol data."""
    return _query_collection("market_information", query)

@mcp.tool()
def search_investment_research(query: str, asset_class: str = "both") -> str:
    """Retrieve dated source evidence for stock or mutual-fund research; this tool does not generate investment advice."""
    if asset_class not in {"stocks", "mutual_funds", "both"}:
        return "asset_class must be 'stocks', 'mutual_funds', or 'both'."

    sections = []
    for collection_key in COLLECTIONS:
        result = _query_collection(collection_key, query, limit=3)
        if not result.startswith("No relevant ") and not result.startswith("No ") and not result.startswith("RAG database"):
            sections.append(f"## {SOURCE_LABELS[collection_key]}\n{result}")
    if not sections:
        return "No indexed research evidence matched the query. Run sync_market_docs.py first."
    return "\n\n---\n\n".join(sections)

if __name__ == "__main__":
    mcp.run()
