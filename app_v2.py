#!/usr/bin/env python3
"""
Scalping Analyzer V3.2 - Pro Trading System
專業剝頭皮交易系統 V3.2

V3.2 新增功能：
1. 即時 K 線圖表 (TradingView Lightweight Charts)
2. 智能重試機制 (指數退避 + 錯誤分類)
3. 中文錯誤訊息 + 錯誤類型分類
4. 進度指示器 + Toast 通知取代 alert()
5. EMA/布林通道 overlay 時間序列

既有功能：
- 成交量分析 / 多時間框架確認 / 動態止損止盈
- 信號品質評分 / 瀏覽器通知
- Bollinger Bands / Stochastic / Fibonacci
- 自定義商品 / 策略快照 / 智能警報
"""

import http.server
import socketserver
import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
from datetime import datetime
import math
import os
import time
import sys

def parse_port():
    """從命令列參數解析 port，支援 --port <N> 或 -p <N>"""
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg in ('--port', '-p') and i + 1 < len(args):
            try:
                port = int(args[i + 1])
                if not (1 <= port <= 65535):
                    raise ValueError
                return port
            except ValueError:
                print(f"❌ 無效的 port 值：{args[i + 1]}（應為 1–65535）")
                sys.exit(1)
    return 80  # 預設值

PORT = parse_port()

def parse_prefix():
    """從命令列參數解析路徑前綴，支援 --prefix <PATH>"""
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == '--prefix' and i + 1 < len(args):
            prefix = args[i + 1].rstrip('/')
            if prefix and not prefix.startswith('/'):
                prefix = '/' + prefix
            return prefix
    return ''  # 預設無前綴

PREFIX = parse_prefix()
BINANCE_API = "https://api.binance.com/api/v3"


def fetch_with_retry(url, ctx=None, max_retries=3, base_timeout=10):
    """帶重試機制的 HTTP 請求（指數退避）"""
    if ctx is None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    last_error = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, context=ctx, timeout=base_timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            last_error = e
            # 400 無效交易對，不重試
            if e.code == 400:
                raise
            # 429 限速，延長等待
            if e.code == 429:
                time.sleep(2 ** attempt * 2)
                continue
            # 5xx 伺服器錯誤，重試
            if e.code >= 500:
                time.sleep(2 ** attempt * 0.5)
                continue
            raise
        except urllib.error.URLError as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt * 0.5)
                continue
        except TimeoutError:
            last_error = TimeoutError("連線逾時")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt * 0.5)
                continue
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt * 0.5)
                continue

    raise last_error


def classify_error(e):
    """錯誤分類，返回結構化中文錯誤資訊"""
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 400:
            return {
                'error_type': 'invalid_symbol',
                'error': '無效的交易對，請確認交易對名稱是否正確',
                'icon': 'warning'
            }
        if e.code == 429:
            return {
                'error_type': 'rate_limit',
                'error': '請求過於頻繁，請稍後再試',
                'icon': 'clock'
            }
        if e.code >= 500:
            return {
                'error_type': 'server_error',
                'error': 'Binance 伺服器暫時不可用，請稍後再試',
                'icon': 'server'
            }
        return {
            'error_type': 'api_error',
            'error': f'API 錯誤 (HTTP {e.code})',
            'icon': 'warning'
        }
    if isinstance(e, urllib.error.URLError):
        return {
            'error_type': 'network',
            'error': '網路連線失敗，請檢查網路狀態',
            'icon': 'network'
        }
    if isinstance(e, (TimeoutError, OSError)):
        if 'timed out' in str(e).lower() or '逾時' in str(e):
            return {
                'error_type': 'timeout',
                'error': '連線逾時，請檢查網路或稍後再試',
                'icon': 'clock'
            }
    return {
        'error_type': 'unknown',
        'error': f'發生未知錯誤：{str(e)}',
        'icon': 'warning'
    }
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

    @staticmethod
    def export_to_csv():
        """匯出快照為 CSV 格式"""
        try:
            if not os.path.exists(SNAPSHOTS_FILE):
                return {'success': False, 'error': 'No snapshots found'}

            with open(SNAPSHOTS_FILE, 'r', encoding='utf-8') as f:
                snapshots = json.load(f)

            if not snapshots:
                return {'success': False, 'error': 'No snapshots to export'}

            # 建立 CSV 內容
            csv_lines = []
            # CSV 標頭
            csv_lines.append('時間,交易對,價格,操作建議,信號強度,品質評分,止損,止盈1,止盈2,RSI,MACD信號,成交量信號,趨勢')

            for snapshot in snapshots:
                signals = snapshot.get('signals', {})
                sl_tp = signals.get('stop_loss_take_profit', {})

                line = ','.join([
                    f'"{snapshot.get("timestamp", "")}"',
                    snapshot.get('symbol', ''),
                    str(snapshot.get('price', 0)),
                    f'"{snapshot.get("action", "")}"',
                    str(snapshot.get('strength', 0)),
                    str(snapshot.get('quality_score', 0)),
                    str(sl_tp.get('stop_loss', 0)),
                    str(sl_tp.get('take_profit_1', 0)),
                    str(sl_tp.get('take_profit_2', 0)),
                    str(signals.get('rsi', {}).get('value', 0)),
                    f'"{signals.get("macd", {}).get("signal", "")}"',
                    f'"{signals.get("volume", {}).get("signal", "")}"',
                    f'"{signals.get("multi_timeframe", {}).get("trend", "")}"'
                ])
                csv_lines.append(line)

            csv_content = '\n'.join(csv_lines)
            return {'success': True, 'csv': csv_content}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def search_snapshots(symbol=None, action=None, min_quality=None, start_date=None, end_date=None):
        """搜尋與篩選快照"""
        try:
            if not os.path.exists(SNAPSHOTS_FILE):
                return []

            with open(SNAPSHOTS_FILE, 'r', encoding='utf-8') as f:
                snapshots = json.load(f)

            filtered = snapshots

            # 依交易對篩選
            if symbol:
                filtered = [s for s in filtered if s.get('symbol') == symbol]

            # 依操作類型篩選
            if action:
                filtered = [s for s in filtered if action.lower() in s.get('action', '').lower()]

            # 依品質評分篩選
            if min_quality is not None:
                filtered = [s for s in filtered if s.get('quality_score', 0) >= min_quality]

            # 依日期範圍篩選
            if start_date:
                filtered = [s for s in filtered if s.get('timestamp', '') >= start_date]
            if end_date:
                filtered = [s for s in filtered if s.get('timestamp', '') <= end_date]

            return filtered[::-1]  # 倒序返回（最新的在前）
        except Exception as e:
            return []


