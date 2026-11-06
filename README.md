trading_agent_project/
├── market_data.db            # SQLite Database (Instruments, Cash, & Positions)
├── qdrant_db/                # Local Vector Store (Daily-Synced Zerodha Market Docs)
├── trading_engine.py         # SQLite DB Initialization & Trade Execution Logic
├── sync_market_docs.py       # Daily Ingestion & Overwrite Script (Zerodha APIs & Scraper)
└── mcp_server.py             # Model Context Protocol (MCP) Tooling Server

## Investment Research RAG

Install the project dependencies with Python 3.10 or newer:

```bash
python -m pip install -r requirements.txt
```

Run `sync_market_docs.py` to refresh the Qdrant collections. Zerodha instruments and circulars remain in `zerodha_market_docs`; Kuvera, Groww, and Paytm Money collections are built from matching user-provided statement files in `customer_data`. Moneycontrol indexes current market and mutual-fund headlines with short listing snippets, publication metadata when available, and source links.

Run `mcp_server.py` as a stdio MCP server. It exposes `query_zerodha_market_docs`, `query_kuvera_portfolio`, `query_groww_portfolio`, `query_paytmmoney_portfolio`, and `query_moneycontrol_market_docs`, plus `search_investment_research` for retrieving evidence by asset class. These tools provide source context for downstream suggestions; they do not produce guaranteed returns or execute trades.