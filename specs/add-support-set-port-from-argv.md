# feat: 支援透過命令列參數指定 Port

**分支**: feat/add-support-set-port-from-argv  
**日期**: 2026-03-02

## 描述

透過解析 `sys.argv`，讓使用者在啟動 `app_v2.py` 時可指定監聽的 port，無須修改程式碼。

## 使用方式

```bash
# 預設 port 80
python3 app_v2.py

# 指定 port（長格式）
python3 app_v2.py --port 8080

# 指定 port（短格式）
python3 app_v2.py -p 9000
```

## 修改檔案

- `app_v2.py`：新增 `import sys`，將 `PORT = 80` 替換為 `parse_port()` 函數

## 任務清單

- [x] 建立 git 分支
- [x] 設計並確認規格
- [x] 修改 `app_v2.py`（新增 `sys` import + `parse_port()` 函數）
- [x] 驗證：預設值、--port、-p、無效輸入均通過
