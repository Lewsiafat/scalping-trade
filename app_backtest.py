#!/usr/bin/env python3
"""
Scalping Backtest Engine V1.0
回測引擎 — 基於 ScalpingAnalyzerPro 信號引擎進行歷史數據回測

使用方式：
  python3 app_backtest.py                          # 預設 port 8081
  python3 app_backtest.py --port 9090              # 自訂 port
  python3 app_backtest.py --api-url http://host:80 # 自訂 app_v3 位址（預留）

需要 app_v3.py 在同目錄下（import ScalpingAnalyzerPro）。
"""

import http.server
import socketserver
import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
import sys
import time
import math
from datetime import datetime

# === 匯入 app_v3 的分析引擎 ===
# 暫時清除 argv 防止 app_v3 的 parse_port/parse_prefix 誤讀
_orig_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
from app_v3 import (
    ScalpingAnalyzerPro,
    fetch_with_retry,
    validate_kline_data,
    FIXED_PARAMS,
    BINANCE_API,
    BINANCE_FAPI,
    classify_error,
)
sys.argv = _orig_argv

VERSION = "2.0.0"

# MTF 時間框架映射：主圖 interval → 確認用高級 interval
MTF_INTERVAL_MAP = {
    '1m': '5m',
    '3m': '15m',
    '5m': '15m',
    '15m': '1h',
    '30m': '1h',
    '1h': '4h',
    '4h': '1d',
}


# === CLI 參數解析 ===

def parse_args():
    """解析命令列參數"""
    args = sys.argv[1:]
    config = {
        'port': 8081,
        'api_url': 'http://localhost:80',
    }
    i = 0
    while i < len(args):
        if args[i] in ('--port', '-p') and i + 1 < len(args):
            try:
                port = int(args[i + 1])
                if not (1 <= port <= 65535):
                    raise ValueError
                config['port'] = port
            except ValueError:
                print(f"❌ 無效的 port 值：{args[i + 1]}（應為 1–65535）")
                sys.exit(1)
            i += 2
        elif args[i] == '--api-url' and i + 1 < len(args):
            config['api_url'] = args[i + 1]
            i += 2
        else:
            i += 1
    return config


CONFIG = parse_args()


# === 回測引擎 ===

