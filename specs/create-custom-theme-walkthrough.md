# 建立新主題 (create-custom-theme) — Walkthrough

- **分支:** `feat/create-custom-theme`
- **日期:** 2026-03-03

## 變更摘要
使用 `theme-factory` 建立了一個名為 "Soft Minimalist" 的柔和簡約主題，並將其色彩、字體變數成功導入 `app_v2.py` 的前端模板中。主背景改為溫潤米白（Oatmeal），按鈕移除高飽和度，變更為主副按鈕分明之極簡邊框風格（Ghost Buttons）。

## 修改的檔案
- `app_v2.py`: 
  - 導入 Google Fonts (`Lora` 與 `Nunito`)。
  - 新增 CSS 變數區塊定義主題顏色群 (`--color-bg`, `--color-buy` 等)。
  - 修正所有次要 `<button>` 樣式為 outline 邊框風格，僅保留分析按鈕為實色。
- `.agent/skills/theme-factory/themes/soft-minimalist.md`:
  - 產出的 Soft Minimalist 主題規格紀錄。
- `specs/create-custom-theme.md`:
  - 任務初始規格與代辦事項。

## 技術細節
- **顏色變數替換**: 將所有原本寫死在 HTML 字串、內聯樣式 (`style="background: #10b981;"`) 的 Hex 色碼替換成彈性的 CSS `var(--color-...)` 變量。
- **次要按鈕降級**: 發現原本的實色按鈕會過度吸引注意力，破壞極簡風格。故將多數次要功能調整為 `background: var(--color-bg); border: 1px solid var(--color-border);` 等設定的 Ghost UI 設計。
