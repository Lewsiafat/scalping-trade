# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Scalping Trade Analyzer Pro — a real-time scalping trading signal analysis system for cryptocurrency. Built entirely with Python standard library (no third-party dependencies). Single-file architecture with embedded HTML/CSS/JS frontend.

## Running the Application

```bash
python3 app_v2.py
# Serves on http://localhost:80

# Optional: specify port
python3 app_v2.py --port 8080

# Optional: nginx sub-path deployment
python3 app_v2.py --port 9000 --prefix /scalping
```

No dependency installation needed — uses only Python 3.11+ standard library.

## Architecture

**Single-file monolith** (`app_v2.py`): Backend HTTP server + embedded frontend (HTML/CSS/JS as string literals) in one file.

### Key Classes

- `ScalpingHandler` — HTTP request handler (extends `http.server.SimpleHTTPRequestHandler`). Routes requests to API endpoints or serves the embedded HTML page.
- `ScalpingAnalyzerPro` — Static-methods-only analysis engine. Implements all technical indicators (RSI, EMA, MACD, ATR, Bollinger Bands, Stochastic, Fibonacci) and signal scoring logic.
- `SnapshotManager` — Persists strategy snapshots to `snapshots.json`. Supports save/load/delete/search/CSV export.
- `SymbolManager` — Manages custom trading pairs in `custom_symbols.json`. Validates symbols against Binance API.
- `AlertManager` — Smart alert system persisted to `alerts.json`. Supports price/quality/signal alert types.

### Data Flow

1. Frontend sends AJAX request to `/api/analyze` with symbol + indicator parameters
2. Backend fetches candlestick data from Binance Public API (`/api/v3/klines`)
3. `ScalpingAnalyzerPro` computes all indicators and generates a composite signal score (0-5 stars)
4. JSON response returned with signals, action recommendation, and stop-loss/take-profit levels

### API Endpoints

- `GET /` — Serves embedded HTML page
- `GET /api/analyze` — Core analysis endpoint (params: symbol, interval, RSI/EMA/MACD settings)
- `GET /api/snapshots`, `POST /api/snapshot/save`, `DELETE /api/snapshot/{id}` — Snapshot CRUD
- `GET /api/snapshots/search`, `GET /api/snapshots/export` — Snapshot search & CSV export
- `GET /api/symbols`, `POST /api/symbol/add`, `DELETE /api/symbol/{symbol}` — Custom symbol management
- `GET /api/alerts`, `POST /api/alert/add`, `POST /api/alert/toggle`, `DELETE /api/alert/{id}` — Alert management
- `GET /api/presets` — Parameter preset configurations

### Data Files

- `snapshots.json` — Saved strategy snapshots (max 100, auto-trimmed)
- `custom_symbols.json` — User-added trading pairs
- `alerts.json` — Alert configurations and trigger history

### Helper Functions

- `fetch_with_retry(url, ctx, max_retries, base_timeout)` — HTTP request with exponential backoff retry. Classifies errors (HTTP 400 no-retry, 429 rate-limit, 5xx server error).
- `classify_error(e)` — Returns structured Chinese error message with error type classification.

### Frontend Features

- TradingView Lightweight Charts for real-time K-line display with EMA/Bollinger overlay
- Toast notification system (replaces native `alert()`)
- Progress indicator during analysis
- Custom UI Themes: Dynamic CSS variable management with "Soft Minimalist" aesthetic theme
- Interactive Layouts: Horizontal sidebar folding and vertical analysis panels with `localStorage` state saving

## Key Technical Details

- External data source: Binance Public API (no API key required)
- SSL verification is disabled for Binance API calls (`ssl.CERT_NONE`)
- Server port configurable via `--port <N>` / `-p <N>` (default: 80)
- URL path prefix configurable via `--prefix <PATH>` for nginx reverse proxy (default: empty)
- Signal quality scoring combines 8 indicators with weighted contributions, capped at 0-5
- MACD uses a simplified signal line calculation (not full EMA-based)
- Frontend auto-refreshes every 10 seconds when enabled
- API requests use exponential backoff retry (max 3 attempts) with error classification

## Language

This project uses Traditional Chinese (繁體中文) for all UI text, comments, and documentation.
