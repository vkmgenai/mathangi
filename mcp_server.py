# mcp_server.py
import os
from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
from langchain_community.embeddings import FastEmbedEmbeddings

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
QDRANT_PATH = os.path.join(PROJECT_DIR, "qdrant_db")
COLLECTIONS = {
    "zerodha": "zerodha_market_docs",
    "kuvera": "kuvera_market_docs",
    "groww": "groww_market_docs",
    "paytmmoney": "paytmmoney_market_docs",
    "moneycontrol": "moneycontrol_market_docs",
}
SOURCE_LABELS = {
    "zerodha": "Zerodha",
    "kuvera": "Kuvera",
    "groww": "Groww",
    "paytmmoney": "Paytm Money",
    "moneycontrol": "Moneycontrol",
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
def query_zerodha_market_docs(query: str) -> str:
    """
    Search the daily-synced database of Zerodha market documents,
    instrument specs, and market circulars for Liquid Funds and ETFs.
    """
    return _query_collection("zerodha", query)

@mcp.tool()
def query_kuvera_portfolio(query: str) -> str:
    """Search locally uploaded Kuvera portfolio statements for holdings context."""
    return _query_collection("kuvera", query)

@mcp.tool()
def query_groww_portfolio(query: str) -> str:
    """Search locally uploaded Groww portfolio statements for holdings context."""
    return _query_collection("groww", query)

@mcp.tool()
def query_paytmmoney_portfolio(query: str) -> str:
    """Search locally uploaded Paytm Money portfolio statements for holdings context."""
    return _query_collection("paytmmoney", query)

@mcp.tool()
def query_moneycontrol_market_docs(query: str) -> str:
    """Search dated Moneycontrol market and mutual-fund headlines and short listing snippets."""
    return _query_collection("moneycontrol", query)

@mcp.tool()
def search_investment_research(query: str, asset_class: str = "both") -> str:
    """Retrieve dated source evidence for stock or mutual-fund research; this tool does not generate investment advice."""
    if asset_class not in {"stocks", "mutual_funds", "both"}:
        return "asset_class must be 'stocks', 'mutual_funds', or 'both'."

    if asset_class == "stocks":
        sources = ("zerodha", "groww", "paytmmoney", "moneycontrol")
    elif asset_class == "mutual_funds":
        sources = ("kuvera", "groww", "paytmmoney", "moneycontrol")
    else:
        sources = tuple(COLLECTIONS)

    sections = []
    for source in sources:
        result = _query_collection(source, query, limit=3)
        if not result.startswith("No relevant ") and not result.startswith("No ") and not result.startswith("RAG database"):
            sections.append(f"## {SOURCE_LABELS[source]}\n{result}")
    if not sections:
        return "No indexed research evidence matched the query. Run sync_market_docs.py first."
    return "\n\n---\n\n".join(sections)

if __name__ == "__main__":
    mcp.run()