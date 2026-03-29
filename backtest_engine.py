#!/usr/bin/env python3
"""
backtest_engine.py — 回測引擎
Scalping Trade Analyzer Pro — Backtest Feedback Loop (Phase 3)

用法:
    python3 backtest_engine.py                          # 自動選最新 history/ 檔案
    python3 backtest_engine.py -f history/BTCUSDT_5m_*.json
    python3 backtest_engine.py -f history/BTCUSDT_5m_*.json --run-id run01
    python3 backtest_engine.py -f history/BTCUSDT_5m_*.json --export csv

功能:
    - 讀取 history/ 歷史 K 線 + backtest_params.json
    - 逐 bar 滾動窗口（150 根）模擬訊號觸發
    - 追蹤每筆交易 SL / TP / 到期，計算 R 損益
    - 輸出統計摘要 + backtest_history/run_{id}.json
    - 不修改 app_v3.py（零侵入）
"""

import json
import os
import sys
import csv
import argparse
from datetime import datetime, timezone
from pathlib import Path

# ─── 導入主程式分析類（零修改）───────────────────────────────────────────────

sys.path.insert(0, os.path.dirname(__file__))

try:
    from app_v3 import ScalpingAnalyzerPro, FIXED_PARAMS
except ImportError as e:
    print(f"❌ 無法 import app_v3.py: {e}")
    print("   請確認 app_v3.py 與 backtest_engine.py 在同一目錄")
    sys.exit(1)

# ─── 設定 ────────────────────────────────────────────────────────────────────

HISTORY_DIR      = "history"
BACKTEST_DIR     = "backtest_history"
PARAMS_FILE      = "backtest_params.json"
PARAMS_DEFAULT   = "backtest_params_default.json"

# ─── MTF 中性佔位（回測不發 API）────────────────────────────────────────────

MTF_NEUTRAL = {
    "timeframe":    "N/A",
    "trend":        "neutral",
    "trend_strength": 0,
    "confirmation": False,
    "note":         "backtest_mode_no_live_api"
}

# ─── 工具函式 ─────────────────────────────────────────────────────────────────

