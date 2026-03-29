#!/usr/bin/env python3
"""
optimizer.py — 自動參數優化器
Scalping Trade Analyzer Pro — Backtest Feedback Loop (Phase 5)

用法:
    python3 optimizer.py                          # 用最新 history/ 檔案，grid search
    python3 optimizer.py -f history/BTCUSDT_5m_*.json
    python3 optimizer.py --mode random -n 80      # 隨機搜尋 80 次
    python3 optimizer.py --mode hill              # 爬山法

功能:
    - 在搜尋空間內自動跑多次 backtest_engine 回測
    - 找出最佳參數組合（依 profit_factor × win_rate 評分）
    - 輸出 backtest_history/optimizer_{ts}.json + best_params.json
    - 自動更新 backtest_params.json 為最佳結果
"""

import json
import os
import sys
import copy
import random
import argparse
import itertools
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from backtest_engine import (
    run_backtest, load_params, flatten_params,
    load_history, list_history_files, save_results
)

# ─── 搜尋空間定義 ─────────────────────────────────────────────────────────────

SEARCH_SPACE = {
    # ── 強信號門檻（strong_only=true，normal 參數不影響結果）────
    # 聚焦在上輪最佳區域 composite=70 附近
    "strong_signal_composite":  [60, 65, 70, 75],
    "strong_signal_min_floor":  [35, 40],

    # ── 選2：拉高 TP 目標（avg win 需達 ~1.93R 才能 break-even）─
    # 上輪 clamp_min=2.5 / tp1_min=4.5 → avg win 1.53R，需更高 RR
    # 目標 RR 2.0~2.5+（tp1_min = clamp_min × 2.0~2.5）
    "atr_clamp_min":            [2.0, 2.5, 3.0],
    "atr_tp1_min":              [4.5, 5.0, 5.5, 6.0, 6.75, 7.5],

    # max_hold_bars 已設為 0（無時間限制），不列入搜尋空間
}

# 固定不動（非獨立變數）
FIXED_IN_SEARCH = {
    "weight_trend":     0.35,
    "weight_structure": 0.40,
    "weight_momentum":  0.25,
}

PARAMS_FILE      = "backtest_params.json"
PARAMS_BEST_FILE = "backtest_params_best.json"
BACKTEST_DIR     = "backtest_history"

# ─── 評分函式 ─────────────────────────────────────────────────────────────────

def score_result(summary: dict) -> float:
    """
    綜合評分（越高越好）:
        profit_factor × win_rate_factor × sample_penalty
    - profit_factor: 越高越好（上限 5 防止過擬合）
    - win_rate_factor: 勝率 0~1
    - sample_penalty: 樣本 < 15 筆大幅降分
    """
    total = summary.get("total_trades", 0)
    if total < 5:
        return -999.0   # 樣本太少，不列入

    pf       = min(summary.get("profit_factor", 0), 5.0)
    wr       = summary.get("win_rate", 0) / 100.0
    avg_rr   = summary.get("avg_rr", 0)
    max_loss = summary.get("max_consecutive_loss", 999)

    # 樣本數獎懲
    sample_factor = min(total / 30.0, 1.0)

    # 連虧懲罰（連虧 > 5 次打折）
    loss_penalty = max(0.5, 1.0 - max(0, max_loss - 5) * 0.05)

    raw = pf * wr * sample_factor * loss_penalty
    return round(raw, 4)


# ─── Grid Search ──────────────────────────────────────────────────────────────

def grid_combinations() -> list:
    """產生所有參數組合"""
    keys   = list(SEARCH_SPACE.keys())
    values = list(SEARCH_SPACE.values())
    combos = []
    for combo in itertools.product(*values):
        d = dict(zip(keys, combo))
        # 合法性檢查：TP 距離必須 ≥ 1.5 × SL 距離（確保 RR ≥ 1.5）
        if d.get("atr_tp1_min", 0) < d.get("atr_clamp_min", 0) * 1.5:
            continue
        # atr_clamp_max 必須 ≥ atr_clamp_min（避免 max < min 產生衝突）
        d["atr_clamp_max"] = max(d.get("atr_clamp_min", 1.0), 2.5)
        combos.append(d)
    return combos


