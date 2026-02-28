#!/usr/bin/env python3
"""
Scalping Analyzer V2 - Pro Trading System
專業剝頭皮交易系統 V2.0

新增功能：
1. 成交量分析 (Volume Analysis)
2. 多時間框架確認 (Multi-Timeframe Confirmation)
3. 動態止損止盈計算 (Dynamic Stop-Loss/Take-Profit)
"""

import http.server
import socketserver
import json
import urllib.request
import urllib.parse
import ssl
from datetime import datetime
import math

PORT = 80
BINANCE_API = "https://api.binance.com/api/v3"

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

        # 信號評分系統
        signals = {
            'rsi': {'value': rsi, 'signal': 'neutral'},
            'ema': {'fast': ema_fast, 'slow': ema_slow, 'signal': 'neutral'},
            'macd': {'line': macd_line, 'signal': signal_line, 'histogram': histogram, 'signal': 'neutral'},
            'volume': volume_analysis,
            'multi_timeframe': mtf_analysis,
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


HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>剝頭皮交易分析器 Pro V2 | Scalping Analyzer Pro</title>
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
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }

        h1 {
            color: #333;
            font-size: 32px;
            margin-bottom: 5px;
        }

        .version-badge {
            display: inline-block;
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            margin-left: 10px;
        }

        .subtitle {
            color: #666;
            font-size: 14px;
            margin-top: 10px;
        }

        .feature-tags {
            display: flex;
            gap: 10px;
            margin-top: 15px;
            flex-wrap: wrap;
        }

        .feature-tag {
            background: #f0f4ff;
            color: #667eea;
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 12px;
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
            <h1>📊 剝頭皮交易分析器 Pro<span class="version-badge">V2.0</span></h1>
            <p class="subtitle">Professional Scalping Trading System - 專業級實時交易信號分析</p>
            <div class="feature-tags">
                <span class="feature-tag">✨ 成交量分析</span>
                <span class="feature-tag">📈 多時間框架確認</span>
                <span class="feature-tag">🎯 動態止損止盈</span>
                <span class="feature-tag">⭐ 信號品質評分</span>
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
        });
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), ScalpingHandler) as httpd:
        print(f"✅ 剝頭皮交易分析器 Pro V2 已啟動！")
        print(f"🌐 訪問: http://localhost:{PORT}")
        print(f"")
        print(f"✨ 新功能:")
        print(f"  1. 成交量分析 - 放量/縮量/CVD趨勢")
        print(f"  2. 多時間框架確認 - 過濾假信號")
        print(f"  3. 動態止損止盈 - ATR自動計算")
        print(f"  4. 信號品質評分 - 0-5星評級")
        print(f"")
        print(f"🚀 支援交易對: BTC, ETH, BNB, SOL 等")
        print(f"\n按 Ctrl+C 停止服務\n")
        httpd.serve_forever()
