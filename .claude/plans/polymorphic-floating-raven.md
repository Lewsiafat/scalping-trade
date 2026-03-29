# Backtest Feedback Loop v2 — Full Rewrite

## Context

The current backtest system (on `feat/backtest-feedback-loop` branch) has fundamental bugs that make optimization meaningless:

1. **SL/TP params disconnected** — `calc_dynamic_sl_tp()` (app_v3.py:1679) hardcodes ATR×1.0/2.5 and R:R 0.7/1.0/1.5. The `backtest_params.json` fields (`atr_clamp_min`, `rr_ok`, etc.) are never passed through. The optimizer tunes dead knobs.
2. **Volume analysis disabled** — backtest passes `volume_analysis=None`, killing 25/100 momentum points.
3. **MTF always neutral** — `MTF_NEUTRAL` stub means ±25 trend points are dead.
4. **prev_histogram=None** — MACD crossover detection (+20 momentum points) disabled.
5. **Only 7/60+ params searched** — scoring weights fixed, no walk-forward validation.

**Result**: Best found = profit_factor 0.77, -44R P&L. Strategy can't be profitable with broken signals.

**Goal**: Rewrite backtest + optimizer to produce signals matching live quality, then optimize smarter entry signals with overfitting protection.

---

## Phase 1: Fix Signal Fidelity in `backtest_engine.py` (Full Rewrite)

### 1a. Restore volume analysis
- Call `ScalpingAnalyzerPro.analyze_volume(window)` instead of passing `None`
- Kline data already has volume (index 5) and taker_buy_vol (index 9)

### 1b. Synthesize MTF from 5m data
New helper `synthesize_mtf(klines_5m, ema_fast=20, ema_slow=50)`:
- Group 5m bars into 15m candles by `open_time // (15*60*1000)`
- Merge: open=first.open, high=max, low=min, close=last.close, volume=sum
- Compute EMA(20)/EMA(50) on 15m closes
- Return dict matching `multi_timeframe_analysis()` format
- Increase `rolling_window` default to 200 (gives ~66 15m candles for stable EMA50)

### 1c. Fix prev_histogram
```python
_, _, prev_histogram = ScalpingAnalyzerPro.calculate_macd(
    closes[:-1], fp["macd_fast"], fp["macd_slow"], fp["macd_signal"]
)
```

### 1d. SL/TP param passthrough wrapper
New helper `_apply_sl_tp_overrides(sl_tp, params, signal_type, price, atr)`:
- Post-process `calc_dynamic_sl_tp()` output (no app_v3.py changes)
- Enforce `atr_clamp_min` / `atr_clamp_max` on SL distance
- Enforce `atr_tp1_min` on TP1 distance
- Recompute R:R, apply `rr_reject` / `rr_ok` / `rr_good` from params

### 1e. Enhanced `evaluate_signal()`
- Use all fixes above (volume, MTF, prev_histogram, SL/TP wrapper)
- Read scoring weights from params (not hardcoded 0.35/0.40/0.25)
- Read all signal thresholds from params
- Support `strong_only` and `long_only` filters

### 1f. Enhanced summary
- Add `pnl_list` (all trade R values) for Sharpe calculation
- Add `max_drawdown_r` (equity curve peak-to-trough)
- Add `avg_win_r` / `avg_loss_r`

**Files**: `backtest_engine.py` (rewrite ~700 lines)

---

## Phase 2: Optimizer v2 (`optimizer.py` Full Rewrite)

### 2a. Expanded search space (~18 params)

**Tier 1 — Scoring Weights (2 independent + 1 derived)**
- `weight_trend`: [0.25, 0.30, 0.35, 0.40]
- `weight_structure`: [0.30, 0.35, 0.40, 0.45]
- `weight_momentum` = 1.0 - wt - ws (must be 0.10-0.40)

**Tier 2 — Signal Thresholds (4)**
- `strong_signal_composite`: [55, 60, 65, 70]
- `strong_signal_min_floor`: [25, 30, 35, 40]
- `normal_signal_composite`: [40, 45, 50]
- `normal_signal_min_floor`: [15, 20, 25, 30]