def random_combinations(n: int, seed: int = 42) -> list:
    """隨機採樣 n 個參數組合"""
    random.seed(seed)
    combos = []
    for _ in range(n * 5):   # 多生成後過濾
        d = {k: random.choice(v) for k, v in SEARCH_SPACE.items()}
        # 合法性檢查：TP 距離必須 ≥ 1.5 × SL 距離（確保 RR ≥ 1.5）
        if d.get("atr_tp1_min", 0) < d.get("atr_clamp_min", 0) * 1.5:
            continue
        # atr_clamp_max 必須 ≥ atr_clamp_min（避免 max < min 產生衝突）
        d["atr_clamp_max"] = max(d.get("atr_clamp_min", 1.0), 2.5)
        combos.append(d)
        if len(combos) >= n:
            break
    return combos


# ─── 爬山法 ───────────────────────────────────────────────────────────────────

def hill_climb(base_params: dict, klines: list, symbol: str,
               max_iter: int = 50, verbose: bool = True) -> tuple:
    """
    Hill Climbing 爬山法
    每輪對每個搜尋維度嘗試相鄰值，取改善最大者
    回傳 (best_params, best_score)
    """
    def _run(p):
        result = run_backtest(klines, p, symbol)
        return score_result(result["summary"]), result["summary"]

    current = copy.deepcopy(base_params)
    best_score, best_summary = _run(current)
    if verbose:
        print(f"[初始] score={best_score:.4f}  trades={best_summary['total_trades']}  "
              f"wr={best_summary['win_rate']:.1f}%  pf={best_summary['profit_factor']:.2f}")

    improved = True
    iteration = 0
    while improved and iteration < max_iter:
        improved = False
        iteration += 1
        for key, choices in SEARCH_SPACE.items():
            for val in choices:
                if val == current.get(key):
                    continue
                trial = copy.deepcopy(current)
                trial[key] = val
                # 合法性：RR ≥ 1.5
                if trial.get("atr_tp1_min", 0) < trial.get("atr_clamp_min", 0) * 1.5:
                    continue
                trial["atr_clamp_max"] = max(trial.get("atr_clamp_min", 1.0), 2.5)

                s, summ = _run(trial)
                if s > best_score:
                    best_score = s
                    current    = trial
                    improved   = True
                    if verbose:
                        print(f"[iter {iteration}] ✅ {key}={val}  "
                              f"score={s:.4f}  wr={summ['win_rate']:.1f}%  "
                              f"pf={summ['profit_factor']:.2f}")

    return current, best_score


# ─── 主流程 ───────────────────────────────────────────────────────────────────

# ─── 平行化工作函式（必須在 module 頂層，ProcessPoolExecutor 才能 pickle）────

def _worker(args):
    """單次回測工作（供多進程使用）"""
    override, base_params, klines, symbol = args
    trial_params = copy.deepcopy(base_params)
    trial_params.update(override)
    trial_params.update(FIXED_IN_SEARCH)
    result  = run_backtest(klines, trial_params, symbol)
    summary = result["summary"]
    sc      = score_result(summary)
    return {
        "rank":    0,
        "params":  override,
        "score":   sc,
        "summary": {
            "total_trades":         summary["total_trades"],
            "win_rate":             summary["win_rate"],
            "profit_factor":        summary["profit_factor"],
            "avg_rr":               summary["avg_rr"],
            "total_pnl_r":          summary["total_pnl_r"],
            "max_consecutive_loss": summary["max_consecutive_loss"],
        },
        "full_params": trial_params,
        "full_summary": summary,
    }


