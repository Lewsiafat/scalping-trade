#!/usr/bin/env python3
"""
optimizer.py — 自動參數優化器 v2
Scalping Trade Analyzer Pro — Backtest Feedback Loop v2

用法:
    python3 optimizer.py                              # 隨機搜尋 300 次 + walk-forward
    python3 optimizer.py -f history/BTCUSDT_5m_*.json
    python3 optimizer.py --mode random -n 500
    python3 optimizer.py --mode hill                  # 爬山法
    python3 optimizer.py --mode two-stage             # 粗搜 + 精搜
    python3 optimizer.py --no-walkforward             # 停用 walk-forward

v2 改進:
    - 搜尋空間擴展至 ~18 個參數（含評分權重、SL/TP、R:R）
    - Walk-forward 驗證（train/test 分割，防過擬合）
    - 新評分函式（期望值 + Sharpe + 獲利因子 + 勝率）
    - Two-stage 搜尋（粗搜 → 精搜）
"""

import json
import os
import sys
import copy
import math
import random
import argparse
import multiprocessing
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from backtest_engine import (
    run_backtest, load_params, load_history, list_history_files, save_results,
    precompute_indicators, log
)

# ─── 搜尋空間定義 ─────────────────────────────────────────────────────────────

SEARCH_SPACE = {
    # Tier 1: 評分權重（weight_momentum = 1 - wt - ws，自動推導）
    "weight_trend":             [0.25, 0.30, 0.35, 0.40],
    "weight_structure":         [0.30, 0.35, 0.40, 0.45],

    # Tier 2: 信號門檻
    "strong_signal_composite":  [55, 60, 65, 70],
    "strong_signal_min_floor":  [25, 30, 35, 40],
    "normal_signal_composite":  [40, 45, 50],
    "normal_signal_min_floor":  [15, 20, 25, 30],

    # Tier 3: SL/TP ATR 倍數
    "atr_clamp_min":            [1.0, 1.5, 2.0, 2.5],
    "atr_clamp_max":            [2.5, 3.0, 3.5],
    "atr_tp1_min":              [1.5, 2.0, 2.5, 3.0],
    "atr_sl_fallback":          [1.5, 2.0],

    # Tier 4: R:R 門檻
    "rr_reject":                [0.5, 0.7],
    "rr_ok":                    [0.8, 1.0, 1.2],
    "rr_good":                  [1.5, 2.0],

    # Tier 5: 交易管理
    "max_hold_bars":            [0, 12, 20, 30],
    "strong_only":              [True, False],
}

PARAMS_FILE      = "backtest_params.json"
PARAMS_BEST_FILE = "backtest_params_best.json"
BACKTEST_DIR     = "backtest_history"

# ─── 參數組合生成 ──────────────────────────────────────────────────────────────

def generate_valid_combo(base_params: dict) -> dict:
    """生成一個有效的隨機參數組合

    約束:
    - weight_momentum = 1.0 - wt - ws，且 >= 0.10
    - strong_signal > normal_signal
    - atr_clamp_min < atr_clamp_max
    - rr_reject < rr_ok < rr_good
    """
    for _ in range(100):
        combo = {k: random.choice(v) for k, v in SEARCH_SPACE.items()}

        # 權重約束
        wm = round(1.0 - combo["weight_trend"] - combo["weight_structure"], 2)
        if wm < 0.10 or wm > 0.40:
            continue
        combo["weight_momentum"] = wm

        # 門檻排序約束
        if combo["strong_signal_composite"] <= combo["normal_signal_composite"]:
            continue
        if combo["strong_signal_min_floor"] <= combo["normal_signal_min_floor"]:
            continue

        # ATR clamp 約束
        if combo["atr_clamp_min"] >= combo["atr_clamp_max"]:
            continue

        # R:R 約束
        if combo["rr_reject"] >= combo["rr_ok"]:
            continue
        if combo["rr_ok"] >= combo["rr_good"]:
            continue

        # 合併為完整 params
        merged = copy.deepcopy(base_params)
        merged.update(combo)
        return merged

    return None


