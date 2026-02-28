# 📋 Technical Specification - Scalping Trade Analyzer Pro V2

## 技術規格文件

Version: 2.0
Last Updated: 2026-02-28
Author: Lewis Chan

---

## 📑 目錄

1. [系統架構](#系統架構)
2. [核心演算法](#核心演算法)
3. [API規格](#api規格)
4. [數據結構](#數據結構)
5. [前端實作](#前端實作)
6. [信號評分邏輯](#信號評分邏輯)
7. [效能優化](#效能優化)
8. [安全性考量](#安全性考量)

---

## 系統架構

### 整體架構圖

```
┌─────────────────────────────────────────────────────────────┐
│                         Browser                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   HTML UI    │  │  JavaScript  │  │ Notification │     │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘     │
│         │                  │                                 │
│         └──────────────────┼─────────────────────────────────┤
│                            │ HTTP/AJAX                       │
└────────────────────────────┼─────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python Backend                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           ScalpingHandler (HTTP Server)              │  │
│  │  - GET /         → HTML Page                         │  │
│  │  - GET /api/analyze → JSON Response                  │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                            │
│  ┌──────────────▼───────────────────────────────────────┐  │
│  │         ScalpingAnalyzerPro (Analysis Engine)        │  │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐       │  │
│  │  │   RSI      │ │    EMA     │ │   MACD     │       │  │
│  │  └────────────┘ └────────────┘ └────────────┘       │  │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐       │  │
│  │  │   Volume   │ │    MTF     │ │    ATR     │       │  │
│  │  └────────────┘ └────────────┘ └────────────┘       │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                            │
└─────────────────┼────────────────────────────────────────────┘
                  │
                  ▼
         ┌─────────────────┐
         │  Binance API    │
         │  (Public Data)  │
         └─────────────────┘
```

### 組件說明

#### 1. HTTP Server
- **類別**: `ScalpingHandler`
- **基礎類**: `http.server.SimpleHTTPRequestHandler`
- **功能**: 處理HTTP請求，提供靜態頁面與API服務
- **端口**: 80

#### 2. 分析引擎
- **類別**: `ScalpingAnalyzerPro`
- **類型**: Static Methods Only
- **功能**: 實作所有技術指標與信號分析邏輯

#### 3. 數據來源
- **API**: Binance Public API
- **端點**: `https://api.binance.com/api/v3/klines`
- **認證**: 無需（公開數據）

---

## 核心演算法

### 1. RSI（相對強弱指標）

**公式**:
```
RSI = 100 - (100 / (1 + RS))
RS = Average Gain / Average Loss
```

**實作**:
```python
def calculate_rsi(prices, period=14):
    gains = []
    losses = []

    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)
```

**參數**:
- `period`: 14（預設）
- `overbought`: 70
- `oversold`: 30

**信號判定**:
- RSI < 30: 超賣 → BUY
- RSI > 70: 超買 → SELL
- 45 < RSI < 55: 中性區域（降低品質分數）

---

### 2. EMA（指數移動平均）

**公式**:
```
Multiplier = 2 / (Period + 1)
EMA = (Price - Previous_EMA) × Multiplier + Previous_EMA
```

**實作**:
```python
def calculate_ema(prices, period):
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period

    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema

    return round(ema, 2)
```

**參數**:
- `fast_period`: 5（剝頭皮優化）
- `slow_period`: 20

**信號判定**:
- EMA_fast > EMA_slow: 上升趨勢 → BULLISH
- EMA_fast < EMA_slow: 下降趨勢 → BEARISH

---

### 3. MACD（平滑異同移動平均）

**公式**:
```
MACD_Line = EMA_fast - EMA_slow
Signal_Line = EMA(MACD_Line, signal_period)
Histogram = MACD_Line - Signal_Line
```

**實作**:
```python
def calculate_macd(prices, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)

    macd_line = ema_fast - ema_slow
    signal_line = macd_line * 0.9  # 簡化版
    histogram = macd_line - signal_line

    return round(macd_line, 2), round(signal_line, 2), round(histogram, 2)
```

**參數**（剝頭皮優化）:
- `fast`: 5
- `slow`: 20
- `signal`: 5

**信號判定**:
- MACD_line > Signal_line AND Histogram > 0: BUY
- MACD_line < Signal_line AND Histogram < 0: SELL

---

### 4. ATR（平均真實波幅）✨ V2

**公式**:
```
True_Range = max(
    High - Low,
    abs(High - Previous_Close),
    abs(Low - Previous_Close)
)
ATR = Average(True_Range, period)
```

**實作**:
```python
def calculate_atr(data, period=14):
    true_ranges = []
    for i in range(1, len(data)):
        high = float(data[i][2])
        low = float(data[i][3])
        prev_close = float(data[i-1][4])

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        true_ranges.append(tr)

    atr = sum(true_ranges[-period:]) / period
    return round(atr, 2)
```

**應用**:
- 止損距離 = 1.5 × ATR
- 獲利目標 = 止損距離 × RR比率

---

### 5. 成交量分析 ✨ V2

**組件**:

#### a) 成交量比率
```
Volume_Ratio = Current_Volume / Average_Volume(20)
```

**信號分級**:
- Ratio > 1.5: 強（放量）
- 0.8 < Ratio < 1.5: 正常
- Ratio < 0.8: 弱（縮量）

#### b) CVD（累積成交量差異）
```python
cvd_score = 0
for candle in last_10_candles:
    if close > open:
        cvd_score += volume  # 上漲K線加成交量
    else:
        cvd_score -= volume  # 下跌K線減成交量

trend = "bullish" if cvd_score > 0 else "bearish"
```

**實作**:
```python
def analyze_volume(data):
    volumes = [float(k[5]) for k in data[-20:]]
    avg_volume = sum(volumes) / len(volumes)
    current_volume = volumes[-1]
    volume_ratio = current_volume / avg_volume

    # CVD 計算
    cvd_score = 0
    for i in range(len(data)-10, len(data)):
        close = float(data[i][4])
        open_price = float(data[i][1])
        volume = float(data[i][5])

        if close > open_price:
            cvd_score += volume
        else:
            cvd_score -= volume

    cvd_trend = "bullish" if cvd_score > 0 else "bearish"

    return {
        'volume_ratio': round(volume_ratio, 2),
        'cvd_trend': cvd_trend,
        'signal': 'strong' if volume_ratio > 1.5 else
                  ('normal' if volume_ratio > 0.8 else 'weak')
    }
```

---

### 6. 多時間框架分析 ✨ V2

**時間框架映射**:
```
1m  → 5m   (檢查更大週期)
3m  → 15m
5m  → 15m
15m → 1h
```

**趨勢判定**:
```
EMA_20 > EMA_50 → Uptrend
EMA_20 < EMA_50 → Downtrend
否則 → Neutral
```

**實作**:
```python
def multi_timeframe_analysis(symbol, current_interval):
    timeframe_map = {
        '1m': '5m',
        '3m': '15m',
        '5m': '15m',
        '15m': '1h'
    }

    higher_tf = timeframe_map.get(current_interval, '15m')

    # 獲取更大時間框架數據
    data = fetch_binance_klines(symbol, higher_tf, 50)
    closes = [float(k[4]) for k in data]

    ema_20 = calculate_ema(closes, 20)
    ema_50 = calculate_ema(closes, 50)

    if ema_20 > ema_50:
        trend = "uptrend"
        trend_strength = (ema_20 - ema_50) / ema_50 * 100
    else:
        trend = "downtrend"
        trend_strength = (ema_50 - ema_20) / ema_50 * 100

    return {
        'timeframe': higher_tf,
        'trend': trend,
        'trend_strength': abs(trend_strength),
        'confirmation': trend != "neutral"
    }
```

---

### 7. 動態止損止盈計算 ✨ V2

**公式**:
```
Stop_Distance = ATR × 1.5
Target_Distance = Stop_Distance × Risk_Reward_Ratio

For BUY:
  Stop_Loss = Current_Price - Stop_Distance
  TP1 = Current_Price + Target_Distance × 0.5
  TP2 = Current_Price + Target_Distance

For SELL:
  Stop_Loss = Current_Price + Stop_Distance
  TP1 = Current_Price - Target_Distance × 0.5
  TP2 = Current_Price - Target_Distance
```

**實作**:
```python
def calculate_stop_loss_take_profit(current_price, atr, signal_type, risk_reward_ratio=2):
    stop_distance = atr * 1.5
    target_distance = stop_distance * risk_reward_ratio

    if signal_type == 'buy':
        stop_loss = current_price - stop_distance
        take_profit_1 = current_price + target_distance * 0.5
        take_profit_2 = current_price + target_distance
    else:  # sell
        stop_loss = current_price + stop_distance
        take_profit_1 = current_price - target_distance * 0.5
        take_profit_2 = current_price - target_distance

    risk_amount = abs(current_price - stop_loss)
    reward_amount = abs(take_profit_2 - current_price)
    actual_rr = reward_amount / risk_amount

    return {
        'stop_loss': round(stop_loss, 2),
        'take_profit_1': round(take_profit_1, 2),
        'take_profit_2': round(take_profit_2, 2),
        'risk_amount': round(risk_amount, 2),
        'reward_amount': round(reward_amount, 2),
        'risk_reward_ratio': round(actual_rr, 2),
        'atr': atr
    }
```

---

## 信號評分邏輯

### 品質評分系統（0-5星）

**評分組成**:

```python
quality_score = 0

# 1. RSI 信號貢獻 (+1/-0.5)
if rsi < oversold or rsi > overbought:
    quality_score += 1
elif 45 < rsi < 55:  # 中性區域
    quality_score -= 0.5

# 2. MACD 信號貢獻 (+1)
if (macd_line > signal_line and histogram > 0) or
   (macd_line < signal_line and histogram < 0):
    quality_score += 1

# 3. 成交量信號貢獻 (+1.5/-1)
if volume_signal == 'strong':
    quality_score += 1.5
elif volume_signal == 'weak':
    quality_score -= 1

# 4. 多時間框架確認 (+1.5/-1)
if mtf_confirmation and trend_matches_signal:
    quality_score += 1.5
elif mtf_confirmation and trend_opposite_signal:
    quality_score -= 1  # 逆勢扣分

# 5. CVD 趨勢確認 (+0.5)
if cvd_trend_matches_signal:
    quality_score += 0.5

# 最終評分（限制在0-5）
quality_score = max(0, min(5, quality_score))
```

### 綜合信號強度

**強度計算**:
```python
score = 0

# RSI 貢獻 (±1)
if rsi < oversold: score += 1
elif rsi > overbought: score -= 1

# EMA 貢獻 (±1)
if ema_fast > ema_slow: score += 1
else: score -= 1

# MACD 貢獻 (±1)
if macd_line > signal_line and histogram > 0: score += 1
elif macd_line < signal_line and histogram < 0: score -= 1

# 成交量加成 (±0.5)
if volume_signal == 'strong':
    score += 0.5 if score > 0 else -0.5

# 多時間框架加成 (±1)
if mtf_trend == 'uptrend' and score > 0: score += 1
elif mtf_trend == 'downtrend' and score < 0: score -= 1

strength = abs(score)
```

### 操作建議決策樹

```
if score >= 3 AND quality_score >= 3:
    → 強烈買入 BUY (Strong Buy)

elif score >= 2 AND quality_score >= 2:
    → 考慮買入 (Buy)

elif score <= -3 AND quality_score >= 3:
    → 強烈賣出 SELL (Strong Sell)

elif score <= -2 AND quality_score >= 2:
    → 考慮賣出 (Sell)

else:
    → 觀望 WAIT (Neutral)
```

---

## API規格

### 端點: `GET /api/analyze`

**請求參數**:

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| symbol | string | BTCUSDT | 交易對 |
| interval | string | 5m | 時間框架 |
| rsi_period | integer | 14 | RSI週期 |
| rsi_overbought | integer | 70 | RSI超買線 |
| rsi_oversold | integer | 30 | RSI超賣線 |
| ema_fast | integer | 5 | 快速EMA |
| ema_slow | integer | 20 | 慢速EMA |
| macd_fast | integer | 5 | MACD快線 |
| macd_slow | integer | 20 | MACD慢線 |
| macd_signal | integer | 5 | MACD信號線 |

**範例請求**:
```
GET /api/analyze?symbol=BTCUSDT&interval=5m&rsi_period=14
```

**回應格式**:

```json
{
  "success": true,
  "symbol": "BTCUSDT",
  "price": 65000.50,
  "timestamp": "2026-02-28T14:30:00.000Z",
  "signals": {
    "rsi": {
      "value": 45.5,
      "signal": "neutral"
    },
    "ema": {
      "fast": 64990.2,
      "slow": 64950.8,
      "signal": "bullish"
    },
    "macd": {
      "line": 12.5,
      "signal": 10.2,
      "histogram": 2.3,
      "signal": "buy"
    },
    "volume": {
      "volume_ratio": 1.8,
      "cvd_trend": "bullish",
      "signal": "strong",
      "avg_volume": 1500000,
      "current_volume": 2700000
    },
    "multi_timeframe": {
      "timeframe": "15m",
      "trend": "uptrend",
      "trend_strength": 1.2,
      "ema_20": 65100,
      "ema_50": 64350,
      "confirmation": true
    },
    "stop_loss_take_profit": {
      "stop_loss": 64775.0,
      "take_profit_1": 65225.0,
      "take_profit_2": 65450.0,
      "risk_amount": 225.0,
      "reward_amount": 450.0,
      "risk_reward_ratio": 2.0,
      "atr": 150.0
    },
    "overall": "strong_buy",
    "action": "強烈買入 BUY",
    "strength": 3,
    "quality_score": 4.5
  }
}
```

**錯誤回應**:
```json
{
  "success": false,
  "error": "Error message"
}
```

---

## 數據結構

### Binance K線數據格式

```python
[
  [
    1499040000000,      # 0: 開盤時間
    "0.01634000",       # 1: 開盤價
    "0.80000000",       # 2: 最高價
    "0.01575800",       # 3: 最低價
    "0.01577100",       # 4: 收盤價
    "148976.11427815",  # 5: 成交量
    1499644799999,      # 6: 收盤時間
    "2434.19055334",    # 7: 成交額
    308,                # 8: 成交筆數
    "1756.87402397",    # 9: 主動買入成交量
    "28.46694368",      # 10: 主動買入成交額
    "17928899.62484339" # 11: 忽略
  ]
]
```

### 內部信號結構

```python
signals = {
    'rsi': {
        'value': float,
        'signal': str  # 'buy' | 'sell' | 'neutral'
    },
    'ema': {
        'fast': float,
        'slow': float,
        'signal': str  # 'bullish' | 'bearish' | 'neutral'
    },
    'macd': {
        'line': float,
        'signal': float,
        'histogram': float,
        'signal': str  # 'buy' | 'sell' | 'neutral'
    },
    'volume': {
        'volume_ratio': float,
        'avg_volume': float,
        'current_volume': float,
        'cvd_trend': str,  # 'bullish' | 'bearish'
        'signal': str  # 'strong' | 'normal' | 'weak'
    },
    'multi_timeframe': {
        'timeframe': str,
        'trend': str,  # 'uptrend' | 'downtrend' | 'neutral'
        'trend_strength': float,
        'ema_20': float,
        'ema_50': float,
        'confirmation': bool
    },
    'stop_loss_take_profit': {
        'stop_loss': float,
        'take_profit_1': float,
        'take_profit_2': float,
        'risk_amount': float,
        'reward_amount': float,
        'risk_reward_ratio': float,
        'atr': float
    },
    'overall': str,  # 'strong_buy' | 'buy' | 'sell' | 'strong_sell' | 'neutral'
    'action': str,   # 中文操作建議
    'strength': int,  # 0-3
    'quality_score': float  # 0-5
}
```

---

## 前端實作

### UI組件層級

```html
<div class="container">
  <div class="header">
    <!-- 標題、版本、功能標籤 -->
  </div>

  <div class="main-grid">
    <!-- 左側：控制面板 -->
    <div class="panel">
      <div class="form-group">...</div>
      <button onclick="analyze()">分析</button>
      <div class="auto-refresh">...</div>
    </div>

    <!-- 右側：分析結果 -->
    <div class="panel result-panel">
      <!-- 順序：建議操作 → 價格/評分 → 止損止盈 → 指標詳情 -->
      <div id="results">
        <div class="action-card">...</div>
        <div class="price-display">...</div>
        <div class="sl-tp-card">...</div>
        <div class="signal-card">...</div>
      </div>
    </div>
  </div>
</div>
```

### 響應式設計

```css
/* 桌面版 (> 768px) */
.main-grid {
  display: grid;
  grid-template-columns: 350px 1fr;
  gap: 20px;
}

/* 移動版 (≤ 768px) */
@media (max-width: 768px) {
  .main-grid {
    grid-template-columns: 1fr;
  }

  .sl-tp-grid {
    grid-template-columns: 1fr;
  }
}
```

### JavaScript 核心函數

**分析函數**:
```javascript
async function analyze() {
  // 1. 獲取參數
  const params = collectFormParams();

  // 2. 顯示載入動畫
  showLoading();

  // 3. 呼叫API
  const response = await fetch(`/api/analyze?${params}`);
  const data = await response.json();

  // 4. 顯示結果
  if (data.success) {
    displayResults(data);

    // 5. 檢查是否需要通知
    if (shouldNotify(data.signals)) {
      sendNotification(data);
    }
  } else {
    showError(data.error);
  }
}
```

**通知系統**:
```javascript
function sendNotification(title, body) {
  if (!("Notification" in window)) {
    return;
  }

  if (Notification.permission === "granted") {
    new Notification(title, {
      body: body,
      icon: "📈",
      badge: "⭐",
      vibrate: [200, 100, 200],
      requireInteraction: true
    });
  } else if (Notification.permission !== "denied") {
    Notification.requestPermission().then(permission => {
      if (permission === "granted") {
        new Notification(title, { body: body });
      }
    });
  }
}
```

---

## 效能優化

### 1. 數據快取

**Binance API**:
- 每次請求100根K線（足夠計算所有指標）
- 避免重複請求相同數據

### 2. 計算優化

**避免重複計算**:
```python
# 一次計算，多次使用
closes = [float(k[4]) for k in data]
rsi = calculate_rsi(closes)
ema_fast = calculate_ema(closes, 5)
ema_slow = calculate_ema(closes, 20)
```

### 3. 前端優化

**自動刷新**:
- 10秒間隔（可配置）
- 使用 `setInterval` 而非輪詢
- 避免同時發送多個請求

**DOM更新**:
- 使用 `innerHTML` 一次性更新
- 避免多次 DOM 操作

### 4. 網路優化

**SSL驗證**:
```python
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
```
- 減少SSL驗證時間
- 適用於開發環境

---

## 安全性考量

### 1. 輸入驗證

**參數範圍檢查**:
```python
rsi_period = int(params.get('rsi_period', [14])[0])
# 前端HTML已限制範圍: min="5" max="30"
```

### 2. 錯誤處理

**API請求異常**:
```python
try:
    response = urllib.request.urlopen(req, timeout=10)
    data = json.loads(response.read().decode())
except Exception as e:
    return {'success': False, 'error': str(e)}
```

### 3. CORS設置

```python
self.send_header('Access-Control-Allow-Origin', '*')
```
- 允許跨域請求（適用於開發環境）
- 生產環境應限制特定域名

### 4. 資料清理

**防止注入**:
- 所有外部數據經過 JSON 解析
- 使用參數化查詢（如適用）
- HTML輸出經過轉義

### 5. 速率限制

**Binance API限制**:
- 重量限制：1200/分鐘
- 單一IP限制：1200請求/分鐘
- 建議：自動刷新間隔 ≥ 10秒

---

## 部署建議

### 開發環境

```bash
python3 app_v2.py
```

### 生產環境

**使用 systemd**:
```ini
[Unit]
Description=Scalping Trade Analyzer
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/scalping-trade
ExecStart=/usr/bin/python3 /opt/scalping-trade/app_v2.py
Restart=always

[Install]
WantedBy=multi-user.target
```

**使用 Docker**:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY app_v2.py .
EXPOSE 80
CMD ["python3", "app_v2.py"]
```

### 反向代理（Nginx）

```nginx
server {
    listen 80;
    server_name trading.example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 測試建議

### 單元測試

**測試RSI計算**:
```python
def test_rsi():
    prices = [100, 102, 101, 103, 105, 104, 106, 108]
    rsi = calculate_rsi(prices, period=7)
    assert 0 <= rsi <= 100
```

### 整合測試

**測試API端點**:
```bash
curl "http://localhost:80/api/analyze?symbol=BTCUSDT&interval=5m"
```

### 效能測試

**負載測試**:
```bash
ab -n 1000 -c 10 "http://localhost:80/api/analyze?symbol=BTCUSDT"
```

---

## 版本更新記錄

### V2.0 (2026-02-28)
- ✨ 成交量分析（CVD、成交量比率）
- ✨ 多時間框架確認
- ✨ 動態止損止盈（ATR）
- ✨ 信號品質評分（0-5星）
- ✨ 瀏覽器通知
- 🎨 UI優化（建議操作置頂）

### V1.0 (2026-02-26)
- 基礎技術指標（RSI、EMA、MACD）
- HTTP服務器
- 響應式UI

---

## 已知限制

1. **MACD計算簡化**: 使用簡化版信號線計算
2. **無歷史數據儲存**: 每次請求都重新計算
3. **單一數據源**: 僅依賴Binance API
4. **無認證機制**: 公開訪問（適合個人使用）
5. **無資料庫**: 所有數據即時計算

---

## 未來改進方向

1. **數據持久化**: SQLite/PostgreSQL
2. **多交易所支援**: Coinbase, Kraken, Bybit
3. **歷史回測**: 驗證策略有效性
4. **機器學習**: 優化信號評分
5. **Webhook通知**: Telegram, Discord, Email
6. **用戶認證**: 多用戶支援
7. **更多指標**: Bollinger Bands, Stochastic, Fibonacci

---

**文件版本**: 2.0
**最後更新**: 2026-02-28
**維護者**: Lewis Chan
**授權**: MIT License
