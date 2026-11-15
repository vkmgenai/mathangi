import os
import io
import csv
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

ZERODHA_INSTRUMENTS_URL = "https://api.kite.trade/instruments"
ZERODHA_CIRCULARS_URL = "https://zerodha.com/marketintel/circulars/"
COLLECTION_NAME = "zerodha_market_docs"
USER_DOCUMENTS_COLLECTION = "user_documents"
MARKET_INFORMATION_COLLECTION = "market_information"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH = os.path.join(PROJECT_DIR, "chroma_db")
CUSTOMER_DATA_PATH = os.path.join(PROJECT_DIR, "customer_data")
EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
EMBEDDING_MODEL_CHUNK_SIZE = 500
EMBEDDING_MODEL_CHUNK_OVERLAP = 50
EMBEDDING_DIMENSION = 768
BROKER_SOURCE_LABELS = {
    "zerodha_portfolio": "Zerodha",
    "kuvera": "Kuvera",
    "groww": "Groww",
    "paytmmoney": "Paytm Money",
    "bajaj_finserv": "Bajaj Finserv",
    "customer_portfolio": "Customer portfolio",
}
MONEYCONTROL_SECTION_URLS = {
    "stocks": "https://www.moneycontrol.com/news/business/markets/",
    "mutual_funds": "https://www.moneycontrol.com/mutual-funds/",
}

def fetch_zerodha_instruments() -> list[Document]:
    """Fetch Liquid Funds & ETF master file from Zerodha API dump."""
    print("Downloading Zerodha instruments dump...")
    res = requests.get(ZERODHA_INSTRUMENTS_URL)
    res.raise_for_status()
    
    reader = csv.DictReader(io.StringIO(res.text))
    docs = []
    
    for row in reader:
        symbol = row.get("tradingsymbol", "")
        name = row.get("name", "")
        instrument_type = row.get("instrument_type", "")
        
        # Filter for Liquid Funds & ETFs
        if "ETF" in symbol or "LIQUID" in symbol or instrument_type == "EQ-ETF":
            content = (
                f"Trading Symbol: {symbol}\n"
                f"Name: {name}\n"
                f"Exchange: {row.get('exchange')}\n"
                f"Segment: {row.get('segment')}\n"
                f"Instrument Type: {instrument_type}\n"
                f"Last Price: {row.get('last_price')}\n"
                f"Tick Size: {row.get('tick_size')}"
            )
            metadata = {
                "doc_type": "instrument_master",
                "symbol": symbol,
                "exchange": row.get("exchange")
            }
            docs.append(Document(page_content=content, metadata=metadata))
            
    print(f"Parsed {len(docs)} ETF & Liquid Fund records.")
    return docs

def fetch_zerodha_market_bulletins() -> list[Document]:
    """Scrape recent public market circulars from Zerodha Market Intel."""
    print("Fetching Zerodha public market circulars...")
    res = requests.get(ZERODHA_CIRCULARS_URL)
    docs = []
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, "html.parser")
        circular_items = soup.find_all("li")
        for item in circular_items[:30]:  # Limit to latest 30 public circulars
            text = item.get_text(strip=True)
            if text:
                docs.append(Document(
                    page_content=text,
                    metadata={"doc_type": "exchange_circular"}
                ))
    print(f"Parsed {len(docs)} public market circulars.")
    return docs

