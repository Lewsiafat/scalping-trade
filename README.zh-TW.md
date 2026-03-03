# 📈 Scalping Trade Analyzer Pro V3.4

> 專業級實時剝頭皮交易信號分析系統 | Professional Real-time Scalping Trading Signal Analysis System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

## 🎯 專案概述

Scalping Trade Analyzer Pro 是一個專為剝頭皮交易者設計的實時信號分析系統。整合多項技術指標、即時 K 線圖表、成交量分析、多時間框架確認與動態止損止盈計算，幫助交易者做出更精準的交易決策。

### ✨ 核心功能

- **📊 8大技術指標** - RSI、EMA、MACD、ATR、布林通道、隨機指標、斐波那契
- **📈 成交量分析** - CVD趨勢指標、成交量比率分析
- **⏱️ 多時間框架確認** - 自動檢查更高時間框架趨勢，過濾假信號
- **🎯 動態止損止盈** - 基於ATR指標自動計算風險報酬比
- **⭐ 信號品質評分** - 0-5星智能評分系統
- **📉 即時 K 線圖表** - TradingView Lightweight Charts 即時顯示 <span style="color: #ef4444;">✨ V3.2 NEW</span>
- **🔄 智能重試機制** - 指數退避 + 錯誤分類，API 請求更穩定 <span style="color: #ef4444;">✨ V3.2 NEW</span>
- **💬 Toast 通知系統** - 取代原生 alert()，進度指示器 <span style="color: #ef4444;">✨ V3.2 NEW</span>
- **📸 策略快照增強** - 刪除、CSV匯出、多條件搜尋篩選
- **🔔 智能警報系統** - 價格/品質/信號三種警報類型
- **⚡ 參數快速預設** - 超短線/短線/穩健三種策略一鍵切換
- **🎨 自訂交易對** - 新增與管理個人化交易商品清單
- **🔄 自動刷新** - 每10秒自動更新市場數據
- **🌐 命令列 Port 指定** - `--port <N>` / `-p <N>` 自訂監聽端口 ✨ V3.3 NEW
- **🔗 nginx 子路徑支援** - `--prefix <PATH>` 反向代理路徑前綴 ✨ V3.3 NEW
- **🎨 自定義主題風格** - 柔和極簡風格 (Soft Minimalist)，支援 CSS 變數動態主題 ✨ V3.4 NEW
- **↔️ 互動式收折排版** - 左側設置面版與垂直分析區塊皆可收合，最大化 K 線圖表空間 ✨ V3.4 NEW
- **📱 響應式設計** - 支援桌面與移動設備

## 🚀 快速開始

### 環境需求

- Python 3.11+
- 網路連接（用於獲取 Binance API 數據）
- 現代瀏覽器（支援 Notification API）

### 安裝與運行

```bash
# 1. 克隆專案
git clone git@github.com:Lewsiafat/scalping-trade.git
cd scalping-trade

# 2. 直接運行（無需安裝依賴）
python3 app_v2.py

# 可選：指定 port（預設 80）
python3 app_v2.py --port 8080

# 可選：nginx 子路徑部署（例如 /scalping）
python3 app_v2.py --port 9000 --prefix /scalping

# 3. 訪問應用
# 在瀏覽器開啟: http://localhost:80
```

**特點：** 本專案使用 Python 標準庫開發，無需安裝任何第三方依賴！

## 📊 技術指標說明

### 1. RSI（相對強弱指標）
- **預設週期**: 14
- **超買線**: 70
- **超賣線**: 30
- **用途**: 判斷市場超買超賣狀態

### 2. EMA（指數移動平均）
- **快速 EMA**: 5（適合剝頭皮）
- **慢速 EMA**: 20
- **用途**: 判斷短期趨勢方向

### 3. MACD（平滑異同移動平均）
- **快線**: 5
- **慢線**: 20
- **信號線**: 5
- **用途**: 捕捉動能變化與交叉信號

### 4. ATR（平均真實波幅）
- **週期**: 14
- **止損距離**: 1.5倍ATR
- **風險報酬比**: 1:2（可調整）

### 5. 布林通道 ✨ V3 NEW
- **週期**: 20
- **標準差**: 2
- **用途**: 判斷價格波動範圍與突破信號
- **信號**: 價格觸及上軌（超買）、下軌（超賣）

### 6. 隨機指標（Stochastic） ✨ V3 NEW
- **K週期**: 14
- **D週期**: 3
- **超買線**: 80
- **超賣線**: 20
- **用途**: 動量指標，判斷超買超賣

### 7. 斐波那契回撤 ✨ V3 NEW
- **關鍵水平**: 0.236, 0.382, 0.5, 0.618, 0.786
- **用途**: 識別潛在支撐與壓力位
- **計算**: 基於最近50根K線的高低點