def generate_neighbor(params: dict, base_params: dict) -> dict:
    """生成鄰居參數（爬山法用）：隨機修改 1-2 個參數"""
    neighbor = copy.deepcopy(params)
    keys_to_tweak = random.sample(list(SEARCH_SPACE.keys()), min(2, len(SEARCH_SPACE)))

    for key in keys_to_tweak:
        neighbor[key] = random.choice(SEARCH_SPACE[key])

    # 重新推導 weight_momentum
    wm = round(1.0 - neighbor["weight_trend"] - neighbor["weight_structure"], 2)
    if wm < 0.10 or wm > 0.40:
        return None
    neighbor["weight_momentum"] = wm

    # 約束檢查
    if neighbor["strong_signal_composite"] <= neighbor["normal_signal_composite"]:
        return None
    if neighbor["strong_signal_min_floor"] <= neighbor["normal_signal_min_floor"]:
        return None
    if neighbor["atr_clamp_min"] >= neighbor["atr_clamp_max"]:
        return None
    if neighbor["rr_reject"] >= neighbor["rr_ok"] or neighbor["rr_ok"] >= neighbor["rr_good"]:
        return None

    return neighbor


# ─── 評分函式 ─────────────────────────────────────────────────────────────────

def score_result(summary: dict) -> float:
    """v2 綜合評分（越高越好）

    組成:
    1. 期望值 (avg_rr) — 0.35 權重，Scalping 最重要
    2. 獲利因子 — 0.25 權重
    3. 一致性 (Sharpe-like) — 0.25 權重
    4. 勝率 — 0.15 權重
    再乘以樣本充足度、回撤懲罰、連虧懲罰
    """
    total = summary.get("total_trades", 0)
    if total < 10:
        return -999.0

    pf      = summary.get("profit_factor", 0)
    wr      = summary.get("win_rate", 0) / 100.0
    avg_rr  = summary.get("avg_rr", 0)
    max_dd  = summary.get("max_drawdown_r", 0)
    max_consec = summary.get("max_consecutive_loss", 999)
    pnl_list = summary.get("pnl_list", [])

    # 1. 期望值
    expectancy = max(0, avg_rr * 10)  # 0.1R → 1.0 分

    # 2. 獲利因子（封頂 3.0）
    pf_norm = min(pf, 3.0) / 3.0

    # 3. 一致性（Sharpe-like）
    if pnl_list and len(pnl_list) > 1:
        mean_r = sum(pnl_list) / len(pnl_list)
        var_r = sum((x - mean_r) ** 2 for x in pnl_list) / (len(pnl_list) - 1)
        std_r = math.sqrt(var_r) if var_r > 0 else 0
        sharpe = mean_r / std_r if std_r > 0 else 0
        consistency = max(0, min(2.0, sharpe))
    else:
        consistency = 0

    # 4. 加權合分
    raw = (expectancy * 0.35 +
           pf_norm * 0.25 +
           consistency * 0.25 +
           wr * 0.15)

    # 5. 樣本充足度（30+ 筆滿分）
    sample_factor = min(1.0, total / 30.0)

    # 6. 回撤懲罰（> 5R 開始扣分）
    dd_penalty = max(0.3, 1.0 - max(0, max_dd - 5) * 0.05)

    # 7. 連虧懲罰（> 5 次開始扣分）
    consec_penalty = max(0.5, 1.0 - max(0, max_consec - 5) * 0.08)

    return round(raw * sample_factor * dd_penalty * consec_penalty, 4)


def walk_forward_score(train_summary: dict, test_summary: dict) -> float:
    """Walk-forward 綜合評分

    train 佔 30%，test 佔 70%。
    若 train >> test（過擬合），加懲罰。
    若 test 虧損，重罰。
    """
    train_s = score_result(train_summary)
    test_s  = score_result(test_summary)

    # 無效結果
    if train_s <= -900 or test_s <= -900:
        if test_s <= -900:
            return -999.0
        return train_s * 0.1

    # 過擬合懲罰
    if train_s > 0 and test_s > 0:
        divergence = abs(train_s - test_s) / max(train_s, test_s)
        penalty = max(0.5, 1.0 - divergence * 0.5)
    elif test_s <= 0 < train_s:
        penalty = 0.2  # 訓練獲利但測試虧損 → 嚴重過擬合
    else:
        penalty = 1.0

    combined = train_s * 0.3 + test_s * 0.7
    return round(combined * penalty, 4)


# ─── Walk-Forward 分割 ────────────────────────────────────────────────────────

def split_data(klines: list, train_ratio: float = 0.667) -> tuple:
    """將 K 線資料分割為 train / test 兩段

    分割點對齊到日邊界（UTC 00:00）避免不完整的交易日。
    回傳 (train_klines, test_klines)
    """
    split_idx = int(len(klines) * train_ratio)

    # 對齊到日邊界
    day_ms = 24 * 3600 * 1000
    if split_idx < len(klines):
        split_time = int(klines[split_idx][0])
        day_start = split_time - (split_time % day_ms) + day_ms  # 下一個 UTC 0:00
        while split_idx < len(klines) and int(klines[split_idx][0]) < day_start:
            split_idx += 1

    train = klines[:split_idx]
    test  = klines[split_idx:]
    return train, test


