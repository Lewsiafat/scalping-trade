#!/usr/bin/env python3
"""
backtest_engine.py — 回測引擎 v2
Scalping Trade Analyzer Pro — Backtest Feedback Loop v2

用法:
    python3 backtest_engine.py                          # 自動選最新 history/ 檔案
    python3 backtest_engine.py -f history/BTCUSDT_5m_*.json
    python3 backtest_engine.py -f history/BTCUSDT_5m_*.json --run-id run01
    python3 backtest_engine.py -f history/BTCUSDT_5m_*.json --export csv

v2 改進:
    - 修復 volume_analysis（從 K 線計算，非 None）
    - 修復 MTF（5m→15m 合成，非中性佔位）
    - 修復 prev_histogram（MACD 穿越判斷）
    - SL/TP 參數實際生效（post-processing wrapper）
    - 評分權重從 params 讀取（非硬編碼）
    - 增加 max_drawdown_r / pnl_list / avg_win_r / avg_loss_r 統計
    - 預計算指標陣列，大幅提升回測速度（~20x）
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
    print(f"[ERROR] 無法 import app_v3.py: {e}")
    print("   請確認 app_v3.py 與 backtest_engine.py 在同一目錄")
    sys.exit(1)

# ─── 設定 ────────────────────────────────────────────────────────────────────

HISTORY_DIR      = "history"
BACKTEST_DIR     = "backtest_history"
PARAMS_FILE      = "backtest_params.json"

# ─── 工具函式 ─────────────────────────────────────────────────────────────────

def log(msg: str, end="\n"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", end=end, flush=True)


def ms_to_dt(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def load_params(path: str = PARAMS_FILE) -> dict:
    """載入回測參數表"""
    if not os.path.exists(path):
        log(f"找不到 {path}，使用預設值")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_history(fpath: str) -> dict:
    """載入歷史 K 線 JSON"""
    with open(fpath, "r", encoding="utf-8") as f:
        return json.load(f)


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


# ─── MTF 合成（5m → 15m）────────────────────────────────────────────────────

def _merge_candles(bucket: list) -> list:
    """合併多根 5m K 線為一根 15m K 線"""
    return [
        bucket[0][0],                                    # open_time
        bucket[0][1],                                    # open
        str(max(float(k[2]) for k in bucket)),           # high
        str(min(float(k[3]) for k in bucket)),           # low
        bucket[-1][4],                                   # close
        str(sum(float(k[5]) for k in bucket)),           # volume
        bucket[-1][6],                                   # close_time
        str(sum(float(k[7]) for k in bucket)),           # quote_vol
        str(sum(int(k[8]) for k in bucket)),             # trades
        str(sum(float(k[9]) for k in bucket)),           # taker_buy_vol
        str(sum(float(k[10]) for k in bucket)),          # taker_buy_quote_vol
        bucket[-1][11],                                  # ignore
    ]


def synthesize_mtf(klines_5m: list, ema_fast_period: int = 20,
                   ema_slow_period: int = 50) -> dict:
    """從 5m K 線合成 15m MTF 分析結果

    以 open_time 分組到 15 分鐘邊界，計算 EMA(fast)/EMA(slow) 判斷趨勢。
    回傳格式與 ScalpingAnalyzerPro.multi_timeframe_analysis() 一致。
    """
    period_ms = 15 * 60 * 1000
    candles_15m = []
    bucket = []
    bucket_key = None

    for k in klines_5m:
        open_time = int(k[0])
        key = open_time // period_ms

        if bucket_key is None:
            bucket_key = key

        if key != bucket_key:
            if bucket:
                candles_15m.append(_merge_candles(bucket))
            bucket = [k]
            bucket_key = key
        else:
            bucket.append(k)

    if bucket:
        candles_15m.append(_merge_candles(bucket))

    if len(candles_15m) < ema_slow_period:
        return {
            "timeframe": "15m", "trend": "neutral",
            "trend_strength": 0, "confirmation": False,
        }

    closes_15m = [float(c[4]) for c in candles_15m]
    ema_fast = ScalpingAnalyzerPro.calculate_ema(closes_15m, ema_fast_period)
    ema_slow = ScalpingAnalyzerPro.calculate_ema(closes_15m, ema_slow_period)

    if ema_fast and ema_slow:
        if ema_fast > ema_slow:
            trend = "uptrend"
            strength = round((ema_fast - ema_slow) / ema_slow * 100, 2)
        else:
            trend = "downtrend"
            strength = round((ema_slow - ema_fast) / ema_slow * 100, 2)
    else:
        trend = "neutral"
        strength = 0

    return {
        "timeframe": "15m",
        "trend": trend,
        "trend_strength": abs(strength),
        "ema_20": ema_fast,
        "ema_50": ema_slow,
        "confirmation": trend != "neutral",
    }


# ─── SL/TP 參數覆寫 ──────────────────────────────────────────────────────────

def _apply_sl_tp_overrides(sl_tp: dict, params: dict,
                           signal_type: str, current_price: float,
                           atr: float) -> dict:
    """對 calc_dynamic_sl_tp() 輸出套用 backtest_params 的 ATR / R:R 參數

    原始 calc_dynamic_sl_tp 使用硬編碼 ATR×1.0/2.5 和 R:R 0.7/1.0/1.5。
    此 wrapper 讀取 params 覆寫這些值，讓優化器能真正調整 SL/TP。
    """
    if sl_tp is None:
        return None

    result = dict(sl_tp)

    # ── SL 距離 clamp ──
    clamp_min = params.get("atr_clamp_min", 1.0)
    clamp_max = params.get("atr_clamp_max", 2.5)
    sl_dist = abs(current_price - result["stop_loss"])
    sl_dist = max(atr * clamp_min, min(atr * clamp_max, sl_dist))

    if signal_type == "buy":
        result["stop_loss"] = round(current_price - sl_dist, 6)
    else:
        result["stop_loss"] = round(current_price + sl_dist, 6)

    # ── TP1 最小距離 ──
    tp1_min = params.get("atr_tp1_min", 1.0)
    tp1_dist = abs(result["take_profit_1"] - current_price)
    tp1_dist = max(tp1_dist, atr * tp1_min)

    if signal_type == "buy":
        result["take_profit_1"] = round(current_price + tp1_dist, 6)
    else:
        result["take_profit_1"] = round(current_price - tp1_dist, 6)

    # ── TP2 最小距離 ──
    tp2_min = params.get("atr_tp2_min", 2.0)
    tp2_dist = abs(result["take_profit_2"] - current_price)
    tp2_dist = max(tp2_dist, atr * tp2_min)

    if signal_type == "buy":
        result["take_profit_2"] = round(current_price + tp2_dist, 6)
    else:
        result["take_profit_2"] = round(current_price - tp2_dist, 6)

    # ── 重新計算 R:R ──
    risk = sl_dist
    reward = tp1_dist
    rr = round(reward / risk, 2) if risk > 0 else 0
    extended_rr = round(tp2_dist / risk, 2) if risk > 0 else 0

    # ── R:R 分級（使用 params 門檻）──
    rr_reject = params.get("rr_reject", 0.7)
    rr_ok = params.get("rr_ok", 1.0)
    rr_good = params.get("rr_good", 1.5)

    if rr < rr_reject:
        return None  # 完全拒絕

    if rr >= rr_good:
        rr_grade = "good"
    elif rr >= rr_ok:
        rr_grade = "acceptable"
    else:
        rr_grade = "caution"

    result["risk_amount"] = round(risk, 6)
    result["reward_amount"] = round(reward, 6)
    result["risk_reward_ratio"] = rr
    result["extended_rr"] = extended_rr
    result["rr_grade"] = rr_grade
    result["atr"] = round(atr, 6)

    return result


# ─── 批量指標計算（一次遍歷全陣列）────────────────────────────────────────────

def _bulk_rsi(prices: list, period: int = 14) -> list:
    """批量計算 RSI，回傳完整陣列（Wilder's 平滑法）"""
    n = len(prices)
    result = [None] * n
    if n < period + 1:
        return result
    gains = []
    losses = []
    for i in range(1, n):
        change = prices[i] - prices[i - 1]
        gains.append(change if change > 0 else 0)
        losses.append(abs(change) if change < 0 else 0)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        result[period] = 100.0
    else:
        result[period] = round(100 - (100 / (1 + avg_gain / avg_loss)), 2)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            result[i + 1] = round(100 - (100 / (1 + avg_gain / avg_loss)), 2)
    return result


