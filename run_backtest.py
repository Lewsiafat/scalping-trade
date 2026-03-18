#!/usr/bin/env python3
"""
完整回測執行器 — 只統計品質 ≥ 3.0★ 的確認信號
修正邏輯：確認信號出現時，檢查其品質，如果 ≥ 3.0 則開倉
"""

import sys
import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
from datetime import datetime
import math
import time
from collections import defaultdict

# 避免 app_v3 啟動伺服器
_orig_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
from app_v3 import (
    ScalpingAnalyzerPro,
    fetch_with_retry,
    validate_kline_data,
    FIXED_PARAMS,
    BINANCE_API,
    classify_error,
)
sys.argv = _orig_argv

VERSION = "CLI Backtest 1.0"
MIN_WINDOW = 150

def fetch_historical_klines(symbol, interval='5m', limit=500):
    """抓取歷史 K 線"""
    url = f"{BINANCE_API}/klines?symbol={symbol}&interval={interval}&limit={limit}"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    data = fetch_with_retry(url, ctx, max_retries=3, base_timeout=10, is_kline_req=True)
    
    if not isinstance(data, list) or len(data) < MIN_WINDOW:
        raise ValueError(f"insufficient data: got {len(data)}, need at least {MIN_WINDOW}")
    
    try:
        validate_kline_data(data)
    except Exception as e:
        pass
    
    return data

def _mock_mtf_analysis(symbol, current_interval='5m'):
    """模擬多時間框架分析"""
    return {
        'status': 'not_available',
        'higher_tf_trend': None,
        'confirmation': False,
    }

def _check_sl_tp(position, bar_high, bar_low, bar_open):
    """檢查止損/止盈是否被觸發"""
    direction = position['direction']
    sl = position['sl']
    tp1 = position['tp1']
    tp2 = position.get('tp2')
    
    if direction == 'long':
        if bar_low <= sl:
            return {'type': 'sl', 'price': sl}
        if tp2 and bar_high >= tp2:
            return {'type': 'tp2', 'price': tp2}
        if bar_high >= tp1:
            return {'type': 'tp1', 'price': tp1}
    else:
        if bar_high >= sl:
            return {'type': 'sl', 'price': sl}
        if tp2 and bar_low <= tp2:
            return {'type': 'tp2', 'price': tp2}
        if bar_low <= tp1:
            return {'type': 'tp1', 'price': tp1}
    
    return None

def run_backtest(symbol, interval='5m', limit=500, min_quality=3.0):
    """執行完整回測"""
    all_data = fetch_historical_klines(symbol, interval, limit)
    total_bars = len(all_data)
    
    trades = []
    equity_curve = []
    cumulative_pnl = 0.0
    position = None
    last_exit_bar = -999
    
    signals_list = []
    
    # 走過每根 K 線
    for bar_idx in range(MIN_WINDOW, total_bars):
        data_window = all_data[max(0, bar_idx - MIN_WINDOW):bar_idx + 1]
        bar = all_data[bar_idx]
        bar_open = float(bar[1])
        bar_high = float(bar[2])
        bar_low = float(bar[3])
        bar_close = float(bar[4])
        bar_time = int(bar[0])
        
        # === 持倉中檢查 SL/TP ===
        if position is not None:
            hit = _check_sl_tp(position, bar_high, bar_low, bar_open)
            if hit:
                exit_price = hit['price']
                direction = position['direction']
                entry_price = position['entry_price']
                
                if direction == 'long':
                    pnl_pct = (exit_price - entry_price) / entry_price * 100
                else:
                    pnl_pct = (entry_price - exit_price) / entry_price * 100
                
                cumulative_pnl += pnl_pct
                holding_bars = bar_idx - position['entry_bar_idx']
                
                trade = {
                    'id': len(trades) + 1,
                    'direction': direction,
                    'entry_time': position['entry_time'],
                    'entry_price': entry_price,
                    'exit_time': bar_time,
                    'exit_price': exit_price,
                    'exit_type': hit['type'],
                    'sl': position['sl'],
                    'tp1': position['tp1'],
                    'tp2': position.get('tp2'),
                    'pnl_pct': round(pnl_pct, 4),
                    'cumulative_pnl': round(cumulative_pnl, 4),
                    'holding_bars': holding_bars,
                    'quality_score': position['quality_score'],
                }
                trades.append(trade)
                equity_curve.append(cumulative_pnl)
                position = None
                last_exit_bar = bar_idx
        
        # === 未持倉：生成信號 ===
        if position is None and bar_idx - last_exit_bar > 0:
            # 暫時替換 MTF
            orig_mtf = ScalpingAnalyzerPro.multi_timeframe_analysis
            ScalpingAnalyzerPro.multi_timeframe_analysis = staticmethod(_mock_mtf_analysis)
            
            # 暫時替換 update_signal_state
            orig_update = ScalpingAnalyzerPro.update_signal_state
            ScalpingAnalyzerPro.update_signal_state = staticmethod(lambda *args, **kwargs: None)
            
            try:
                signals = ScalpingAnalyzerPro.analyze_entry_signal(
                    data_window, FIXED_PARAMS, symbol
                )
            finally:
                ScalpingAnalyzerPro.multi_timeframe_analysis = orig_mtf
                ScalpingAnalyzerPro.update_signal_state = orig_update
            
            quality = signals.get('quality_score', 0)
            signal_stage = signals.get('signal_stage', 'none')
            direction = signals.get('direction')
            sl = signals.get('sl')
            tp = signals.get('tp')
            
            # 只記錄確認信號
            if signal_stage == 'confirmed':
                signal_record = {
                    'bar_idx': bar_idx,
                    'time': bar_time,
                    'price': bar_close,
                    'direction': direction,
                    'quality_score': quality,
                    'rr': 0,  # 暫時
                }
                
                if quality >= min_quality and sl is not None and tp is not None and direction in ('long', 'short'):
                    # 計算 R:R
                    if direction == 'long':
                        risk = bar_close - sl
                        reward = tp - bar_close
                    else:
                        risk = sl - bar_close
                        reward = bar_close - tp
                    
                    if risk > 0 and reward > 0:
                        rr = round(reward / risk, 2)
                    else:
                        rr = 0
                    
                    signal_record['rr'] = rr
                    signals_list.append(signal_record)
                    
                    # 開倉
                    position = {
                        'direction': direction,
                        'entry_price': bar_close,
                        'entry_bar_idx': bar_idx,
                        'entry_time': bar_time,
                        'sl': sl,
                        'tp1': tp,
                        'tp2': None,
                        'quality_score': quality,
                    }
    
    # 統計
    total_signals = len(signals_list)
    total_trades = len(trades)
    
    wins = sum(1 for t in trades if t['pnl_pct'] > 0)
    losses = sum(1 for t in trades if t['pnl_pct'] < 0)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    avg_rr = sum(s['rr'] for s in signals_list) / total_signals if total_signals > 0 else 0
    
    total_profit = sum(t['pnl_pct'] for t in trades if t['pnl_pct'] > 0)
    total_loss = sum(abs(t['pnl_pct']) for t in trades if t['pnl_pct'] < 0)
    profit_factor = (total_profit / total_loss) if total_loss > 0 else 0
    
    max_dd = 0
    running_dd = 0
    for pnl in equity_curve:
        if pnl < 0:
            running_dd = min(running_dd, pnl)
            max_dd = min(max_dd, running_dd)
        else:
            running_dd = 0
    
    return {
        'trades': trades,
        'signals': signals_list,
        'stats': {
            'total_bars': total_bars,
            'total_signals': total_signals,
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 2),
            'avg_rr': round(avg_rr, 2),
            'profit_factor': round(profit_factor, 2),
            'max_dd': round(max_dd, 4),
            'cumulative_pnl': round(cumulative_pnl, 4),
            'min_quality': min_quality,
        },
    }