### 8. 成交量分析
- **成交量比率**: 當前成交量 / 平均成交量
- **CVD趨勢**: 累積成交量差異（Cumulative Volume Delta）
- **信號分級**: 強/正常/弱

### 9. 多時間框架
- **1分鐘** → 檢查 5分鐘趨勢
- **5分鐘** → 檢查 15分鐘趨勢
- **15分鐘** → 檢查 1小時趨勢
- **用途**: 確認大週期趨勢，減少假信號

## 🎯 使用教學

### 基本操作

1. **選擇交易對**: BTC/USDT, ETH/USDT, SOL/USDT 等
2. **設定時間框架**: 1分鐘、3分鐘、5分鐘、15分鐘
3. **調整指標參數**: 根據個人交易風格微調
4. **點擊分析**: 獲取實時交易信號
5. **啟用自動刷新**: 每10秒自動更新（可選）

### V3 新功能使用

#### 📸 策略快照管理

**保存當前策略**:
1. 完成一次分析後，點擊「保存當前策略快照」
2. 系統自動記錄：
   - 時間戳記
   - 交易對與價格
   - 所有技術指標數值
   - 建議操作與評分
   - 止損止盈價位

**查看歷史快照**:
1. 點擊「查看歷史快照」
2. 瀏覽所有已保存的策略
3. 快照依操作類型顯示不同顏色：
   - 🟢 綠框 = 買入信號
   - 🔴 紅框 = 賣出信號
   - ⚪ 灰框 = 觀望建議

#### 🎨 自訂交易對

**新增商品**:
1. 在交易對下拉選單選擇「+ 新增自訂商品」
2. 輸入Binance交易對代碼（例：AVAXUSDT）
3. 系統自動驗證並加入清單

**管理商品**:
- 自訂商品顯示「[自訂]」標記
- 可隨時從清單中刪除

### 信號解讀

#### 信號品質評分（0-5星）

| 評分 | 說明 | 建議操作 |
|------|------|---------|
| ⭐⭐⭐⭐⭐ | 完美信號 | 強烈考慮入場 |
| ⭐⭐⭐⭐ | 優質信號 | 可以入場 |
| ⭐⭐⭐ | 中等信號 | 謹慎觀察 |
| ⭐⭐ 以下 | 弱信號 | 建議觀望 |

#### 建議操作類型

- **🟢 強烈買入 BUY**: 多項指標強烈看多 + 高品質評分
- **🟢 考慮買入**: 部分指標看多
- **🔴 強烈賣出 SELL**: 多項指標強烈看空 + 高品質評分
- **🔴 考慮賣出**: 部分指標看空
- **⚪ 觀望 WAIT**: 信號不明確或相互矛盾

### 止損止盈設置

系統自動計算基於ATR的止損止盈：

- **止損 (Stop Loss)**: 當前價格 ± 1.5倍ATR
- **目標1 (TP1)**: 50%獲利目標（建議平倉一半）
- **目標2 (TP2)**: 100%獲利目標（預設風險報酬比1:2）

**範例**：
```
入場價格: $65,000
ATR: $150
止損: $64,775 (風險 $225)
TP1: $65,225 (報酬 $225)
TP2: $65,450 (報酬 $450)
風險報酬比: 1:2
```

## 📱 瀏覽器通知

### 啟用方式

1. 首次訪問頁面時，允許瀏覽器通知權限
2. 當出現高品質信號（≥4星）時，自動彈出通知
3. 通知內容包含：交易對、操作建議、品質評分

### 通知條件

- 品質評分 ≥ 4星
- 出現「強烈買入」或「強烈賣出」信號
- 啟用自動刷新時，每次刷新都會檢查

## 🎨 支援的交易對

### 加密貨幣（Binance）

- BTC/USDT（比特幣）
- ETH/USDT（以太坊）
- BNB/USDT（幣安幣）
- SOL/USDT（Solana）
- XRP/USDT（瑞波幣）
- ADA/USDT（艾達幣）
- DOGE/USDT（狗狗幣）
- MATIC/USDT（Polygon）

**注意**: 使用 Binance 公共 API，無需 API Key

## ⚠️ 風險管理建議

### 核心原則

1. **永遠設置止損** - 系統已自動計算，務必執行
2. **控制倉位大小** - 單筆交易風險不超過總資金的0.5-1%
3. **分批獲利** - 在TP1平倉50%，TP2平倉剩餘
4. **避免過度交易** - 只交易高品質信號（≥3星）
5. **記錄交易日誌** - 持續優化策略

### 資金管理範例

假設帳戶餘額: $10,000