def _bulk_ema(prices: list, period: int) -> list:
    """批量計算 EMA，回傳完整陣列"""
    n = len(prices)
    result = [None] * n
    if n < period:
        return result
    mult = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    result[period - 1] = round(ema, 2)
    for i in range(period, n):
        ema = (prices[i] - ema) * mult + ema
        result[i] = round(ema, 2)
    return result


def _bulk_macd(prices: list, fast: int = 12, slow: int = 26,
               signal: int = 9) -> tuple:
    """批量計算 MACD，回傳 (macd_line[], signal_line[], histogram[])"""
    n = len(prices)
    ml = [None] * n
    sl = [None] * n
    h  = [None] * n
    if n < slow + signal:
        return ml, sl, h

    # 快 EMA 完整序列
    fast_mult = 2 / (fast + 1)
    fast_ema = sum(prices[:fast]) / fast
    fast_arr = [None] * n
    fast_arr[fast - 1] = fast_ema
    for i in range(fast, n):
        fast_ema = (prices[i] - fast_ema) * fast_mult + fast_ema
        fast_arr[i] = fast_ema

    # 慢 EMA 完整序列
    slow_mult = 2 / (slow + 1)
    slow_ema = sum(prices[:slow]) / slow
    slow_arr = [None] * n
    slow_arr[slow - 1] = slow_ema
    for i in range(slow, n):
        slow_ema = (prices[i] - slow_ema) * slow_mult + slow_ema
        slow_arr[i] = slow_ema

    # MACD line
    macd_vals = []
    macd_start = slow - 1
    for i in range(macd_start, n):
        if fast_arr[i] is not None and slow_arr[i] is not None:
            ml[i] = round(fast_arr[i] - slow_arr[i], 6)
            macd_vals.append(ml[i])
        else:
            macd_vals.append(None)

    # Signal line（MACD 的 EMA）
    sig_mult = 2 / (signal + 1)
    valid_macd = [v for v in macd_vals if v is not None]
    if len(valid_macd) < signal:
        return ml, sl, h

    sig_ema = sum(valid_macd[:signal]) / signal
    sig_start = macd_start + signal - 1
    sl[sig_start] = round(sig_ema, 6)
    h[sig_start] = round(ml[sig_start] - sig_ema, 6) if ml[sig_start] is not None else None

    idx = signal
    for i in range(sig_start + 1, n):
        if ml[i] is not None:
            sig_ema = (ml[i] - sig_ema) * sig_mult + sig_ema
            sl[i] = round(sig_ema, 6)
            h[i] = round(ml[i] - sig_ema, 6)
            idx += 1

    return ml, sl, h