class BacktestEngine:
    """回測引擎：滑動窗口分析 + 交易模擬"""

    # 分析所需最小 K 線數
    MIN_WINDOW = 150

    @staticmethod
    def fetch_historical_klines(symbol, interval='5m', limit=500):
        """從 Binance 拉取歷史 K 線數據"""
        url = f"{BINANCE_API}/klines?symbol={symbol}&interval={interval}&limit={limit}"
        data = fetch_with_retry(url, is_kline_req=True)
        is_valid, data, warnings = validate_kline_data(data, min_count=BacktestEngine.MIN_WINDOW)
        if not is_valid:
            raise ValueError(warnings[0] if warnings else 'K 線數據不足')
        return data

    @staticmethod
    def _mock_mtf_analysis(symbol, current_interval='5m'):
        """回測模式下的 MTF 替代（回傳 neutral）"""
        return {
            'timeframe': '15m',
            'trend': 'neutral',
            'trend_strength': 0,
            'ema_20': None,
            'ema_50': None,
            'confirmation': False,
        }

    @staticmethod
    def analyze_bar(data_window, symbol, mtf_slice=None, mtf_interval='15m', params=None):
        """對單一窗口執行分析，回傳信號結果

        Args:
            data_window: 主圖 K 線窗口
            symbol: 交易對
            mtf_slice: 高級時間框架 K 線切片（None 時降級為 neutral mock）
            mtf_interval: MTF 時間框架字串，用於回傳 metadata
            params: 自訂指標參數（覆蓋 FIXED_PARAMS），None 時使用預設
        """
        use_params = {**FIXED_PARAMS}
        if params:
            use_params.update(params)
        orig_mtf = ScalpingAnalyzerPro.multi_timeframe_analysis
        orig_update = ScalpingAnalyzerPro.update_signal_state

        if mtf_slice and len(mtf_slice) >= 20:
            # 使用真實 MTF 歷史數據計算趨勢
            _mtf_interval = mtf_interval

            def _historical_mtf(sym, current_interval='5m'):
                closes = [float(k[4]) for k in mtf_slice]
                ema_20 = ScalpingAnalyzerPro.calculate_ema(closes, 20)
                ema_50 = ScalpingAnalyzerPro.calculate_ema(closes, min(50, len(closes)))
                if ema_20 and ema_50:
                    if ema_20 > ema_50:
                        trend = 'uptrend'
                        strength = (ema_20 - ema_50) / ema_50 * 100
                    else:
                        trend = 'downtrend'
                        strength = (ema_50 - ema_20) / ema_50 * 100
                else:
                    trend = 'neutral'
                    strength = 0
                return {
                    'timeframe': _mtf_interval,
                    'trend': trend,
                    'trend_strength': abs(round(strength, 2)),
                    'ema_20': ema_20,
                    'ema_50': ema_50,
                    'confirmation': trend != 'neutral',
                }

            ScalpingAnalyzerPro.multi_timeframe_analysis = staticmethod(_historical_mtf)
        else:
            # MTF 數據不足，降級為 neutral mock
            ScalpingAnalyzerPro.multi_timeframe_analysis = staticmethod(
                BacktestEngine._mock_mtf_analysis
            )

        # 回測中不追蹤信號狀態（每 bar 獨立分析）
        ScalpingAnalyzerPro.update_signal_state = staticmethod(
            lambda *args, **kwargs: None
        )

        try:
            signals = ScalpingAnalyzerPro.analyze_entry_signal(
                data_window, use_params, symbol
            )
            return signals
        finally:
            ScalpingAnalyzerPro.multi_timeframe_analysis = orig_mtf
            ScalpingAnalyzerPro.update_signal_state = orig_update

    @staticmethod
    def run_backtest(symbol, interval='5m', limit=500,
                     min_quality=3.0, slippage_pct=0.05, cooldown_bars=0,
                     params=None, trailing_stop=False, partial_tp=False,
                     lose_streak_pause=0, lose_streak_cooldown=10,
                     entry_mode='strong_only', require_confirmed=True,
                     allow_caution_rr=False,
                     _prefetched=None):
        """執行完整回測

        Args:
            symbol: 交易對
            interval: K 線週期
            limit: K 線數量（500 或 1000）
            min_quality: 最低品質星數門檻
            slippage_pct: 滑價百分比
            cooldown_bars: 冷卻根數（0=不啟用，持倉中不開單仍有效）
            params: 自訂指標參數（覆蓋 FIXED_PARAMS）
            trailing_stop: 啟用移動止損（TP1 後 SL 移至入場價）
            partial_tp: 啟用部分止盈（TP1 平 50%，剩餘跑 TP2）
            lose_streak_pause: 連虧 N 次後暫停（0=不啟用）
            lose_streak_cooldown: 連虧暫停後等待 M 根 K 線
            entry_mode: 入場模式 — 'strong_only'(僅強烈) | 'include_normal'(含一般)
            require_confirmed: 是否要求 signal_stage == 'confirmed'
            allow_caution_rr: 是否接受 'caution' R:R 等級
            _prefetched: 預拉取的數據 {'all_data':..., 'mtf_data':...}（優化器內部用）

        Returns:
            dict: {trades, stats, equity_curve, candles}
        """
        # 拉取主圖歷史數據（支援預拉取以避免優化器重複拉取）
        if _prefetched:
            all_data = _prefetched['all_data']
            mtf_data = _prefetched.get('mtf_data', [])
            mtf_interval = _prefetched.get('mtf_interval', MTF_INTERVAL_MAP.get(interval, '15m'))
        else:
            all_data = BacktestEngine.fetch_historical_klines(symbol, interval, limit)
            mtf_interval = MTF_INTERVAL_MAP.get(interval, '15m')
            try:
                mtf_data = BacktestEngine.fetch_historical_klines(symbol, mtf_interval, limit)
            except Exception:
                mtf_data = []

        total_bars = len(all_data)
        window_size = BacktestEngine.MIN_WINDOW
        mtf_timestamps = [int(k[0]) for k in mtf_data]

        def _get_mtf_slice(bar_open_ts):
            """取得截至 bar_open_ts 的最近 50 根 MTF K 線"""
            if not mtf_timestamps:
                return None
            lo, hi = 0, len(mtf_data) - 1
            idx = -1
            while lo <= hi:
                mid = (lo + hi) // 2
                if mtf_timestamps[mid] <= bar_open_ts:
                    idx = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            if idx < 19:  # 至少需要 20 根 MTF K 線
                return None
            return mtf_data[max(0, idx - 49):idx + 1]

        trades = []          # 已完成交易列表
        equity_curve = []    # 累計損益序列
        cumulative_pnl = 0.0

        # 持倉狀態
        position = None      # None | dict
        last_exit_bar = -999  # 上次出場的 bar index（用於 cooldown_bars）

        # 連虧保護
        consecutive_losses = 0
        lose_streak_pause_until = -999  # bar index until which trading is paused

        # 遍歷每根 K 線（從第 window_size 根開始）
        for bar_idx in range(window_size, total_bars):
            bar = all_data[bar_idx]
            bar_open = float(bar[1])
            bar_high = float(bar[2])
            bar_low = float(bar[3])
            bar_close = float(bar[4])
            bar_time = int(bar[0])

            # === 持倉中：檢查 SL/TP ===
            if position is not None:
                # 部分止盈 / Trailing Stop — 在 TP1 觸發的同 bar 只啟用，不檢查新 SL
                trailing_just_activated = False

                if partial_tp and not position.get('partial_closed'):
                    direction = position['direction']
                    hit_tp1 = (direction == 'long' and bar_high >= position['tp1']) or \
                              (direction == 'short' and bar_low <= position['tp1'])
                    if hit_tp1:
                        entry_price = position['entry_price']
                        tp1_price = position['tp1']
                        if direction == 'long':
                            partial_pnl = (tp1_price - entry_price) / entry_price * 100 * 0.5
                        else:
                            partial_pnl = (entry_price - tp1_price) / entry_price * 100 * 0.5
                        position['partial_pnl'] = partial_pnl
                        position['partial_closed'] = True
                        position['sl'] = position['entry_price']
                        position['trailing_activated'] = True
                        trailing_just_activated = True

                elif trailing_stop and not position.get('trailing_activated'):
                    direction = position['direction']
                    if direction == 'long' and bar_high >= position['tp1']:
                        position['sl'] = position['entry_price']
                        position['trailing_activated'] = True
                        trailing_just_activated = True
                    elif direction == 'short' and bar_low <= position['tp1']:
                        position['sl'] = position['entry_price']
                        position['trailing_activated'] = True
                        trailing_just_activated = True

                # 跳過剛啟用 trailing 的 bar（避免同一 bar TP1 觸發後立即被新 SL 出場）
                if trailing_just_activated:
                    equity_curve.append({
                        'time': bar_time // 1000,
                        'value': round(cumulative_pnl, 4),
                    })
                    continue

                hit = BacktestEngine._check_sl_tp(position, bar_high, bar_low, bar_open)
                if hit:
                    exit_price = hit['price']
                    direction = position['direction']
                    entry_price = position['entry_price']

                    if direction == 'long':
                        pnl_pct = (exit_price - entry_price) / entry_price * 100
                    else:
                        pnl_pct = (entry_price - exit_price) / entry_price * 100

                    # 部分止盈模式下，剩餘 50% 倉位的 PnL
                    if position.get('partial_closed'):
                        remaining_pnl = pnl_pct * 0.5
                        total_pnl = position['partial_pnl'] + remaining_pnl
                        pnl_pct = total_pnl
                        exit_type = f"partial_{hit['type']}"
                    else:
                        exit_type = hit['type']

                    # Trailing stop 類型標記
                    if position.get('trailing_activated') and not position.get('partial_closed'):
                        if hit['type'] == 'sl':
                            exit_type = 'trailing_be'  # break-even
                        elif hit['type'] in ('tp1', 'tp2'):
                            exit_type = hit['type']

                    cumulative_pnl += pnl_pct
                    holding_bars = bar_idx - position['entry_bar_idx']

                    trade = {
                        'id': len(trades) + 1,
                        'direction': direction,
                        'entry_time': position['entry_time'],
                        'entry_price': entry_price,
                        'entry_bar': position['entry_bar_idx'],
                        'exit_time': bar_time,
                        'exit_price': exit_price,
                        'exit_bar': bar_idx,
                        'exit_type': exit_type,
                        'sl': position['sl'],
                        'tp1': position['tp1'],
                        'tp2': position['tp2'],
                        'pnl_pct': round(pnl_pct, 4),
                        'cumulative_pnl': round(cumulative_pnl, 4),
                        'holding_bars': holding_bars,
                        'rr_ratio': position['rr_ratio'],
                        'quality_score': position['quality_score'],
                        'signal_label': position['signal_label'],
                    }
                    trades.append(trade)
                    last_exit_bar = bar_idx
                    position = None

                    # 連虧保護
                    if pnl_pct <= 0:
                        consecutive_losses += 1
                        if lose_streak_pause > 0 and consecutive_losses >= lose_streak_pause:
                            lose_streak_pause_until = bar_idx + lose_streak_cooldown
                            consecutive_losses = 0
                    else:
                        consecutive_losses = 0

                equity_curve.append({
                    'time': bar_time // 1000,
                    'value': round(cumulative_pnl, 4),
                })
                continue

            # === 無持倉：檢查入場信號 ===

            # CD 冷卻檢查（K 線根數）
            if cooldown_bars > 0 and (bar_idx - last_exit_bar) < cooldown_bars:
                equity_curve.append({
                    'time': bar_time // 1000,
                    'value': round(cumulative_pnl, 4),
                })
                continue

            # 連虧暫停檢查
            if bar_idx < lose_streak_pause_until:
                equity_curve.append({
                    'time': bar_time // 1000,
                    'value': round(cumulative_pnl, 4),
                })
                continue

            # 取窗口數據進行分析
            data_window = all_data[bar_idx - window_size:bar_idx]
            mtf_slice = _get_mtf_slice(bar_time)
            signals = BacktestEngine.analyze_bar(data_window, symbol, mtf_slice, mtf_interval, params)

            overall = signals.get('overall', 'neutral')
            quality = signals.get('quality_score', 0)
            sl_tp = signals.get('stop_loss_take_profit')
            signal_stage = signals.get('signal_stage')
            signal_label = signals.get('signal_label', '')

            # 入場信號等級判斷
            if entry_mode == 'include_normal':
                valid_signals = ('strong_buy', 'buy', 'strong_sell', 'sell')
            else:
                valid_signals = ('strong_buy', 'strong_sell')

            # R:R 等級判斷
            valid_rr = ('good', 'acceptable')
            if allow_caution_rr:
                valid_rr = ('good', 'acceptable', 'caution')

            # 入場條件
            can_enter = (
                overall in valid_signals
                and quality >= min_quality
                and (not require_confirmed or signal_stage == 'confirmed')
                and sl_tp is not None
                and sl_tp.get('rr_grade') in valid_rr
            )

            if can_enter:
                direction = 'long' if overall in ('strong_buy', 'buy') else 'short'
                # 入場價 = 當前 bar 收盤價 + 滑價
                if direction == 'long':
                    entry_price = bar_close * (1 + slippage_pct / 100)
                else:
                    entry_price = bar_close * (1 - slippage_pct / 100)

                position = {
                    'direction': direction,
                    'entry_price': round(entry_price, 6),
                    'entry_time': bar_time,
                    'entry_bar_idx': bar_idx,
                    'sl': sl_tp['stop_loss'],
                    'tp1': sl_tp['take_profit_1'],
                    'tp2': sl_tp['take_profit_2'],
                    'rr_ratio': sl_tp.get('risk_reward_ratio', 0),
                    'quality_score': quality,
                    'signal_label': signal_label,
                }

            equity_curve.append({
                'time': bar_time // 1000,
                'value': round(cumulative_pnl, 4),
            })

        # 若回測結束仍有持倉，以最後一根 bar 收盤價強制平倉
        if position is not None:
            last_bar = all_data[-1]
            exit_price = float(last_bar[4])
            direction = position['direction']
            entry_price = position['entry_price']

            if direction == 'long':
                pnl_pct = (exit_price - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - exit_price) / entry_price * 100

            if position.get('partial_closed'):
                remaining_pnl = pnl_pct * 0.5
                pnl_pct = position['partial_pnl'] + remaining_pnl

            cumulative_pnl += pnl_pct

            trade = {
                'id': len(trades) + 1,
                'direction': direction,
                'entry_time': position['entry_time'],
                'entry_price': entry_price,
                'entry_bar': position['entry_bar_idx'],
                'exit_time': int(last_bar[0]),
                'exit_price': exit_price,
                'exit_bar': total_bars - 1,
                'exit_type': 'force_close',
                'sl': position['sl'],
                'tp1': position['tp1'],
                'tp2': position['tp2'],
                'pnl_pct': round(pnl_pct, 4),
                'cumulative_pnl': round(cumulative_pnl, 4),
                'holding_bars': (total_bars - 1) - position['entry_bar_idx'],
                'rr_ratio': position['rr_ratio'],
                'quality_score': position['quality_score'],
                'signal_label': position['signal_label'],
            }
            trades.append(trade)
            position = None

        # 計算績效
        stats = BacktestEngine._calc_stats(trades)

        # 組裝 K 線數據供前端繪圖
        candles = []
        for k in all_data:
            candles.append({
                'time': int(k[0]) // 1000,
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
            })

        return {
            'trades': trades,
            'stats': stats,
            'equity_curve': equity_curve,
            'candles': candles,
            'config': {
                'symbol': symbol,
                'interval': interval,
                'mtf_interval': mtf_interval,
                'limit': limit,
                'min_quality': min_quality,
                'slippage_pct': slippage_pct,
                'cooldown_bars': cooldown_bars,
                'entry_mode': entry_mode,
                'require_confirmed': require_confirmed,
                'allow_caution_rr': allow_caution_rr,
                'trailing_stop': trailing_stop,
                'partial_tp': partial_tp,
                'total_bars': total_bars,
                'analyzed_bars': total_bars - window_size,
            }
        }

    @staticmethod
    def _check_sl_tp(position, bar_high, bar_low, bar_open):
        """檢查單根 K 線是否觸及 SL/TP

        同時觸及時，根據開盤價方向判斷先觸及哪個。
        使用 TP2（延伸止盈）作為止盈目標。
        """
        direction = position['direction']
        sl = position['sl']
        tp1 = position['tp1']
        tp2 = position['tp2']

        if direction == 'long':
            hit_sl = bar_low <= sl
            hit_tp2 = bar_high >= tp2
            hit_tp1 = bar_high >= tp1

            if hit_sl and hit_tp2:
                # 同時觸及：用開盤價方向判斷
                if bar_open <= sl:
                    return {'type': 'sl', 'price': sl}
                elif bar_open >= tp2:
                    return {'type': 'tp2', 'price': tp2}
                else:
                    # 開盤在中間，假設先向下觸 SL
                    return {'type': 'sl', 'price': sl}
            if hit_sl:
                return {'type': 'sl', 'price': sl}
            if hit_tp2:
                return {'type': 'tp2', 'price': tp2}
            if hit_tp1:
                return {'type': 'tp1', 'price': tp1}

        else:  # short
            hit_sl = bar_high >= sl
            hit_tp2 = bar_low <= tp2
            hit_tp1 = bar_low <= tp1

            if hit_sl and hit_tp2:
                if bar_open >= sl:
                    return {'type': 'sl', 'price': sl}
                elif bar_open <= tp2:
                    return {'type': 'tp2', 'price': tp2}
                else:
                    return {'type': 'sl', 'price': sl}
            if hit_sl:
                return {'type': 'sl', 'price': sl}
            if hit_tp2:
                return {'type': 'tp2', 'price': tp2}
            if hit_tp1:
                return {'type': 'tp1', 'price': tp1}

        return None

    @staticmethod
    def _calc_stats(trades):
        """計算績效統計"""
        if not trades:
            return {
                'total_trades': 0,
                'long_trades': 0,
                'short_trades': 0,
                'win_rate': 0,
                'long_win_rate': 0,
                'short_win_rate': 0,
                'avg_pnl': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'avg_rr': 0,
                'max_consecutive_losses': 0,
                'max_drawdown': 0,
                'total_pnl': 0,
                'avg_holding_bars': 0,
                'profit_factor': 0,
                'best_trade': 0,
                'worst_trade': 0,
            }

        total = len(trades)
        long_trades = [t for t in trades if t['direction'] == 'long']
        short_trades = [t for t in trades if t['direction'] == 'short']

        wins = [t for t in trades if t['pnl_pct'] > 0]
        losses = [t for t in trades if t['pnl_pct'] <= 0]
        long_wins = [t for t in long_trades if t['pnl_pct'] > 0]
        short_wins = [t for t in short_trades if t['pnl_pct'] > 0]

        win_rate = len(wins) / total * 100 if total > 0 else 0
        long_win_rate = len(long_wins) / len(long_trades) * 100 if long_trades else 0
        short_win_rate = len(short_wins) / len(short_trades) * 100 if short_trades else 0

        avg_pnl = sum(t['pnl_pct'] for t in trades) / total
        avg_win = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t['pnl_pct'] for t in losses) / len(losses) if losses else 0
        avg_rr = sum(t['rr_ratio'] for t in trades) / total

        # 最大連續虧損
        max_consecutive = 0
        current_consecutive = 0
        for t in trades:
            if t['pnl_pct'] <= 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0

        # 最大回撤
        peak = 0
        max_dd = 0
        cum = 0
        for t in trades:
            cum += t['pnl_pct']
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        total_pnl = sum(t['pnl_pct'] for t in trades)
        avg_holding = sum(t['holding_bars'] for t in trades) / total

        # Profit Factor
        gross_profit = sum(t['pnl_pct'] for t in wins) if wins else 0
        gross_loss = abs(sum(t['pnl_pct'] for t in losses)) if losses else 0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (
            float('inf') if gross_profit > 0 else 0
        )

        pnl_values = [t['pnl_pct'] for t in trades]

        # 按出場類型統計
        exit_type_stats = {}
        for t in trades:
            et = t['exit_type']
            if et not in exit_type_stats:
                exit_type_stats[et] = {'count': 0, 'pnl': 0}
            exit_type_stats[et]['count'] += 1
            exit_type_stats[et]['pnl'] = round(exit_type_stats[et]['pnl'] + t['pnl_pct'], 4)

        return {
            'total_trades': total,
            'long_trades': len(long_trades),
            'short_trades': len(short_trades),
            'win_rate': round(win_rate, 1),
            'long_win_rate': round(long_win_rate, 1),
            'short_win_rate': round(short_win_rate, 1),
            'avg_pnl': round(avg_pnl, 4),
            'avg_win': round(avg_win, 4),
            'avg_loss': round(avg_loss, 4),
            'avg_rr': round(avg_rr, 2),
            'max_consecutive_losses': max_consecutive,
            'max_drawdown': round(max_dd, 4),
            'total_pnl': round(total_pnl, 4),
            'avg_holding_bars': round(avg_holding, 1),
            'profit_factor': profit_factor if profit_factor != float('inf') else 999.99,
            'best_trade': round(max(pnl_values), 4),
            'worst_trade': round(min(pnl_values), 4),
            'exit_type_stats': exit_type_stats,
        }


