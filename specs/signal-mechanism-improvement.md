# 信號機制根本性改善

- **分支:** `refactor/signal-mechanism-improvement`
- **日期:** 2026-03-12

## 描述
從機制層面改善信號難以觸發的問題。方案 A 修改 app_v3.py（四項核心改動 + 前端明細面板），方案 B 產出獨立檔案供測試比較。

## 任務清單

### 方案 A — 核心改動（app_v3.py）
- [x] 改動1: Partial Sweep 三級檢測 — `detect_liquidity_sweep()` 新增 full/partial/near 分類 + `calc_structure_score()` 分級給分
- [x] 改動2: Momentum 趨勢延續 — `calc_momentum_score()` 新增 trend_direction 參數 + 延續評分邏輯
- [x] 改動3: R:R 分級處理 — `calc_dynamic_sl_tp()` 四級 rr_grade + 用 TP1 計算主要 R:R
- [x] 改動4: 加權合分 — `analyze_entry_signal()` 信號判定改為 composite 加權 + min_floor
- [x] 改動5: 評分明細 — 三個 calc_*_score() 回傳 dict 含 details + API 新增 score_breakdown
- [x] 改動6: 前端明細面板 — `<details>` 展開評分明細 + i18n 雙語

### 方案 B — 獨立測試檔案
- [x] `signal_engine_b.py` — 條件累積引擎（10 個布林條件，≥5 觸發信號）
- [x] `test_signal_compare.py` — A/B 對比測試腳本（支援 --loop）
