# Walkthrough: feat/add-support-set-port-from-argv

**分支**: feat/add-support-set-port-from-argv  
**日期**: 2026-03-02  
**Commit**: `95c1a68`

## 摘要

新增 `parse_port()` 函數，讓使用者可透過 `--port <N>` 或 `-p <N>` 命令列參數指定伺服器監聽的 port，無需修改程式碼。向下相容，預設仍為 port 80。

## 變更檔案

| 檔案 | 說明 |
|------|------|
| `app_v2.py` | 新增 `import sys` 及 `parse_port()` 函數，取代硬編碼 `PORT = 80` |
| `specs/add-support-set-port-from-argv.md` | 任務規格文件 |

## 技術細節

- 使用 `sys.argv` 手動解析，不引入 `argparse`，維持「無第三方依賴」原則
- 支援 `--port <N>` 長格式與 `-p <N>` 短格式
- 無效輸入（非整數或超出 1–65535 範圍）印出中文錯誤訊息並 `sys.exit(1)`
- 預設值 80，完全向下相容

## 測試驗證

| 情境 | 指令 | 結果 |
|------|------|------|
| 預設 | `python3 app_v2.py` | PORT = 80 ✅ |
| 長格式 | `python3 app_v2.py --port 8080` | PORT = 8080 ✅ |
| 短格式 | `python3 app_v2.py -p 9000` | PORT = 9000 ✅ |
| 無效輸入 | `python3 app_v2.py --port abc` | 印出錯誤，exit 1 ✅ |
