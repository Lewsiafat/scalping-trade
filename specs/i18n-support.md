# feat: i18n Support (EN / ZH_TW)

- **分支:** `feat/i18n-support`
- **日期:** 2026-03-05

## 描述
為前端 UI 新增多語言支援（i18n）。預設語言為英文（EN），使用者可切換至繁體中文（ZH_TW）。語言偏好透過 `localStorage` 持久化，無須後端配合。

## 技術設計
- 在前端 JS 中建立 `LANG` 翻譯字典（包含 `en` 和 `zh_TW` 兩組）
- 所有靜態 UI 文字元素加上 `data-i18n="key"` 屬性
- `applyLang(lang)` 函數負責遍歷並替換文字內容
- 右上角新增 EN / 中文 語言切換按鈕
- 預設語言為 `en`，使用者切換後儲存至 `localStorage`
- 動態 API 回傳的分析文字（訊號說明等）**暫不處理**

## 任務清單
- [ ] 建立 `LANG` 翻譯字典（en / zh_TW）
- [ ] 為所有靜態 UI 元素加上 `data-i18n` 屬性
- [ ] 實作 `applyLang()` 函數
- [ ] 加入語言切換按鈕（EN / 中文）
- [ ] 整合 `localStorage` 語言偏好，預設 EN
- [ ] 測試切換與持久化行為