# === 參數優化引擎 ===

class ParameterOptimizer:
    """網格搜尋參數優化器 — 在預拉取數據上跑多組參數組合"""

    # 預設搜尋範圍
    # 注意：EMA/RSI 對 SMC 信號影響極小，預設只搜尋 1 組指標參數
    # 主要優化方向：入場條件 + 品質門檻
    DEFAULT_GRID = {
        'ema_fast': [9],
        'ema_slow': [21],
        'rsi_period': [14],
        'min_quality': [2.0, 2.5, 3.0, 3.5, 4.0],
        'entry_mode': ['strong_only', 'include_normal'],
        'require_confirmed': [True, False],
        'allow_caution_rr': [False, True],
    }

    @staticmethod
    def generate_combinations(grid):
        """產生所有參數組合（笛卡爾積）"""
        keys = sorted(grid.keys())
        values = [grid[k] for k in keys]
        combos = [{}]
        for key, vals in zip(keys, values):
            new_combos = []
            for combo in combos:
                for v in vals:
                    c = dict(combo)
                    c[key] = v
                    new_combos.append(c)
            combos = new_combos
        return combos

    @staticmethod
    def run_optimization(symbol, interval='5m', limit=500, grid=None,
                         slippage_pct=0.05, cooldown_bars=0,
                         trailing_stop=False, partial_tp=False,
                         lose_streak_pause=0, lose_streak_cooldown=10):
        """執行參數優化

        Args:
            symbol: 交易對
            interval: K 線週期
            limit: K 線數量
            grid: 搜尋範圍 dict（None 時用 DEFAULT_GRID）
            其他參數同 run_backtest

        Returns:
            dict: {results: [...top10], total_combinations, data_info}
        """
        if grid is None:
            grid = ParameterOptimizer.DEFAULT_GRID

        # 分離 backtest 過濾參數 vs 指標參數
        backtest_keys = {'min_quality', 'cooldown_bars', 'slippage_pct',
                         'entry_mode', 'require_confirmed', 'allow_caution_rr'}

        # 預拉取數據（只拉一次）
        all_data = BacktestEngine.fetch_historical_klines(symbol, interval, limit)
        mtf_interval = MTF_INTERVAL_MAP.get(interval, '15m')
        try:
            mtf_data = BacktestEngine.fetch_historical_klines(symbol, mtf_interval, limit)
        except Exception:
            mtf_data = []

        prefetched = {
            'all_data': all_data,
            'mtf_data': mtf_data,
            'mtf_interval': mtf_interval,
        }

        # 產生所有組合
        all_combos = ParameterOptimizer.generate_combinations(grid)
        total = len(all_combos)

        results = []
        for i, combo in enumerate(all_combos):
            # 分離指標參數和過濾參數
            ind_params = {k: v for k, v in combo.items() if k not in backtest_keys}
            mq = combo.get('min_quality', 3.0)
            cd = combo.get('cooldown_bars', cooldown_bars)
            sp = combo.get('slippage_pct', slippage_pct)
            em = combo.get('entry_mode', 'strong_only')
            rc = combo.get('require_confirmed', True)
            acr = combo.get('allow_caution_rr', False)

            try:
                result = BacktestEngine.run_backtest(
                    symbol=symbol, interval=interval, limit=limit,
                    min_quality=mq, slippage_pct=sp, cooldown_bars=cd,
                    params=ind_params if ind_params else None,
                    trailing_stop=trailing_stop, partial_tp=partial_tp,
                    lose_streak_pause=lose_streak_pause,
                    lose_streak_cooldown=lose_streak_cooldown,
                    entry_mode=em, require_confirmed=rc, allow_caution_rr=acr,
                    _prefetched=prefetched,
                )
                stats = result['stats']

                # 過濾：至少 5 筆交易
                if stats['total_trades'] < 5:
                    continue

                # 計算排序指標
                pf = stats['profit_factor']
                pnl = stats['total_pnl']
                dd = stats['max_drawdown']
                dd_ratio = pnl / dd if dd > 0 else (999.0 if pnl > 0 else 0)

                results.append({
                    'rank': 0,
                    'params': combo,
                    'stats': stats,
                    'score': round(dd_ratio, 2),
                    'profit_factor': pf,
                    'total_pnl': round(pnl, 4),
                    'max_drawdown': round(dd, 4),
                    'win_rate': stats['win_rate'],
                    'total_trades': stats['total_trades'],
                })
            except Exception:
                continue

        # 排序：PnL/DD ratio 為主，Profit Factor 為次
        results.sort(key=lambda r: (r['score'], r['profit_factor']), reverse=True)

        # 取 Top 10
        top_results = results[:10]
        for i, r in enumerate(top_results):
            r['rank'] = i + 1

        return {
            'results': top_results,
            'total_combinations': total,
            'valid_combinations': len(results),
            'data_info': {
                'symbol': symbol,
                'interval': interval,
                'mtf_interval': mtf_interval,
                'total_bars': len(all_data),
                'analyzed_bars': len(all_data) - BacktestEngine.MIN_WINDOW,
            }
        }


