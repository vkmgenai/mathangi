## Investment Research RAG

Install the project dependencies with Python 3.10 or newer:

```bash
python -m pip install -r requirements.txt
```

ollama run phi4-mini

The chat workflow is orchestrated by LangGraph in `agent_main.py`. It runs four
stages in order: `agent_analyst.py` retrieves portfolio and market RAG context
and creates a research brief; `agent_strategy.py` develops a cautious view;
`agent_execute.py` drafts a hypothetical execution checklist; and
`agent_evaluate.py` reviews the work and prepares the user-facing answer. The
user's request and both RAG contexts travel through the workflow state. The
execution stage does not place trades.

Install the added LangGraph dependency by rerunning the install command above.
The existing Flask endpoint continues to call `ask_strategy_agent`, which now
delegates to the LangGraph workflow.

The RAG index uses Chroma, persisted in `chroma_db`, with two collections:
`user_documents` contains private uploaded portfolio statements and
`market_information` contains public Zerodha and Moneycontrol market data. Run
`python3 sync_market_docs.py` to populate or refresh both collections. Existing
data in `qdrant_db` is not migrated automatically; the sync script rebuilds the
Chroma collections from the source documents.

MCP server endpoints and the data requested from each provider are listed in `mcp_servers.json`. Add future providers under `mcp_servers`; do not store credentials in this file. The sync script does not yet connect to these endpoints.

Run python3 app.py and browse http://127.0.0.1:50001/

TODO LIST
add cart funcationality

display risk meter next to suggestions (buy new stuff or buy old again or sell old again) - based on portfolio

say u cannot make sell suggestions withoug understanding portfolio

if no pportfolio make only buy suggestuiojs based on index funds or best performainf funds

agent which asks questions and gives buy sell suggestions if asked

does refresh button work in portfolio?

phi-4 mini answers are too ling and not to the point -> modify system prompt in agent_analyst

remove mutual fund and stock - do just 1
