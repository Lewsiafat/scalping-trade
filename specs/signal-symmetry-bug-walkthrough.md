# 修正信號引擎多空非對稱 Bug

## 任務摘要
- **分支**: `fix/signal-symmetry-bug`
- **日期**: 2026-03-17
- **Summary**: 修正信號引擎中 3 處多空條件不對稱的邏輯缺陷，解決系統幾乎不產生賣出信號的問題。

## 變更項目
- `app_v3.py` — 修正 3 處非對稱邏輯 + 賣出分支 composite 翻轉計算 + UI 回傳值修正
- `specs/signal-symmetry-bug.md` — 任務規格文件

## 技術細節

### Bug 1: MTF 一致性加/扣分不對稱 (L1398-1401)
- **問題:** `calc_trend_score()` 中 MTF 與 BOS 方向一致時 +25，不一致時僅 -10
- **修正:** 不一致改為 -25，使加/扣分對稱

### Bug 2: RSI 背離門檻不對稱 (L1573-1576)
- **問題:** `calc_momentum_score()` 中看多背離要求 RSI > 35，看空背離要求 RSI < 65（不對稱於中點 50）
- **修正:** 改為 RSI > 30 / RSI < 70（對稱於中點 50，距離各 20）

### Bug 3: 賣出分支 composite/min_floor 計算矛盾 (L2035-2047)
- **問題:** 信號判定使用 `trend_score` 原始值計算 `composite` 和 `min_floor`。做空時 trend_score 越低代表越看空，但同時拉低 composite 和 min_floor，導致越看空越不可能觸發賣出信號。
- **修正:** 在賣出分支中使用 `bearish_strength = 100 - trend_score` 計算 `sell_composite` 和 `sell_min_floor`，將方向性分數轉為強度分數。
- **UI 同步:** API 回傳的 `composite_score`、`min_floor`、`composite_formula` 在賣出時使用翻轉後的值，確保前端顯示與實際判定一致。

### 驗證結果
修正後批量測試 30 個交易對，出現 5 個賣出信號（ETHUSDT strong_sell, SOLUSDT/LINKUSDT/PEPEUSDT/ATOMUSDT sell），修正前為 0 個。買入信號正常不受影響。
