# feat: i18n Support (EN / ZH_TW) — Walkthrough

- **分支:** `feat/i18n-support`
- **日期:** 2026-03-05

## 變更摘要

為 Scalping Trade Analyzer Pro 加入完整的國際化（i18n）支援，預設語言為英文（EN），可切換至繁體中文（ZH_TW）。翻譯範圍涵蓋所有靜態 UI 文字與動態生成內容（分析結果、快照管理器、警報設定），確保語言切換不影響任何業務邏輯。

## 修改的檔案

- `app_v2.py` — 唯一修改文件，所有變更集中於嵌入式前端 JavaScript：
  - 新增 `LANG` 翻譯字典（`en` / `zh_TW`），共約 250+ 個翻譯鍵值
  - 在靜態 HTML 元素加上 `data-i18n` 屬性
  - 實作 `applyLang(lang)` / `switchLang(lang)` 函數
  - 新增語言切換按鈕（EN / 中文）至 header 右上角
  - 整合 `localStorage` 儲存語言偏好（預設 EN）
  - 擴充 `displayResults()` 以支援動態內容翻譯
  - 新增 `translateAction()` 函數翻譯 API 回傳的動作字串

## 技術細節

### 翻譯架構
- **靜態 UI**: 使用 `data-i18n` 屬性 + `applyLang()` 掃描更新
- **動態 HTML**: 在模板字串中直接使用 `LANG[currentLang].key`
- **API 動作字串**: 後端永遠回傳中文（`觀望 WAIT`、`強烈買入 BUY` 等），前端透過 `translateAction()` 做純顯示轉換，不修改原始值

### 功能隔離保障
`translateAction()` 為純函數，僅用於渲染層。所有依賴原始 action 字串的邏輯（快照顏色判斷、警報觸發、搜尋篩選）繼續使用中文字串，不受影響。

### Commit 記錄
| Commit | 說明 |
|--------|------|
| `ae2bba0` | feat: 靜態 UI 的 EN/ZH_TW 語言支援 |
| `ed5e379` | feat: 擴充翻譯至動態內容（SL/TP、MTF、指標卡片等） |
| `92bc6a9` | feat: 翻譯 API 動作字串（觀望/買入/賣出） |
| `e084cf0` | fix: 使用 signals.overall 判斷通知觸發條件 |