def _read_customer_statement(path: str, filename: str, source: str) -> list[Document]:
    extension = os.path.splitext(filename)[1].lower()
    source_label = BROKER_SOURCE_LABELS[source]
    indexed_at = datetime.now(timezone.utc).isoformat()
    docs = []

    if extension == ".pdf":
        from pypdf import PdfReader

        for page_number, page in enumerate(PdfReader(path).pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                docs.append(Document(
                    page_content=f"Source: {source_label}\nPortfolio statement: {filename}\nPage: {page_number}\n{text}",
                    metadata={
                        "source": source,
                        "source_label": source_label,
                        "doc_type": "portfolio_statement",
                        "file_name": filename,
                        "page": page_number,
                        "indexed_at": indexed_at,
                    },
                ))
    elif extension in {".txt", ".csv"}:
        with open(path, encoding="utf-8-sig", errors="replace") as source_file:
            text = source_file.read().strip()
        if text:
            docs.append(Document(
                page_content=f"Source: {source_label}\nPortfolio statement: {filename}\n{text}",
                metadata={
                    "source": source,
                    "source_label": source_label,
                    "doc_type": "portfolio_statement",
                    "file_name": filename,
                    "indexed_at": indexed_at,
                },
            ))
    elif extension == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        for sheet in workbook.worksheets:
            rows = ["\t".join("" if value is None else str(value) for value in row) for row in sheet.iter_rows(values_only=True)]
            text = "\n".join(row for row in rows if row.strip())
            if text:
                docs.append(Document(
                    page_content=f"Source: {source_label}\nPortfolio statement: {filename}\nSheet: {sheet.title}\n{text}",
                    metadata={
                        "source": source,
                        "source_label": source_label,
                        "doc_type": "portfolio_statement",
                        "file_name": filename,
                        "sheet": sheet.title,
                        "indexed_at": indexed_at,
                    },
                ))
        workbook.close()
    elif extension == ".xls":
        import xlrd

        workbook = xlrd.open_workbook(path, on_demand=True)
        for sheet in workbook.sheets():
            rows = ["\t".join(str(value) for value in sheet.row_values(index)) for index in range(sheet.nrows)]
            text = "\n".join(row for row in rows if row.strip())
            if text:
                docs.append(Document(
                    page_content=f"Source: {source_label}\nPortfolio statement: {filename}\nSheet: {sheet.name}\n{text}",
                    metadata={
                        "source": source,
                        "source_label": source_label,
                        "doc_type": "portfolio_statement",
                        "file_name": filename,
                        "sheet": sheet.name,
                        "indexed_at": indexed_at,
                    },
                ))
        workbook.release_resources()
    return docs

def fetch_customer_portfolio_docs(source: str) -> list[Document]:
    """Read user-provided statement files for one supported broker."""
    if source not in BROKER_SOURCE_LABELS or source == "customer_portfolio" or not os.path.isdir(CUSTOMER_DATA_PATH):
        return []

    supported_extensions = {".pdf", ".txt", ".csv", ".xls", ".xlsx"}
    docs = []
    for filename in sorted(os.listdir(CUSTOMER_DATA_PATH)):
        extension = os.path.splitext(filename)[1].lower()
        if source not in filename.lower() or extension not in supported_extensions:
            continue
        path = os.path.join(CUSTOMER_DATA_PATH, filename)
        if not os.path.isfile(path):
            continue
        try:
            docs.extend(_read_customer_statement(path, filename, source))
        except Exception:
            logging.exception("Could not read %s portfolio statement %s", source, filename)
    print(f"Indexed {len(docs)} {BROKER_SOURCE_LABELS[source]} statement pages/sheets.")
    return docs

def fetch_unmatched_customer_portfolio_docs() -> list[Document]:
    """Index uploaded statements that do not match a known provider filename."""
    if not os.path.isdir(CUSTOMER_DATA_PATH):
        return []

    known_providers = tuple(source for source in BROKER_SOURCE_LABELS if source != "customer_portfolio")
    supported_extensions = {".pdf", ".txt", ".csv", ".xls", ".xlsx"}
    docs = []
    for filename in sorted(os.listdir(CUSTOMER_DATA_PATH)):
        extension = os.path.splitext(filename)[1].lower()
        if extension not in supported_extensions or any(source in filename.lower() for source in known_providers):
            continue
        path = os.path.join(CUSTOMER_DATA_PATH, filename)
        if not os.path.isfile(path):
            continue
        try:
            docs.extend(_read_customer_statement(path, filename, "customer_portfolio"))
        except Exception:
            logging.exception("Could not read customer portfolio statement %s", filename)
    print(f"Indexed {len(docs)} additional customer statement pages/sheets.")
    return docs

def fetch_moneycontrol_market_docs() -> list[Document]:
    """Index current Moneycontrol headlines and short listing snippets, not full articles."""
    docs = []
    seen_urls = set()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MarketDocsRAG/1.0)"}

    for asset_class, section_url in MONEYCONTROL_SECTION_URLS.items():
        section_doc_count = 0
        try:
            response = requests.get(section_url, headers=headers, timeout=20)
            response.raise_for_status()
        except requests.RequestException:
            logging.exception("Could not fetch Moneycontrol %s page", asset_class)
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.find_all("a", href=True):
            article_url = urljoin(section_url, anchor.get("href", ""))
            parsed_url = urlparse(article_url)
            if parsed_url.hostname not in {"moneycontrol.com", "www.moneycontrol.com"}:
                continue
            if "/news/" not in parsed_url.path or article_url in seen_urls:
                continue

            title = " ".join(anchor.get_text(" ", strip=True).split())
            if len(title) < 12:
                continue
            seen_urls.add(article_url)

            container = anchor.find_parent("article") or anchor.find_parent("li") or anchor.parent
            snippet = " ".join(container.get_text(" ", strip=True).split()) if container else title
            snippet = snippet[:400]
            time_element = container.find("time") if container else None
            published_at = ""
            if time_element:
                published_at = time_element.get("datetime") or time_element.get_text(" ", strip=True)

            content = (
                f"Source: Moneycontrol\nAsset class: {asset_class}\nHeadline: {title}\n"
                f"Published: {published_at or 'date not listed'}\nSummary snippet: {snippet}\nURL: {article_url}"
            )
            docs.append(Document(
                page_content=content,
                metadata={
                    "source": "moneycontrol",
                    "source_label": "Moneycontrol",
                    "doc_type": "market_headline",
                    "asset_class": asset_class,
                    "title": title,
                    "url": article_url,
                    "published_at": published_at,
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                },
            ))
            section_doc_count += 1
            if section_doc_count >= 15:
                break

    print(f"Parsed {len(docs)} current Moneycontrol headlines.")
    return docs

