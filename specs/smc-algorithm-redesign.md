# SMC 演算法重構

- **分支:** `refactor/smc-algorithm-redesign`
- **日期:** 2026-03-09

## 描述
以 SMC (Smart Money Concepts) 為主導架構，全面重構剝頭皮分析引擎。修正現有指標計算錯誤、導入 OB/BOS/FVG/Liquidity Sweep、改用三維評分系統、實作兩階段信號（預警+確認）、動態止損止盈。詳細設計見 `docs/plans/2026-03-09-smc-algorithm-redesign.md`。

## 任務清單

### 後端 — SMC 引擎（新增）
- [x]實作 `find_swing_points()` — Swing High/Low 識別（N=3/5，保留 20 個）
- [x]實作 `detect_bos()` — Break of Structure 檢測（收盤價突破，記錄方向+時間戳）
- [x]實作 `identify_order_blocks()` — Order Block 識別（BOS 前最後反向 K 線，最多 5 個有效 OB）
- [x]實作 `identify_fvg()` — Fair Value Gap 識別（三根 K 線跳空，最多 3 個未填補 FVG）
- [x]實作 `detect_liquidity_sweep()` — Liquidity Sweep 檢測（影線掃盤+收盤反轉，1-3 根確認窗口，ATR×0.5 最小深度）

### 後端 — 指標修正
- [x]重寫 `calculate_rsi()` — 改用 Wilder's 平滑法
- [x]重寫 `calculate_macd()` — 信號線改 EMA(9)，預設參數改 12/26/9
- [x]重寫 `calculate_stochastic()` — %D 改為 SMA(%K, 3)
- [x]修改 `calculate_ema()` — 預設快線 9、慢線 21
- [x]刪除 `calculate_fibonacci_levels()` 及相關引用
- [x]改良 `analyze_volume()` — CVD 用 taker_buy_volume，窗口 10→20

### 後端 — 三維評分系統
- [x]實作趨勢分數計算（BOS 方向 + EMA 排列 + BB 位置，映射 0-100）
- [x]實作結構分數計算（OB 進入 + FVG + Sweep 確認，累加 0-100）
- [x]實作動量分數計算（RSI/MACD/Stochastic/Volume/taker_buy，累加 0-100）
- [x]實作綜合信號判定（三維門檻：強烈買入/考慮買入/強烈賣出/考慮賣出/觀望）

### 後端 — 兩階段信號
- [x]實作預警觸發邏輯（距離 OB ≤ ATR×0.5 / 接近 Swing / FVG 50%）
- [x]實作正式信號確認邏輯（預警 + 三維達標）
- [x]實作過期機制（預警 6 根過期、信號 3 根失效）

### 後端 — 動態止損止盈
- [x]重寫 `calculate_stop_loss_take_profit()` — 結構錨點 + ATR clamp(1.0, 2.5)
- [x]止盈用結構目標（FVG/OB/Swing），回退 ATR 倍數
- [x]R:R < 1.0 時不發出信號

### 後端 — 數據管線
- [x]K 線請求量 100→150
- [x]實作 MTF 記憶體快取（同一根未收盤 K 線不重複請求）
- [x]新增數據驗證層（數量/zero-volume/時間戳連續性/異常波動）
- [x]解析 taker_buy_base_volume 欄位

### 後端 — API 回傳格式
- [x]`/api/analyze` 回傳新增三維分數（trend_score, structure_score, momentum_score）
- [x]回傳預警資訊（alert_type, alert_message, proximity）
- [x]回傳信號類型標籤（signal_label: "OB 反彈", "Sweep 確認" 等）
- [x]回傳 R:R 比率
- [x]向後相容：保留 quality_score（取三維平均）和 action 欄位

### 前端 — UI 調整
- [x]星級顯示改為三維進度條（趨勢/結構/動量，各 0-100）
- [x]新增預警提示 UI（黃色/橘色色調，不建議動作）
- [x]正式信號 UI（綠色/紅色，含信號類型標籤）
- [x]止損止盈顯示 R:R 比率
- [x]i18n 支援新增文字（預警、三維度名稱、信號類型）
