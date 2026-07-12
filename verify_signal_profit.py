#!/usr/bin/env python3
"""
高等級建議獲利驗證機制 (Signal Grade Profit Verifier) V1.0

逐訊號事件研究（event study）：重播歷史 K 線，記錄「每一次」訊號觸發當下的
完整等級剖面（overall / signal_stage / rr_grade / 3D 分數 / composite / label），
並對每筆訊號用它給出的入場價 + SL/TP 獨立模擬結局（不受持倉互斥影響），
最後按訊號等級分層統計勝率 / 期望值 / Profit Factor，
回答核心問題：「高等級建議給的入場數據是否真的賺得到錢？」

與 app_backtest.py 的差異：
  - app_backtest 是組合回測（持倉互斥、cooldown），衡量的是「策略」績效
  - 本工具是逐訊號驗證（每筆訊號獨立模擬），衡量的是「建議本身」的品質
  - 每筆事件記錄完整等級欄位，可按 A/B/C/D/E 等級分層對照

使用方式：
  python3 verify_signal_profit.py --symbols BTCUSDT,ETHUSDT --bars 3000
  python3 verify_signal_profit.py --symbols BTCUSDT --interval 5m --bars 3000 \
      --max-hold 144 --cooldown 6 --fee 0.1 --slippage 0.05 --out result.json

需要 app_v3.py 與 app_backtest.py 在同目錄下。
"""

import json
import sys
import time

# === 匯入 app_backtest（連帶 app_v3），暫時清除 argv 防止誤讀 ===
_orig_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
from app_backtest import BacktestEngine, MTF_INTERVAL_MAP
from app_v3 import fetch_with_retry, BINANCE_API
sys.argv = _orig_argv

VERSION = "1.0.0"

WINDOW = BacktestEngine.MIN_WINDOW  # 150

# interval → 分鐘數（分頁抓取與 MTF 根數換算用）
INTERVAL_MINUTES = {
    '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440,
}


# === 數據抓取（分頁，突破單次 1000 根上限） ===

def fetch_klines_paginated(symbol, interval, total_bars):
    """向前分頁抓取 K 線，回傳按時間升冪排列的列表"""
    chunks = []
    end_time = None
    remaining = total_bars
    while remaining > 0:
        limit = min(1000, remaining)
        url = f"{BINANCE_API}/klines?symbol={symbol}&interval={interval}&limit={limit}"
        if end_time is not None:
            url += f"&endTime={end_time}"
        data = fetch_with_retry(url, is_kline_req=True)
        if not data:
            break
        chunks.append(data)
        remaining -= len(data)
        end_time = int(data[0][0]) - 1
        if len(data) < limit:
            break  # 已到最早歷史
        time.sleep(0.15)  # 避免觸發 rate limit
    # 由舊到新串接並去重
    all_data = []
    seen = set()
    for chunk in reversed(chunks):
        for k in chunk:
            ts = int(k[0])
            if ts not in seen:
                seen.add(ts)
                all_data.append(k)
    all_data.sort(key=lambda k: int(k[0]))
    return all_data


# === 等級判定 ===

def classify_tier(signals):
    """將一次分析結果歸入訊號等級層級，無可驗證訊號回傳 None

    分層定義（由高到低）：
      A: strong_* + confirmed + rr_grade=good      —— 系統最高等級建議
      B: strong_* + confirmed + rr_grade=acceptable
      C: buy/sell + confirmed                       —— 一般等級確認訊號
      D: 有 signal_type 與 SL/TP 但無 pre-alert（signal_stage=None）
      E: 謹慎進場（R:R caution，降級為 pre_alert 但保留 SL/TP）
    """
    overall = signals.get('overall')
    stage = signals.get('signal_stage')
    sl_tp = signals.get('stop_loss_take_profit')
    action = signals.get('action', '')
    if not sl_tp:
        return None
    rr_grade = sl_tp.get('rr_grade')
    is_strong = overall in ('strong_buy', 'strong_sell')
    is_normal = overall in ('buy', 'sell')
    if stage == 'confirmed':
        if is_strong:
            return 'A_strong_confirmed_good' if rr_grade == 'good' else 'B_strong_confirmed_acceptable'
        if is_normal:
            return 'C_normal_confirmed'
        return None
    if '謹慎進場' in action and (is_strong or is_normal):
        return 'E_caution_rr'
    if stage is None and (is_strong or is_normal):
        return 'D_unconfirmed'
    return None


def signal_direction(signals):
    """回傳 'long' / 'short'"""
    return 'long' if signals.get('overall') in ('strong_buy', 'buy') else 'short'


# === 逐訊號結局模擬 ===

