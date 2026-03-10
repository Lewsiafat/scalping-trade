# 回顧 v4.0.0 信號觸發問題修復 — Walkthrough

## 任務摘要
- **分支**: `refactor/review-last-tags-changes`
- **日期**: 2026-03-10
- **Summary**: 修復 v4.0.0 重構後買賣信號幾乎無法觸發的問題。根因為兩個設計缺陷：一是 pre-alert 被設為正式信號的強制前置條件，導致三維評分達標仍輸出觀望；二是 MACD 評分使用固定絕對值閾值（0.5/0.3），對高價資產（BTC/ETH）完全失效。

## 變更項目

- **`app_v3.py`** — 核心邏輯修改（兩處）
- **`specs/review-last-tags-changes.md`** — 任務規格文件（新增）
- **`specs/review-last-tags-changes-walkthrough.md`** — 本 Walkthrough 文件（新增）

## 技術細節

### 問題 1：pre-alert 強制前置（`analyze_entry_signal` L1942）

**原始邏輯：**
```python
else:
    # 三維達標但無預警 → 降級為觀望
    overall = 'neutral'
    action = '觀望 WAIT'
    signal_type = None
```
三維評分（Trend/Structure/Momentum）全部達到閾值，但若價格沒有接近 OB/Swing/FVG（ATR×0.5 內），整個信號被強制歸零。這使得三維評分形同虛設。

**修改後（方案 A）：**
```python
else:
    # 三維達標但無預警 → 仍發出信號，不帶 confirmed badge
    sl_tp = ScalpingAnalyzerPro.calc_dynamic_sl_tp(...)
    signal_stage = None   # 無結構確認，無 badge
    signal_label = ScalpingAnalyzerPro.determine_signal_label(...)
```
- 三維達標 → 發出 buy/sell 指示（`overall` 保持 `strong_buy`/`buy`/`sell` 等）
- `signal_stage = None` → 前端不顯示 confirmed badge
- pre-alert + 三維 + R:R ≥ 1.0 仍可升級為 `confirmed`（最高等級不變）

### 問題 2：MACD 絕對值閾值（`calc_momentum_score` L1524）

**原始邏輯：**
```python
if 0 < histogram < 0.5:    # MACD 柱翻 +20
if 0 < diff < 0.3:          # MACD 叉 +10
```
BTC 的 MACD histogram 可能是幾百，ETH 也是幾十，完全不會落在 0~0.5 的範圍，導致 momentum score 永遠拿不到 MACD 的 30 分。

**修改後：**

*MACD 柱翻（+20）*：改為比對前後兩根 histogram 的符號穿越
```python
_, _, prev_histogram = calculate_macd(closes[:-1], ...)  # 前一根
if prev_histogram <= 0 < histogram:   score += 20  # 從負轉正
elif prev_histogram >= 0 > histogram: score += 20  # 從正轉負
```

*MACD 叉（+10）*：改為 ATR 正規化閾值
```python
threshold = atr * 0.1   # BTC ATR ~400 → 閾值 $40
if 0 < diff < threshold:   score += 10  # 金叉
elif -threshold < diff < 0: score += 10  # 死叉
```
無 ATR 時 fallback 使用 MACD line 相對比例（`diff / abs(macd_line) < 0.15`）。

### 信號等級體系（修改後完整版）

| 條件 | signal_stage | 行為 |
|------|-------------|------|
| 三維達標 + pre-alert + R:R ≥ 1.0 | `confirmed` | 顯示 confirmed badge + SL/TP |
| 三維達標，無 pre-alert | `None` | 顯示 buy/sell，嘗試計算 SL/TP，無 badge |
| 三維達標 + pre-alert，但 R:R < 1.0 | `pre_alert` | 降為預警，顯示 R:R 不足 |
| 僅 pre-alert（三維未達標） | `pre_alert` | 預警通知 |
| 以上皆非 | `None` | 觀望 WAIT |