def _bulk_bb(prices: list, period: int = 20, std_dev: float = 2.0) -> tuple:
    """批量計算 Bollinger Bands，回傳 (upper[], middle[], lower[])"""
    n = len(prices)
    upper = [None] * n
    middle = [None] * n
    lower = [None] * n
    if n < period:
        return upper, middle, lower
    for i in range(period - 1, n):
        seg = prices[i - period + 1:i + 1]
        sma = sum(seg) / period
        variance = sum((p - sma) ** 2 for p in seg) / period
        std = variance ** 0.5
        middle[i] = round(sma, 2)
        upper[i] = round(sma + std_dev * std, 2)
        lower[i] = round(sma - std_dev * std, 2)
    return upper, middle, lower


def _bulk_stochastic(klines: list, k_period: int = 14,
                     d_period: int = 3) -> tuple:
    """批量計算 Stochastic，回傳 (%K[], %D[])"""
    n = len(klines)
    k_arr = [None] * n
    d_arr = [None] * n
    if n < k_period:
        return k_arr, d_arr
    for i in range(k_period - 1, n):
        seg = klines[i - k_period + 1:i + 1]
        highest = max(float(k[2]) for k in seg)
        lowest  = min(float(k[3]) for k in seg)
        close   = float(klines[i][4])
        if highest != lowest:
            k_arr[i] = round((close - lowest) / (highest - lowest) * 100, 2)
        else:
            k_arr[i] = 50.0
    # %D = SMA(%K, d_period)
    for i in range(k_period - 1 + d_period - 1, n):
        vals = [k_arr[j] for j in range(i - d_period + 1, i + 1) if k_arr[j] is not None]
        if len(vals) == d_period:
            d_arr[i] = round(sum(vals) / d_period, 2)
    return k_arr, d_arr


def _bulk_atr(klines: list, period: int = 14) -> list:
    """批量計算 ATR"""
    n = len(klines)
    result = [None] * n
    if n < period + 1:
        return result
    trs = []
    for i in range(1, n):
        h = float(klines[i][2])
        l = float(klines[i][3])
        pc = float(klines[i - 1][4])
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    # 第一個 ATR = SMA(TR, period)
    atr_val = sum(trs[:period]) / period
    result[period] = round(atr_val, 6)
    for i in range(period, len(trs)):
        atr_val = (atr_val * (period - 1) + trs[i]) / period
        result[i + 1] = round(atr_val, 6)
    return result


def _bulk_volume(klines: list, window: int = 20) -> list:
    """批量計算 volume_analysis"""
    n = len(klines)
    result = [None] * n
    if n < window:
        return result
    for i in range(window - 1, n):
        seg = klines[i - window + 1:i + 1]
        result[i] = ScalpingAnalyzerPro.analyze_volume(seg)
    return result


# ─── 預計算指標陣列（效能關鍵）─────────────────────────────────────────────────

def precompute_indicators(klines: list, params: dict) -> dict:
    """一次性計算所有技術指標的完整陣列（批量版，比逐 bar 快 ~10x）

    RSI/EMA/MACD/BB/Stoch/ATR 使用批量函式單次遍歷。
    Volume 和 MTF 仍需滾動窗口但頻率較低。

    陣列長度 = len(klines)，前段不可用的值為 None。
    """
    fp = FIXED_PARAMS
    n = len(klines)
    closes = [float(k[4]) for k in klines]

    rsi_period = params.get("rsi_period", fp["rsi_period"])
    ema_fast_p = params.get("ema_fast", fp["ema_fast"])
    ema_slow_p = params.get("ema_slow", fp["ema_slow"])
    macd_fast  = params.get("macd_fast", fp["macd_fast"])
    macd_slow  = params.get("macd_slow", fp["macd_slow"])
    macd_sig   = params.get("macd_signal", fp["macd_signal"])
    atr_period = params.get("atr_period", 14)
    bb_period  = params.get("bb_period", 20)
    bb_std     = params.get("bb_std_dev", 2)
    stoch_k_p  = params.get("stoch_k_period", 14)
    stoch_d_p  = params.get("stoch_d_period", 3)
    mtf_fast   = params.get("mtf_ema_fast", 20)
    mtf_slow   = params.get("mtf_ema_slow", 50)
    rolling    = params.get("rolling_window", 200)

    # 批量指標（各一次遍歷）
    rsi_arr = _bulk_rsi(closes, rsi_period)
    ema_fast_arr = _bulk_ema(closes, ema_fast_p)
    ema_slow_arr = _bulk_ema(closes, ema_slow_p)
    macd_line_arr, signal_line_arr, histogram_arr = _bulk_macd(
        closes, macd_fast, macd_slow, macd_sig
    )
    bb_upper_arr, bb_middle_arr, bb_lower_arr = _bulk_bb(closes, bb_period, bb_std)
    stoch_k_arr, stoch_d_arr = _bulk_stochastic(klines, stoch_k_p, stoch_d_p)
    atr_arr = _bulk_atr(klines, atr_period)

    # prev_histogram = histogram[i-1]
    prev_hist_arr = [None] + histogram_arr[:-1]

    # Volume（滾動 20 bar 窗口，較快）
    vol_arr = _bulk_volume(klines, 20)

    # MTF（每 3 bar 更新一次）
    mtf_arr = [None] * n
    last_mtf = {"timeframe": "15m", "trend": "neutral", "trend_strength": 0, "confirmation": False}
    for i in range(rolling, n):
        if i % 3 == 0 or i == rolling:
            chunk = klines[max(0, i - rolling + 1):i + 1]
            last_mtf = synthesize_mtf(chunk, mtf_fast, mtf_slow)
        mtf_arr[i] = last_mtf

    return {
        "closes":       closes,
        "rsi":          rsi_arr,
        "ema_fast":     ema_fast_arr,
        "ema_slow":     ema_slow_arr,
        "macd_line":    macd_line_arr,
        "signal_line":  signal_line_arr,
        "histogram":    histogram_arr,
        "prev_histogram": prev_hist_arr,
        "bb_upper":     bb_upper_arr,
        "bb_middle":    bb_middle_arr,
        "bb_lower":     bb_lower_arr,
        "stoch_k":      stoch_k_arr,
        "stoch_d":      stoch_d_arr,
        "atr":          atr_arr,
        "volume":       vol_arr,
        "mtf":          mtf_arr,
    }


