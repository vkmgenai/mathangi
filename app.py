import csv
import io
import logging
import os
import re
from flask import Flask, render_template_string, request, jsonify
from werkzeug.utils import secure_filename
from trading_engine import init_trading_db, get_account_summary, set_account_cash_balance, execute_trade

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
CUSTOMER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "customer_data")
ALLOWED_HOLDING_EXTENSIONS = {"csv", "xls", "xlsx", "pdf", "txt"}
init_trading_db()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>AEGIS AI Trading Agent</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 font-sans min-h-screen">
    <div class="max-w-7xl mx-auto p-6">
        <!-- Header -->
        <header class="flex justify-between items-center border-b border-slate-800 pb-4 mb-6">
            <div>
                <h1 class="text-2xl font-bold text-blue-400">🤖 AEGIS AI Trading Agent</h1>
                <p class="text-sm text-slate-400">Autonomous Liquid Fund & ETF Advisory Engine (Read-Only Safety Lock Active)</p>
            </div>
            <div class="flex gap-4 items-center">
                <div class="bg-slate-900 border border-slate-800 px-4 py-2 rounded-lg min-w-48">
                    <div class="flex items-center justify-between gap-4">
                        <div>
                            <span class="text-xs text-slate-400 block">Dummy Cash Balance</span>
                            <span id="cash-display" class="text-lg font-semibold text-emerald-400">₹1,000.00</span>
                        </div>
                        <button type="button" onclick="showCashEditor()" class="border border-slate-700 hover:bg-slate-800 text-slate-200 px-3 py-1 rounded text-sm">Edit</button>
                    </div>
                    <form id="cash-editor" onsubmit="saveCashBalance(event)" class="mt-3 space-y-2" hidden>
                        <label for="cash-input" class="block text-xs text-slate-400">Mock starting cash (₹)</label>
                        <input id="cash-input" type="number" min="0" step="0.01" required
                            class="w-full bg-slate-950 border border-slate-700 rounded p-2 text-sm text-slate-100">
                        <div class="flex gap-2">
                            <button type="submit" class="bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1 rounded text-sm">Save</button>
                            <button type="button" onclick="hideCashEditor()" class="border border-slate-700 hover:bg-slate-800 text-slate-200 px-3 py-1 rounded text-sm">Cancel</button>
                        </div>
                        <p id="cash-status" role="status" aria-live="polite" class="text-xs text-slate-400"></p>
                    </form>
                </div>

                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl shadow-lg">
                    <h2 class="text-md font-semibold mb-3 text-indigo-400">Upload Holdings Summary</h2>
                    <form id="holdings-upload-form" onsubmit="uploadHoldingsSummary(event)" class="space-y-3">
                        <input id="holdings-file" name="file" type="file" accept=".csv,.xls,.xlsx,.pdf,.txt" required
                            class="block w-full text-sm text-slate-300 file:mr-3 file:rounded file:border-0 file:bg-blue-600 file:px-3 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-blue-500">
                        <button type="submit" class="bg-blue-600 hover:bg-blue-500 text-white font-medium px-4 py-2 rounded text-sm transition">Upload summary</button>
                        <p id="holdings-upload-status" role="status" aria-live="polite" class="text-xs text-slate-400"></p>
                    </form>
                </div>
            </div>
        </header>

        <!-- Main Grid -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            <!-- Left Column: LLM Config & Risk Profiles -->
            <div class="space-y-6">
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl shadow-lg">
                    <h2 class="text-md font-semibold mb-3 text-indigo-400">What do you want to do today?</h2>
                    <input type="text" id="agent-prompt" aria-label="Strategy prompt" value="Optimize asset allocation for my available capital." autofocus class="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-sm font-normal italic caret-emerald-400 mb-3">
                    <button onclick="runAgent()" class="w-full bg-blue-600 hover:bg-blue-500 text-white font-medium py-2 rounded-lg text-sm transition">Run Advisory Agent</button>
                </div>

                <!-- Risk Profile Recommendations -->
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl shadow-lg">
                    <h2 class="text-md font-semibold mb-3 text-indigo-400">📊 Risk-Based Allocations</h2>
                    <div class="space-y-3">
                        <div class="p-3 bg-slate-950 rounded-lg border border-slate-800">
                            <div class="flex justify-between items-center mb-1">
                                <span class="font-medium text-emerald-400 text-sm">Low Risk (LIQUIDCASE)</span>
                                <button onclick="quickBuy('LIQUIDCASE', 'Zerodha Nifty 1D Rate Liquid ETF', 8, 116.75)" class="text-xs bg-emerald-600 hover:bg-emerald-500 px-2 py-1 rounded text-white">Buy (8 Units)</button>
                            </div>
                            <p class="text-xs text-slate-400">Expense: 0.23% | Focus: Capital Safety & Near-Zero Volatility</p>
                        </div>
                        <div class="p-3 bg-slate-950 rounded-lg border border-slate-800">
                            <div class="flex justify-between items-center mb-1">
                                <span class="font-medium text-blue-400 text-sm">Medium Risk (NIFTYBEES)</span>
                                <button onclick="quickBuy('NIFTYBEES', 'Nifty 50 ETF', 3, 250.00)" class="text-xs bg-blue-600 hover:bg-blue-500 px-2 py-1 rounded text-white">Buy (3 Units)</button>
                            </div>
                            <p class="text-xs text-slate-400">Expense: 0.05% | Focus: Blue-chip Growth & Stability</p>
                        </div>
                        <div class="p-3 bg-slate-950 rounded-lg border border-slate-800">
                            <div class="flex justify-between items-center mb-1">
                                <span class="font-medium text-amber-400 text-sm">High Risk (ITBEES)</span>
                                <button onclick="quickBuy('ITBEES', 'Nifty IT Sector ETF', 1, 500.00)" class="text-xs bg-amber-600 hover:bg-amber-500 px-2 py-1 rounded text-white">Buy (1 Unit)</button>
                            </div>
                            <p class="text-xs text-slate-400">Focus: Sectoral Upside & Aggressive Growth</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Center & Right Column: Terminal, Portfolio & Execution Controls -->
            <div class="lg:col-span-2 space-y-6">
                <!-- Agent Reasoning & RAG Output Terminal -->
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl shadow-lg">
                    <h2 class="text-md font-semibold mb-3 text-indigo-400">💬 Agent Advisory Log & RAG Context</h2>
                    <div id="terminal-output" class="bg-slate-950 border border-slate-800 p-4 rounded-lg h-48 overflow-y-auto text-xs font-mono text-slate-300">
                        System initialized with ₹1,000 cash. Zerodha daily document RAG ready. Select a profile or run agent query to generate recommendations...
                    </div>
                </div>

                <!-- Customer Holdings Summaries -->
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl shadow-lg">
                    <div class="flex items-center justify-between gap-3 mb-3">
                        <h2 class="text-md font-semibold text-indigo-400">Current Available Portfolio</h2>
                        <button id="refresh-summaries" type="button" onclick="fetchCustomerSummaries()" title="Refresh summaries" aria-label="Refresh summaries"
                            class="border border-slate-700 hover:bg-slate-800 text-slate-200 px-3 py-1.5 rounded text-sm">Refresh</button>
                    </div>
                    <div id="customer-portfolio-totals" class="mb-5 grid grid-cols-2 gap-y-3 md:grid-cols-4 md:gap-0" aria-live="polite">
                        <p class="text-sm text-slate-400">Loading customer totals...</p>
                    </div>
                    <div id="holdings-summaries" class="space-y-2" aria-live="polite">
                        <p class="text-sm text-slate-400">Loading summaries...</p>
                    </div>
                </div>
            </div>

        </div>
    </div>

    <script>
        let currentCashBalance = 1000;

        async function fetchAccountSummary() {
            const res = await fetch('/api/portfolio');
            const data = await res.json();
            currentCashBalance = data.cash_balance;
            document.getElementById('cash-display').textContent = '₹' + currentCashBalance.toFixed(2);
        }

        function showCashEditor() {
            document.getElementById('cash-input').value = currentCashBalance.toFixed(2);
            document.getElementById('cash-status').textContent = '';
            document.getElementById('cash-editor').hidden = false;
            document.getElementById('cash-input').focus();
        }

        function hideCashEditor() {
            document.getElementById('cash-editor').hidden = true;
        }

        function formatCurrency(value) {
            if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
            return new Intl.NumberFormat('en-IN', {
                style: 'currency',
                currency: 'INR',
                maximumFractionDigits: 2
            }).format(value);
        }

        function formatQuantity(value) {
            if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
            return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 3 }).format(value);
        }

        function appendPortfolioMetric(container, label, value, accentClass) {
            const metric = document.createElement('div');
            metric.className = 'min-w-0 border-l border-slate-800 pl-3 first:border-l-0 first:pl-0';
            const caption = document.createElement('p');
            caption.className = 'text-xs text-slate-400';
            caption.textContent = label;
            const amount = document.createElement('p');
            amount.className = `mt-1 truncate text-sm font-semibold ${accentClass || 'text-slate-100'}`;
            amount.textContent = value;
            metric.append(caption, amount);
            container.appendChild(metric);
        }

        function renderPortfolioCategory(category) {
            const section = document.createElement('section');
            section.className = 'border-t border-slate-800 pt-4 first:border-t-0 first:pt-0';

            const heading = document.createElement('div');
            heading.className = 'mb-3 flex items-center justify-between gap-3';
            const title = document.createElement('h3');
            title.className = 'text-sm font-semibold text-slate-100';
            title.textContent = category.label;
            const count = document.createElement('span');
            count.className = 'text-xs text-slate-400';
            count.textContent = `${category.holdings.length} holdings`;
            heading.append(title, count);
            section.appendChild(heading);

            const metrics = document.createElement('div');
            metrics.className = 'mb-4 grid grid-cols-2 gap-y-3 md:grid-cols-4 md:gap-0';
            appendPortfolioMetric(metrics, 'Invested', formatCurrency(category.totals.invested_value));
            appendPortfolioMetric(metrics, 'Current value', formatCurrency(category.totals.current_value), 'text-emerald-300');
            const pnlColor = category.totals.pnl_amount === null
                ? 'text-slate-100'
                : category.totals.pnl_amount >= 0 ? 'text-emerald-300' : 'text-rose-300';
            appendPortfolioMetric(metrics, 'Total return', formatCurrency(category.totals.pnl_amount), pnlColor);
            appendPortfolioMetric(metrics, 'Return', category.totals.pnl_percent === null ? '—' : `${category.totals.pnl_percent.toFixed(2)}%`);
            section.appendChild(metrics);

            const tableWrap = document.createElement('div');
            tableWrap.className = 'overflow-x-auto';
            const table = document.createElement('table');
            table.className = 'w-full min-w-[760px] text-left text-xs';
            const head = document.createElement('thead');
            head.className = 'border-b border-slate-700 text-slate-400';
            const headRow = document.createElement('tr');
            ['Holding', 'Qty / units', 'Avg. cost', 'Market price', 'Invested', 'Current value', 'P&L'].forEach(label => {
                const cell = document.createElement('th');
                cell.className = 'px-2 py-2 font-medium';
                cell.textContent = label;
                headRow.appendChild(cell);
            });
            head.appendChild(headRow);
            table.appendChild(head);

            const body = document.createElement('tbody');
            category.holdings.forEach(holding => {
                const row = document.createElement('tr');
                row.className = 'border-b border-slate-800/70';
                const nameCell = document.createElement('td');
                nameCell.className = 'px-2 py-2 text-slate-200';
                nameCell.textContent = holding.name;
                if (holding.isin) {
                    const isin = document.createElement('span');
                    isin.className = 'mt-1 block text-[10px] text-slate-500';
                    isin.textContent = holding.isin;
                    nameCell.appendChild(isin);
                }
                row.appendChild(nameCell);

                const pnl = holding.pnl_amount ?? (
                    typeof holding.current_value === 'number' && typeof holding.invested_value === 'number'
                        ? holding.current_value - holding.invested_value
                        : null
                );
                [
                    formatQuantity(holding.quantity),
                    formatCurrency(holding.avg_cost),
                    formatCurrency(holding.market_price),
                    formatCurrency(holding.invested_value),
                    formatCurrency(holding.current_value),
                    formatCurrency(pnl)
                ].forEach((value, index) => {
                    const cell = document.createElement('td');
                    const pnlColor = pnl === null ? 'text-slate-300' : pnl >= 0 ? 'text-emerald-300' : 'text-rose-300';
                    cell.className = `px-2 py-2 whitespace-nowrap ${index === 5 ? pnlColor : 'text-slate-300'}`;
                    cell.textContent = value;
                    row.appendChild(cell);
                });
                body.appendChild(row);
            });
            table.appendChild(body);
            tableWrap.appendChild(table);
            section.appendChild(tableWrap);
            return section;
        }

        async function saveCashBalance(event) {
            event.preventDefault();
            const status = document.getElementById('cash-status');
            status.textContent = 'Saving...';
            try {
                const response = await fetch('/api/portfolio/cash', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cash_balance: Number(document.getElementById('cash-input').value) })
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || 'Could not save the cash balance.');
                }
                currentCashBalance = result.cash_balance;
                document.getElementById('cash-display').textContent = '₹' + currentCashBalance.toFixed(2);
                hideCashEditor();
            } catch (error) {
                status.textContent = error.message;
            }
        }

        function renderHoldingSummary(file) {
            const details = document.createElement('details');
            details.className = 'border border-slate-800 rounded';

            const heading = document.createElement('summary');
            heading.className = 'cursor-pointer px-4 py-3 text-sm font-medium text-slate-200 hover:bg-slate-800/60';
            heading.textContent = file.kind === 'portfolio'
                ? `${file.filename} · ${file.holdings.length} holdings`
                : file.filename;
            details.appendChild(heading);

            const content = document.createElement('div');
            content.className = 'border-t border-slate-800 p-4';
            if (file.error) {
                content.textContent = file.error;
                content.className += ' text-sm text-amber-300';
            } else if (file.kind === 'portfolio') {
                file.categories.forEach(category => content.appendChild(renderPortfolioCategory(category)));
            } else {
                const text = document.createElement('pre');
                text.className = 'max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-300';
                text.textContent = file.content || 'No readable text found in this file.';
                content.appendChild(text);
            }

            details.appendChild(content);
            return details;
        }

        function renderCustomerTotals(files) {
            const container = document.getElementById('customer-portfolio-totals');
            container.replaceChildren();
            const portfolioFiles = files.filter(file => file.kind === 'portfolio' && file.totals);
            if (portfolioFiles.length === 0) {
                container.textContent = 'No portfolio totals available.';
                return;
            }

            const sumField = field => portfolioFiles.reduce((total, file) => {
                const value = file.totals[field];
                return total + (typeof value === 'number' && Number.isFinite(value) ? value : 0);
            }, 0);
            const invested = sumField('invested_value');
            const current = sumField('current_value');
            const totalReturn = current - invested;
            const returnPercent = invested ? totalReturn / invested * 100 : null;

            appendPortfolioMetric(container, 'Invested Value', formatCurrency(invested));
            appendPortfolioMetric(container, 'Current Value', formatCurrency(current), 'text-emerald-300');
            appendPortfolioMetric(
                container,
                'Total Profit/Loss',
                formatCurrency(totalReturn),
                totalReturn >= 0 ? 'text-emerald-300' : 'text-rose-300'
            );
            appendPortfolioMetric(
                container,
                'Return',
                returnPercent === null ? '—' : `${returnPercent.toFixed(2)}%`
            );
        }

        async function fetchCustomerSummaries() {
            const container = document.getElementById('holdings-summaries');
            const totalsContainer = document.getElementById('customer-portfolio-totals');
            const refreshButton = document.getElementById('refresh-summaries');
            refreshButton.disabled = true;
            try {
                const response = await fetch('/api/holdings', { cache: 'no-store' });
                const files = await response.json();
                if (!response.ok) {
                    throw new Error(files.error || 'Could not load holding summaries.');
                }
                renderCustomerTotals(files);
                container.replaceChildren();
                if (files.length === 0) {
                    container.textContent = 'No holding summaries found in customer_data.';
                    return;
                }
                files.forEach(file => container.appendChild(renderHoldingSummary(file)));
            } catch (error) {
                container.textContent = error.message;
                totalsContainer.textContent = error.message;
            } finally {
                refreshButton.disabled = false;
            }
        }

        async function quickBuy(symbol, name, quantity, price) {
            const res = await fetch('/api/trade', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'BUY', symbol, name, quantity, price })
            });
            const result = await res.json();
            const terminal = document.getElementById('terminal-output');
            terminal.innerHTML += `\\n[EXECUTION] ${result.message || result.error}`;
            terminal.scrollTop = terminal.scrollHeight;
            fetchAccountSummary();
        }

        async function quickSell(symbol, name, quantity, price) {
            const res = await fetch('/api/trade', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'SELL', symbol, name, quantity, price })
            });
            const result = await res.json();
            const terminal = document.getElementById('terminal-output');
            terminal.innerHTML += `\\n[EXECUTION] ${result.message || result.error}`;
            terminal.scrollTop = terminal.scrollHeight;
            fetchAccountSummary();
        }

        async function uploadHoldingsSummary(event) {
            event.preventDefault();
            const form = event.currentTarget;
            const status = document.getElementById('holdings-upload-status');
            status.textContent = 'Uploading...';

            try {
                const response = await fetch('/api/holdings/upload', {
                    method: 'POST',
                    body: new FormData(form)
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || 'Upload failed.');
                }

                status.textContent = `${result.filename} saved to customer_data.`;
                form.reset();
                fetchCustomerSummaries();
            } catch (error) {
                status.textContent = error.message;
            }
        }

        async function runAgent() {
            const prompt = document.getElementById('agent-prompt').value;
            const terminal = document.getElementById('terminal-output');
            terminal.textContent += `\\n[AGENT QUERY] ${prompt}\\nAnalyzing Zerodha market RAG docs...`;

            setTimeout(() => {
                terminal.textContent += `\\n[AGENT RESPONSE] Based on the available market documentation, review the portfolio summaries and risk options before making a simulated trade.`;
                terminal.scrollTop = terminal.scrollHeight;
            }, 800);
        }

        fetchAccountSummary();
        fetchCustomerSummaries();
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/portfolio")
def api_portfolio():
    return jsonify(get_account_summary())

