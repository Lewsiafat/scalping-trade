# 高等級建議獲利驗證機制 — Walkthrough

- **分支:** `feat/verify-signal-profit`
- **日期:** 2026-07-12

## 變更摘要

建立逐訊號獲利驗證機制（event study），回答「高等級建議給的入場數據是否真的賺得到錢」。驗證結果證實 SMC 結構訊號在 5m–1h K 線層面**沒有可統計確立的 edge**；過程中發現並修復兩個使低價幣訊號全滅、標籤退化的 P0 bug。完整分析與外部策略研究見 `specs/verify-signal-profit-report.md`。

## 修改的檔案

- **`verify_signal_profit.py`（新增）** — 逐訊號事件研究工具。重播歷史 K 線，記錄每次訊號觸發當下的完整等級剖面（overall / signal_stage / rr_grade / 3D 分數 / composite / label），用系統給的入場價 + SL/TP 獨立模擬結局（含手續費、滑價、MFE/MAE），按等級 A–E 分層統計勝率 / PF / 期望值。分頁抓取突破單次 1000 根上限。
- **`test_precision_label.py`（新增）** — P0 bug 的回歸測試（5 項，先紅後綠）：低價幣 ATR/SL 精度、label 時近性過濾。
- **`app_v3.py`（修改）** — P0-1 修復：
  - 全部價格尺度捨入 `round(x, 2)` → `round(x, 8)`（ATR/EMA/MACD/BB/SL/TP/sweep depth）。
  - `determine_signal_label` 新增 `current_index` 參數，只採計近 10 根 bar 內的 sweep。
- **`specs/verify-signal-profit-report.md`（新增）** — 完整驗證報告（八節）：機制設計、基準結果、P0 修復、低摩擦假設空間研究、擴大樣本推翻、外部 deep-research 綜合、路線建議。
- **`backtest_results/research_20260711/`（gitignored）** — 研究數據與 deep-research 原始輸出。

## 技術細節

### P0 bug 根因（systematic-debugging，真實數據證實）

兩個根因、三個症狀：
1. **`calculate_atr` 的 `round(atr, 2)`** — DOGE 原始 ATR ≈ 0.00013、XRP ≈ 0.0018，捨入後 100% 歸零，觸發全管線 `atr <= 0` 防衛。一個捨入同時造成 DOGE 零訊號與 XRP 的 SL 尺度異常（ATR ≥ 0.005 時捨成 0.01，放大最多 5.8 倍）。
2. **`determine_signal_label` 無時近性過濾** — `detect_liquidity_sweep` 掃全 150 根窗口，實測 BTC 651 個窗口 100% sweeps 非空，`if sweeps:` 永遠短路，導致 1691 筆事件 100% 同一標籤。

驗收（5m × 5000 根重跑）：DOGE 0 → 319 筆、XRP 9 → 313 筆且 SL 距離中位 1.105% → 0.254%、label 1 類 → 6 類全出現。

### 核心發現

- 5m 零摩擦期望值 ≈ 0（訊號無 edge），taker 費率下嚴重虧損。
- 30m/1h A 級的正期望點估計（+0.345R, n=25）在樣本擴大至 n=130–155 後回歸零/負，CI 含零——小樣本假象。
- 外部 deep-research（24 來源 / 22 條三票查證）：真正短線 edge 在秒級 L2 orderbook；造市家族依賴散戶拿不到的 maker 返佣；K 線技術規則無無條件 edge。
- 現架構唯一有學術支撐的方向：日頻 order flow 因子（非 scalping，需重新設計訊號）。

### 未變更但已記錄的事項

- `calc_structure_score` 的 sweep 計分（`app_v3.py:1496`）有同樣無時近性問題，屬計分語義變更，本次未動。
- 舊版 `calculate_stop_loss_take_profit`（`app_v3.py:941`）為死代碼，未觸碰。
- `app_v3.py` 的 `VERSION` 常數仍為 4.2.2（v4.3.0 發布時未同步更新，屬既有狀況）。