# ─── 快速信號評估（使用預計算資料）─────────────────────────────────────────────

def evaluate_signal_fast(bar_idx: int, window: list, params: dict,
                         pre: dict) -> dict:
    """使用預計算指標 + 只跑 SMC 引擎的快速信號評估

    pre: precompute_indicators() 的回傳結果
    bar_idx: 當前 bar 在完整 klines 中的索引
    window: 當前 rolling window 的 klines（供 SMC 用）
    """
    current_price = pre["closes"][bar_idx]
    rsi       = pre["rsi"][bar_idx]
    ema_fast  = pre["ema_fast"][bar_idx]
    ema_slow  = pre["ema_slow"][bar_idx]
    macd_line = pre["macd_line"][bar_idx]
    signal_line = pre["signal_line"][bar_idx]
    histogram = pre["histogram"][bar_idx]
    prev_histogram = pre["prev_histogram"][bar_idx]
    bb_upper  = pre["bb_upper"][bar_idx]
    bb_middle = pre["bb_middle"][bar_idx]
    bb_lower  = pre["bb_lower"][bar_idx]
    stoch_k   = pre["stoch_k"][bar_idx]
    stoch_d   = pre["stoch_d"][bar_idx]
    atr       = pre["atr"][bar_idx]
    volume_analysis = pre["volume"][bar_idx]
    mtf_analysis    = pre["mtf"][bar_idx]

    if any(v is None for v in [rsi, ema_fast, ema_slow, atr]):
        return {"signal_type": None, "signal_grade": None, "signal_stage": None,
                "trend_score": 50, "structure_score": 0, "momentum_score": 0,
                "composite": 0, "current_price": current_price, "atr": atr, "sl_tp": None}

    # ── SMC 引擎（必須用 window，無法預計算）──
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
    elif ema_fast is not None and ema_slow is not None:
        trend_dir = "bullish" if ema_fast > ema_slow else "bearish"

    # ── 三維評分 ──
    trend_res = ScalpingAnalyzerPro.calc_trend_score(
        bos_list, mtf_analysis, ema_fast, ema_slow, current_price,
        bb_upper, bb_middle, bb_lower
    )
    structure_res = ScalpingAnalyzerPro.calc_structure_score(
        obs, fvgs, sweeps, current_price, atr, bos_list
    )
    momentum_res = ScalpingAnalyzerPro.calc_momentum_score(
        rsi, macd_line, signal_line, histogram, stoch_k, stoch_d,
        volume_analysis, window,
        prev_histogram=prev_histogram, atr=atr,
        trend_direction=trend_dir
    )

    trend_score     = trend_res["score"]     if isinstance(trend_res, dict)     else trend_res
    structure_score = structure_res["score"]  if isinstance(structure_res, dict) else structure_res
    momentum_score  = momentum_res["score"]  if isinstance(momentum_res, dict)  else momentum_res

    # ── 加權合分 ──
    wt = params.get("weight_trend",     0.35)
    ws = params.get("weight_structure", 0.40)
    wm = params.get("weight_momentum",  0.25)
    composite = trend_score * wt + structure_score * ws + momentum_score * wm

    # ── 信號門檻 ──
    strong_comp  = params.get("strong_signal_composite",  55)
    strong_floor = params.get("strong_signal_min_floor",  30)
    strong_trend = params.get("strong_signal_trend",      55)
    normal_comp  = params.get("normal_signal_composite",  45)
    normal_floor = params.get("normal_signal_min_floor",  25)
    normal_trend = params.get("normal_signal_trend",      45)

    min_floor = min(trend_score, structure_score, momentum_score)
    signal_type  = None
    signal_grade = None
    long_only = params.get("long_only", False)
    strong_only = params.get("strong_only", False)

    if trend_score > 50:
        if composite >= strong_comp and min_floor >= strong_floor and trend_score >= strong_trend:
            signal_type, signal_grade = "buy", "strong"
        elif not strong_only and composite >= normal_comp and min_floor >= normal_floor and trend_score >= normal_trend:
            signal_type, signal_grade = "buy", "normal"
    elif trend_score < 50 and not long_only:
        bearish_strength = 100 - trend_score
        sell_composite = bearish_strength * wt + structure_score * ws + momentum_score * wm
        sell_floor = min(bearish_strength, structure_score, momentum_score)
        if sell_composite >= strong_comp and sell_floor >= strong_floor and trend_score <= (100 - strong_trend):
            signal_type, signal_grade = "sell", "strong"
        elif not strong_only and sell_composite >= normal_comp and sell_floor >= normal_floor and trend_score <= (100 - normal_trend):
            signal_type, signal_grade = "sell", "normal"
    elif trend_score == 50 and not strong_only:
        if trend_dir == "bullish" and composite >= normal_comp and min_floor >= normal_floor:
            signal_type, signal_grade = "buy", "normal"
        elif trend_dir == "bearish" and not long_only and composite >= normal_comp and min_floor >= normal_floor:
            signal_type, signal_grade = "sell", "normal"

    # ── SL/TP + 兩階段信號 ──
    sl_tp = None
    signal_stage = None

    if signal_type:
        pre_alert_triggered, _ = ScalpingAnalyzerPro.check_pre_alert(
            current_price, atr, obs, swing_pts, fvgs
        )
        if pre_alert_triggered:
            raw_sl_tp = ScalpingAnalyzerPro.calc_dynamic_sl_tp(
                current_price, atr, signal_type, obs, fvgs, swing_pts
            )
            sl_tp = _apply_sl_tp_overrides(
                raw_sl_tp, params, signal_type, current_price, atr
            )
            if sl_tp is None:
                signal_stage = "pre_alert"
                signal_type = None
            elif sl_tp.get("rr_grade") == "caution":
                signal_stage = "pre_alert"
                signal_type = None
            else:
                signal_stage = "confirmed"
        else:
            signal_stage = "pre_alert"
            signal_type = None

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