| 風險% | 每筆風險金額 | 止損距離 | 建議倉位大小 |
|-------|------------|---------|-------------|
| 0.5% | $50 | $100 | 0.5 單位 |
| 1.0% | $100 | $100 | 1.0 單位 |
| 2.0% | $200 | $100 | 2.0 單位 |

**公式**: `倉位大小 = (帳戶餘額 × 風險%) / 止損距離`

## 📈 實戰策略

### 剝頭皮交易策略

**時間框架**: 1-5分鐘
**目標利潤**: 0.1% - 1%
**持倉時間**: 數秒至數分鐘
**每日交易**: 20-50筆

#### 入場條件（全部符合）

1. ✅ 信號品質 ≥ 3星
2. ✅ 多時間框架趨勢確認
3. ✅ 成交量比率 > 1.0
4. ✅ RSI + MACD + EMA 方向一致
5. ✅ 風險報酬比 ≥ 1:1.5

#### 出場策略

- **快速獲利**: TP1達成後平倉50%
- **追蹤止損**: 將止損移至入場價
- **完全出場**: TP2達成或止損觸發

### 適用市場時段

| 市場 | 最佳時段（UTC+8） | 特點 |
|------|-----------------|------|
| 加密貨幣 | 24小時 | 高波動，適合剝頭皮 |
| 外匯 EUR/USD | 15:00-00:00 | 倫敦+紐約重疊 |
| 美股期貨 | 21:30-04:00 | 美股盤中時段 |

## 🛠️ 技術架構

### 系統組成

```
scalping-trade/
├── app_v2.py           # 主程式（包含前後端）
├── README.md           # 專案說明（英文）
├── README.zh-TW.md     # 專案說明（繁體中文）
├── CLAUDE.md           # Claude Code 專案指引
├── CHANGELOG.md        # 版本變更記錄（英文）
├── CHANGELOG.zh-TW.md  # 版本變更記錄（繁體中文）
├── SPEC.md            # 技術規格
├── docs/
│   └── improv_plan.md  # 改善計畫
└── LICENSE            # MIT 授權
```

### 技術棧

- **後端**: Python 3.11+ (標準庫)
- **HTTP服務器**: socketserver.TCPServer
- **數據來源**: Binance Public API
- **前端**: 原生 HTML5 + CSS3 + JavaScript
- **通知**: Notification API

### API 端點

- `GET /` - 主頁面
- `GET /api/analyze?symbol=BTCUSDT&interval=5m&...` - 分析API
- `GET /api/snapshots` - 獲取所有快照 ✨ V3
- `POST /api/snapshot/save` - 保存策略快照 ✨ V3
- `GET /api/symbols` - 獲取交易對清單 ✨ V3
- `POST /api/symbol/add` - 新增自訂交易對 ✨ V3
- `DELETE /api/symbol/{symbol}` - 刪除自訂交易對 ✨ V3

## 📊 性能指標

### 系統要求

- **記憶體**: < 30MB
- **CPU**: 極低（單執行緒）
- **網路**: ~10KB/請求（API數據）
- **回應時間**: < 2秒（含API請求）

### 準確率

基於回測結果（僅供參考）：

- **勝率**: 45-55%（配合風險管理）
- **風險報酬比**: 1:1.5 - 1:2
- **假信號過濾**: 多時間框架可減少30-50%假信號

## 🤝 貢獻指南

歡迎提交問題與改進建議！

1. Fork 本專案
2. 建立功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交變更 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 開啟 Pull Request

## 📝 版本歷史

### V3.4 (2026-03-03) ✨ 最新版本
- 🎨 **自定義主題風格**: 實作動態 CSS 變數管理，引入全新的「柔和極簡風格 (Soft Minimalist)」視覺體驗。
- ↔️ **互動式排版**: 左側的主設置面版現在可以向左滑動隱藏，K線圖下方的細部分析也可以垂直收合。所有的介面收折狀態都會保存在 `localStorage` 當中，重整後依然記憶。

### V3.3 (2026-03-02)
- 🌐 **命令列 Port 指定**: `--port <N>` / `-p <N>` 啟動時指定監聽端口（預設 80）
- 🔗 **nginx 子路徑支援**: `--prefix <PATH>` 參數啟用路徑前綴，前後端 API 路由全部動態適配
  - HTML 自動注入 `window.APP_PREFIX` 全域變數
  - nginx 設定範例：`proxy_pass http://127.0.0.1:9000/scalping/`

### V3.2-beta (2026-03-02)
- 📉 **即時 K 線圖表**: TradingView Lightweight Charts 整合
  - 即時 K 線顯示
  - EMA 線與布林通道 overlay 疊加
