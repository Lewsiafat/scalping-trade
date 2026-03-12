#!/usr/bin/env python3
"""A/B 信號引擎對比測試

用法：
    python3 test_signal_compare.py [symbol] [interval]
    python3 test_signal_compare.py BTCUSDT 5m
    python3 test_signal_compare.py ETHUSDT 15m --loop

預設：BTCUSDT 5m
"""

import sys
import os
import time
import json
import ssl
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_v3 import ScalpingAnalyzerPro, fetch_klines_cached, FIXED_PARAMS
from signal_engine_b import evaluate_conditions


def fetch_klines(symbol, interval, limit=150):
    """直接從 Binance 抓取 K 線數據"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
        return json.loads(resp.read().decode())


def run_comparison(symbol, interval):
    """執行一次 A/B 比較"""
    params = FIXED_PARAMS

    # 抓取數據（固定 5m）
    data = fetch_klines(symbol, '5m')
    if not data or len(data) < 50:
        print(f"❌ 數據不足：僅 {len(data)} 根 K 線")
        return

    current_price = float(data[-1][4])

    # 方案 A：app_v3 改良版
    result_a = ScalpingAnalyzerPro.analyze_entry_signal(data, params, symbol)

    # 方案 B：條件累積
    result_b = evaluate_conditions(data, params, symbol)

    # 輸出
    print(f"\n{'='*60}")
    print(f"  {symbol} | {interval} | ${current_price:,.2f}")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # 對比表格
    print(f"\n{'':>14} {'方案 A (加權合分)':>20} {'方案 B (條件累積)':>20}")
    print(f"  {'─'*54}")
    print(f"  {'Signal':>12} {result_a['overall']:>20} {result_b['signal']:>20}")
    print(f"  {'Action':>12} {result_a['action']:>20} {result_b['action']:>20}")
    print(f"  {'Stage':>12} {str(result_a.get('signal_stage') or '—'):>20} {'—':>20}")

    # 方案 A 分數
    composite = result_a.get('composite_score', 0)
    min_floor = result_a.get('min_floor', 0)
    print(f"\n  ── 方案 A 明細 ──")
    print(f"  Trend:     {result_a['trend_score']:>3}")
    print(f"  Structure: {result_a['structure_score']:>3}")
    print(f"  Momentum:  {result_a['momentum_score']:>3}")
    print(f"  Composite: {composite:>5.1f}  (T×0.35 + S×0.40 + M×0.25)")
    print(f"  Min Floor: {min_floor:>3}")

    # 方案 A score_breakdown
    breakdown = result_a.get('score_breakdown', {})
    for dim in ['trend', 'structure', 'momentum']:
        details = breakdown.get(dim, [])
        if details:
            items = ', '.join(f"{d['item']}({d['points']:+d})" for d in details)
            print(f"    {dim}: {items}")

    if breakdown.get('composite_formula'):
        print(f"    formula: {breakdown['composite_formula']}")

    # R:R
    sl_tp_a = result_a.get('stop_loss_take_profit')
    if sl_tp_a:
        print(f"  R:R:       {sl_tp_a['risk_reward_ratio']} ({sl_tp_a.get('rr_grade', '—')})")
        print(f"  SL: {sl_tp_a['stop_loss']}  TP1: {sl_tp_a['take_profit_1']}  TP2: {sl_tp_a['take_profit_2']}")
    else:
        print(f"  R:R:       — (no SL/TP)")

    # SMC
    smc = result_a.get('smc', {})
    sweeps = smc.get('sweeps', [])
    if sweeps:
        sweep_info = ', '.join(f"{s['type']}({s.get('strength','full')})" for s in sweeps)
        print(f"  Sweeps:    {sweep_info}")

    # 方案 B 明細
    print(f"\n  ── 方案 B 明細 ({result_b['true_count']}/{result_b['total']}) ──")
    print(f"  Direction: {result_b['direction']}")
    for name, val in result_b['conditions'].items():
        mark = '✓' if val else '✗'
        print(f"    {mark} {name}")

    sl_tp_b = result_b.get('sl_tp')
    if sl_tp_b:
        print(f"  R:R:       {sl_tp_b['risk_reward_ratio']} ({sl_tp_b.get('rr_grade', '—')})")

    print()


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else 'BTCUSDT'
    interval = sys.argv[2] if len(sys.argv) > 2 else '5m'
    loop = '--loop' in sys.argv

    symbol = symbol.upper()
    print(f"🔍 信號引擎 A/B 對比測試")
    print(f"   Symbol: {symbol} | Interval: {interval} | Loop: {loop}")

    if loop:
        while True:
            try:
                run_comparison(symbol, interval)
                print(f"  ⏳ 10 秒後重新整理...")
                time.sleep(10)
            except KeyboardInterrupt:
                print("\n👋 結束測試")
                break
            except Exception as e:
                print(f"  ❌ 錯誤: {e}")
                time.sleep(5)
    else:
        run_comparison(symbol, interval)


if __name__ == '__main__':
    main()