# ─── 信號評估（完整版，CLI 單次使用）────────────────────────────────────────────

def evaluate_signal(window: list, params: dict, symbol: str,
                    mtf_cache: dict = None) -> dict:
    """以一個滾動窗口的 K 線計算信號（v2: 修復所有信號缺陷）

    v2 修復:
    1. volume_analysis 從 K 線計算（非 None）
    2. MTF 從 5m 合成 15m（非中性佔位）
    3. prev_histogram 正確計算（MACD 穿越判斷）
    4. SL/TP 套用 params 參數（非硬編碼）
    5. 評分權重從 params 讀取

    回傳 dict: {signal_type, signal_grade, signal_stage, trend_score,
                structure_score, momentum_score, composite, current_price,
                atr, sl_tp}
    """
    closes = [float(k[4]) for k in window]
    current_price = closes[-1]
    fp = FIXED_PARAMS

    # ── 技術指標 ──
    rsi_period = params.get("rsi_period", fp["rsi_period"])
    ema_fast_p = params.get("ema_fast", fp["ema_fast"])
    ema_slow_p = params.get("ema_slow", fp["ema_slow"])
    macd_fast  = params.get("macd_fast", fp["macd_fast"])
    macd_slow  = params.get("macd_slow", fp["macd_slow"])
    macd_sig   = params.get("macd_signal", fp["macd_signal"])

    rsi = ScalpingAnalyzerPro.calculate_rsi(closes, rsi_period)
    ema_fast = ScalpingAnalyzerPro.calculate_ema(closes, ema_fast_p)
    ema_slow = ScalpingAnalyzerPro.calculate_ema(closes, ema_slow_p)
    macd_line, signal_line, histogram = ScalpingAnalyzerPro.calculate_macd(
        closes, macd_fast, macd_slow, macd_sig
    )

    # v2 修復: prev_histogram（與 live path 一致）
    _, _, prev_histogram = ScalpingAnalyzerPro.calculate_macd(
        closes[:-1], macd_fast, macd_slow, macd_sig
    )

    atr_period = params.get("atr_period", 14)
    atr = ScalpingAnalyzerPro.calculate_atr(window, atr_period)

    bb_period = params.get("bb_period", 20)
    bb_std = params.get("bb_std_dev", 2)
    bb_upper, bb_middle, bb_lower = ScalpingAnalyzerPro.calculate_bollinger_bands(
        closes, bb_period, bb_std
    )

    stoch_k_p = params.get("stoch_k_period", 14)
    stoch_d_p = params.get("stoch_d_period", 3)
    stoch_k, stoch_d = ScalpingAnalyzerPro.calculate_stochastic(window, stoch_k_p, stoch_d_p)

    # v2 修復: volume_analysis 從 K 線計算（非 None）
    volume_analysis = ScalpingAnalyzerPro.analyze_volume(window)

    # v2 修復: MTF 從 5m 合成 15m
    mtf_fast = params.get("mtf_ema_fast", 20)
    mtf_slow = params.get("mtf_ema_slow", 50)
    if mtf_cache is not None:
        mtf_analysis = mtf_cache
    else:
        mtf_analysis = synthesize_mtf(window, mtf_fast, mtf_slow)

    # ── SMC 引擎 ──
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
    elif ema_fast is not None and ema_slow is not None:
        trend_dir = "bullish" if ema_fast > ema_slow else "bearish"

    # ── 三維評分 ──
    trend_res = ScalpingAnalyzerPro.calc_trend_score(
        bos_list, mtf_analysis, ema_fast, ema_slow, current_price,
        bb_upper, bb_middle, bb_lower
    )
    structure_res = ScalpingAnalyzerPro.calc_structure_score(
        obs, fvgs, sweeps, current_price, atr, bos_list
    )
    momentum_res = ScalpingAnalyzerPro.calc_momentum_score(
        rsi, macd_line, signal_line, histogram, stoch_k, stoch_d,
        volume_analysis, window,
        prev_histogram=prev_histogram, atr=atr,
        trend_direction=trend_dir
    )

    trend_score     = trend_res["score"]     if isinstance(trend_res, dict)     else trend_res
    structure_score = structure_res["score"]  if isinstance(structure_res, dict) else structure_res
    momentum_score  = momentum_res["score"]  if isinstance(momentum_res, dict)  else momentum_res

    # ── 加權合分（v2: 從 params 讀取權重）──
    wt = params.get("weight_trend",     0.35)
    ws = params.get("weight_structure", 0.40)
    wm = params.get("weight_momentum",  0.25)
    composite = trend_score * wt + structure_score * ws + momentum_score * wm

    # ── 信號門檻 ──
    strong_comp  = params.get("strong_signal_composite",  55)
    strong_floor = params.get("strong_signal_min_floor",  30)
    strong_trend = params.get("strong_signal_trend",      55)
    normal_comp  = params.get("normal_signal_composite",  45)
    normal_floor = params.get("normal_signal_min_floor",  25)
    normal_trend = params.get("normal_signal_trend",      45)

    min_floor = min(trend_score, structure_score, momentum_score)
    signal_type  = None
    signal_grade = None

    # ── 方向篩選 ──
    long_only = params.get("long_only", False)
    strong_only = params.get("strong_only", False)

    if trend_score > 50:
        # 多方信號
        if composite >= strong_comp and min_floor >= strong_floor and trend_score >= strong_trend:
            signal_type, signal_grade = "buy", "strong"
        elif not strong_only and composite >= normal_comp and min_floor >= normal_floor and trend_score >= normal_trend:
            signal_type, signal_grade = "buy", "normal"
    elif trend_score < 50 and not long_only:
        # 空方信號
        bearish_strength = 100 - trend_score
        sell_composite = bearish_strength * wt + structure_score * ws + momentum_score * wm
        sell_floor = min(bearish_strength, structure_score, momentum_score)
        if sell_composite >= strong_comp and sell_floor >= strong_floor and trend_score <= (100 - strong_trend):
            signal_type, signal_grade = "sell", "strong"
        elif not strong_only and sell_composite >= normal_comp and sell_floor >= normal_floor and trend_score <= (100 - normal_trend):
            signal_type, signal_grade = "sell", "normal"
    elif trend_score == 50 and not strong_only:
        # 中性由 BOS 方向決定
        if trend_dir == "bullish" and composite >= normal_comp and min_floor >= normal_floor:
            signal_type, signal_grade = "buy", "normal"
        elif trend_dir == "bearish" and not long_only and composite >= normal_comp and min_floor >= normal_floor:
            signal_type, signal_grade = "sell", "normal"

    # ── SL/TP + 兩階段信號 ──
    sl_tp = None
    signal_stage = None

    if signal_type:
        pre_alert_triggered, _ = ScalpingAnalyzerPro.check_pre_alert(
            current_price, atr, obs, swing_pts, fvgs
        )
        if pre_alert_triggered:
            # 先用原始 calc_dynamic_sl_tp，再套用 params 覆寫
            raw_sl_tp = ScalpingAnalyzerPro.calc_dynamic_sl_tp(
                current_price, atr, signal_type, obs, fvgs, swing_pts
            )
            sl_tp = _apply_sl_tp_overrides(
                raw_sl_tp, params, signal_type, current_price, atr
            )
            if sl_tp is None:
                signal_stage = "pre_alert"
                signal_type = None
            elif sl_tp.get("rr_grade") == "caution":
                signal_stage = "pre_alert"
                signal_type = None
            else:
                signal_stage = "confirmed"
        else:
            signal_stage = "pre_alert"
            signal_type = None

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

