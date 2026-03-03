# 實作側邊欄及面板折疊功能 Walkthrough

## 任務摘要
- **分支**: `feat/change-ui-behavior-hide`
- **日期**: 2026-03-03
- **Summary**: 實作了交易設定面版向左折疊的功能，並讓細部分析面版及K線圖能自由折放，所有操作狀態均記憶在瀏覽器 Local Storage 當中。

## 變更項目
- `app_v2.py`: 核心更動。
  - 新增了 `.sidebar-toggle-btn`。 
  - 調整了 `.main-grid` 使其支援 `sidebar-collapsed` 折疊類別，將包含「交易設定」的 `.sidebar` 面板動態寬度由 350px 縮減至 0px 並隱藏。
  - 調整了「K 線圖表」與「細部分析」面版，使其具有 `.collapsible-header` / `.collapsible-content` 來支援上下折疊。
  - 將 K線圖表的展開小圖示 (▼) 在 CSS 排版上將 `chart-legend` 加上 flex-grow 強制分離以解決擋住按鈕問題。
  - 實作了 JS 端 `localstorage` 的狀態記錄，以及在介面顯示與隱藏切換時觸發 `window.dispatchEvent(new Event('resize'))` 以免重整時 LightweightCharts 大小破版。
- `specs/change-ui-behavior-hide.md`: 存放當前任務的開發規格與核對項目。

## 技術細節
- 圖表重新渲染問題：圖表當其母容器處於 `display: none` 或者 `hidden` 中被繪製時會有無法取得容器面積的 bug。為了解決這項問題，加入了強制讓圖表重新 Resize 的觸發 `window.dispatchEvent(new Event('resize'))` 。
- UI 流暢度：加入了一系列 CSS `transition` 平滑動畫處理以提升使用者體驗。
