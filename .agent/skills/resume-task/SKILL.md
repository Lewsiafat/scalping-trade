---
name: resume-task
description: >
  接續 save-progress 儲存的開發進度，恢復任務上下文並繼續開發。
  Use when the user says "/resume-task", "接續進度", "恢復任務",
  "繼續任務", "繼續上次的工作", "continue task", "resume progress",
  or wants to continue from a previously saved development checkpoint.
---

# Resume Task — 接續開發進度

## Overview

從 `temp/` 目錄讀取 `save-progress` 儲存的進度檔，恢復開發上下文，讓使用者可以在新的對話中接續上次的任務。

## Workflow

### Step 1: 尋找進度檔

1. 列出 `temp/` 目錄中所有 `*.md` 檔案
2. **若找不到任何檔案：** 告知使用者「`temp/` 目錄中沒有儲存的進度，請先使用 `/save-progress` 儲存進度」，結束流程
3. **若只有一個檔案：** 直接使用該檔案
4. **若有多個檔案：** 使用 AskUserQuestion 列出所有檔案（顯示檔名和最後修改日期），讓使用者選擇要接續哪一個

### Step 2: 讀取進度內容

1. 讀取選定的進度檔，取得：
   - 分支名稱（`**分支:**` 欄位）
   - 規格摘要
   - 已完成項目清單
   - 待完成項目清單
   - 檔案變更清單
2. 從分支名稱解析 `{scope-name}`（例如 `feat/add-config-manager-system` → `add-config-manager-system`）
3. 若 `specs/{scope-name}.md` 存在，讀取作為補充參考

### Step 3: 驗證 Git 狀態

1. 執行 `git branch --show-current` 確認目前分支
2. **若分支不一致（目前分支 ≠ 進度檔記錄的分支）：**
   - 告知使用者目前在 `{current-branch}`，進度檔記錄的是 `{saved-branch}`
   - 使用 AskUserQuestion 詢問是否要切換到 `{saved-branch}`
   - 若使用者同意，執行 `git checkout {saved-branch}`
3. 執行 `git status` 掌握未提交的變更

### Step 4: 呈現上下文摘要

以清晰的格式呈現恢復的上下文：

```markdown
## 已恢復進度 — {scope-name}

**分支:** `{branch}`
**進度檔:** `{file-path}`

### 任務摘要
{規格摘要的 1-2 句話}

### 已完成 ✅
{列出已完成項目}

### 待完成 📋
{列出待完成項目}

### 未提交的變更
{來自 git status 的簡要摘要}
```

### Step 5: 引導繼續

根據「待完成」清單，提出具體的下一步建議：
- 列出待完成項目，讓使用者選擇從哪個開始
- 若所有項目都已完成，建議使用 `/finish-task` 結束任務

## Notes

- 進度檔為 `save-progress` skill 產生，格式固定（見 `save-progress` SKILL.md）
- 若使用者在 Step 1 選擇的檔案已過期（例如跨多天），提醒其確認內容是否仍符合現況
- 此 skill 不修改進度檔，只讀取用於上下文恢復