def _overwrite_collection(persist_directory, embeddings, text_splitter, collection_name, docs, preserve_on_empty=False):
    if not docs and preserve_on_empty:
        print(f"No fresh documents for '{collection_name}'; preserving the previous index.")
        return

    if not docs:
        print(f"No documents available for '{collection_name}'.")
        return

    splits = text_splitter.split_documents(docs)
    existing_store = Chroma(
        persist_directory=persist_directory,
        collection_name=collection_name,
        embedding_function=embeddings,
        collection_metadata={"hnsw:space": "cosine"},
    )
    existing_store.delete_collection()
    vector_store = Chroma(
        persist_directory=persist_directory,
        collection_name=collection_name,
        embedding_function=embeddings,
        collection_metadata={"hnsw:space": "cosine"},
    )
    vector_store.add_documents(splits)
    print(f"Indexed {len(splits)} chunks into '{collection_name}'.")

def overwrite_market_vector_store():
    """Refresh the private user-documents and public market-information indexes."""
    user_docs = []
    for source in BROKER_SOURCE_LABELS:
        if source != "customer_portfolio":
            user_docs.extend(fetch_customer_portfolio_docs(source))
    user_docs.extend(fetch_unmatched_customer_portfolio_docs())

    market_docs = fetch_zerodha_instruments() + fetch_zerodha_market_bulletins()
    market_docs.extend(fetch_moneycontrol_market_docs())

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=EMBEDDING_MODEL_CHUNK_SIZE, chunk_overlap=EMBEDDING_MODEL_CHUNK_OVERLAP)

    _overwrite_collection(
        CHROMA_PATH,
        embeddings,
        text_splitter,
        USER_DOCUMENTS_COLLECTION,
        user_docs,
        preserve_on_empty=True,
    )
    _overwrite_collection(
        CHROMA_PATH,
        embeddings,
        text_splitter,
        MARKET_INFORMATION_COLLECTION,
        market_docs,
        preserve_on_empty=True,
    )
    print("Daily sync complete: user_documents and market_information.")

if __name__ == "__main__":
    overwrite_market_vector_store()