def run_backtest(klines: list, params: dict, symbol: str,
                 quiet: bool = False, precomputed: dict = None) -> dict:
    """逐 bar 滾動回測

    v2 改進: 修復信號計算 + SL/TP 參數生效 + 增強統計 + 預計算加速

    klines: Binance 原始 K 線陣列
    params: 展平後的 backtest_params
    symbol: 交易對名稱
    quiet:  抑制進度輸出（optimizer 模式）
    precomputed: 預計算的指標陣列（若 None 則自動計算）

    回傳: {trades: [...], summary: {...}}
    """
    rolling_window = params.get("rolling_window", 200)
    min_data_bars  = params.get("min_data_bars",   50)
    max_hold_bars  = params.get("max_hold_bars",   12)
    commission     = params.get("commission_rate", 0.0004)

    total_bars = len(klines)
    if not quiet:
        log(f"回測開始 | {symbol} | {total_bars:,} 根 K 線")
        log(f"   滾動窗口: {rolling_window} | 最長持倉: {max_hold_bars or 'unlimited'} | 手續費: {commission*100:.2f}%")

    trades     = []
    trade_id   = 0
    active     = None

    start_bar = rolling_window
    if start_bar >= total_bars:
        if not quiet:
            log(f"資料不足: {total_bars} < rolling_window {rolling_window}")
        return {"trades": [], "summary": _calc_summary([], params)}

    # ── 預計算指標 ──
    if precomputed is None:
        if not quiet:
            log("預計算指標陣列...")
        pre = precompute_indicators(klines, params)
    else:
        pre = precomputed

    bar_count = total_bars - start_bar

    for i in range(start_bar, total_bars):
        if not quiet and (i - start_bar) % 2000 == 0:
            pct = (i - start_bar) / bar_count * 100
            print(f"\r   進度 {pct:5.1f}% ({i - start_bar:,}/{bar_count:,}) | "
                  f"交易筆數: {len(trades)}", end="", flush=True)

        current_bar = klines[i]
        bar_time_ms = int(current_bar[0])
        bar_high    = float(current_bar[2])
        bar_low     = float(current_bar[3])
        bar_close   = float(current_bar[4])

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
            else:
                if bar_high >= active["sl_price"]:
                    result, exit_price = "sl_hit", active["sl_price"]
                elif bar_low <= active["tp_price"]:
                    result, exit_price = "tp_hit", active["tp_price"]

            if result is None and max_hold_bars > 0 and hold_bars >= max_hold_bars:
                result, exit_price = "expired", bar_close

            if result:
                sl_dist  = abs(active["entry_price"] - active["sl_price"])
                tp_dist  = abs(active["tp_price"]    - active["entry_price"])
                rr_ratio = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0

                if result == "tp_hit":
                    pnl_r = round(rr_ratio, 3)
                elif result == "sl_hit":
                    pnl_r = -1.0
                else:
                    if active["signal_type"] == "buy":
                        pnl_r = round((exit_price - active["entry_price"]) / sl_dist, 3) if sl_dist > 0 else 0
                    else:
                        pnl_r = round((active["entry_price"] - exit_price) / sl_dist, 3) if sl_dist > 0 else 0

                # 手續費（進出場各一次）
                if sl_dist > 0 and active["entry_price"] > 0:
                    pnl_r -= commission * 2 / (sl_dist / active["entry_price"])

                trades.append({
                    **active,
                    "result":         result,
                    "exit_price":     round(exit_price, 6),
                    "exit_time":      ms_to_dt(bar_time_ms),
                    "exit_bar_index": i,
                    "hold_bars":      hold_bars,
                    "pnl_r":          round(pnl_r, 3),
                    "rr_ratio":       rr_ratio,
                })
                active = None

        # ── 尋找新訊號（使用快速路徑）──
        if active is None:
            window = klines[i - rolling_window + 1 : i + 1]
            try:
                sig = evaluate_signal_fast(i, window, params, pre)
            except Exception:
                continue

            if sig["signal_type"] and sig["sl_tp"]:
                trade_id += 1
                sl_tp = sig["sl_tp"]
                active = {
                    "trade_id":        trade_id,
                    "symbol":          symbol,
                    "signal_type":     sig["signal_type"],
                    "signal_grade":    sig["signal_grade"],
                    "entry_price":     round(sig["current_price"], 6),
                    "sl_price":        round(sl_tp["stop_loss"], 6),
                    "tp_price":        round(sl_tp.get("take_profit_1", 0), 6),
                    "trigger_time":    ms_to_dt(bar_time_ms),
                    "trigger_bar_index": i,
                    "trend_score":     sig["trend_score"],
                    "structure_score": sig["structure_score"],
                    "momentum_score":  sig["momentum_score"],
                    "composite":       sig["composite"],
                    "atr":             round(sig["atr"], 6) if sig["atr"] else None,
                    "rr_grade":        sl_tp.get("rr_grade", ""),
                }

    if not quiet:
        print()

    # ── 未平倉強制出場 ──
    if active:
        last_bar = klines[-1]
        exit_price = float(last_bar[4])
        sl_dist = abs(active["entry_price"] - active["sl_price"])
        if sl_dist > 0:
            if active["signal_type"] == "buy":
                pnl_r = round((exit_price - active["entry_price"]) / sl_dist, 3)
            else:
                pnl_r = round((active["entry_price"] - exit_price) / sl_dist, 3)
        else:
            pnl_r = 0.0

        trades.append({
            **active,
            "result":         "force_close",
            "exit_price":     round(exit_price, 6),
            "exit_time":      ms_to_dt(int(last_bar[0])),
            "exit_bar_index": total_bars - 1,
            "hold_bars":      total_bars - 1 - active["trigger_bar_index"],
            "pnl_r":          round(pnl_r, 3),
            "rr_ratio":       round(abs(active["tp_price"] - active["entry_price"]) / sl_dist, 2) if sl_dist > 0 else 0,
        })

    summary = _calc_summary(trades, params)
    if not quiet:
        log(f"回測完成 | {summary['total_trades']} 筆交易 | "
            f"勝率 {summary['win_rate']:.1f}% | "
            f"總 R: {summary['total_pnl_r']:+.2f} | "
            f"PF: {summary['profit_factor']:.2f}")

    return {"trades": trades, "summary": summary}


