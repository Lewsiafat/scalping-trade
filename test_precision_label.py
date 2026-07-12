#!/usr/bin/env python3
"""
低價幣精度與 signal_label 時近性回歸測試

背景（基準驗證 2026-07-10 發現的 P0 bug）：
  1. calculate_atr 以 round(atr, 2) 回傳 → DOGE（ATR≈0.00013）100% 捨入為 0.0，
     訊號管線全滅；XRP（ATR≈0.0018）捨入為 0.0 或放大數倍的 0.01。
  2. calc_dynamic_sl_tp 的 SL/TP 價格 round(, 2) → 低價幣止損距離被量化摧毀。
  3. determine_signal_label 只要 sweeps 列表非空即回「Sweep 確認」，
     無時近性過濾 → 1691 筆事件 100% 同一標籤，其餘五類標籤成死代碼。

執行：python3 test_precision_label.py
"""

import sys

_orig_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
from app_v3 import ScalpingAnalyzerPro as S
sys.argv = _orig_argv


def make_klines(n, base_price, tr):
    """產生 n 根合成 K 線：價格 base_price、每根真實波幅約 tr"""
    rows = []
    ts = 1700000000000
    for i in range(n):
        o = base_price
        h = base_price + tr / 2
        l = base_price - tr / 2
        c = base_price + (tr / 4 if i % 2 == 0 else -tr / 4)
        rows.append([
            ts + i * 300000, f'{o:.8f}', f'{h:.8f}', f'{l:.8f}', f'{c:.8f}',
            '1000', ts + i * 300000 + 299999, '100', 10, '500', '50', '0'
        ])
    return rows


def test_atr_low_price():
    """DOGE 尺度（價格 0.07、TR 0.0002）的 ATR 不得被捨入為 0"""
    data = make_klines(50, 0.07, 0.0002)
    atr = S.calculate_atr(data)
    assert atr is not None and atr > 0, f'低價幣 ATR 被捨入為 {atr}（應 > 0）'
    assert abs(atr - 0.0002) < 0.0001, f'ATR 精度異常：{atr}（預期 ≈ 0.0002）'


def test_sl_tp_low_price():
    """DOGE 尺度的 SL/TP 價格不得被 2 位小數量化摧毀"""
    price, atr = 0.07, 0.00015
    result = S.calc_dynamic_sl_tp(price, atr, 'buy', [], [], [])
    assert result is not None, 'SL/TP 計算在低價幣上回傳 None'
    sl, tp1 = result['stop_loss'], result['take_profit_1']
    assert sl < price, f'止損 {sl} 未低於現價 {price}（精度被捨入摧毀）'
    assert tp1 > price, f'止盈 {tp1} 未高於現價 {price}（精度被捨入摧毀）'
    sl_dist = price - sl
    assert atr * 0.99 <= sl_dist <= atr * 2.51, \
        f'SL 距離 {sl_dist:.8f} 超出 ATR clamp 範圍 [{atr}, {atr * 2.5}]'


def test_label_stale_sweep():
    """久遠的 sweep（>10 根 bar 前）不應標為「Sweep 確認」"""
    stale_sweep = [{'type': 'bullish', 'sweep_price': 100.0, 'swing_price': 100.5,
                    'index': 100, 'time': 0, 'depth': 0.5, 'strength': 'full'}]
    label = S.determine_signal_label([], [], stale_sweep, 105.0, 1.0,
                                     current_index=149)
    assert label != 'Sweep 確認', f'距今 49 根 bar 的 sweep 仍標為「{label}」'
    assert label == '指標共振', f'無近期結構時應為「指標共振」，實得「{label}」'


def test_label_recent_sweep():
    """近期的 sweep（≤10 根 bar 內）應標為「Sweep 確認」"""
    recent_sweep = [{'type': 'bullish', 'sweep_price': 100.0, 'swing_price': 100.5,
                     'index': 145, 'time': 0, 'depth': 0.5, 'strength': 'full'}]
    label = S.determine_signal_label([], [], recent_sweep, 105.0, 1.0,
                                     current_index=149)
    assert label == 'Sweep 確認', f'近期 sweep 應標為「Sweep 確認」，實得「{label}」'


def test_label_ob_reachable():
    """無近期 sweep 但價格在 OB 區間內 → 應能標出「OB 反彈」（原 100% 短路使此類永不出現）"""
    stale_sweep = [{'type': 'bullish', 'sweep_price': 100.0, 'swing_price': 100.5,
                    'index': 50, 'time': 0, 'depth': 0.5, 'strength': 'near'}]
    obs = [{'type': 'bullish', 'top': 106.0, 'bottom': 104.0, 'index': 140,
            'time': 0, 'touches': 0}]
    label = S.determine_signal_label(obs, [], stale_sweep, 105.0, 1.0,
                                     current_index=149)
    assert label == 'OB 反彈', f'應標為「OB 反彈」，實得「{label}」'


if __name__ == '__main__':
    tests = [test_atr_low_price, test_sl_tp_low_price, test_label_stale_sweep,
             test_label_recent_sweep, test_label_ob_reachable]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'✅ {t.__name__}')
        except AssertionError as e:
            print(f'❌ {t.__name__}: {e}')
            failed += 1
        except TypeError as e:
            print(f'❌ {t.__name__}: {e}（簽名尚未支援）')
            failed += 1
    print(f'\n{len(tests) - failed}/{len(tests)} 通過')
    sys.exit(1 if failed else 0)
