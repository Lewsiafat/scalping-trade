# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> 🌐 [繁體中文版 CHANGELOG](CHANGELOG.zh-TW.md)

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
