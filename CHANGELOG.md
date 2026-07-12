# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> 🌐 [繁體中文版 CHANGELOG](CHANGELOG.zh-TW.md)

## [4.4.0] - 2026-07-12

### Added
- **Signal Profit Verifier** (`verify_signal_profit.py`): Per-signal event-study tool that replays historical klines, records each signal's full grade profile (overall / signal_stage / rr_grade / 3D scores / composite / label) at trigger time, and independently simulates each signal's outcome using its own entry/SL/TP (with fees, slippage, MFE/MAE). Reports win rate / PF / expectancy stratified by grade tier A–E. Paginated fetching lifts the single-request 1000-candle cap.
- **Precision & Label Regression Tests** (`test_precision_label.py`): Five tests covering low-price-coin ATR/SL precision and signal_label recency filtering.
- **Verification Report** (`specs/verify-signal-profit-report.md`): Full analysis — mechanism design, baseline results, P0 fixes, low-friction hypothesis-space research, sample-expansion refutation, and a 24-source deep-research synthesis of external scalping-strategy evidence.

### Fixed
- **Low-Price-Coin Signal Blackout**: `calculate_atr` and all price-scale roundings changed from `round(x, 2)` to `round(x, 8)`. At 2 decimals, low-price coins (DOGE ATR ≈ 0.00013, XRP ≈ 0.0018) rounded to zero, tripping the `atr <= 0` guard across the whole pipeline — DOGE produced zero signals and XRP's SL distances were scale-distorted. After the fix DOGE went from 0 to 319 events and XRP's median SL distance from 1.105% to 0.254% over 5000 candles.
- **signal_label Degeneration**: `determine_signal_label` now takes a `current_index` argument and only counts sweeps within the last 10 bars. Previously `detect_liquidity_sweep` scanned the full 150-bar window (100% of windows had a non-empty sweep list), so the `if sweeps:` short-circuit labeled 100% of events "Sweep 確認"; the other five labels were dead code. All six labels now appear.

### Notes
- Key finding (both internal 4,435+ event verification and external deep-research): SMC structure signals have **no statistically established edge at the K-line level (5m to 1h)**. 5m zero-friction expectancy ≈ 0; the 30m/1h positive-expectancy point estimate collapsed toward zero once the sample grew to n=130–155. Real short-horizon edge lives in sub-second L2 order book data, outside the current REST + pure-Python architecture.

## [4.3.0] - 2026-03-18

### Added
- **Backtest System** (`app_backtest.py` v2.0.0): Standalone backtesting engine with web UI on port 8081. Fetches historical klines from Binance, runs bar-by-bar signal analysis, and reports trades/equity/stats.
- **Parameter Optimizer** (`ParameterOptimizer`): Grid search engine that tests indicator parameter combinations (EMA/RSI/quality/entry mode) and ranks by PnL/MaxDrawdown ratio. Pre-fetches data once to avoid redundant API calls. New `/api/optimize` endpoint.
- **Trailing Stop**: After TP1 is hit, SL moves to entry price (break-even). Same-bar activation guard prevents immediate stop-out.
- **Partial Take-Profit**: TP1 closes 50% position, remaining runs to TP2 or trailing stop. Combined PnL calculation.
- **Lose Streak Protection**: Pauses trading for M bars after N consecutive losses (configurable, default N=3, M=10).
- **Entry Mode Controls**: Three new filter switches — `entry_mode` (strong_only/include_normal), `require_confirmed`, `allow_caution_rr` — all optimizable via grid search.
- **Exit Type Classification**: Stats now break down by exit type (SL/TP1/TP2/trailing_be/partial_sl/partial_tp1/partial_tp2).
- **CLI Backtest Runner** (`run_backtest.py`): Lightweight CLI script for quick backtesting without the web server.

## [4.2.2] - 2026-03-17