# === HTTP Handler ===

class BacktestHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            html = HTML_PAGE.replace('V{VERSION}', f'V{VERSION}')
            self.wfile.write(html.encode('utf-8'))
        elif self.path.startswith('/api/optimize'):
            self.handle_optimize()
        elif self.path.startswith('/api/backtest'):
            self.handle_backtest()
        else:
            self.send_error(404)

    def handle_backtest(self):
        """處理回測請求"""
        try:
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)

            symbol = params.get('symbol', ['BTCUSDT'])[0].upper()
            interval = params.get('interval', ['5m'])[0]
            limit = int(params.get('limit', ['500'])[0])
            min_quality = float(params.get('min_quality', ['3.0'])[0])
            slippage_pct = float(params.get('slippage_pct', ['0.05'])[0])
            cooldown_bars = int(params.get('cooldown_bars', ['0'])[0])
            trailing_stop = params.get('trailing_stop', ['0'])[0] == '1'
            partial_tp = params.get('partial_tp', ['0'])[0] == '1'
            lose_streak_pause = int(params.get('lose_streak_pause', ['0'])[0])
            lose_streak_cooldown = int(params.get('lose_streak_cooldown', ['10'])[0])
            entry_mode = params.get('entry_mode', ['strong_only'])[0]
            require_confirmed = params.get('require_confirmed', ['1'])[0] == '1'
            allow_caution_rr = params.get('allow_caution_rr', ['0'])[0] == '1'

            # 自訂指標參數
            custom_params = {}
            for key in ('ema_fast', 'ema_slow', 'rsi_period', 'rsi_overbought',
                        'rsi_oversold', 'macd_fast', 'macd_slow', 'macd_signal'):
                if key in params:
                    custom_params[key] = int(params[key][0])

            # 限制範圍
            limit = max(200, min(1000, limit))
            min_quality = max(0, min(5, min_quality))
            slippage_pct = max(0, min(1.0, slippage_pct))
            cooldown_bars = max(0, min(100, cooldown_bars))
            lose_streak_pause = max(0, min(20, lose_streak_pause))
            lose_streak_cooldown = max(0, min(50, lose_streak_cooldown))

            result = BacktestEngine.run_backtest(
                symbol=symbol,
                interval=interval,
                limit=limit,
                min_quality=min_quality,
                slippage_pct=slippage_pct,
                cooldown_bars=cooldown_bars,
                params=custom_params if custom_params else None,
                trailing_stop=trailing_stop,
                partial_tp=partial_tp,
                lose_streak_pause=lose_streak_pause,
                lose_streak_cooldown=lose_streak_cooldown,
                entry_mode=entry_mode,
                require_confirmed=require_confirmed,
                allow_caution_rr=allow_caution_rr,
            )

            response = {
                'success': True,
                'timestamp': datetime.now().isoformat(),
                **result,
            }

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

        except Exception as e:
            error_info = classify_error(e)
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'error': error_info.get('error', str(e)),
                'error_type': error_info.get('error_type', 'unknown'),
            }, ensure_ascii=False).encode('utf-8'))

    def handle_optimize(self):
        """處理參數優化請求"""
        try:
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)

            symbol = params.get('symbol', ['BTCUSDT'])[0].upper()
            interval = params.get('interval', ['5m'])[0]
            limit = int(params.get('limit', ['500'])[0])
            slippage_pct = float(params.get('slippage_pct', ['0.05'])[0])
            cooldown_bars = int(params.get('cooldown_bars', ['0'])[0])
            trailing_stop = params.get('trailing_stop', ['0'])[0] == '1'
            partial_tp = params.get('partial_tp', ['0'])[0] == '1'

            # 限制範圍
            limit = max(200, min(1000, limit))
            slippage_pct = max(0, min(1.0, slippage_pct))

            # 自訂搜尋範圍（用逗號分隔）
            grid = {}
            grid_mappings = {
                'grid_ema_fast': ('ema_fast', int),
                'grid_ema_slow': ('ema_slow', int),
                'grid_rsi_period': ('rsi_period', int),
                'grid_min_quality': ('min_quality', float),
            }
            for param_key, (grid_key, cast_fn) in grid_mappings.items():
                if param_key in params:
                    try:
                        grid[grid_key] = [cast_fn(v.strip()) for v in params[param_key][0].split(',')]
                    except ValueError:
                        pass

            # 合併自訂 grid 和預設 grid（自訂覆蓋預設）
            merged_grid = dict(ParameterOptimizer.DEFAULT_GRID)
            if grid:
                merged_grid.update(grid)

            result = ParameterOptimizer.run_optimization(
                symbol=symbol, interval=interval, limit=limit,
                grid=merged_grid,
                slippage_pct=slippage_pct, cooldown_bars=cooldown_bars,
                trailing_stop=trailing_stop, partial_tp=partial_tp,
            )

            response = {
                'success': True,
                'timestamp': datetime.now().isoformat(),
                **result,
            }

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

        except Exception as e:
            error_info = classify_error(e)
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'error': error_info.get('error', str(e)),
                'error_type': error_info.get('error_type', 'unknown'),
            }, ensure_ascii=False).encode('utf-8'))

    def log_message(self, format, *args):
        """安靜模式：只記錄 API 請求"""
        if '/api/' in str(args[0]) if args else False:
            super().log_message(format, *args)


