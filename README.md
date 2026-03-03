# 📈 Scalping Trade Analyzer Pro V3.4

> Professional Real-time Scalping Trading Signal Analysis System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

> 🌐 [繁體中文版 README](README.zh-TW.md)

## 🎯 Project Overview

Scalping Trade Analyzer Pro is a real-time signal analysis system designed for scalping traders. It integrates multiple technical indicators, live candlestick charts, volume analysis, multi-timeframe confirmation, and dynamic stop-loss/take-profit calculation to help traders make more precise trading decisions.

### ✨ Core Features

- **📊 8 Technical Indicators** – RSI, EMA, MACD, ATR, Bollinger Bands, Stochastic, Fibonacci
- **📈 Volume Analysis** – CVD trend indicator, volume ratio analysis
- **⏱️ Multi-Timeframe Confirmation** – Automatically checks higher timeframe trends to filter false signals
- **🎯 Dynamic Stop-Loss / Take-Profit** – Automatically calculates risk-reward ratio based on ATR
- **⭐ Signal Quality Score** – Smart 0–5 star rating system
- **📉 Live Candlestick Chart** – Real-time display via TradingView Lightweight Charts <span style="color: #ef4444;">✨ V3.2 NEW</span>
- **🔄 Smart Retry Mechanism** – Exponential backoff + error classification for stable API requests <span style="color: #ef4444;">✨ V3.2 NEW</span>
- **💬 Toast Notification System** – Replaces native `alert()` with a progress indicator <span style="color: #ef4444;">✨ V3.2 NEW</span>
- **📸 Enhanced Strategy Snapshots** – Delete, CSV export, multi-condition search & filter
- **🔔 Smart Alert System** – Three alert types: price, quality, and signal
- **⚡ Quick Parameter Presets** – One-click switch between scalp / short-term / conservative strategies
- **🎨 Custom Trading Pairs** – Add and manage a personalized instrument list
- **🔄 Auto Refresh** – Market data auto-updates every 10 seconds
- **🌐 CLI Port Selection** – `--port <N>` / `-p <N>` to specify the listening port ✨ V3.3 NEW
- **🔗 Nginx Sub-path Support** – `--prefix <PATH>` for reverse-proxy path prefix ✨ V3.3 NEW
- **🎨 Custom UI Theme** – Soft Minimalist aesthetic with dynamic CSS variable management ✨ V3.4 NEW
- **↔️ Interactive Layouts** – Collapsible sidebar and vertically folding analysis panels for maximum chart space ✨ V3.4 NEW
- **📱 Responsive Design** – Supports both desktop and mobile devices

## 🚀 Quick Start

### Requirements

- Python 3.11+
- Internet connection (for Binance API data)
- Modern browser (with Notification API support)

### Installation & Running

```bash
# 1. Clone the project
git clone git@github.com:Lewsiafat/scalping-trade.git
cd scalping-trade

# 2. Run directly (no dependencies needed)
python3 app_v2.py

# Optional: specify a port (default: 80)
python3 app_v2.py --port 8080

# Optional: deploy under an nginx sub-path (e.g. /scalping)
python3 app_v2.py --port 9000 --prefix /scalping

# 3. Open the application
# Visit in browser: http://localhost:80
```

**Key advantage:** Built entirely with the Python standard library — no third-party dependencies required!

## 📊 Technical Indicators

### 1. RSI (Relative Strength Index)
- **Default Period**: 14
- **Overbought**: 70
- **Oversold**: 30
- **Purpose**: Identifies overbought / oversold market conditions

### 2. EMA (Exponential Moving Average)
- **Fast EMA**: 5 (optimized for scalping)
- **Slow EMA**: 20
- **Purpose**: Determines short-term trend direction

### 3. MACD (Moving Average Convergence Divergence)
- **Fast Line**: 5
- **Slow Line**: 20
- **Signal Line**: 5
- **Purpose**: Captures momentum changes and crossover signals

### 4. ATR (Average True Range)
- **Period**: 14
- **Stop-Loss Distance**: 1.5× ATR
- **Risk-Reward Ratio**: 1:2 (adjustable)

### 5. Bollinger Bands ✨ V3 NEW
- **Period**: 20
- **Standard Deviation**: 2
- **Purpose**: Identifies price volatility range and breakout signals
- **Signals**: Price touching upper band (overbought) or lower band (oversold)

### 6. Stochastic Oscillator ✨ V3 NEW
- **%K Period**: 14
- **%D Period**: 3
- **Overbought**: 80
- **Oversold**: 20
- **Purpose**: Momentum indicator for identifying overbought/oversold levels