if __name__ == '__main__':
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    intervals = ['5m', '15m']
    min_quality = 3.0
    
    all_results = {}
    print(f"\n===== 回測執行 (品質門檻: {min_quality} 星 = 三維評分平均 ≥ 60) =====\n", flush=True)
    
    grand_total_signals = 0
    grand_total_trades = 0
    grand_wins = 0
    grand_total_profit = 0.0
    grand_total_loss = 0.0
    
    for symbol in symbols:
        all_results[symbol] = {}
        for interval in intervals:
            try:
                print(f"分析 {symbol} {interval}...", flush=True)
                result = run_backtest(symbol, interval, limit=500, min_quality=min_quality)
                all_results[symbol][interval] = result
                stats = result['stats']
                
                print(f"✓ {symbol:12} {interval:5} | 信號: {stats['total_signals']:3d} | "
                      f"交易: {stats['total_trades']:3d} | 勝率: {stats['win_rate']:6.2f}% | "
                      f"平均RR: {stats['avg_rr']:5.2f} | 利潤因子: {stats['profit_factor']:6.2f}")
                
                grand_total_signals += stats['total_signals']
                grand_total_trades += stats['total_trades']
                grand_wins += stats['wins']
                grand_total_profit += sum(t['pnl_pct'] for t in result['trades'] if t['pnl_pct'] > 0)
                grand_total_loss += sum(abs(t['pnl_pct']) for t in result['trades'] if t['pnl_pct'] < 0)
            except Exception as e:
                print(f"✗ {symbol:12} {interval:5} | 錯誤: {e}", flush=True)
                import traceback
                traceback.print_exc()
    
    print(f"\n===== 綜合統計 =====\n")
    print(f"全部交易對 & 時間框架總計:")
    print(f"  總信號數 (確認 ≥{min_quality}★): {grand_total_signals}")
    print(f"  總成交數: {grand_total_trades}")
    if grand_total_trades > 0:
        overall_win_rate = (grand_wins / grand_total_trades * 100)
        overall_profit_factor = grand_total_profit / grand_total_loss if grand_total_loss > 0 else 0
        print(f"  全局勝率: {overall_win_rate:.2f}%")
        print(f"  全局利潤因子: {overall_profit_factor:.2f}")
    print()
    
    print(f"===== 各交易對/時間框架明細 =====\n")
    for symbol in symbols:
        for interval in intervals:
            if interval not in all_results[symbol]:
                continue
            result = all_results[symbol][interval]
            stats = result['stats']
            
            print(f"{symbol:10} {interval:5} | K線: {stats['total_bars']:4d} | "
                  f"信號: {stats['total_signals']:3d} | 交易: {stats['total_trades']:3d} | "
                  f"勝率: {stats['win_rate']:6.2f}% | RR: {stats['avg_rr']:5.2f} | "
                  f"利潤: {stats['profit_factor']:6.2f} | 累計: {stats['cumulative_pnl']:+.4f}%")

