# 信號機制根本性改善 — Walkthrough
## 任務摘要
- **分支**: `refactor/signal-mechanism-improvement`
- **日期**: 2026-03-12
- **Summary**: 從機制層面解決信號難以觸發的五大根本原因。方案 A 對 app_v3.py 進行四項核心改動（Partial Sweep、趨勢延續、R:R 分級、加權合分）並新增前端評分明細面板；方案 B 產出獨立的條件累積引擎及 A/B 對比測試腳本。

## 變更項目
- `app_v3.py` — 主程式，改動涵蓋 6 個方面：
  - `detect_liquidity_sweep()`: 三級 Sweep 分類（full +25 / partial +15 / near +8），保留最近 5 個
  - `calc_structure_score()`: 根據 sweep strength 分級給分，回傳 dict 含 details
  - `calc_momentum_score()`: 新增 trend_direction 參數，RSI/MACD/Stoch 反轉 vs 延續取較高分，回傳 dict 含 details
  - `calc_trend_score()`: 回傳 dict 含 details
  - `calc_dynamic_sl_tp()`: R:R 用 TP1 計算，四級分類（good/acceptable/caution/reject），0.7 為底線
  - `analyze_entry_signal()`: 加權合分（T×0.35 + S×0.40 + M×0.25）+ min_floor 取代硬門檻，trend_direction 推導，score_breakdown 組裝
  - 前端 CSS: 新增 `.score-breakdown-details` 系列樣式
  - 前端 JS: 新增 `renderBreakdownSection()` 函數，`<details>` 展開明細面板
  - i18n: EN/ZH_TW 新增 `score_breakdown_title` 鍵
- `signal_engine_b.py` — 方案 B 獨立引擎，10 個布林條件累積判定信號
- `test_signal_compare.py` — A/B 對比測試腳本，支援 `--loop` 持續刷新
- `specs/signal-mechanism-improvement.md` — 任務規格文件（所有項目已完成）

## 技術細節

### 根本問題
v4.0.0 信號難以觸發的五大原因：
1. Structure Score ≥ 60 幾乎依賴 Sweep（低頻事件）
2. Momentum Score 常態只有 20-30 分（只獎勵反轉）
3. R:R < 1.0 一刀切拒絕信號
4. 三維硬門檻 AND 邏輯聯合機率太低
5. Momentum 缺少趨勢延續給分

### 方案 A 核心設計
- **Partial Sweep**: 降低 Sweep 檢測門檻但保留分級（depth ≥ ATR×0.3 即可 partial，wick 觸碰 ± ATR×0.2 為 near）
- **趨勢延續**: 同一指標反轉 vs 延續互斥取較高分，避免重複計分。需要 trend_direction 從 BOS+EMA 推導
- **R:R 分級**: 0.7-1.0 為 caution（降級但保留 SL/TP），< 0.7 才完全拒絕。改用 TP1 算主要 R:R
- **加權合分**: composite = T×0.35 + S×0.40 + M×0.25，min_floor 防止單維度為零。Structure 權重最高（SMC 核心）

### 方案 B 設計
10 個布林條件（BOS 方向、MTF、OB、FVG、Sweep、MACD、RSI、Stoch、成交量、R:R），≥5 觸發、≥7 強信號。方向由多數決。

### A/B 測試結果
| 幣種 | 方案 A | 方案 B |
|------|--------|--------|
| BTCUSDT 5m | 觀望 (composite 47.2, min_floor 18) | 買入 (6/10) |
| ETHUSDT 15m | 觀望 (composite 40.0, min_floor 25) | 強賣 (7/10) |
| SOLUSDT 5m | 觀望 (composite 58.5, min_floor 15) | 買入 (5/10) |

方案 A 較保守（min_floor 保護），方案 B 較積極，適合作為輔助參考。
