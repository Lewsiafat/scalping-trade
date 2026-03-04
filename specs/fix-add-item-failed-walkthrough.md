# 修復新增商品失敗的問題 (Fix Add Item Failed)
## 任務摘要
- **分支**: `fix/add-item-failed`
- **日期**: 2026-03-04
- **Summary**: 改善新增自選商品的防呆機制，新增即時 Binance 交易代碼自動完成 (Autocomplete)，並改寫核心 API 向合約/現貨執行雙重驗證。

## 變更項目
- `app_v2.py`: 
  - 後端增加 `/api/supported_symbols` 提供現貨與合約代碼清單
  - 修改 `SymbolManager.add_symbol` 增加自動補齊後綴功能，並向 Binance 現貨/合約 API 分別進行雙重驗證避免無效代碼
  - 改寫 `fetch_with_retry`，使其在遭遇 400 無效商品錯誤且呼叫 K 線時，能夠自動降級切換到合約端點取資料
  - 前端增加 HTML5 `<datalist>` AutoComplete 元件
- `update_exchange_info.py`: 新增定期擷取 Binance 現貨與合約 API 的 Python 輔助工作腳本
- `supported_symbols.json`: 由工作腳本產出的 600+ Binance USDT 合約與現貨交易對列表
- `custom_symbols.json`: (系統更新儲存結構狀態) 可正確儲存新的代碼，並新增如合約專用代碼 (e.g. `XAUUSDT`, `1000PEPEUSDT`)

## 技術細節
- Binance 在呼叫價格時，分為 `https://api.binance.com` (現貨) 以及 `https://fapi.binance.com` (合約)。為了提供全面性的分析器支援，系統的核心元件 `fetch_with_retry` 現在擁有了錯誤處理機制的 fallback 邏輯，當向現貨端點發生 `HTTPError 400`，即動態調配重構成 `fapi` 重新呼叫取得合約資料。
