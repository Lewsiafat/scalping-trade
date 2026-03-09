# SMC 演算法重構設計

> 日期：2026-03-09
> 狀態：已核准
> 方案：A — SMC 主導架構

## 問題背景

現有剝頭皮演算法存在五大問題：

1. **假突破反轉** — 強烈賣出信號後行情反轉為買入，因系統無法辨識流動性掃盤（Liquidity Sweep）
2. **時效性不足** — 信號觸發時行情已過，缺乏預警機制
3. **指標計算錯誤** — MACD 信號線用 `×0.9` 取代 EMA、Stochastic %D 同樣簡化、RSI 未用 Wilder's 平滑法
4. **止損止盈缺乏依據** — 固定 ATR×1.5 倍數，不考慮市場結構
5. **評分系統粗糙** — 單一分數無法反映信號品質的多面向

## 設計原則

剝頭皮的本質不能因 SMC 導入而改變：

- 快進快出、小利潤高勝率、不戀戰
- 信號要求即時性，不等完美結構
- 止盈目標近且務實，不貪大波段
- 持倉時間預期幾分鐘到半小時
- 寧可錯過也不要套牢

## 方案選擇

| 方案 | 描述 | 結論 |
|------|------|------|
| A（採用） | SMC 主導架構，傳統指標為確認工具 | 直擊假突破問題，天然支持兩階段信號 |
| B | 傳統指標重構 + SMC 過濾器 | 太保守，SMC 只是事後過濾 |
| C | 雙引擎並行 | 太複雜，合併規則難調優 |

## 一、SMC 核心結構分析引擎

### Swing Point 識別

```
Swing High: 該 K 線的 high 高於前後各 N 根 K 線的 high
Swing Low:  該 K 線的 low 低於前後各 N 根 K 線的 low
N = 3（5m 圖）/ 5（15m 圖）
```

保留最近 20 個 Swing Points。

### Break of Structure (BOS)

```
多頭 BOS：收盤價突破最近的 Swing High → 結構轉多
空頭 BOS：收盤價跌破最近的 Swing Low → 結構轉空
```

- 只看收盤價突破，影線不算（過濾假突破）
- BOS 發生後記錄方向 + 時間戳，直到下一次 BOS 才更新

### Order Block (OB)

```
Bullish OB：BOS 向上突破前的「最後一根陰線」的範圍 (open~close)
Bearish OB：BOS 向下跌破前的「最後一根陽線」的範圍 (open~close)
```

- 只保留未被測試過的 OB
- 第一次碰觸有效，第二次碰觸失效移除
- 最多追蹤最近 5 個有效 OB

### Fair Value Gap (FVG)

```
Bullish FVG：K線1 的 high < K線3 的 low（中間跳空缺口）
Bearish FVG：K線1 的 low > K線3 的 high
FVG 範圍 = 缺口的上下邊界
```

- 被填補超過 50% 後標記失效
- 只追蹤最近 3 個未填補的 FVG

### Liquidity Sweep 檢測

```
Bullish Sweep：
  1. 價格影線跌破最近 Swing Low（掃停損）
  2. 收盤價收回 Swing Low 之上
  3. 隨後 1-3 根 K 線內出現反轉（收陽）

Bearish Sweep：
  1. 價格影線突破最近 Swing High（掃停損）
  2. 收盤價收回 Swing High 之下
  3. 隨後 1-3 根 K 線內出現反轉（收陰）
```

- 1-3 根 K 線為剝頭皮約束，過期作廢
- Sweep 深度須超過 Swing Point 的 ATR × 0.5 才算有效

## 二、傳統指標修正

### RSI — Wilder's 平滑法

```
第一次：avg_gain = SMA(gains, 14), avg_loss = SMA(losses, 14)
後續：avg_gain = (prev_avg_gain × 13 + current_gain) / 14
      avg_loss = (prev_avg_loss × 13 + current_loss) / 14
RSI = 100 - (100 / (1 + avg_gain / avg_loss))
```

### MACD — 正規信號線

```
MACD Line = EMA(12) - EMA(26)（回歸標準參數）
Signal Line = EMA(MACD Line, 9)（正規 9 週期 EMA）
Histogram = MACD Line - Signal Line
```

### Stochastic — 正規 %D

```
%K = ((Close - Lowest Low) / (Highest High - Lowest Low)) × 100（14 週期）
%D = SMA(%K, 3)（正規 3 週期 SMA）
```

### EMA — 預設參數調整

```
快線：5 → 9
慢線：20 → 21
```

### 維持不動

- Bollinger Bands、ATR 演算法不變
- CVD 窗口從 10 擴大到 20 根

### 移除

- Fibonacci Retracement（算了沒用，SMC 的 OB/FVG 取代）

## 三、三維評分系統

每個維度 0-100 分，各自獨立。

### 趨勢分數（Trend Score）

回答：「大方向站在哪一邊？」

