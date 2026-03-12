# 簡化 Interval 與 Presets 機制

- **分支:** `refactor/simplify-interval-presets`
- **日期:** 2026-03-12

## 描述
移除不實用的 Preset 系統和 Interval 選擇，固定 5m 為主交易框架、15m 為 MTF 確認。將所有寫死的評分閾值與指標參數統一對齊 5m+15m 組合。

## 任務清單

### 後端（app_v3.py）
- [x] 移除 `PresetManager` class 和 `/api/presets` endpoint，改為 `FIXED_PARAMS`
- [x] `analyze_entry_signal()` 固定 interval=5m，移除 params 中的 interval 依賴
- [x] Swing window 固定 n=3（5m 適用）
- [x] `/api/analyze` endpoint 移除 interval 及指標參數，固定 5m + 標準參數
- [x] MTF 確認固定使用 15m（移除 timeframe_map 動態對應）

### 前端（HTML_PAGE）
- [x] 移除 Quick Presets 面板（三個按鈕）+ `loadPreset()` 函數
- [x] 移除 Interval 下拉選單
- [x] 移除指標參數調整控制項（RSI/EMA/MACD 設定）
- [x] 簡化 `analyze()` URL 只傳 symbol
- [x] 快照保存改用固定參數
