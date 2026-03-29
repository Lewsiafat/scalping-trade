# optimizer-v2-wider-search

- **Branch**: feat/optimizer-v2-wider-search
- **Date**: 2026-03-29
- **Base**: feat/backtest-feedback-loop

## 問題診斷

原始 Grid Search（2376 組合）最佳結果：
- 獲利因子 0.356，嚴重虧損
- 根本原因：5m ATR ≈ $150，atr_clamp_min=0.8 → SL ≈ $120
- 手續費 R 佔比 = 0.08% ÷ 0.15% = **0.53R / 每筆**，無法獲利

## 三個優化方向

| 方向 | 變數 | 新範圍 |
|------|------|--------|
| 1. 減少交易頻率 | strong_signal_composite | 55-75（↑ 嚴格） |
| 2. 擴大止損距離 | atr_clamp_min | 1.5-3.0（↑ 更大 SL） |
| 3. 強制更高 TP | atr_tp1_min | 1.5-2.5（↑ 更遠 TP） |

## 預期效果

- atr_clamp_min 2.0 → SL ≈ $300 → 手續費 R ≈ 0.27（從 0.53 降低）
- atr_tp1_min 2.0 → TP 至少 2R → 每次獲利更多
- 提高信號門檻 → 每天 16 筆 → 每天 3-5 筆（高品質）

## 實作清單

- [x] 修改 optimizer.py SEARCH_SPACE（3 個新方向）
- [x] 修改 backtest_engine.py evaluate_signal：實際套用 atr_clamp_min / atr_tp1_min / rr_ok
- [ ] 執行 Random Search -n 100 驗證
