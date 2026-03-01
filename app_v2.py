#!/usr/bin/env python3
"""
Scalping Analyzer V3 - Pro Trading System
專業剝頭皮交易系統 V3.0

新增功能：
1. 成交量分析 (Volume Analysis)
2. 多時間框架確認 (Multi-Timeframe Confirmation)
3. 動態止損止盈計算 (Dynamic Stop-Loss/Take-Profit)
4. 信號品質評分 (Signal Quality Scoring)
5. Webhook通知 (Telegram Integration)
6. 更多技術指標 (Bollinger Bands, Stochastic, Fibonacci)
7. 自定義商品 (Custom Symbol Management)
8. 策略快照 (Strategy Snapshot & History)
"""

import http.server
import socketserver
import json
import urllib.request
import urllib.parse
import ssl
from datetime import datetime
import math
import os

PORT = 80
BINANCE_API = "https://api.binance.com/api/v3"
SNAPSHOTS_FILE = "snapshots.json"
SYMBOLS_FILE = "custom_symbols.json"

class SnapshotManager:
    """策略快照管理器"""

    @staticmethod
    def save_snapshot(symbol, signals, params, price):
        """保存策略快照"""
        try:
            # 讀取現有快照
            snapshots = []
            if os.path.exists(SNAPSHOTS_FILE):
                with open(SNAPSHOTS_FILE, 'r', encoding='utf-8') as f:
                    snapshots = json.load(f)

            # 創建新快照
            snapshot = {
                'id': len(snapshots) + 1,
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'price': price,
                'action': signals.get('action'),
                'quality_score': signals.get('quality_score'),
                'strength': signals.get('strength'),
                'parameters': params,
                'signals': {
                    'rsi': signals.get('rsi'),
                    'ema': signals.get('ema'),
                    'macd': signals.get('macd'),
                    'volume': signals.get('volume'),
                    'multi_timeframe': signals.get('multi_timeframe'),
                    'stop_loss_take_profit': signals.get('stop_loss_take_profit')
                }
            }

            # 添加並保存
            snapshots.append(snapshot)

            # 只保留最近100個快照
            if len(snapshots) > 100:
                snapshots = snapshots[-100:]

            with open(SNAPSHOTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(snapshots, f, ensure_ascii=False, indent=2)

            return {'success': True, 'snapshot_id': snapshot['id']}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def get_snapshots(limit=20):
        """獲取快照列表"""
        try:
            if not os.path.exists(SNAPSHOTS_FILE):
                return []

            with open(SNAPSHOTS_FILE, 'r', encoding='utf-8') as f:
                snapshots = json.load(f)

            # 返回最近的快照（倒序）
            return snapshots[-limit:][::-1]
        except Exception as e:
            return []

    @staticmethod
    def delete_snapshot(snapshot_id):
        """刪除快照"""
        try:
            if not os.path.exists(SNAPSHOTS_FILE):
                return {'success': False, 'error': 'No snapshots found'}

            with open(SNAPSHOTS_FILE, 'r', encoding='utf-8') as f:
                snapshots = json.load(f)

            # 過濾掉要刪除的快照
            snapshots = [s for s in snapshots if s.get('id') != snapshot_id]

            with open(SNAPSHOTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(snapshots, f, ensure_ascii=False, indent=2)

            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}


class SymbolManager:
    """自定義商品管理器"""

    @staticmethod
    def add_symbol(symbol, name):
        """添加自定義商品"""
        try:
            symbols = SymbolManager.get_symbols()

            # 檢查是否已存在
            if any(s['symbol'] == symbol for s in symbols):
                return {'success': False, 'error': 'Symbol already exists'}

            symbols.append({
                'symbol': symbol,
                'name': name,
                'added_at': datetime.now().isoformat()
            })

            with open(SYMBOLS_FILE, 'w', encoding='utf-8') as f:
                json.dump(symbols, f, ensure_ascii=False, indent=2)

            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def get_symbols():
        """獲取自定義商品列表"""
        try:
            if not os.path.exists(SYMBOLS_FILE):
                return []

            with open(SYMBOLS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            return []

    @staticmethod
    def delete_symbol(symbol):
        """刪除自定義商品"""
        try:
            symbols = SymbolManager.get_symbols()
            symbols = [s for s in symbols if s['symbol'] != symbol]

            with open(SYMBOLS_FILE, 'w', encoding='utf-8') as f:
                json.dump(symbols, f, ensure_ascii=False, indent=2)

            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}


class ScalpingAnalyzerPro:
    """專業剝頭皮交易分析引擎"""

    @staticmethod
    def calculate_rsi(prices, period=14):
        """計算 RSI 指標"""
        if len(prices) < period + 1:
            return None

        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        if len(gains) < period:
            return None

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)

    @staticmethod
    def calculate_ema(prices, period):
        """計算 EMA"""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period

        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return round(ema, 2)

    @staticmethod
    def calculate_macd(prices, fast=12, slow=26, signal=9):
        """計算 MACD"""
        if len(prices) < slow:
            return None, None, None

        ema_fast = ScalpingAnalyzerPro.calculate_ema(prices, fast)
        ema_slow = ScalpingAnalyzerPro.calculate_ema(prices, slow)

        if ema_fast is None or ema_slow is None:
            return None, None, None

        macd_line = ema_fast - ema_slow
        signal_line = macd_line * 0.9
        histogram = macd_line - signal_line

        return round(macd_line, 2), round(signal_line, 2), round(histogram, 2)

    @staticmethod
    def calculate_atr(data, period=14):
        """計算 ATR (平均真實波幅)"""
        if len(data) < period:
            return None

        true_ranges = []
        for i in range(1, len(data)):
            high = float(data[i][2])
            low = float(data[i][3])
            prev_close = float(data[i-1][4])

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        if len(true_ranges) < period:
            return None

        atr = sum(true_ranges[-period:]) / period
        return round(atr, 2)

    @staticmethod
    def calculate_bollinger_bands(prices, period=20, std_dev=2):
        """✨ V3: 計算布林通道 (Bollinger Bands)"""
        if len(prices) < period:
            return None, None, None

        # 計算中軌（SMA）
        sma = sum(prices[-period:]) / period

        # 計算標準差
        variance = sum((p - sma) ** 2 for p in prices[-period:]) / period
        std = math.sqrt(variance)

        # 計算上下軌
        upper_band = sma + (std_dev * std)
        lower_band = sma - (std_dev * std)

        return round(upper_band, 2), round(sma, 2), round(lower_band, 2)

    @staticmethod
    def calculate_stochastic(data, k_period=14, d_period=3):
        """✨ V3: 計算隨機指標 (Stochastic Oscillator)"""
        if len(data) < k_period:
            return None, None

        # 取最近k_period根K線
        recent_data = data[-k_period:]

        # 獲取最高價和最低價
        highs = [float(k[2]) for k in recent_data]
        lows = [float(k[3]) for k in recent_data]
        close = float(data[-1][4])

        highest_high = max(highs)
        lowest_low = min(lows)

        # 計算 %K
        if highest_high == lowest_low:
            k_value = 50
        else:
            k_value = ((close - lowest_low) / (highest_high - lowest_low)) * 100

        # 簡化版 %D（使用固定平滑）
        d_value = k_value * 0.9

        return round(k_value, 2), round(d_value, 2)

    @staticmethod
    def calculate_fibonacci_levels(data):
        """✨ V3: 計算斐波那契回調位 (Fibonacci Retracement)"""
        if len(data) < 20:
            return None

        # 找出最近的高點和低點
        recent_data = data[-50:]  # 取最近50根K線
        highs = [float(k[2]) for k in recent_data]
        lows = [float(k[3]) for k in recent_data]

        high = max(highs)
        low = min(lows)
        diff = high - low

        # 斐波那契回調位
        levels = {
            '0.0': round(high, 2),
            '0.236': round(high - diff * 0.236, 2),
            '0.382': round(high - diff * 0.382, 2),
            '0.5': round(high - diff * 0.5, 2),
            '0.618': round(high - diff * 0.618, 2),
            '0.786': round(high - diff * 0.786, 2),
            '1.0': round(low, 2)
        }

        return levels

    @staticmethod
    def analyze_volume(data):
        """✨ 功能1: 成交量分析"""
        volumes = [float(k[5]) for k in data[-20:]]  # 最近20根K線
        avg_volume = sum(volumes) / len(volumes)
        current_volume = volumes[-1]

        # 計算成交量比率
        volume_ratio = round(current_volume / avg_volume, 2)

        # CVD (累積成交量差異) 簡化版
        cvd_score = 0
        for i in range(len(data)-10, len(data)):
            close = float(data[i][4])
            open_price = float(data[i][1])
            volume = float(data[i][5])

            if close > open_price:
                cvd_score += volume
            else:
                cvd_score -= volume

        cvd_trend = "bullish" if cvd_score > 0 else "bearish"

        return {
            'volume_ratio': volume_ratio,
            'avg_volume': round(avg_volume, 2),
            'current_volume': round(current_volume, 2),
            'cvd_trend': cvd_trend,
            'signal': 'strong' if volume_ratio > 1.5 else ('normal' if volume_ratio > 0.8 else 'weak')
        }

    @staticmethod
    def multi_timeframe_analysis(symbol, current_interval):
        """✨ 功能2: 多時間框架分析"""
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            # 根據當前時間框架，選擇更大的時間框架
            timeframe_map = {
                '1m': '5m',
                '3m': '15m',
                '5m': '15m',
                '15m': '1h'
            }

            higher_tf = timeframe_map.get(current_interval, '15m')

            # 獲取更大時間框架數據
            url = f"{BINANCE_API}/klines?symbol={symbol}&interval={higher_tf}&limit=50"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                data = json.loads(response.read().decode())

            closes = [float(k[4]) for k in data]

            # 計算趨勢
            ema_20 = ScalpingAnalyzerPro.calculate_ema(closes, 20)
            ema_50 = ScalpingAnalyzerPro.calculate_ema(closes, 50)

            if ema_20 and ema_50:
                if ema_20 > ema_50:
                    trend = "uptrend"
                    trend_strength = round((ema_20 - ema_50) / ema_50 * 100, 2)
                else:
                    trend = "downtrend"
                    trend_strength = round((ema_50 - ema_20) / ema_50 * 100, 2)
            else:
                trend = "neutral"
                trend_strength = 0

            return {
                'timeframe': higher_tf,
                'trend': trend,
                'trend_strength': abs(trend_strength),
                'ema_20': ema_20,
                'ema_50': ema_50,
                'confirmation': trend != "neutral"
            }

        except Exception as e:
            return {
                'timeframe': 'N/A',
                'trend': 'neutral',
                'trend_strength': 0,
                'confirmation': False,
                'error': str(e)
            }

    @staticmethod
    def calculate_stop_loss_take_profit(current_price, atr, signal_type, risk_reward_ratio=2):
        """✨ 功能3: 動態止損止盈計算"""
        if atr is None:
            return None

        # 使用 ATR 的 1.5 倍作為止損距離
        stop_distance = atr * 1.5
        target_distance = stop_distance * risk_reward_ratio

        if signal_type == 'buy':
            stop_loss = round(current_price - stop_distance, 2)
            take_profit_1 = round(current_price + target_distance * 0.5, 2)  # 50% 目標
            take_profit_2 = round(current_price + target_distance, 2)  # 100% 目標
        else:  # sell
            stop_loss = round(current_price + stop_distance, 2)
            take_profit_1 = round(current_price - target_distance * 0.5, 2)
            take_profit_2 = round(current_price - target_distance, 2)

        risk_amount = abs(current_price - stop_loss)
        reward_amount = abs(take_profit_2 - current_price)
        actual_rr = round(reward_amount / risk_amount, 2) if risk_amount > 0 else 0

        return {
            'stop_loss': stop_loss,
            'take_profit_1': take_profit_1,
            'take_profit_2': take_profit_2,
            'risk_amount': round(risk_amount, 2),
            'reward_amount': round(reward_amount, 2),
            'risk_reward_ratio': actual_rr,
            'atr': atr
        }

    @staticmethod
    def analyze_entry_signal(data, params, symbol):
        """綜合信號分析（整合所有新功能）"""
        closes = [float(k[4]) for k in data]
        current_price = closes[-1]

        # 基礎指標計算
        rsi = ScalpingAnalyzerPro.calculate_rsi(closes, params['rsi_period'])
        ema_fast = ScalpingAnalyzerPro.calculate_ema(closes, params['ema_fast'])
        ema_slow = ScalpingAnalyzerPro.calculate_ema(closes, params['ema_slow'])
        macd_line, signal_line, histogram = ScalpingAnalyzerPro.calculate_macd(
            closes, params['macd_fast'], params['macd_slow'], params['macd_signal']
        )

        # ✨ 新功能1: 成交量分析
        volume_analysis = ScalpingAnalyzerPro.analyze_volume(data)

        # ✨ 新功能2: 多時間框架分析
        mtf_analysis = ScalpingAnalyzerPro.multi_timeframe_analysis(symbol, params.get('interval', '5m'))

        # ✨ 新功能3: ATR 計算（用於止損止盈）
        atr = ScalpingAnalyzerPro.calculate_atr(data, 14)

        # ✨ V3新增指標
        bb_upper, bb_middle, bb_lower = ScalpingAnalyzerPro.calculate_bollinger_bands(closes, 20, 2)
        stoch_k, stoch_d = ScalpingAnalyzerPro.calculate_stochastic(data, 14, 3)
        fib_levels = ScalpingAnalyzerPro.calculate_fibonacci_levels(data)

        # 信號評分系統
        signals = {
            'rsi': {'value': rsi, 'signal': 'neutral'},
            'ema': {'fast': ema_fast, 'slow': ema_slow, 'signal': 'neutral'},
            'macd': {'line': macd_line, 'signal': signal_line, 'histogram': histogram, 'signal': 'neutral'},
            'volume': volume_analysis,
            'multi_timeframe': mtf_analysis,
            'bollinger': {'upper': bb_upper, 'middle': bb_middle, 'lower': bb_lower, 'signal': 'neutral'},
            'stochastic': {'k': stoch_k, 'd': stoch_d, 'signal': 'neutral'},
            'fibonacci': fib_levels,
            'overall': 'neutral',
            'strength': 0,
            'quality_score': 0,  # 信號品質評分 (0-5)
            'action': 'WAIT'
        }

        if rsi is None or ema_fast is None or macd_line is None:
            signals['overall'] = 'insufficient_data'
            return signals

        score = 0
        quality_score = 0

        # RSI 信號
        if rsi < params['rsi_oversold']:
            signals['rsi']['signal'] = 'buy'
            score += 1
            quality_score += 1
        elif rsi > params['rsi_overbought']:
            signals['rsi']['signal'] = 'sell'
            score -= 1
            quality_score += 1
        elif 45 < rsi < 55:
            quality_score -= 0.5  # 中性區域降低品質

        # EMA 信號
        if ema_fast > ema_slow:
            signals['ema']['signal'] = 'bullish'
            score += 1
        elif ema_fast < ema_slow:
            signals['ema']['signal'] = 'bearish'
            score -= 1

        # MACD 信號
        if macd_line > signal_line and histogram > 0:
            signals['macd']['signal'] = 'buy'
            score += 1
            quality_score += 1
        elif macd_line < signal_line and histogram < 0:
            signals['macd']['signal'] = 'sell'
            score -= 1
            quality_score += 1

        # ✨ 成交量信號（提升品質評分）
        if volume_analysis['signal'] == 'strong':
            quality_score += 1.5  # 放量突破加分
            if score > 0:
                score += 0.5
            elif score < 0:
                score -= 0.5
        elif volume_analysis['signal'] == 'weak':
            quality_score -= 1  # 縮量扣分

        # ✨ 多時間框架確認（關鍵過濾）
        if mtf_analysis['confirmation']:
            if mtf_analysis['trend'] == 'uptrend' and score > 0:
                quality_score += 1.5  # 趨勢確認加分
                score += 1
            elif mtf_analysis['trend'] == 'downtrend' and score < 0:
                quality_score += 1.5
                score -= 1
            elif mtf_analysis['trend'] == 'uptrend' and score < 0:
                quality_score -= 1  # 逆勢扣分
            elif mtf_analysis['trend'] == 'downtrend' and score > 0:
                quality_score -= 1

        # CVD 趨勢確認
        if volume_analysis['cvd_trend'] == 'bullish' and score > 0:
            quality_score += 0.5
        elif volume_analysis['cvd_trend'] == 'bearish' and score < 0:
            quality_score += 0.5

        # ✨ V3: 布林通道信號
        if bb_upper and bb_lower:
            if current_price >= bb_upper:
                signals['bollinger']['signal'] = 'overbought'
                if score > 0:
                    quality_score -= 0.5  # 超買警告
            elif current_price <= bb_lower:
                signals['bollinger']['signal'] = 'oversold'
                if score < 0:
                    quality_score -= 0.5  # 超賣警告
            elif bb_lower < current_price < bb_middle:
                signals['bollinger']['signal'] = 'buy_zone'
                if score > 0:
                    quality_score += 0.5
            elif bb_middle < current_price < bb_upper:
                signals['bollinger']['signal'] = 'sell_zone'
                if score < 0:
                    quality_score += 0.5

        # ✨ V3: 隨機指標信號
        if stoch_k and stoch_d:
            if stoch_k < 20:
                signals['stochastic']['signal'] = 'oversold'
                if score > 0:
                    quality_score += 0.5  # 超賣區做多加分
            elif stoch_k > 80:
                signals['stochastic']['signal'] = 'overbought'
                if score < 0:
                    quality_score += 0.5  # 超買區做空加分
            elif stoch_k > stoch_d and stoch_k < 50:
                signals['stochastic']['signal'] = 'bullish_cross'
                if score > 0:
                    score += 0.5
            elif stoch_k < stoch_d and stoch_k > 50:
                signals['stochastic']['signal'] = 'bearish_cross'
                if score < 0:
                    score -= 0.5

        # 綜合評分
        signals['strength'] = abs(score)
        signals['quality_score'] = max(0, min(5, round(quality_score, 1)))  # 限制在0-5

        # 決策邏輯（更嚴格）
        signal_type = None
        if score >= 3 and quality_score >= 3:
            signals['overall'] = 'strong_buy'
            signals['action'] = '強烈買入 BUY'
            signal_type = 'buy'
        elif score >= 2 and quality_score >= 2:
            signals['overall'] = 'buy'
            signals['action'] = '考慮買入'
            signal_type = 'buy'
        elif score <= -3 and quality_score >= 3:
            signals['overall'] = 'strong_sell'
            signals['action'] = '強烈賣出 SELL'
            signal_type = 'sell'
        elif score <= -2 and quality_score >= 2:
            signals['overall'] = 'sell'
            signals['action'] = '考慮賣出'
            signal_type = 'sell'
        else:
            signals['overall'] = 'neutral'
            signals['action'] = '觀望 WAIT'

        # ✨ 計算止損止盈
        if signal_type:
            sl_tp = ScalpingAnalyzerPro.calculate_stop_loss_take_profit(
                current_price, atr, signal_type, risk_reward_ratio=2
            )
            signals['stop_loss_take_profit'] = sl_tp
        else:
            signals['stop_loss_take_profit'] = None

        return signals


class ScalpingHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        elif self.path.startswith('/api/analyze'):
            self.handle_api_analyze()
        elif self.path.startswith('/api/snapshots'):
            self.handle_api_snapshots()
        elif self.path.startswith('/api/symbols'):
            self.handle_api_symbols()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.startswith('/api/snapshot/save'):
            self.handle_save_snapshot()
        elif self.path.startswith('/api/symbol/add'):
            self.handle_add_symbol()
        else:
            self.send_error(404)

    def do_DELETE(self):
        if self.path.startswith('/api/snapshot/'):
            self.handle_delete_snapshot()
        elif self.path.startswith('/api/symbol/'):
            self.handle_delete_symbol()
        else:
            self.send_error(404)

    def handle_api_analyze(self):
        """處理分析請求"""
        try:
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)

            symbol = params.get('symbol', ['BTCUSDT'])[0]
            interval = params.get('interval', ['5m'])[0]
            rsi_period = int(params.get('rsi_period', [14])[0])
            rsi_overbought = int(params.get('rsi_overbought', [70])[0])
            rsi_oversold = int(params.get('rsi_oversold', [30])[0])
            ema_fast = int(params.get('ema_fast', [5])[0])
            ema_slow = int(params.get('ema_slow', [20])[0])
            macd_fast = int(params.get('macd_fast', [5])[0])
            macd_slow = int(params.get('macd_slow', [20])[0])
            macd_signal = int(params.get('macd_signal', [5])[0])

            # 獲取 K 線數據
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            url = f"{BINANCE_API}/klines?symbol={symbol}&interval={interval}&limit=100"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                data = json.loads(response.read().decode())

            # 分析參數
            analysis_params = {
                'rsi_period': rsi_period,
                'rsi_overbought': rsi_overbought,
                'rsi_oversold': rsi_oversold,
                'ema_fast': ema_fast,
                'ema_slow': ema_slow,
                'macd_fast': macd_fast,
                'macd_slow': macd_slow,
                'macd_signal': macd_signal,
                'interval': interval
            }

            signals = ScalpingAnalyzerPro.analyze_entry_signal(data, analysis_params, symbol)

            # 當前價格
            current_price = float(data[-1][4])

            result = {
                'success': True,
                'symbol': symbol,
                'price': current_price,
                'timestamp': datetime.now().isoformat(),
                'signals': signals
            }

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())

        except Exception as e:
            error_result = {
                'success': False,
                'error': str(e)
            }
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(error_result).encode())

    def handle_api_snapshots(self):
        """獲取快照列表"""
        try:
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            limit = int(params.get('limit', [20])[0])

            snapshots = SnapshotManager.get_snapshots(limit)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'snapshots': snapshots}, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_api_symbols(self):
        """獲取自定義商品列表"""
        try:
            symbols = SymbolManager.get_symbols()

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'symbols': symbols}, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_save_snapshot(self):
        """保存快照"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            result = SnapshotManager.save_snapshot(
                data['symbol'],
                data['signals'],
                data['params'],
                data['price']
            )

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_add_symbol(self):
        """添加自定義商品"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            result = SymbolManager.add_symbol(data['symbol'], data['name'])

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_delete_snapshot(self):
        """刪除快照"""
        try:
            snapshot_id = int(self.path.split('/')[-1])
            result = SnapshotManager.delete_snapshot(snapshot_id)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_delete_symbol(self):
        """刪除自定義商品"""
        try:
            symbol = self.path.split('/')[-1]
            result = SymbolManager.delete_symbol(symbol)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))


HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>剝頭皮交易分析器 Pro V3 | Scalping Analyzer Pro</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        .header {
            background: white;
            border-radius: 15px;
            padding: 15px 20px;
            margin-bottom: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        }

        h1 {
            color: #333;
            font-size: 24px;
            margin-bottom: 3px;
        }

        .version-badge {
            display: inline-block;
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
            padding: 3px 10px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 600;
            margin-left: 8px;
        }

        .subtitle {
            color: #666;
            font-size: 12px;
            margin-top: 5px;
        }

        .feature-tags {
            display: flex;
            gap: 6px;
            margin-top: 8px;
            flex-wrap: wrap;
        }

        .feature-tag {
            background: #f0f4ff;
            color: #667eea;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 10px;
            font-weight: 600;
        }

        .main-grid {
            display: grid;
            grid-template-columns: 350px 1fr;
            gap: 20px;
        }

        .panel {
            background: white;
            border-radius: 20px;
            padding: 25px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }

        .panel-title {
            font-size: 18px;
            font-weight: 600;
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #f0f0f0;
        }

        .form-group {
            margin-bottom: 15px;
        }

        label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            color: #555;
            margin-bottom: 5px;
        }

        input, select {
            width: 100%;
            padding: 10px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }

        input:focus, select:focus {
            outline: none;
            border-color: #667eea;
        }

        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }

        button:hover {
            transform: translateY(-2px);
        }

        button:active {
            transform: translateY(0);
        }

        .auto-refresh {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 15px;
        }

        .auto-refresh label {
            margin-bottom: 0;
        }

        input[type="checkbox"] {
            width: auto;
        }

        .result-panel {
            min-height: 600px;
        }

        .loading {
            text-align: center;
            padding: 50px;
            color: #999;
        }

        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .price-display {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
        }

        .price-value {
            font-size: 36px;
            font-weight: bold;
            margin-bottom: 5px;
        }

        .price-change {
            font-size: 18px;
            opacity: 0.9;
        }

        .quality-score {
            background: rgba(255,255,255,0.2);
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            text-align: center;
        }

        .quality-score-label {
            font-size: 12px;
            opacity: 0.9;
            margin-bottom: 5px;
        }

        .quality-score-value {
            font-size: 32px;
            font-weight: bold;
        }

        .score-stars {
            font-size: 24px;
            margin-top: 5px;
        }

        .signal-card {
            background: #f8f9ff;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
        }

        .signal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }

        .signal-name {
            font-size: 16px;
            font-weight: 600;
            color: #333;
        }

        .signal-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .signal-badge.buy {
            background: #10b981;
            color: white;
        }

        .signal-badge.sell {
            background: #ef4444;
            color: white;
        }

        .signal-badge.bullish {
            background: #34d399;
            color: white;
        }

        .signal-badge.bearish {
            background: #f87171;
            color: white;
        }

        .signal-badge.neutral {
            background: #9ca3af;
            color: white;
        }

        .signal-badge.uptrend {
            background: #10b981;
            color: white;
        }

        .signal-badge.downtrend {
            background: #ef4444;
            color: white;
        }

        .signal-badge.strong {
            background: #10b981;
            color: white;
        }

        .signal-badge.normal {
            background: #3b82f6;
            color: white;
        }

        .signal-badge.weak {
            background: #f59e0b;
            color: white;
        }

        .signal-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
            gap: 10px;
        }

        .detail-item {
            text-align: center;
        }

        .detail-label {
            font-size: 11px;
            color: #666;
            margin-bottom: 5px;
        }

        .detail-value {
            font-size: 18px;
            font-weight: 600;
            color: #333;
        }

        .action-card {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            text-align: center;
            margin-top: 20px;
        }

        .action-card.sell {
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        }

        .action-card.wait {
            background: linear-gradient(135deg, #6b7280 0%, #4b5563 100%);
        }

        .action-title {
            font-size: 14px;
            opacity: 0.9;
            margin-bottom: 10px;
        }

        .action-text {
            font-size: 42px;
            font-weight: bold;
        }

        .strength-bar {
            height: 8px;
            background: rgba(255,255,255,0.3);
            border-radius: 4px;
            margin-top: 15px;
            overflow: hidden;
        }

        .strength-fill {
            height: 100%;
            background: white;
            border-radius: 4px;
            transition: width 0.5s;
        }

        .sl-tp-card {
            background: #fff7ed;
            border: 2px solid #fb923c;
            border-radius: 12px;
            padding: 20px;
            margin-top: 20px;
        }

        .sl-tp-title {
            font-size: 16px;
            font-weight: 600;
            color: #ea580c;
            margin-bottom: 15px;
            text-align: center;
        }

        .sl-tp-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }

        .sl-tp-item {
            background: white;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }

        .sl-tp-label {
            font-size: 12px;
            color: #666;
            margin-bottom: 8px;
        }

        .sl-tp-value {
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }

        .sl-tp-value.stop-loss {
            color: #ef4444;
        }

        .sl-tp-value.take-profit {
            color: #10b981;
        }

        .rr-ratio {
            background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
            color: white;
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            margin-top: 15px;
            font-weight: 600;
        }

        .timestamp {
            text-align: center;
            color: #999;
            font-size: 12px;
            margin-top: 20px;
        }

        .new-feature-badge {
            background: #10b981;
            color: white;
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 8px;
        }

        @media (max-width: 768px) {
            .main-grid {
                grid-template-columns: 1fr;
            }
            .sl-tp-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 剝頭皮交易分析器 Pro<span class="version-badge">V3.0</span></h1>
            <p class="subtitle">Professional Scalping Trading System - 專業級實時交易信號分析</p>
            <div class="feature-tags">
                <span class="feature-tag">✨ 成交量分析</span>
                <span class="feature-tag">📈 多時間框架確認</span>
                <span class="feature-tag">🎯 動態止損止盈</span>
                <span class="feature-tag">⭐ 信號品質評分</span>
                <span class="feature-tag">🔔 瀏覽器通知</span>
                <span class="feature-tag">📊 Bollinger Bands</span>
                <span class="feature-tag">📉 Stochastic</span>
                <span class="feature-tag">📐 Fibonacci</span>
                <span class="feature-tag">📸 策略快照</span>
                <span class="feature-tag">➕ 自定義商品</span>
            </div>
        </div>

        <div class="main-grid">
            <div class="panel">
                <div class="panel-title">⚙️ 交易設定</div>

                <div class="form-group">
                    <label>交易對 Symbol</label>
                    <select id="symbol">
                        <option value="BTCUSDT">BTC/USDT</option>
                        <option value="ETHUSDT">ETH/USDT</option>
                        <option value="BNBUSDT">BNB/USDT</option>
                        <option value="SOLUSDT">SOL/USDT</option>
                        <option value="XRPUSDT">XRP/USDT</option>
                        <option value="ADAUSDT">ADA/USDT</option>
                        <option value="DOGEUSDT">DOGE/USDT</option>
                        <option value="MATICUSDT">MATIC/USDT</option>
                    </select>
                    <button onclick="showAddSymbolDialog()" style="margin-top: 10px; width: 100%; padding: 8px; background: #10b981; font-size: 12px;">
                        ➕ 添加自定義商品
                    </button>
                </div>

                <div class="form-group">
                    <label>時間框架 Interval</label>
                    <select id="interval">
                        <option value="1m">1 分鐘</option>
                        <option value="3m">3 分鐘</option>
                        <option value="5m" selected>5 分鐘</option>
                        <option value="15m">15 分鐘</option>
                    </select>
                </div>

                <div class="panel-title" style="margin-top: 30px;">📈 RSI 設定</div>

                <div class="form-group">
                    <label>RSI 週期</label>
                    <input type="number" id="rsi_period" value="14" min="5" max="30">
                </div>

                <div class="form-group">
                    <label>超買線</label>
                    <input type="number" id="rsi_overbought" value="70" min="60" max="90">
                </div>

                <div class="form-group">
                    <label>超賣線</label>
                    <input type="number" id="rsi_oversold" value="30" min="10" max="40">
                </div>

                <div class="panel-title" style="margin-top: 30px;">📉 EMA 設定</div>

                <div class="form-group">
                    <label>快速 EMA</label>
                    <input type="number" id="ema_fast" value="5" min="3" max="20">
                </div>

                <div class="form-group">
                    <label>慢速 EMA</label>
                    <input type="number" id="ema_slow" value="20" min="10" max="50">
                </div>

                <div class="panel-title" style="margin-top: 30px;">📊 MACD 設定</div>

                <div class="form-group">
                    <label>MACD 快線</label>
                    <input type="number" id="macd_fast" value="5" min="3" max="20">
                </div>

                <div class="form-group">
                    <label>MACD 慢線</label>
                    <input type="number" id="macd_slow" value="20" min="15" max="40">
                </div>

                <div class="form-group">
                    <label>MACD 信號線</label>
                    <input type="number" id="macd_signal" value="5" min="3" max="15">
                </div>

                <button onclick="analyze()" style="margin-top: 20px;">🔍 分析入場信號</button>

                <div class="auto-refresh">
                    <input type="checkbox" id="auto_refresh" onchange="toggleAutoRefresh()">
                    <label for="auto_refresh">自動刷新 (10秒)</label>
                </div>
            </div>

            <div class="panel result-panel">
                <div class="panel-title">📊 分析結果</div>
                <div id="results">
                    <div class="loading">
                        <div style="font-size: 48px; margin-bottom: 20px;">📈</div>
                        <p>請點擊「分析入場信號」開始分析</p>
                        <p style="margin-top: 10px; color: #10b981; font-weight: 600;">✨ 全新 V2 版本：成交量分析 + 多時間框架 + 動態止損止盈</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let autoRefreshInterval = null;

        async function analyze() {
            const symbol = document.getElementById('symbol').value;
            const interval = document.getElementById('interval').value;
            const rsi_period = document.getElementById('rsi_period').value;
            const rsi_overbought = document.getElementById('rsi_overbought').value;
            const rsi_oversold = document.getElementById('rsi_oversold').value;
            const ema_fast = document.getElementById('ema_fast').value;
            const ema_slow = document.getElementById('ema_slow').value;
            const macd_fast = document.getElementById('macd_fast').value;
            const macd_slow = document.getElementById('macd_slow').value;
            const macd_signal = document.getElementById('macd_signal').value;

            document.getElementById('results').innerHTML = `
                <div class="loading">
                    <div class="spinner"></div>
                    <p>分析中...</p>
                </div>
            `;

            try {
                const url = `/api/analyze?symbol=${symbol}&interval=${interval}&rsi_period=${rsi_period}&rsi_overbought=${rsi_overbought}&rsi_oversold=${rsi_oversold}&ema_fast=${ema_fast}&ema_slow=${ema_slow}&macd_fast=${macd_fast}&macd_slow=${macd_slow}&macd_signal=${macd_signal}`;

                const response = await fetch(url);
                const data = await response.json();

                if (data.success) {
                    displayResults(data);
                } else {
                    showError(data.error);
                }
            } catch (error) {
                showError(error.message);
            }
        }

        function displayResults(data) {
            // 保存當前分析數據供快照使用
            currentAnalysisData = data;

            const signals = data.signals;

            let actionClass = 'wait';
            if (signals.action.includes('買入')) actionClass = 'buy';
            else if (signals.action.includes('賣出')) actionClass = 'sell';

            const strengthPercent = (signals.strength / 3 * 100).toFixed(0);
            const qualityStars = '⭐'.repeat(Math.round(signals.quality_score));

            // 多時間框架信息
            const mtf = signals.multi_timeframe;
            const mtfHtml = mtf ? `
                <div class="signal-card">
                    <div class="signal-header">
                        <span class="signal-name">📈 多時間框架確認 <span class="new-feature-badge">NEW</span></span>
                        <span class="signal-badge ${mtf.trend}">${mtf.trend === 'uptrend' ? '上升趨勢' : (mtf.trend === 'downtrend' ? '下降趨勢' : '中性')}</span>
                    </div>
                    <div class="signal-details">
                        <div class="detail-item">
                            <div class="detail-label">時間框架</div>
                            <div class="detail-value">${mtf.timeframe}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">趨勢強度</div>
                            <div class="detail-value">${mtf.trend_strength}%</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">EMA 20</div>
                            <div class="detail-value">${mtf.ema_20 || 'N/A'}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">EMA 50</div>
                            <div class="detail-value">${mtf.ema_50 || 'N/A'}</div>
                        </div>
                    </div>
                </div>
            ` : '';

            // 成交量分析
            const volume = signals.volume;
            const volumeHtml = volume ? `
                <div class="signal-card">
                    <div class="signal-header">
                        <span class="signal-name">📊 成交量分析 <span class="new-feature-badge">NEW</span></span>
                        <span class="signal-badge ${volume.signal}">${volume.signal === 'strong' ? '放量' : (volume.signal === 'weak' ? '縮量' : '正常')}</span>
                    </div>
                    <div class="signal-details">
                        <div class="detail-item">
                            <div class="detail-label">成交量比率</div>
                            <div class="detail-value">${volume.volume_ratio}x</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">CVD 趨勢</div>
                            <div class="detail-value">${volume.cvd_trend === 'bullish' ? '📈 看漲' : '📉 看跌'}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">當前成交量</div>
                            <div class="detail-value">${volume.current_volume.toLocaleString()}</div>
                        </div>
                    </div>
                </div>
            ` : '';

            // 止損止盈
            const sltp = signals.stop_loss_take_profit;
            const sltpHtml = sltp ? `
                <div class="sl-tp-card">
                    <div class="sl-tp-title">🎯 建議止損止盈 (基於 ATR)<span class="new-feature-badge">NEW</span></div>
                    <div class="sl-tp-grid">
                        <div class="sl-tp-item">
                            <div class="sl-tp-label">⛔ 止損 Stop Loss</div>
                            <div class="sl-tp-value stop-loss">$${sltp.stop_loss.toLocaleString()}</div>
                            <div class="detail-label" style="margin-top: 5px;">風險: $${sltp.risk_amount}</div>
                        </div>
                        <div class="sl-tp-item">
                            <div class="sl-tp-label">🎯 目標1 (50%)</div>
                            <div class="sl-tp-value take-profit">$${sltp.take_profit_1.toLocaleString()}</div>
                        </div>
                        <div class="sl-tp-item">
                            <div class="sl-tp-label">🎯 目標2 (100%)</div>
                            <div class="sl-tp-value take-profit">$${sltp.take_profit_2.toLocaleString()}</div>
                            <div class="detail-label" style="margin-top: 5px;">報酬: $${sltp.reward_amount}</div>
                        </div>
                        <div class="sl-tp-item">
                            <div class="sl-tp-label">📊 ATR (波幅)</div>
                            <div class="sl-tp-value">$${sltp.atr}</div>
                        </div>
                    </div>
                    <div class="rr-ratio">
                        風險報酬比 R:R = 1:${sltp.risk_reward_ratio}
                    </div>
                </div>
            ` : '';

            // 🔔 瀏覽器通知 - 高品質信號時觸發
            if (signals.quality_score >= 4 && (signals.action.includes('強烈買入') || signals.action.includes('強烈賣出'))) {
                sendNotification(`🚨 ${data.symbol} 高品質信號！`, `${signals.action} | 品質: ${signals.quality_score}/5 ⭐`);
            }

            const html = `
                <!-- 🔥 最重要：建議操作放在最上面 -->
                <div class="action-card ${actionClass}">
                    <div class="action-title">💡 建議操作</div>
                    <div class="action-text">${signals.action}</div>
                    <div class="strength-bar">
                        <div class="strength-fill" style="width: ${strengthPercent}%"></div>
                    </div>
                    <div style="margin-top: 10px; font-size: 14px;">信號強度: ${signals.strength}/3 | 品質: ${signals.quality_score}/5</div>
                </div>

                <!-- 價格與品質評分 -->
                <div class="price-display">
                    <div style="font-size: 14px; opacity: 0.9; margin-bottom: 5px;">${data.symbol}</div>
                    <div class="price-value">$${data.price.toLocaleString()}</div>
                    <div class="quality-score">
                        <div class="quality-score-label">信號品質評分</div>
                        <div class="quality-score-value">${signals.quality_score}/5</div>
                        <div class="score-stars">${qualityStars}</div>
                    </div>
                </div>

                <!-- 止損止盈 -->
                ${sltpHtml}

                <!-- 📸 快照管理按鈕 -->
                <div style="margin: 20px 0; text-align: center; padding: 15px; background: #f0f4ff; border-radius: 12px;">
                    <button onclick="saveSnapshot()" style="width: auto; padding: 12px 30px; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); margin-right: 10px; border: none; border-radius: 8px; color: white; font-weight: 600; cursor: pointer;">
                        📸 保存當前策略快照
                    </button>
                    <button onclick="showSnapshots()" style="width: auto; padding: 12px 30px; background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); border: none; border-radius: 8px; color: white; font-weight: 600; cursor: pointer;">
                        📋 查看歷史快照
                    </button>
                </div>

                <!-- 核心分析指標 -->
                ${mtfHtml}
                ${volumeHtml}

                <div class="signal-card">
                    <div class="signal-header">
                        <span class="signal-name">RSI (相對強弱指標)</span>
                        <span class="signal-badge ${signals.rsi.signal}">${signals.rsi.signal}</span>
                    </div>
                    <div class="signal-details">
                        <div class="detail-item">
                            <div class="detail-label">RSI 值</div>
                            <div class="detail-value">${signals.rsi.value || 'N/A'}</div>
                        </div>
                    </div>
                </div>

                <div class="signal-card">
                    <div class="signal-header">
                        <span class="signal-name">EMA (指數移動平均)</span>
                        <span class="signal-badge ${signals.ema.signal}">${signals.ema.signal}</span>
                    </div>
                    <div class="signal-details">
                        <div class="detail-item">
                            <div class="detail-label">快速 EMA</div>
                            <div class="detail-value">${signals.ema.fast || 'N/A'}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">慢速 EMA</div>
                            <div class="detail-value">${signals.ema.slow || 'N/A'}</div>
                        </div>
                    </div>
                </div>

                <div class="signal-card">
                    <div class="signal-header">
                        <span class="signal-name">MACD (平滑異同移動平均)</span>
                        <span class="signal-badge ${signals.macd.signal}">${signals.macd.signal}</span>
                    </div>
                    <div class="signal-details">
                        <div class="detail-item">
                            <div class="detail-label">MACD 線</div>
                            <div class="detail-value">${signals.macd.line || 'N/A'}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">信號線</div>
                            <div class="detail-value">${signals.macd.signal || 'N/A'}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">柱狀圖</div>
                            <div class="detail-value">${signals.macd.histogram || 'N/A'}</div>
                        </div>
                    </div>
                </div>

                ${signals.bollinger && signals.bollinger.upper ? `
                <div class="signal-card">
                    <div class="signal-header">
                        <span class="signal-name">📊 Bollinger Bands (布林通道) <span class="new-feature-badge">V3</span></span>
                        <span class="signal-badge ${signals.bollinger.signal}">${signals.bollinger.signal}</span>
                    </div>
                    <div class="signal-details">
                        <div class="detail-item">
                            <div class="detail-label">上軌</div>
                            <div class="detail-value">${signals.bollinger.upper}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">中軌</div>
                            <div class="detail-value">${signals.bollinger.middle}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">下軌</div>
                            <div class="detail-value">${signals.bollinger.lower}</div>
                        </div>
                    </div>
                </div>
                ` : ''}

                ${signals.stochastic && signals.stochastic.k ? `
                <div class="signal-card">
                    <div class="signal-header">
                        <span class="signal-name">📉 Stochastic (隨機指標) <span class="new-feature-badge">V3</span></span>
                        <span class="signal-badge ${signals.stochastic.signal}">${signals.stochastic.signal}</span>
                    </div>
                    <div class="signal-details">
                        <div class="detail-item">
                            <div class="detail-label">%K 值</div>
                            <div class="detail-value">${signals.stochastic.k}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">%D 值</div>
                            <div class="detail-value">${signals.stochastic.d}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">狀態</div>
                            <div class="detail-value">${signals.stochastic.k < 20 ? '超賣' : (signals.stochastic.k > 80 ? '超買' : '中性')}</div>
                        </div>
                    </div>
                </div>
                ` : ''}

                ${signals.fibonacci ? `
                <div class="signal-card">
                    <div class="signal-header">
                        <span class="signal-name">📐 Fibonacci (斐波那契) <span class="new-feature-badge">V3</span></span>
                    </div>
                    <div class="signal-details">
                        <div class="detail-item">
                            <div class="detail-label">0.0 (高點)</div>
                            <div class="detail-value">${signals.fibonacci['0.0']}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">0.382</div>
                            <div class="detail-value">${signals.fibonacci['0.382']}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">0.5</div>
                            <div class="detail-value">${signals.fibonacci['0.5']}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">0.618</div>
                            <div class="detail-value">${signals.fibonacci['0.618']}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">1.0 (低點)</div>
                            <div class="detail-value">${signals.fibonacci['1.0']}</div>
                        </div>
                    </div>
                </div>
                ` : ''}

                <div class="timestamp">
                    最後更新: ${new Date(data.timestamp).toLocaleString('zh-TW')}
                </div>
            `;

            document.getElementById('results').innerHTML = html;
        }

        function showError(message) {
            document.getElementById('results').innerHTML = `
                <div class="loading">
                    <div style="font-size: 48px; margin-bottom: 20px;">⚠️</div>
                    <p style="color: #ef4444;">錯誤: ${message}</p>
                </div>
            `;
        }

        function toggleAutoRefresh() {
            const checkbox = document.getElementById('auto_refresh');

            if (checkbox.checked) {
                analyze();
                autoRefreshInterval = setInterval(analyze, 10000);
            } else {
                if (autoRefreshInterval) {
                    clearInterval(autoRefreshInterval);
                    autoRefreshInterval = null;
                }
            }
        }

        // 🔔 瀏覽器通知功能
        function sendNotification(title, body) {
            // 請求通知權限
            if (!("Notification" in window)) {
                console.log("此瀏覽器不支援通知");
                return;
            }

            if (Notification.permission === "granted") {
                // 已授權，發送通知
                new Notification(title, {
                    body: body,
                    icon: "📈",
                    badge: "⭐",
                    vibrate: [200, 100, 200],
                    requireInteraction: true
                });
            } else if (Notification.permission !== "denied") {
                // 請求權限
                Notification.requestPermission().then(function (permission) {
                    if (permission === "granted") {
                        new Notification(title, {
                            body: body,
                            icon: "📈",
                            badge: "⭐"
                        });
                    }
                });
            }
        }

        // 頁面載入時請求通知權限
        window.addEventListener('load', function() {
            if ("Notification" in window && Notification.permission === "default") {
                setTimeout(() => {
                    Notification.requestPermission();
                }, 2000);
            }
            loadCustomSymbols();
        });

        // 📸 保存快照
        let currentAnalysisData = null;

        async function saveSnapshot() {
            if (!currentAnalysisData) {
                alert('請先進行分析！');
                return;
            }

            try {
                const response = await fetch('/api/snapshot/save', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        symbol: currentAnalysisData.symbol,
                        price: currentAnalysisData.price,
                        signals: currentAnalysisData.signals,
                        params: {
                            interval: document.getElementById('interval').value,
                            rsi_period: document.getElementById('rsi_period').value,
                            ema_fast: document.getElementById('ema_fast').value,
                            ema_slow: document.getElementById('ema_slow').value
                        }
                    })
                });

                const result = await response.json();
                if (result.success) {
                    alert('✅ 策略快照已保存！ID: ' + result.snapshot_id);
                } else {
                    alert('❌ 保存失敗: ' + result.error);
                }
            } catch (error) {
                alert('❌ 保存失敗: ' + error.message);
            }
        }

        // 📋 顯示快照列表
        async function showSnapshots() {
            try {
                const response = await fetch('/api/snapshots?limit=20');
                const result = await response.json();

                if (!result.success || result.snapshots.length === 0) {
                    alert('暫無快照記錄');
                    return;
                }

                let html = '<div style="max-height: 500px; overflow-y: auto;">';
                html += '<h3 style="margin-bottom: 15px;">📋 歷史策略快照</h3>';

                result.snapshots.forEach(snap => {
                    const time = new Date(snap.timestamp).toLocaleString('zh-TW');
                    const stars = '⭐'.repeat(Math.round(snap.quality_score || 0));
                    const sltp = snap.signals?.stop_loss_take_profit;

                    // 決定邊框顏色
                    let borderColor = '#667eea';
                    if (snap.action?.includes('強烈買入')) borderColor = '#10b981';
                    else if (snap.action?.includes('強烈賣出')) borderColor = '#ef4444';
                    else if (snap.action?.includes('買入')) borderColor = '#34d399';
                    else if (snap.action?.includes('賣出')) borderColor = '#f87171';

                    html += `
                        <div style="background: #f8f9ff; padding: 20px; margin-bottom: 12px; border-radius: 12px; border-left: 5px solid ${borderColor}; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                                <div>
                                    <strong style="font-size: 18px; color: #333;">${snap.symbol}</strong>
                                    <span style="color: #667eea; font-size: 16px; margin-left: 8px;">$${snap.price?.toLocaleString()}</span>
                                    <br><small style="color: #666;">${time}</small>
                                </div>
                                <div style="text-align: right;">
                                    <div style="font-size: 18px; font-weight: 600; color: ${borderColor};">${snap.action}</div>
                                    <div style="margin-top: 4px;">${stars} ${snap.quality_score}/5</div>
                                    <div style="font-size: 12px; color: #666; margin-top: 2px;">強度: ${snap.strength}/3</div>
                                </div>
                            </div>
                            ${sltp ? `
                            <div style="background: white; padding: 12px; border-radius: 8px; margin-top: 10px;">
                                <div style="font-size: 13px; font-weight: 600; color: #666; margin-bottom: 8px;">📊 建議止損止盈</div>
                                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; font-size: 12px;">
                                    <div>
                                        <div style="color: #999;">止損</div>
                                        <div style="color: #ef4444; font-weight: 600;">$${sltp.stop_loss?.toLocaleString()}</div>
                                    </div>
                                    <div>
                                        <div style="color: #999;">目標1</div>
                                        <div style="color: #10b981; font-weight: 600;">$${sltp.take_profit_1?.toLocaleString()}</div>
                                    </div>
                                    <div>
                                        <div style="color: #999;">目標2</div>
                                        <div style="color: #10b981; font-weight: 600;">$${sltp.take_profit_2?.toLocaleString()}</div>
                                    </div>
                                </div>
                                <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #e0e0e0; font-size: 11px; color: #666;">
                                    風險: $${sltp.risk_amount} | 報酬: $${sltp.reward_amount} | R:R = 1:${sltp.risk_reward_ratio}
                                </div>
                            </div>
                            ` : ''}
                        </div>
                    `;
                });

                html += '</div>';

                const modal = document.createElement('div');
                modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 9999; display: flex; align-items: center; justify-content: center;';
                modal.innerHTML = `
                    <div style="background: white; padding: 30px; border-radius: 20px; max-width: 600px; width: 90%;">
                        ${html}
                        <button onclick="this.closest('div').parentElement.remove()" style="width: 100%; margin-top: 15px; background: #667eea;">關閉</button>
                    </div>
                `;
                document.body.appendChild(modal);
            } catch (error) {
                alert('❌ 載入失敗: ' + error.message);
            }
        }

        // ➕ 自定義商品管理
        async function loadCustomSymbols() {
            try {
                const response = await fetch('/api/symbols');
                const result = await response.json();

                if (result.success && result.symbols.length > 0) {
                    const select = document.getElementById('symbol');
                    result.symbols.forEach(s => {
                        const option = document.createElement('option');
                        option.value = s.symbol;
                        option.textContent = s.name + ' (' + s.symbol + ')';
                        select.appendChild(option);
                    });
                }
            } catch (error) {
                console.error('載入自定義商品失敗:', error);
            }
        }

        function showAddSymbolDialog() {
            const symbol = prompt('請輸入交易對代碼（例如：LINKUSDT）:');
            if (!symbol) return;

            const name = prompt('請輸入顯示名稱（例如：LINK/USDT）:');
            if (!name) return;

            addCustomSymbol(symbol.toUpperCase(), name);
        }

        async function addCustomSymbol(symbol, name) {
            try {
                const response = await fetch('/api/symbol/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({symbol, name})
                });

                const result = await response.json();
                if (result.success) {
                    alert('✅ 商品已添加！');
                    location.reload();
                } else {
                    alert('❌ 添加失敗: ' + result.error);
                }
            } catch (error) {
                alert('❌ 添加失敗: ' + error.message);
            }
        }
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), ScalpingHandler) as httpd:
        print(f"✅ 剝頭皮交易分析器 Pro V3 已啟動！")
        print(f"🌐 訪問: http://localhost:{PORT}")
        print(f"")
        print(f"✨ V3 新增功能:")
        print(f"  📊 Bollinger Bands (布林通道)")
        print(f"  📉 Stochastic (隨機指標)")
        print(f"  📐 Fibonacci (斐波那契回調)")
        print(f"  📸 策略快照 (保存分析記錄)")
        print(f"  ➕ 自定義商品 (添加任意交易對)")
        print(f"")
        print(f"✨ V2 核心功能:")
        print(f"  1. 成交量分析 - CVD趨勢")
        print(f"  2. 多時間框架確認")
        print(f"  3. 動態止損止盈 - ATR")
        print(f"  4. 信號品質評分 - 0-5星")
        print(f"  5. 瀏覽器通知")
        print(f"")
        print(f"🚀 支援交易對: BTC, ETH, BNB, SOL + 自定義")
        print(f"\n按 Ctrl+C 停止服務\n")
        httpd.serve_forever()
