# feat: 支援透過 --prefix 參數指定 URL 路徑前綴

**分支**: feat/add-support-path-prefix  
**日期**: 2026-03-02

## 描述

支援透過 `--prefix <PATH>` 命令列參數指定 URL 路徑前綴，讓應用可正確在 nginx 子路徑下運作（如 `/scalping`）。

## 使用方式

```bash
python3 app_v2.py --port 9000 --prefix /scalping
```

## Nginx 設定範例

```nginx
location /scalping/ {
    proxy_pass http://127.0.0.1:9000/scalping/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

## 修改檔案

- `app_v2.py`：
  1. 新增 `parse_prefix()` → `PREFIX` 全域變數
  2. `do_GET` / `do_POST` / `do_DELETE` 路由加上 `PREFIX`
  3. 回傳 HTML 時注入 `window.APP_PREFIX`
  4. 前端 13 處 `fetch('/api/...')` 改用 `APP_PREFIX + '/api/...'`

## 任務清單

- [x] 建立 git 分支
- [x] 設計並確認規格
- [x] 實作 `parse_prefix()` 函數
- [x] 修改後端路由加上 PREFIX
- [x] HTML 注入 `window.APP_PREFIX`
- [x] 前端 fetch 全部更新（13 處）
- [x] 驗證測試通過