def simulate_outcome(direction, entry, sl, tp1, future_bars, max_hold):
    """對單筆訊號模擬結局（全倉 TP1 出場制，與 app_backtest 預設一致）

    同 bar 同觸 SL/TP 時以開盤價方向判定，模糊時保守判 SL（與 _check_sl_tp 一致）。
    回傳 dict：exit_type(sl/tp1/timeout/no_data)、exit_price、bars_held、mfe/mae（R 倍數）
    """
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    mfe = 0.0  # 最大有利波動（R）
    mae = 0.0  # 最大不利波動（R）
    for j, bar in enumerate(future_bars[:max_hold], start=1):
        o, h, l = float(bar[1]), float(bar[2]), float(bar[3])
        if direction == 'long':
            mfe = max(mfe, (h - entry) / risk)
            mae = max(mae, (entry - l) / risk)
            hit_sl = l <= sl
            hit_tp = h >= tp1
            if hit_sl and hit_tp:
                if o >= tp1:
                    return {'exit_type': 'tp1', 'exit_price': tp1, 'bars_held': j, 'mfe': mfe, 'mae': mae}
                return {'exit_type': 'sl', 'exit_price': sl, 'bars_held': j, 'mfe': mfe, 'mae': mae}
            if hit_sl:
                return {'exit_type': 'sl', 'exit_price': sl, 'bars_held': j, 'mfe': mfe, 'mae': mae}
            if hit_tp:
                return {'exit_type': 'tp1', 'exit_price': tp1, 'bars_held': j, 'mfe': mfe, 'mae': mae}
        else:
            mfe = max(mfe, (entry - l) / risk)
            mae = max(mae, (h - entry) / risk)
            hit_sl = h >= sl
            hit_tp = l <= tp1
            if hit_sl and hit_tp:
                if o <= tp1:
                    return {'exit_type': 'tp1', 'exit_price': tp1, 'bars_held': j, 'mfe': mfe, 'mae': mae}
                return {'exit_type': 'sl', 'exit_price': sl, 'bars_held': j, 'mfe': mfe, 'mae': mae}
            if hit_sl:
                return {'exit_type': 'sl', 'exit_price': sl, 'bars_held': j, 'mfe': mfe, 'mae': mae}
            if hit_tp:
                return {'exit_type': 'tp1', 'exit_price': tp1, 'bars_held': j, 'mfe': mfe, 'mae': mae}
    if not future_bars:
        return {'exit_type': 'no_data', 'exit_price': entry, 'bars_held': 0, 'mfe': 0.0, 'mae': 0.0}
    last_idx = min(max_hold, len(future_bars)) - 1
    exit_price = float(future_bars[last_idx][4])
    return {'exit_type': 'timeout', 'exit_price': exit_price, 'bars_held': last_idx + 1, 'mfe': mfe, 'mae': mae}


# === 主驗證流程 ===