**Tier 3 — SL/TP ATR multipliers (4)**
- `atr_clamp_min`: [1.0, 1.5, 2.0, 2.5]
- `atr_clamp_max`: [2.5, 3.0, 3.5]
- `atr_tp1_min`: [1.5, 2.0, 2.5, 3.0]
- `atr_sl_fallback`: [1.5, 2.0]

**Tier 4 — R:R Thresholds (3)**
- `rr_reject`: [0.5, 0.7]
- `rr_ok`: [0.8, 1.0, 1.2]
- `rr_good`: [1.5, 2.0]

**Tier 5 — Trade Management (2)**
- `max_hold_bars`: [0, 12, 20, 30]
- `strong_only`: [true, false]

**Constraints**: strong > normal, clamp_min < clamp_max, rr_reject < rr_ok < rr_good, weight_momentum >= 0.10

### 2b. Walk-forward validation
- Split 90-day data: train 60 days / test 30 days
- Run backtest on both splits per combo
- Score = `train_score * 0.3 + test_score * 0.7` with divergence penalty
- If train >> test (overfitting), score penalized up to 50%
- If test profitable but train not, still penalized (inconsistent)

### 2c. New scoring function
```
expectancy = avg_rr * 10                              (0-3 range)
pf_norm = min(profit_factor, 3.0) / 3.0              (0-1 range)
sharpe_r = mean(pnl_list) / std(pnl_list)            (0-2 capped)
combined = expectancy*0.35 + pf*0.25 + sharpe*0.25 + wr*0.15
final = combined * sample_factor * drawdown_penalty * consec_loss_penalty
```

### 2d. Search modes
- `--mode random -n 300` (default): random combos with constraint filtering
- `--mode hill`: seed from top-5 random results, greedy local optimization
- `--mode two-stage`: coarse random (100) → narrow fine search (200) around top params

### 2e. Output
- `backtest_history/optimizer_v2_{ts}.json` with train/test metrics per combo
- Auto-update `backtest_params.json` with best walk-forward-validated params
- Console: top-5 results table with train/test comparison

**Files**: `optimizer.py` (rewrite ~500 lines)

---

## Phase 3: Supporting Updates

### 3a. `backtest_params.json` — restructure
Add new fields: `mtf_ema_fast`, `mtf_ema_slow`, `walk_forward_enabled`, `walk_forward_train_ratio`. Update `rolling_window` default to 200.

### 3b. `data_fetcher.py` — minor update
- Default `--days 90`
- Add `--validate` flag for data integrity check
- Keep existing logic

### 3c. `history_viewer.py` — minor update
- Show train/test split boundary
- Color-code trades by period

---

## Implementation Order

1. `backtest_engine.py` — full rewrite with signal fixes
2. Run once with current params to verify signals are now richer (expect different results)
3. `optimizer.py` — full rewrite with walk-forward + expanded search
4. `backtest_params.json` — update schema
5. `data_fetcher.py` — minor update
6. `history_viewer.py` — minor update
7. Run optimizer, compare v1 vs v2 results

## Key Files to Modify

| File | Lines | Action |
|------|-------|--------|
| `backtest_engine.py` | 622→~700 | Full rewrite |
| `optimizer.py` | 419→~500 | Full rewrite |
| `backtest_params.json` | ~70 | Restructure |
| `data_fetcher.py` | 296 | Minor update (default days) |
| `history_viewer.py` | 587 | Minor update (split viz) |
| `app_v3.py` | 5563 | **No changes** (wrapper approach) |

## Verification

1. **Signal fidelity**: Run backtest with fixed signals, verify momentum scores now reach 60-100 (vs ~45 max before), trend scores show full range 0-100 (vs ~35-65 before)
2. **SL/TP passthrough**: Change `atr_clamp_min` in params, verify SL distances actually change in trade output
3. **Walk-forward**: Verify train/test split produces two separate summaries with different metrics
4. **Optimizer**: Run 300 random combos, confirm best walk-forward score > 0 (positive expectancy on test set)
5. **End-to-end**: Best params should show profit_factor > 1.0 on test set (unseen data)