### Fixed
- **Signal Symmetry**: Fixed three asymmetric logic bugs in the signal engine that suppressed sell signals:
  - `calc_trend_score()`: MTF disagreement penalty changed from -10 to -25 (symmetric with +25 agreement bonus).
  - `calc_momentum_score()`: RSI divergence thresholds changed from 35/65 to 30/70 (symmetric around midpoint 50).
  - `analyze_entry_signal()`: Sell branch now uses `bearish_strength = 100 - trend_score` for composite/min_floor calculation, fixing the contradiction where stronger bearish trends made sell signals harder to trigger.
- **Sell Signal UI**: API response `composite_score`, `min_floor`, and `composite_formula` now reflect the flipped bearish strength values when a sell signal is active.

### Added
- **Trading Guide & Developer Guide**: New documentation in `docs/trading-guide.md` and `docs/developer-guide.md` covering analysis flow, scoring logic, and SMC engine internals.

## [4.2.1] - 2026-03-13

### Fixed
- **Real-time Price Update**: Main analysis endpoint (`/api/analyze`) now bypasses `fetch_klines_cached()` and fetches fresh data on every request. Previously, the MTF cache caused price and indicators to freeze for up to 5 minutes (entire candle duration). MTF 15m cache remains unchanged.

## [4.2.0] - 2026-03-12

### Removed
- **PresetManager**: Removed `PresetManager` class and `/api/presets` endpoint. Three presets (scalping/daytrading/conservative) caused parameter-threshold mismatch and added unnecessary complexity.
- **Interval Selection**: Removed interval dropdown and all interval-related API parameters. Manual scalping on 1m is impractical (signal expires before order placement).
- **Indicator Parameter Controls**: Removed RSI/EMA/MACD settings UI. Parameters are now fixed and optimized for the 5m+15m combination.

### Changed
- **Fixed 5m Framework**: Analysis now uses fixed 5m interval with 15m MTF confirmation. All scoring thresholds are aligned to this combination.
- **Simplified API**: `/api/analyze` only requires `symbol` parameter. All indicator parameters use `FIXED_PARAMS` (RSI 14, EMA 9/21, MACD 12/26/9).
- **Simplified Sidebar**: Only trading pair selector, analyze button, auto-refresh, and advanced tools remain.

## [4.1.0] - 2026-03-12

### Added
- **Partial Sweep Detection**: Three-tier Sweep classification (Full +25 / Partial +15 / Near +8) in `detect_liquidity_sweep()`. Lowers the barrier for Structure Score without sacrificing signal quality.
- **Momentum Trend Continuation**: New `trend_direction` parameter in `calc_momentum_score()`. RSI healthy zone (+10), MACD continuation (+15), Stochastic continuation (+10) — mutually exclusive with reversal scores (takes the higher).
- **Weighted Composite Scoring**: Replaces hard AND-threshold signal logic with `composite = T×0.35 + S×0.40 + M×0.25` plus `min_floor` safeguard.
- **R:R Grading System**: Four-tier R:R classification (good ≥1.5 / acceptable ≥1.0 / caution ≥0.7 / reject <0.7). R:R now calculated from TP1 instead of TP2.
- **Score Breakdown Panel**: Frontend `<details>` collapsible panel showing per-item scoring details for all three dimensions. API returns `score_breakdown` field.
- **Composite & Min Floor Display**: Shown below the 3D progress bars with R:R grade.
- **signal_engine_b.py**: Alternative signal engine using boolean condition accumulation (10 conditions, ≥5 triggers signal) for A/B comparison testing.
- **test_signal_compare.py**: A/B comparison test script. Supports `--loop` for continuous refresh.

### Changed
- `calc_trend_score()`, `calc_structure_score()`, `calc_momentum_score()` now return `{'score': int, 'details': list}` instead of plain `int`.
- `calc_dynamic_sl_tp()` returns `rr_grade` and `extended_rr` fields. R:R 0.7-1.0 downgrades to pre_alert instead of full rejection.
- `analyze_entry_signal()` derives `trend_direction` from BOS + EMA for momentum continuation scoring.
- API response adds `composite_score`, `min_floor`, `score_breakdown` fields. Sweep data includes `strength` field.
- i18n: Added `score_breakdown_title` key (EN/ZH_TW).