@app.route("/api/portfolio/cash", methods=["PUT"])
def api_set_portfolio_cash():
    data = request.get_json(silent=True) or {}
    try:
        cash_balance = float(data.get("cash_balance"))
        saved_balance = set_account_cash_balance(cash_balance)
    except (TypeError, ValueError):
        return jsonify({"error": "Enter a valid, non-negative cash amount."}), 400
    return jsonify({"cash_balance": saved_balance})

def _header_field(label):
    normalized = re.sub(r"[^a-z0-9%&]+", "", label.lower())
    if normalized in {"type", "category", "assettype", "instrumenttype"}:
        return "category"
    if any(term in normalized for term in ("name", "company", "instrument", "scheme", "asset", "stock", "symbol", "fund", "groww")):
        return "name"
    if "isin" in normalized:
        return "isin"
    if "p&l" in label.lower():
        return "pnl_percent" if "%" in label else "pnl_amount"
    if "invested" in normalized:
        return "invested_value"
    if "qty" in normalized or "quantity" in normalized or "units" in normalized:
        return "quantity"
    if "avg" in normalized or "average" in normalized:
        return "avg_cost"
    if "ltp" in normalized or ("current" in normalized and any(term in normalized for term in ("price", "nav"))):
        return "market_price"
    if "current" in normalized or normalized == "value":
        return "current_value"
    if "returns" in normalized or "return" in normalized:
        return "returns"
    return None