class AlertManager:
    """警報系統管理器"""
    ALERTS_FILE = "alerts.json"

    @staticmethod
    def add_alert(alert_type, symbol, condition, value, enabled=True):
        """新增警報
        alert_type: 'price' | 'quality' | 'signal'
        condition: 'above' | 'below' | 'equal'
        value: 觸發值
        """
        try:
            alerts = AlertManager.get_alerts()

            alert = {
                'id': len(alerts) + 1,
                'type': alert_type,
                'symbol': symbol,
                'condition': condition,
                'value': value,
                'enabled': enabled,
                'created_at': datetime.now().isoformat(),
                'triggered_count': 0,
                'last_triggered': None
            }

            alerts.append(alert)

            with open(AlertManager.ALERTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(alerts, f, ensure_ascii=False, indent=2)

            return {'success': True, 'alert_id': alert['id']}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def get_alerts():
        """獲取所有警報"""
        try:
            if not os.path.exists(AlertManager.ALERTS_FILE):
                return []

            with open(AlertManager.ALERTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            return []

    @staticmethod
    def delete_alert(alert_id):
        """刪除警報"""
        try:
            alerts = AlertManager.get_alerts()
            alerts = [a for a in alerts if a.get('id') != alert_id]

            with open(AlertManager.ALERTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(alerts, f, ensure_ascii=False, indent=2)

            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def toggle_alert(alert_id, enabled):
        """啟用/停用警報"""
        try:
            alerts = AlertManager.get_alerts()

            for alert in alerts:
                if alert.get('id') == alert_id:
                    alert['enabled'] = enabled
                    break

            with open(AlertManager.ALERTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(alerts, f, ensure_ascii=False, indent=2)

            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def check_alerts(symbol, price, quality_score, action):
        """檢查是否觸發警報"""
        try:
            alerts = AlertManager.get_alerts()
            triggered = []

            for alert in alerts:
                if not alert.get('enabled'):
                    continue

                # 檢查商品匹配（空白表示所有商品）
                if alert.get('symbol') and alert.get('symbol') != symbol:
                    continue

                is_triggered = False
                message = ""

                # 價格警報
                if alert['type'] == 'price':
                    value = float(alert['value'])
                    if alert['condition'] == 'above' and price > value:
                        is_triggered = True
                        message = f"{symbol} 價格 ${price} 突破 ${value}"
                    elif alert['condition'] == 'below' and price < value:
                        is_triggered = True
                        message = f"{symbol} 價格 ${price} 跌破 ${value}"

                # 品質評分警報
                elif alert['type'] == 'quality':
                    value = float(alert['value'])
                    if alert['condition'] == 'above' and quality_score >= value:
                        is_triggered = True
                        message = f"{symbol} 信號品質 {quality_score}★ 達到 {value}★ 以上"

                # 信號類型警報
                elif alert['type'] == 'signal':
                    target_signal = alert['value'].lower()
                    if target_signal in action.lower():
                        is_triggered = True
                        message = f"{symbol} 出現 {action} 信號"

                if is_triggered:
                    # 更新觸發記錄
                    alert['triggered_count'] = alert.get('triggered_count', 0) + 1
                    alert['last_triggered'] = datetime.now().isoformat()

                    triggered.append({
                        'alert_id': alert['id'],
                        'type': alert['type'],
                        'message': message,
                        'symbol': symbol,
                        'price': price,
                        'quality_score': quality_score,
                        'action': action
                    })

            # 保存更新後的警報狀態
            if triggered:
                with open(AlertManager.ALERTS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(alerts, f, ensure_ascii=False, indent=2)

            return triggered
        except Exception as e:
            return []


class PresetManager:
    """參數預設組合管理器"""

    # 預設參數組合
    PRESETS = {
        'scalping': {
            'name': '超短線剝頭皮',
            'description': '適合1-3分鐘快速進出，高頻交易',
            'params': {
                'interval': '1m',
                'rsi_period': 7,
                'rsi_overbought': 75,
                'rsi_oversold': 25,
                'ema_fast': 3,
                'ema_slow': 10,
                'macd_fast': 3,
                'macd_slow': 10,
                'macd_signal': 3,
                'atr_period': 7,
                'risk_reward': 1.5
            }
        },
        'daytrading': {
            'name': '短線當沖',
            'description': '適合5-15分鐘，日內交易',
            'params': {
                'interval': '5m',
                'rsi_period': 14,
                'rsi_overbought': 70,
                'rsi_oversold': 30,
                'ema_fast': 5,
                'ema_slow': 20,
                'macd_fast': 5,
                'macd_slow': 20,
                'macd_signal': 5,
                'atr_period': 14,
                'risk_reward': 2
            }
        },
        'conservative': {
            'name': '穩健策略',
            'description': '適合15分鐘以上，降低假信號',
            'params': {
                'interval': '15m',
                'rsi_period': 21,
                'rsi_overbought': 65,
                'rsi_oversold': 35,
                'ema_fast': 8,
                'ema_slow': 34,
                'macd_fast': 12,
                'macd_slow': 26,
                'macd_signal': 9,
                'atr_period': 21,
                'risk_reward': 2.5
            }
        }
    }

    @staticmethod
    def get_presets():
        """獲取所有預設組合"""
        return PresetManager.PRESETS

    @staticmethod
    def get_preset(preset_name):
        """獲取特定預設組合"""
        return PresetManager.PRESETS.get(preset_name)


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
    def compute_ema_series(prices, period):
        """✨ V3.2: 計算完整 EMA 時間序列"""
        if len(prices) < period:
            return [None] * len(prices)

        result = [None] * (period - 1)
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        result.append(round(ema, 2))

        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
            result.append(round(ema, 2))

        return result

    @staticmethod
    def compute_bb_series(prices, period=20, std_dev=2):
        """✨ V3.2: 計算完整布林通道時間序列"""
        upper = []
        lower = []

        for i in range(len(prices)):
            if i < period - 1:
                upper.append(None)
                lower.append(None)
                continue

            window = prices[i - period + 1:i + 1]
            sma = sum(window) / period
            variance = sum((p - sma) ** 2 for p in window) / period
            std = math.sqrt(variance)
            upper.append(round(sma + std_dev * std, 2))
            lower.append(round(sma - std_dev * std, 2))

        return upper, lower

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
            # 根據當前時間框架，選擇更大的時間框架
            timeframe_map = {
                '1m': '5m',
                '3m': '15m',
                '5m': '15m',
                '15m': '1h'
            }

            higher_tf = timeframe_map.get(current_interval, '15m')

            # 獲取更大時間框架數據（使用帶重試的請求）
            url = f"{BINANCE_API}/klines?symbol={symbol}&interval={higher_tf}&limit=50"
            data = fetch_with_retry(url)

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
        p = PREFIX
        if self.path in ('/', '/index.html', p + '/', p + '/index.html'):
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            html = HTML_PAGE.replace(
                '<head>',
                f'<head><script>window.APP_PREFIX = "{PREFIX}";</script>',
                1
            )
            self.wfile.write(html.encode('utf-8'))
        elif self.path.startswith(p + '/api/analyze'):
            self.handle_api_analyze()
        elif self.path.startswith(p + '/api/snapshots/export'):
            self.handle_export_snapshots()
        elif self.path.startswith(p + '/api/snapshots/search'):
            self.handle_search_snapshots()
        elif self.path.startswith(p + '/api/snapshots'):
            self.handle_api_snapshots()
        elif self.path.startswith(p + '/api/symbols'):
            self.handle_api_symbols()
        elif self.path.startswith(p + '/api/alerts'):
            self.handle_api_alerts()
        elif self.path.startswith(p + '/api/presets'):
            self.handle_api_presets()
        else:
            self.send_error(404)

    def do_POST(self):
        p = PREFIX
        if self.path.startswith(p + '/api/snapshot/save'):
            self.handle_save_snapshot()
        elif self.path.startswith(p + '/api/symbol/add'):
            self.handle_add_symbol()
        elif self.path.startswith(p + '/api/alert/add'):
            self.handle_add_alert()
        elif self.path.startswith(p + '/api/alert/toggle'):
            self.handle_toggle_alert()
        else:
            self.send_error(404)

    def do_DELETE(self):
        p = PREFIX
        if self.path.startswith(p + '/api/snapshot/'):
            self.handle_delete_snapshot()
        elif self.path.startswith(p + '/api/symbol/'):
            self.handle_delete_symbol()
        elif self.path.startswith(p + '/api/alert/'):
            self.handle_delete_alert()
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

            # 獲取 K 線數據（使用帶重試的請求）
            url = f"{BINANCE_API}/klines?symbol={symbol}&interval={interval}&limit=100"
            data = fetch_with_retry(url)

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

            # 檢查警報
            triggered_alerts = AlertManager.check_alerts(
                symbol,
                current_price,
                signals.get('quality_score', 0),
                signals.get('action', '')
            )

            # ✨ V3.2: 生成 K 線數據供前端圖表使用
            closes = [float(k[4]) for k in data]
            klines = []
            for k in data:
                klines.append({
                    'time': int(k[0]) // 1000,  # 毫秒轉秒
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5])
                })

            # ✨ V3.2: 計算 overlay 序列
            ema_fast_series = ScalpingAnalyzerPro.compute_ema_series(closes, ema_fast)
            ema_slow_series = ScalpingAnalyzerPro.compute_ema_series(closes, ema_slow)
            bb_upper_series, bb_lower_series = ScalpingAnalyzerPro.compute_bb_series(closes, 20, 2)

            def build_time_series(values, kline_data):
                """過濾 None 值，生成 {time, value} 陣列"""
                series = []
                for i, v in enumerate(values):
                    if v is not None:
                        series.append({'time': int(kline_data[i][0]) // 1000, 'value': v})
                return series

            overlays = {
                'ema_fast': build_time_series(ema_fast_series, data),
                'ema_slow': build_time_series(ema_slow_series, data),
                'bb_upper': build_time_series(bb_upper_series, data),
                'bb_lower': build_time_series(bb_lower_series, data)
            }

            result = {
                'success': True,
                'symbol': symbol,
                'price': current_price,
                'timestamp': datetime.now().isoformat(),
                'signals': signals,
                'triggered_alerts': triggered_alerts,
                'klines': klines,
                'overlays': overlays
            }

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())

        except Exception as e:
            error_info = classify_error(e)
            error_result = {
                'success': False,
                'error': error_info['error'],
                'error_type': error_info['error_type'],
                'icon': error_info['icon']
            }
            status_code = 400 if error_info['error_type'] == 'invalid_symbol' else 500
            self.send_response(status_code)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(error_result, ensure_ascii=False).encode('utf-8'))

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

    def handle_export_snapshots(self):
        """匯出快照為 CSV"""
        try:
            result = SnapshotManager.export_to_csv()

            if result['success']:
                self.send_response(200)
                self.send_header('Content-type', 'text/csv; charset=utf-8')
                self.send_header('Content-Disposition', 'attachment; filename="snapshots.csv"')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(result['csv'].encode('utf-8-sig'))  # BOM for Excel
            else:
                self.send_error(404, result.get('error', 'Export failed'))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_search_snapshots(self):
        """搜尋快照"""
        try:
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)

            symbol = params.get('symbol', [None])[0]
            action = params.get('action', [None])[0]
            min_quality = float(params.get('min_quality', [0])[0]) if params.get('min_quality') else None
            start_date = params.get('start_date', [None])[0]
            end_date = params.get('end_date', [None])[0]

            snapshots = SnapshotManager.search_snapshots(symbol, action, min_quality, start_date, end_date)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'snapshots': snapshots}, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_api_alerts(self):
        """獲取警報列表"""
        try:
            alerts = AlertManager.get_alerts()

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'alerts': alerts}, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_add_alert(self):
        """新增警報"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            result = AlertManager.add_alert(
                data['type'],
                data.get('symbol', ''),
                data['condition'],
                data['value'],
                data.get('enabled', True)
            )

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_toggle_alert(self):
        """切換警報狀態"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            result = AlertManager.toggle_alert(data['alert_id'], data['enabled'])

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_delete_alert(self):
        """刪除警報"""
        try:
            alert_id = int(self.path.split('/')[-1])
            result = AlertManager.delete_alert(alert_id)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_api_presets(self):
        """獲取參數預設組合"""
        try:
            presets = PresetManager.get_presets()

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'presets': presets}, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))


HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>剝頭皮交易分析器 Pro V3 | Scalping Analyzer Pro</title>
    <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;1,400&family=Nunito:wght@400;600;700&display=swap" rel="stylesheet">
    <style>

        :root {
            --color-primary: #635A54; /* Warm Mocha */
            --color-accent: #9FAFA1; /* Dusty Sage */
            --color-bg: #F7F5F0; /* Oatmeal */
            --color-card: #FBFBF9; /* Linen */
            --color-text-main: #635A54;
            --color-text-muted: #8c857e;
            --color-border: #e8e6e1;
            
            --color-buy: #82a88a;
            --color-sell: #c98276;
            --color-warning: #d4a373;
            --color-wait: #a3a19b;
            
            --font-headings: 'Lora', serif;
            --font-body: 'Nunito', -apple-system, sans-serif;
            
            --shadow-sm: 0 2px 8px rgba(99, 90, 84, 0.04);
            --shadow-md: 0 8px 24px rgba(99, 90, 84, 0.08);
            --radius-md: 12px;
            --radius-lg: 20px;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: var(--font-body);
            background: var(--color-bg);
            color: var(--color-text-main);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        .header {
            background: var(--color-card);
            border-radius: 15px;
            padding: 15px 20px;
            margin-bottom: 15px;
            box-shadow: var(--shadow-sm);
        }

        h1 {
            color: var(--color-text-main);
            font-size: 24px;
            margin-bottom: 3px;
        
            font-family: var(--font-headings);}

        .version-badge {
            display: inline-block;
            background: var(--color-buy);
            color: white;
            padding: 3px 10px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 600;
            margin-left: 8px;
        }

        .subtitle {
            color: var(--color-text-muted);
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
            background: var(--color-bg);
            color: var(--color-accent);
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 10px;
            font-weight: 600;
        }

        .main-grid {
            display: grid;
            grid-template-columns: 350px 1fr;
            gap: 20px;
            transition: grid-template-columns 0.4s ease-in-out, gap 0.4s ease-in-out;
        }

        .main-grid.sidebar-collapsed {
            grid-template-columns: 0px 1fr;
            gap: 0px;
        }

        .sidebar {
            overflow: hidden;
            transition: opacity 0.4s ease, padding 0.4s ease, border 0.4s ease;
        }

        .main-grid.sidebar-collapsed .sidebar {
            opacity: 0;
            padding-left: 0;
            padding-right: 0;
            border: none;
            pointer-events: none;
        }
        
        .sidebar-toggle-btn {
            background: var(--color-card);
            border: 1px solid var(--color-border);
            border-radius: 8px;
            color: var(--color-text-main);
            padding: 8px 15px;
            cursor: pointer;
            margin-bottom: 20px;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-weight: 600;
            font-size: 13px;
            width: auto;
            box-shadow: var(--shadow-sm);
        }
        .sidebar-toggle-btn:hover {
            opacity: 0.8;
            background: rgba(255,255,255,0.05);
            transform: translateY(0);
        }

        .panel {
            background: var(--color-card);
            border-radius: 20px;
            padding: 25px;
            box-shadow: var(--shadow-md);
        }

        .panel-title {
            font-family: var(--font-headings);
            font-size: 18px;
            font-weight: 600;
            color: var(--color-text-main);
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--color-border);
        }

        .form-group {
            margin-bottom: 15px;
        }

        label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            color: var(--color-text-main);
            margin-bottom: 5px;
        }

        input, select {
            width: 100%;
            padding: 10px;
            border: 2px solid var(--color-border);
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }

        input:focus, select:focus {
            outline: none;
            border-color: var(--color-accent);
        }

        button {
            width: 100%;
            padding: 12px;
            background: var(--color-accent);
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
            color: var(--color-text-muted);
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
            background: var(--color-accent);
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
            background: var(--color-bg);
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
            color: var(--color-text-main);
        }

        .signal-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .signal-badge.buy {
            background: var(--color-buy);
            color: white;
        }

        .signal-badge.sell {
            background: var(--color-sell);
            color: white;
        }

        .signal-badge.bullish {
            background: var(--color-buy);
            color: white;
        }

        .signal-badge.bearish {
            background: var(--color-sell);
            color: white;
        }

        .signal-badge.neutral {
            background: var(--color-wait);
            color: white;
        }

        .signal-badge.uptrend {
            background: var(--color-buy);
            color: white;
        }

        .signal-badge.downtrend {
            background: var(--color-sell);
            color: white;
        }

        .signal-badge.strong {
            background: var(--color-buy);
            color: white;
        }

        .signal-badge.normal {
            background: var(--color-accent);
            color: white;
        }

        .signal-badge.weak {
            background: var(--color-warning);
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
            color: var(--color-text-muted);
            margin-bottom: 5px;
        }

        .detail-value {
            font-size: 18px;
            font-weight: 600;
            color: var(--color-text-main);
        }

        .action-card {
            background: var(--color-buy);
            color: white;
            padding: 30px;
            border-radius: 12px;
            text-align: center;
            margin-top: 20px;
        }

        .action-card.sell {
            background: var(--color-sell);
        }

        .action-card.wait {
            background: var(--color-wait);
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
            background: var(--color-card);
            border-radius: 4px;
            transition: width 0.5s;
        }

        .sl-tp-card {
            background: var(--color-bg);
            border: 2px solid var(--color-warning);
            border-radius: 12px;
            padding: 20px;
            margin-top: 20px;
        }

        .sl-tp-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--color-warning);
            margin-bottom: 15px;
            text-align: center;
        }

        .sl-tp-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }

        .sl-tp-item {
            background: var(--color-card);
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }

        .sl-tp-label {
            font-size: 12px;
            color: var(--color-text-muted);
            margin-bottom: 8px;
        }

        .sl-tp-value {
            font-size: 24px;
            font-weight: bold;
            color: var(--color-text-main);
        }

        .sl-tp-value.stop-loss {
            color: var(--color-sell);
        }

        .sl-tp-value.take-profit {
            color: var(--color-buy);
        }

        .rr-ratio {
            background: var(--color-warning);
            color: white;
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            margin-top: 15px;
            font-weight: 600;
        }

        .timestamp {
            text-align: center;
            color: var(--color-text-muted);
            font-size: 12px;
            margin-top: 20px;
        }

        .new-feature-badge {
            background: var(--color-buy);
            color: white;
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 8px;
        }

        /* ✨ V3.2: 進度步驟指示器 */
        .progress-steps {
            display: flex;
            justify-content: center;
            gap: 8px;
            margin-top: 15px;
        }
        .progress-step {
            display: flex;
            align-items: center;
            gap: 5px;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            background: rgba(255,255,255,0.1);
            color: var(--color-text-muted);
            transition: all 0.3s ease;
        }
        .progress-step.active {
            background: rgba(159, 175, 161, 0.2);
            color: var(--color-accent);
            font-weight: 600;
        }
        .progress-step.done {
            background: rgba(130, 168, 138, 0.2);
            color: var(--color-buy);
        }
        .progress-step .step-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #666;
            transition: all 0.3s ease;
        }
        .progress-step.active .step-dot {
            background: #667eea;
            animation: pulse-dot 1s infinite;
        }
        .progress-step.done .step-dot {
            background: var(--color-buy);
        }
        @keyframes pulse-dot {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.5); opacity: 0.7; }
        }

        /* ✨ V3.2: Toast 通知 */
        .toast-container {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 99999;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .toast {
            padding: 14px 20px;
            border-radius: 12px;
            color: white;
            font-size: 14px;
            font-weight: 500;
            box-shadow: 0 8px 30px rgba(0,0,0,0.3);
            animation: toast-in 0.3s ease forwards;
            display: flex;
            align-items: center;
            gap: 10px;
            max-width: 360px;
        }
        .toast.success { background: linear-gradient(135deg, #10b981, #059669); }
        .toast.error { background: linear-gradient(135deg, #ef4444, #dc2626); }
        .toast.warning { background: linear-gradient(135deg, #f59e0b, #d97706); }
        .toast.info { background: linear-gradient(135deg, #3b82f6, #2563eb); }
        .toast.removing {
            animation: toast-out 0.3s ease forwards;
        }
        @keyframes toast-in {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes toast-out {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }

        /* ✨ V3.2: 改善的錯誤顯示 */
        .error-display {
            text-align: center;
            padding: 30px;
        }
        .error-display .error-icon {
            font-size: 48px;
            margin-bottom: 15px;
        }
        .error-display .error-message {
            color: var(--color-sell);
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 8px;
        }
        .error-display .error-hint {
            color: var(--color-text-muted);
            font-size: 13px;
            margin-bottom: 20px;
        }
        .error-display .retry-btn {
            padding: 10px 30px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 14px;
        }
        .error-display .retry-btn:hover {
            opacity: 0.9;
        }

        /* ✨ V3.2: 圖表容器 */
        #chart-container {
            background: #1a1a2e;
            border-radius: 16px;
            padding: 15px;
            margin-bottom: 20px;
            display: none;
        }
        #chart-container .chart-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            padding: 0 5px;
        }
        #chart-container .chart-title {
            color: #e0e0e0;
            font-size: 14px;
            font-weight: 600;
        }
        #chart-container .chart-legend {
            display: flex;
            gap: 12px;
            font-size: 11px;
        }
        #chart-container .chart-legend span {
            display: flex;
            align-items: center;
            gap: 4px;
            color: var(--color-text-muted);
        }
        #chart-container .chart-legend .legend-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }
        #candlestick-chart {
            width: 100%;
            height: 400px;
        }
        #volume-chart {
            width: 100%;
            height: 100px;
            margin-top: 5px;
        }
        .chart-unavailable {
            text-align: center;
            padding: 30px;
            color: var(--color-text-muted);
            font-size: 14px;
        }

        @media (max-width: 768px) {
            .main-grid {
                grid-template-columns: 1fr;
            }
            .sl-tp-grid {
                grid-template-columns: 1fr;
            }
            #candlestick-chart {
                height: 300px;
            }
            #volume-chart {
                height: 80px;
            }
            .progress-steps {
                flex-wrap: wrap;
            }
            .chart-legend {
                flex-wrap: wrap;
            }
        }
        
        /* UI 區塊折疊樣式 */
        .collapsible-header {
            cursor: pointer;
            user-select: none;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .collapsible-header:hover {
            opacity: 0.8;
        }
        .toggle-icon {
            font-size: 12px;
            transition: transform 0.3s ease;
            color: var(--color-text-muted);
        }
        .toggle-icon.collapsed {
            transform: rotate(-90deg);
        }
        .collapsible-content {
            transition: max-height 0.4s ease-in-out, opacity 0.3s ease-in-out, padding 0.3s ease-in-out, margin 0.3s ease-in-out;
            max-height: 4000px;
            overflow: hidden;
            opacity: 1;
        }
        .collapsible-content.collapsed {
            max-height: 0;
            opacity: 0;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            border: none;
        }
    </style>
    <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 剝頭皮交易分析器 Pro<span class="version-badge">V3.2</span></h1>
            <p class="subtitle">Professional Scalping Trading System - 專業級實時交易信號分析</p>
            <div class="feature-tags">
                <span class="feature-tag">📈 即時圖表</span>
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

        <div style="text-align: left;">
            <button class="sidebar-toggle-btn" onclick="toggleMainSidebar()">
                <span id="sidebar-toggle-icon">◀</span> 交易設定
            </button>
        </div>

        <div class="main-grid" id="main-grid">
            <div class="panel sidebar">
                <div class="panel-title collapsible-header" onclick="toggleCollapse('settings-content', this)">
                    <span>⚙️ 交易設定</span>
                    <span class="toggle-icon">▼</span>
                </div>
                <div id="settings-content" class="collapsible-content">

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
                    <button onclick="showAddSymbolDialog()" style="margin-top: 10px; width: 100%; padding: 8px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); box-shadow: none; font-size: 12px; font-weight: normal;">
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

                <div class="panel-title" style="margin-top: 20px;">⚡ 快速預設</div>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin-bottom: 15px;">
                    <button onclick="loadPreset('scalping')" style="padding: 8px 5px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); font-size: 11px; white-space: nowrap; font-weight: normal; box-shadow: none;">
                        🔥 超短線
                    </button>
                    <button onclick="loadPreset('daytrading')" style="padding: 8px 5px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); font-size: 11px; font-weight: normal; box-shadow: none;">
                        📊 短線
                    </button>
                    <button onclick="loadPreset('conservative')" style="padding: 8px 5px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); font-size: 11px; font-weight: normal; box-shadow: none;">
                        🛡️ 穩健
                    </button>
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

                <div class="panel-title" style="margin-top: 25px;">🔧 進階功能</div>

                <button onclick="showSnapshotManager()" style="margin-top: 10px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); box-shadow: none; font-weight: normal;">
                    📸 快照管理
                </button>

                <button onclick="showAlertManager()" style="margin-top: 10px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); box-shadow: none; font-weight: normal;">
                    🔔 警報設定
                </button>
                </div>
            </div>

            <div class="panel result-panel">
                <div class="panel-title">📊 分析結果</div>
                <div id="chart-container">
                    <div class="chart-header collapsible-header" onclick="toggleCollapse('chart-content', this)">
                        <div class="chart-title">K 線圖表</div>
                        <div class="chart-legend" style="pointer-events: none; flex-grow: 1; justify-content: flex-end; margin-right: 15px;">
                            <span><span class="legend-dot" style="background:#f0b90b"></span>EMA Fast</span>
                            <span><span class="legend-dot" style="background:#2962ff"></span>EMA Slow</span>
                            <span><span class="legend-dot" style="background:#ab47bc"></span>布林通道</span>
                            <span><span class="legend-dot" style="background:#ef4444"></span>止損</span>
                            <span><span class="legend-dot" style="background:#10b981"></span>止盈</span>
                        </div>
                        <span class="toggle-icon">▼</span>
                    </div>
                    <div id="chart-content" class="collapsible-content">
                        <div id="candlestick-chart"></div>
                        <div id="volume-chart"></div>
                    </div>
                </div>
                <div id="results">
                    <div class="loading">
                        <div style="font-size: 48px; margin-bottom: 20px;">📈</div>
                        <p>請點擊「分析入場信號」開始分析</p>
                        <p style="margin-top: 10px; color: #10b981; font-weight: 600;">✨ V3.2：即時圖表 + 智能錯誤處理 + 進度指示器</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const APP_PREFIX = window.APP_PREFIX || '';
        let autoRefreshInterval = null;
        let candlestickChart = null;
        let volumeChart = null;
        let lastVisibleRange = null;

        // UI Collapse Logic
        function toggleMainSidebar() {
            const grid = document.getElementById('main-grid');
            const icon = document.getElementById('sidebar-toggle-icon');
            if (grid.classList.contains('sidebar-collapsed')) {
                grid.classList.remove('sidebar-collapsed');
                if (icon) icon.textContent = '◀';
                localStorage.setItem('sidebar_state', 'open');
            } else {
                grid.classList.add('sidebar-collapsed');
                if (icon) icon.textContent = '▶';
                localStorage.setItem('sidebar_state', 'closed');
            }
            // trigger resize for charts
            if (candlestickChart && volumeChart) {
                setTimeout(() => {
                    window.dispatchEvent(new Event('resize'));
                }, 400);
            }
        }

        function toggleCollapse(contentId, headerEl) {
            const content = document.getElementById(contentId);
            const icon = headerEl.querySelector('.toggle-icon');
            
            if (content.classList.contains('collapsed')) {
                content.classList.remove('collapsed');
                if (icon) icon.classList.remove('collapsed');
                localStorage.setItem('collapse_' + contentId, 'open');
                
                // 強制重新調整圖表大小 (避免隱藏時大小為 0)
                if (contentId === 'chart-content' && candlestickChart && volumeChart) {
                    setTimeout(() => {
                        window.dispatchEvent(new Event('resize'));
                    }, 400);
                }
            } else {
                content.classList.add('collapsed');
                if (icon) icon.classList.add('collapsed');
                localStorage.setItem('collapse_' + contentId, 'closed');
            }
        }

        function restoreCollapses() {
            // Sidebar state
            const sidebarState = localStorage.getItem('sidebar_state');
            if (sidebarState === 'closed') {
                const grid = document.getElementById('main-grid');
                if (grid) grid.classList.add('sidebar-collapsed');
                const icon = document.getElementById('sidebar-toggle-icon');
                if (icon) icon.textContent = '▶';
            }

            // Accordion states
            const list = ['settings-content', 'chart-content', 'advanced-analysis-content'];
            list.forEach(id => {
                const state = localStorage.getItem('collapse_' + id);
                if (state === 'closed') {
                    const content = document.getElementById(id);
                    if (content) {
                        content.classList.add('collapsed');
                        // 尋找對應的 header 和 icon
                        // 假設 header 的結構是在前面
                        const header = document.querySelector(`[onclick*="'${id}'"]`);
                        if (header) {
                            const icon = header.querySelector('.toggle-icon');
                            if (icon) icon.classList.add('collapsed');
                        }
                    }
                }
            });
        }
        
        // 頁面加載時恢復靜態狀態
        document.addEventListener('DOMContentLoaded', restoreCollapses);

        // ✨ V3.2: Toast 通知系統
        function showToast(message, type = 'info', duration = 3000) {
            let container = document.querySelector('.toast-container');
            if (!container) {
                container = document.createElement('div');
                container.className = 'toast-container';
                document.body.appendChild(container);
            }

            const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
            const toast = document.createElement('div');
            toast.className = 'toast ' + type;
            toast.innerHTML = '<span>' + (icons[type] || '') + '</span><span>' + message + '</span>';
            container.appendChild(toast);

            setTimeout(() => {
                toast.classList.add('removing');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }

        // ✨ V3.2: 進度步驟更新
        function updateProgressStep(step) {
            const steps = document.querySelectorAll('.progress-step');
            steps.forEach((el, i) => {
                el.classList.remove('active', 'done');
                if (i < step) el.classList.add('done');
                else if (i === step) el.classList.add('active');
            });
        }

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

            // 保存圖表時間軸範圍（自動刷新時用）
            if (candlestickChart) {
                try { lastVisibleRange = candlestickChart.timeScale().getVisibleRange(); } catch(e) {}
            }

            document.getElementById('results').innerHTML = `
                <div class="loading">
                    <div class="spinner"></div>
                    <p>分析中...</p>
                    <div class="progress-steps">
                        <div class="progress-step active"><span class="step-dot"></span>獲取數據</div>
                        <div class="progress-step"><span class="step-dot"></span>計算指標</div>
                        <div class="progress-step"><span class="step-dot"></span>生成建議</div>
                    </div>
                </div>
            `;

            // 模擬進度步驟
            setTimeout(() => updateProgressStep(1), 800);
            setTimeout(() => updateProgressStep(2), 1500);

            try {
                const url = `${APP_PREFIX}/api/analyze?symbol=${symbol}&interval=${interval}&rsi_period=${rsi_period}&rsi_overbought=${rsi_overbought}&rsi_oversold=${rsi_oversold}&ema_fast=${ema_fast}&ema_slow=${ema_slow}&macd_fast=${macd_fast}&macd_slow=${macd_slow}&macd_signal=${macd_signal}`;

                const response = await fetch(url);
                const data = await response.json();

                if (data.success) {
                    displayResults(data);
                } else {
                    showError(data.error, data.error_type);
                }
            } catch (error) {
                showError('網路連線失敗，請檢查網路狀態', 'network');
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
                sendNotification(`🚨 ${data.symbol} 高品質信號！`, `${signals.action} | 品質: ${signals.quality_score}/5 ⭐`, `quality_${data.symbol}`);
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
                    <button onclick="saveSnapshot()" style="width: auto; padding: 12px 30px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); margin-right: 10px; border-radius: 8px; font-weight: 600; cursor: pointer; box-shadow: none;">
                        📸 保存當前策略快照
                    </button>
                    <button onclick="showSnapshots()" style="width: auto; padding: 12px 30px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); border-radius: 8px; font-weight: 600; cursor: pointer; box-shadow: none;">
                        📋 查看歷史快照
                    </button>
                </div>

                <!-- 核心分析指標 -->
                <div class="panel-title collapsible-header" onclick="toggleCollapse('advanced-analysis-content', this)" style="margin-top: 25px; margin-bottom: 15px;">
                    <span>🔬 細部分析結果（多時間框架及以下）</span>
                    <span class="toggle-icon">▼</span>
                </div>
                <div id="advanced-analysis-content" class="collapsible-content">
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

                </div> <!-- 結束 advanced-analysis-content -->

                <div class="timestamp">
                    最後更新: ${new Date(data.timestamp).toLocaleString('zh-TW')}
                </div>
            `;

            document.getElementById('results').innerHTML = html;

            // 恢復折疊狀態
            restoreCollapses();

            // ✨ V3.2: 渲染圖表
            renderChart(data);

            // 檢查並顯示觸發的警報
            if (data.triggered_alerts && data.triggered_alerts.length > 0) {
                data.triggered_alerts.forEach(a => {
                    sendNotification('🔔 警報觸發', a.message, `alert_${a.id}`);
                });
            }
        }

        // ✨ V3.2: 圖表渲染
        function renderChart(data) {
            if (typeof LightweightCharts === 'undefined') {
                document.getElementById('chart-container').innerHTML = '<div class="chart-unavailable">圖表功能不可用（CDN 載入失敗）</div>';
                document.getElementById('chart-container').style.display = 'block';
                return;
            }

            if (!data.klines || data.klines.length === 0) return;

            const container = document.getElementById('chart-container');
            container.style.display = 'block';

            const candleEl = document.getElementById('candlestick-chart');
            const volumeEl = document.getElementById('volume-chart');
            candleEl.innerHTML = '';
            volumeEl.innerHTML = '';

            // 銷毀舊圖表
            if (candlestickChart) { candlestickChart.remove(); candlestickChart = null; }
            if (volumeChart) { volumeChart.remove(); volumeChart = null; }

            const chartOptions = {
                layout: { background: { color: '#1a1a2e' }, textColor: '#d1d4dc' },
                grid: { vertLines: { color: 'rgba(42, 46, 57, 0.5)' }, horzLines: { color: 'rgba(42, 46, 57, 0.5)' } },
                crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                rightPriceScale: { borderColor: 'rgba(197, 203, 206, 0.3)' },
                timeScale: { borderColor: 'rgba(197, 203, 206, 0.3)', timeVisible: true, secondsVisible: false }
            };

            // K 線圖
            candlestickChart = LightweightCharts.createChart(candleEl, { ...chartOptions, height: 400 });
            const candleSeries = candlestickChart.addCandlestickSeries({
                upColor: '#26a69a', downColor: '#ef5350',
                borderUpColor: '#26a69a', borderDownColor: '#ef5350',
                wickUpColor: '#26a69a', wickDownColor: '#ef5350'
            });
            candleSeries.setData(data.klines);

            // EMA 疊加
            if (data.overlays) {
                if (data.overlays.ema_fast && data.overlays.ema_fast.length > 0) {
                    const emaFastLine = candlestickChart.addLineSeries({ color: '#f0b90b', lineWidth: 1, title: 'EMA Fast' });
                    emaFastLine.setData(data.overlays.ema_fast);
                }
                if (data.overlays.ema_slow && data.overlays.ema_slow.length > 0) {
                    const emaSlowLine = candlestickChart.addLineSeries({ color: '#2962ff', lineWidth: 1, title: 'EMA Slow' });
                    emaSlowLine.setData(data.overlays.ema_slow);
                }
                // 布林通道
                if (data.overlays.bb_upper && data.overlays.bb_upper.length > 0) {
                    const bbUpper = candlestickChart.addLineSeries({ color: '#ab47bc', lineWidth: 1, lineStyle: 2, title: 'BB Upper' });
                    bbUpper.setData(data.overlays.bb_upper);
                }
                if (data.overlays.bb_lower && data.overlays.bb_lower.length > 0) {
                    const bbLower = candlestickChart.addLineSeries({ color: '#ab47bc', lineWidth: 1, lineStyle: 2, title: 'BB Lower' });
                    bbLower.setData(data.overlays.bb_lower);
                }
            }

            // 止損止盈水平線
            const sltp = data.signals.stop_loss_take_profit;
            if (sltp) {
                const markers = [];
                candleSeries.createPriceLine({ price: sltp.stop_loss, color: '#ef4444', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'SL' });
                candleSeries.createPriceLine({ price: sltp.take_profit_1, color: '#10b981', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'TP1' });
                candleSeries.createPriceLine({ price: sltp.take_profit_2, color: '#10b981', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'TP2' });
            }

            // 成交量圖
            volumeChart = LightweightCharts.createChart(volumeEl, {
                ...chartOptions,
                height: 100,
                rightPriceScale: { ...chartOptions.rightPriceScale, scaleMargins: { top: 0.1, bottom: 0 } },
                timeScale: { ...chartOptions.timeScale, visible: false }
            });

            const volumeSeries = volumeChart.addHistogramSeries({
                priceFormat: { type: 'volume' },
                priceScaleId: ''
            });
            volumeSeries.setData(data.klines.map(k => ({
                time: k.time,
                value: k.volume,
                color: k.close >= k.open ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)'
            })));

            // 雙圖表時間軸同步
            let isSyncing = false;
            candlestickChart.timeScale().subscribeVisibleTimeRangeChange(() => {
                if (isSyncing) return;
                isSyncing = true;
                const range = candlestickChart.timeScale().getVisibleRange();
                if (range) volumeChart.timeScale().setVisibleRange(range);
                isSyncing = false;
            });
            volumeChart.timeScale().subscribeVisibleTimeRangeChange(() => {
                if (isSyncing) return;
                isSyncing = true;
                const range = volumeChart.timeScale().getVisibleRange();
                if (range) candlestickChart.timeScale().setVisibleRange(range);
                isSyncing = false;
            });

            // 恢復先前的時間軸範圍（自動刷新時）
            if (lastVisibleRange) {
                try {
                    candlestickChart.timeScale().setVisibleRange(lastVisibleRange);
                } catch(e) {}
                lastVisibleRange = null;
            } else {
                candlestickChart.timeScale().fitContent();
                volumeChart.timeScale().fitContent();
            }

            // 響應式
            const resizeObserver = new ResizeObserver(() => {
                if (candlestickChart) candlestickChart.applyOptions({ width: candleEl.clientWidth });
                if (volumeChart) volumeChart.applyOptions({ width: volumeEl.clientWidth });
            });
            resizeObserver.observe(candleEl);
        }

        function showError(message, errorType) {
            const errorConfig = {
                'network':        { icon: '🌐', hint: '請確認網路連線是否正常' },
                'timeout':        { icon: '⏱️', hint: '伺服器回應時間過長，請稍後再試' },
                'invalid_symbol': { icon: '🔍', hint: '請確認交易對名稱是否正確（如 BTCUSDT）' },
                'rate_limit':     { icon: '🚦', hint: '請等待幾秒後再試' },
                'server_error':   { icon: '🖥️', hint: 'Binance 伺服器暫時不可用' },
                'unknown':        { icon: '⚠️', hint: '如持續發生，請檢查網路或稍後重試' }
            };
            const config = errorConfig[errorType] || errorConfig['unknown'];

            document.getElementById('chart-container').style.display = 'none';
            document.getElementById('results').innerHTML = `
                <div class="error-display">
                    <div class="error-icon">${config.icon}</div>
                    <div class="error-message">${message}</div>
                    <div class="error-hint">${config.hint}</div>
                    <button class="retry-btn" onclick="analyze()">🔄 重新嘗試</button>
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

        // 🔔 瀏覽器通知冷卻機制
        const notificationCooldowns = {};
        const NOTIFICATION_COOLDOWN_MS = 60 * 1000; // 1 分鐘的冷卻時間

        // 🔔 瀏覽器通知功能
        function sendNotification(title, body, customKey = null) {
            const key = customKey || (title + "|" + body);
            const now = Date.now();

            // 檢查冷卻時間
            if (notificationCooldowns[key] && (now - notificationCooldowns[key] < NOTIFICATION_COOLDOWN_MS)) {
                console.log(`[通知冷卻中] 略過發送: ${title}, key: ${key}`);
                return;
            }

            // 更新最後發送時間
            notificationCooldowns[key] = now;

            // 請求通知權限
            if (!("Notification" in window)) {
                console.log("此瀏覽器不支援通知");
                return;
            }

            if (Notification.permission === "granted") {
                // 已授權，發送通知
                new Notification(title, {
                    body: body,
                    vibrate: [200, 100, 200],
                    requireInteraction: true
                });
            } else if (Notification.permission !== "denied") {
                // 請求權限
                Notification.requestPermission().then(function (permission) {
                    if (permission === "granted") {
                        new Notification(title, {
                            body: body
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
                showToast('請先進行分析！', 'warning');
                return;
            }

            try {
                const response = await fetch(APP_PREFIX + '/api/snapshot/save', {
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
                    showToast('策略快照已保存！ID: ' + result.snapshot_id, 'success');
                } else {
                    showToast('保存失敗: ' + result.error, 'error');
                }
            } catch (error) {
                showToast('保存失敗: ' + error.message, 'error');
            }
        }

        // 📋 顯示快照列表
        async function showSnapshots() {
            try {
                const response = await fetch(APP_PREFIX + '/api/snapshots?limit=20');
                const result = await response.json();

                if (!result.success || result.snapshots.length === 0) {
                    showToast('暫無快照記錄', 'info');
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
                        <button onclick="this.closest('div').parentElement.remove()" style="width: 100%; margin-top: 15px; background: var(--color-accent);">關閉</button>
                    </div>
                `;
                document.body.appendChild(modal);
            } catch (error) {
                showToast('載入失敗: ' + error.message, 'error');
            }
        }

        // ➕ 自定義商品管理
        async function loadCustomSymbols() {
            try {
                const response = await fetch(APP_PREFIX + '/api/symbols');
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

        // ⚡ 載入參數預設組合
        async function loadPreset(presetName) {
            try {
                const response = await fetch(APP_PREFIX + '/api/presets');
                const result = await response.json();

                if (result.success && result.presets[presetName]) {
                    const preset = result.presets[presetName];
                    const params = preset.params;

                    // 設置參數
                    document.getElementById('interval').value = params.interval;
                    document.getElementById('rsi_period').value = params.rsi_period;
                    document.getElementById('rsi_overbought').value = params.rsi_overbought;
                    document.getElementById('rsi_oversold').value = params.rsi_oversold;
                    document.getElementById('ema_fast').value = params.ema_fast;
                    document.getElementById('ema_slow').value = params.ema_slow;
                    document.getElementById('macd_fast').value = params.macd_fast;
                    document.getElementById('macd_slow').value = params.macd_slow;
                    document.getElementById('macd_signal').value = params.macd_signal;

                    showToast('已載入「' + preset.name + '」預設', 'success');
                } else {
                    showToast('載入預設失敗', 'error');
                }
            } catch (error) {
                showToast('載入預設失敗: ' + error.message, 'error');
            }
        }

        // 📸 快照管理器
        function showSnapshotManager() {
            const modal = document.createElement('div');
            modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 10000; display: flex; align-items: center; justify-content: center; padding: 20px;';
            modal.innerHTML = `
                <div style="background: white; padding: 30px; border-radius: 20px; max-width: 900px; width: 100%; max-height: 90vh; overflow-y: auto;">
                    <h2 style="margin-bottom: 20px;">📸 快照管理器</h2>

                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 20px;">
                        <button onclick="exportSnapshots()" style="padding: 10px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); box-shadow: none; font-weight: normal;">
                            📥 匯出 CSV
                        </button>
                        <button onclick="showSearchDialog()" style="padding: 10px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); box-shadow: none; font-weight: normal;">
                            🔍 搜尋篩選
                        </button>
                        <button onclick="loadSnapshotsInModal()" style="padding: 10px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); box-shadow: none; font-weight: normal;">
                            🔄 重新載入
                        </button>
                    </div>

                    <div id="snapshotList" style="min-height: 200px;">
                        <p style="text-align: center; color: #666;">載入中...</p>
                    </div>

                    <button onclick="this.closest('div').parentElement.remove()" style="width: 100%; margin-top: 20px; background: var(--color-accent);">關閉</button>
                </div>
            `;
            document.body.appendChild(modal);
            loadSnapshotsInModal();
        }

        async function loadSnapshotsInModal() {
            try {
                const response = await fetch(APP_PREFIX + '/api/snapshots?limit=50');
                const result = await response.json();

                const listDiv = document.getElementById('snapshotList');
                if (!result.success || result.snapshots.length === 0) {
                    listDiv.innerHTML = '<p style="text-align: center; color: #666;">暫無快照記錄</p>';
                    return;
                }

                let html = '';
                result.snapshots.forEach(snapshot => {
                    const borderColor = snapshot.action.includes('買入') ? '#10b981' : (snapshot.action.includes('賣出') ? '#ef4444' : '#6b7280');
                    html += `
                        <div style="border: 2px solid ${borderColor}; border-radius: 10px; padding: 15px; margin-bottom: 15px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <div>
                                    <strong>${snapshot.symbol}</strong> - ${snapshot.action}
                                    <span style="margin-left: 10px;">⭐ ${snapshot.quality_score}</span>
                                </div>
                                <button onclick="deleteSnapshot(${snapshot.id})" style="padding: 5px 10px; background: var(--color-sell); font-size: 12px;">
                                    🗑️ 刪除
                                </button>
                            </div>
                            <div style="font-size: 12px; color: #666;">
                                時間: ${new Date(snapshot.timestamp).toLocaleString('zh-TW')}
                            </div>
                            <div style="font-size: 12px; margin-top: 5px;">
                                價格: $${snapshot.price} | 止損: $${snapshot.signals.stop_loss_take_profit?.stop_loss} | 止盈: $${snapshot.signals.stop_loss_take_profit?.take_profit_2}
                            </div>
                        </div>
                    `;
                });

                listDiv.innerHTML = html;
            } catch (error) {
                document.getElementById('snapshotList').innerHTML = '<p style="text-align: center; color: #ef4444;">載入失敗</p>';
            }
        }

        async function exportSnapshots() {
            try {
                window.open('/api/snapshots/export', '_blank');
                showToast('開始下載 CSV 檔案', 'success');
            } catch (error) {
                showToast('匯出失敗: ' + error.message, 'error');
            }
        }

        async function deleteSnapshot(id) {
            if (!confirm('確定要刪除此快照嗎？')) return;

            try {
                const response = await fetch(APP_PREFIX + '/api/snapshot/' + id, { method: 'DELETE' });
                const result = await response.json();

                if (result.success) {
                    showToast('快照已刪除', 'success');
                    loadSnapshotsInModal();
                } else {
                    showToast('刪除失敗', 'error');
                }
            } catch (error) {
                showToast('刪除失敗: ' + error.message, 'error');
            }
        }

        function showSearchDialog() {
            const symbol = prompt('搜尋交易對（留空=全部）:');
            const action = prompt('搜尋信號類型（買入/賣出/觀望，留空=全部）:');
            const minQuality = prompt('最低品質評分（0-5，留空=全部）:');

            searchSnapshots(symbol, action, minQuality);
        }

        async function searchSnapshots(symbol, action, minQuality) {
            try {
                let url = '/api/snapshots/search?';
                if (symbol) url += 'symbol=' + symbol + '&';
                if (action) url += 'action=' + action + '&';
                if (minQuality) url += 'min_quality=' + minQuality + '&';

                const response = await fetch(url);
                const result = await response.json();

                const listDiv = document.getElementById('snapshotList');
                if (!result.success || result.snapshots.length === 0) {
                    listDiv.innerHTML = '<p style="text-align: center; color: #666;">沒有符合條件的快照</p>';
                    return;
                }

                let html = '<p style="color: #10b981; margin-bottom: 15px;">找到 ' + result.snapshots.length + ' 筆結果</p>';
                result.snapshots.forEach(snapshot => {
                    const borderColor = snapshot.action.includes('買入') ? '#10b981' : (snapshot.action.includes('賣出') ? '#ef4444' : '#6b7280');
                    html += `
                        <div style="border: 2px solid ${borderColor}; border-radius: 10px; padding: 15px; margin-bottom: 15px;">
                            <div><strong>${snapshot.symbol}</strong> - ${snapshot.action} ⭐ ${snapshot.quality_score}</div>
                            <div style="font-size: 12px; color: #666;">${new Date(snapshot.timestamp).toLocaleString('zh-TW')}</div>
                        </div>
                    `;
                });

                listDiv.innerHTML = html;
            } catch (error) {
                showToast('搜尋失敗: ' + error.message, 'error');
            }
        }

        // 🔔 警報管理器
        function showAlertManager() {
            const modal = document.createElement('div');
            modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 10000; display: flex; align-items: center; justify-content: center; padding: 20px;';
            modal.innerHTML = `
                <div style="background: white; padding: 30px; border-radius: 20px; max-width: 700px; width: 100%; max-height: 90vh; overflow-y: auto;">
                    <h2 style="margin-bottom: 20px;">🔔 警報設定</h2>

                    <button onclick="showAddAlertDialog()" style="width: 100%; margin-bottom: 20px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); box-shadow: none; font-weight: normal;">
                        ➕ 新增警報
                    </button>

                    <div id="alertList" style="min-height: 200px;">
                        <p style="text-align: center; color: #666;">載入中...</p>
                    </div>

                    <button onclick="this.closest('div').parentElement.remove()" style="width: 100%; margin-top: 20px; background: var(--color-accent);">關閉</button>
                </div>
            `;
            document.body.appendChild(modal);
            loadAlertsInModal();
        }

        async function loadAlertsInModal() {
            try {
                const response = await fetch(APP_PREFIX + '/api/alerts');
                const result = await response.json();

                const listDiv = document.getElementById('alertList');
                if (!result.success || result.alerts.length === 0) {
                    listDiv.innerHTML = '<p style="text-align: center; color: #666;">暫無警報設定</p>';
                    return;
                }

                let html = '';
                result.alerts.forEach(alert => {
                    const typeText = alert.type === 'price' ? '💰 價格' : (alert.type === 'quality' ? '⭐ 品質' : '📊 信號');
                    const condText = alert.condition === 'above' ? '高於' : (alert.condition === 'below' ? '低於' : '等於');
                    const status = alert.enabled ? '✅ 啟用' : '❌ 停用';

                    html += `
                        <div style="border: 2px solid ${alert.enabled ? 'var(--color-buy)' : '#6b7280'}; border-radius: 10px; padding: 15px; margin-bottom: 15px;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <strong>${typeText}</strong> ${condText} ${alert.value}
                                    ${alert.symbol ? '(' + alert.symbol + ')' : '(所有商品)'}
                                </div>
                                <div style="display: flex; gap: 5px;">
                                    <button onclick="toggleAlert(${alert.id}, ${!alert.enabled})" style="padding: 5px 10px; background: ${alert.enabled ? 'var(--color-warning)' : 'var(--color-buy)'}; font-size: 12px;">
                                        ${alert.enabled ? '暫停' : '啟用'}
                                    </button>
                                    <button onclick="deleteAlert(${alert.id})" style="padding: 5px 10px; background: var(--color-sell); font-size: 12px;">
                                        刪除
                                    </button>
                                </div>
                            </div>
                            <div style="font-size: 12px; color: #666; margin-top: 5px;">
                                觸發次數: ${alert.triggered_count || 0} | ${status}
                            </div>
                        </div>
                    `;
                });

                listDiv.innerHTML = html;
            } catch (error) {
                document.getElementById('alertList').innerHTML = '<p style="text-align: center; color: #ef4444;">載入失敗</p>';
            }
        }

        function showAddAlertDialog() {
            const type = prompt('警報類型（price=價格 / quality=品質評分 / signal=信號類型）:');
            if (!type || !['price', 'quality', 'signal'].includes(type)) {
                alert('❌ 請輸入正確的警報類型');
                return;
            }

            const symbol = prompt('交易對（留空=所有商品）:');
            const condition = type === 'signal' ? 'equal' : prompt('條件（above=高於 / below=低於）:');

            if (type !== 'signal' && !['above', 'below'].includes(condition)) {
                alert('❌ 請輸入正確的條件');
                return;
            }

            const value = prompt(type === 'price' ? '價格:' : (type === 'quality' ? '品質評分(0-5):' : '信號類型（買入/賣出）:'));
            if (!value) return;

            addAlert(type, symbol || '', condition, value);
        }

        async function addAlert(type, symbol, condition, value) {
            try {
                const response = await fetch(APP_PREFIX + '/api/alert/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({type, symbol, condition, value, enabled: true})
                });

                const result = await response.json();
                if (result.success) {
                    showToast('警報已新增！', 'success');
                    loadAlertsInModal();
                } else {
                    showToast('新增失敗: ' + result.error, 'error');
                }
            } catch (error) {
                showToast('新增失敗: ' + error.message, 'error');
            }
        }

        async function toggleAlert(id, enabled) {
            try {
                const response = await fetch(APP_PREFIX + '/api/alert/toggle', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({alert_id: id, enabled})
                });

                const result = await response.json();
                if (result.success) {
                    loadAlertsInModal();
                } else {
                    showToast('更新失敗', 'error');
                }
            } catch (error) {
                showToast('更新失敗: ' + error.message, 'error');
            }
        }

        async function deleteAlert(id) {
            if (!confirm('確定要刪除此警報嗎？')) return;

            try {
                const response = await fetch(APP_PREFIX + '/api/alert/' + id, { method: 'DELETE' });
                const result = await response.json();

                if (result.success) {
                    showToast('警報已刪除', 'success');
                    loadAlertsInModal();
                } else {
                    showToast('刪除失敗', 'error');
                }
            } catch (error) {
                showToast('刪除失敗: ' + error.message, 'error');
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
                const response = await fetch(APP_PREFIX + '/api/symbol/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({symbol, name})
                });

                const result = await response.json();
                if (result.success) {
                    showToast('商品已添加！', 'success');
                    location.reload();
                } else {
                    showToast('添加失敗: ' + result.error, 'error');
                }
            } catch (error) {
                showToast('添加失敗: ' + error.message, 'error');
            }
        }
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), ScalpingHandler) as httpd:
        print(f"✅ 剝頭皮交易分析器 Pro V3.2 已啟動！")
        print(f"🌐 訪問: http://localhost:{PORT}")
        print(f"")
        print(f"✨ V3.2 新增功能:")
        print(f"  📈 即時 K 線圖表 (TradingView Lightweight Charts)")
        print(f"  🔄 智能重試機制 (指數退避)")
        print(f"  🌐 中文錯誤訊息 + 錯誤分類")
        print(f"  📊 進度指示器 + Toast 通知")
        print(f"")
        print(f"✨ V3 功能:")
        print(f"  📊 Bollinger Bands | 📉 Stochastic | 📐 Fibonacci")
        print(f"  📸 策略快照 | ➕ 自定義商品 | 🔔 智能警報")
        print(f"")
        print(f"🚀 支援交易對: BTC, ETH, BNB, SOL + 自定義")
        print(f"\n按 Ctrl+C 停止服務\n")
        httpd.serve_forever()