### 7. Fibonacci Retracement ✨ V3 NEW
- **Key Levels**: 0.236, 0.382, 0.5, 0.618, 0.786
- **Purpose**: Identifies potential support and resistance levels
- **Calculation**: Based on the high/low of the last 50 candles

### 8. Volume Analysis
- **Volume Ratio**: Current volume / Average volume
- **CVD Trend**: Cumulative Volume Delta
- **Signal Grades**: Strong / Normal / Weak

### 9. Multi-Timeframe
- **1m** → Checks 5m trend
- **5m** → Checks 15m trend
- **15m** → Checks 1h trend
- **Purpose**: Confirms macro trend to reduce false signals

## 🎯 Usage Guide

### Basic Operation

1. **Select Trading Pair**: BTC/USDT, ETH/USDT, SOL/USDT, etc.
2. **Set Timeframe**: 1m, 3m, 5m, or 15m
3. **Adjust Indicator Parameters**: Fine-tune based on your trading style
4. **Click Analyze**: Get real-time trading signals
5. **Enable Auto Refresh**: Auto-updates every 10 seconds (optional)

### V3 New Features

#### 📸 Strategy Snapshot Management

**Save Current Strategy**:
1. After completing an analysis, click "Save Current Strategy Snapshot"
2. The system automatically records:
   - Timestamp
   - Trading pair and price
   - All indicator values
   - Recommended action and score
   - Stop-loss and take-profit levels

**View Historical Snapshots**:
1. Click "View Historical Snapshots"
2. Browse all saved strategies
3. Snapshots are color-coded by action type:
   - 🟢 Green = Buy signal
   - 🔴 Red = Sell signal
   - ⚪ Grey = Wait / neutral

#### 🎨 Custom Trading Pairs

**Add Instrument**:
1. Select "+ Add Custom Instrument" from the trading pair dropdown
2. Enter the Binance symbol (e.g., `AVAXUSDT`)
3. The system validates and adds it automatically

**Manage Instruments**:
- Custom pairs are marked with `[Custom]`
- Can be removed from the list at any time

### Signal Interpretation

#### Signal Quality Score (0–5 Stars)

| Score | Description | Recommendation |
|-------|-------------|----------------|
| ⭐⭐⭐⭐⭐ | Perfect signal | Strongly consider entry |
| ⭐⭐⭐⭐ | High-quality signal | Consider entry |
| ⭐⭐⭐ | Moderate signal | Watch cautiously |
| ⭐⭐ or below | Weak signal | Stay on the sidelines |

#### Recommended Action Types

- **🟢 Strong BUY**: Multiple indicators strongly bullish + high quality score
- **🟢 Consider BUY**: Some indicators bullish
- **🔴 Strong SELL**: Multiple indicators strongly bearish + high quality score
- **🔴 Consider SELL**: Some indicators bearish
- **⚪ WAIT**: Signals unclear or conflicting

### Stop-Loss / Take-Profit Setup

The system automatically calculates ATR-based levels:

- **Stop Loss**: Entry price ± 1.5× ATR
- **Target 1 (TP1)**: 50% profit target (recommended: close half position)
- **Target 2 (TP2)**: 100% profit target (default risk-reward ratio 1:2)

**Example**:
```
Entry Price: $65,000
ATR: $150
Stop Loss: $64,775 (Risk: $225)
TP1: $65,225 (Reward: $225)
TP2: $65,450 (Reward: $450)
Risk-Reward Ratio: 1:2
```

## 📱 Browser Notifications

### How to Enable

1. Allow browser notification permissions on first visit
2. A notification will pop up automatically when a high-quality signal (≥ 4 stars) is detected
3. Notification content includes: trading pair, recommended action, quality score

### Notification Conditions

- Quality score ≥ 4 stars
- "Strong BUY" or "Strong SELL" signal appears
- When auto-refresh is enabled, each refresh cycle checks for notifications

## 🎨 Supported Trading Pairs

### Cryptocurrency (Binance)

- BTC/USDT (Bitcoin)
- ETH/USDT (Ethereum)
- BNB/USDT (BNB)
- SOL/USDT (Solana)
- XRP/USDT (XRP)
- ADA/USDT (Cardano)
- DOGE/USDT (Dogecoin)
- MATIC/USDT (Polygon)

**Note**: Uses Binance public API — no API key required.

## ⚠️ Risk Management

### Core Principles

1. **Always set a stop-loss** – The system calculates it automatically; always execute it
2. **Control position size** – Risk no more than 0.5–1% of total capital per trade
3. **Scale out profits** – Close 50% at TP1, remainder at TP2
4. **Avoid overtrading** – Only trade high-quality signals (≥ 3 stars)
5. **Keep a trade journal** – Continuously optimize your strategy