# === Frontend HTML ===

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Scalping Backtest Engine V{VERSION}</title>
    <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a2e;
            --bg-input: #16213e;
            --border: #2a2a4a;
            --text-primary: #e0e0e0;
            --text-secondary: #8888aa;
            --accent: #6c63ff;
            --accent-hover: #7b73ff;
            --green: #00c853;
            --green-dim: #00c85340;
            --red: #ff1744;
            --red-dim: #ff174440;
            --orange: #ff9800;
            --blue: #2196f3;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }

        /* === Header === */
        .header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .header h1 {
            font-size: 16px;
            font-weight: 600;
            color: var(--accent);
        }
        .header .version {
            font-size: 12px;
            color: var(--text-secondary);
        }

        /* === Control Panel === */
        .control-panel {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
            padding: 16px 24px;
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            align-items: flex-end;
        }
        .control-group {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .control-group label {
            font-size: 11px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .control-group input,
        .control-group select {
            background: var(--bg-input);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 13px;
            font-family: inherit;
            outline: none;
            transition: border-color 0.2s;
        }
        .control-group input:focus,
        .control-group select:focus {
            border-color: var(--accent);
        }
        .control-group input[type="number"] { width: 80px; }
        .control-group select { min-width: 120px; }

        .btn-run {
            background: var(--accent);
            color: white;
            border: none;
            padding: 8px 24px;
            border-radius: 6px;
            font-size: 13px;
            font-family: inherit;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            height: 35px;
        }
        .btn-run:hover { background: var(--accent-hover); filter: brightness(1.1); }
        .btn-run:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        /* === Main Content === */
        .main-content {
            padding: 20px 24px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        /* === Stats Cards === */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            gap: 12px;
        }
        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 14px;
            text-align: center;
        }
        .stat-card .label {
            font-size: 11px;
            color: var(--text-secondary);
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .stat-card .value {
            font-size: 20px;
            font-weight: 700;
        }
        .stat-card .value.positive { color: var(--green); }
        .stat-card .value.negative { color: var(--red); }
        .stat-card .sub {
            font-size: 11px;
            color: var(--text-secondary);
            margin-top: 4px;
        }

        /* === Charts === */
        .chart-section {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
        }
        .chart-header {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border);
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
        }
        .chart-container {
            width: 100%;
            height: 400px;
        }
        .equity-chart-container {
            width: 100%;
            height: 250px;
        }

        /* === Trade Table === */
        .trade-table-section {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
        }
        .trade-table-header {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .trade-table-header span {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
        }
        .trade-table-wrap {
            max-height: 400px;
            overflow-y: auto;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }
        thead th {
            position: sticky;
            top: 0;
            background: var(--bg-secondary);
            padding: 10px 8px;
            text-align: center;
            color: var(--text-secondary);
            font-weight: 500;
            border-bottom: 1px solid var(--border);
            white-space: nowrap;
        }
        tbody td {
            padding: 8px;
            text-align: center;
            border-bottom: 1px solid var(--border);
            white-space: nowrap;
        }
        tbody tr:hover {
            background: rgba(108, 99, 255, 0.05);
        }
        .dir-long { color: var(--green); font-weight: 600; }
        .dir-short { color: var(--red); font-weight: 600; }
        .pnl-pos { color: var(--green); }
        .pnl-neg { color: var(--red); }
        .exit-sl { color: var(--red); }
        .exit-tp { color: var(--green); }
        .exit-force { color: var(--orange); }

        /* === Empty State === */
        .empty-state {
            text-align: center;
            padding: 80px 20px;
            color: var(--text-secondary);
        }
        .empty-state h2 {
            font-size: 18px;
            margin-bottom: 8px;
            color: var(--text-primary);
        }
        .empty-state p {
            font-size: 13px;
        }

        /* === Loading === */
        .loading-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.7);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            flex-direction: column;
            gap: 16px;
        }
        .loading-overlay.active { display: flex; }
        .spinner {
            width: 40px; height: 40px;
            border: 3px solid var(--border);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .loading-text {
            color: var(--text-secondary);
            font-size: 14px;
        }
        .loading-progress {
            color: var(--accent);
            font-size: 12px;
        }

        /* === Toast === */
        .toast {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 8px;
            font-size: 13px;
            z-index: 2000;
            animation: slideIn 0.3s ease;
            max-width: 400px;
        }
        .toast.error {
            background: var(--red-dim);
            border: 1px solid var(--red);
            color: var(--red);
        }
        .toast.success {
            background: var(--green-dim);
            border: 1px solid var(--green);
            color: var(--green);
        }
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }

        /* Scrollbar */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: var(--bg-secondary); }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
    </style>
</head>
<body>

<div class="header">
    <h1>Scalping Backtest Engine</h1>
    <span class="version">V{VERSION}</span>
</div>