def run_optimizer(klines: list, symbol: str, base_params: dict,
                  mode: str = "grid", n_random: int = 80,
                  workers: int = None, verbose: bool = True) -> dict:
    """
    執行優化，回傳:
    {
        "best_params": {...},
        "best_score": float,
        "best_summary": {...},
        "all_runs": [...]
    }
    workers: 並行進程數（預設 = CPU 核心數）
    """
    if workers is None:
        workers = multiprocessing.cpu_count()

    print(f"\n{'='*60}")
    print(f"  🔍 參數優化器 | 模式: {mode.upper()} | {symbol}")
    print(f"  ⚡ 並行進程: {workers} 核心")
    print(f"{'='*60}\n")

    if mode == "hill":
        print("⛰️  爬山法啟動（單執行緒）...")
        best_combo, best_score = hill_climb(base_params, klines, symbol, verbose=verbose)
        result = run_backtest(klines, best_combo, symbol)
        best_summary = result["summary"]
        all_runs = [{"params": best_combo, "score": best_score, "summary": best_summary}]

    else:
        if mode == "random":
            combos = random_combinations(n_random)
            print(f"🎲 隨機搜尋 {len(combos)} 種組合 × {workers} 核心...")
        else:
            combos = grid_combinations()
            print(f"📐 格狀搜尋 {len(combos)} 種組合 × {workers} 核心...")

        all_runs     = []
        best_score   = -999.0
        best_combo   = None
        best_summary = None
        completed    = 0
        total        = len(combos)

        work_args = [(override, base_params, klines, symbol) for override in combos]

        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_worker, arg): arg for arg in work_args}
            for future in as_completed(futures):
                completed += 1
                try:
                    run = future.result()
                except Exception as e:
                    completed_safely = completed
                    if verbose:
                        print(f"\r  ⚠️ 某次回測失敗: {e}", flush=True)
                    continue

                all_runs.append(run)

                if run["score"] > best_score:
                    best_score   = run["score"]
                    best_combo   = run["full_params"]
                    best_summary = run["full_summary"]

                if verbose and completed % 10 == 0:
                    pct = completed / total * 100
                    ws  = best_summary["win_rate"] if best_summary else 0
                    pf  = best_summary["profit_factor"] if best_summary else 0
                    print(f"\r  進度 {pct:5.1f}% ({completed}/{total}) | "
                          f"最佳 score={best_score:.4f}  wr={ws:.1f}%  pf={pf:.2f}   ",
                          end="", flush=True)

        print()  # 換行

        # 清除 full_params / full_summary（節省記憶體）
        for r in all_runs:
            r.pop("full_params",   None)
            r.pop("full_summary",  None)

        # 排序
        all_runs.sort(key=lambda x: x["score"], reverse=True)
        for rank, r in enumerate(all_runs, 1):
            r["rank"] = rank

    return {
        "best_params":  best_combo,
        "best_score":   best_score,
        "best_summary": best_summary,
        "all_runs":     all_runs,
    }


def print_best(result: dict):
    best  = result["best_params"]
    summ  = result["best_summary"]
    score = result["best_score"]

    pf = f"{summ['profit_factor']:.2f}" if summ["profit_factor"] != float("inf") else "∞"

    print()
    print("┌─────────────────────────────────────────────────────┐")
    print("│               🏆 最佳參數結果                        │")
    print("├─────────────────────────────────────────────────────┤")
    print(f"│  綜合評分:      {score:>8.4f}                           │")
    print(f"│  總交易筆數:    {summ['total_trades']:>6}                                │")
    print(f"│  勝率:          {summ['win_rate']:>6.1f}%                               │")
    print(f"│  獲利因子:      {pf:>7}                               │")
    print(f"│  平均 R:R:      {summ['avg_rr']:>+7.3f}                               │")
    print(f"│  總 R 損益:     {summ['total_pnl_r']:>+7.3f}                               │")
    print(f"│  最大連虧:      {summ['max_consecutive_loss']:>6}  次                           │")
    print("├─────────────────────────────────────────────────────┤")
    print("│  最佳參數:                                          │")

    # 只顯示搜尋空間裡的參數
    for k in SEARCH_SPACE.keys():
        v = best.get(k, "?")
        print(f"│    {k:<32} = {str(v):<8}         │")

    print("└─────────────────────────────────────────────────────┘")
    print()