def _classify_asset_category(label):
    normalized = re.sub(r"[^a-z0-9]+", " ", str(label or "").lower()).strip()
    if re.search(r"\b(mutual|fund|scheme|nav)\b", normalized):
        return "mutual_funds"
    if re.search(r"\b(equity|equities|stock|stocks|share|shares|asset class|short name)\b", normalized):
        return "stocks"
    return "other"

def _parse_number(value):
    text = str(value).replace(",", "").replace("−", "-")
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", text)
    if not match:
        return None
    number = float(match.group())
    return -abs(number) if "(" in text and ")" in text else number

def _items_from_rows(rows, default_category="other"):
    for header_index, header in enumerate(rows[:30]):
        fields = [_header_field(str(cell or "")) for cell in header]
        if "name" not in fields or "quantity" not in fields or "invested_value" not in fields:
            continue
        if "current_value" not in fields and "market_price" not in fields:
            continue
        return _items_from_fields(fields, rows[header_index + 1:], default_category)
    return []

def _items_from_fields(fields, rows, default_category="other"):
    items = []
    for row in rows:
        row = list(row) + [""] * max(0, len(fields) - len(row))
        item = {}
        for index, field in enumerate(fields):
            if field == "name":
                item[field] = str(row[index] or "").strip()
            elif field in {"isin", "category"}:
                item[field] = str(row[index] or "").strip()
            elif field:
                item[field] = _parse_number(row[index])

        name = item.get("name", "")
        if not name or name.lower() in {"total", "summary", "equity holdings", "fund holdings"}:
            continue
        if item.get("quantity") is None or item.get("invested_value") is None:
            continue
        if item.get("current_value") is None and item.get("market_price") is None:
            continue
        item["category"] = _classify_asset_category(item.get("category") or default_category or name)
        items.append(item)
    return items