| 條件 | 分數 |
|------|------|
| 15m BOS 方向（多/空） | +30 / -30 |
| 5m BOS 與 15m 一致 | +25 |
| 5m BOS 與 15m 矛盾 | -10 |
| EMA 9 > EMA 21（多頭排列） | +15 |
| EMA 9 < EMA 21（空頭排列） | -15 |
| 價格在 EMA 9 之上/之下 | +10 / -10 |
| Bollinger Band 位置 | +10 ~ -10 |

原始分加 50 映射到 0-100。50 = 中性，70+ = 多頭，30- = 空頭。

### 結構分數（Structure Score）

回答：「SMC 結構支不支持進場？」

| 條件 | 分數 |
|------|------|
| 價格進入未測試的 OB 區域 | +30 |
| OB 方向與趨勢一致 | +15（矛盾則 +0） |
| 附近存在未填補的 FVG | +15 |
| 偵測到 Liquidity Sweep 且反轉確認 | +25 |
| Sweep 深度合理（ATR × 0.3~0.8） | +10 |
| Sweep 深度過深（> ATR × 1.5） | -10 |
| OB 已被測試過一次 | -15 |

直接累加，底線 0，上限 100。60+ = 結構良好。

### 動量分數（Momentum Score）

回答：「現在的力道夠不夠？」

| 條件 | 分數 |
|------|------|
| RSI 超賣/超買反轉 | +20 |
| RSI 背離 | +15 |
| MACD 柱狀圖翻正/翻負 | +20 |
| MACD 金叉/死叉 | +10 |
| Stochastic %K 穿越 %D | +10 |
| 成交量比率 > 1.5 | +15 |
| 成交量比率 < 0.8 | -10 |
| 主動買入量佔比 > 60% | +10 |

直接累加，底線 0，上限 100。60+ = 動量充足。

### 綜合信號判定

```
強烈買入：趨勢 ≥ 65 AND 結構 ≥ 60 AND 動量 ≥ 55
考慮買入：趨勢 ≥ 55 AND 結構 ≥ 45 AND 動量 ≥ 45
強烈賣出：趨勢 ≤ 35 AND 結構 ≥ 60 AND 動量 ≥ 55
考慮賣出：趨勢 ≤ 45 AND 結構 ≥ 45 AND 動量 ≥ 45
觀望：任一維度不達標
```

結構分數為必要條件 — 沒有 SMC 結構支撐不發信號。

## 四、兩階段信號系統

### 第一階段：預警

觸發條件（任一）：

1. 價格距離未測試 OB ≤ ATR × 0.5
2. 價格正在接近 Swing High/Low（潛在 Sweep 區域）
3. FVG 即將被填補（價格進入 FVG 範圍 50% 內）

預警不建議任何動作，僅提醒注意。前端用柔和提示色（黃色/橘色）。

### 第二階段：正式信號

觸發條件：預警觸發後 + 三維評分全部達標。

前端用強烈提示色（綠色/紅色）+ 瀏覽器通知。

### 過期機制

```
預警：超過 6 根 K 線未觸發確認 → 自動過期（5m 圖 = 30 分鐘）
正式信號：超過 3 根 K 線價格未朝預期方向移動 → 標記為「失效」
```

## 五、動態止損止盈

### 止損

```
基礎止損 = OB 邊界外側
最小止損 = ATR × 1.0
最大止損 = ATR × 2.5
最終止損 = clamp(結構止損, ATR×1.0, ATR×2.5)
```

若結構止損超過 ATR×2.5 → 不適合剝頭皮，降低結構分數。

### 止盈

```
止盈① = 最近阻力結構（FVG 上緣、對面 OB、前 Swing Point），最小 ATR×1.0
止盈② = 下一層阻力結構，最小 ATR×2.0
找不到結構目標 → 回退到 ATR×1.5 / ATR×3.0
```

### 風險報酬比

```
R:R = (止盈① - 進場) / (進場 - 止損)
R:R < 1.0 → 不發出信號
```

## 六、數據管線優化

### K 線請求量

100 → 150 根，支撐 Wilder's RSI 暖機 + SMC 回溯。

### MTF 快取

```
記憶體快取：{symbol}_{interval} → {candles, fetched_at, close_time}
快取策略：當前時間 < 當前 K 線收盤時間 → 用快取，否則重新請求
效果：約 70% 請求省掉一次 API call
```

### CVD 改良

```
舊：volume if close > open, else -volume
新：2 × taker_buy_volume - total_volume（真實主動買賣差）
```

### 數據驗證

1. K 線數量 ≥ 150，不足回傳錯誤
2. Zero-volume K 線標記但不排除
3. 時間戳連續性檢查
4. 單根波動 > ATR×5 標記異常

## 七、不變的部分

- 單檔架構 `app_v2.py`
- Binance 免費 API，無需額外資料來源
- SnapshotManager / SymbolManager / AlertManager
- i18n 雙語系統
- API 路由結構（`/api/analyze` 回傳格式擴充但向後相容）

## 八、前端調整

- 星級顯示 → 三維進度條（趨勢/結構/動量）
- 新增預警提示（黃色/橘色色調）
- 信號卡片顯示類型標籤（OB 反彈、Sweep 確認等）
- 止損止盈顯示 R:R 比率
