"""方案 B：條件累積信號引擎（獨立檔案，供 A/B 比較測試）

從 app_v3 import 基礎指標計算，只重寫信號判定邏輯。
10 個布林條件，≥5 觸發信號，≥7 強信號。
"""

import sys
import os

# 確保可以 import app_v3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app_v3 import ScalpingAnalyzerPro


def determine_direction(bos_list, ema_fast, ema_slow, mtf_analysis):
    """多數決判定方向：BOS + EMA + MTF"""
    votes = {'bullish': 0, 'bearish': 0}

    if bos_list:
        d = bos_list[-1]['direction']
        votes[d] = votes.get(d, 0) + 1

    if ema_fast is not None and ema_slow is not None:
        if ema_fast > ema_slow:
            votes['bullish'] += 1
        else:
            votes['bearish'] += 1

    mtf_trend = mtf_analysis.get('trend', 'neutral')
    if mtf_trend == 'uptrend':
        votes['bullish'] += 1
    elif mtf_trend == 'downtrend':
        votes['bearish'] += 1

    return 'bullish' if votes['bullish'] >= votes['bearish'] else 'bearish'


def evaluate_conditions(data, params, symbol):
    """評估 10 個布林條件，回傳結果 dict"""
    closes = [float(k[4]) for k in data]
    current_price = closes[-1]
    interval = params.get('interval', '5m')

    # 基礎指標
    rsi = ScalpingAnalyzerPro.calculate_rsi(closes, params['rsi_period'])
    ema_fast = ScalpingAnalyzerPro.calculate_ema(closes, params['ema_fast'])
    ema_slow = ScalpingAnalyzerPro.calculate_ema(closes, params['ema_slow'])
    macd_line, signal_line, histogram = ScalpingAnalyzerPro.calculate_macd(
        closes, params['macd_fast'], params['macd_slow'], params['macd_signal']
    )
    atr = ScalpingAnalyzerPro.calculate_atr(data, 14)
    stoch_k, stoch_d = ScalpingAnalyzerPro.calculate_stochastic(data, 14, 3)
    volume_analysis = ScalpingAnalyzerPro.analyze_volume(data)
    mtf_analysis = ScalpingAnalyzerPro.multi_timeframe_analysis(symbol, interval)

    # SMC
    swing_n = 5 if interval == '15m' else 3
    swing_points = ScalpingAnalyzerPro.find_swing_points(data, n=swing_n)
    bos_list = ScalpingAnalyzerPro.detect_bos(data, swing_points)
    order_blocks = ScalpingAnalyzerPro.identify_order_blocks(data, bos_list)
    fvgs = ScalpingAnalyzerPro.identify_fvg(data)
    sweeps = ScalpingAnalyzerPro.detect_liquidity_sweep(data, swing_points, atr)

    # 方向
    direction = determine_direction(bos_list, ema_fast, ema_slow, mtf_analysis)

    # === 10 個條件 ===
    conditions = {}

    # 1. BOS 方向一致
    bos_aligned = False
    if bos_list and ema_fast is not None and ema_slow is not None:
        bos_dir = bos_list[-1]['direction']
        ema_dir = 'bullish' if ema_fast > ema_slow else 'bearish'
        bos_aligned = bos_dir == ema_dir
    conditions['BOS 方向一致'] = bos_aligned

    # 2. MTF 確認
    mtf_confirmed = False
    mtf_trend = mtf_analysis.get('trend', 'neutral')
    if direction == 'bullish' and mtf_trend == 'uptrend':
        mtf_confirmed = True
    elif direction == 'bearish' and mtf_trend == 'downtrend':
        mtf_confirmed = True
    conditions['MTF 確認'] = mtf_confirmed

    # 3. OB 接近/進入
    ob_active = False
    if atr and atr > 0:
        for ob in reversed(order_blocks):
            if ob['bottom'] <= current_price <= ob['top']:
                ob_active = True
                break
            dist = min(abs(current_price - ob['top']), abs(current_price - ob['bottom']))
            if dist <= atr * 0.5:
                ob_active = True
                break
    conditions['OB 接近'] = ob_active

    # 4. FVG 存在
    fvg_active = False
    if fvgs and atr and atr > 0:
        for fvg in fvgs:
            if fvg['bottom'] <= current_price <= fvg['top']:
                fvg_active = True
                break
            dist = min(abs(current_price - fvg['top']), abs(current_price - fvg['bottom']))
            if dist <= atr * 0.5:
                fvg_active = True
                break
    conditions['FVG 存在'] = fvg_active

    # 5. Sweep 發生（任何等級）
    conditions['Sweep 發生'] = len(sweeps) > 0

    # 6. MACD 同向
    macd_aligned = False
    if macd_line is not None:
        if direction == 'bullish' and macd_line > 0:
            macd_aligned = True
        elif direction == 'bearish' and macd_line < 0:
            macd_aligned = True
    conditions['MACD 同向'] = macd_aligned

    # 7. RSI 合理區間
    rsi_ok = rsi is not None and 25 <= rsi <= 75
    conditions['RSI 合理'] = rsi_ok

    # 8. Stoch 方向一致
    stoch_aligned = False
    if stoch_k is not None and stoch_d is not None:
        if direction == 'bullish' and stoch_k > stoch_d:
            stoch_aligned = True
        elif direction == 'bearish' and stoch_k < stoch_d:
            stoch_aligned = True
    conditions['Stoch 同向'] = stoch_aligned

    # 9. 成交量支持
    vol_ok = False
    if volume_analysis:
        vol_ok = volume_analysis.get('volume_ratio', 0) > 0.8
    conditions['成交量支持'] = vol_ok

    # 10. R:R ≥ 0.7
    rr_ok = False
    signal_type_for_rr = 'buy' if direction == 'bullish' else 'sell'
    sl_tp = ScalpingAnalyzerPro.calc_dynamic_sl_tp(
        current_price, atr, signal_type_for_rr, order_blocks, fvgs, swing_points
    )
    if sl_tp:
        rr_ok = sl_tp.get('risk_reward_ratio', 0) >= 0.7
    conditions['R:R ≥ 0.7'] = rr_ok

    # 信號判定
    true_count = sum(1 for v in conditions.values() if v)

    if true_count >= 7:
        if direction == 'bullish':
            signal = 'strong_buy'
            action = '強烈買入 BUY'
        else:
            signal = 'strong_sell'
            action = '強烈賣出 SELL'
    elif true_count >= 5:
        if direction == 'bullish':
            signal = 'buy'
            action = '考慮買入'
        else:
            signal = 'sell'
            action = '考慮賣出'
    else:
        signal = 'neutral'
        action = '觀望 WAIT'

    return {
        'signal': signal,
        'action': action,
        'direction': direction,
        'conditions': conditions,
        'true_count': true_count,
        'total': 10,
        'sl_tp': sl_tp,
    }
