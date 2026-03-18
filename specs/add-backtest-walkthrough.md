# 增加回測功能 Walkthrough
## 任務摘要
- **分支**: `feat/add-backtest`
- **日期**: 2026-03-18
- **Summary**: 新增獨立回測程式 `app_backtest.py`，基於 ScalpingAnalyzerPro 信號引擎對歷史 K 線數據進行多空雙向回測。修正原實作的兩大核心問題：MTF 歷史數據為 neutral mock 導致 quality_score 偏低、前端缺少時間週期選擇器。

## 變更項目
- **`app_backtest.py`**（新增）— 獨立回測程式，含 HTTP server（port 8081）、`BacktestEngine`、`/api/backtest` 端點、嵌入式前端（TradingView Lightweight Charts + Equity Curve + 交易明細表）
- **`specs/add-backtest.md`**（新增）— 任務規格文件

## 技術細節

### MTF 歷史數據修正
原始實作的 `_mock_mtf_analysis()` 固定回傳 `trend: neutral`，導致 `calc_trend_score()` 無法取得 MTF 加分（±25 分），使 quality_score 最高只有 3.6，無法達到原始預設門檻 4.0，造成零交易。

**解法**：在 `run_backtest()` 啟動時預拉取 MTF 歷史 K 線，並在逐 bar 分析時以二分搜尋取得對應時間點的 MTF 切片，傳入 `analyze_bar()` 計算真實 EMA20/EMA50 趨勢。

```python
# MTF 時間框架映射
MTF_INTERVAL_MAP = {
    '1m': '5m', '3m': '15m', '5m': '15m',
    '15m': '1h', '30m': '1h', '1h': '4h', '4h': '1d',
}
```

`analyze_bar(data_window, symbol, mtf_slice, mtf_interval)` 新增 `mtf_slice` 參數：MTF 切片 ≥ 20 根時使用真實趨勢，不足時自動降級為 neutral mock。

### Interval 選擇器
前端新增 `<select id="interval">`（1m / 3m / 5m / 15m / 30m / 1h / 4h，預設 5m），`runBacktest()` 將 `interval` 加入 URLSearchParams 傳至後端。

### 品質門檻預設值調整
預設 `min_quality` 由 4.0 降為 3.0，提供開箱即用的回測體驗。使用者可透過前端滑桿（範圍 1–5）自行調高。

### 回測核心邏輯（已完整實作）
- **滑動窗口**：從第 150 根開始，每次分析 150 根 K 線窗口
- **入場條件**：`signal_stage == confirmed` + `overall in (strong_buy, strong_sell)` + `quality >= min_quality` + `rr_grade in (good, acceptable)`
- **出場條件**：逐 bar 檢查 SL/TP，同時觸及時以開盤價方向判斷優先級
- **CD 機制**：持倉中不開新單；`cooldown_bars > 0` 時出場後額外等待 N 根
- **滑價**：做多 `×(1 + slippage/100)`，做空 `×(1 - slippage/100)`
- **強制平倉**：回測結束時若仍持倉，以最後一根收盤價平倉（`exit_type: force_close`）