def save_best(result: dict, base_params_raw: dict):
    """
    將最佳參數寫回 backtest_params.json（只更新搜尋空間的 key）
    同時儲存 backtest_params_best.json 備份
    """
    os.makedirs(BACKTEST_DIR, exist_ok=True)
    best = result["best_params"]

    # 更新各 section
    updated = copy.deepcopy(base_params_raw)
    sections = ["scoring_weights", "signal_thresholds", "rr_thresholds",
                "atr_params", "backtest_params"]
    for section in sections:
        if section in updated and isinstance(updated[section], dict):
            for k in list(updated[section].keys()):
                if k.startswith("_"):
                    continue
                if k in best:
                    updated[section][k] = best[k]

    # 寫回 backtest_params.json
    with open(PARAMS_FILE, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)
    print(f"✅ backtest_params.json 已更新為最佳參數")

    # 備份 best
    with open(PARAMS_BEST_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            "score":      result["best_score"],
            "summary":    result["best_summary"],
            "params":     result["best_params"],
        }, f, ensure_ascii=False, indent=2)
    print(f"💾 backtest_params_best.json 已儲存")

    # 儲存所有 runs 至 backtest_history/
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fpath = os.path.join(BACKTEST_DIR, f"optimizer_{ts}.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump({
            "run_at":      datetime.now(tz=timezone.utc).isoformat(),
            "mode":        "optimizer",
            "best_score":  result["best_score"],
            "best_summary":result["best_summary"],
            "top10":       result["all_runs"][:10],
        }, f, ensure_ascii=False, indent=2)
    print(f"📊 優化記錄已儲存 {fpath}")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scalping Trade Analyzer — 自動參數優化器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
模式說明:
  grid   — 格狀搜尋所有組合（最完整，預設）
  random — 隨機搜尋 N 次（快速，適合參數多時）
  hill   — 爬山法（最快，但可能局部最優）

範例:
  python3 optimizer.py
  python3 optimizer.py -f history/BTCUSDT_5m_*.json --mode random -n 80
  python3 optimizer.py --mode hill
  python3 optimizer.py --workers 8         # 指定 8 核心並行
  python3 optimizer.py --no-update         # 只跑優化，不更新 backtest_params.json
        """
    )
    parser.add_argument("-f", "--file",    default=None)
    parser.add_argument("--mode",          choices=["grid", "random", "hill"], default="grid")
    parser.add_argument("-n", "--n-random",type=int, default=80,
                        help="隨機搜尋次數（--mode random 時使用）")
    parser.add_argument("--workers",       type=int, default=None,
                        help=f"並行進程數（預設: CPU 核心數 = {multiprocessing.cpu_count()}）")
    parser.add_argument("--params",        default=PARAMS_FILE)
    parser.add_argument("--no-update",     action="store_true",
                        help="不更新 backtest_params.json")
    parser.add_argument("--quiet",         action="store_true",
                        help="減少輸出")

    args = parser.parse_args()

    # 選擇歷史檔案
    if args.file:
        fpath = args.file
    else:
        files = list_history_files()
        if not files:
            print("❌ history/ 目錄無資料，請先執行 data_fetcher.py")
            sys.exit(1)
        fpath = files[0]
        print(f"📂 自動選擇: {fpath}")

    if not os.path.exists(fpath):
        print(f"❌ 找不到檔案: {fpath}")
        sys.exit(1)

    hist   = load_history(fpath)
    klines = hist.get("klines", [])
    symbol = hist.get("symbol", "UNKNOWN")
    print(f"   {symbol} | {len(klines):,} 根 K 線")

    # 載入基礎參數
    raw_params  = load_params(args.params)
    base_params = flatten_params(raw_params)

    # 執行優化
    result = run_optimizer(
        klines, symbol, base_params,
        mode=args.mode,
        n_random=args.n_random,
        workers=args.workers,
        verbose=not args.quiet,
    )

    # 輸出最佳結果
    print_best(result)

    # 儲存 + 更新
    if not args.no_update:
        save_best(result, raw_params)
        print("\n💡 下一步: python3 backtest_engine.py   (使用最佳參數重跑確認)")
    else:
        print("\n⚠️  --no-update：backtest_params.json 未修改")


if __name__ == "__main__":
    main()
