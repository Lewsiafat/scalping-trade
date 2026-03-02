# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.2.0-beta] - 2026-03-02

### Added
- 即時 K 線圖表：整合 TradingView Lightweight Charts，顯示即時 K 線與技術指標覆蓋
- EMA/布林通道 overlay 時間序列：在圖表上疊加 EMA 線與布林通道帶
- 智能重試機制：API 請求支援指數退避重試（`fetch_with_retry`），依錯誤類型分類處理
- 中文錯誤訊息：結構化錯誤分類與友善中文提示（`classify_error`）
- 進度指示器：分析過程中顯示載入進度
- Toast 通知系統：取代原生 `alert()` 彈窗，提供更好的使用者體驗

### Changed
- 前端 UI 大幅改進，新增圖表區域與 Toast 通知元件
- 後端新增 `fetch_with_retry()` 和 `classify_error()` 輔助函數
- API 請求錯誤處理更加完善（HTTP 429 限速、5xx 伺服器錯誤自動重試）

## [3.1.0] - 2026-03-01

### Added
- 快照增強：刪除功能、CSV 匯出（UTF-8 BOM）、多條件搜尋篩選
- 智能警報系統：價格/品質/信號三種警報類型，支援啟用/停用/刪除
- 參數快速預設：超短線/短線/穩健三種策略一鍵切換
- 新增 API 端點：`/api/snapshots/export`, `/api/snapshots/search`, `/api/alerts`, `/api/alert/add`, `/api/alert/toggle`, `/api/presets`

### Fixed
- JavaScript 模板字符串語法錯誤
- 函數名稱不匹配問題

## [3.0.0] - 2026-03-01

### Added
- 3大技術指標：布林通道、隨機指標、斐波那契回撤
- 策略快照管理：保存/查看歷史快照
- 自訂交易對管理：新增/刪除個人化商品清單
- 新增 API 端點：`/api/snapshots`, `/api/symbols`, `/api/snapshot/save`, `/api/symbol/add`

### Changed
- 精簡頁首高度，節省 50% 顯示空間
- 優化信號評分邏輯，納入新指標

## [2.0.0] - 2026-02-28

### Added
- 成交量分析（CVD、成交量比率）
- 多時間框架確認
- 動態止損止盈計算（ATR）
- 信號品質評分系統（0-5 星）
- 瀏覽器通知功能

### Changed
- UI 佈局優化（建議操作置頂）

## [1.0.0] - 2026-02-26

### Added
- 初始版本
- 基礎技術指標（RSI、EMA、MACD）
- 即時數據分析
- 響應式網頁設計