# ─── 統計摘要（v2 增強）─────────────────────────────────────────────────────

def _calc_max_drawdown_r(pnl_list: list) -> float:
    """計算最大回撤（R 單位）"""
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnl_list:
        equity += pnl
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
    return round(max_dd, 3)


def _calc_summary(trades: list, params: dict) -> dict:
    """計算統計摘要（v2: 增加 pnl_list / max_drawdown_r / avg_win_r / avg_loss_r）"""
    if not trades:
        return {
            "total_trades": 0, "win_trades": 0, "loss_trades": 0,
            "expired_trades": 0, "win_rate": 0.0, "avg_rr": 0.0,
            "total_pnl_r": 0.0, "max_consecutive_loss": 0,
            "profit_factor": 0.0, "gross_profit_r": 0.0, "gross_loss_r": 0.0,
            "max_drawdown_r": 0.0, "avg_win_r": 0.0, "avg_loss_r": 0.0,
            "pnl_list": [], "params_used": params,
        }

    wins   = [t for t in trades if t["pnl_r"] > 0]
    losses = [t for t in trades if t["pnl_r"] < 0]
    exp    = [t for t in trades if t["result"] in ("expired", "force_close")]
    total  = len(trades)

    pnl_list   = [t["pnl_r"] for t in trades]
    total_pnl  = round(sum(pnl_list), 3)
    win_rate   = round(len(wins) / total * 100, 2) if total > 0 else 0.0
    avg_rr     = round(total_pnl / total, 3) if total > 0 else 0.0

    gross_profit = sum(p for p in pnl_list if p > 0)
    gross_loss   = abs(sum(p for p in pnl_list if p < 0))
    profit_factor = round(gross_profit / gross_loss, 3) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    avg_win_r  = round(sum(t["pnl_r"] for t in wins) / len(wins), 3) if wins else 0.0
    avg_loss_r = round(sum(t["pnl_r"] for t in losses) / len(losses), 3) if losses else 0.0

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
        "total_trades":         total,
        "win_trades":           len(wins),
        "loss_trades":          len(losses),
        "expired_trades":       len(exp),
        "win_rate":             win_rate,
        "avg_rr":               avg_rr,
        "total_pnl_r":          total_pnl,
        "max_consecutive_loss": max_consec_loss,
        "profit_factor":        profit_factor,
        "gross_profit_r":       round(gross_profit, 3),
        "gross_loss_r":         round(gross_loss, 3),
        "max_drawdown_r":       _calc_max_drawdown_r(pnl_list),
        "avg_win_r":            avg_win_r,
        "avg_loss_r":           avg_loss_r,
        "pnl_list":             pnl_list,
        "params_used":          params,
    }