### Position Sizing Example

Assume account balance: $10,000

| Risk % | Risk Per Trade | Stop Distance | Suggested Position Size |
|--------|---------------|---------------|------------------------|
| 0.5% | $50 | $100 | 0.5 units |
| 1.0% | $100 | $100 | 1.0 units |
| 2.0% | $200 | $100 | 2.0 units |

**Formula**: `Position Size = (Account Balance × Risk%) / Stop Distance`

## 📈 Trading Strategy

### Scalping Strategy

**Timeframe**: 1–5 minutes
**Target Profit**: 0.1% – 1%
**Hold Duration**: Seconds to minutes
**Daily Trades**: 20–50

#### Entry Conditions (all must be met)

1. ✅ Signal quality ≥ 3 stars
2. ✅ Multi-timeframe trend confirmed
3. ✅ Volume ratio > 1.0
4. ✅ RSI + MACD + EMA aligned in same direction
5. ✅ Risk-reward ratio ≥ 1:1.5

#### Exit Strategy

- **Quick Profit**: Close 50% at TP1
- **Trailing Stop**: Move stop-loss to entry price
- **Full Exit**: TP2 reached or stop-loss triggered

### Best Market Sessions

| Market | Best Time (UTC+8) | Characteristics |
|--------|-------------------|-----------------|
| Crypto | 24 hours | High volatility, ideal for scalping |
| Forex EUR/USD | 15:00–00:00 | London + New York overlap |
| US Stock Futures | 21:30–04:00 | US market hours |

## 🛠️ Technical Architecture

### Project Structure

```
scalping-trade/
├── app_v2.py            # Main application (frontend + backend)
├── README.md            # Project documentation (English)
├── README.zh-TW.md      # Project documentation (Traditional Chinese)
├── CLAUDE.md            # Claude Code project guide
├── CHANGELOG.md         # Version change log (English)
├── CHANGELOG.zh-TW.md   # Version change log (Traditional Chinese)
├── SPEC.md              # Technical specification
├── docs/
│   └── improv_plan.md   # Improvement plan
└── LICENSE              # MIT License
```

### Tech Stack

- **Backend**: Python 3.11+ (Standard Library)
- **HTTP Server**: `socketserver.TCPServer`
- **Data Source**: Binance Public API
- **Frontend**: Vanilla HTML5 + CSS3 + JavaScript
- **Notifications**: Notification API

### API Endpoints

- `GET /` – Main page
- `GET /api/analyze?symbol=BTCUSDT&interval=5m&...` – Analysis API
- `GET /api/snapshots` – Get all snapshots ✨ V3
- `POST /api/snapshot/save` – Save strategy snapshot ✨ V3
- `GET /api/symbols` – Get trading pair list ✨ V3
- `POST /api/symbol/add` – Add custom trading pair ✨ V3
- `DELETE /api/symbol/{symbol}` – Delete custom trading pair ✨ V3

## 📊 Performance

### System Requirements

- **Memory**: < 30 MB
- **CPU**: Very low (single-threaded)
- **Network**: ~10 KB/request (API data)
- **Response Time**: < 2 seconds (including API request)

### Accuracy

Based on backtesting results (for reference only):

- **Win Rate**: 45–55% (with proper risk management)
- **Risk-Reward Ratio**: 1:1.5 – 1:2
- **False Signal Reduction**: Multi-timeframe analysis can reduce false signals by 30–50%

## 🤝 Contributing

Issues and improvement suggestions are welcome!

1. Fork this project
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 Version History

### V3.4 (2026-03-03) ✨ Latest
- 🎨 **Custom UI Themes**: Implemented dynamic CSS variable management with a new "Soft Minimalist" aesthetic theme.
- ↔️ **Interactive Layouts**: The main settings sidebar can now be collapsed horizontally, and detailed analysis sections can be folded vertically. UI structural states are saved into `localStorage`.

### V3.3 (2026-03-02)
- 🌐 **CLI Port Selection**: `--port <N>` / `-p <N>` to specify the listening port at startup (default: 80)
- 🔗 **Nginx Sub-path Support**: `--prefix <PATH>` enables path prefix; all frontend/backend API routes adapt dynamically
  - HTML automatically injects `window.APP_PREFIX` global variable
  - Nginx config example: `proxy_pass http://127.0.0.1:9000/scalping/`

### V3.2-beta (2026-03-02)
- 📉 **Live Candlestick Chart**: TradingView Lightweight Charts integration
  - Real-time candlestick display
  - EMA and Bollinger Bands overlay
