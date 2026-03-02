# Walkthrough: feat/add-support-path-prefix

**分支**: feat/add-support-path-prefix  
**日期**: 2026-03-02  
**Commit**: `cee68fa`

## 摘要

新增 `--prefix <PATH>` 命令列參數支援，讓應用可在 nginx 子路徑（如 `/scalping`）下正確運作，無需 nginx `sub_filter`。前後端均支援動態路徑前綴。

## 變更檔案

| 檔案 | 說明 |
|------|------|
| `app_v2.py` | 新增 `parse_prefix()` 函數、後端路由加上 PREFIX、HTML 注入 `window.APP_PREFIX`、前端 13 處 fetch 更新 |
| `specs/add-support-path-prefix.md` | 任務規格文件 |

## 技術細節

- `parse_prefix()` 使用 `sys.argv` 解析 `--prefix` 參數，自動正規化（去除尾斜線、補前斜線）
- 後端 `do_GET` / `do_POST` / `do_DELETE` 路由全部加上 `PREFIX` 前綴，`PREFIX=""` 時行為與原版完全相同
- 回傳 HTML 時動態替換 `<head>` 注入 `<script>window.APP_PREFIX = "...";</script>`
- 前端 JS 宣告 `const APP_PREFIX = window.APP_PREFIX || ''` 作為 fallback，確保即使注入失敗也不會爆錯

## 測試驗證

| 情境 | 結果 |
|------|------|
| 預設（無 prefix）→ `PORT=80, PREFIX=""` | ✅ |
| `--port 9000 --prefix /scalping` → 路由正確 | ✅ |
| `/scalping/api/analyze` → API handler | ✅ |
| `/api/analyze`（無 prefix，錯誤請求）→ 404 | ✅ |
| HTML 注入 `window.APP_PREFIX = "/scalping"` | ✅ |
| 前端 13 處 fetch 均含 APP_PREFIX（0 個漏網）| ✅ |

## Nginx 使用範例

```nginx
location /scalping/ {
    proxy_pass http://127.0.0.1:9000/scalping/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```