## [4.0.0] - 2026-03-09

### Added
- **SMC Engine**: Smart Money Concepts analysis — Swing Points, Break of Structure (BOS), Order Blocks (OB), Fair Value Gaps (FVG), Liquidity Sweep detection.
- **3D Signal Scoring**: Three-dimensional scoring system (Trend / Structure / Momentum, each 0-100) replaces the old 0-5 star quality score.
- **Two-Stage Signals**: Pre-alert (approaching key structure) → Confirmed signal (3D thresholds + R:R met) with automatic expiry mechanism.
- **Dynamic SL/TP**: Structure-anchored stop-loss/take-profit with ATR clamp(1.0, 2.5). Signals rejected when R:R < 1.0.
- **Signal Labels**: Categorized signal types — OB Entry, Sweep Confirm, FVG Support, Indicator Confluence.
- **3D Progress Bars**: Frontend tri-color progress bars (Trend purple / Structure gold / Momentum green) replacing star display.
- **Pre-Alert UI**: Orange gradient action card for pre-alerts with structure proximity message.
- **R:R Visual Indicator**: Risk-reward ratio display with status icons (≥2.0 ✅ / ≥1.5 🟡 / <1.5 ⚠️).
- **app_v3.py**: New main entry point (v4.0.0). Original `app_v2.py` preserved as v3.6.0 reference.

### Changed
- **RSI**: Switched to Wilder's smoothing method.
- **MACD**: Signal line changed to EMA(9), default parameters 12/26/9.
- **Stochastic**: %D changed to SMA(%K, 3).
- **EMA**: Default periods changed to 9/21.
- **Volume CVD**: Now uses `taker_buy_base_volume` with window size 20.
- **K-line requests**: Increased from 100 to 150 candles.
- **Data pipeline**: Added `validate_kline_data()` validation layer and `fetch_klines_cached()` MTF memory cache.
- **API response**: Added 7 new fields — `trend_score`, `structure_score`, `momentum_score`, `signal_label`, `signal_stage`, `pre_alert`, `smc`.
- **i18n**: Added 13 new LANG keys per language for SMC terminology.

### Removed
- **Fibonacci Retracement**: Removed `calculate_fibonacci_levels()` method and all references (frontend UI included).

## [3.6.0] - 2026-03-06

### Added
- **Global Settings Modal**: A new centralized settings interface accessible via the gear icon in the header.
- **Refresh Interval Control**: Users can now customize the auto-refresh interval between 2 to 10 seconds via the Global Settings.
- **Alert Cooldown Control**: Browser notification cooldown is now configurable with options for 30s, 1m, and 3m.

### Changed
- Moved the "Analyze Signal" button and "Auto-refresh" toggle from the settings sidebar to the top action bar for better accessibility.
- Enlarged the click target areas for analysis and auto-refresh controls.
- Enhanced the modal background with a darker opacity and a blur backdrop-filter to improve focus and readability over the charts.

## [3.5.0] - 2026-03-05

### Added
- **i18n Support**: Full internationalization with English (EN, default) and Traditional Chinese (ZH_TW) language switching.
  - Language switcher buttons (EN / 中文) in the header.
  - Static UI text translated via `data-i18n` attributes and `applyLang()` function.
  - Dynamic content translated: analysis results, SL/TP, MTF, volume analysis, RSI/EMA/MACD/Bollinger/Stochastic/Fibonacci indicators.
  - Snapshot Manager and Alert Settings modals fully translated.
  - `translateAction()` function maps API action strings (觀望/考慮買入/強烈買入/考慮賣出/強烈賣出) to current language.
  - Language preference persisted in `localStorage`.
- **Version Display**: Added internal versioning mechanism (`VERSION` constant in `app_v2.py`) and UI display in header and page title.

## [3.4.2] - 2026-03-04


### Fixed
- Improve symbol addition stability.

## [3.4.1] - 2026-03-03

### Added
- Feature: Added a cooldown mechanism to browser notifications to prevent spamming.