def log(msg: str, end="\n"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", end=end, flush=True)


def ms_to_dt(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def load_params(path: str = PARAMS_FILE) -> dict:
    """載入回測參數表"""
    if not os.path.exists(path):
        log(f"⚠️  找不到 {path}，使用 app_v3.py 預設值")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        p = json.load(f)
    return p


def flatten_params(p: dict) -> dict:
    """將巢狀參數展平為單層 dict"""
    flat = {}
    for section, values in p.items():
        if section.startswith("_") or not isinstance(values, dict):
            continue
        for k, v in values.items():
            if not k.startswith("_"):
                flat[k] = v
    return flat


def load_history(fpath: str) -> dict:
    """載入歷史 K 線 JSON"""
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def list_history_files() -> list:
    """列出 history/ 目錄的 JSON 檔案（最新在前）"""
    if not os.path.exists(HISTORY_DIR):
        return []
    files = sorted(
        [os.path.join(HISTORY_DIR, f) for f in os.listdir(HISTORY_DIR) if f.endswith(".json")],
        key=os.path.getmtime,
        reverse=True
    )
    return files


# ─── 信號評估（使用 backtest_params 門檻）─────────────────────────────────────

def evaluate_signal(window: list, params: dict, symbol: str) -> dict:
    """
    以一個滾動窗口的 K 線計算信號
    回傳 dict: {signal_type, trend_score, structure_score, momentum_score,
                composite, sl_tp, signal_stage}
    """
    closes = [float(k[4]) for k in window]
    current_price = closes[-1]

    # ── 指標計算 ──
    fp = FIXED_PARAMS  # 指標週期固定與主程式一致

    rsi = ScalpingAnalyzerPro.calculate_rsi(closes, fp["rsi_period"])
    ema_fast = ScalpingAnalyzerPro.calculate_ema(closes, fp["ema_fast"])
    ema_slow = ScalpingAnalyzerPro.calculate_ema(closes, fp["ema_slow"])
    macd_line, signal_line, histogram = ScalpingAnalyzerPro.calculate_macd(
        closes, fp["macd_fast"], fp["macd_slow"], fp["macd_signal"]
    )
    atr_period = params.get("atr_period", 14)
    atr = ScalpingAnalyzerPro.calculate_atr(window, atr_period)
    bb_upper, bb_middle, bb_lower = ScalpingAnalyzerPro.calculate_bollinger_bands(closes, 20, 2)
    stoch_k, stoch_d = ScalpingAnalyzerPro.calculate_stochastic(window, 14, 3)

    # ── SMC 結構 ──
    swing_n = params.get("swing_n", 3)
    swing_pts = ScalpingAnalyzerPro.find_swing_points(window, n=swing_n)
    bos_list  = ScalpingAnalyzerPro.detect_bos(window, swing_pts)
    obs       = ScalpingAnalyzerPro.identify_order_blocks(window, bos_list)
    fvgs      = ScalpingAnalyzerPro.identify_fvg(window)
    sweeps    = ScalpingAnalyzerPro.detect_liquidity_sweep(window, swing_pts, atr)

    # ── 趨勢方向 ──
    trend_dir = None
    if bos_list:
        trend_dir = bos_list[-1]["direction"]
    elif ema_fast and ema_slow:
        trend_dir = "bullish" if ema_fast > ema_slow else "bearish"

    # ── 三維評分 ──
    trend_res     = ScalpingAnalyzerPro.calc_trend_score(
        bos_list, MTF_NEUTRAL, ema_fast, ema_slow, current_price,
        bb_upper, bb_middle, bb_lower
    )
    structure_res = ScalpingAnalyzerPro.calc_structure_score(
        obs, fvgs, sweeps, current_price, atr, bos_list
    )
    momentum_res  = ScalpingAnalyzerPro.calc_momentum_score(
        rsi, macd_line, signal_line, histogram, stoch_k, stoch_d,
        None,            # volume_analysis（回測模式傳 None）
        window,          # data（K 線窗口，供背離計算使用）
        prev_histogram=None,
        atr=atr,
        trend_direction=trend_dir
    )

    trend_score     = trend_res["score"]     if isinstance(trend_res, dict)     else trend_res
    structure_score = structure_res["score"] if isinstance(structure_res, dict) else structure_res
    momentum_score  = momentum_res["score"]  if isinstance(momentum_res, dict)  else momentum_res

    # ── 加權合分（使用 backtest_params 權重）──
    wt = params.get("weight_trend",     0.35)
    ws = params.get("weight_structure", 0.40)
    wm = params.get("weight_momentum",  0.25)
    composite = trend_score * wt + structure_score * ws + momentum_score * wm

    # ── 強 / 普通信號門檻 ──
    strong_comp  = params.get("strong_signal_composite",  55)
    strong_floor = params.get("strong_signal_min_floor",  30)
    strong_trend = params.get("strong_signal_trend",      55)
    normal_comp  = params.get("normal_signal_composite",  45)
    normal_floor = params.get("normal_signal_min_floor",  25)
    normal_trend = params.get("normal_signal_trend",      45)

    min_floor = min(trend_score, structure_score, momentum_score)
    signal_type  = None
    signal_grade = None   # 'strong' | 'normal'

    if trend_score > 50:
        if composite >= strong_comp and min_floor >= strong_floor and trend_score >= strong_trend:
            signal_type, signal_grade = "buy", "strong"
        elif composite >= normal_comp and min_floor >= normal_floor and trend_score >= normal_trend:
            signal_type, signal_grade = "buy", "normal"
    elif trend_score < 50:
        bearish_strength = 100 - trend_score
        sell_composite   = bearish_strength * wt + structure_score * ws + momentum_score * wm
        sell_floor       = min(bearish_strength, structure_score, momentum_score)
        if sell_composite >= strong_comp and sell_floor >= strong_floor and trend_score <= (100 - strong_trend):
            signal_type, signal_grade = "sell", "strong"
        elif sell_composite >= normal_comp and sell_floor >= normal_floor and trend_score <= (100 - normal_trend):
            signal_type, signal_grade = "sell", "normal"

    # ── SL/TP 計算 ──
    sl_tp       = None
    signal_stage = None

    if signal_type:
        # 先確認 pre-alert 是否觸發（check_pre_alert 不依賴 backtest_params）
        pre_alert_triggered, _ = ScalpingAnalyzerPro.check_pre_alert(
            current_price, atr, obs, swing_pts, fvgs
        )
        if pre_alert_triggered:
            sl_tp = ScalpingAnalyzerPro.calc_dynamic_sl_tp(
                current_price, atr, signal_type, obs, fvgs, swing_pts
            )
            if sl_tp is None:
                signal_stage = "pre_alert"
                signal_type  = None
            else:
                # ── 覆蓋 TP1：強制最小 TP 距離 = atr × atr_tp1_min ──
                tp1_min_mult = params.get("atr_tp1_min", 1.0)
                if atr and tp1_min_mult > 1.0:
                    min_tp_dist = atr * tp1_min_mult
                    tp1_key = "take_profit_1"
                    if signal_type == "buy":
                        forced_tp1 = current_price + min_tp_dist
                        if sl_tp[tp1_key] < forced_tp1:
                            sl_tp = dict(sl_tp)
                            sl_tp[tp1_key] = round(forced_tp1, 6)
                    else:
                        forced_tp1 = current_price - min_tp_dist
                        if sl_tp[tp1_key] > forced_tp1:
                            sl_tp = dict(sl_tp)
                            sl_tp[tp1_key] = round(forced_tp1, 6)

                # ── 覆蓋 SL：強制最小 SL 距離 = atr × atr_clamp_min ──
                sl_min_mult = params.get("atr_clamp_min", 1.0)
                if atr and sl_min_mult > 0:
                    min_sl_dist = atr * sl_min_mult
                    if signal_type == "buy":
                        forced_sl = current_price - min_sl_dist
                        if sl_tp["stop_loss"] > forced_sl:
                            sl_tp = dict(sl_tp)
                            sl_tp["stop_loss"] = round(forced_sl, 6)
                    else:
                        forced_sl = current_price + min_sl_dist
                        if sl_tp["stop_loss"] < forced_sl:
                            sl_tp = dict(sl_tp)
                            sl_tp["stop_loss"] = round(forced_sl, 6)

                # ── 重新計算 R:R，低於門檻則拒絕 ──
                sl_dist_new = abs(current_price - sl_tp["stop_loss"])
                tp_dist_new = abs(sl_tp["take_profit_1"] - current_price)
                rr_new = tp_dist_new / sl_dist_new if sl_dist_new > 0 else 0

                rr_min = params.get("rr_ok", 1.0)
                if rr_new < rr_min:
                    signal_stage = "pre_alert"
                    signal_type  = None
                else:
                    sl_tp = dict(sl_tp)
                    sl_tp["risk_reward_ratio"] = round(rr_new, 2)
                    signal_stage = "confirmed"
        else:
            signal_stage = "pre_alert"
            signal_type  = None

    return {
        "signal_type":     signal_type,
        "signal_grade":    signal_grade,
        "signal_stage":    signal_stage,
        "trend_score":     trend_score,
        "structure_score": structure_score,
        "momentum_score":  momentum_score,
        "composite":       round(composite, 2),
        "current_price":   current_price,
        "atr":             atr,
        "sl_tp":           sl_tp,
    }


# ─── 回測核心 ──────────────────────────────────────────────────────────────────

def run_backtest(klines: list, params: dict, symbol: str) -> dict:
    """
    逐 bar 滾動回測

    klines: Binance 原始 K 線陣列 [[open_time, open, high, low, close, volume, ...], ...]
    params: 展平後的 backtest_params
    symbol: 交易對名稱（用於記錄）

    回傳: {trades: [...], summary: {...}}
    """
    rolling_window = params.get("rolling_window", 150)
    min_data_bars  = params.get("min_data_bars",   50)
    max_hold_bars  = params.get("max_hold_bars",   12)
    commission     = params.get("commission_rate", 0.0004)

    total_bars = len(klines)
    log(f"📊 回測開始 | {symbol} | {total_bars:,} 根 K 線")
    log(f"   滾動窗口: {rolling_window} | 最長持倉: {max_hold_bars} | 手續費: {commission*100:.2f}%")

    trades     = []
    trade_id   = 0
    active     = None   # 目前持倉 dict

    start_bar = rolling_window
    bar_count = total_bars - start_bar

    for i in range(start_bar, total_bars):
        # 進度（每 500 根更新一次）
        if (i - start_bar) % 500 == 0:
            pct = (i - start_bar) / bar_count * 100
            print(f"\r   進度 {pct:5.1f}% ({i - start_bar:,}/{bar_count:,}) | "
                  f"交易筆數: {len(trades)}", end="", flush=True)

        current_bar = klines[i]
        bar_time_ms  = int(current_bar[0])
        bar_high     = float(current_bar[2])
        bar_low      = float(current_bar[3])
        bar_close    = float(current_bar[4])

        # ── 處理持倉 ──
        if active:
            hold_bars = i - active["trigger_bar_index"]
            result    = None
            exit_price = None

            if active["signal_type"] == "buy":
                if bar_low <= active["sl_price"]:
                    result, exit_price = "sl_hit", active["sl_price"]
                elif bar_high >= active["tp_price"]:
                    result, exit_price = "tp_hit", active["tp_price"]
            else:  # sell
                if bar_high >= active["sl_price"]:
                    result, exit_price = "sl_hit", active["sl_price"]
                elif bar_low <= active["tp_price"]:
                    result, exit_price = "tp_hit", active["tp_price"]

            if result is None and max_hold_bars > 0 and hold_bars >= max_hold_bars:
                result, exit_price = "expired", bar_close

            if result:
                # 計算 R 損益
                sl_dist  = abs(active["entry_price"] - active["sl_price"])
                tp_dist  = abs(active["tp_price"]    - active["entry_price"])
                rr_ratio = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0

                if result == "tp_hit":
                    pnl_r = round(rr_ratio, 3)
                elif result == "sl_hit":
                    pnl_r = -1.0
                else:   # expired
                    if active["signal_type"] == "buy":
                        pnl_r = round((exit_price - active["entry_price"]) / sl_dist, 3)
                    else:
                        pnl_r = round((active["entry_price"] - exit_price) / sl_dist, 3)

                # 手續費（扣兩次：進出場）
                pnl_r -= commission * 2 / (sl_dist / active["entry_price"]) if active["entry_price"] > 0 else 0

                trade = {**active,
                    "result":         result,
                    "exit_price":     round(exit_price, 6),
                    "exit_time":      ms_to_dt(bar_time_ms),
                    "exit_bar_index": i,
                    "hold_bars":      hold_bars,
                    "pnl_r":          round(pnl_r, 3),
                    "rr_ratio":       rr_ratio,
                }
                trades.append(trade)
                active = None

        # ── 尋找新訊號（無持倉時）──
        if active is None and i >= start_bar:
            window = klines[i - rolling_window + 1 : i + 1]
            try:
                sig = evaluate_signal(window, params, symbol)
            except Exception as e:
                continue   # 跳過計算失敗的 bar

            # 過濾：只取強信號 / 只做買方
            if params.get("strong_only", False) and sig["signal_grade"] != "strong":
                continue
            if params.get("long_only", False) and sig["signal_type"] != "buy":
                continue

            if sig["signal_type"] and sig["sl_tp"]:
                trade_id += 1
                sl_tp = sig["sl_tp"]
                active = {
                    "trade_id":       trade_id,
                    "symbol":         symbol,
                    "signal_type":    sig["signal_type"],
                    "signal_grade":   sig["signal_grade"],
                    "entry_price":    round(sig["current_price"], 6),
                    "sl_price":       round(sl_tp["stop_loss"],   6),
                    "tp_price":       round(sl_tp.get("tp1", sl_tp.get("take_profit_1", 0)), 6),
                    "trigger_time":   ms_to_dt(bar_time_ms),
                    "trigger_bar_index": i,
                    "trend_score":    sig["trend_score"],
                    "structure_score":sig["structure_score"],
                    "momentum_score": sig["momentum_score"],
                    "composite":      sig["composite"],
                    "atr":            round(sig["atr"], 6) if sig["atr"] else None,
                    "rr_grade":       sl_tp.get("rr_grade", ""),
                }

    print()  # 換行

    # ── 若持倉未平倉，強制以最後一根收盤出場 ──
    if active:
        last_bar   = klines[-1]
        exit_price = float(last_bar[4])
        sl_dist    = abs(active["entry_price"] - active["sl_price"])
        if sl_dist > 0:
            if active["signal_type"] == "buy":
                pnl_r = round((exit_price - active["entry_price"]) / sl_dist, 3)
            else:
                pnl_r = round((active["entry_price"] - exit_price) / sl_dist, 3)
        else:
            pnl_r = 0.0

        trades.append({**active,
            "result":         "force_close",
            "exit_price":     round(exit_price, 6),
            "exit_time":      ms_to_dt(int(last_bar[0])),
            "exit_bar_index": total_bars - 1,
            "hold_bars":      total_bars - 1 - active["trigger_bar_index"],
            "pnl_r":          round(pnl_r, 3),
            "rr_ratio":       round(abs(active["tp_price"] - active["entry_price"]) / sl_dist, 2) if sl_dist > 0 else 0,
        })

    summary = _calc_summary(trades, params)
    log(f"✅ 回測完成 | {summary['total_trades']} 筆交易 | "
        f"勝率 {summary['win_rate']:.1f}% | "
        f"總 R: {summary['total_pnl_r']:+.2f} | "
        f"PF: {summary['profit_factor']:.2f}")

    return {"trades": trades, "summary": summary}


def _calc_summary(trades: list, params: dict) -> dict:
    """計算統計摘要"""
    if not trades:
        return {k: 0 for k in [
            "total_trades", "win_trades", "loss_trades", "expired_trades",
            "win_rate", "avg_rr", "total_pnl_r",
            "max_consecutive_loss", "profit_factor",
        ]}

    tp_trades  = [t for t in trades if t["result"] == "tp_hit"]
    sl_trades  = [t for t in trades if t["result"] == "sl_hit"]
    exp_trades = [t for t in trades if t["result"] in ("expired", "force_close")]

    wins   = len(tp_trades)
    losses = len(sl_trades)
    total  = len(trades)

    win_rate = round(wins / total * 100, 2) if total > 0 else 0.0

    pnl_list   = [t["pnl_r"] for t in trades]
    total_pnl  = round(sum(pnl_list), 3)
    avg_rr     = round(sum(pnl_list) / total, 3) if total > 0 else 0.0

    gross_profit = sum(p for p in pnl_list if p > 0)
    gross_loss   = abs(sum(p for p in pnl_list if p < 0))
    profit_factor = round(gross_profit / gross_loss, 3) if gross_loss > 0 else float("inf")

    # 最大連虧
    max_consec_loss = 0
    cur_loss = 0
    for t in trades:
        if t["pnl_r"] < 0:
            cur_loss += 1
            max_consec_loss = max(max_consec_loss, cur_loss)
        else:
            cur_loss = 0

    return {
        "total_trades":          total,
        "win_trades":            wins,
        "loss_trades":           losses,
        "expired_trades":        len(exp_trades),
        "win_rate":              win_rate,
        "avg_rr":                avg_rr,
        "total_pnl_r":           total_pnl,
        "max_consecutive_loss":  max_consec_loss,
        "profit_factor":         profit_factor,
        "gross_profit_r":        round(gross_profit, 3),
        "gross_loss_r":          round(gross_loss, 3),
        "params_used":           params,
    }


# ─── 輸出 ─────────────────────────────────────────────────────────────────────

def save_results(result: dict, run_id: str = None) -> str:
    """儲存至 backtest_history/"""
    os.makedirs(BACKTEST_DIR, exist_ok=True)

    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    fname = f"run_{run_id}.json"
    fpath = os.path.join(BACKTEST_DIR, fname)

    output = {
        "run_id":     run_id,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        **result
    }

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(output, f, separators=(",", ":"), ensure_ascii=False)

    # latest.json（方便快速存取）
    latest_path = os.path.join(BACKTEST_DIR, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(fpath) / 1024
    log(f"💾 已儲存 {fpath}（{size_kb:.0f} KB）")
    log(f"   快速存取: {latest_path}")
    return fpath


def export_csv(trades: list, run_id: str = None):
    """輸出 CSV"""
    os.makedirs(BACKTEST_DIR, exist_ok=True)
    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    fpath = os.path.join(BACKTEST_DIR, f"run_{run_id}.csv")
    if not trades:
        log("⚠️  沒有交易記錄，CSV 略過")
        return

    keys = list(trades[0].keys())
    with open(fpath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)

    log(f"📄 CSV 已輸出 {fpath}")


def print_summary(summary: dict):
    """美化輸出統計摘要"""
    s = summary
    pf = f"{s['profit_factor']:.2f}" if s["profit_factor"] != float("inf") else "∞"

    print()
    print("┌─────────────────────────────────────────────────────┐")
    print("│                  📊 回測統計摘要                    │")
    print("├─────────────────────────────────────────────────────┤")
    print(f"│  總交易筆數：  {s['total_trades']:>6}                                │")
    print(f"│  獲利（TP）：  {s['win_trades']:>6}   虧損（SL）：  {s['loss_trades']:>6}          │")
    print(f"│  到期收場：    {s['expired_trades']:>6}                                │")
    print(f"│  勝率：        {s['win_rate']:>6.1f}%                               │")
    print("├─────────────────────────────────────────────────────┤")
    print(f"│  平均 R:R：    {s['avg_rr']:>+7.3f}                               │")
    print(f"│  總 R 損益：   {s['total_pnl_r']:>+7.3f}  R                           │")
    print(f"│  總獲利 R：    {s['gross_profit_r']:>+7.3f}  R                           │")
    print(f"│  總虧損 R：    {s['gross_loss_r']:>+7.3f}  R                           │")
    print(f"│  獲利因子：    {pf:>7}                               │")
    print(f"│  最大連虧：    {s['max_consecutive_loss']:>6}  次                             │")
    print("└─────────────────────────────────────────────────────┘")
    print()

    # 建議
    if s["total_trades"] < 10:
        print("⚠️  樣本數不足（< 10 筆），統計意義有限，建議增加歷史資料天數")
    elif s["win_rate"] < 40:
        print("⚠️  勝率偏低（< 40%），建議提高 strong_signal_composite / min_floor")
    elif s["profit_factor"] != float("inf") and s["profit_factor"] < 1.0:
        print("⚠️  獲利因子 < 1.0，策略整體虧損，建議調整 rr_good / atr_clamp 參數")
    elif s["win_rate"] >= 50 and (s["profit_factor"] == float("inf") or s["profit_factor"] >= 1.5):
        print("✅  策略表現良好！勝率 ≥ 50% 且獲利因子 ≥ 1.5")
    else:
        print("ℹ️  策略表現尚可，可微調參數嘗試優化")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scalping Trade Analyzer — 回測引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python3 backtest_engine.py                              # 自動選最新檔案
  python3 backtest_engine.py -f history/BTCUSDT_5m_*.json
  python3 backtest_engine.py -f history/BTCUSDT_5m_*.json --run-id apr01
  python3 backtest_engine.py -f history/BTCUSDT_5m_*.json --export csv
  python3 backtest_engine.py -f history/BTCUSDT_5m_*.json --params my_params.json
        """
    )
    parser.add_argument("-f", "--file",   default=None,
                        help="歷史 K 線 JSON 路徑（預設: history/ 最新檔案）")
    parser.add_argument("--run-id",      default=None,
                        help="此次回測識別碼（預設: 時間戳記）")
    parser.add_argument("--export",      choices=["csv"],
                        help="輸出格式（目前支援: csv）")
    parser.add_argument("--params",      default=PARAMS_FILE,
                        help=f"參數表路徑（預設: {PARAMS_FILE}）")
    parser.add_argument("--no-save",     action="store_true",
                        help="不儲存結果至 backtest_history/")

    args = parser.parse_args()

    # ── 選擇歷史檔案 ──
    if args.file:
        fpath = args.file
    else:
        files = list_history_files()
        if not files:
            log(f"❌ history/ 目錄無資料，請先執行 data_fetcher.py")
            sys.exit(1)
        fpath = files[0]
        log(f"📂 自動選擇最新檔案: {fpath}")

    if not os.path.exists(fpath):
        log(f"❌ 找不到檔案: {fpath}")
        sys.exit(1)

    # ── 載入資料 ──
    log(f"📂 載入歷史資料: {fpath}")
    hist = load_history(fpath)
    klines = hist.get("klines", [])
    symbol = hist.get("symbol", "UNKNOWN")

    if not klines:
        log("❌ K 線資料為空")
        sys.exit(1)

    log(f"   {symbol} | {len(klines):,} 根 K 線 | "
        f"{hist.get('start_time', '?')} ~ {hist.get('end_time', '?')}")

    # ── 載入參數 ──
    raw_params = load_params(args.params)
    params     = flatten_params(raw_params)

    log(f"⚙️  使用參數: {args.params}")
    log(f"   weight_trend={params.get('weight_trend', 0.35)} "
        f"structure={params.get('weight_structure', 0.40)} "
        f"momentum={params.get('weight_momentum', 0.25)}")
    log(f"   強信號門檻: composite≥{params.get('strong_signal_composite', 55)} "
        f"floor≥{params.get('strong_signal_min_floor', 30)}")
    log(f"   max_hold_bars={params.get('max_hold_bars', 12)} "
        f"commission={params.get('commission_rate', 0.0004)*100:.2f}%")
    log("")

    # ── 執行回測 ──
    result = run_backtest(klines, params, symbol)

    # ── 輸出摘要 ──
    print_summary(result["summary"])

    # ── 儲存 ──
    if not args.no_save:
        run_id = args.run_id
        save_results(result, run_id)

        if args.export == "csv":
            export_csv(result["trades"], run_id)


if __name__ == "__main__":
    main()