<div class="control-panel">
    <div class="control-group">
        <label>交易對 Symbol</label>
        <select id="symbol">
            <option value="BTCUSDT">BTC/USDT</option>
            <option value="ETHUSDT">ETH/USDT</option>
            <option value="BNBUSDT">BNB/USDT</option>
            <option value="SOLUSDT">SOL/USDT</option>
            <option value="DOGEUSDT">DOGE/USDT</option>
            <option value="XRPUSDT">XRP/USDT</option>
            <option value="ADAUSDT">ADA/USDT</option>
            <option value="AVAXUSDT">AVAX/USDT</option>
        </select>
    </div>
    <div class="control-group">
        <label>自訂交易對</label>
        <input type="text" id="customSymbol" placeholder="如 PEPEUSDT" style="width:120px;">
    </div>
    <div class="control-group">
        <label>時間週期</label>
        <select id="interval">
            <option value="1m">1m</option>
            <option value="3m">3m</option>
            <option value="5m" selected>5m</option>
            <option value="15m">15m</option>
            <option value="30m">30m</option>
            <option value="1h">1h</option>
            <option value="4h">4h</option>
        </select>
    </div>
    <div class="control-group">
        <label>K 線數量</label>
        <select id="limit">
            <option value="500">500</option>
            <option value="750">750</option>
            <option value="1000" selected>1000</option>
        </select>
    </div>
    <div class="control-group">
        <label>最低星數</label>
        <input type="number" id="minQuality" value="3" min="1" max="5" step="0.5">
    </div>
    <div class="control-group">
        <label>滑價 %</label>
        <input type="number" id="slippage" value="0.05" min="0" max="1" step="0.01">
    </div>
    <div class="control-group">
        <label>CD 根數</label>
        <input type="number" id="cooldownBars" value="0" min="0" max="100" step="1">
    </div>
    <div class="control-group">
        <label>入場模式</label>
        <select id="entryMode">
            <option value="strong_only">僅強烈信號</option>
            <option value="include_normal">含一般信號</option>
        </select>
    </div>
    <div class="control-group">
        <label>需 Confirmed</label>
        <select id="requireConfirmed">
            <option value="1">是</option>
            <option value="0">否</option>
        </select>
    </div>
    <div class="control-group">
        <label>接受 Caution RR</label>
        <select id="allowCautionRR">
            <option value="0">否</option>
            <option value="1">是</option>
        </select>
    </div>
    <div class="control-group">
        <label>Trailing Stop</label>
        <select id="trailingStop">
            <option value="0">關閉</option>
            <option value="1">開啟</option>
        </select>
    </div>
    <div class="control-group">
        <label>部分止盈</label>
        <select id="partialTp">
            <option value="0">關閉</option>
            <option value="1">開啟</option>
        </select>
    </div>
    <div class="control-group">
        <label>連虧暫停</label>
        <input type="number" id="loseStreakPause" value="0" min="0" max="20" step="1" title="連續虧損 N 次後暫停（0=不啟用）">
    </div>
    <div class="control-group">
        <label>暫停根數</label>
        <input type="number" id="loseStreakCooldown" value="10" min="1" max="50" step="1" title="連虧暫停後等待 M 根 K 線">
    </div>
    <button class="btn-run" id="btnRun" onclick="runBacktest()">開始回測</button>
    <button class="btn-run" id="btnOptimize" onclick="runOptimize()" style="background:#ff9800;">參數優化</button>
</div>

<div class="main-content" id="mainContent">
    <div class="empty-state" id="emptyState">
        <h2>Scalping Backtest Engine</h2>
        <p>設定參數後按「開始回測」，系統將對歷史 K 線數據進行信號回測分析</p>
        <p style="margin-top:8px; font-size:11px; color:var(--text-secondary);">
            引擎版本 V{VERSION} — 基於 ScalpingAnalyzerPro SMC 信號引擎
        </p>
    </div>
</div>

<div class="loading-overlay" id="loading">
    <div class="spinner"></div>
    <div class="loading-text">回測分析中...</div>
    <div class="loading-progress" id="loadingProgress">正在拉取歷史數據</div>
</div>

<script>
// === 全域狀態 ===
let backtestResult = null;
let klineChart = null;
let equityChart = null;

// === Toast 通知 ===
function showToast(msg, type = 'error') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// === 時間格式化 ===
function formatTime(ts) {
    const d = new Date(ts);
    return d.toLocaleDateString('zh-TW', {month:'2-digit', day:'2-digit'})
        + ' ' + d.toLocaleTimeString('zh-TW', {hour:'2-digit', minute:'2-digit', hour12:false});
}