def _portfolio_totals(holdings):
    invested = [item["invested_value"] for item in holdings if item.get("invested_value") is not None]
    current = [item["current_value"] for item in holdings if item.get("current_value") is not None]
    invested_total = sum(invested) if invested else None
    current_total = sum(current) if current else None
    pnl_total = current_total - invested_total if current_total is not None and invested_total is not None else None
    pnl_percent = pnl_total / invested_total * 100 if pnl_total is not None and invested_total else None
    return {
        "invested_value": invested_total,
        "current_value": current_total,
        "pnl_amount": pnl_total,
        "pnl_percent": pnl_percent,
    }

def _make_portfolio_summary(filename, holdings):
    category_labels = {
        "mutual_funds": "Mutual Funds",
        "stocks": "Stocks",
        "other": "Other",
    }
    categories = []
    for key, label in category_labels.items():
        category_holdings = [item for item in holdings if item.get("category", "other") == key]
        if category_holdings:
            categories.append({
                "key": key,
                "label": label,
                "holdings": category_holdings,
                "totals": _portfolio_totals(category_holdings),
            })
    return {
        "filename": filename,
        "kind": "portfolio",
        "holdings": holdings,
        "categories": categories,
        "totals": _portfolio_totals(holdings),
    }

def _pdf_header(words):
    triggers = {
        "instrument", "isin", "qty", "qty.", "quantity", "units", "avg", "average", "ltp",
        "invested", "current", "total", "returns", "p&l", "name", "company", "scheme", "asset", "stock", "symbol", "fund", "groww",
    }
    normalized = [word["text"].lower().strip(".,:%()") for word in words]
    has_groww_or_fund = "groww" in normalized or "fund" in normalized
    starts = []
    for word, token in zip(words, normalized):
        if token not in triggers or (token == "name" and has_groww_or_fund):
            continue
        starts.append((word["x0"], token))

    groups = []
    for x_position, token in sorted(starts):
        if groups and x_position - groups[-1][0] <= 24:
            groups[-1][1].append(token)
        else:
            groups.append([x_position, [token]])

    columns = []
    for index, (x_position, _) in enumerate(groups):
        next_position = groups[index + 1][0] if index + 1 < len(groups) else float("inf")
        header_words = [word for word in words if x_position <= word["x0"] < next_position]
        label = " ".join(word["text"] for word in header_words)
        field = _header_field(label)
        if field:
            center = sum((word["x0"] + word["x1"]) / 2 for word in header_words) / len(header_words)
            columns.append({"start": x_position, "center": center, "field": field})

    fields = {column["field"] for column in columns}
    if "name" not in fields or "quantity" not in fields or "invested_value" not in fields:
        return None
    if "current_value" not in fields and "market_price" not in fields:
        return None
    return {
        "columns": columns,
        "label": " ".join(word["text"] for word in words),
        "top": min(word["top"] for word in words),
        "bottom": max(word["top"] for word in words),
    }

