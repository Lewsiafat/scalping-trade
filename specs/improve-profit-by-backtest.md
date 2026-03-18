# 透過回測優化交易績效

- **分支:** `feat/improve-profit-by-backtest`
- **日期:** 2026-03-18

## 描述
目前回測績效不佳，透過兩階段改善：(1) 新增參數優化引擎，以網格搜尋自動找出最佳指標/過濾參數組合；(2) 改善入場/出場邏輯，包含時段過濾、連虧保護、Trailing Stop、部分止盈等機制。

## Phase 1: 參數優化引擎

### 可優化參數
**Layer A — 指標參數（影響信號產生）**
- `ema_fast`: [5, 7, 9, 12]
- `ema_slow`: [15, 21, 30]
- `rsi_period`: [10, 14, 18]
- `rsi_overbought/oversold`: [65/35, 70/30, 75/25]

**Layer B — 回測過濾參數（影響入場品質）**
- `min_quality`: [2.5, 3.0, 3.5, 4.0]
- `cooldown_bars`: [0, 1, 3, 5]

### 排序指標
- 主要：Profit Factor（總盈利 / 總虧損）
- 次要：PnL% / MaxDrawdown 比值（類 Sharpe）
- 過濾：交易次數 ≥ 5 筆才納入排名

### API
- `GET /api/optimize` — 參數：symbol, interval, limit, 各參數搜尋範圍（可選）
- 回傳 Top 10 參數組合 + 各自績效指標

### 前端
- 「參數優化」按鈕（獨立於一般回測）
- 結果排行表（可點擊套用最佳參數）
- 進度條（顯示已完成/總組合數）

## Phase 2: 入場/出場邏輯改善

### 入場改善
- **時段過濾**：統計各小時勝率，可設定避開低勝率時段
- **連虧保護**：連續 N 次虧損後暫停 M 根 K 線（預設 N=3, M=10）

### 出場改善
- **Trailing Stop（移動止損）**：價格達 TP1 後，SL 上移至入場價（保本）
- **部分止盈**：TP1 平 50% 倉位，剩餘跑到 TP2 或被 Trailing Stop 平倉

### 前端
- 新增開關：Trailing Stop (on/off)、部分止盈 (on/off)
- 新增輸入：連虧保護 N/M 值、時段過濾設定
- 績效統計增加：按出場類型分類統計（SL/TP1/TP2/Trailing/Force）

## 任務清單

### Phase 1
- [x] 實作 `ParameterOptimizer` 類別（網格搜尋 + 結果排序）
- [x] 新增 `/api/optimize` 端點
- [x] 前端：參數優化 UI（按鈕、進度條、排行表）
- [x] 排行表點擊套用最佳參數功能
- [x] 新增入場模式優化（strong_only / include_normal）
- [x] 新增 confirmed / caution RR 開關優化

### Phase 2
- [x] 實作 Trailing Stop 邏輯（TP1 後 SL 移至入場價）
- [x] 實作部分止盈邏輯（TP1 平 50%，剩餘跑 TP2）
- [x] 實作連虧保護機制（連 N 虧停 M 根）
- [ ] 實作時段過濾（統計小時勝率 + 可配置過濾）— 留待下次
- [x] 前端：新增 Phase 2 控制項
- [x] 績效統計：按出場類型分類
- [x] 修正 Trailing Stop bug（同 bar TP1 觸發後不應立即檢查新 SL）