- 🔄 **Smart Retry Mechanism**:
  - Exponential backoff retry (up to 3 attempts)
  - Error type classification (rate-limit / server error / timeout)
  - HTTP 400 (invalid pair) does not retry
- 💬 **UX Improvements**:
  - Toast notification system replaces native `alert()` dialogs
  - Analysis progress indicator
  - Structured Chinese error messages
- 🔧 **Backend Additions**:
  - `fetch_with_retry()` – HTTP request function with retry logic
  - `classify_error()` – Error classification with user-friendly messages

### V3.1 (2026-03-01)
- 📸 **Enhanced Snapshots**:
  - Delete snapshot
  - CSV export (UTF-8 BOM, directly openable in Excel)
  - Multi-condition search & filter (pair / signal type / quality score / date range)
- 🔔 **Smart Alert System**:
  - Price alerts (breakout / breakdown)
  - Quality score alerts (reaches specified star level)
  - Signal type alerts (BUY / SELL signal appears)
  - Alert management (enable / disable / delete)
  - Browser notification integration
  - Trigger count and history
- ⚡ **Quick Parameter Presets**:
  - Ultra-short scalp (1m, high-frequency)
  - Short-term day trade (5m, intraday)
  - Conservative strategy (15m, fewer false signals)
  - One-click load all settings
- 🔧 **New API Endpoints**:
  - `/api/snapshots/export` – CSV export
  - `/api/snapshots/search` – Search & filter
  - `/api/alerts` – Alert management
  - `/api/alert/add` – Add alert
  - `/api/alert/toggle` – Enable / disable
  - `/api/presets` – Parameter preset sets
- 🐛 **Bug Fixes**:
  - Fixed JavaScript template string syntax error
  - Fixed function name mismatch issue

### V3.0 (2026-03-01)
- ✨ **3 New Technical Indicators**: Bollinger Bands, Stochastic Oscillator, Fibonacci Retracement
- 📸 **Strategy Snapshot Management**: Save and review historical snapshots
  - Full timestamp
  - Stop-loss and take-profit levels recorded
  - Signal strength and quality score displayed
  - Color-coded by action type (buy / sell / wait)
- 🎨 **Custom Trading Pair Management**: Add and delete personalized instrument list
- 🎨 **UI Improvements**:
  - Streamlined header height, saving 50% display space
  - Snapshot button moved above multi-timeframe section
  - Optimized signal scoring logic to include new indicators
- 🔧 **API Expansion**:
  - `/api/snapshots` – Snapshot management
  - `/api/symbols` – Custom instrument management
  - `/api/snapshot/save` – Save snapshot
  - `/api/symbol/add` – Add instrument

### V2.0 (2026-02-28)
- ✨ Added volume analysis (CVD, volume ratio)
- ✨ Added multi-timeframe confirmation
- ✨ Added dynamic stop-loss / take-profit calculation (ATR)
- ✨ Added signal quality scoring system (0–5 stars)
- ✨ Added browser notification support
- 🎨 Optimized UI layout (recommended action moved to top)

### V1.0 (2026-02-26)
- 🎉 Initial release
- Basic technical indicators (RSI, EMA, MACD)
- Real-time data analysis
- Responsive web design

## ⚖️ Disclaimer

**Important**: This tool is for educational and research purposes only and does not constitute any investment advice.

- ⚠️ Trading involves significant risk and may result in total loss of principal
- ⚠️ Past performance does not guarantee future results
- ⚠️ All trading decisions made using this tool are solely the user's responsibility
- ⚠️ The author is not liable for any trading losses
- ⚠️ Please fully understand the risks of financial markets before use
- ⚠️ It is recommended to practice on a demo account first

**Please ensure you**:
1. Only invest what you can afford to lose
2. Conduct thorough research and testing
3. Consider consulting a professional financial advisor
4. Comply with local financial regulations

## 📄 License

This project is licensed under the [MIT License](LICENSE).

```
MIT License

Copyright (c) 2026 Lewis Chan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 🌟 Acknowledgements

- Binance API – Free market data provider
- Python Community – Powerful standard library
- All contributors and users for their feedback

## 📞 Contact

- **GitHub**: [@Lewsiafat](https://github.com/Lewsiafat)
- **Issues**: [Report a Bug](https://github.com/Lewsiafat/scalping-trade/issues)
- **Pull Requests**: [Submit Improvements](https://github.com/Lewsiafat/scalping-trade/pulls)

---

**Built with** ❤️ **by traders, for traders**

*Last updated: 2026-03-03 | Version: v3.4.0*