def _pdf_headers(page):
    words = page.extract_words(x_tolerance=2, y_tolerance=2)
    headers = []
    for top in sorted({word["top"] for word in words}):
        band = [word for word in words if top <= word["top"] <= top + 14]
        header = _pdf_header(band)
        if header:
            header["top"] = top
            headers.append(header)

    unique_headers = []
    for header in sorted(headers, key=lambda item: (item["top"], -len(item["columns"]))):
        overlapping = next((item for item in unique_headers if header["top"] <= item["bottom"] + 2), None)
        if overlapping is None:
            unique_headers.append(header)
        elif len(header["columns"]) > len(overlapping["columns"]):
            unique_headers[unique_headers.index(overlapping)] = header

    for header in unique_headers:
        category = _classify_asset_category(header["label"])
        if category == "other":
            nearby_words = [
                word["text"] for word in words
                if header["top"] - 55 <= word["top"] < header["top"] - 2
            ]
            category = _classify_asset_category(" ".join(nearby_words))
        header["category"] = category
    return sorted(unique_headers, key=lambda item: item["top"])

def _items_from_pdf(path):
    import pdfplumber

    holdings = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            headers = _pdf_headers(page)
            for header_index, header in enumerate(headers):
                columns = header["columns"]
                quantity_column = next(column for column in columns if column["field"] == "quantity")
                name_column = next(column for column in columns if column["field"] == "name")
                name_end = next(
                    (column["start"] for column in columns if column["start"] > name_column["start"]),
                    quantity_column["start"],
                )
                body_top = header["bottom"] + 1
                body_bottom = headers[header_index + 1]["top"] - 3 if header_index + 1 < len(headers) else page.height
                body_words = [word for word in words if body_top <= word["top"] < body_bottom]

                quantity_anchors = []
                for word in body_words:
                    word_center = (word["x0"] + word["x1"]) / 2
                    nearest = min(columns, key=lambda column: abs(column["center"] - word_center))
                    if nearest is quantity_column and _parse_number(word["text"]) is not None:
                        if not quantity_anchors or word["top"] - quantity_anchors[-1] > 3:
                            quantity_anchors.append(word["top"])

                for row_index, anchor in enumerate(quantity_anchors):
                    row_top = body_top if row_index == 0 else (quantity_anchors[row_index - 1] + anchor) / 2
                    row_bottom = (
                        (anchor + quantity_anchors[row_index + 1]) / 2
                        if row_index + 1 < len(quantity_anchors)
                        else body_bottom
                    )
                    row_words = [word for word in body_words if row_top <= word["top"] < row_bottom]
                    item = {}
                    name_words = [
                        word["text"] for word in row_words
                        if word["x0"] >= name_column["start"] - 2
                        and word["x0"] < name_end
                        and not re.fullmatch(r"[₹$]?[-+]?\d[\d,]*(?:\.\d+)?%?", word["text"])
                    ]
                    item["name"] = " ".join(name_words).strip(" •")
                    item["category"] = header["category"]
                    for column in columns:
                        if column["field"] == "name":
                            continue
                        cell_words = []
                        for word in row_words:
                            word_center = (word["x0"] + word["x1"]) / 2
                            nearest = min(columns, key=lambda item: abs(item["center"] - word_center))
                            if nearest is column:
                                cell_words.append(word["text"])
                        cell_text = " ".join(cell_words)
                        if column["field"] == "isin":
                            item["isin"] = cell_text.strip()
                        else:
                            item[column["field"]] = _parse_number(cell_text)
                    if item.get("name") and item.get("quantity") is not None and item.get("invested_value") is not None and item.get("current_value") is not None:
                        holdings.append(item)
    return holdings

