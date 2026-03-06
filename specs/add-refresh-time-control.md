# feat: 增加控制項調整刷新時間 (10s ~ 2s)

**Branch**: `feat/add-refresh-time-control`
**Date**: `2026-03-06`

## Description

增加控制項 可以調整reflash time from 10 ~ 2 
介面採用浮動、預先隱藏起來的介面設計。

## Task Items

- [ ] 調整 HTML：建立一個浮動、預先隱藏的介面 (例如透過一個齒輪圖示或點擊 Auto-refresh 旁邊的按鈕展開)，裡面包含更新頻率的輸入控制項 (2~10秒)。
- [ ] 實作顯示/隱藏浮動介面的 JavaScript 邏輯 (包含點擊外部關閉等 UX 優化)。
- [ ] 修改 `toggleAutoRefresh()`，讓它根據控制項的值來設定 `setInterval`。
- [ ] 增加事件監聽 (onchange/oninput)，當秒數改變時，若自動更新運行中，即時自動重設計時器。
- [ ] 更新中／英文的 UI 語言檔 (修改 `auto_refresh` 相關鍵值以及新增控制項介面的翻譯)。
- [ ] 手動測試功能是否正確運作 (切換秒數是否生效、浮動介面行為是否正常、API 請求是否會頻率異常等)。