### Changed
- UX: Replaced native `prompt()` dialogs with custom HTML Modals for adding Custom Symbols and configuring Alerts, improving user experience and input validation.

## [3.4.0] - 2026-03-03

### Added
- Feature: Custom UI themes - implemented dynamic CSS variable management with theme-switching logic.
- Feature: Interactive layouts - support collapsing the main settings sidebar horizontally and folding detailed analysis sections vertically.
- UX: Saved structural UI states (sidebar/panels toggles) into `localStorage` for continuity across page loads.
- UI enhancement: Hand-crafted "Soft Minimalist" aesthetic theme offering a polished, muted pastel color palette with gentle box shadows, and applied it to inputs, buttons, and layouts seamlessly.

## [3.3.1] - 2026-03-02

### Changed
- Translated `README.md` and `CHANGELOG.md` from Traditional Chinese to English
- Added `README.zh-TW.md` and `CHANGELOG.zh-TW.md` as Traditional Chinese mirrors
- Moved `SPEC.md` from project root to `docs/SPEC.md`
- Added `GEMINI.md` as Gemini CLI project guide

## [3.3.0] - 2026-03-02

### Added
- CLI port selection: `--port <N>` / `-p <N>` argument to specify the listening port at startup (default: 80)
- URL path prefix support: `--prefix <PATH>` argument so the app works correctly under an nginx sub-path (e.g. `/scalping`)
- Dynamic PREFIX routing in the backend: `do_GET` / `do_POST` / `do_DELETE` all respect the path prefix
- HTML dynamically injects `window.APP_PREFIX` global variable so all frontend API requests automatically include the path prefix

## [3.2.0-beta] - 2026-03-02

### Added
- Live candlestick chart: integrated TradingView Lightweight Charts for real-time candlestick display with indicator overlays
- EMA / Bollinger Bands overlay time-series: EMA lines and Bollinger Bands bands rendered on the chart
- Smart retry mechanism: API requests support exponential backoff retry (`fetch_with_retry`) with error-type classification
- Chinese error messages: structured error classification with user-friendly Chinese prompts (`classify_error`)
- Progress indicator: displays loading progress during analysis
- Toast notification system: replaces native `alert()` dialogs for a better user experience

### Changed
- Frontend UI significantly improved: added chart area and Toast notification component
- Backend: added `fetch_with_retry()` and `classify_error()` helper functions
- API request error handling improved (HTTP 429 rate-limit and 5xx server errors now auto-retry)

## [3.1.0] - 2026-03-01

### Added
- Snapshot enhancements: delete function, CSV export (UTF-8 BOM), multi-condition search & filter
- Smart alert system: three alert types (price / quality score / signal), with enable / disable / delete support
- Quick parameter presets: one-click switch between ultra-short scalp / short-term / conservative strategies
- New API endpoints: `/api/snapshots/export`, `/api/snapshots/search`, `/api/alerts`, `/api/alert/add`, `/api/alert/toggle`, `/api/presets`

### Fixed
- JavaScript template string syntax error
- Function name mismatch issue

## [3.0.0] - 2026-03-01

### Added
- 3 new technical indicators: Bollinger Bands, Stochastic Oscillator, Fibonacci Retracement
- Strategy snapshot management: save and view historical snapshots
- Custom trading pair management: add / delete personalized instrument list
- New API endpoints: `/api/snapshots`, `/api/symbols`, `/api/snapshot/save`, `/api/symbol/add`

### Changed
- Streamlined header height, saving 50% of display space
- Optimized signal scoring logic to incorporate the new indicators

## [2.0.0] - 2026-02-28

### Added
- Volume analysis (CVD, volume ratio)
- Multi-timeframe confirmation
- Dynamic stop-loss / take-profit calculation (ATR)
- Signal quality scoring system (0–5 stars)
- Browser notification support

### Changed
- UI layout optimized (recommended action moved to top)

## [1.0.0] - 2026-02-26

### Added
- Initial release
- Basic technical indicators (RSI, EMA, MACD)
- Real-time data analysis
- Responsive web design
