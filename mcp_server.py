# mcp_server.py
import os
from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
from langchain_community.embeddings import FastEmbedEmbeddings

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
QDRANT_PATH = os.path.join(PROJECT_DIR, "qdrant_db")
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
    if not os.path.isdir(QDRANT_PATH):
        return "RAG database is unavailable. Run sync_market_docs.py first."

    collection_name = COLLECTIONS[source]
    client = QdrantClient(path=QDRANT_PATH)
    try:
        if not client.collection_exists(collection_name):
            return f"No {SOURCE_LABELS[source]} documents are indexed. Run sync_market_docs.py first."

        embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
        query_vector = embeddings.embed_query(query)
        if hasattr(client, "query_points"):
            hits = client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
            ).points
        else:
            hits = client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
            )
        results = []
        for hit in hits:
            payload = hit.payload or {}
            metadata = payload.get("metadata", {})
            page_content = payload.get("page_content", "")
            source_label = metadata.get("source_label", SOURCE_LABELS[source])
            citation = [source_label]
            for field in ("file_name", "published_at", "indexed_at", "url"):
                value = metadata.get(field)
                if value:
                    citation.append(f"{field}: {value}")
            results.append(f"[{'; '.join(citation)}]\n{page_content}")

        if not results:
            return f"No relevant {SOURCE_LABELS[source]} documents matched the query."
        return "\n\n---\n\n".join(results)
    finally:
        client.close()

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