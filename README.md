## Investment Research RAG

Install the project dependencies with Python 3.10 or newer:

```bash
python -m pip install -r requirements.txt
```

ollama run phi4-mini

The RAG index uses two collections: `user_documents` contains private uploaded portfolio statements; `market_information` contains public Zerodha and Moneycontrol market data. Run `python3 sync_market_docs.py` to refresh both collections.

Run python3 app.py and browse http://127.0.0.1:50001/