// === 執行回測 ===
async function runBacktest() {
    const btn = document.getElementById('btnRun');
    const loading = document.getElementById('loading');
    btn.disabled = true;
    loading.classList.add('active');

    const customSym = document.getElementById('customSymbol').value.trim().toUpperCase();
    const symbol = customSym || document.getElementById('symbol').value;
    const interval = document.getElementById('interval').value;
    const limit = document.getElementById('limit').value;
    const minQuality = document.getElementById('minQuality').value;
    const slippage = document.getElementById('slippage').value;
    const cooldownBars = document.getElementById('cooldownBars').value;

    const entryMode = document.getElementById('entryMode').value;
    const requireConfirmed = document.getElementById('requireConfirmed').value;
    const allowCautionRR = document.getElementById('allowCautionRR').value;
    const trailingStop = document.getElementById('trailingStop').value;
    const partialTp = document.getElementById('partialTp').value;
    const loseStreakPause = document.getElementById('loseStreakPause').value;
    const loseStreakCooldown = document.getElementById('loseStreakCooldown').value;

    const params = new URLSearchParams({
        symbol, interval, limit, min_quality: minQuality,
        slippage_pct: slippage, cooldown_bars: cooldownBars,
        entry_mode: entryMode, require_confirmed: requireConfirmed,
        allow_caution_rr: allowCautionRR,
        trailing_stop: trailingStop, partial_tp: partialTp,
        lose_streak_pause: loseStreakPause, lose_streak_cooldown: loseStreakCooldown
    });

    // 套用優化器選定的自訂參數
    if (window._customParams) {
        const cp = window._customParams;
        if (cp.ema_fast) params.set('ema_fast', cp.ema_fast);
        if (cp.ema_slow) params.set('ema_slow', cp.ema_slow);
        if (cp.rsi_period) params.set('rsi_period', cp.rsi_period);
    }

    try {
        document.getElementById('loadingProgress').textContent = `正在回測 ${symbol} ${interval} (${limit} 根 K 線)...`;
        const resp = await fetch(`/api/backtest?${params}`);
        const data = await resp.json();

        if (!data.success) {
            showToast(data.error || '回測失敗', 'error');
            return;
        }

        backtestResult = data;
        renderResults(data);
        showToast(`回測完成：${data.stats.total_trades} 筆交易`, 'success');

    } catch (err) {
        showToast('回測請求失敗: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        loading.classList.remove('active');
    }
}

// === 渲染結果 ===
function renderResults(data) {
    const { stats, trades, equity_curve, candles, config } = data;
    const container = document.getElementById('mainContent');

    container.innerHTML = '';

    // 1. 設定摘要
    const configInfo = document.createElement('div');
    configInfo.style.cssText = 'font-size:12px; color:var(--text-secondary); padding:4px 0;';
    const features = [];
    if (config.trailing_stop) features.push('TS');
    if (config.partial_tp) features.push('PT');
    if (config.entry_mode === 'include_normal') features.push('含一般信號');
    if (!config.require_confirmed) features.push('不需Confirmed');
    if (config.allow_caution_rr) features.push('含Caution RR');
    const featureStr = features.length > 0 ? ` | ${features.join(' + ')}` : '';
    configInfo.textContent = `${config.symbol} | ${config.interval} (MTF: ${config.mtf_interval}) | ${config.total_bars} 根 K 線 | 分析 ${config.analyzed_bars} 根 | Q≥${config.min_quality} | 滑價 ${config.slippage_pct}%${featureStr}`;
    container.appendChild(configInfo);

    // 2. 績效統計卡片
    renderStats(container, stats);

    // 3. K 線圖
    renderKlineChart(container, candles, trades);

    // 4. Equity Curve
    renderEquityCurve(container, equity_curve);

    // 5. 交易明細表
    renderTradeTable(container, trades);
}

// === 績效統計卡片 ===
function renderStats(container, s) {
    const grid = document.createElement('div');
    grid.className = 'stats-grid';

    const cards = [
        { label: '總交易數', value: s.total_trades, sub: `多 ${s.long_trades} / 空 ${s.short_trades}` },
        { label: '勝率', value: s.win_rate + '%', cls: s.win_rate >= 50 ? 'positive' : 'negative',
          sub: `多 ${s.long_win_rate}% / 空 ${s.short_win_rate}%` },
        { label: '總損益', value: s.total_pnl.toFixed(2) + '%', cls: s.total_pnl >= 0 ? 'positive' : 'negative' },
        { label: '平均損益', value: s.avg_pnl.toFixed(3) + '%', cls: s.avg_pnl >= 0 ? 'positive' : 'negative' },
        { label: '平均盈利', value: s.avg_win.toFixed(3) + '%', cls: 'positive' },
        { label: '平均虧損', value: s.avg_loss.toFixed(3) + '%', cls: 'negative' },
        { label: '平均 R:R', value: s.avg_rr.toFixed(2), cls: s.avg_rr >= 1.5 ? 'positive' : '' },
        { label: 'Profit Factor', value: s.profit_factor, cls: s.profit_factor >= 1 ? 'positive' : 'negative' },
        { label: '最大連續虧損', value: s.max_consecutive_losses, cls: 'negative' },
        { label: '最大回撤', value: s.max_drawdown.toFixed(2) + '%', cls: 'negative' },
        { label: '最佳單筆', value: s.best_trade.toFixed(3) + '%', cls: 'positive' },
        { label: '最差單筆', value: s.worst_trade.toFixed(3) + '%', cls: 'negative' },
        { label: '平均持倉', value: s.avg_holding_bars.toFixed(1) + ' 根' },
    ];

    for (const c of cards) {
        const card = document.createElement('div');
        card.className = 'stat-card';
        card.innerHTML = `
            <div class="label">${c.label}</div>
            <div class="value ${c.cls || ''}">${c.value}</div>
            ${c.sub ? `<div class="sub">${c.sub}</div>` : ''}
        `;
        grid.appendChild(card);
    }
    container.appendChild(grid);
}

// === K 線圖 + 買賣點標記 ===
function renderKlineChart(container, candles, trades) {
    const section = document.createElement('div');
    section.className = 'chart-section';
    section.innerHTML = `<div class="chart-header">K 線圖 + 買賣點標記</div><div class="chart-container" id="klineChart"></div>`;
    container.appendChild(section);

    const chartEl = section.querySelector('#klineChart');

    if (klineChart) { klineChart.remove(); klineChart = null; }

    const chart = LightweightCharts.createChart(chartEl, {
        width: chartEl.clientWidth,
        height: 400,
        layout: { background: { color: '#1a1a2e' }, textColor: '#8888aa' },
        grid: {
            vertLines: { color: '#2a2a4a20' },
            horzLines: { color: '#2a2a4a20' },
        },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        timeScale: { timeVisible: true, secondsVisible: false },
    });
    klineChart = chart;

    const candleSeries = chart.addCandlestickSeries({
        upColor: '#00c853', downColor: '#ff1744',
        borderUpColor: '#00c853', borderDownColor: '#ff1744',
        wickUpColor: '#00c85380', wickDownColor: '#ff174480',
    });
    candleSeries.setData(candles);

    // 買賣點標記
    const markers = [];
    for (const t of trades) {
        // 入場標記
        const entryTime = t.entry_time / 1000;
        markers.push({
            time: entryTime,
            position: t.direction === 'long' ? 'belowBar' : 'aboveBar',
            color: t.direction === 'long' ? '#00c853' : '#ff1744',
            shape: t.direction === 'long' ? 'arrowUp' : 'arrowDown',
            text: t.direction === 'long' ? 'L' : 'S',
        });

        // 出場標記
        const exitTime = t.exit_time / 1000;
        const isWin = t.pnl_pct > 0;
        markers.push({
            time: exitTime,
            position: t.direction === 'long' ? 'aboveBar' : 'belowBar',
            color: isWin ? '#00c853' : '#ff1744',
            shape: 'circle',
            text: t.exit_type === 'sl' ? 'SL' : (t.exit_type === 'force_close' ? 'FC' : 'TP'),
        });
    }

    // 按時間排序
    markers.sort((a, b) => a.time - b.time);
    if (markers.length > 0) {
        candleSeries.setMarkers(markers);
    }

    // SL/TP 線（顯示最後一筆交易的）
    if (trades.length > 0) {
        const lastTrade = trades[trades.length - 1];
        // 可選：為每筆交易畫 SL/TP 線
    }

    // 自適應寬度
    new ResizeObserver(() => {
        chart.applyOptions({ width: chartEl.clientWidth });
    }).observe(chartEl);

    chart.timeScale().fitContent();
}

// === Equity Curve ===
function renderEquityCurve(container, equityCurve) {
    if (!equityCurve || equityCurve.length === 0) return;

    const section = document.createElement('div');
    section.className = 'chart-section';
    section.innerHTML = `<div class="chart-header">Equity Curve (累計損益 %)</div><div class="equity-chart-container" id="equityChart"></div>`;
    container.appendChild(section);

    const chartEl = section.querySelector('#equityChart');

    if (equityChart) { equityChart.remove(); equityChart = null; }

    const chart = LightweightCharts.createChart(chartEl, {
        width: chartEl.clientWidth,
        height: 250,
        layout: { background: { color: '#1a1a2e' }, textColor: '#8888aa' },
        grid: {
            vertLines: { color: '#2a2a4a20' },
            horzLines: { color: '#2a2a4a20' },
        },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        timeScale: { timeVisible: true, secondsVisible: false },
        rightPriceScale: { borderColor: '#2a2a4a' },
    });
    equityChart = chart;

    // 判斷最終是正還是負
    const lastVal = equityCurve[equityCurve.length - 1]?.value || 0;
    const lineColor = lastVal >= 0 ? '#00c853' : '#ff1744';
    const topColor = lastVal >= 0 ? '#00c85320' : '#ff174420';

    const areaSeries = chart.addAreaSeries({
        lineColor: lineColor,
        topColor: topColor,
        bottomColor: 'transparent',
        lineWidth: 2,
    });

    // 過濾重複時間戳
    const seen = new Set();
    const filtered = equityCurve.filter(p => {
        if (seen.has(p.time)) return false;
        seen.add(p.time);
        return true;
    });

    areaSeries.setData(filtered);

    // 零線
    areaSeries.createPriceLine({
        price: 0,
        color: '#8888aa40',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
    });

    new ResizeObserver(() => {
        chart.applyOptions({ width: chartEl.clientWidth });
    }).observe(chartEl);

    chart.timeScale().fitContent();
}

// === 交易明細表 ===
function renderTradeTable(container, trades) {
    if (!trades || trades.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'stat-card';
        empty.style.textAlign = 'center';
        empty.innerHTML = '<div class="label">無觸發交易</div><div class="value">0</div>';
        container.appendChild(empty);
        return;
    }

    const section = document.createElement('div');
    section.className = 'trade-table-section';
    section.innerHTML = `
        <div class="trade-table-header">
            <span>交易明細（共 ${trades.length} 筆）</span>
        </div>
        <div class="trade-table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>方向</th>
                        <th>入場時間</th>
                        <th>入場價</th>
                        <th>出場時間</th>
                        <th>出場價</th>
                        <th>出場類型</th>
                        <th>SL</th>
                        <th>TP1</th>
                        <th>TP2</th>
                        <th>損益 %</th>
                        <th>累計 %</th>
                        <th>持倉</th>
                        <th>R:R</th>
                        <th>星數</th>
                        <th>信號</th>
                    </tr>
                </thead>
                <tbody id="tradeBody"></tbody>
            </table>
        </div>
    `;
    container.appendChild(section);

    const tbody = section.querySelector('#tradeBody');
    for (const t of trades) {
        const tr = document.createElement('tr');
        const dirCls = t.direction === 'long' ? 'dir-long' : 'dir-short';
        const dirText = t.direction === 'long' ? 'LONG' : 'SHORT';
        const pnlCls = t.pnl_pct >= 0 ? 'pnl-pos' : 'pnl-neg';
        const cumCls = t.cumulative_pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
        const exitTypeMap = {
            'sl': ['exit-sl', 'SL'], 'tp1': ['exit-tp', 'TP1'], 'tp2': ['exit-tp', 'TP2'],
            'force_close': ['exit-force', '強平'], 'trailing_be': ['exit-force', 'T-BE'],
            'partial_sl': ['exit-sl', 'P-SL'], 'partial_tp1': ['exit-tp', 'P-TP1'],
            'partial_tp2': ['exit-tp', 'P-TP2'],
        };
        const [exitCls, exitText] = exitTypeMap[t.exit_type] || ['exit-force', t.exit_type];

        const priceDecimals = t.entry_price > 100 ? 2 : (t.entry_price > 1 ? 4 : 6);

        tr.innerHTML = `
            <td>${t.id}</td>
            <td class="${dirCls}">${dirText}</td>
            <td>${formatTime(t.entry_time)}</td>
            <td>${t.entry_price.toFixed(priceDecimals)}</td>
            <td>${formatTime(t.exit_time)}</td>
            <td>${t.exit_price.toFixed(priceDecimals)}</td>
            <td class="${exitCls}">${exitText}</td>
            <td>${t.sl.toFixed(priceDecimals)}</td>
            <td>${t.tp1.toFixed(priceDecimals)}</td>
            <td>${t.tp2.toFixed(priceDecimals)}</td>
            <td class="${pnlCls}">${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct.toFixed(3)}%</td>
            <td class="${cumCls}">${t.cumulative_pnl >= 0 ? '+' : ''}${t.cumulative_pnl.toFixed(3)}%</td>
            <td>${t.holding_bars} 根</td>
            <td>${t.rr_ratio}</td>
            <td>${t.quality_score}</td>
            <td>${t.signal_label || '-'}</td>
        `;
        tbody.appendChild(tr);
    }
}

// === 參數優化 ===
async function runOptimize() {
    const btn = document.getElementById('btnOptimize');
    const loading = document.getElementById('loading');
    btn.disabled = true;
    loading.classList.add('active');

    const customSym = document.getElementById('customSymbol').value.trim().toUpperCase();
    const symbol = customSym || document.getElementById('symbol').value;
    const interval = document.getElementById('interval').value;
    const limit = document.getElementById('limit').value;
    const slippage = document.getElementById('slippage').value;
    const cooldownBars = document.getElementById('cooldownBars').value;
    const trailingStop = document.getElementById('trailingStop').value;
    const partialTp = document.getElementById('partialTp').value;

    const params = new URLSearchParams({
        symbol, interval, limit,
        slippage_pct: slippage, cooldown_bars: cooldownBars,
        trailing_stop: trailingStop, partial_tp: partialTp,
    });

    try {
        document.getElementById('loadingProgress').textContent =
            `正在優化 ${symbol} ${interval} 參數（可能需要數分鐘）...`;
        const resp = await fetch(`/api/optimize?${params}`);
        const data = await resp.json();

        if (!data.success) {
            showToast(data.error || '優化失敗', 'error');
            return;
        }

        renderOptimizeResults(data);
        showToast(`優化完成：測試 ${data.total_combinations} 組，有效 ${data.valid_combinations} 組`, 'success');

    } catch (err) {
        showToast('優化請求失敗: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        loading.classList.remove('active');
    }
}

function renderOptimizeResults(data) {
    const container = document.getElementById('mainContent');
    container.innerHTML = '';

    // 資訊欄
    const info = document.createElement('div');
    info.style.cssText = 'font-size:12px; color:var(--text-secondary); padding:4px 0;';
    info.textContent = `${data.data_info.symbol} | ${data.data_info.interval} (MTF: ${data.data_info.mtf_interval}) | ${data.data_info.total_bars} 根 K 線 | 測試 ${data.total_combinations} 組合 | 有效 ${data.valid_combinations} 組`;
    container.appendChild(info);

    if (data.results.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.innerHTML = '<h2>無有效結果</h2><p>所有參數組合的交易次數均不足 5 筆</p>';
        container.appendChild(empty);
        return;
    }

    // 排行表
    const section = document.createElement('div');
    section.className = 'trade-table-section';
    section.innerHTML = `
        <div class="trade-table-header">
            <span>參數優化排行（Top ${data.results.length}，依 PnL/DD 比值排序）</span>
        </div>
        <div class="trade-table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>EMA</th>
                        <th>RSI</th>
                        <th>Q</th>
                        <th>入場模式</th>
                        <th>Confirmed</th>
                        <th>Caution RR</th>
                        <th>交易數</th>
                        <th>勝率</th>
                        <th>總 PnL%</th>
                        <th>回撤%</th>
                        <th>PnL/DD</th>
                        <th>PF</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody id="optimizeBody"></tbody>
            </table>
        </div>
    `;
    container.appendChild(section);

    const tbody = section.querySelector('#optimizeBody');
    for (const r of data.results) {
        const tr = document.createElement('tr');
        const pnlCls = r.total_pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
        const pfCls = r.profit_factor >= 1 ? 'pnl-pos' : 'pnl-neg';

        const ema = `${r.params.ema_fast || '-'}/${r.params.ema_slow || '-'}`;
        const entryMode = r.params.entry_mode === 'include_normal' ? '含一般' : '僅強烈';
        const confirmed = r.params.require_confirmed === false ? '否' : '是';
        const cautionRR = r.params.allow_caution_rr === true ? '是' : '否';

        tr.innerHTML = `
            <td>${r.rank}</td>
            <td>${ema}</td>
            <td>${r.params.rsi_period || '-'}</td>
            <td>${r.params.min_quality || '-'}</td>
            <td>${entryMode}</td>
            <td>${confirmed}</td>
            <td>${cautionRR}</td>
            <td>${r.total_trades}</td>
            <td>${r.win_rate}%</td>
            <td class="${pnlCls}">${r.total_pnl >= 0 ? '+' : ''}${r.total_pnl.toFixed(3)}%</td>
            <td class="pnl-neg">${r.max_drawdown.toFixed(3)}%</td>
            <td>${r.score}</td>
            <td class="${pfCls}">${r.profit_factor}</td>
            <td><button class="btn-run" style="padding:4px 12px;font-size:11px;height:auto;"
                onclick="applyParams(${JSON.stringify(r.params).replace(/"/g, '&quot;')})">套用</button></td>
        `;
        tbody.appendChild(tr);
    }
}

function applyParams(params) {
    if (params.min_quality !== undefined) {
        document.getElementById('minQuality').value = params.min_quality;
    }
    if (params.entry_mode) {
        document.getElementById('entryMode').value = params.entry_mode;
    }
    if (params.require_confirmed !== undefined) {
        document.getElementById('requireConfirmed').value = params.require_confirmed ? '1' : '0';
    }
    if (params.allow_caution_rr !== undefined) {
        document.getElementById('allowCautionRR').value = params.allow_caution_rr ? '1' : '0';
    }
    window._customParams = params;
    showToast(`已套用參數：EMA ${params.ema_fast || '-'}/${params.ema_slow || '-'}, RSI ${params.rsi_period || '-'}, Q≥${params.min_quality || '-'}, ${params.entry_mode === 'include_normal' ? '含一般信號' : '僅強烈信號'}`, 'success');
}

// === 鍵盤快捷鍵 ===
document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) {
        const active = document.activeElement;
        if (active && (active.tagName === 'INPUT' || active.tagName === 'SELECT')) {
            runBacktest();
        }
    }
});
</script>

</body>
</html>
"""


# === Main ===

if __name__ == "__main__":
    port = CONFIG['port']
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), BacktestHandler) as httpd:
        print(f"{'='*50}")
        print(f"  Scalping Backtest Engine V{VERSION}")
        print(f"{'='*50}")
        print(f"  伺服器地址: http://localhost:{port}")
        print(f"  分析引擎: ScalpingAnalyzerPro (from app_v3)")
        print(f"  回測模式: 歷史滑動窗口 ({BacktestEngine.MIN_WINDOW} bar window)")
        print(f"{'='*50}")
        print(f"\n按 Ctrl+C 停止服務\n")
        httpd.serve_forever()
