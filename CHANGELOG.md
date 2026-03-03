# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> 🌐 [繁體中文版 CHANGELOG](CHANGELOG.zh-TW.md)

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