def verify_symbol(symbol, interval='5m', total_bars=3000, max_hold=144,
                  cooldown_bars=6, fee_pct=0.1, slippage_pct=0.05):
    """對單一交易對執行逐訊號驗證，回傳 {events, suppressed, bars_analyzed, span}"""
    mtf_interval = MTF_INTERVAL_MAP.get(interval, '15m')
    main_min = INTERVAL_MINUTES.get(interval, 5)
    mtf_min = INTERVAL_MINUTES.get(mtf_interval, 15)

    all_data = fetch_klines_paginated(symbol, interval, total_bars)
    if len(all_data) < WINDOW + 10:
        raise ValueError(f'{symbol} K 線不足：{len(all_data)} 根')
    # MTF 根數 = 主圖跨度換算 + 60 根緩衝
    mtf_bars_needed = (len(all_data) * main_min) // mtf_min + 60
    mtf_data = fetch_klines_paginated(symbol, mtf_interval, mtf_bars_needed)
    mtf_timestamps = [int(k[0]) for k in mtf_data]

    def get_mtf_slice(bar_open_ts):
        """截至 bar_open_ts『前一根已收盤』的最近 50 根 MTF K 線（排除未收盤的當根，避免 look-ahead）"""
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
        # 排除與主圖 bar 同期尚未收盤的 MTF K 線
        if idx >= 0 and int(mtf_data[idx][6]) > bar_open_ts:
            idx -= 1
        if idx < 19:
            return None
        return mtf_data[max(0, idx - 49):idx + 1]

    events = []
    suppressed = 0
    last_event_bar = {'long': -999, 'short': -999}
    fee_frac = fee_pct / 100.0
    slip_frac = slippage_pct / 100.0

    # 窗口含當前 bar i（訊號 = bar i 收盤時所見），結局從 bar i+1 開始模擬
    for i in range(WINDOW - 1, len(all_data) - 1):
        window = all_data[i - WINDOW + 1:i + 1]
        bar_open_ts = int(all_data[i][0])
        signals = BacktestEngine.analyze_bar(
            window, symbol,
            mtf_slice=get_mtf_slice(bar_open_ts),
            mtf_interval=mtf_interval,
        )
        if not signals:
            continue
        tier = classify_tier(signals)
        if tier is None:
            continue
        direction = signal_direction(signals)
        # 同方向冷卻去重：模擬即時系統中連續 bar 重複觸發同一結構
        if i - last_event_bar[direction] < cooldown_bars:
            suppressed += 1
            continue
        last_event_bar[direction] = i

        sl_tp = signals['stop_loss_take_profit']
        close = float(all_data[i][4])
        entry = close * (1 + slip_frac) if direction == 'long' else close * (1 - slip_frac)
        sl = sl_tp['stop_loss']
        tp1 = sl_tp['take_profit_1']
        outcome = simulate_outcome(direction, entry, sl, tp1, all_data[i + 1:], max_hold)
        if outcome is None:
            continue
        if direction == 'long':
            gross_pnl = (outcome['exit_price'] - entry) / entry * 100
        else:
            gross_pnl = (entry - outcome['exit_price']) / entry * 100
        net_pnl = gross_pnl - fee_pct  # 來回手續費
        risk = abs(entry - sl)
        r_multiple = (net_pnl / 100 * entry) / risk if risk > 0 else 0.0

        events.append({
            'symbol': symbol,
            'time': int(all_data[i][0]),
            'bar_idx': i,
            'direction': direction,
            'tier': tier,
            'overall': signals.get('overall'),
            'action': signals.get('action'),
            'signal_stage': signals.get('signal_stage'),
            'signal_label': signals.get('signal_label'),
            'rr_grade': sl_tp.get('rr_grade'),
            'rr_ratio': sl_tp.get('risk_reward_ratio'),
            'quality_score': signals.get('quality_score'),
            'trend_score': signals.get('trend_score'),
            'structure_score': signals.get('structure_score'),
            'momentum_score': signals.get('momentum_score'),
            'composite_score': signals.get('composite_score'),
            'min_floor': signals.get('min_floor'),
            'entry': round(entry, 8),
            'sl': sl,
            'tp1': tp1,
            'tp2': sl_tp.get('take_profit_2'),
            'exit_type': outcome['exit_type'],
            'exit_price': outcome['exit_price'],
            'bars_held': outcome['bars_held'],
            'gross_pnl_pct': round(gross_pnl, 4),
            'net_pnl_pct': round(net_pnl, 4),
            'r_multiple': round(r_multiple, 3),
            'mfe_r': round(outcome['mfe'], 3),
            'mae_r': round(outcome['mae'], 3),
        })

    span_hours = (int(all_data[-1][0]) - int(all_data[0][0])) / 3600000
    return {
        'events': events,
        'suppressed': suppressed,
        'bars_analyzed': len(all_data) - WINDOW,
        'span_hours': round(span_hours, 1),
    }


# === 分層統計 ===

def calc_group_stats(events):
    """對一組事件計算獲利統計"""
    n = len(events)
    if n == 0:
        return {'n': 0}
    wins = [e for e in events if e['net_pnl_pct'] > 0]
    losses = [e for e in events if e['net_pnl_pct'] <= 0]
    gross_win = sum(e['net_pnl_pct'] for e in wins)
    gross_loss = abs(sum(e['net_pnl_pct'] for e in losses))
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else (999.99 if gross_win > 0 else 0)
    return {
        'n': n,
        'win_rate': round(len(wins) / n * 100, 1),
        'tp1_rate': round(sum(1 for e in events if e['exit_type'] == 'tp1') / n * 100, 1),
        'sl_rate': round(sum(1 for e in events if e['exit_type'] == 'sl') / n * 100, 1),
        'timeout_rate': round(sum(1 for e in events if e['exit_type'] == 'timeout') / n * 100, 1),
        'total_net_pnl_pct': round(sum(e['net_pnl_pct'] for e in events), 2),
        'avg_net_pnl_pct': round(sum(e['net_pnl_pct'] for e in events) / n, 4),
        'profit_factor': pf,
        'expectancy_r': round(sum(e['r_multiple'] for e in events) / n, 3),
        'avg_rr_given': round(sum(e['rr_ratio'] or 0 for e in events) / n, 2),
        'avg_mfe_r': round(sum(e['mfe_r'] for e in events) / n, 2),
        'avg_mae_r': round(sum(e['mae_r'] for e in events) / n, 2),
        'avg_bars_held': round(sum(e['bars_held'] for e in events) / n, 1),
    }


