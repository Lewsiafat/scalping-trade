# 透過回測優化交易績效 — Walkthrough

- **分支:** `feat/improve-profit-by-backtest`
- **日期:** 2026-03-18

## 變更摘要
為回測系統新增兩大功能：(1) 參數優化引擎（ParameterOptimizer），以網格搜尋自動找出最佳指標/過濾參數組合並以 PnL/DD 比值排序；(2) 改善入場/出場邏輯，包含 Trailing Stop（移動止損）、部分止盈（TP1 平 50%）、連虧保護、入場模式/Confirmed/Caution RR 開關。版本升級至 2.0.0。

## 修改的檔案
- **app_backtest.py** — 核心變更：
  - `BacktestEngine.analyze_bar()` 支援自訂 `params` 覆蓋 FIXED_PARAMS
  - `BacktestEngine.run_backtest()` 新增 trailing_stop / partial_tp / lose_streak / entry_mode / require_confirmed / allow_caution_rr 參數
  - 持倉中新增 Trailing Stop 及部分止盈邏輯（TP1 觸發後 SL 移至入場價，同 bar 不檢查新 SL）
  - 連虧保護機制（連 N 虧後暫停 M 根 K 線）
  - 入場模式控制（strong_only / include_normal）及 confirmed / caution_rr 開關
  - 新增 `ParameterOptimizer` 類別 — 網格搜尋 + _prefetched 數據重用避免重複 API 拉取
  - 新增 `/api/optimize` 端點
  - 績效統計按出場類型分類（sl/tp1/tp2/trailing_be/partial_sl/partial_tp1/partial_tp2）
  - 前端：新增 Phase 2 控制項（入場模式、Confirmed、Caution RR、Trailing Stop、部分止盈、連虧暫停）
  - 前端：參數優化 UI（按鈕、排行表、套用功能）
  - 前端：出場類型顯示對應標籤
- **run_backtest.py** — 新增獨立 CLI 回測執行器（不依賴 Web 伺服器的簡易版）
- **specs/improve-profit-by-backtest.md** — 任務規格文件

## 技術細節
- **參數優化策略**：預拉取數據一次（`_prefetched`），所有參數組合共用相同的 K 線數據，大幅減少 API 呼叫次數。排序指標為 PnL%/MaxDrawdown 比值，過濾交易次數 ≥ 5 筆。
- **Trailing Stop 邊界處理**：TP1 觸發的同一 bar 設定 `trailing_just_activated` 標記，跳過該 bar 的 SL 檢查，避免同 bar 立即被新 SL（入場價）出場。
- **部分止盈計算**：TP1 時記錄 50% 倉位的 partial_pnl，最終出場時剩餘 50% 倉位的 pnl 加上 partial_pnl 得到總 PnL。
- **入場品質控制**：新增三個開關維度（entry_mode × require_confirmed × allow_caution_rr），參數優化器可遍歷這些組合找出最佳配置。
- **時段過濾**：列入規格但標記為「留待下次」，未在此版本實作。
