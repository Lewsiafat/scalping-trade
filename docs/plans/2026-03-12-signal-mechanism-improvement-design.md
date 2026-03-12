# 信號機制根本性改善設計

**日期：** 2026-03-12
**分支：** （待建立）
**狀態：** 設計完成，待實作

## 背景

v4.0.0 的 SMC 重構 + `refactor/review-last-tags-changes` 修正後，信號仍然難以觸發。
`feature/relax-signal-thresholds` 嘗試放寬門檻有改善，但屬於治標。

### 根本原因（五大問題）

1. **Structure Score ≥ 60 幾乎依賴 Sweep** — Sweep 是低頻事件（需 wick 穿透 + close 反向 + 確認 K 線），無 Sweep 時最高只能拿 45 分
2. **Momentum Score 常態只有 20-30 分** — 只獎勵反轉信號，趨勢延續時幾乎不給分
3. **R:R < 1.0 一刀切拒絕信號** — 用 TP2 計算 R:R，且 0.7-1.0 之間的可接受機會被完全過濾
4. **三維硬門檻 AND 邏輯** — 三個獨立中等難度條件同時滿足的聯合機率極低
5. **Momentum 缺少趨勢延續給分** — RSI 40-60、MACD 同向等常見狀態完全不得分

## 方案 A：結構權重動態化（主要實作，修改 app_v3.py）

### 改動 1：Partial Sweep（三級 Sweep 檢測）

修改方法：`detect_liquidity_sweep()` + `calc_structure_score()`

三級分類：

| 等級 | 條件 | 分數 |
|------|------|------|
| Full Sweep | wick 穿透 + close 反向 + depth ≥ ATR×0.5 + 確認 K 線 | +25 |
| Partial Sweep | (a) wick 穿透，close 未反向但 depth ≥ ATR×0.3；或 (b) wick 穿透 + close 反向但無確認 K 線 | +15 |
| Near Sweep | wick 到達 swing point ± ATR×0.2（觸碰但未穿透） | +8 |

`detect_liquidity_sweep()` 回傳新增 `strength` 欄位：`'full'` / `'partial'` / `'near'`

### 改動 2：Momentum 趨勢延續模式

修改方法：`calc_momentum_score()` 簽名新增 `trend_direction` 參數

趨勢延續條件（與反轉互斥，同一指標只取較高分）：

**Bullish 延續：**
- MACD > 0 且 histogram > 0 → +15
- 40 < RSI < 65 → +10
- Stoch K > D 且 K < 70 → +10

**Bearish 延續：**
- MACD < 0 且 histogram < 0 → +15
- 35 < RSI < 60 → +10
- Stoch K < D 且 K > 30 → +10

`trend_direction` 由 `analyze_entry_signal()` 根據 BOS + EMA 方向推導後傳入。

### 改動 3：R:R 分級處理

修改方法：`calc_dynamic_sl_tp()` + 信號判定區塊

| R:R 範圍 | 處理方式 | rr_grade |
|----------|---------|----------|
| ≥ 1.5 | 正常信號 | `'good'` |
| 1.0 ~ 1.5 | 正常信號 | `'acceptable'` |
| 0.7 ~ 1.0 | 降級為 pre_alert，保留 SL/TP | `'caution'` |
| < 0.7 | 拒絕信號（return None） | — |

R:R 改用 TP1（而非 TP2）計算主要比值，TP2 作為 `extended_rr` 附加資訊。

### 改動 4：加權合分取代硬門檻

修改方法：`analyze_entry_signal()` 信號判定區塊

```
composite = trend × 0.35 + structure × 0.40 + momentum × 0.25
min_floor = min(trend, structure, momentum)

strong_buy:  composite ≥ 55, min_floor ≥ 30, trend ≥ 55
buy:         composite ≥ 45, min_floor ≥ 25, trend ≥ 45
strong_sell: composite ≥ 55, min_floor ≥ 30, trend ≤ 45
sell:        composite ≥ 45, min_floor ≥ 25, trend ≤ 55
neutral:     其他
```

權重邏輯：Structure 最重要（0.40），Trend 次之（0.35），Momentum 輔助（0.25）。

### 改動 5：評分明細面板（前端）

每個 `calc_*_score()` 回傳值從 `int` 改為 `dict`：

```python
return {
    'score': max(0, min(100, score)),
    'details': [
        {'item': 'BOS bullish', 'points': 30},
        {'item': 'MTF 一致', 'points': 25},
        ...
    ]
}
```

API response 新增 `score_breakdown` 欄位。

前端用 `<details><summary>` 原生元素，預設收合。三維明細 + composite 計算過程 + R:R 等級。配合 i18n 雙語。

## 方案 B：條件累積引擎（獨立檔案，供測試比較）

### 檔案：`signal_engine_b.py`

從 `app_v3.py` import 基礎指標計算方法，只重寫信號判定邏輯。

10 個布林條件：

1. BOS 方向一致 — 最近 BOS 與 EMA 排列同向
2. MTF 確認 — 多時間框架趨勢一致
3. OB 接近/進入 — 價格在 OB 範圍或 ≤ ATR×0.5
4. FVG 存在 — 未填補 FVG 且價格接近
5. Sweep 發生 — 任何等級（full/partial/near）
6. MACD 同向 — macd_line 與信號方向一致
7. RSI 合理區間 — 非極端區域（25-75）
8. Stoch 方向一致 — K/D 叉方向與信號一致
9. 成交量支持 — volume_ratio > 0.8
10. R:R ≥ 0.7 — 止損止盈比可接受

信號判定：
- strong_buy/sell: ≥ 7/10
- buy/sell: ≥ 5/10
- neutral: < 5

方向判定：BOS + EMA + MTF 多數決。

### 檔案：`test_signal_compare.py`

```
用法：python3 test_signal_compare.py [symbol] [interval]
預設：BTCUSDT 5m
```

從 Binance 抓 150 根 K 線，分別餵給方案 A 和方案 B，輸出對比表格。
支援 `--loop` 參數持續每 10 秒刷新比較。

## 影響範圍

### 後端修改（app_v3.py）
- `detect_liquidity_sweep()` — 新增三級分類 + strength 欄位
- `calc_structure_score()` — 根據 sweep strength 給不同分數
- `calc_momentum_score()` — 新增 trend_direction 參數 + 趨勢延續評分
- `calc_trend_score()` — 回傳 dict（含 details）
- `calc_dynamic_sl_tp()` — R:R 分級 + 用 TP1 計算 + rr_grade
- `analyze_entry_signal()` — 加權合分 + trend_direction 推導 + 組裝 score_breakdown

### 前端修改（HTML_PAGE 內嵌）
- 新增 `<details>` 評分明細面板
- 解析 score_breakdown 渲染明細列表
- i18n 新增明細相關文字

### 新增檔案
- `signal_engine_b.py` — 方案 B 獨立引擎
- `test_signal_compare.py` — A/B 對比測試腳本