def _parse_holding_summary(path, filename):
    extension = filename.rsplit(".", 1)[-1].lower()
    if extension == "pdf":
        holdings = _items_from_pdf(path)
        if not holdings:
            return {"filename": filename, "error": "No itemized holdings table could be detected."}
        return _make_portfolio_summary(filename, holdings)

    sheets = []
    if extension == "csv":
        with open(path, newline="", encoding="utf-8-sig", errors="replace") as source:
            sheets.append(("Summary", [["" if cell is None else str(cell) for cell in row] for row in csv.reader(source)]))
    elif extension == "xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        sheets = [(sheet.title, [["" if value is None else str(value) for value in row] for row in sheet.iter_rows(values_only=True)]) for sheet in workbook.worksheets]
        workbook.close()
    elif extension == "xls":
        import xlrd

        workbook = xlrd.open_workbook(path, on_demand=True)
        sheets = [(sheet.name, [[str(value) for value in sheet.row_values(index)] for index in range(sheet.nrows)]) for sheet in workbook.sheets()]
        workbook.release_resources()
    else:
        with open(path, encoding="utf-8", errors="replace") as source:
            content = source.read()
        try:
            dialect = csv.Sniffer().sniff(content[:2048], delimiters=",\t;|")
            rows = [["" if cell is None else str(cell) for cell in row] for row in csv.reader(io.StringIO(content), dialect)]
            holdings = _items_from_rows(rows, filename)
            if holdings:
                return _make_portfolio_summary(filename, holdings)
        except csv.Error:
            pass
        return {"filename": filename, "kind": "text", "content": content}

    holdings = []
    for sheet_name, rows in sheets:
        for item in _items_from_rows(rows, f"{filename} {sheet_name}"):
            item["section"] = sheet_name
            holdings.append(item)
    if holdings:
        return _make_portfolio_summary(filename, holdings)
    return {"filename": filename, "error": "No itemized holdings table could be detected."}