# ─── 搜尋模式 ─────────────────────────────────────────────────────────────────

def _worker_batch(args: tuple) -> list:
    """Worker 函式：接收 klines + combos 批次，預計算一次，跑所有 combo

    每個 worker 獨立預計算指標（~3.5s），然後跑分配的 combo 批次。
    """
    train_klines, test_klines, combos, symbol, base_params, use_wf = args

    train_pre = precompute_indicators(train_klines, base_params)
    test_pre = precompute_indicators(test_klines, base_params) if test_klines else None

    results = []
    for combo in combos:
        train_result = run_backtest(train_klines, combo, symbol, quiet=True,
                                    precomputed=train_pre)
        train_summary = train_result["summary"]

        if use_wf and test_klines:
            test_result = run_backtest(test_klines, combo, symbol, quiet=True,
                                      precomputed=test_pre)
            test_summary = test_result["summary"]
            sc = walk_forward_score(train_summary, test_summary)
        else:
            test_summary = None
            sc = score_result(train_summary)

        results.append({
            "params":        combo,
            "score":         sc,
            "train_summary": _slim_summary(train_summary),
            "test_summary":  _slim_summary(test_summary) if test_summary else None,
        })
    return results


def random_search(base_params: dict, klines: list, symbol: str,
                  n: int = 300, use_walkforward: bool = True,
                  train_ratio: float = 0.667, verbose: bool = True,
                  n_workers: int = 0) -> list:
    """隨機搜尋 N 個參數組合（支援多進程加速）

    n_workers: 0=自動（CPU 核心數 - 2），1=單進程，N=指定 worker 數

    回傳: [{params, score, train_summary, test_summary}, ...]
    """
    if use_walkforward:
        train_klines, test_klines = split_data(klines, train_ratio)
        if verbose:
            print(f"  Walk-forward: train={len(train_klines):,} bars, "
                  f"test={len(test_klines):,} bars")
    else:
        train_klines = klines
        test_klines = None

    # 生成所有有效 combo
    combos = []
    attempts = 0
    while len(combos) < n and attempts < n * 10:
        c = generate_valid_combo(base_params)
        if c is not None:
            combos.append(c)
        attempts += 1
    if verbose:
        print(f"  生成 {len(combos)} 個有效參數組合")

    # 決定 worker 數
    cpu_count = os.cpu_count() or 4
    if n_workers <= 0:
        n_workers = max(1, min(cpu_count - 2, len(combos)))
    n_workers = min(n_workers, len(combos))

    if n_workers <= 1 or len(combos) < 10:
        # 單進程（少量 trial 不值得 fork）
        if verbose:
            log("單進程模式")
            log("預計算指標陣列...")
        train_pre = precompute_indicators(train_klines, base_params)
        test_pre = precompute_indicators(test_klines, base_params) if test_klines else None

        results = []
        for i, combo in enumerate(combos):
            tr = run_backtest(train_klines, combo, symbol, quiet=True, precomputed=train_pre)
            if use_walkforward and test_klines:
                te = run_backtest(test_klines, combo, symbol, quiet=True, precomputed=test_pre)
                sc = walk_forward_score(tr["summary"], te["summary"])
                te_slim = _slim_summary(te["summary"])
            else:
                sc = score_result(tr["summary"])
                te_slim = None
            results.append({
                "params": combo, "score": sc,
                "train_summary": _slim_summary(tr["summary"]),
                "test_summary": te_slim,
            })
            if verbose and (i + 1) % 20 == 0:
                best = max(results, key=lambda x: x["score"])
                bs = best["train_summary"]
                ts_str = ""
                if best["test_summary"]:
                    ts = best["test_summary"]
                    ts_str = f" | test: wr={ts['win_rate']:.0f}% pf={ts['profit_factor']:.2f}"
                print(f"\r  [{i+1:>4}/{len(combos)}] best={best['score']:.4f} "
                      f"train: wr={bs['win_rate']:.0f}% pf={bs['profit_factor']:.2f}{ts_str}",
                      end="", flush=True)
        if verbose:
            print()
    else:
        # 多進程：將 combos 分配給 worker
        if verbose:
            log(f"多進程模式: {n_workers} workers × ~{len(combos)//n_workers} combos")

        # 平均分配
        batches = [[] for _ in range(n_workers)]
        for i, c in enumerate(combos):
            batches[i % n_workers].append(c)

        worker_args = [
            (train_klines, test_klines, batch, symbol, base_params, use_walkforward)
            for batch in batches if batch
        ]

        with multiprocessing.Pool(processes=n_workers) as pool:
            batch_results = pool.map(_worker_batch, worker_args)

        results = []
        for batch in batch_results:
            results.extend(batch)

        if verbose:
            print(f"  完成 {len(results)} 筆搜尋")

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def hill_climb(base_params: dict, klines: list, symbol: str,
               seed_params: dict = None, max_iter: int = 50,
               use_walkforward: bool = True, train_ratio: float = 0.667,
               verbose: bool = True,
               train_pre: dict = None, test_pre: dict = None) -> list:
    """爬山法（從 seed_params 或 base_params 開始）"""
    if use_walkforward:
        train_klines, test_klines = split_data(klines, train_ratio)
    else:
        train_klines = klines
        test_klines = None

    # 預計算（若未傳入則自行計算）
    if train_pre is None:
        train_pre = precompute_indicators(train_klines, base_params)
    if test_klines and test_pre is None:
        test_pre = precompute_indicators(test_klines, base_params)

    def _eval(p):
        tr = run_backtest(train_klines, p, symbol, quiet=True, precomputed=train_pre)
        if test_klines:
            te = run_backtest(test_klines, p, symbol, quiet=True, precomputed=test_pre)
            return walk_forward_score(tr["summary"], te["summary"]), tr["summary"], te["summary"]
        return score_result(tr["summary"]), tr["summary"], None

    current = seed_params or base_params
    best_score, train_s, test_s = _eval(current)
    if verbose:
        print(f"  [init] score={best_score:.4f} wr={train_s['win_rate']:.1f}% "
              f"pf={train_s['profit_factor']:.2f}")

    results = [{
        "params": current, "score": best_score,
        "train_summary": _slim_summary(train_s),
        "test_summary": _slim_summary(test_s) if test_s else None,
    }]

    improved = True
    iteration = 0
    while improved and iteration < max_iter:
        improved = False
        iteration += 1
        for _ in range(len(SEARCH_SPACE) * 3):
            neighbor = generate_neighbor(current, base_params)
            if neighbor is None:
                continue
            sc, tr_s, te_s = _eval(neighbor)
            results.append({
                "params": neighbor, "score": sc,
                "train_summary": _slim_summary(tr_s),
                "test_summary": _slim_summary(te_s) if te_s else None,
            })
            if sc > best_score:
                best_score = sc
                current = neighbor
                improved = True
                if verbose:
                    print(f"  [iter {iteration}] score={sc:.4f} "
                          f"wr={tr_s['win_rate']:.1f}% pf={tr_s['profit_factor']:.2f}")

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def two_stage_search(base_params: dict, klines: list, symbol: str,
                     n_coarse: int = 100, n_fine: int = 200,
                     use_walkforward: bool = True, train_ratio: float = 0.667,
                     verbose: bool = True) -> list:
    """兩階段搜尋：粗搜 → 精搜

    Stage 1: 隨機搜尋 n_coarse 找 top-5
    Stage 2: 以 top-5 為種子，各跑 n_fine/5 次爬山法

    指標只計算一次（random_search 內部預計算，hill_climb 共用同一份）。
    """
    if verbose:
        print(f"  === Stage 1: 粗搜 ({n_coarse} 次) ===")

    # Stage 1 — 多進程粗搜
    results_s1 = random_search(
        base_params, klines, symbol, n=n_coarse,
        use_walkforward=use_walkforward, train_ratio=train_ratio,
        verbose=verbose
    )
    top5 = results_s1[:5]

    if verbose:
        print(f"\n  === Stage 2: 精搜 (top-5 × {n_fine // 5} 次爬山) ===")

    all_results = list(results_s1)
    hill_per_seed = max(10, n_fine // 5)

    # 為 hill climb 預計算（只算一次，5 個 seed 共用）
    if use_walkforward:
        train_klines, test_klines = split_data(klines, train_ratio)
    else:
        train_klines, test_klines = klines, None
    if verbose:
        log("預計算 hill-climb 指標...")
    train_pre = precompute_indicators(train_klines, base_params)
    test_pre = precompute_indicators(test_klines, base_params) if test_klines else None

    for rank, seed in enumerate(top5, 1):
        if verbose:
            print(f"\n  Seed #{rank} (score={seed['score']:.4f}):")
        hill_results = hill_climb(
            base_params, klines, symbol,
            seed_params=seed["params"], max_iter=hill_per_seed,
            use_walkforward=use_walkforward, train_ratio=train_ratio,
            verbose=verbose, train_pre=train_pre, test_pre=test_pre,
        )
        all_results.extend(hill_results)

    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results


def _slim_summary(summary: dict) -> dict:
    """精簡 summary（移除大型欄位供記錄用）"""
    if summary is None:
        return None
    return {k: v for k, v in summary.items()
            if k not in ("pnl_list", "params_used")}


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def run_optimizer(klines: list, symbol: str, base_params: dict,
                  mode: str = "random", n: int = 300,
                  use_walkforward: bool = True, train_ratio: float = 0.667,
                  verbose: bool = True, n_workers: int = 0) -> dict:
    """執行優化"""
    cpu_count = os.cpu_count() or 4
    workers = n_workers if n_workers > 0 else max(1, cpu_count - 2)

    print(f"\n{'='*60}")
    print(f"  參數優化器 v2 | {mode.upper()} | {symbol}")
    print(f"  Walk-forward: {'ON' if use_walkforward else 'OFF'}")
    print(f"  Workers: {workers} / {cpu_count} cores")
    print(f"{'='*60}\n")

    if mode == "hill":
        results = hill_climb(
            base_params, klines, symbol,
            use_walkforward=use_walkforward, train_ratio=train_ratio,
            verbose=verbose
        )
    elif mode == "two-stage":
        results = two_stage_search(
            base_params, klines, symbol,
            n_coarse=max(50, n // 3), n_fine=n - max(50, n // 3),
            use_walkforward=use_walkforward, train_ratio=train_ratio,
            verbose=verbose
        )
    else:  # random
        results = random_search(
            base_params, klines, symbol, n=n,
            use_walkforward=use_walkforward, train_ratio=train_ratio,
            verbose=verbose, n_workers=workers
        )

    if not results:
        print("  [!] 無有效結果")
        return None

    best = results[0]
    return {
        "best_params":   best["params"],
        "best_score":    best["score"],
        "train_summary": best["train_summary"],
        "test_summary":  best["test_summary"],
        "top10":         results[:10],
        "total_runs":    len(results),
    }


def print_best(result: dict, use_walkforward: bool):
    """輸出最佳結果"""
    if result is None:
        return

    best  = result["best_params"]
    train = result["train_summary"]
    test  = result.get("test_summary")
    score = result["best_score"]

    print()
    print("=" * 60)
    print("              最佳參數結果")
    print("=" * 60)
    print(f"  綜合評分:      {score:>8.4f}")
    print(f"  搜尋總次數:    {result['total_runs']:>6}")
    print()

    # Train 結果
    pf_t = f"{train['profit_factor']:.2f}" if train["profit_factor"] < 99 else "INF"
    print("  [Train]")
    print(f"    交易筆數:  {train['total_trades']:>5}  |  勝率: {train['win_rate']:>5.1f}%")
    print(f"    獲利因子:  {pf_t:>5}  |  總R: {train['total_pnl_r']:>+7.2f}")
    print(f"    最大回撤:  {train.get('max_drawdown_r', 0):>+6.2f} R  |  最大連虧: {train['max_consecutive_loss']}")

    # Test 結果
    if use_walkforward and test:
        pf_e = f"{test['profit_factor']:.2f}" if test["profit_factor"] < 99 else "INF"
        print()
        print("  [Test]")
        print(f"    交易筆數:  {test['total_trades']:>5}  |  勝率: {test['win_rate']:>5.1f}%")
        print(f"    獲利因子:  {pf_e:>5}  |  總R: {test['total_pnl_r']:>+7.2f}")
        print(f"    最大回撤:  {test.get('max_drawdown_r', 0):>+6.2f} R  |  最大連虧: {test['max_consecutive_loss']}")

    print()
    print("  最佳參數:")
    display_keys = list(SEARCH_SPACE.keys()) + ["weight_momentum"]
    for k in display_keys:
        v = best.get(k, "?")
        print(f"    {k:<32} = {v}")

    print("=" * 60)
    print()


def save_best(result: dict, base_params: dict, use_walkforward: bool):
    """儲存最佳結果"""
    os.makedirs(BACKTEST_DIR, exist_ok=True)
    best = result["best_params"]

    # 寫回 backtest_params.json
    updated = copy.deepcopy(base_params)
    updated.update(best)
    with open(PARAMS_FILE, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)
    print(f"  backtest_params.json 已更新為最佳參數")

    # 備份 best
    best_output = {
        "updated_at":    datetime.now(tz=timezone.utc).isoformat(),
        "score":         result["best_score"],
        "train_summary": result["train_summary"],
        "params":        result["best_params"],
    }
    if use_walkforward and result.get("test_summary"):
        best_output["test_summary"] = result["test_summary"]

    with open(PARAMS_BEST_FILE, "w", encoding="utf-8") as f:
        json.dump(best_output, f, ensure_ascii=False, indent=2)
    print(f"  backtest_params_best.json 已儲存")

    # 儲存完整記錄
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fpath = os.path.join(BACKTEST_DIR, f"optimizer_v2_{ts}.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump({
            "run_at":       datetime.now(tz=timezone.utc).isoformat(),
            "mode":         "optimizer_v2",
            "walkforward":  use_walkforward,
            "best_score":   result["best_score"],
            "train_summary": result["train_summary"],
            "test_summary": result.get("test_summary"),
            "top10":        result["top10"],
            "total_runs":   result["total_runs"],
        }, f, ensure_ascii=False, indent=2)
    print(f"  優化記錄已儲存 {fpath}")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scalping Trade Analyzer — 自動參數優化器 v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
模式:
  random     — 隨機搜尋 N 次（預設 300，最通用）
  hill       — 爬山法（快速，局部最優）
  two-stage  — 粗搜 + 精搜（最佳品質）

範例:
  python3 optimizer.py
  python3 optimizer.py -f history/BTCUSDT_5m_*.json --mode random -n 500
  python3 optimizer.py --mode two-stage -n 400
  python3 optimizer.py --mode hill --no-walkforward
  python3 optimizer.py --no-update
        """
    )
    parser.add_argument("-f", "--file",     default=None)
    parser.add_argument("--mode",           choices=["random", "hill", "two-stage"],
                        default="random")
    parser.add_argument("-n", "--n-trials",  type=int, default=300,
                        help="搜尋次數（預設 300）")
    parser.add_argument("--params",         default=PARAMS_FILE)
    parser.add_argument("--no-update",      action="store_true",
                        help="不更新 backtest_params.json")
    parser.add_argument("--no-walkforward", action="store_true",
                        help="停用 walk-forward 驗證")
    parser.add_argument("--train-ratio",    type=float, default=0.667,
                        help="Train 比例（預設 0.667）")
    parser.add_argument("--workers",        type=int, default=0,
                        help="Worker 進程數（預設: CPU-2，1=單進程）")
    parser.add_argument("--quiet",          action="store_true")

    args = parser.parse_args()

    # 選擇歷史檔案
    if args.file:
        fpath = args.file
    else:
        files = list_history_files()
        if not files:
            print("[!] history/ 目錄無資料，請先執行 data_fetcher.py")
            sys.exit(1)
        fpath = files[0]
        print(f"  自動選擇: {fpath}")

    if not os.path.exists(fpath):
        print(f"[!] 找不到檔案: {fpath}")
        sys.exit(1)

    hist   = load_history(fpath)
    klines = hist.get("klines", [])
    symbol = hist.get("symbol", "UNKNOWN")
    print(f"  {symbol} | {len(klines):,} 根 K 線 | {hist.get('days', '?')} 天")

    # Walk-forward 需要足夠資料
    use_wf = not args.no_walkforward
    if use_wf and len(klines) < 5000:
        print(f"  [!] 資料不足 {len(klines)} bars，建議 90+ 天。停用 walk-forward。")
        use_wf = False

    # 載入基礎參數
    base_params = load_params(args.params)

    # 執行優化
    result = run_optimizer(
        klines, symbol, base_params,
        mode=args.mode, n=args.n_trials,
        use_walkforward=use_wf, train_ratio=args.train_ratio,
        verbose=not args.quiet, n_workers=args.workers,
    )

    if result is None:
        sys.exit(1)

    print_best(result, use_wf)

    if not args.no_update:
        save_best(result, base_params, use_wf)
        print("\n  下一步: python3 backtest_engine.py  (使用最佳參數重跑確認)")
    else:
        print("\n  --no-update: backtest_params.json 未修改")


if __name__ == "__main__":
    main()
