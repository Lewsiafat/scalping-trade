---
name: save-progress
description: >
  暫存開發進度到 temp/ 目錄。在開發任務進行中建立進度檢查點，
  記錄規格摘要和已完成/待完成項目。
  Use when the user says "/save-progress", "暫存進度", "存檔進度",
  "save progress", "checkpoint", "暫停", or wants to save current
  development progress mid-task.
---

# Save Progress — 暫存開發進度

## Overview

在 `/task` 和 `/finish-task` 之間建立進度檢查點。將目前的規格摘要、已完成項目、待完成項目寫入 `temp/` 目錄的單一 markdown 檔案，供下次對話恢復上下文。

## Workflow

### Step 1: 收集資訊

1. 取得目前分支名稱，從中解析 `{type}` 和 `{scope-name}`（例如 `feat/add-config-manager-system` → scope=`add-config-manager-system`）
2. 若在 `main` 分支上，提示錯誤：「目前在 main 分支，沒有進行中的任務」
3. 取得當天日期（YYYY-MM-DD 格式）
4. 讀取 `specs/{scope-name}.md`（若存在）作為規格參考
5. 執行 `git status` 和 `git diff main...HEAD` 掌握所有變更

### Step 2: 撰寫進度檔

1. 若 `temp/` 目錄不存在，先建立它
2. 檔名格式：`{scope-name}_{YYYY-MM-DD}.md`
3. 寫入 `temp/{scope-name}_{YYYY-MM-DD}.md`，內容結構如下：

```markdown
# {branch} — 開發進度

**分支:** `{branch}`
**日期:** {date}
**狀態:** 進行中

---

## 規格摘要

{從 spec 或分支描述整理 1-3 句話}

## 已完成

{列出已完成的項目，每項附簡要說明}

## 測試結果

| 功能 | 狀態 | 備註 |
|------|------|------|
{若有測試過的功能，列出結果}

## 待完成

{列出尚未完成的項目}

---

## 檔案變更清單

```
修改：
  {file} — {description}

新增：
  {file} — {description}
```
```

4. 若 `temp/` 中已存在同名檔案（相同 scope + 日期），覆蓋更新

### Step 3: 確認

1. 告知使用者進度檔已儲存，顯示完整檔案路徑
2. 簡要列出已完成和待完成項目的數量

## Notes

- 進度檔與 `specs/` 下的 spec/walkthrough 不同：spec 是任務開始時的規格，walkthrough 是結束時的記錄，進度檔是中間的暫存點
- 若同一天多次 `/save-progress`，後者覆蓋前者（同 scope + 同日期 = 同檔名）
- 若跨天繼續開發，會產生不同日期的檔案，皆保留
- 進度檔不需 commit，`temp/` 已在 `.gitignore` 中（或應該在）
