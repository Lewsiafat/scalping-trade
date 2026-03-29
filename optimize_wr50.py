#!/usr/bin/env python3
"""快速優化: 目標 >50% WR + 足夠交易量（多進程版）"""
import random, copy, os, sys, time, json, math, multiprocessing

sys.path.insert(0, os.path.dirname(__file__))
from backtest_engine import (
    run_backtest, load_history, load_params, list_history_files,
    precompute_indicators, log
)
from optimizer import split_data, _slim_summary

# ─── 評分：重點 = test profitable + 足夠交易量 + WR > 50% ──────────────────

def score_v3(train_s, test_s):
    if test_s["total_trades"] < 5:
        return -999.0
    if test_s.get("total_pnl_r", 0) <= 0:
        return -100.0

    pf = min(test_s.get("profit_factor", 0), 5.0)
    wr = test_s.get("win_rate", 0) / 100.0
    avg_rr = test_s.get("avg_rr", 0)
    pnl_list = test_s.get("pnl_list", [])

    # WR bonus (want >50%)
    wr_score = wr * 2 if wr > 0.5 else wr * 0.3

    # Trade count: want 15+ on test
    trade_factor = min(1.0, test_s["total_trades"] / 15.0)

    # Consistency (Sharpe-like)
    if pnl_list and len(pnl_list) > 1:
        mean_r = sum(pnl_list) / len(pnl_list)
        var_r = sum((x - mean_r) ** 2 for x in pnl_list) / (len(pnl_list) - 1)
        sharpe = mean_r / (var_r ** 0.5) if var_r > 0 else 0
        consistency = max(0, min(2.0, sharpe))
    else:
        consistency = 0

    raw = (avg_rr * 5 + pf / 3.0 + wr_score + consistency * 0.5) * trade_factor

    # Train consistency bonus
    if train_s.get("profit_factor", 0) > 1.0:
        raw *= 1.3
    elif train_s.get("win_rate", 0) > 45:
        raw *= 1.1

    return round(raw, 4)


# ─── 搜尋空間（放寬門檻以獲更多交易）──────────────────────────────────────────

SPACE = {
    "weight_trend":             [0.25, 0.30, 0.35, 0.40],
    "weight_structure":         [0.30, 0.35, 0.40, 0.45],
    "strong_signal_composite":  [50, 55, 60, 65],
    "strong_signal_min_floor":  [20, 25, 30, 35],
    "normal_signal_composite":  [35, 40, 45],
    "normal_signal_min_floor":  [10, 15, 20, 25],
    "atr_clamp_min":            [1.0, 1.5, 2.0],
    "atr_clamp_max":            [2.5, 3.0, 3.5],
    "atr_tp1_min":              [1.5, 2.0, 2.5],
    "atr_sl_fallback":          [1.5, 2.0],
    "rr_reject":                [0.5, 0.7],
    "rr_ok":                    [0.8, 1.0],
    "rr_good":                  [1.5, 2.0],
    "max_hold_bars":            [0, 16, 24, 32],
    "strong_only":              [False, True],
}


def gen_combo(base):
    for _ in range(100):
        c = {k: random.choice(v) for k, v in SPACE.items()}
        wm = round(1.0 - c["weight_trend"] - c["weight_structure"], 2)
        if wm < 0.10 or wm > 0.40:
            continue
        c["weight_momentum"] = wm
        if c["strong_signal_composite"] <= c["normal_signal_composite"]:
            continue
        if c["strong_signal_min_floor"] <= c["normal_signal_min_floor"]:
            continue
        if c["atr_clamp_min"] >= c["atr_clamp_max"]:
            continue
        if c["rr_reject"] >= c["rr_ok"] or c["rr_ok"] >= c["rr_good"]:
            continue
        merged = copy.deepcopy(base)
        merged.update(c)
        return merged
    return None