# ─── 輸出 ─────────────────────────────────────────────────────────────────────

def save_results(result: dict, run_id: str = None) -> str:
    """儲存至 backtest_history/"""
    os.makedirs(BACKTEST_DIR, exist_ok=True)

    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    fname = f"run_{run_id}.json"
    fpath = os.path.join(BACKTEST_DIR, fname)

    # 輸出時移除 pnl_list（太大），保留在 summary 的其他欄位
    output = {
        "run_id":     run_id,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "trades":     result["trades"],
        "summary":    {k: v for k, v in result["summary"].items() if k != "pnl_list"},
    }

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(output, f, separators=(",", ":"), ensure_ascii=False)

    # latest.json
    latest_path = os.path.join(BACKTEST_DIR, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(fpath) / 1024
    if not os.environ.get("BACKTEST_QUIET"):
        log(f"已儲存 {fpath}（{size_kb:.0f} KB）")
    return fpath


def export_csv(trades: list, run_id: str = None):
    """輸出 CSV"""
    os.makedirs(BACKTEST_DIR, exist_ok=True)
    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    fpath = os.path.join(BACKTEST_DIR, f"run_{run_id}.csv")
    if not trades:
        log("沒有交易記錄，CSV 略過")
        return
    keys = list(trades[0].keys())
    with open(fpath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)
    log(f"CSV 已輸出 {fpath}")


def print_summary(summary: dict):
    """美化輸出統計摘要"""
    s = summary
    pf = f"{s['profit_factor']:.2f}" if s["profit_factor"] < 99 else "INF"

    print()
    print("=" * 56)
    print("            回測統計摘要 (v2)")
    print("=" * 56)
    print(f"  總交易筆數：  {s['total_trades']:>6}")
    print(f"  獲利（TP）：  {s['win_trades']:>6}   虧損（SL）：  {s['loss_trades']:>6}")
    print(f"  到期收場：    {s['expired_trades']:>6}")
    print(f"  勝率：        {s['win_rate']:>6.1f}%")
    print("-" * 56)
    print(f"  平均 R:R：    {s['avg_rr']:>+7.3f}")
    print(f"  總 R 損益：   {s['total_pnl_r']:>+7.3f}  R")
    print(f"  總獲利 R：    {s['gross_profit_r']:>+7.3f}  R")
    print(f"  總虧損 R：    {s['gross_loss_r']:>+7.3f}  R")
    print(f"  獲利因子：    {pf:>7}")
    print(f"  最大連虧：    {s['max_consecutive_loss']:>6}  次")
    print(f"  最大回撤：    {s['max_drawdown_r']:>+7.3f}  R")
    print(f"  平均獲利 R：  {s['avg_win_r']:>+7.3f}")
    print(f"  平均虧損 R：  {s['avg_loss_r']:>+7.3f}")
    print("=" * 56)
    print()

    if s["total_trades"] < 10:
        print("  [!] 樣本數不足（< 10 筆），統計意義有限")
    elif s["profit_factor"] < 1.0:
        print("  [!] 獲利因子 < 1.0，策略整體虧損")
    elif s["win_rate"] >= 50 and s["profit_factor"] >= 1.5:
        print("  [OK] 策略表現良好")
    else:
        print("  [i] 策略表現尚可，可微調參數")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scalping Trade Analyzer — 回測引擎 v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python3 backtest_engine.py
  python3 backtest_engine.py -f history/BTCUSDT_5m_*.json
  python3 backtest_engine.py -f history/BTCUSDT_5m_*.json --run-id test01
  python3 backtest_engine.py -f history/BTCUSDT_5m_*.json --export csv
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
            log("history/ 目錄無資料，請先執行 data_fetcher.py")
            sys.exit(1)
        fpath = files[0]
        log(f"自動選擇最新檔案: {fpath}")

    if not os.path.exists(fpath):
        log(f"找不到檔案: {fpath}")
        sys.exit(1)

    # ── 載入資料 ──
    log(f"載入歷史資料: {fpath}")
    hist = load_history(fpath)
    klines = hist.get("klines", [])
    symbol = hist.get("symbol", "UNKNOWN")

    if not klines:
        log("K 線資料為空")
        sys.exit(1)

    log(f"   {symbol} | {len(klines):,} 根 K 線 | "
        f"{hist.get('start_time', '?')} ~ {hist.get('end_time', '?')}")

    # ── 載入參數 ──
    raw_params = load_params(args.params)
    params = raw_params

    log(f"使用參數: {args.params}")
    log(f"   weight: T={params.get('weight_trend', 0.35)} "
        f"S={params.get('weight_structure', 0.40)} "
        f"M={params.get('weight_momentum', 0.25)}")
    log(f"   strong: composite>={params.get('strong_signal_composite', 55)} "
        f"floor>={params.get('strong_signal_min_floor', 30)}")
    log(f"   SL/TP: clamp=[{params.get('atr_clamp_min', 1.0)}, {params.get('atr_clamp_max', 2.5)}] "
        f"tp1_min={params.get('atr_tp1_min', 1.0)}")
    log(f"   max_hold={params.get('max_hold_bars', 12)} "
        f"commission={params.get('commission_rate', 0.0004)*100:.2f}%")
    log("")

    # ── 執行回測 ──
    result = run_backtest(klines, params, symbol)
    print_summary(result["summary"])

    if not args.no_save:
        save_results(result, args.run_id)
        if args.export == "csv":
            export_csv(result["trades"], args.run_id)


if __name__ == "__main__":
    main()
