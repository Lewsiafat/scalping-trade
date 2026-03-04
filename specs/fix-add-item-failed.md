# 修復新增商品失敗的問題 (Fix Add Item Failed)

- **分支:** `fix/add-item-failed`
- **日期:** 2026-03-04

## 描述
使用者常常不知道正確的 Binance 交易對代碼（例如只輸入 `BTC` 而不是 `BTCUSDT`），導致新增失敗並出現隱含的 API 錯誤。此任務將改進 `SymbolManager.add_symbol` 的邏輯，支援自動補齊 `USDT` 後綴，並透過 Binance API 進行即時驗證，確保代碼有效且存在。同時會在前端加入更好的輸入提示與錯誤訊息。

## 任務清單
- [x] 分析目前新增商品的邏輯與 UI
- [x] 修改 `app_v2.py` 中的 `SymbolManager.add_symbol` 加入 Binance API 驗證與自動補齊 `USDT` 功能
- [x] 更新前端 HTML/JS，在商品代碼輸入框加入 Placeholder ("例如：BTCUSDT, ETHUSDT")，並優化錯誤提示
- [x] 進行本地測試確保能成功新增支援的交易對，並攔截無效的交易對輸入
- [x] 加入 Binance API exchangeInfo 建立的 `supported_symbols.json`，並在後端新增 `/api/supported_symbols` 選單供前端存取
- [x] 在前端加入 `datalist` Autocomplete，協助使用者搜尋交易對代碼
