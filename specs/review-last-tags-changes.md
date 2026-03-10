# 回顧 v4.0.0 信號觸發問題修復

- **分支:** `refactor/review-last-tags-changes`
- **日期:** 2026-03-10

## 描述

v4.0.0 重構後發現買入/賣出指示幾乎無法觸發。根因分析找到兩個問題：
1. **pre-alert 強制前置**：三維評分達標但無 pre-alert 時，信號直接降為觀望（L1925-1929），導致三維評分形同虛設。
2. **MACD 絕對值閾值錯誤**：histogram 判斷用固定範圍 `0 < x < 0.5`、diff 用 `0 < x < 0.3`，對 BTC/ETH 等高價資產完全失效，momentum score 幾乎永遠拿不到 MACD 的 30 分。

修復方案 A：
- 三維達標即可發出 buy/sell 指示，pre-alert 只影響信號是否顯示「confirmed」badge
- MACD 改用相對判斷（histogram 符號翻轉 vs 前一根、diff 符號判斷）

## 任務清單

- [x] 修改 `analyze_entry_signal()`：三維達標但無 pre-alert 時，保留 overall/action 為 buy/sell，signal_stage = None（不顯示 confirmed badge）
- [x] 修改 `calc_momentum_score()`：MACD histogram 從絕對值閾值改為「符號與上一根比較」判斷柱翻轉
- [x] 修改 `calc_momentum_score()`：MACD diff 從 `0 < diff < 0.3` 改為 ATR 正規化閾值
- [x] 確認 sl_tp 在無 pre-alert 情境下仍能嘗試計算（使用現有結構錨點或 ATR fallback）
- [ ] 手動測試：BTC、ETH 各時間框架確認信號能正常觸發
- [x] 確認 pre-alert + confirmed 雙階段機制仍正常運作（不被影響）
