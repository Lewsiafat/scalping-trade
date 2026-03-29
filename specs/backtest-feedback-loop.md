# Backtest Feedback Loop — 回測反饋循環系統

- **分支:** `feat/backtest-feedback-loop`
- **日期:** 2026-03-29

## 描述

為 Scalping Trade Analyzer Pro 新增完整的回測反饋循環系統。透過爬取至少 1 個月的歷史 5m K 線，模擬策略觸發並追蹤每筆交易實際損益，最終利用參數調整表 + LLM 輔助，持續優化交易策略參數。

---

## 架構概覽

```
┌─────────────────────────────────────────────┐
│  1. data_fetcher.py（先導程式）              │
│     爬取 ≥1 個月歷史 K 線 → history/        │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  2. backtest_params.json（獨立變數表）       │
│     可調整的分析參數（門檻、評分權重等）     │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  3. backtest_engine.py（回測核心）           │
│     逐 bar 模擬 → 觸發訊號 → 追蹤結果       │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  4. backtest_results.json（交易記錄）        │
│     進場價、SL、TP、結果、時間、統計摘要     │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  5. LLM 調整建議（可選）                    │
│     分析結果 → 建議調整方向 → 重跑回測      │
└─────────────────────────────────────────────┘
```

---

## 任務清單

### Phase 1：歷史資料爬取（先導程式）
- [ ] 建立獨立腳本 `data_fetcher.py`
- [ ] 支援指定 symbol + 起始日期（預設抓最近 30 天）
- [ ] Binance API 分批請求（每次 1000 根，自動分頁到指定天數）
- [ ] 輸出存至 `history/{symbol}_5m_{date}.json`
- [ ] 顯示進度（幾根 / 總共幾根，預計時間）
- [ ] 加入錯誤重試與 rate limit 處理

### Phase 2：獨立參數變數表
- [ ] 建立 `backtest_params.json`（獨立於主程式的可調整參數表）
- [ ] 包含三維評分門檻：`min_trend_score`, `min_structure_score`, `min_momentum_score`
- [ ] 包含評分權重：`weight_trend`, `weight_structure`, `weight_momentum`
- [ ] 包含 SMC 參數：`swing_n_small`, `swing_n_large`, `atr_clamp_min/max`
- [ ] 包含訊號門檻：`min_rr_ratio`, `pre_alert_atr_mult`
- [ ] 包含回測參數：`max_hold_bars`（最長持倉 bar 數，預設 12）、`commission_rate`
- [ ] 建立 `backtest_params_default.json` 備份原始預設值

### Phase 3：回測引擎
- [ ] 建立 `backtest_engine.py`（獨立腳本，可直接執行）
- [ ] 讀取 `history/` 資料 + `backtest_params.json`
- [ ] 逐 bar 滾動窗口模擬（每根 K 線調用 `ScalpingAnalyzerPro` 方法）
- [ ] 觸發條件：confirmed signal（三維分數 + R:R 達標）
- [ ] 每筆觸發記錄：
  - `symbol`, `signal_type`（BUY/SELL）
  - `entry_price`（進場價）
  - `sl_price`（停損價）
  - `tp_price`（獲利目標）
  - `trigger_time`（觸發時間 ISO 格式）
  - `trigger_bar_index`（K 線索引）
  - `trend_score`, `structure_score`, `momentum_score`
- [ ] 追蹤持倉結果（在後續 K 線中檢查是否觸 SL / TP / max_hold_bars 到期）
- [ ] 記錄每筆交易最終結果：
  - `result`（`tp_hit` / `sl_hit` / `expired`）
  - `exit_price`（出場價）
  - `exit_time`（出場時間）
  - `pnl_r`（以 R 為單位的損益：TP = +RR, SL = -1.0, expired = 實際 R）
  - `hold_bars`（持倉 bar 數）

### Phase 4：統計摘要與結果輸出
- [ ] 輸出 `backtest_results.json` 包含：
  - 所有交易詳情陣列 `trades[]`
  - 統計摘要 `summary`：
    - `total_trades`, `win_trades`, `loss_trades`, `expired_trades`
    - `win_rate`（勝率 %）
    - `avg_rr`（平均 R:R）
    - `total_pnl_r`（總 R 損益）
    - `max_consecutive_loss`（最大連虧次數）
    - `profit_factor`（獲利因子）
    - `params_used`（本次使用的參數快照）
- [ ] CLI 輸出美化（表格形式顯示摘要）
- [ ] 支援輸出 CSV（`--export csv`）

### Phase 5：反饋循環
- [ ] 支援 `--run-id` 參數，每次回測結果存入 `backtest_history/run_{id}.json`
- [ ] 建立 `compare_runs.py`：比較多次回測結果的統計差異
- [ ] 自動建議：若勝率 < 50% 或 profit_factor < 1.0，輸出參數調整建議

### Phase 6：LLM 調整輔助（可選）
- [ ] 建立 `llm_advisor.py`
- [ ] 讀取最近一次回測結果 + 目前參數表
- [ ] 組成 prompt：「以下是交易統計與參數，請分析失敗原因並建議調整方向」
- [ ] 支援 Gemini API（與 `AICodeReviewCLI` 同款）或 Claude API
- [ ] 輸出 LLM 建議至 `backtest_advice.md`
- [ ] 加入 `--apply-advice` flag，自動將 LLM 建議的參數寫回 `backtest_params.json`

---

## 檔案結構

```
scalping-trade/
├── app_v3.py                    # 主程式（不修改）
├── backtest_params.json         # 可調整參數表
├── backtest_params_default.json # 預設參數備份
├── data_fetcher.py              # 歷史資料爬取先導程式
├── backtest_engine.py           # 回測引擎主程式
├── compare_runs.py              # 多次結果比較
├── llm_advisor.py               # LLM 調整建議（Phase 6）
├── history/
│   └── {SYMBOL}_5m_{date}.json # 歷史 K 線資料
└── backtest_history/
    ├── latest.json              # 最新回測結果（軟連結）
    └── run_{id}.json            # 每次回測記錄
```

---

## 技術備註

- 滾動窗口大小：150 根（與主程式 fetch limit 一致）
- 5m × 1 個月 = 約 8640 根 K 線（30天 × 24h × 12根/h）
- Binance API 每次最多 1000 根，需分 9 批次請求
- 回測引擎直接 import `app_v3.py` 中的 `ScalpingAnalyzerPro` 靜態方法
- 主程式 `app_v3.py` 零修改，確保向下相容
- LLM Phase 為可選功能，可獨立啟用
