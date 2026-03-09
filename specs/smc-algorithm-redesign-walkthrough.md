# SMC 演算法重構 — Walkthrough
## 任務摘要
- **分支**: `refactor/smc-algorithm-redesign`
- **日期**: 2026-03-09
- **Summary**: 以 SMC (Smart Money Concepts) 為主導架構全面重構剝頭皮分析引擎。修正 RSI/MACD/Stochastic 計算、導入 OB/BOS/FVG/Liquidity Sweep 結構分析、改用三維評分系統（趨勢/結構/動量 0-100）、實作兩階段信號（預警→確認）、動態止損止盈（結構錨點 + ATR clamp）。前端新增三維進度條、預警/確認信號 UI、R:R 視覺提示。新檔案 `app_v3.py` (v4.0.0)，原 `app_v2.py` 保留為 v3.6.0 參考。

## 變更項目
| 檔案 | 狀態 | 說明 |
|------|------|------|
| `app_v3.py` | 新增 | SMC 重構版 v4.0.0（原 app_v2.py 重構後更名），+1100 行新增程式碼 |
| `app_v2.py` | 還原 | 從 main 還原為 v3.6.0 舊版，保留參考 |
| `specs/smc-algorithm-redesign.md` | 新增 | 31 項任務規格清單 |
| `specs/smc-algorithm-redesign-walkthrough.md` | 新增 | 本文件 |

## 技術細節

### 階段 1：數據管線 + 指標修正
- K 線請求量 100→150，新增 `validate_kline_data()` 驗證層
- `fetch_klines_cached()` MTF 記憶體快取，未收盤 K 線不重複請求
- RSI 改 Wilder's 平滑法、MACD 信號線改 EMA(9)、Stochastic %D 改 SMA(%K,3)
- EMA 預設 9/21、刪除 Fibonacci、Volume CVD 改用 taker_buy_base_volume

### 階段 2：SMC 引擎
- `find_swing_points()` — N=3/5 雙窗口 Swing High/Low
- `detect_bos()` — 收盤價突破 Swing 確認 Break of Structure
- `identify_order_blocks()` — BOS 前最後反向 K 線（最多 5 個）
- `identify_fvg()` — 三根 K 線跳空 Fair Value Gap（50% 填補失效）
- `detect_liquidity_sweep()` — 影線掃盤 + 收盤反轉（深度 ≥ ATR×0.5）

### 階段 3：三維評分 + 動態止損止盈
- 趨勢分數 (0-100): BOS 方向 + MTF 一致 + EMA 排列 + BB 位置
- 結構分數 (0-100): OB 進入 + 趨勢一致 + FVG + Sweep 確認
- 動量分數 (0-100): RSI 反轉/背離 + MACD 柱翻/交叉 + Stoch 交叉 + 放量
- 動態 SL/TP: 結構錨點 + ATR clamp(1.0, 2.5)，R:R < 1.0 不發信號

### 階段 4：兩階段信號 + API 格式
- 預警觸發：距 OB ≤ ATR×0.5 / 接近 Swing / FVG 內
- 正式信號：預警 + 三維達標 + R:R ≥ 1.0
- 過期機制：預警 6 根、信號 3 根 K 線失效
- API 新增 7 欄位：trend/structure/momentum_score, signal_label, signal_stage, pre_alert, smc

### 階段 5：前端 UI
- 三維進度條取代星級顯示（趨勢紫/結構金/動量綠）
- 預警 UI（橘黃色漸層，顯示 alert_message）
- 確認信號 UI（信號類型標籤 badge）
- R:R 視覺提示（≥2.0 ✅ / ≥1.5 🟡 / <1.5 ⚠️）
- i18n EN/ZH_TW 各新增 13 個 key
