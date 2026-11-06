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

Run python3 app.py and browse http://127.0.0.1:50001/