@app.route("/api/holdings")
def api_holdings():
    os.makedirs(CUSTOMER_DATA_DIR, exist_ok=True)
    summaries = []
    for entry in sorted(os.scandir(CUSTOMER_DATA_DIR), key=lambda item: item.name.lower()):
        if not entry.is_file(follow_symlinks=False):
            continue
        filename = entry.name
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in ALLOWED_HOLDING_EXTENSIONS:
            continue
        try:
            summaries.append(_parse_holding_summary(entry.path, filename))
        except Exception:
            logging.exception("Could not parse holding summary %s", filename)
            summaries.append({"filename": filename, "error": "Could not parse this file."})
    response = jsonify(summaries)
    response.headers["Cache-Control"] = "no-store"
    return response

@app.route("/api/trade", methods=["POST"])
def api_trade():
    data = request.json
    res = execute_trade(
        action=data.get("action"),
        symbol=data.get("symbol"),
        name=data.get("name"),
        quantity=int(data.get("quantity")),
        price=float(data.get("price"))
    )
    return jsonify(res)

@app.route("/api/holdings/upload", methods=["POST"])
def upload_holdings_summary():
    if "file" not in request.files:
        return jsonify({"error": "Choose a holding summary file to upload."}), 400

    uploaded_file = request.files["file"]
    filename = secure_filename(uploaded_file.filename or "")
    if not filename:
        return jsonify({"error": "Choose a file with a valid name."}), 400

    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_HOLDING_EXTENSIONS:
        return jsonify({"error": "Supported formats: CSV, Excel, PDF, and TXT."}), 400

    os.makedirs(CUSTOMER_DATA_DIR, exist_ok=True)
    destination = os.path.join(CUSTOMER_DATA_DIR, filename)
    if os.path.exists(destination):
        return jsonify({"error": "A file with that name already exists."}), 409

    uploaded_file.save(destination)
    return jsonify({"filename": filename}), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=50001, debug=True, use_reloader=False)