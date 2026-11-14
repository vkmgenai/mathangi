"""Tool-using investment research agent backed by Ollama and Qdrant RAG.

Model requests use an OpenAI-compatible HTTP API, so switching model tags or
providers does not require model-specific Python imports.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

# Model setup: change MODEL_NAME to switch to another locally installed model.
# For a hosted provider later, change MODEL_BASE_URL and set STRATEGY_LLM_API_KEY.
MODEL_PROVIDER = "ollama"
MODEL_NAME = "phi4-mini:latest"
MODEL_BASE_URL = "http://localhost:11434/v1"

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
QDRANT_PATH = os.path.join(PROJECT_DIR, "qdrant_db")
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
COLLECTIONS = {
    "user_documents": "user_documents",
    "market_information": "market_information",
}
SOURCE_LABELS = {
    "user_documents": "User documents",
    "market_information": "Market information",
}

SYSTEM_PROMPT = """You are an investment research assistant. The user message may include evidence retrieved from local portfolio statements and market documents; use it before answering and do not ask the user to repeat holdings already present in that evidence. Clearly distinguish user-provided portfolio statements from public market research, and include source names, dates, and links when returned by the tools. Portfolio statements are snapshots, not live prices. If sources are missing, stale, or disagree, say so. Do not invent prices, returns, or facts; do not promise returns or present your response as personalized financial advice. You cannot place, recommend, or execute trades."""

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_investment_research",
            "description": "Retrieve evidence from the indexed RAG sources for stock or mutual-fund research. This tool only searches documents; it does not trade.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "A concise research query."},
                    "asset_class": {
                        "type": "string",
                        "enum": ["stocks", "mutual_funds", "both"],
                        "description": "Which asset class to research.",
                    },
                },
                "required": ["query", "asset_class"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_source_documents",
            "description": "Search one source collection for specific holdings or market-document context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": list(COLLECTIONS),
                        "description": "The source collection to search.",
                    },
                    "query": {"type": "string", "description": "A concise search query."},
                },
                "required": ["source", "query"],
                "additionalProperties": False,
            },
        },
    },
]


class StrategyAgentError(RuntimeError):
    """Raised when the model endpoint or tool-calling loop cannot complete."""


@dataclass(frozen=True)
class AgentConfig:
    base_url: str = MODEL_BASE_URL
    model: str = MODEL_NAME
    api_key: Optional[str] = None
    timeout_seconds: int = 600
    max_tokens: int = 1024
    max_tool_rounds: int = 4
    results_per_source: int = 3

    @classmethod
    def from_environment(cls) -> "AgentConfig":
        return cls(
            base_url=os.getenv("STRATEGY_LLM_BASE_URL", MODEL_BASE_URL),
            model=os.getenv("STRATEGY_LLM_MODEL", MODEL_NAME),
            api_key=os.getenv("STRATEGY_LLM_API_KEY"),
            timeout_seconds=int(os.getenv("STRATEGY_LLM_TIMEOUT", "600")),
            max_tokens=int(os.getenv("STRATEGY_LLM_MAX_TOKENS", "1024")),
            max_tool_rounds=int(os.getenv("STRATEGY_AGENT_MAX_TOOL_ROUNDS", "4")),
        )


_EMBEDDINGS = None


def _get_embeddings():
    global _EMBEDDINGS
    if _EMBEDDINGS is None:
        from langchain_community.embeddings import FastEmbedEmbeddings

        _EMBEDDINGS = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)
    return _EMBEDDINGS


def _query_collections(query: str, sources: List[str], limit: int) -> str:
    if not os.path.isdir(QDRANT_PATH):
        return "The local RAG database is unavailable. Run sync_market_docs.py first."

    from qdrant_client import QdrantClient

    client = QdrantClient(path=QDRANT_PATH)
    try:
        query_vector = _get_embeddings().embed_query(query)
        sections = []
        for source in sources:
            collection_name = COLLECTIONS[source]
            if not client.collection_exists(collection_name):
                continue

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

            for hit in hits:
                payload = hit.payload or {}
                metadata = payload.get("metadata") or {}
                label = metadata.get("source_label", SOURCE_LABELS[source])
                citation = [label]
                for field in ("file_name", "published_at", "indexed_at", "url"):
                    value = metadata.get(field)
                    if value:
                        citation.append("{}: {}".format(field, value))
                content = payload.get("page_content", "")
                sections.append("[{}]\n{}".format("; ".join(citation), content))

        if not sections:
            return "No matching indexed evidence was found for this query. Run sync_market_docs.py if the source collections are empty."
        return "\n\n---\n\n".join(sections)
    finally:
        client.close()


def _search_investment_research(query: str, asset_class: str) -> str:
    if asset_class not in {"stocks", "mutual_funds", "both"}:
        return "asset_class must be stocks, mutual_funds, or both."
    return _query_collections(
        "Asset class: {}\nResearch question: {}".format(asset_class, query),
        ["user_documents", "market_information"],
        limit=3,
    )


def _query_source_documents(source: str, query: str) -> str:
    if source not in COLLECTIONS:
        return "Unknown source."
    return _query_collections(query, [source], limit=5)


def _infer_asset_class(prompt: str) -> str:
    normalized = prompt.lower()
    mentions_funds = any(term in normalized for term in ("fund", "mutual", "sip", "nav"))
    mentions_stocks = any(term in normalized for term in ("stock", "share", "equity", "etf", "ticker"))
    if mentions_funds and mentions_stocks:
        return "both"
    if mentions_funds:
        return "mutual_funds"
    if mentions_stocks:
        return "stocks"
    return "both"


TOOL_HANDLERS = {
    "search_investment_research": _search_investment_research,
    "query_source_documents": _query_source_documents,
}


class StrategyAgent:
    """OpenAI-compatible tool-calling agent with a local Ollama default."""

    def __init__(self, config: Optional[AgentConfig] = None, session: Any = None):
        self.config = config or AgentConfig.from_environment()
        self.session = session or requests

    def _chat_completion(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        endpoint = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key
        if "openrouter.ai" in self.config.base_url:
            headers["HTTP-Referer"] = os.getenv("OPENROUTER_SITE_URL", "http://localhost")
            headers["X-Title"] = os.getenv("OPENROUTER_APP_NAME", "AEGIS Investment Research")

        payload = {
            "model": self.config.model,
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "tool_choice": "auto",
            "max_tokens": self.config.max_tokens,
        }
        try:
            response = self.session.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=self.config.timeout_seconds,
            )
        except requests.Timeout as error:
            raise StrategyAgentError(
                "The model did not respond within {} seconds. It may still be loading or generating; increase STRATEGY_LLM_TIMEOUT or lower STRATEGY_LLM_MAX_TOKENS.".format(
                    self.config.timeout_seconds
                )
            ) from error
        except requests.ConnectionError as error:
            raise StrategyAgentError(
                "Could not connect to the model endpoint at {}. Confirm the service is running and STRATEGY_LLM_BASE_URL is correct.".format(
                    self.config.base_url
                )
            ) from error
        except requests.RequestException as error:
            raise StrategyAgentError("The model HTTP request failed: {}.".format(error)) from error

        if response.status_code >= 400:
            raise StrategyAgentError("The model endpoint returned HTTP {}.".format(response.status_code))
        try:
            return response.json()
        except ValueError as error:
            raise StrategyAgentError("The model endpoint returned invalid JSON.") from error

    def _run_tool(self, name: str, arguments_json: Any) -> str:
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return "That tool is not available."
        try:
            arguments = arguments_json if isinstance(arguments_json, dict) else json.loads(arguments_json or "{}")
            result = handler(**arguments)
            return str(result)[:12000]
        except (TypeError, ValueError, json.JSONDecodeError):
            return "The tool call had invalid arguments."
        except Exception:
            return "The requested research source could not be queried."

    def ask(self, prompt: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Enter a research question.")

        asset_class = _infer_asset_class(prompt)
        evidence = _search_investment_research(prompt, asset_class)
        history = []
        for item in (chat_history or [])[-8:]:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
                history.append({"role": role, "content": content[:4000]})
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {
                "role": "user",
                "content": "{}\n\nRetrieved local research evidence (use this as context, not as live market data):\n{}".format(
                    prompt,
                    evidence,
                ),
            },
        ]
        for _ in range(self.config.max_tool_rounds + 1):
            result = self._chat_completion(messages)
            choices = result.get("choices") or []
            if not choices:
                raise StrategyAgentError("The model endpoint returned no choices.")
            message = choices[0].get("message") or {}
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                answer = message.get("content")
                if answer:
                    return answer.strip()
                raise StrategyAgentError("The model returned neither an answer nor a tool call.")

            messages.append(message)
            for tool_call in tool_calls:
                function = tool_call.get("function") or {}
                tool_result = self._run_tool(function.get("name", ""), function.get("arguments"))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": tool_result,
                })

        raise StrategyAgentError("The agent reached its tool-call limit before producing a final answer.")


def ask_strategy_agent(prompt: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
    """Run one research turn with environment-configured model and RAG tools."""
    return StrategyAgent().ask(prompt, chat_history=chat_history)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Ask the configured investment research agent.")
    parser.add_argument("prompt", nargs="+", help="Stock or mutual-fund research question")
    args = parser.parse_args(argv)
    try:
        print(ask_strategy_agent(" ".join(args.prompt)))
    except (StrategyAgentError, ValueError) as error:
        print("Agent error: {}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
