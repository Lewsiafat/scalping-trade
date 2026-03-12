# 變更日誌

此專案的所有重要變更均記錄於此檔案中。

格式依據 [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)，
版本管理遵循 [語義化版本](https://semver.org/spec/v2.0.0.html)。
> 🌐 [English CHANGELOG](CHANGELOG.md)

## [4.2.0] - 2026-03-12

### 移除
- **PresetManager**：移除 `PresetManager` class 和 `/api/presets` endpoint。三套預設（超短線/當沖/穩健）造成參數與閾值不匹配。
- **Interval 選擇**：移除時間框架下拉選單及相關 API 參數。1m 手動下單根本來不及。
- **指標參數調整**：移除 RSI/EMA/MACD 設定 UI。參數固定並針對 5m+15m 最佳化。

### 變更
- **固定 5m 框架**：分析使用固定 5m 主框架 + 15m MTF 確認，所有評分閾值對齊此組合。
- **API 簡化**：`/api/analyze` 只需 `symbol` 參數，指標參數使用 `FIXED_PARAMS`。
- **側邊欄簡化**：僅保留交易對選擇、分析按鈕、自動刷新、進階工具。

## [4.1.0] - 2026-03-12

### 新增
- **三級 Sweep 檢測**：`detect_liquidity_sweep()` 新增 Full(+25) / Partial(+15) / Near(+8) 分類，降低 Structure Score 門檻。
- **動量趨勢延續**：`calc_momentum_score()` 新增 `trend_direction` 參數。RSI 健康區間(+10)、MACD 延續(+15)、Stoch 延續(+10)，與反轉互斥取較高分。
- **加權合分信號判定**：以 `composite = T×0.35 + S×0.40 + M×0.25` + `min_floor` 取代原本的三維硬門檻 AND 邏輯。
- **R:R 分級系統**：四級分類（good ≥1.5 / acceptable ≥1.0 / caution ≥0.7 / reject <0.7）。R:R 改用 TP1 計算。
- **評分明細面板**：前端 `<details>` 可展開面板，顯示三維評分的逐項明細。API 回傳 `score_breakdown` 欄位。
- **Composite 與 Min Floor 顯示**：三維進度條下方顯示合成分數與 R:R 等級。
- **signal_engine_b.py**：方案 B 條件累積引擎（10 個布林條件，≥5 觸發信號），供 A/B 比較測試。
- **test_signal_compare.py**：A/B 對比測試腳本，支援 `--loop` 持續刷新。

### 變更
- `calc_trend_score()`、`calc_structure_score()`、`calc_momentum_score()` 回傳值從 `int` 改為 `{'score': int, 'details': list}`。
- `calc_dynamic_sl_tp()` 新增 `rr_grade` 和 `extended_rr` 欄位。R:R 0.7-1.0 降級為預警而非完全拒絕。
- `analyze_entry_signal()` 從 BOS+EMA 推導 `trend_direction` 供動量延續評分使用。
- API 回應新增 `composite_score`、`min_floor`、`score_breakdown` 欄位。Sweep 資料含 `strength` 欄位。
- i18n：新增 `score_breakdown_title` 鍵（EN/ZH_TW）。

## [4.0.0] - 2026-03-09

### 新增
- **SMC 引擎**：Smart Money Concepts 分析 — Swing Points、Break of Structure (BOS)、Order Blocks (OB)、Fair Value Gaps (FVG)、Liquidity Sweep 檢測。
- **三維信號評分**：三維評分系統（趨勢/結構/動量，各 0-100）取代舊有 0-5 星評分。
- **兩階段信號**：預警（接近關鍵結構）→ 確認信號（三維門檻 + R:R 達標），含自動過期機制。
- **動態止損止盈**：結構錨點 SL/TP + ATR clamp(1.0, 2.5)，R:R < 1.0 拒絕信號。
- **信號標籤**：分類信號類型 — OB 反彈、Sweep 確認、FVG 支撐、指標共振。
- **三維進度條**：前端三色進度條（趨勢紫/結構金/動量綠）取代星星顯示。
- **預警 UI**：橘色漸層動作卡片，含結構接近提示訊息。
- **R:R 視覺指示**：風險報酬比顯示含狀態圖示（≥2.0 ✅ / ≥1.5 🟡 / <1.5 ⚠️）。

### 變更
- RSI 改用 Wilder's 平滑法。
- MACD 信號線改用 EMA(9)。
- Stochastic %D 改用 SMA(%K, 3)。
- EMA 預設期數改為 9/21。
- K 線請求增至 150 根，新增數據驗證層與 MTF 記憶體快取。

## [3.6.0] - 2026-03-06

### 新增
- **全域設定視窗**：在頁首新增一個由齒輪圖示觸發的集中式設定介面。
- **自訂自動刷新時間**：使用者現在能透過全域設定自訂 2 到 10 秒的分析圖表自動刷新時間。
- **警報冷卻時間控制**：新增瀏覽器通知冷卻時間設定，提供 30 秒、1 分鐘或 3 分鐘的選項。

### 變更
- 將「分析入場信號」與「自動刷新」選項從側邊的交易設定面板中移出，放置在頂部主要按鈕列，提升操作便利性。
- 放大分析功能和自動刷新的點擊區域及字體大小。
- 改善浮動視窗背景：調降背景透明度並加上毛玻璃 (`backdrop-filter`) 效果，增強閱讀性且不會透出後方圖表。

## [3.5.0] - 2026-03-05

### 新增
- **國際化 (i18n) 支援**：完整雙語切換，預設為英文（EN），可切換至繁體中文（ZH_TW）。
  - 頁首新增語言切換按鈕（EN / 中文）。
  - 所有靜態 UI 文字透過 `data-i18n` 屬性與 `applyLang()` 函數動態翻譯。
  - 動態內容完整翻譯：分析結果、止損止盈、多時間框架、成交量分析、RSI/EMA/MACD/布林通道/隨機指標/斐波那契指標。
  - 快照管理器與警報設定 Modal 全面翻譯。
  - `translateAction()` 函數將 API 回傳的中文動作字串（觀望/考慮買入/強烈買入/考慮賣出/強烈賣出）轉換為當前語言顯示。
  - 語言偏好設定儲存於 `localStorage`，頁面重載後保持選擇。
- **版本顯示機制**：新增內部版本號碼管理（`app_v2.py` 中的 `VERSION` 常數），並顯示於網頁標題與頂部標籤。

## [3.4.2] - 2026-03-04


### 修復
- 提升新增交易對時的穩定性。

## [3.4.1] - 2026-03-03

### 新增
- 功能：為瀏覽器通知增加冷卻時間機制，避免頻繁發送相同通知。

### 變更
- UX：將「添加自定義商品」與「新增警報」功能中使用的原生 `prompt()` 彈出視窗替換為美觀的 HTML Modal 對話框，提升使用者體驗與輸入驗證。

## [3.4.0] - 2026-03-03

### 新增
- 功能：自定義 UI 主題 - 實作動態 CSS 變數管理與主題切換邏輯。
- 功能：互動式排版 - 支援左側「交易設定」面板水平折收，並支援細部分析結果的垂直折收。
- UX：UI 的結構狀態 (面板折收) 自動儲存於 `localStorage` 中以維持頁面重載後的連續性。
- UI 強化：套用了「柔和極簡風格 (Soft Minimalist)」主題，帶來更舒適精緻的粉彩配色及陰影變化，並套用於按鈕、輸入框與視覺排版上。

## [3.3.1] - 2026-03-02

### 變更
- 翻譯 `README.md` 和 `CHANGELOG.md` 為英文
- 新增 `README.zh-TW.md` 及 `CHANGELOG.zh-TW.md` 作為繁體中文對照版本
- 將 `SPEC.md` 移動到 `docs/` 資料夾
- 新增 `GEMINI.md`

## [3.3.0] - 2026-03-02

### 新增
- 命令列 Port 指定：支援 `--port <N>` / `-p <N>` 參數，啟動時指定監聽端口（預設 80）
- URL 路徑前綴支援：支援 `--prefix <PATH>` 參數，讓應用可在 nginx 子路徑下正確運作（如 `/scalping`）
- 後端路由動態 PREFIX：`do_GET` / `do_POST` / `do_DELETE` 全部支援路徑前綴
- HTML 動態注入 `window.APP_PREFIX` 全域變數，前端所有 API 請求自動帶上路徑前綴

## [3.2.0-beta] - 2026-03-02

### 新增
- 即時 K 線圖表：整合 TradingView Lightweight Charts，顯示即時 K 線與技術指標覆蓋
- EMA/布林通道 overlay 時間序列：在圖表上疊加 EMA 線與布林通道帶
- 智能重試機制：API 請求支援指數退避重試（`fetch_with_retry`），依錯誤類型分類處理
- 中文錯誤訊息：結構化錯誤分類與友善中文提示（`classify_error`）
- 進度指示器：分析過程中顯示載入進度
- Toast 通知系統：取代原生 `alert()` 彈窗，提供更好的使用者體驗

### 變更
- 前端 UI 大幅改進，新增圖表區域與 Toast 通知元件
- 後端新增 `fetch_with_retry()` 和 `classify_error()` 輔助函數
- API 請求錯誤處理更加完善（HTTP 429 限速、5xx 伺服器錯誤自動重試）

## [3.1.0] - 2026-03-01

### 新增
- 快照增強：刪除功能、CSV 匯出（UTF-8 BOM）、多條件搜尋篩選
- 智能警報系統：價格/品質/信號三種警報類型，支援啟用/停用/刪除
- 參數快速預設：超短線/短線/穩健三種策略一鍵切換
- 新增 API 端點：`/api/snapshots/export`, `/api/snapshots/search`, `/api/alerts`, `/api/alert/add`, `/api/alert/toggle`, `/api/presets`

### 修復
- JavaScript 模板字符串語法錯誤
- 函數名稱不匹配問題

## [3.0.0] - 2026-03-01

### 新增
- 3大技術指標：布林通道、隨機指標、斐波那契回撤
- 策略快照管理：保存/查看歷史快照
- 自訂交易對管理：新增/刪除個人化商品清單
- 新增 API 端點：`/api/snapshots`, `/api/symbols`, `/api/snapshot/save`, `/api/symbol/add`

### 變更
- 精簡頁首高度，節省 50% 顯示空間
- 優化信號評分邏輯，納入新指標

## [2.0.0] - 2026-02-28

### 新增
- 成交量分析（CVD、成交量比率）
- 多時間框架確認
- 動態止損止盈計算（ATR）
- 信號品質評分系統（0-5 星）
- 瀏覽器通知功能

### 變更
- UI 佈局優化（建議操作置頂）

## [1.0.0] - 2026-02-26

### 新增
- 初始版本
- 基礎技術指標（RSI、EMA、MACD）
- 即時數據分析
- 響應式網頁設計