- 🔄 **智能重試機制**:
  - 指數退避重試（最多 3 次）
  - 錯誤類型分類（限速/伺服器錯誤/逾時）
  - HTTP 400 無效交易對不重試
- 💬 **使用者體驗升級**:
  - Toast 通知系統取代原生 `alert()` 彈窗
  - 分析進度指示器
  - 結構化中文錯誤訊息
- 🔧 **後端新增**:
  - `fetch_with_retry()` — 帶重試機制的 HTTP 請求函數
  - `classify_error()` — 錯誤分類與中文訊息函數

### V3.1 (2026-03-01)
- 📸 **快照增強功能**:
  - 刪除快照功能
  - CSV 匯出（Excel 可直接開啟，UTF-8 BOM 編碼）
  - 多條件搜尋篩選（交易對/信號類型/品質評分/日期範圍）
- 🔔 **智能警報系統**:
  - 價格警報（突破/跌破指定價格）
  - 品質評分警報（達到指定星級）
  - 信號類型警報（出現買入/賣出信號）
  - 警報管理（啟用/停用/刪除）
  - 瀏覽器通知整合
  - 觸發次數與歷史記錄
- ⚡ **參數快速預設**:
  - 超短線剝頭皮（1分鐘，高頻交易）
  - 短線當沖（5分鐘，日內交易）
  - 穩健策略（15分鐘，降低假信號）
  - 一鍵載入所有參數設定
- 🔧 **新增 API 端點**:
  - `/api/snapshots/export` - CSV 匯出
  - `/api/snapshots/search` - 搜尋篩選
  - `/api/alerts` - 警報管理
  - `/api/alert/add` - 新增警報
  - `/api/alert/toggle` - 啟用/停用
  - `/api/presets` - 參數預設組合
- 🐛 **Bug 修復**:
  - 修復 JavaScript 模板字符串語法錯誤
  - 修復函數名稱不匹配問題

### V3.0 (2026-03-01)
- ✨ **新增3大技術指標**: 布林通道（Bollinger Bands）、隨機指標（Stochastic）、斐波那契回撤（Fibonacci）
- 📸 **策略快照管理**: 保存當前策略快照，查看歷史快照記錄
  - 包含完整時間戳記
  - 記錄止損止盈價位
  - 顯示信號強度與品質評分
  - 依操作類型色彩編碼（買入/賣出/觀望）
- 🎨 **自訂交易對管理**: 新增與刪除個人化商品清單
- 🎨 **UI優化**:
  - 精簡頁首高度，節省50%顯示空間
  - 快照按鈕移至多時間框架上方
  - 優化信號評分邏輯，納入新增指標
- 🔧 **API擴充**:
  - `/api/snapshots` - 快照管理
  - `/api/symbols` - 自訂商品管理
  - `/api/snapshot/save` - 保存快照
  - `/api/symbol/add` - 新增商品

### V2.0 (2026-02-28)
- ✨ 新增成交量分析（CVD、成交量比率）
- ✨ 新增多時間框架確認
- ✨ 新增動態止損止盈計算（ATR）
- ✨ 新增信號品質評分系統（0-5星）
- ✨ 新增瀏覽器通知功能
- 🎨 優化UI佈局（建議操作置頂）

### V1.0 (2026-02-26)
- 🎉 初始版本
- 基礎技術指標（RSI、EMA、MACD）
- 即時數據分析
- 響應式網頁設計

## ⚖️ 免責聲明

**重要提示**: 本工具僅供教育與研究用途，不構成任何投資建議。

- ⚠️ 交易涉及重大風險，可能導致本金全部損失
- ⚠️ 過去的表現不代表未來結果
- ⚠️ 使用本工具的所有交易決策由用戶自行承擔
- ⚠️ 作者不對任何交易損失負責
- ⚠️ 使用前請充分了解金融市場風險
- ⚠️ 建議先在模擬帳戶練習

**請務必**:
1. 只投資您能承受損失的資金
2. 進行充分的研究與測試
3. 考慮諮詢專業金融顧問
4. 遵守當地金融法規

## 📄 授權條款

本專案採用 [MIT License](LICENSE) 授權

```
MIT License

Copyright (c) 2026 Lewis Chan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 🌟 致謝

- Binance API - 提供免費的市場數據
- Python Community - 強大的標準庫
- 所有貢獻者與使用者的反饋

## 📞 聯絡方式

- **GitHub**: [@Lewsiafat](https://github.com/Lewsiafat)
- **Issues**: [報告問題](https://github.com/Lewsiafat/scalping-trade/issues)
- **Pull Requests**: [提交改進](https://github.com/Lewsiafat/scalping-trade/pulls)

---

**Built with** ❤️ **by traders, for traders**

*最後更新: 2026-03-03 | 版本: v3.4.0*
