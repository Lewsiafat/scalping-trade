# 📈 Scalping Trade Analyzer Pro - 專案指南 (GEMINI.md)

歡迎使用 **Scalping Trade Analyzer Pro** 專案。本文件為 Gemini CLI 提供專案背景、開發慣例及操作指南，請在後續互動中遵循此脈絡。

## 🎯 專案概述

本專案是一個專業級的實時剝頭皮 (Scalping) 交易信號分析系統，專為加密貨幣市場設計。它具備多項技術指標分析、即時 K 線圖表、成交量分析、多時間框架確認及動態止損止盈計算等核心功能。

*   **核心理念**: 僅使用 Python 標準庫實現，無須安裝第三方依賴，確保輕量、安全且易於部署。
*   **主要技術棧**: 
    *   **後端**: Python 3.11+ (Standard Library: `http.server`, `socketserver`, `urllib`)
    *   **前端**: 原生 HTML5 / CSS3 / Vanilla JavaScript
    *   **數據源**: Binance Public API (免 API Key)
    *   **圖表**: TradingView Lightweight Charts (CDN 載入)

## 🏗️ 系統架構

專案採用 **單文件單體架構 (Single-file Monolith)**：

*   **`app_v2.py`**: 包含後端 HTTP 服務器、API 路由、交易分析邏輯，以及嵌入式的前端 HTML/CSS/JS 代碼。
*   **資料持久化**: 
    *   `snapshots.json`: 存儲交易策略快照。
    *   `alerts.json`: 存儲價格、品質及信號警報配置。
    *   `custom_symbols.json`: 存儲使用者自訂的交易對。

## 🚀 運行與測試

### 運行指令
```bash
# 直接執行主程式，預設監聽 80 端口 (可能需要管理員權限)
python3 app_v2.py
```
*   **存取路徑**: `http://localhost:80`

### 測試與驗證
目前專案尚未建立獨立的測試框架，主要通過手動驗證。
*   **API 測試**: 可使用 `curl` 測試分析端點：
    ```bash
    curl "http://localhost:80/api/analyze?symbol=BTCUSDT&interval=5m"
    ```

## 🛠️ 開發慣例與規範

1.  **語言規範**:
    *   UI 界面、註釋及文件統一使用 **正體繁體中文**。
    *   代碼變量、函數名使用英文，遵循 PEP 8 規範。
2.  **架構設計**:
    *   **`ScalpingAnalyzerPro`**: 靜態方法類，負責所有技術指標 (RSI, EMA, MACD, ATR, Bollinger, Stoch, Fib) 的純數學計算。
    *   **`ScalpingHandler`**: 繼承自 `SimpleHTTPRequestHandler`，處理 API 請求與頁面渲染。
    *   **錯誤處理**: 使用 `fetch_with_retry` 進行 API 請求，具備指數退避重試機制；使用 `classify_error` 提供結構化的中文錯誤回饋。
3.  **依賴控制**:
    *   **嚴禁引入第三方庫** (如 `requests`, `pandas`, `flask` 等)。所有功能必須使用 Python 標準庫實現。
4.  **前端更新**:
    *   前端代碼以字符串形式嵌入在 `app_v2.py` 中。在修改前端邏輯時，需確保 JavaScript 模板字符串的轉義正確。

## 📂 關鍵檔案說明

*   `app_v2.py`: 核心主程式（唯一邏輯文件）。
*   `docs/SPEC.md`: 技術規格書，詳細記錄了各項指標的計算公式與評分邏輯。
*   `docs/improv_plan.md`: 專案改進與優化路徑圖。
*   `README.md`: 使用者手冊及功能清單。
*   `CLAUDE.md`: 針對 AI 助手 (Claude/Gemini) 的開發導引。

## ⚠️ 安全與風險提示

*   本系統僅供教育與研究用途，不構成投資建議。
*   API 請求目前禁用 SSL 驗證 (`ssl.CERT_NONE`) 以簡化環境需求，請知悉相關風險。
*   伺服器預設監聽所有接口 (`0.0.0.0`)，在公網環境部署時需注意防火牆配置。