def build_report(all_events, meta):
    """按等級 / label / 方向 / 幣種分層產出報告"""
    def group_by(key_fn):
        groups = {}
        for e in all_events:
            groups.setdefault(key_fn(e), []).append(e)
        return {k: calc_group_stats(v) for k, v in sorted(groups.items())}

    return {
        'version': VERSION,
        'meta': meta,
        'overall': calc_group_stats(all_events),
        'by_tier': group_by(lambda e: e['tier']),
        'by_label': group_by(lambda e: e['signal_label'] or 'none'),
        'by_direction': group_by(lambda e: e['direction']),
        'by_symbol': group_by(lambda e: e['symbol']),
        'by_rr_grade': group_by(lambda e: e['rr_grade'] or 'none'),
        'events': all_events,
    }


# === CLI ===

def parse_cli():
    args = sys.argv[1:]
    cfg = {
        'symbols': ['BTCUSDT'],
        'interval': '5m',
        'bars': 3000,
        'max_hold': 144,
        'cooldown': 6,
        'fee': 0.1,
        'slippage': 0.05,
        'out': None,
    }
    i = 0
    while i < len(args):
        key = args[i]
        if key == '--symbols' and i + 1 < len(args):
            cfg['symbols'] = [s.strip().upper() for s in args[i + 1].split(',') if s.strip()]
            i += 2
        elif key == '--interval' and i + 1 < len(args):
            cfg['interval'] = args[i + 1]
            i += 2
        elif key == '--bars' and i + 1 < len(args):
            cfg['bars'] = max(WINDOW + 50, int(args[i + 1]))
            i += 2
        elif key == '--max-hold' and i + 1 < len(args):
            cfg['max_hold'] = int(args[i + 1])
            i += 2
        elif key == '--cooldown' and i + 1 < len(args):
            cfg['cooldown'] = int(args[i + 1])
            i += 2
        elif key == '--fee' and i + 1 < len(args):
            cfg['fee'] = float(args[i + 1])
            i += 2
        elif key == '--slippage' and i + 1 < len(args):
            cfg['slippage'] = float(args[i + 1])
            i += 2
        elif key == '--out' and i + 1 < len(args):
            cfg['out'] = args[i + 1]
            i += 2
        else:
            i += 1
    return cfg


def main():
    cfg = parse_cli()
    all_events = []
    per_symbol_meta = {}
    for symbol in cfg['symbols']:
        t0 = time.time()
        print(f"▶ {symbol} {cfg['interval']} × {cfg['bars']} 根驗證中...", flush=True)
        result = verify_symbol(
            symbol, cfg['interval'], cfg['bars'],
            max_hold=cfg['max_hold'], cooldown_bars=cfg['cooldown'],
            fee_pct=cfg['fee'], slippage_pct=cfg['slippage'],
        )
        all_events.extend(result['events'])
        per_symbol_meta[symbol] = {
            'bars_analyzed': result['bars_analyzed'],
            'span_hours': result['span_hours'],
            'events': len(result['events']),
            'suppressed_by_cooldown': result['suppressed'],
        }
        print(f"  完成：{len(result['events'])} 筆事件（冷卻去重 {result['suppressed']} 筆），"
              f"耗時 {time.time() - t0:.0f}s", flush=True)

    report = build_report(all_events, {
        'interval': cfg['interval'],
        'bars_per_symbol': cfg['bars'],
        'max_hold_bars': cfg['max_hold'],
        'cooldown_bars': cfg['cooldown'],
        'fee_pct_roundtrip': cfg['fee'],
        'slippage_pct': cfg['slippage'],
        'exit_model': '全倉 TP1 出場制（同 bar 同觸保守判 SL）',
        'per_symbol': per_symbol_meta,
    })

    if cfg['out']:
        with open(cfg['out'], 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        print(f"✅ 報告已存至 {cfg['out']}")

    # 終端摘要
    print(f"\n=== 高等級建議獲利驗證摘要（fee {cfg['fee']}% / slippage {cfg['slippage']}%）===")
    print(f"總事件：{report['overall'].get('n', 0)} 筆")
    for tier, stats in report['by_tier'].items():
        if stats['n'] == 0:
            continue
        print(f"  [{tier}] n={stats['n']} 勝率={stats['win_rate']}% "
              f"PF={stats['profit_factor']} 期望值={stats['expectancy_r']}R "
              f"均PnL={stats['avg_net_pnl_pct']}%")


if __name__ == '__main__':
    main()
