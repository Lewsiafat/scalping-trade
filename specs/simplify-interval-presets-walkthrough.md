# 簡化 Interval 與 Presets 機制 — Walkthrough
## 任務摘要
- **分支**: `refactor/simplify-interval-presets`
- **日期**: 2026-03-12
- **Summary**: 移除不實用的 Preset 系統和 Interval 選擇機制，固定 5m 為主交易框架、15m 為 MTF 確認。手動剝頭皮在 1m 根本來不及下單，保留多套參數只增加複雜度且讓評分閾值與指標參數脫節。

## 變更項目
- `app_v3.py` — 主程式：
  - 移除 `PresetManager` class（~60 行）及 `/api/presets` endpoint
  - 新增 `FIXED_PARAMS` 常數（5m, RSI14, EMA9/21, MACD12/26/9）
  - `handle_api_analyze()` 簡化為只需 symbol 參數
  - `analyze_entry_signal()` 固定 interval='5m'、swing n=3
  - `multi_timeframe_analysis()` 固定 15m 確認（移除 timeframe_map）
  - 前端移除：Interval 下拉選單、Quick Presets 面板、RSI/EMA/MACD 參數調整、`loadPreset()` 函數
  - 快照保存改用固定參數、overlay 序列改用 FIXED_PARAMS
- `test_signal_compare.py` — 改用 `FIXED_PARAMS` import
- `specs/simplify-interval-presets.md` — 任務規格

## 技術細節

### 為什麼移除
1. **1m 手動不可行**：信號出現到下單已過 2-3 根 K 線
2. **Presets 造成參數脫節**：preset 改了指標計算參數，但評分閾值（RSI 30-40、MACD ATR×0.1 等）全部寫死，兩者不配合
3. **5m+15m 是手動剝頭皮最佳組合**：業界共識，有足夠時間判斷和下單

### 淨效果
- 刪除 ~200 行程式碼
- API 更簡潔：`/api/analyze?symbol=BTCUSDT` 即可
- UI 側邊欄大幅簡化
- 所有評分閾值都針對 5m+15m 調校，不再有參數不匹配問題
