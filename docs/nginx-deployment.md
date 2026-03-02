# 🌐 Nginx 反向代理部署指南

**適用版本**: v3.3.0+  
**最後更新**: 2026-03-02

---

## 概述

從 v3.3.0 起，應用支援 `--prefix <PATH>` 參數，讓你可以透過 nginx 將應用部署在子路徑下（如 `https://example.com/scalping/`），無需額外的 `sub_filter` 模組。

---

## 啟動應用

### 基本啟動（根路徑）

```bash
python3 app_v2.py --port 9000
# 訪問：http://localhost:9000/
```

### 子路徑部署（搭配 nginx）

```bash
python3 app_v2.py --port 9000 --prefix /scalping
# 訪問：http://localhost:9000/scalping/
```

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `--port <N>` / `-p <N>` | 指定監聽 port | `80` |
| `--prefix <PATH>` | 指定 URL 路徑前綴（不含尾斜線） | 空字串 |

---

## Nginx 設定

### 完整建議設定

```nginx
location /scalping/ {
    proxy_pass http://127.0.0.1:9000/scalping/;
    proxy_set_header Host                $host;
    proxy_set_header X-Real-IP           $remote_addr;
    proxy_set_header X-Forwarded-For     $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto   $scheme;
    proxy_http_version 1.1;
    proxy_set_header Upgrade             $http_upgrade;
    proxy_set_header Connection          "upgrade";
}
```

### 各 Header 用途說明

| Header | 作用 |
|--------|------|
| `Host` | 傳遞原始主機名稱 |
| `X-Real-IP` | 傳遞客戶端真實 IP |
| `X-Forwarded-For` | 多層代理時追蹤完整 IP 鏈 |
| `X-Forwarded-Proto` | 告知後端原始請求是 HTTP 或 HTTPS |
| `proxy_http_version 1.1` | 啟用 HTTP/1.1，支援 keep-alive 連線 |
| `Upgrade` + `Connection` | WebSocket 支援（此應用目前未使用，保留備用） |

---

## `proxy_pass` 路徑說明

```nginx
# location 路徑           proxy_pass 路徑
location /scalping/ {
    proxy_pass http://127.0.0.1:9000/scalping/;
}
```

> **重要**：`proxy_pass` 末尾必須包含 `/scalping/`，讓後端收到的完整路徑包含 prefix，才能與 Python 後端的路由判斷一致。

| 客戶端請求 | 後端收到 |
|-----------|----------|
| `GET /scalping/` | `GET /scalping/` |
| `GET /scalping/api/analyze?...` | `GET /scalping/api/analyze?...` |

---

## 完整部署範例

**步驟 1：啟動應用（建議使用 systemd 或 screen）**

```bash
python3 app_v2.py --port 9000 --prefix /scalping
```

**步驟 2：Nginx 設定（加入 server 區塊內）**

```nginx
server {
    listen 80;
    server_name example.com;

    location /scalping/ {
        proxy_pass http://127.0.0.1:9000/scalping/;
        proxy_set_header Host                $host;
        proxy_set_header X-Real-IP           $remote_addr;
        proxy_set_header X-Forwarded-For     $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto   $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade             $http_upgrade;
        proxy_set_header Connection          "upgrade";
    }
}
```

**步驟 3：重新載入 Nginx**

```bash
sudo nginx -t          # 測試設定語法
sudo nginx -s reload   # 重新載入
```

**步驟 4：訪問應用**

```
https://example.com/scalping/
```

---

## 常見問題

### Q：前端 API 請求出現 404？

確認 `--prefix` 參數與 nginx `location` 和 `proxy_pass` 路徑**三者一致**：

```bash
# ✅ 正確
python3 app_v2.py --port 9000 --prefix /scalping
# nginx: location /scalping/ → proxy_pass .../scalping/

# ❌ 錯誤（prefix 不一致）
python3 app_v2.py --port 9000 --prefix /trade
# nginx: location /scalping/ → 無法匹配
```

### Q：部署在根路徑（無子路徑）？

不需要 `--prefix` 參數，直接使用標準 nginx 反向代理即可：

```bash
python3 app_v2.py --port 9000
```

```nginx
location / {
    proxy_pass http://127.0.0.1:9000/;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
}
```
