# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Scalping Trade Analyzer Pro — a real-time scalping trading signal analysis system for cryptocurrency. Built entirely with Python standard library (no third-party dependencies). Single-file architecture with embedded HTML/CSS/JS frontend.

## Running the Application

```bash
python3 app_v3.py
# Serves on http://localhost:80

# Optional: specify port
python3 app_v3.py --port 8080

# Optional: nginx sub-path deployment
python3 app_v3.py --port 9000 --prefix /scalping
```

No dependency installation needed — uses only Python 3.11+ standard library.

## Architecture

**Current version**: `app_v3.py` (v4.2.0). Legacy `app_v2.py` (v3.6.0) kept as reference.

**Single-file monolith** (`app_v3.py`): Backend HTTP server + embedded frontend (HTML/CSS/JS as string literals) in one file.

### Key Classes

- `ScalpingHandler` — HTTP request handler (extends `http.server.SimpleHTTPRequestHandler`). Routes requests to API endpoints or serves the embedded HTML page.
- `ScalpingAnalyzerPro` — Static-methods-only analysis engine. Implements SMC (Smart Money Concepts) analysis, technical indicators (RSI, EMA, MACD, ATR, Bollinger Bands, Stochastic), three-dimensional scoring (Trend/Structure/Momentum), two-stage signals (pre-alert → confirmed), and dynamic SL/TP.
- `SnapshotManager` — Persists strategy snapshots to `snapshots.json`. Supports save/load/delete/search/CSV export.
- `SymbolManager` — Manages custom trading pairs in `custom_symbols.json`. Validates symbols against Binance API.
- `AlertManager` — Smart alert system persisted to `alerts.json`. Supports price/quality/signal alert types.

### Data Flow

1. Frontend sends AJAX request to `/api/analyze` with symbol + indicator parameters
2. Backend fetches candlestick data from Binance Public API (`/api/v3/klines`) with MTF caching and data validation
3. `ScalpingAnalyzerPro` runs SMC analysis (Swing/BOS/OB/FVG/Sweep), computes indicators, calculates 3D scores (Trend/Structure/Momentum 0-100), and determines two-stage signal (pre-alert or confirmed)
4. JSON response returned with 3D scores, signal stage/label, SMC data, action recommendation, and structure-anchored SL/TP with R:R ratio

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
- `validate_kline_data(data)` — Validates K-line data integrity (count, zero-volume, timestamp continuity, anomalous spikes).
- `fetch_klines_cached(symbol, interval, limit, ctx)` — MTF memory cache for K-line data; skips re-fetch for unclosed candles.

### SMC Engine Methods

- `find_swing_points(data, n_small, n_large)` — Identifies Swing High/Low with dual-window (N=3/5), retains last 20.
- `detect_bos(swing_points, data)` — Detects Break of Structure via closing price breakthrough.
- `identify_order_blocks(data, bos_list)` — Identifies Order Blocks (last counter-trend candle before BOS, max 5).
- `identify_fvg(data)` — Identifies Fair Value Gaps (3-candle gaps, invalidated at 50% fill).
- `detect_liquidity_sweep(data, swing_points, atr)` — Detects Liquidity Sweeps (wick sweep + close reversal, depth ≥ ATR×0.5).

### Scoring & Signal Methods

- `calc_trend_score(bos_list, mtf, ema_fast, ema_slow, price, atr, bb)` — Trend dimension (0-100).
- `calc_structure_score(obs, fvgs, sweeps, price, atr, trend_dir)` — Structure dimension (0-100).
- `calc_momentum_score(rsi, macd, signal, hist, stoch_k, stoch_d, vol, taker_buy)` — Momentum dimension (0-100).
- `calc_dynamic_sl_tp(price, atr, signal_type, obs, fvgs, swings)` — Structure-anchored SL/TP with ATR clamp(1.0, 2.5). Returns None if R:R < 1.0.
- `check_pre_alert(price, atr, obs, swings, fvgs)` — Pre-alert trigger (OB/Swing/FVG proximity).
- `determine_signal_label(obs, fvgs, sweeps, price, atr)` — Signal type label (OB Entry > Sweep Confirm > FVG Support > Indicator Confluence).

### Frontend Features

- TradingView Lightweight Charts for real-time K-line display with EMA/Bollinger overlay
- Toast notification system (replaces native `alert()`)
- Progress indicator during analysis
- Custom UI Themes: Dynamic CSS variable management with "Soft Minimalist" aesthetic theme
- Interactive Layouts: Horizontal sidebar folding and vertical analysis panels with `localStorage` state saving
- Global Settings Modal: Centralized settings for customizing auto-refresh intervals and alert cooldown times.
- **3D Score Display**: Tri-color progress bars (Trend/Structure/Momentum) replacing old star rating.
- **Two-Stage Signal UI**: Pre-alert (orange gradient) vs confirmed signal (green/red) with signal type label badge.
- **i18n**: EN (default) / ZH_TW language switcher. Static text via `data-i18n` + `applyLang()`. Dynamic text via `LANG[currentLang].key`. `translateAction()` converts API action strings (always Chinese) to current language for display only.

## Key Technical Details

- External data source: Binance Public API (no API key required)
- SSL verification is disabled for Binance API calls (`ssl.CERT_NONE`)
- Server port configurable via `--port <N>` / `-p <N>` (default: 80)
- URL path prefix configurable via `--prefix <PATH>` for nginx reverse proxy (default: empty)
- K-line requests fetch 150 candles (up from 100) with data validation layer
- Three-dimensional scoring: Trend (BOS+EMA+BB) / Structure (OB+FVG+Sweep) / Momentum (RSI+MACD+Stoch+Volume), each 0-100. Legacy quality_score (0-5) = average / 20.
- Two-stage signal: Pre-alert triggers when price approaches key structure (OB/Swing/FVG ≤ ATR×0.5). Confirmed signal requires pre-alert + 3D thresholds + R:R ≥ 1.0. Expiry: pre-alert 6 bars, signal 3 bars.
- RSI uses Wilder's smoothing; MACD signal line uses EMA(9); Stochastic %D uses SMA(%K, 3); EMA defaults 9/21.
- Dynamic SL/TP anchored to SMC structure (OB/FVG/Swing) with ATR clamp(1.0, 2.5). R:R < 1.0 rejects signal.
- Frontend auto-refreshes based on customizable interval (2-10 seconds, default 10s) defined in Global Settings.
- API requests use exponential backoff retry (max 3 attempts) with error classification
- Browser alert notifications respect a configurable cooldown duration (default 1 min) to prevent spamming.

## Language

UI text is bilingual (EN/ZH_TW) via the i18n system. Backend Python code, API responses, and stored data always use Traditional Chinese (繁體中文). Comments and documentation use Traditional Chinese.
