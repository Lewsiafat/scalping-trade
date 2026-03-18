# 增加回測功能

- **分支:** `feat/add-backtest`
- **日期:** 2026-03-18

## 描述
新增獨立回測程式 `app_backtest.py`，透過呼叫 `app_v3.py` 的 `/api/analyze` API 端點，對歷史 K 線數據進行信號回測。支援多空雙向回測，含 CD 機制防止連續開單，並提供完整績效統計與視覺化圖表。

## 架構設計

### 獨立程式 `app_backtest.py`
- 自帶 HTTP server + 嵌入式前端（與 `app_v3.py` 相同的單檔架構）
- 預設 port `8081`，支援 `--port` 參數自訂
- 透過 HTTP 呼叫 `app_v3.py` 的 `/api/analyze` 端點取得分析結果
- 支援 `--api-url` 參數指定 `app_v3.py` 的位址（預設 `http://localhost:80`）

### 回測流程
1. 從 Binance API 拉取歷史 K 線數據（500 或 1000 根，可選）
2. 以滑動窗口方式，逐段送入 `/api/analyze` 取得信號分析
3. 根據入場/出場規則模擬交易
4. 彙整績效指標，回傳結果

### 入場條件
- 信號類型：確認信號（強烈買入 或 強烈賣出）
- 品質門檻：quality_score ≥ 4（含 4 星）
- 多空雙向：同時回測做多與做空信號

### 出場條件
- 使用 API 回傳的動態 SL/TP 價格
- 以下一根 K 線逐 bar 檢查是否觸及 SL 或 TP
- 若同一根 K 線同時觸及 SL 和 TP，以先觸及者為準（用 high/low 判斷）

### CD 冷卻機制
- **主要規則：** 持倉中不開新單（前一筆交易 SL/TP 觸發後才能開下一筆）
- **預留參數：** `cooldown_bars`（K 線根數冷卻），預設 0（不啟用），供後續擴充使用
- 避免連續信號造成不切實際的交易頻率

### 滑價模擬
- 入場滑價：±0.05%（做多加、做空減）
- 可透過參數 `slippage_pct` 自訂（預設 0.05）

## 績效指標

### 統計指標
- 總交易次數（多/空分開統計）
- 勝率（Win Rate）
- 平均盈虧比（Average R:R）
- 最大連續虧損次數（Max Consecutive Losses）
- 最大回撤（Max Drawdown %）
- 總累計損益（Total PnL %）
- 平均持倉時間（Average Holding Bars）

### 視覺化
- K 線圖上標記買賣點（進場▲/▼ + 出場標記，區分勝/負）
- 累計損益曲線（Equity Curve）
- 績效統計面板

## 前端設計

### 控制面板
- 交易對選擇（symbol）
- 時間週期選擇（interval）
- K 線數量選擇（500 / 1000）
- 品質星數門檻（滑桿，1-5，預設 4）
- 滑價百分比（輸入框，預設 0.05）
- CD 根數（輸入框，預設 0）
- 「開始回測」按鈕

### 結果展示
- 績效統計卡片（勝率、交易次數、R:R、最大回撤等）
- K 線圖 + 買賣點標記（TradingView Lightweight Charts）
- Equity Curve 折線圖
- 交易明細表（可展開，含每筆進出場價格、盈虧、持倉時間）

## API 端點

### `GET /api/backtest`
參數：
- `symbol` — 交易對（必填）
- `interval` — K 線週期（必填）
- `limit` — K 線數量，500 或 1000（預設 500）
- `min_quality` — 最低品質星數（預設 4）
- `slippage_pct` — 滑價百分比（預設 0.05）
- `cooldown_bars` — CD 冷卻根數（預設 0）
- 指標參數（rsi_period, ema_fast, ema_slow 等，透傳給 `/api/analyze`）

回傳：
- `trades[]` — 每筆交易明細（入場/出場時間、價格、方向、盈虧、持倉 bars）
- `stats` — 績效統計摘要
- `equity_curve[]` — 累計損益序列
- `candles[]` — K 線數據（供前端繪圖）

## 任務清單
- [x] 建立 `app_backtest.py` 基礎架構（HTTP server + CLI 參數）
- [x] 實作 Binance 歷史 K 線數據拉取（500/1000 根）
- [x] 實作滑動窗口回測引擎（import ScalpingAnalyzerPro）
- [x] 實作入場邏輯（強烈買入/賣出 + quality ≥ 4 + confirmed）
- [x] 實作出場邏輯（SL/TP 逐 bar 檢查，含同時觸及判斷）
- [x] 實作 CD 機制（持倉中不開單 + 預留 cooldown_bars）
- [x] 實作滑價模擬（±slippage_pct%）
- [x] 實作績效指標計算（勝率/RR/PF/回撤/連虧等）
- [x] 實作 `/api/backtest` 端點
- [x] 建立前端頁面（控制面板 + 結果展示）
- [x] K 線圖買賣點標記（TradingView Lightweight Charts）
- [x] Equity Curve 圖表
- [x] 交易明細表