def worker_batch(args):
    """Worker: precompute once, run all combos in batch"""
    train_kl, test_kl, combos, symbol, base_params = args
    train_pre = precompute_indicators(train_kl, base_params)
    test_pre = precompute_indicators(test_kl, base_params)

    results = []
    for combo in combos:
        tr = run_backtest(train_kl, combo, symbol, quiet=True, precomputed=train_pre)
        te = run_backtest(test_kl, combo, symbol, quiet=True, precomputed=test_pre)
        sc = score_v3(tr["summary"], te["summary"])
        results.append({
            "params": combo,
            "score": sc,
            "train": _slim_summary(tr["summary"]),
            "test": _slim_summary(te["summary"]),
        })
    return results


def main():
    N = 500
    fpath = list_history_files()[0]
    hist = load_history(fpath)
    klines = hist["klines"]
    base = load_params()
    symbol = hist.get("symbol", "BTCUSDT")

    train_kl, test_kl = split_data(klines, 0.667)
    log(f"{symbol} | train={len(train_kl):,} | test={len(test_kl):,}")

    # Generate combos
    combos = []
    for _ in range(N * 10):
        c = gen_combo(base)
        if c:
            combos.append(c)
        if len(combos) >= N:
            break
    log(f"Generated {len(combos)} combos")

    # Multiprocessing
    n_workers = max(1, (os.cpu_count() or 4) - 2)
    batches = [[] for _ in range(n_workers)]
    for i, c in enumerate(combos):
        batches[i % n_workers].append(c)

    log(f"Running {n_workers} workers...")
    t0 = time.perf_counter()

    worker_args = [
        (train_kl, test_kl, batch, symbol, base)
        for batch in batches if batch
    ]
    with multiprocessing.Pool(processes=n_workers) as pool:
        batch_results = pool.map(worker_batch, worker_args)

    results = []
    for batch in batch_results:
        results.extend(batch)

    t1 = time.perf_counter()
    log(f"Done: {len(results)} combos in {t1 - t0:.1f}s")

    results.sort(key=lambda x: x["score"], reverse=True)

    # Show top 5
    print(f"\n{'='*70}")
    print(f"  TOP 5 RESULTS (target: WR>50% + enough trades)")
    print(f"{'='*70}")
    for rank, r in enumerate(results[:5], 1):
        tr, te = r["train"], r["test"]
        p = r["params"]
        print(f"\n  #{rank}  score={r['score']:.3f}")
        print(f"  Train: {tr['total_trades']:>4}t  WR={tr['win_rate']:>5.1f}%  "
              f"PF={tr['profit_factor']:.2f}  PnL={tr['total_pnl_r']:>+7.1f}R  "
              f"MaxDD={tr.get('max_drawdown_r',0):>+6.1f}R")
        print(f"  Test:  {te['total_trades']:>4}t  WR={te['win_rate']:>5.1f}%  "
              f"PF={te['profit_factor']:.2f}  PnL={te['total_pnl_r']:>+7.1f}R  "
              f"MaxDD={te.get('max_drawdown_r',0):>+6.1f}R")
        print(f"  Params: wt={p['weight_trend']} ws={p['weight_structure']} wm={p['weight_momentum']}")
        print(f"          strong_comp={p['strong_signal_composite']} floor={p['strong_signal_min_floor']} "
              f"normal_comp={p['normal_signal_composite']} nfloor={p['normal_signal_min_floor']}")
        print(f"          clamp=[{p['atr_clamp_min']},{p['atr_clamp_max']}] tp1={p['atr_tp1_min']} "
              f"rr=[{p['rr_reject']},{p['rr_ok']},{p['rr_good']}] hold={p['max_hold_bars']} "
              f"strong_only={p['strong_only']}")

    # Save best
    best = results[0]
    with open("backtest_params.json", "w") as f:
        json.dump(best["params"], f, indent=2, ensure_ascii=False)
    log("Saved best params to backtest_params.json")

    # Also save full results
    with open(os.path.join("backtest_history", f"optimize_wr50_{time.strftime('%Y%m%d_%H%M%S')}.json"), "w") as f:
        json.dump({
            "target": "WR>50% with more trades",
            "total_combos": len(results),
            "top10": results[:10],
        }, f, indent=2, ensure_ascii=False)
    log("Results saved to backtest_history/")


if __name__ == "__main__":
    main()
