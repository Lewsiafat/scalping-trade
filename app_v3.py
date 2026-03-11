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
- Bollinger Bands / Stochastic
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
VERSION = "4.0.0"
BINANCE_API = "https://api.binance.com/api/v3"
BINANCE_FAPI = "https://fapi.binance.com/fapi/v1"


def fetch_with_retry(url, ctx=None, max_retries=3, base_timeout=10, is_kline_req=False):
    """帶重試機制的 HTTP 請求（指數退避）。如果是 K 線請求且現貨失敗，則嘗試合約 API。"""
    if ctx is None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    def _do_fetch(req_url):
        last_error = None
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(req_url)
                with urllib.request.urlopen(req, context=ctx, timeout=base_timeout) as response:
                    return json.loads(response.read().decode())
            except urllib.error.HTTPError as e:
                last_error = e
                if e.code == 400:
                    raise  # 400 不重試同一 URL
                if e.code == 429:
                    time.sleep(2 ** attempt * 2)
                    continue
                if e.code >= 500:
                    time.sleep(2 ** attempt * 0.5)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, Exception) as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt * 0.5)
                    continue
        raise last_error

    try:
        return _do_fetch(url)
    except urllib.error.HTTPError as e:
        if e.code == 400 and is_kline_req and url.startswith(BINANCE_API):
            # 現貨失敗，嘗試轉換 URL 為合約
            fapi_url = url.replace(BINANCE_API, BINANCE_FAPI)
            return _do_fetch(fapi_url)
        raise


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
def validate_kline_data(data, min_count=50):
    """驗證 K 線數據品質，返回 (is_valid, cleaned_data, warnings)"""
    warnings = []

    # 數量檢查
    if not data or len(data) < min_count:
        return False, data, [f'K 線數據不足：需要至少 {min_count} 根，實際 {len(data) if data else 0} 根']

    cleaned = []
    prev_time = None

    for i, k in enumerate(data):
        ts = int(k[0])
        open_p = float(k[1])
        high = float(k[2])
        low = float(k[3])
        close = float(k[4])
        volume = float(k[5])

        # zero-volume 檢查（跳過無成交量的 K 線，但允許最後一根未收盤）
        if volume == 0 and i < len(data) - 1:
            warnings.append(f'跳過零成交量 K 線：index={i}, time={ts}')
            continue

        # 時間戳連續性檢查
        if prev_time is not None:
            gap = ts - prev_time
            if gap <= 0:
                warnings.append(f'時間戳異常（非遞增）：index={i}')
                continue

        # 異常波動檢查（單根 K 線波動超過 50%）
        if low > 0:
            volatility = (high - low) / low
            if volatility > 0.5:
                warnings.append(f'異常波動 K 線：index={i}, 波動={volatility:.1%}')
                # 仍保留，但記錄警告

        cleaned.append(k)
        prev_time = ts

    if len(cleaned) < min_count:
        return False, cleaned, warnings + [f'清理後數據不足：{len(cleaned)} 根']

    return True, cleaned, warnings


# MTF 記憶體快取：避免同一根未收盤 K 線重複請求
# key: "{symbol}_{interval}", value: {"data": [...], "last_close_time": int, "fetched_at": float}
_mtf_cache = {}

def fetch_klines_cached(symbol, interval, limit=150):
    """帶快取的 K 線請求。當前時間 < 最後一根 K 線收盤時間時使用快取。"""
    cache_key = f"{symbol}_{interval}"
    now_ms = int(time.time() * 1000)

    if cache_key in _mtf_cache:
        cached = _mtf_cache[cache_key]
        # 最後一根 K 線的收盤時間（kline[6]）
        if now_ms < cached['last_close_time']:
            return cached['data']

    url = f"{BINANCE_API}/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = fetch_with_retry(url, is_kline_req=True)

    if data:
        _mtf_cache[cache_key] = {
            'data': data,
            'last_close_time': int(data[-1][6]),  # kline[6] = close_time
            'fetched_at': time.time()
        }

    return data


# 兩階段信號狀態快取：追蹤預警和信號的過期
# key: "{symbol}_{interval}", value: {"type": "pre_alert"|"signal", "bar_index": int,
#   "alert_type": str, "alert_message": str, "proximity": float, "created_at": float}
_signal_state = {}

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
                'ema_fast': 9,
                'ema_slow': 21,
                'macd_fast': 12,
                'macd_slow': 26,
                'macd_signal': 9,
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
            symbol = symbol.strip().upper()
            
            # 準備驗證函數
            def validate_symbol(sym):
                spot_url = f"{BINANCE_API}/ticker/price?symbol={sym}"
                fapi_url = f"{BINANCE_FAPI}/ticker/price?symbol={sym}"
                
                def _check_url(u):
                    try:
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                        req = urllib.request.Request(u)
                        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
                            return True
                    except urllib.error.HTTPError as e:
                        if e.code == 400:
                            return False
                        raise
                    except Exception:
                        return False

                # 只要現貨或合約其一是有效的代碼，就視為正確
                return _check_url(spot_url) or _check_url(fapi_url)
                    
            # 驗證代碼
            is_valid = validate_symbol(symbol)
            
            # 若無效且未包含 USDT，嘗試補上 USDT
            if not is_valid and 'USDT' not in symbol:
                test_symbol = symbol + 'USDT'
                if validate_symbol(test_symbol):
                    symbol = test_symbol
                    is_valid = True
                    
            if not is_valid:
                return {'success': False, 'error': f'無效的交易對代碼 (找不到 {symbol})，請確認 Binance 是否支援'}

            symbols = SymbolManager.get_symbols()

            # 檢查是否已存在
            if any(s['symbol'] == symbol for s in symbols):
                return {'success': False, 'error': f'商品 {symbol} 已經存在'}

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
        """計算 RSI 指標（Wilder's 平滑法）"""
        if len(prices) < period + 1:
            return None

        # 計算每期漲跌幅
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

        # 第一個 period 用 SMA 初始化
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Wilder's 平滑法：逐步遞推
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

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
        """計算 MACD（完整 EMA 信號線）"""
        if len(prices) < slow + signal:
            return None, None, None

        # 計算快慢線的完整 EMA 序列
        fast_multiplier = 2 / (fast + 1)
        slow_multiplier = 2 / (slow + 1)

        # 初始化慢線 EMA（前 slow 根用 SMA）
        ema_slow_val = sum(prices[:slow]) / slow
        # 初始化快線 EMA（前 fast 根用 SMA）
        ema_fast_val = sum(prices[:fast]) / fast

        # 快線需要先推進到 slow 起始點
        for i in range(fast, slow):
            ema_fast_val = (prices[i] - ema_fast_val) * fast_multiplier + ema_fast_val

        # 從 slow 開始計算 MACD line 序列
        macd_series = []
        macd_val = ema_fast_val - ema_slow_val
        macd_series.append(macd_val)

        for i in range(slow, len(prices)):
            ema_fast_val = (prices[i] - ema_fast_val) * fast_multiplier + ema_fast_val
            ema_slow_val = (prices[i] - ema_slow_val) * slow_multiplier + ema_slow_val
            macd_val = ema_fast_val - ema_slow_val
            macd_series.append(macd_val)

        if len(macd_series) < signal:
            return None, None, None

        # 信號線 = EMA(MACD_series, signal_period)
        signal_multiplier = 2 / (signal + 1)
        signal_val = sum(macd_series[:signal]) / signal

        for i in range(signal, len(macd_series)):
            signal_val = (macd_series[i] - signal_val) * signal_multiplier + signal_val

        macd_line = macd_series[-1]
        signal_line = signal_val
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
        """✨ V3: 計算隨機指標 (Stochastic Oscillator)，%D = SMA(%K, d_period)"""
        # 需要足夠的數據來計算 d_period 個 %K 值
        required = k_period + d_period - 1
        if len(data) < required:
            return None, None

        # 計算多個 %K 值（至少 d_period 個）
        k_values = []
        for i in range(d_period):
            # 從尾端往前取每組 k_period 根 K 線
            end_idx = len(data) - (d_period - 1 - i)
            start_idx = end_idx - k_period
            window = data[start_idx:end_idx]

            highs = [float(k[2]) for k in window]
            lows = [float(k[3]) for k in window]
            close = float(window[-1][4])

            highest_high = max(highs)
            lowest_low = min(lows)

            if highest_high == lowest_low:
                k_values.append(50.0)
            else:
                k_values.append(((close - lowest_low) / (highest_high - lowest_low)) * 100)

        # %K 為最新值
        k_value = k_values[-1]

        # %D = SMA(%K, d_period)
        d_value = sum(k_values) / len(k_values)

        return round(k_value, 2), round(d_value, 2)

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
        """✨ 功能1: 成交量分析（使用 taker_buy_base_volume 計算 CVD）"""
        volumes = [float(k[5]) for k in data[-20:]]  # 最近20根K線
        avg_volume = sum(volumes) / len(volumes)
        current_volume = volumes[-1]

        # 計算成交量比率
        volume_ratio = round(current_volume / avg_volume, 2)

        # CVD (累積成交量差異) — 使用 taker_buy_base_volume（klines 欄位索引 9）
        # CVD = taker_buy_vol - (total_vol - taker_buy_vol) = 2 * taker_buy_vol - total_vol
        cvd_score = 0
        cvd_window = min(20, len(data))
        for i in range(len(data) - cvd_window, len(data)):
            total_vol = float(data[i][5])
            taker_buy_vol = float(data[i][9])
            cvd_score += (2 * taker_buy_vol - total_vol)

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

            # 獲取更大時間框架數據（使用快取）
            data = fetch_klines_cached(symbol, higher_tf, limit=50)

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

    # ============================================================
    # SMC (Smart Money Concepts) 引擎
    # ============================================================

    @staticmethod
    def find_swing_points(data, n=3, max_points=20):
        """識別 Swing High / Swing Low
        N 根 K 線確認：左右各 N 根都不超過中心點即為 Swing Point。
        Args:
            data: K 線數據列表
            n: 確認窗口大小（5m 用 3，15m 用 5）
            max_points: 最多保留的 Swing Point 數量
        Returns:
            list of dict: [{'type': 'high'|'low', 'price': float, 'index': int, 'time': int}, ...]
        """
        if len(data) < 2 * n + 1:
            return []

        swings = []

        for i in range(n, len(data) - n):
            high_i = float(data[i][2])
            low_i = float(data[i][3])

            # 檢查 Swing High：左右各 n 根的 high 都 <= 中心 high
            is_swing_high = True
            for j in range(i - n, i + n + 1):
                if j == i:
                    continue
                if float(data[j][2]) > high_i:
                    is_swing_high = False
                    break

            # 檢查 Swing Low：左右各 n 根的 low 都 >= 中心 low
            is_swing_low = True
            for j in range(i - n, i + n + 1):
                if j == i:
                    continue
                if float(data[j][3]) < low_i:
                    is_swing_low = False
                    break

            if is_swing_high:
                swings.append({
                    'type': 'high',
                    'price': high_i,
                    'index': i,
                    'time': int(data[i][0])
                })
            if is_swing_low:
                swings.append({
                    'type': 'low',
                    'price': low_i,
                    'index': i,
                    'time': int(data[i][0])
                })

        # 按 index 排序，保留最近 max_points 個
        swings.sort(key=lambda s: s['index'])
        return swings[-max_points:]

    @staticmethod
    def detect_bos(data, swing_points):
        """檢測 Break of Structure (BOS)
        規則：收盤價突破最近的 Swing High（看多 BOS）或 Swing Low（看空 BOS）。
        Args:
            data: K 線數據列表
            swing_points: find_swing_points() 的輸出
        Returns:
            list of dict: [{'direction': 'bullish'|'bearish', 'break_price': float,
                            'break_index': int, 'swing_price': float, 'time': int}, ...]
        """
        if not swing_points or len(data) < 2:
            return []

        bos_list = []
        # 分別追蹤最近的 Swing High 和 Swing Low
        last_swing_high = None
        last_swing_low = None

        for sp in swing_points:
            if sp['type'] == 'high':
                last_swing_high = sp
            elif sp['type'] == 'low':
                last_swing_low = sp

            # 檢查之後的 K 線是否突破
            start_idx = sp['index'] + 1
            for i in range(start_idx, len(data)):
                close_i = float(data[i][4])

                # 看多 BOS：收盤價突破 Swing High
                if sp['type'] == 'high' and close_i > sp['price']:
                    bos_list.append({
                        'direction': 'bullish',
                        'break_price': close_i,
                        'break_index': i,
                        'swing_price': sp['price'],
                        'time': int(data[i][0])
                    })
                    break

                # 看空 BOS：收盤價突破 Swing Low
                if sp['type'] == 'low' and close_i < sp['price']:
                    bos_list.append({
                        'direction': 'bearish',
                        'break_price': close_i,
                        'break_index': i,
                        'swing_price': sp['price'],
                        'time': int(data[i][0])
                    })
                    break

        return bos_list

    @staticmethod
    def identify_order_blocks(data, bos_list, max_obs=5):
        """識別 Order Block (OB)
        規則：BOS 前最後一根反向 K 線的 open~close 範圍。
        碰兩次後失效（由外部邏輯處理）。
        Args:
            data: K 線數據列表
            bos_list: detect_bos() 的輸出
            max_obs: 最多保留的有效 OB 數量
        Returns:
            list of dict: [{'type': 'bullish'|'bearish', 'top': float, 'bottom': float,
                            'index': int, 'time': int, 'touches': 0, 'bos_direction': str}, ...]
        """
        if not bos_list:
            return []

        obs = []
        current_price = float(data[-1][4])

        for bos in bos_list:
            break_idx = bos['break_index']

            # 往回找 BOS 前的最後一根反向 K 線
            for i in range(break_idx - 1, max(0, break_idx - 20) - 1, -1):
                open_p = float(data[i][1])
                close_p = float(data[i][4])
                is_bullish_candle = close_p > open_p

                # 看多 BOS → 找最後一根看空 K 線（OB 為支撐）
                if bos['direction'] == 'bullish' and not is_bullish_candle:
                    ob_top = max(open_p, close_p)
                    ob_bottom = min(open_p, close_p)
                    # 只保留價格仍在上方的 OB（尚未跌破）
                    if current_price >= ob_bottom:
                        obs.append({
                            'type': 'bullish',
                            'top': ob_top,
                            'bottom': ob_bottom,
                            'index': i,
                            'time': int(data[i][0]),
                            'touches': 0,
                            'bos_direction': bos['direction']
                        })
                    break

                # 看空 BOS → 找最後一根看多 K 線（OB 為阻力）
                if bos['direction'] == 'bearish' and is_bullish_candle:
                    ob_top = max(open_p, close_p)
                    ob_bottom = min(open_p, close_p)
                    # 只保留價格仍在下方的 OB（尚未突破）
                    if current_price <= ob_top:
                        obs.append({
                            'type': 'bearish',
                            'top': ob_top,
                            'bottom': ob_bottom,
                            'index': i,
                            'time': int(data[i][0]),
                            'touches': 0,
                            'bos_direction': bos['direction']
                        })
                    break

        # 按時間排序，保留最近 max_obs 個
        obs.sort(key=lambda o: o['index'])
        return obs[-max_obs:]

    @staticmethod
    def identify_fvg(data, max_fvgs=3):
        """識別 Fair Value Gap (FVG)
        規則：三根 K 線跳空 — K[0].high < K[2].low（看多）或 K[0].low > K[2].high（看空）。
        填補 50% 後失效。
        Args:
            data: K 線數據列表
            max_fvgs: 最多保留的未填補 FVG 數量
        Returns:
            list of dict: [{'type': 'bullish'|'bearish', 'top': float, 'bottom': float,
                            'index': int, 'time': int, 'filled_pct': float}, ...]
        """
        if len(data) < 3:
            return []

        fvgs = []
        current_price = float(data[-1][4])

        for i in range(2, len(data)):
            high_0 = float(data[i - 2][2])
            low_0 = float(data[i - 2][3])
            high_2 = float(data[i][2])
            low_2 = float(data[i][3])

            # 看多 FVG：K[0] 的 high < K[2] 的 low（中間有向上跳空）
            if high_0 < low_2:
                gap_top = low_2
                gap_bottom = high_0
                gap_size = gap_top - gap_bottom
                if gap_size <= 0:
                    continue
                # 計算填補百分比：價格從上方回填多少
                if current_price >= gap_top:
                    filled_pct = 0.0
                elif current_price <= gap_bottom:
                    filled_pct = 1.0
                else:
                    filled_pct = (gap_top - current_price) / gap_size

                if filled_pct < 0.5:
                    fvgs.append({
                        'type': 'bullish',
                        'top': gap_top,
                        'bottom': gap_bottom,
                        'index': i - 1,
                        'time': int(data[i - 1][0]),
                        'filled_pct': round(filled_pct, 2)
                    })

            # 看空 FVG：K[0] 的 low > K[2] 的 high（中間有向下跳空）
            if low_0 > high_2:
                gap_top = low_0
                gap_bottom = high_2
                gap_size = gap_top - gap_bottom
                if gap_size <= 0:
                    continue
                # 計算填補百分比：價格從下方回填多少
                if current_price <= gap_bottom:
                    filled_pct = 0.0
                elif current_price >= gap_top:
                    filled_pct = 1.0
                else:
                    filled_pct = (current_price - gap_bottom) / gap_size

                if filled_pct < 0.5:
                    fvgs.append({
                        'type': 'bearish',
                        'top': gap_top,
                        'bottom': gap_bottom,
                        'index': i - 1,
                        'time': int(data[i - 1][0]),
                        'filled_pct': round(filled_pct, 2)
                    })

        # 按時間排序，保留最近 max_fvgs 個未填補 FVG
        fvgs.sort(key=lambda f: f['index'])
        return fvgs[-max_fvgs:]

    @staticmethod
    def detect_liquidity_sweep(data, swing_points, atr, confirmation_window=3):
        """檢測 Liquidity Sweep（掃盤）
        規則：影線突破 Swing Point 但收盤價反轉回來，深度 ≥ ATR×0.5。
        Args:
            data: K 線數據列表
            swing_points: find_swing_points() 的輸出
            atr: 當前 ATR 值
            confirmation_window: 確認 K 線窗口（1-3 根）
        Returns:
            list of dict: [{'type': 'bullish'|'bearish', 'sweep_price': float,
                            'swing_price': float, 'index': int, 'time': int, 'depth': float}, ...]
        """
        if not swing_points or atr is None or atr <= 0 or len(data) < 3:
            return []

        min_depth = atr * 0.5
        sweeps = []

        for sp in swing_points:
            sp_idx = sp['index']

            # 在 Swing Point 之後的 K 線中尋找 Sweep
            for i in range(sp_idx + 1, min(sp_idx + 20, len(data))):
                high_i = float(data[i][2])
                low_i = float(data[i][3])
                close_i = float(data[i][4])
                open_i = float(data[i][1])

                if sp['type'] == 'high':
                    # 看空 Sweep：影線突破 Swing High 但收盤在下方
                    if high_i > sp['price'] and close_i < sp['price']:
                        depth = high_i - sp['price']
                        if depth >= min_depth:
                            # 確認：後續 K 線繼續向下
                            confirmed = False
                            for j in range(i + 1, min(i + confirmation_window + 1, len(data))):
                                if float(data[j][4]) < close_i:
                                    confirmed = True
                                    break
                            if confirmed or i == len(data) - 1:
                                sweeps.append({
                                    'type': 'bearish',
                                    'sweep_price': high_i,
                                    'swing_price': sp['price'],
                                    'index': i,
                                    'time': int(data[i][0]),
                                    'depth': round(depth, 2)
                                })
                            break

                elif sp['type'] == 'low':
                    # 看多 Sweep：影線突破 Swing Low 但收盤在上方
                    if low_i < sp['price'] and close_i > sp['price']:
                        depth = sp['price'] - low_i
                        if depth >= min_depth:
                            # 確認：後續 K 線繼續向上
                            confirmed = False
                            for j in range(i + 1, min(i + confirmation_window + 1, len(data))):
                                if float(data[j][4]) > close_i:
                                    confirmed = True
                                    break
                            if confirmed or i == len(data) - 1:
                                sweeps.append({
                                    'type': 'bullish',
                                    'sweep_price': low_i,
                                    'swing_price': sp['price'],
                                    'index': i,
                                    'time': int(data[i][0]),
                                    'depth': round(depth, 2)
                                })
                            break

        return sweeps

    # ============================================================
    # 三維評分系統
    # ============================================================

    @staticmethod
    def calc_trend_score(bos_list, mtf_analysis, ema_fast, ema_slow, current_price,
                         bb_upper, bb_middle, bb_lower):
        """計算趨勢分數 (0-100)
        BOS 方向(±30) + MTF 一致(+25/-10) + EMA 排列(±15) + 價格 vs EMA(±10) + BB(±10)
        原始分 +50 後映射到 0-100
        """
        raw = 0

        # BOS 方向 (±30)：取最近的 BOS
        if bos_list:
            last_bos = bos_list[-1]
            if last_bos['direction'] == 'bullish':
                raw += 30
            else:
                raw -= 30

        # MTF 一致 (+25/-10)
        if mtf_analysis.get('confirmation'):
            mtf_trend = mtf_analysis.get('trend', 'neutral')
            if bos_list:
                bos_dir = bos_list[-1]['direction']
                if (bos_dir == 'bullish' and mtf_trend == 'uptrend') or \
                   (bos_dir == 'bearish' and mtf_trend == 'downtrend'):
                    raw += 25
                else:
                    raw -= 10
            else:
                if mtf_trend == 'uptrend':
                    raw += 15
                elif mtf_trend == 'downtrend':
                    raw -= 15

        # EMA 排列 (±15)
        if ema_fast is not None and ema_slow is not None:
            if ema_fast > ema_slow:
                raw += 15
            elif ema_fast < ema_slow:
                raw -= 15

        # 價格 vs EMA (±10)
        if ema_fast is not None:
            if current_price > ema_fast:
                raw += 10
            elif current_price < ema_fast:
                raw -= 10

        # BB 位置 (±10)
        if bb_upper and bb_lower and bb_middle:
            if current_price > bb_middle:
                raw += 10
            elif current_price < bb_middle:
                raw -= 10

        # 映射：raw ∈ [-100, +100] → +50 → [0, 100]，clamp
        score = max(0, min(100, raw + 50))
        return score

    @staticmethod
    def calc_structure_score(order_blocks, fvgs, sweeps, current_price, atr,
                             bos_list):
        """計算結構分數 (0-100)
        OB 進入(+30) + 趨勢一致(+15) + FVG(+15) + Sweep 確認(+25) +
        深度合理(+10) + 過深(-10) + 已測試(-15)
        """
        score = 0

        # OB 進入 (+30)：價格進入某個 OB 區域
        active_ob = None
        for ob in reversed(order_blocks):
            if ob['bottom'] <= current_price <= ob['top']:
                score += 30
                active_ob = ob
                break
            # 接近 OB（距離 ≤ ATR×0.5），放寬給分
            if atr and atr > 0:
                dist_to_ob = min(abs(current_price - ob['top']), abs(current_price - ob['bottom']))
                if dist_to_ob <= atr * 0.5:
                    score += 25  # 提升接近 OB 的分數
                    active_ob = ob
                    break

        # 趨勢一致 (+15)：OB 方向與最近 BOS 一致
        if active_ob and bos_list:
            last_bos = bos_list[-1]
            if active_ob['type'] == last_bos['direction']:
                score += 15

        # FVG (+15)：存在未填補的 FVG
        if fvgs:
            for fvg in fvgs:
                if fvg['bottom'] <= current_price <= fvg['top']:
                    score += 15
                    break
            else:
                # 接近 FVG
                if atr and atr > 0:
                    for fvg in fvgs:
                        dist = min(abs(current_price - fvg['top']), abs(current_price - fvg['bottom']))
                        if dist <= atr * 0.5:
                            score += 15  # 提升接近 FVG 的分數
                            break

        # 基礎結構分數 (+10)
        if active_ob and bos_list:
             last_bos = bos_list[-1]
             if active_ob['type'] == last_bos['direction']:
                  score += 10

        # Sweep 確認 (+25)：最近有 Sweep 發生
        if sweeps:
            last_sweep = sweeps[-1]
            # Sweep 在最近 10 根 K 線內
            score += 25

        # 深度合理 (+10) / 過深 (-10)
        if active_ob and atr and atr > 0:
            ob_mid = (active_ob['top'] + active_ob['bottom']) / 2
            depth_ratio = abs(current_price - ob_mid) / atr
            if 0.3 <= depth_ratio <= 1.5:
                score += 10  # 深度合理
            elif depth_ratio > 2.5:
                score -= 10  # 過深

        # 已測試 (-15)：OB 被碰過
        if active_ob and active_ob.get('touches', 0) >= 1:
            score -= 15

        return max(0, min(100, score))

    @staticmethod
    def calc_momentum_score(rsi, macd_line, signal_line, histogram, stoch_k, stoch_d,
                            volume_analysis, data, prev_histogram=None, atr=None):
        """計算動量分數 (0-100)
        RSI 反轉(+20) + RSI 背離(+15) + MACD 柱翻(+20) + MACD 叉(+10) +
        Stoch 叉(+10) + 放量(+15) + 縮量(-10) + taker_buy>60%(+10)
        """
        score = 0

        # RSI 反轉 (+20) 或 合理區間 (+10)
        if rsi is not None:
            if 30 <= rsi <= 40:
                score += 20  # 從超賣區反轉
            elif 60 <= rsi <= 70:
                score += 20  # 從超買區反轉
            elif rsi < 25 or rsi > 75:
                score += 10  # 極端區域，可能反轉
            elif 40 < rsi < 55:
                # 合理偏離區間給予基礎分
                if macd_line is not None and macd_line > 0:
                    score += 10
            elif 45 < rsi < 60:
                if macd_line is not None and macd_line < 0:
                    score += 10

        # RSI 背離 (+15)：簡化版 — 價格新低但 RSI 未新低（或反向）
        if rsi is not None and len(data) >= 20:
            closes_recent = [float(data[i][4]) for i in range(len(data) - 10, len(data))]
            closes_prev = [float(data[i][4]) for i in range(len(data) - 20, len(data) - 10)]
            if min(closes_recent) < min(closes_prev) and rsi > 35:
                score += 15  # 看多背離
            elif max(closes_recent) > max(closes_prev) and rsi < 65:
                score += 15  # 看空背離

        # MACD 柱翻 (+20)：比較前後兩根 histogram 符號穿越（相對判斷，適用各價格資產）
        if histogram is not None:
            if prev_histogram is not None:
                if prev_histogram <= 0 < histogram:
                    score += 20  # 從負轉正（多頭柱翻）
                elif prev_histogram >= 0 > histogram:
                    score += 20  # 從正轉負（空頭柱翻）
            elif atr and atr > 0 and abs(histogram) < atr * 0.05:
                # fallback：histogram 極小代表接近穿越
                score += 10

        # MACD 叉 (+10) 或 同向 (+10)：用 ATR 正規化閾值，避免絕對值問題
        if macd_line is not None and signal_line is not None:
            diff = macd_line - signal_line
            if atr and atr > 0:
                threshold = atr * 0.1
                if 0 < diff < threshold:
                    score += 10  # 金叉（差距在 ATR 10% 內）
                elif -threshold < diff < 0:
                    score += 10  # 死叉
                elif diff > threshold and macd_line > 0:
                    score += 10  # 同向做多基礎分
                elif diff < -threshold and macd_line < 0:
                    score += 10  # 同向做空基礎分
            else:
                # 無 ATR 時用相對比例
                denom = abs(macd_line) + 1e-8
                if 0 < diff / denom < 0.15:
                    score += 10
                elif -0.15 < diff / denom < 0:
                    score += 10
                elif diff / denom >= 0.15 and macd_line > 0:
                    score += 10
                elif diff / denom <= -0.15 and macd_line < 0:
                    score += 10

        # Stochastic 叉 (+10)
        if stoch_k is not None and stoch_d is not None:
            if stoch_k > stoch_d and stoch_k < 30:
                score += 10  # 低位金叉
            elif stoch_k < stoch_d and stoch_k > 70:
                score += 10  # 高位死叉

        # 放量 (+15) / 普通 (+5) / 縮量 (-10)
        if volume_analysis:
            if volume_analysis.get('signal') == 'strong':
                score += 15
            elif volume_analysis.get('signal') == 'normal':
                score += 5
            elif volume_analysis.get('signal') == 'weak':
                score -= 10

        # taker_buy > 60% (+10)
        if volume_analysis and len(data) >= 1:
            total_vol = float(data[-1][5])
            taker_buy = float(data[-1][9])
            if total_vol > 0 and (taker_buy / total_vol) > 0.6:
                score += 10

        return max(0, min(100, score))

    @staticmethod
    def calc_dynamic_sl_tp(current_price, atr, signal_type, order_blocks, fvgs, swing_points):
        """動態止損止盈計算（結構錨點 + ATR clamp）
        止損: clamp(OB 邊界外側, ATR×1.0, ATR×2.5)
        止盈①: 最近結構目標，最小 ATR×1.0 (R:R ≥ 1:1)
        止盈②: 下一層結構，最小 ATR×2.0 (R:R ≥ 1:2)
        回退: ATR×1.5 / ATR×3.0
        R:R < 1.0 不發信號（返回 None）
        """
        if atr is None or atr <= 0:
            return None

        atr_min = atr * 1.0
        atr_max = atr * 2.5

        # === 止損計算 ===
        sl_anchor = None
        if signal_type == 'buy':
            # 找最近的 bullish OB 底部作為止損錨點
            for ob in reversed(order_blocks):
                if ob['type'] == 'bullish' and ob['bottom'] < current_price:
                    sl_anchor = ob['bottom']
                    break
            if sl_anchor is None:
                # 回退：找最近的 Swing Low
                for sp in reversed(swing_points):
                    if sp['type'] == 'low' and sp['price'] < current_price:
                        sl_anchor = sp['price']
                        break

            if sl_anchor is not None:
                sl_distance = current_price - sl_anchor
                # clamp 到 ATR 範圍
                sl_distance = max(atr_min, min(atr_max, sl_distance))
            else:
                sl_distance = atr * 1.5  # 回退

            stop_loss = round(current_price - sl_distance, 2)

        else:  # sell
            # 找最近的 bearish OB 頂部作為止損錨點
            for ob in reversed(order_blocks):
                if ob['type'] == 'bearish' and ob['top'] > current_price:
                    sl_anchor = ob['top']
                    break
            if sl_anchor is None:
                for sp in reversed(swing_points):
                    if sp['type'] == 'high' and sp['price'] > current_price:
                        sl_anchor = sp['price']
                        break

            if sl_anchor is not None:
                sl_distance = sl_anchor - current_price
                sl_distance = max(atr_min, min(atr_max, sl_distance))
            else:
                sl_distance = atr * 1.5

            stop_loss = round(current_price + sl_distance, 2)

        # === 止盈計算 ===
        tp1_anchor = None
        tp2_anchor = None

        if signal_type == 'buy':
            # 止盈目標：向上找結構（FVG top / OB top / Swing High）
            targets = []
            for fvg in fvgs:
                if fvg['type'] == 'bearish' and fvg['bottom'] > current_price:
                    targets.append(fvg['bottom'])
            for ob in order_blocks:
                if ob['type'] == 'bearish' and ob['bottom'] > current_price:
                    targets.append(ob['bottom'])
            for sp in swing_points:
                if sp['type'] == 'high' and sp['price'] > current_price:
                    targets.append(sp['price'])
            targets.sort()

            if targets:
                tp1_anchor = targets[0]
            if len(targets) > 1:
                tp2_anchor = targets[1]

        else:  # sell
            targets = []
            for fvg in fvgs:
                if fvg['type'] == 'bullish' and fvg['top'] < current_price:
                    targets.append(fvg['top'])
            for ob in order_blocks:
                if ob['type'] == 'bullish' and ob['top'] < current_price:
                    targets.append(ob['top'])
            for sp in swing_points:
                if sp['type'] == 'low' and sp['price'] < current_price:
                    targets.append(sp['price'])
            targets.sort(reverse=True)

            if targets:
                tp1_anchor = targets[0]
            if len(targets) > 1:
                tp2_anchor = targets[1]

        # 計算止盈距離 + 最小值保證
        if signal_type == 'buy':
            tp1_dist = (tp1_anchor - current_price) if tp1_anchor else atr * 1.5
            tp1_dist = max(tp1_dist, atr * 1.0)
            tp2_dist = (tp2_anchor - current_price) if tp2_anchor else atr * 3.0
            tp2_dist = max(tp2_dist, atr * 2.0)
            take_profit_1 = round(current_price + tp1_dist, 2)
            take_profit_2 = round(current_price + tp2_dist, 2)
        else:
            tp1_dist = (current_price - tp1_anchor) if tp1_anchor else atr * 1.5
            tp1_dist = max(tp1_dist, atr * 1.0)
            tp2_dist = (current_price - tp2_anchor) if tp2_anchor else atr * 3.0
            tp2_dist = max(tp2_dist, atr * 2.0)
            take_profit_1 = round(current_price - tp1_dist, 2)
            take_profit_2 = round(current_price - tp2_dist, 2)

        # R:R 計算
        risk = sl_distance
        reward = tp2_dist
        rr_ratio = round(reward / risk, 2) if risk > 0 else 0

        # R:R < 1.0 不發信號
        if rr_ratio < 1.0:
            return None

        return {
            'stop_loss': stop_loss,
            'take_profit_1': take_profit_1,
            'take_profit_2': take_profit_2,
            'risk_amount': round(risk, 2),
            'reward_amount': round(reward, 2),
            'risk_reward_ratio': rr_ratio,
            'atr': round(atr, 2)
        }

    # ============================================================
    # 兩階段信號系統
    # ============================================================

    @staticmethod
    def check_pre_alert(current_price, atr, order_blocks, swing_points, fvgs):
        """檢查預警觸發條件
        觸發條件（任一即可）：
        - 距離 OB ≤ ATR×0.5
        - 接近 Swing High/Low（≤ ATR×0.5）
        - 在 FVG 50% 範圍內
        Returns: (triggered: bool, alert_info: dict|None)
        """
        if atr is None or atr <= 0:
            return False, None

        threshold = atr * 0.5

        # 檢查 OB 接近
        for ob in reversed(order_blocks):
            dist = min(abs(current_price - ob['top']), abs(current_price - ob['bottom']))
            if dist <= threshold:
                direction = '多方' if ob['type'] == 'bullish' else '空方'
                return True, {
                    'alert_type': 'ob_proximity',
                    'alert_message': f'接近{direction} Order Block ({ob["bottom"]:.1f}-{ob["top"]:.1f})',
                    'proximity': round(dist / atr, 2)
                }

        # 檢查 Swing Point 接近
        for sp in reversed(swing_points):
            dist = abs(current_price - sp['price'])
            if dist <= threshold:
                sp_type = 'Swing High' if sp['type'] == 'high' else 'Swing Low'
                return True, {
                    'alert_type': 'swing_proximity',
                    'alert_message': f'接近 {sp_type} ({sp["price"]:.1f})',
                    'proximity': round(dist / atr, 2)
                }

        # 檢查 FVG 範圍內
        for fvg in fvgs:
            if fvg['bottom'] <= current_price <= fvg['top']:
                direction = '多方' if fvg['type'] == 'bullish' else '空方'
                return True, {
                    'alert_type': 'fvg_inside',
                    'alert_message': f'進入{direction} FVG 區域 ({fvg["bottom"]:.1f}-{fvg["top"]:.1f})',
                    'proximity': 0.0
                }
            # 接近 FVG
            dist = min(abs(current_price - fvg['top']), abs(current_price - fvg['bottom']))
            if dist <= threshold * 0.5:
                direction = '多方' if fvg['type'] == 'bullish' else '空方'
                return True, {
                    'alert_type': 'fvg_proximity',
                    'alert_message': f'接近{direction} FVG ({fvg["bottom"]:.1f}-{fvg["top"]:.1f})',
                    'proximity': round(dist / atr, 2)
                }

        return False, None

    @staticmethod
    def determine_signal_label(order_blocks, fvgs, sweeps, current_price, atr):
        """判定信號類型標籤"""
        if not atr or atr <= 0:
            return '指標共振'

        # Sweep 確認優先級最高
        if sweeps:
            last = sweeps[-1]
            return 'Sweep 確認' if last['type'] == 'bullish' else 'Sweep 確認'

        # OB 反彈
        for ob in reversed(order_blocks):
            if ob['bottom'] <= current_price <= ob['top']:
                return 'OB 反彈' if ob['type'] == 'bullish' else 'OB 壓力'

        # FVG 進入
        for fvg in fvgs:
            if fvg['bottom'] <= current_price <= fvg['top']:
                return 'FVG 支撐' if fvg['type'] == 'bullish' else 'FVG 阻力'

        return '指標共振'

    @staticmethod
    def update_signal_state(symbol, interval, current_bar_index, pre_alert_info, is_confirmed):
        """更新兩階段信號狀態（預警 6 根過期、信號 3 根失效）"""
        cache_key = f"{symbol}_{interval}"
        now = time.time()

        existing = _signal_state.get(cache_key)

        if is_confirmed:
            _signal_state[cache_key] = {
                'type': 'signal',
                'bar_index': current_bar_index,
                'created_at': now
            }
            return 'signal'

        if pre_alert_info:
            # 檢查是否已有預警
            if existing and existing['type'] == 'pre_alert':
                bars_elapsed = current_bar_index - existing['bar_index']
                if bars_elapsed >= 6:
                    # 預警過期，重新建立
                    _signal_state[cache_key] = {
                        'type': 'pre_alert',
                        'bar_index': current_bar_index,
                        'created_at': now,
                        **pre_alert_info
                    }
                    return 'pre_alert'
                return 'pre_alert'  # 預警仍有效
            else:
                _signal_state[cache_key] = {
                    'type': 'pre_alert',
                    'bar_index': current_bar_index,
                    'created_at': now,
                    **pre_alert_info
                }
                return 'pre_alert'

        # 無預警也無信號：檢查現有狀態是否過期
        if existing:
            bars_elapsed = current_bar_index - existing['bar_index']
            if existing['type'] == 'pre_alert' and bars_elapsed >= 6:
                del _signal_state[cache_key]
            elif existing['type'] == 'signal' and bars_elapsed >= 3:
                del _signal_state[cache_key]

        return None

    @staticmethod
    def analyze_entry_signal(data, params, symbol):
        """綜合信號分析 — SMC + 三維評分 + 兩階段信號"""
        closes = [float(k[4]) for k in data]
        current_price = closes[-1]
        interval = params.get('interval', '5m')

        # 基礎指標計算
        rsi = ScalpingAnalyzerPro.calculate_rsi(closes, params['rsi_period'])
        ema_fast = ScalpingAnalyzerPro.calculate_ema(closes, params['ema_fast'])
        ema_slow = ScalpingAnalyzerPro.calculate_ema(closes, params['ema_slow'])
        macd_line, signal_line, histogram = ScalpingAnalyzerPro.calculate_macd(
            closes, params['macd_fast'], params['macd_slow'], params['macd_signal']
        )
        # 取前一根 histogram 用於穿越判斷（相對判斷，避免絕對值問題）
        _, _, prev_histogram = ScalpingAnalyzerPro.calculate_macd(
            closes[:-1], params['macd_fast'], params['macd_slow'], params['macd_signal']
        )
        atr = ScalpingAnalyzerPro.calculate_atr(data, 14)
        bb_upper, bb_middle, bb_lower = ScalpingAnalyzerPro.calculate_bollinger_bands(closes, 20, 2)
        stoch_k, stoch_d = ScalpingAnalyzerPro.calculate_stochastic(data, 14, 3)
        volume_analysis = ScalpingAnalyzerPro.analyze_volume(data)
        mtf_analysis = ScalpingAnalyzerPro.multi_timeframe_analysis(symbol, interval)

        # SMC 引擎
        swing_n = 5 if interval == '15m' else 3
        swing_points = ScalpingAnalyzerPro.find_swing_points(data, n=swing_n)
        bos_list = ScalpingAnalyzerPro.detect_bos(data, swing_points)
        order_blocks = ScalpingAnalyzerPro.identify_order_blocks(data, bos_list)
        fvgs = ScalpingAnalyzerPro.identify_fvg(data)
        sweeps = ScalpingAnalyzerPro.detect_liquidity_sweep(data, swing_points, atr)

        # 三維評分
        trend_score = ScalpingAnalyzerPro.calc_trend_score(
            bos_list, mtf_analysis, ema_fast, ema_slow, current_price,
            bb_upper, bb_middle, bb_lower
        )
        structure_score = ScalpingAnalyzerPro.calc_structure_score(
            order_blocks, fvgs, sweeps, current_price, atr, bos_list
        )
        momentum_score = ScalpingAnalyzerPro.calc_momentum_score(
            rsi, macd_line, signal_line, histogram, stoch_k, stoch_d,
            volume_analysis, data, prev_histogram=prev_histogram, atr=atr
        )

        # 品質評分轉換 (Quality Score)：滿分 300 分
        quality_score = round((trend_score + structure_score + momentum_score) / 2.5 / 20, 1)
        quality_score = max(0, min(5, quality_score))

        # 信號判定（調降門檻）
        signal_type = None
        if trend_score >= 60 and structure_score >= 45 and momentum_score >= 45 and (structure_score + momentum_score) >= 100:
            overall = 'strong_buy'
            action = '強烈買入 BUY'
            signal_type = 'buy'
        elif trend_score >= 50 and structure_score >= 35 and momentum_score >= 35 and (structure_score + momentum_score) >= 80:
            overall = 'buy'
            action = '考慮買入'
            signal_type = 'buy'
        elif trend_score <= 40 and structure_score >= 45 and momentum_score >= 45 and (structure_score + momentum_score) >= 100:
            overall = 'strong_sell'
            action = '強烈賣出 SELL'
            signal_type = 'sell'
        elif trend_score <= 50 and structure_score >= 35 and momentum_score >= 35 and (structure_score + momentum_score) >= 80:
            overall = 'sell'
            action = '考慮賣出'
            signal_type = 'sell'
        else:
            overall = 'neutral'
            action = '觀望 WAIT'

        # 兩階段信號系統
        current_bar_index = len(data) - 1
        pre_alert_triggered, pre_alert_info = ScalpingAnalyzerPro.check_pre_alert(
            current_price, atr, order_blocks, swing_points, fvgs
        )

        # 動態止損止盈（結構錨點 + ATR clamp）
        sl_tp = None
        signal_label = None
        signal_stage = None  # 'pre_alert' | 'confirmed' | None

        if signal_type:
            # 正式信號需要預警已觸發（或同時觸發）
            if pre_alert_triggered:
                sl_tp = ScalpingAnalyzerPro.calc_dynamic_sl_tp(
                    current_price, atr, signal_type, order_blocks, fvgs, swing_points
                )
                if sl_tp is None:
                    # R:R < 1.0 → 降級為預警
                    signal_stage = 'pre_alert'
                    overall = 'pre_alert'
                    action = '觀望 WAIT（R:R 不足）'
                    signal_type = None
                else:
                    signal_stage = 'confirmed'
                    signal_label = ScalpingAnalyzerPro.determine_signal_label(
                        order_blocks, fvgs, sweeps, current_price, atr
                    )
            else:
                # 方案 A：三維達標但無預警 → 仍發出信號，不帶 confirmed badge
                sl_tp = ScalpingAnalyzerPro.calc_dynamic_sl_tp(
                    current_price, atr, signal_type, order_blocks, fvgs, swing_points
                )
                signal_stage = None  # 無結構確認，無 badge
                signal_label = ScalpingAnalyzerPro.determine_signal_label(
                    order_blocks, fvgs, sweeps, current_price, atr
                )
        elif pre_alert_triggered:
            signal_stage = 'pre_alert'

        # 更新信號狀態（過期管理）
        ScalpingAnalyzerPro.update_signal_state(
            symbol, interval, current_bar_index, pre_alert_info,
            is_confirmed=(signal_stage == 'confirmed')
        )

        # 組裝結果（向後相容 + 三維/SMC/兩階段信號）
        signals = {
            'rsi': {'value': rsi, 'signal': 'neutral'},
            'ema': {'fast': ema_fast, 'slow': ema_slow, 'signal': 'neutral'},
            'macd': {'line': macd_line, 'signal': signal_line, 'histogram': histogram},
            'volume': volume_analysis,
            'multi_timeframe': mtf_analysis,
            'bollinger': {'upper': bb_upper, 'middle': bb_middle, 'lower': bb_lower, 'signal': 'neutral'},
            'stochastic': {'k': stoch_k, 'd': stoch_d, 'signal': 'neutral'},
            'overall': overall,
            'action': action,
            'strength': abs(trend_score - 50) / 10,
            'quality_score': quality_score,
            'trend_score': trend_score,
            'structure_score': structure_score,
            'momentum_score': momentum_score,
            'signal_label': signal_label,
            'signal_stage': signal_stage,
            'pre_alert': pre_alert_info,
            'smc': {
                'swing_points': len(swing_points),
                'bos': [{'direction': b['direction'], 'time': b['time']} for b in bos_list[-3:]],
                'order_blocks': [{'type': o['type'], 'top': o['top'], 'bottom': o['bottom']}
                                 for o in order_blocks],
                'fvgs': [{'type': f['type'], 'top': f['top'], 'bottom': f['bottom'],
                          'filled_pct': f['filled_pct']} for f in fvgs],
                'sweeps': [{'type': s['type'], 'depth': s['depth']} for s in sweeps]
            },
            'stop_loss_take_profit': sl_tp
        }

        # 填充個別指標信號狀態（用於前端顯示）
        if rsi is not None:
            if rsi < params['rsi_oversold']:
                signals['rsi']['signal'] = 'buy'
            elif rsi > params['rsi_overbought']:
                signals['rsi']['signal'] = 'sell'
        if ema_fast and ema_slow:
            signals['ema']['signal'] = 'bullish' if ema_fast > ema_slow else 'bearish'
        if macd_line is not None and signal_line is not None:
            if histogram and histogram > 0:
                signals['macd']['signal'] = 'buy'
            elif histogram and histogram < 0:
                signals['macd']['signal'] = 'sell'
        if bb_upper and bb_lower:
            if current_price >= bb_upper:
                signals['bollinger']['signal'] = 'overbought'
            elif current_price <= bb_lower:
                signals['bollinger']['signal'] = 'oversold'
            elif current_price < bb_middle:
                signals['bollinger']['signal'] = 'buy_zone'
            else:
                signals['bollinger']['signal'] = 'sell_zone'
        if stoch_k and stoch_d:
            if stoch_k < 20:
                signals['stochastic']['signal'] = 'oversold'
            elif stoch_k > 80:
                signals['stochastic']['signal'] = 'overbought'
            elif stoch_k > stoch_d:
                signals['stochastic']['signal'] = 'bullish_cross'
            else:
                signals['stochastic']['signal'] = 'bearish_cross'

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
                f'<head><script>window.APP_PREFIX = "{PREFIX}"; window.APP_VERSION = "{VERSION}";</script>',
                1
            ).replace('V{VERSION}', f'V{VERSION}')
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
        elif self.path.startswith(p + '/api/supported_symbols'):
            self.handle_api_supported_symbols()
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
            ema_fast = int(params.get('ema_fast', [9])[0])
            ema_slow = int(params.get('ema_slow', [21])[0])
            macd_fast = int(params.get('macd_fast', [12])[0])
            macd_slow = int(params.get('macd_slow', [26])[0])
            macd_signal = int(params.get('macd_signal', [9])[0])

            # 獲取 K 線數據（使用快取 + 重試）
            data = fetch_klines_cached(symbol, interval, limit=150)

            # 數據驗證
            is_valid, data, data_warnings = validate_kline_data(data, min_count=50)
            if not is_valid:
                raise ValueError(data_warnings[0] if data_warnings else 'K 線數據驗證失敗')

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
                    'volume': float(k[5]),
                    'taker_buy_volume': float(k[9])  # taker_buy_base_asset_volume
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
                'overlays': overlays,
                'data_warnings': data_warnings if data_warnings else None
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

    def handle_api_supported_symbols(self):
        """獲取所有支援的 Binance USDT 商品"""
        try:
            file_path = 'supported_symbols.json'
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    symbols = json.load(f)
            else:
                symbols = []

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'supported_symbols': symbols}, ensure_ascii=False).encode('utf-8'))
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
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Scalping Analyzer Pro V{VERSION} | 剝頭皮交易分析器</title>
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
            position: relative;
        }

        .auto-refresh label {
            margin-bottom: 0;
            cursor: pointer;
            user-select: none;
        }

        /* ✨ Refresh & Global Settings Popover/Modal */
        .header-settings-btn {
            background: var(--color-bg);
            border: 1px solid var(--color-border);
            font-size: 16px;
            cursor: pointer;
            padding: 5px 10px !important;
            border-radius: 6px;
            color: var(--color-text-main);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
        }
        .header-settings-btn:hover {
            border-color: var(--color-accent);
            background: rgba(102, 126, 234, 0.1);
        }
        
        .global-settings-modal {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.85); /* 提高透明度 */
            backdrop-filter: blur(8px); /* 增加毛玻璃效果避免看到後面 */
            -webkit-backdrop-filter: blur(8px);
            z-index: 10005;
            display: none;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .global-settings-modal.show {
            display: flex;
        }
        
        .global-settings-content {
            background: var(--color-bg); /* 改用不透明底色取代 panel-bg */
            border: 2px solid var(--color-border);
            border-radius: 12px;
            padding: 24px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.8);
        }
        
        .settings-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .settings-row:last-child {
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
        }
        
        .settings-label {
            font-size: 15px;
            font-weight: 600;
            color: var(--color-text-main);
        }
        
        .settings-control input[type="number"], .settings-control select {
            width: 100px;
            padding: 8px 12px;
            font-size: 16px;
            background: var(--color-bg);
            border: 1px solid var(--color-border);
            color: var(--color-accent);
            border-radius: 6px;
            text-align: center;
            font-weight: bold;
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

        /* === 三維評分進度條 === */
        .tri-score-panel {
            background: var(--color-bg);
            border-radius: 12px;
            padding: 20px;
            margin-top: 20px;
        }
        .tri-score-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--color-text-main);
            margin-bottom: 16px;
            text-align: center;
        }
        .tri-score-row {
            display: flex;
            align-items: center;
            margin-bottom: 12px;
            gap: 10px;
        }
        .tri-score-row:last-child {
            margin-bottom: 0;
        }
        .tri-score-label {
            font-size: 13px;
            font-weight: 600;
            color: var(--color-text-muted);
            min-width: 65px;
            text-align: right;
        }
        .tri-score-bar {
            flex: 1;
            height: 14px;
            background: var(--color-card);
            border-radius: 7px;
            overflow: hidden;
            position: relative;
        }
        .tri-score-fill {
            height: 100%;
            border-radius: 7px;
            transition: width 0.6s ease;
            min-width: 2px;
        }
        .tri-score-fill.trend { background: linear-gradient(90deg, #6366f1, #818cf8); }
        .tri-score-fill.structure { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
        .tri-score-fill.momentum { background: linear-gradient(90deg, #10b981, #34d399); }
        .tri-score-val {
            font-size: 14px;
            font-weight: 700;
            color: var(--color-text-main);
            min-width: 32px;
            text-align: left;
        }

        /* === 預警 / 正式信號卡片 === */
        .action-card.pre_alert {
            background: linear-gradient(135deg, #f59e0b, #d97706);
        }
        .signal-label-badge {
            display: inline-block;
            margin-top: 8px;
            padding: 4px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            background: rgba(255,255,255,0.25);
            color: white;
        }
        .pre-alert-hint {
            margin-top: 8px;
            font-size: 13px;
            opacity: 0.85;
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
        <div class="header" style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 10px;">
            <div style="flex: 1;">
                <h1>📊 Scalping Analyzer Pro<span class="version-badge">V{VERSION}</span></h1>
                <p class="subtitle" data-i18n="subtitle">Professional Scalping Trading System - Real-time Signal Analysis</p>
                <div class="feature-tags">
                    <span class="feature-tag" data-i18n="tag_chart">📈 Live Chart</span>
                    <span class="feature-tag" data-i18n="tag_volume">✨ Volume Analysis</span>
                    <span class="feature-tag" data-i18n="tag_mtf">📈 Multi-Timeframe</span>
                    <span class="feature-tag" data-i18n="tag_sltp">🎯 Dynamic SL/TP</span>
                    <span class="feature-tag" data-i18n="tag_quality">📊 3D Signal Score</span>
                    <span class="feature-tag" data-i18n="tag_notify">🔔 Browser Alerts</span>
                    <span class="feature-tag">📊 Bollinger Bands</span>
                    <span class="feature-tag">📉 Stochastic</span>
                    <span class="feature-tag" data-i18n="tag_snapshot">📸 Snapshots</span>
                    <span class="feature-tag" data-i18n="tag_custom">➕ Custom Symbols</span>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 6px; flex-shrink: 0;">
                <button class="header-settings-btn" onclick="toggleGlobalSettings()" title="Global Settings">⚙️</button>
                <button id="lang-en-btn" onclick="switchLang('en')" style="padding: 5px 12px; font-size: 12px; background: var(--color-accent); color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 700; width: auto;">EN</button>
                <button id="lang-zh-btn" onclick="switchLang('zh_TW')" style="padding: 5px 12px; font-size: 12px; background: var(--color-bg); color: var(--color-text-muted); border: 1px solid var(--color-border); border-radius: 6px; cursor: pointer; font-weight: 600; width: auto;">中文</button>
            </div>
        </div>

        <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 15px; flex-wrap: wrap;">
            <button class="sidebar-toggle-btn" onclick="toggleMainSidebar()" style="margin: 0; padding: 10px 15px; font-size: 15px; border-radius: 8px; background: var(--color-panel-bg); color: var(--color-text-main); border: 1px solid var(--color-border); cursor: pointer; font-weight: bold; transition: all 0.3s ease;">
                <span id="sidebar-toggle-icon">◀</span> <span data-i18n="settings_title">Settings</span>
            </button>
            <button onclick="analyze()" style="margin: 0; padding: 10px 20px; font-size: 16px; background: linear-gradient(135deg, #10b981, #059669); color: white; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); transition: all 0.3s ease;">
                🔍 <span data-i18n="btn_analyze">Analyze Signal</span>
            </button>
            <div class="auto-refresh-large" style="display: flex; align-items: center; gap: 8px; background: var(--color-panel-bg); padding: 8px 15px; border-radius: 8px; border: 1px solid var(--color-border);">
                <input type="checkbox" id="auto_refresh" onchange="toggleAutoRefresh()" style="width: 20px; height: 20px; cursor: pointer; accent-color: var(--color-buy); margin: 0;">
                <label for="auto_refresh" id="auto_refresh_label" style="margin: 0; font-size: 15px; font-weight: 600; cursor: pointer; user-select: none; color: var(--color-text-main);">
                    <span data-i18n="auto_refresh">Auto-refresh</span> (<span id="refresh_sec_display">10</span>s)
                </label>
            </div>
        </div>

        <div class="main-grid" id="main-grid">
            <div class="panel sidebar">
                <div class="panel-title collapsible-header" onclick="toggleCollapse('settings-content', this)">
                    <span>⚙️ <span data-i18n="settings_title">Settings</span></span>
                    <span class="toggle-icon">▼</span>
                </div>
                <div id="settings-content" class="collapsible-content">

                <div class="form-group">
                    <label data-i18n="label_symbol">Trading Pair Symbol</label>
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
                        ➕ <span data-i18n="btn_add_symbol">Add Custom Symbol</span>
                    </button>
                </div>

                <div class="form-group">
                    <label data-i18n="label_interval">Interval</label>
                    <select id="interval">
                        <option value="1m" data-i18n="interval_1m">1 min</option>
                        <option value="3m" data-i18n="interval_3m">3 min</option>
                        <option value="5m" selected data-i18n="interval_5m">5 min</option>
                        <option value="15m" data-i18n="interval_15m">15 min</option>
                    </select>
                </div>

                <div class="panel-title" style="margin-top: 20px;">⚡ <span data-i18n="presets_title">Quick Presets</span></div>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin-bottom: 15px;">
                    <button onclick="loadPreset('scalping')" style="padding: 8px 5px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); font-size: 11px; white-space: nowrap; font-weight: normal; box-shadow: none;">
                        🔥 <span data-i18n="preset_scalping">Scalping</span>
                    </button>
                    <button onclick="loadPreset('daytrading')" style="padding: 8px 5px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); font-size: 11px; font-weight: normal; box-shadow: none;">
                        📊 <span data-i18n="preset_daytrading">Swing</span>
                    </button>
                    <button onclick="loadPreset('conservative')" style="padding: 8px 5px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); font-size: 11px; font-weight: normal; box-shadow: none;">
                        🛡️ <span data-i18n="preset_conservative">Stable</span>
                    </button>
                </div>

                <div class="panel-title" style="margin-top: 30px;">📈 <span data-i18n="rsi_title">RSI Settings</span></div>

                <div class="form-group">
                    <label data-i18n="label_rsi_period">RSI Period</label>
                    <input type="number" id="rsi_period" value="14" min="5" max="30">
                </div>

                <div class="form-group">
                    <label data-i18n="label_rsi_overbought">Overbought</label>
                    <input type="number" id="rsi_overbought" value="70" min="60" max="90">
                </div>

                <div class="form-group">
                    <label data-i18n="label_rsi_oversold">Oversold</label>
                    <input type="number" id="rsi_oversold" value="30" min="10" max="40">
                </div>

                <div class="panel-title" style="margin-top: 30px;">📉 <span data-i18n="ema_title">EMA Settings</span></div>

                <div class="form-group">
                    <label data-i18n="label_ema_fast">Fast EMA</label>
                    <input type="number" id="ema_fast" value="9" min="3" max="20">
                </div>

                <div class="form-group">
                    <label data-i18n="label_ema_slow">Slow EMA</label>
                    <input type="number" id="ema_slow" value="21" min="10" max="50">
                </div>

                <div class="panel-title" style="margin-top: 30px;">📊 <span data-i18n="macd_title">MACD Settings</span></div>

                <div class="form-group">
                    <label data-i18n="label_macd_fast">MACD Fast</label>
                    <input type="number" id="macd_fast" value="12" min="3" max="20">
                </div>

                <div class="form-group">
                    <label data-i18n="label_macd_slow">MACD Slow</label>
                    <input type="number" id="macd_slow" value="26" min="15" max="40">
                </div>

                <div class="form-group">
                    <label data-i18n="label_macd_signal">MACD Signal</label>
                    <input type="number" id="macd_signal" value="9" min="3" max="15">
                </div>


                <div class="panel-title" style="margin-top: 25px;">🔧 <span data-i18n="advanced_title">Advanced</span></div>

                <button onclick="showSnapshotManager()" style="margin-top: 10px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); box-shadow: none; font-weight: normal;">
                    📸 <span data-i18n="btn_snapshot">Snapshot Manager</span>
                </button>

                <button onclick="showAlertManager()" style="margin-top: 10px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); box-shadow: none; font-weight: normal;">
                    🔔 <span data-i18n="btn_alerts">Alert Settings</span>
                </button>
                </div>
            </div>

            <div class="panel result-panel">
                <div class="panel-title">📊 <span data-i18n="results_title">Analysis Results</span></div>
                <div id="chart-container">
                    <div class="chart-header collapsible-header" onclick="toggleCollapse('chart-content', this)">
                        <div class="chart-title" data-i18n="chart_title">Candlestick Chart</div>
                        <div class="chart-legend" style="pointer-events: none; flex-grow: 1; justify-content: flex-end; margin-right: 15px;">
                            <span><span class="legend-dot" style="background:#f0b90b"></span>EMA Fast</span>
                            <span><span class="legend-dot" style="background:#2962ff"></span>EMA Slow</span>
                            <span><span class="legend-dot" style="background:#ab47bc"></span><span data-i18n="legend_bb">Bollinger</span></span>
                            <span><span class="legend-dot" style="background:#ef4444"></span><span data-i18n="legend_sl">Stop Loss</span></span>
                            <span><span class="legend-dot" style="background:#10b981"></span><span data-i18n="legend_tp">Take Profit</span></span>
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
                        <p data-i18n="hint_start">Click "Analyze Signal" to start analysis</p>
                        <p style="margin-top: 10px; color: #10b981; font-weight: 600;">✨ V3.2: Live Chart + Smart Error Handling + Progress Indicator</p>
                    </div>
                </div>
            </div>
            </div>
        </div>

        <!-- Add Alert Modal -->
        <div id="add-alert-modal" style="display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 10001; align-items: center; justify-content: center; padding: 20px;">
            <div style="background: white; padding: 30px; border-radius: 20px; max-width: 500px; width: 100%;">
                <h3 style="margin-bottom: 20px;">➕ <span data-i18n="modal_alert_title">Add Alert</span></h3>
                
                <div class="form-group">
                    <label data-i18n="label_alert_type">Alert Type</label>
                    <select id="new_alert_type" onchange="updateAlertConditionOptions()">
                        <option value="price" data-i18n="alert_type_price">💰 Price Alert (e.g. BTC above 70000)</option>
                        <option value="quality" data-i18n="alert_type_quality">⭐ Quality Alert (e.g. Score above 4)</option>
                        <option value="signal" data-i18n="alert_type_signal">📊 Signal Alert (e.g. Strong Buy appears)</option>
                    </select>
                </div>

                <div class="form-group">
                    <label data-i18n="label_alert_symbol">Symbol (leave empty for all)</label>
                    <input type="text" id="new_alert_symbol" placeholder="e.g. BTCUSDT" style="text-transform: uppercase;">
                </div>

                <div class="form-group">
                    <label data-i18n="label_alert_condition">Condition</label>
                    <select id="new_alert_condition">
                        <option value="above" data-i18n="condition_above">Above / Greater than</option>
                        <option value="below" data-i18n="condition_below">Below / Less than</option>
                    </select>
                </div>

                <div class="form-group" id="new_alert_value_group">
                    <label id="new_alert_value_label" data-i18n="label_alert_value">Target Value</label>
                    <input type="text" id="new_alert_value" placeholder="Enter trigger value...">
                    <div id="new_alert_value_hint" style="font-size: 11px; color: #666; margin-top: 5px;"></div>
                </div>

                <div style="display: flex; gap: 10px; margin-top: 25px;">
                    <button onclick="submitNewAlert()" style="background: var(--color-buy); flex: 1;">📝 <span data-i18n="btn_save_alert">Save Alert</span></button>
                    <button onclick="document.getElementById('add-alert-modal').style.display='none'" style="background: var(--color-bg); color: var(--color-text-main); border: 1px solid var(--color-border); flex: 1;" data-i18n="btn_cancel">Cancel</button>
                </div>
            </div>
        </div>

        <!-- Add Custom Symbol Modal -->
        <div id="add-symbol-modal" style="display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 10001; align-items: center; justify-content: center; padding: 20px;">
            <div style="background: white; padding: 30px; border-radius: 20px; max-width: 400px; width: 100%;">
                <h3 style="margin-bottom: 20px;">➕ <span data-i18n="modal_symbol_title">Add Custom Symbol</span></h3>
                
                <div class="form-group">
                    <label data-i18n="label_symbol_code">Symbol Code</label>
                    <input type="text" id="new_symbol_code" list="supported-symbols-list" placeholder="e.g. BTCUSDT, DOGE (auto-appends USDT)" style="text-transform: uppercase;">
                    <datalist id="supported-symbols-list"></datalist>
                    <div style="font-size: 11px; color: #666; margin-top: 5px;" data-i18n="hint_symbol_code">Enter full code or search via dropdown. USDT will be appended if missing.</div>
                </div>

                <div class="form-group">
                    <label data-i18n="label_symbol_name">Display Name</label>
                    <input type="text" id="new_symbol_name" placeholder="e.g. DOGE/USDT">
                    <div style="font-size: 11px; color: #666; margin-top: 5px;" data-i18n="hint_symbol_name">Human-readable name shown in the selector.</div>
                </div>

                <div style="display: flex; gap: 10px; margin-top: 25px;">
                    <button onclick="submitNewSymbol()" style="background: var(--color-buy); flex: 1;">✅ <span data-i18n="btn_confirm_add">Confirm Add</span></button>
                    <button onclick="document.getElementById('add-symbol-modal').style.display='none'" style="background: var(--color-bg); color: var(--color-text-main); border: 1px solid var(--color-border); flex: 1;" data-i18n="btn_cancel">Cancel</button>
                </div>
            </div>
        </div>
        <!-- Global Settings Modal -->
        <div id="global-settings-modal" class="global-settings-modal">
            <div class="global-settings-content">
                <h3 style="margin-bottom: 25px; text-align: center; font-size: 20px;">⚙️ <span data-i18n="global_settings_title">Global Settings</span></h3>
                
                <div class="settings-row">
                    <div class="settings-label" data-i18n="refresh_interval">Refresh Interval (s):</div>
                    <div class="settings-control">
                        <input type="number" id="refresh_interval_input" min="2" max="10" value="10" oninput="updateRefreshInterval()">
                    </div>
                </div>

                <div class="settings-row">
                    <div class="settings-label" data-i18n="alert_cooldown">Alert Cooldown:</div>
                    <div class="settings-control">
                        <select id="alert_cooldown_select" onchange="updateAlertCooldown()">
                            <option value="30000" data-i18n="cooldown_30s">30 sec</option>
                            <option value="60000" selected data-i18n="cooldown_1m">1 min</option>
                            <option value="180000" data-i18n="cooldown_3m">3 min</option>
                        </select>
                    </div>
                </div>

                <button onclick="toggleGlobalSettings()" style="width: 100%; margin-top: 15px; padding: 12px; font-size: 16px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main);">
                    <span data-i18n="btn_close">Close</span>
                </button>
            </div>
        </div>

    </div>

    <script>
        const APP_PREFIX = window.APP_PREFIX || '';
        let autoRefreshInterval = null;
        let currentRefreshSeconds = 10;
        let candlestickChart = null;
        let volumeChart = null;
        let lastVisibleRange = null;

        // ===== i18n System =====
        const LANG = {
            en: {
                subtitle: 'Professional Scalping Trading System - Real-time Signal Analysis',
                tag_chart: '📈 Live Chart',
                tag_volume: '✨ Volume Analysis',
                tag_mtf: '📈 Multi-Timeframe',
                tag_sltp: '🎯 Dynamic SL/TP',
                tag_quality: '📊 3D Signal Score',
                tag_notify: '🔔 Browser Alerts',
                tag_snapshot: '📸 Snapshots',
                tag_custom: '➕ Custom Symbols',
                settings_title: 'Settings',
                label_symbol: 'Trading Pair Symbol',
                btn_add_symbol: 'Add Custom Symbol',
                label_interval: 'Interval',
                interval_1m: '1 min',
                interval_3m: '3 min',
                interval_5m: '5 min',
                interval_15m: '15 min',
                presets_title: 'Quick Presets',
                preset_scalping: 'Scalping',
                preset_daytrading: 'Swing',
                preset_conservative: 'Stable',
                rsi_title: 'RSI Settings',
                label_rsi_period: 'RSI Period',
                label_rsi_overbought: 'Overbought',
                label_rsi_oversold: 'Oversold',
                ema_title: 'EMA Settings',
                label_ema_fast: 'Fast EMA',
                label_ema_slow: 'Slow EMA',
                macd_title: 'MACD Settings',
                label_macd_fast: 'MACD Fast',
                label_macd_slow: 'MACD Slow',
                label_macd_signal: 'MACD Signal',
                btn_analyze: 'Analyze Signal',
                auto_refresh: 'Auto-refresh',
                refresh_interval: 'Refresh Interval (s):',
                alert_cooldown: 'Alert Cooldown:',
                cooldown_30s: '30 sec',
                cooldown_1m: '1 min',
                cooldown_3m: '3 min',
                global_settings_title: 'Global Settings',
                btn_close: 'Close',
                advanced_title: 'Advanced',
                btn_snapshot: 'Snapshot Manager',
                btn_alerts: 'Alert Settings',
                results_title: 'Analysis Results',
                chart_title: 'Candlestick Chart',
                legend_bb: 'Bollinger',
                legend_sl: 'Stop Loss',
                legend_tp: 'Take Profit',
                hint_start: 'Click "Analyze Signal" to start analysis',
                modal_alert_title: 'Add Alert',
                label_alert_type: 'Alert Type',
                alert_type_price: '💰 Price Alert (e.g. BTC above 70000)',
                alert_type_quality: '⭐ Quality Alert (e.g. Score above 4)',
                alert_type_signal: '📊 Signal Alert (e.g. Strong Buy appears)',
                label_alert_symbol: 'Symbol (leave empty for all)',
                label_alert_condition: 'Condition',
                condition_above: 'Above / Greater than',
                condition_below: 'Below / Less than',
                label_alert_value: 'Target Value',
                btn_save_alert: 'Save Alert',
                btn_cancel: 'Cancel',
                modal_symbol_title: 'Add Custom Symbol',
                label_symbol_code: 'Symbol Code',
                hint_symbol_code: 'Enter full code or search via dropdown. USDT will be appended if missing.',
                label_symbol_name: 'Display Name',
                hint_symbol_name: 'Human-readable name shown in the selector.',
                btn_confirm_add: 'Confirm Add',
                // --- analyze loading ---
                analyzing: 'Analyzing...',
                step_fetch: 'Fetching Data',
                step_calc: 'Calculating',
                step_suggest: 'Generating',
                network_error: 'Network error, please check connection',
                // --- analysis results ---
                suggested_action: '💡 Suggested Action',
                signal_strength: 'Signal Strength',
                quality: 'Quality',
                quality_score_label: 'Signal Quality Score',
                save_snapshot_btn: '📸 Save Snapshot',
                view_snapshot_btn: '📋 View History',
                detail_section: '🔬 Detailed Analysis',
                // --- MTF ---
                mtf_title: '📈 Multi-Timeframe Confirmation',
                mtf_uptrend: 'Uptrend',
                mtf_downtrend: 'Downtrend',
                mtf_neutral: 'Neutral',
                mtf_timeframe: 'Timeframe',
                mtf_strength: 'Trend Strength',
                // --- Volume ---
                vol_title: '📊 Volume Analysis',
                vol_strong: 'High Volume',
                vol_weak: 'Low Volume',
                vol_normal: 'Normal',
                vol_ratio: 'Vol Ratio',
                vol_cvd: 'CVD Trend',
                vol_cvd_bull: '📈 Bullish',
                vol_cvd_bear: '📉 Bearish',
                vol_current: 'Current Vol',
                // --- SL/TP ---
                sltp_title: '🎯 Suggested SL/TP (ATR-based)',
                sltp_sl: '⛔ Stop Loss',
                sltp_risk: 'Risk',
                sltp_tp1: '🎯 Target 1 (50%)',
                sltp_tp2: '🎯 Target 2 (100%)',
                sltp_reward: 'Reward',
                sltp_atr: '📊 ATR',
                rr_ratio: 'Risk/Reward R:R',
                // --- Indicators ---
                rsi_label: 'RSI Value',
                ema_fast_label: 'Fast EMA',
                ema_slow_label: 'Slow EMA',
                macd_line: 'MACD Line',
                macd_signal_line: 'Signal Line',
                macd_hist: 'Histogram',
                bb_upper: 'Upper Band',
                bb_middle: 'Middle Band',
                bb_lower: 'Lower Band',
                stoch_state: 'State',
                stoch_oversold: 'Oversold',
                stoch_overbought: 'Overbought',
                stoch_neutral: 'Neutral',
                fib_high: '0.0 (High)',
                fib_low: '1.0 (Low)',
                last_updated: 'Last updated',
                // --- 三維評分 + SMC 信號 ---
                tri_score_title: '📊 3D Signal Score',
                tri_trend: 'Trend',
                tri_structure: 'Structure',
                tri_momentum: 'Momentum',
                signal_stage_pre_alert: '⚠️ Pre-Alert',
                signal_stage_confirmed: '✅ Confirmed Signal',
                pre_alert_hint: 'Approaching key structure — no action yet',
                action_pre_alert: '⚠️ Pre-Alert (Observe)',
                signal_type_ob_entry: 'OB Entry',
                signal_type_sweep_confirm: 'Sweep Confirm',
                signal_type_fvg_support: 'FVG Support',
                signal_type_indicator: 'Indicator Confluence',
                sltp_rr: 'R:R',
                // --- action translations (API returns Chinese) ---
                action_strong_buy: '🟢 Strong Buy',
                action_buy: '🟡 Consider Buying',
                action_strong_sell: '🔴 Strong Sell',
                action_sell: '🟠 Consider Selling',
                action_wait: '⏸️ Wait / Observe',
                // --- Snapshot Manager ---
                snap_mgr_title: '📸 Snapshot Manager',
                snap_export: '📥 Export CSV',
                snap_search: '🔍 Search',
                snap_reload: '🔄 Reload',
                snap_loading: 'Loading...',
                snap_empty: 'No snapshots yet',
                snap_close: 'Close',
                snap_delete: '🗑️ Delete',
                snap_time: 'Time',
                snap_price: 'Price',
                snap_sl: 'SL',
                snap_tp: 'TP',
                snap_sltp_title: '📊 Suggested SL/TP',
                snap_stop_loss: 'Stop Loss',
                snap_target1: 'Target 1',
                snap_target2: 'Target 2',
                snap_risk: 'Risk',
                snap_reward: 'Reward',
                snap_no_match: 'No snapshots match the criteria',
                snap_found: 'Found',
                snap_results: 'results',
                snap_saved: 'Snapshot saved! ID: ',
                snap_save_fail: 'Save failed: ',
                snap_deleted: 'Snapshot deleted',
                snap_delete_fail: 'Delete failed',
                snap_load_fail: 'Load failed: ',
                snap_search_fail: 'Search failed: ',
                snap_confirm_delete: 'Delete this snapshot?',
                snap_strength: 'Strength',
                snap_history_title: '📋 Snapshot History',
                // --- Alert Manager ---
                alert_mgr_title: '🔔 Alert Settings',
                alert_add_btn: '➕ Add Alert',
                alert_loading: 'Loading...',
                alert_empty: 'No alerts configured',
                alert_close: 'Close',
                alert_type_price_short: '💰 Price',
                alert_type_quality_short: '⭐ Quality',
                alert_type_signal_short: '📊 Signal',
                alert_above: 'above',
                alert_below: 'below',
                alert_equal: 'equals',
                alert_all_symbols: '(All symbols)',
                alert_enabled: '✅ Enabled',
                alert_disabled: '❌ Disabled',
                alert_triggers: 'Triggers',
                alert_pause: 'Pause',
                alert_enable: 'Enable',
                alert_delete: 'Delete',
                alert_added: 'Alert added!',
                alert_add_fail: 'Add failed: ',
                alert_toggled: 'Alert updated',
                alert_toggle_fail: 'Update failed',
                alert_deleted: 'Alert deleted',
                alert_delete_fail: 'Delete failed',
                alert_load_fail: 'Load failed',
                alert_value_required: '❌ Please enter target value',
                // --- alert condition options (dynamic dropdown) ---
                cond_price_above: 'Above / Higher (Above)',
                cond_price_below: 'Below / Lower (Below)',
                cond_quality_above: 'Above / Equal (>=)',
                cond_quality_below: 'Below / Less than (<)',
                cond_signal_equal: 'Contains Signal (Contains)',
                price_label: 'Target Price',
                price_placeholder: 'e.g. 65000 or 0.52',
                price_hint: 'Triggers when price meets this condition.',
                quality_label: 'Quality Score (0~5)',
                quality_placeholder: 'e.g. 4',
                quality_hint: '0 = weakest, 5⭐ = strongest signal.',
                signal_label: 'Signal Type',
                signal_placeholder: 'e.g. Buy, Sell, Strong Buy',
                signal_hint: 'Triggers when action text contains this keyword.',
                // --- symbol ---
                symbol_added: 'Symbol added!',
                symbol_add_fail: 'Add failed: ',
                symbol_code_required: '❌ Please enter symbol code',
                symbol_name_required: '❌ Please enter display name',
            },
            zh_TW: {
                subtitle: '專業級實時交易信號分析系統',
                tag_chart: '📈 即時圖表',
                tag_volume: '✨ 成交量分析',
                tag_mtf: '📈 多時間框架確認',
                tag_sltp: '🎯 動態止損止盈',
                tag_quality: '📊 三維信號評分',
                tag_notify: '🔔 瀏覽器通知',
                tag_snapshot: '📸 策略快照',
                tag_custom: '➕ 自定義商品',
                settings_title: '交易設定',
                label_symbol: '交易對 Symbol',
                btn_add_symbol: '添加自定義商品',
                label_interval: '時間框架 Interval',
                interval_1m: '1 分鐘',
                interval_3m: '3 分鐘',
                interval_5m: '5 分鐘',
                interval_15m: '15 分鐘',
                presets_title: '快速預設',
                preset_scalping: '超短線',
                preset_daytrading: '短線',
                preset_conservative: '穩健',
                rsi_title: 'RSI 設定',
                label_rsi_period: 'RSI 週期',
                label_rsi_overbought: '超買線',
                label_rsi_oversold: '超賣線',
                ema_title: 'EMA 設定',
                label_ema_fast: '快速 EMA',
                label_ema_slow: '慢速 EMA',
                macd_title: 'MACD 設定',
                label_macd_fast: 'MACD 快線',
                label_macd_slow: 'MACD 慢線',
                label_macd_signal: 'MACD 信號線',
                btn_analyze: '分析入場信號',
                auto_refresh: '自動刷新',
                refresh_interval: '刷新間隔 (秒):',
                alert_cooldown: '警報冷卻時間:',
                cooldown_30s: '30 秒',
                cooldown_1m: '1 分鐘',
                cooldown_3m: '3 分鐘',
                global_settings_title: '全域設定',
                btn_close: '關閉',
                advanced_title: '進階功能',
                btn_snapshot: '快照管理',
                btn_alerts: '警報設定',
                results_title: '分析結果',
                chart_title: 'K 線圖表',
                legend_bb: '布林通道',
                legend_sl: '止損',
                legend_tp: '止盈',
                hint_start: '請點擊「分析入場信號」開始分析',
                modal_alert_title: '新增警報設定',
                label_alert_type: '警報類型',
                alert_type_price: '💰 價格警報 (例如: BTC大於 70000)',
                alert_type_quality: '⭐ 品質評分警報 (例如: 綜合星等大於 4)',
                alert_type_signal: '📊 信號警報 (例如: 出現強烈買入)',
                label_alert_symbol: '指定交易對 (留空則套用所有商品)',
                label_alert_condition: '觸發條件',
                condition_above: '大於 / 高於 (Above)',
                condition_below: '小於 / 低於 (Below)',
                label_alert_value: '目標數值',
                btn_save_alert: '儲存警報',
                btn_cancel: '取消',
                modal_symbol_title: '添加自定義商品',
                label_symbol_code: '交易對代碼 (Symbol)',
                hint_symbol_code: '建議輸入完整代碼，可透過下拉選單搜尋挑選。若未包含 USDT 將嘗試自動補齊。',
                label_symbol_name: '顯示名稱 (Display Name)',
                hint_symbol_name: '在選單中顯示的可讀名稱。',
                btn_confirm_add: '確認添加',
                // --- analyze loading ---
                analyzing: '分析中...',
                step_fetch: '獲取數據',
                step_calc: '計算指標',
                step_suggest: '生成建議',
                network_error: '網路連線失敗，請檢查網路狀態',
                // --- analysis results ---
                suggested_action: '💡 建議操作',
                signal_strength: '信號強度',
                quality: '品質',
                quality_score_label: '信號品質評分',
                save_snapshot_btn: '📸 保存當前策略快照',
                view_snapshot_btn: '📋 查看歷史快照',
                detail_section: '🔬 細部分析結果',
                // --- MTF ---
                mtf_title: '📈 多時間框架確認',
                mtf_uptrend: '上升趨勢',
                mtf_downtrend: '下降趨勢',
                mtf_neutral: '中性',
                mtf_timeframe: '時間框架',
                mtf_strength: '趨勢強度',
                // --- Volume ---
                vol_title: '📊 成交量分析',
                vol_strong: '放量',
                vol_weak: '縮量',
                vol_normal: '正常',
                vol_ratio: '成交量比率',
                vol_cvd: 'CVD 趨勢',
                vol_cvd_bull: '📈 看漲',
                vol_cvd_bear: '📉 看跌',
                vol_current: '當前成交量',
                // --- SL/TP ---
                sltp_title: '🎯 建議止損止盈 (基於 ATR)',
                sltp_sl: '⛔ 止損 Stop Loss',
                sltp_risk: '風險',
                sltp_tp1: '🎯 目標1 (50%)',
                sltp_tp2: '🎯 目標2 (100%)',
                sltp_reward: '報酬',
                sltp_atr: '📊 ATR (波幅)',
                rr_ratio: '風險報酬比 R:R',
                // --- Indicators ---
                rsi_label: 'RSI 值',
                ema_fast_label: '快速 EMA',
                ema_slow_label: '慢速 EMA',
                macd_line: 'MACD 線',
                macd_signal_line: '信號線',
                macd_hist: '柱狀圖',
                bb_upper: '上軌',
                bb_middle: '中軌',
                bb_lower: '下軌',
                stoch_state: '狀態',
                stoch_oversold: '超賣',
                stoch_overbought: '超買',
                stoch_neutral: '中性',
                fib_high: '0.0 (高點)',
                fib_low: '1.0 (低點)',
                last_updated: '最後更新',
                // --- 三維評分 + SMC 信號 ---
                tri_score_title: '📊 三維信號評分',
                tri_trend: '趨勢',
                tri_structure: '結構',
                tri_momentum: '動量',
                signal_stage_pre_alert: '⚠️ 預警',
                signal_stage_confirmed: '✅ 確認信號',
                pre_alert_hint: '接近關鍵結構 — 尚未建議操作',
                action_pre_alert: '⚠️ 預警觀察中',
                signal_type_ob_entry: 'OB 反彈',
                signal_type_sweep_confirm: 'Sweep 確認',
                signal_type_fvg_support: 'FVG 支撐',
                signal_type_indicator: '指標共振',
                sltp_rr: 'R:R',
                // --- action translations ---
                action_strong_buy: '🟢 強烈買入 BUY',
                action_buy: '🟡 考慮買入',
                action_strong_sell: '🔴 強烈賣出 SELL',
                action_sell: '🟠 考慮賣出',
                action_wait: '⏸️ 觀望 WAIT',
                // --- Snapshot Manager ---
                snap_mgr_title: '📸 快照管理器',
                snap_export: '📥 匯出 CSV',
                snap_search: '🔍 搜尋篩選',
                snap_reload: '🔄 重新載入',
                snap_loading: '載入中...',
                snap_empty: '暫無快照記錄',
                snap_close: '關閉',
                snap_delete: '🗑️ 刪除',
                snap_time: '時間',
                snap_price: '價格',
                snap_sl: '止損',
                snap_tp: '止盈',
                snap_sltp_title: '📊 建議止損止盈',
                snap_stop_loss: '止損',
                snap_target1: '目標1',
                snap_target2: '目標2',
                snap_risk: '風險',
                snap_reward: '報酬',
                snap_no_match: '沒有符合條件的快照',
                snap_found: '找到',
                snap_results: '筆結果',
                snap_saved: '策略快照已保存！ID: ',
                snap_save_fail: '保存失敗: ',
                snap_deleted: '快照已刪除',
                snap_delete_fail: '刪除失敗',
                snap_load_fail: '載入失敗: ',
                snap_search_fail: '搜尋失敗: ',
                snap_confirm_delete: '確定要刪除此快照嗎？',
                snap_strength: '強度',
                snap_history_title: '📋 歷史策略快照',
                // --- Alert Manager ---
                alert_mgr_title: '🔔 警報設定',
                alert_add_btn: '➕ 新增警報',
                alert_loading: '載入中...',
                alert_empty: '暫無警報設定',
                alert_close: '關閉',
                alert_type_price_short: '💰 價格',
                alert_type_quality_short: '⭐ 品質',
                alert_type_signal_short: '📊 信號',
                alert_above: '高於',
                alert_below: '低於',
                alert_equal: '等於',
                alert_all_symbols: '(所有商品)',
                alert_enabled: '✅ 啟用',
                alert_disabled: '❌ 停用',
                alert_triggers: '觸發次數',
                alert_pause: '暫停',
                alert_enable: '啟用',
                alert_delete: '刪除',
                alert_added: '警報已新增！',
                alert_add_fail: '新增失敗: ',
                alert_toggled: '警報已更新',
                alert_toggle_fail: '更新失敗',
                alert_deleted: '警報已刪除',
                alert_delete_fail: '刪除失敗',
                alert_load_fail: '載入失敗',
                alert_value_required: '❌ 請輸入目標數值',
                // --- alert condition options (dynamic dropdown) ---
                cond_price_above: '大於 / 高於 (Above)',
                cond_price_below: '小於 / 低於 (Below)',
                cond_quality_above: '大於 / 等於 (>=)',
                cond_quality_below: '小於 / 低於 (<)',
                cond_signal_equal: '包含此信號 (Contains)',
                price_label: '目標價格',
                price_placeholder: '例如: 65000 或者 0.52',
                price_hint: '當商品價格達到此數值條件時觸發通知。',
                quality_label: '品質評分 (0~5)',
                quality_placeholder: '例如: 4',
                quality_hint: '0分最弱，5分(⭐⭐⭐⭐⭐)表示最強烈信號。',
                signal_label: '信號類型',
                signal_placeholder: '例如: 買入, 賣出, 強烈買入',
                signal_hint: '當分析結果的「行動建議」包含此關鍵字時觸發。',
                // --- symbol ---
                symbol_added: '商品已添加！',
                symbol_add_fail: '添加失敗: ',
                symbol_code_required: '❌ 請輸入交易對代碼！',
                symbol_name_required: '❌ 請輸入顯示名稱！',
            }
        };

        let currentLang = localStorage.getItem('app_lang') || 'en';

        function applyLang(lang) {
            currentLang = lang;
            localStorage.setItem('app_lang', lang);
            const dict = LANG[lang] || LANG['en'];
            document.querySelectorAll('[data-i18n]').forEach(el => {
                const key = el.getAttribute('data-i18n');
                if (dict[key] !== undefined) {
                    el.textContent = dict[key];
                }
            });
            // Update html lang attribute
            document.documentElement.lang = lang === 'zh_TW' ? 'zh-TW' : 'en';
            // Update language button styles
            const enBtn = document.getElementById('lang-en-btn');
            const zhBtn = document.getElementById('lang-zh-btn');
            if (enBtn && zhBtn) {
                if (lang === 'en') {
                    enBtn.style.background = 'var(--color-accent)';
                    enBtn.style.color = 'white';
                    enBtn.style.border = 'none';
                    zhBtn.style.background = 'var(--color-bg)';
                    zhBtn.style.color = 'var(--color-text-muted)';
                    zhBtn.style.border = '1px solid var(--color-border)';
                } else {
                    zhBtn.style.background = 'var(--color-accent)';
                    zhBtn.style.color = 'white';
                    zhBtn.style.border = 'none';
                    enBtn.style.background = 'var(--color-bg)';
                    enBtn.style.color = 'var(--color-text-muted)';
                    enBtn.style.border = '1px solid var(--color-border)';
                }
            }
        }

        function switchLang(lang) {
            applyLang(lang);
        }

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
        
        // 頁面加載時恢復靜態狀態與語言
        document.addEventListener('DOMContentLoaded', () => {
            restoreCollapses();
            applyLang(currentLang);
        });

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
                    <p>${LANG[currentLang].analyzing}</p>
                    <div class="progress-steps">
                        <div class="progress-step active"><span class="step-dot"></span>${LANG[currentLang].step_fetch}</div>
                        <div class="progress-step"><span class="step-dot"></span>${LANG[currentLang].step_calc}</div>
                        <div class="progress-step"><span class="step-dot"></span>${LANG[currentLang].step_suggest}</div>
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
                showError(LANG[currentLang].network_error, 'network');
            }
        }

        function displayResults(data) {
            // 保存當前分析數據供快照使用
            currentAnalysisData = data;

            const signals = data.signals;

            // 根據 overall 或 action 字串判斷類型
            const overall = signals.overall || '';
            let actionClass = 'wait';
            if (overall === 'strong_buy' || overall === 'buy') actionClass = 'buy';
            else if (overall === 'strong_sell' || overall === 'sell') actionClass = 'sell';
            else if (overall === 'pre_alert') actionClass = 'pre_alert';

            // 翻譯 action 字串
            function translateAction(action) {
                if (!action) return action;
                if (overall === 'pre_alert') return LANG[currentLang].action_pre_alert;
                if (action.includes('強烈買入') || overall === 'strong_buy') return LANG[currentLang].action_strong_buy;
                if (action.includes('考慮買入') || overall === 'buy') return LANG[currentLang].action_buy;
                if (action.includes('強烈賣出') || overall === 'strong_sell') return LANG[currentLang].action_strong_sell;
                if (action.includes('考慮賣出') || overall === 'sell') return LANG[currentLang].action_sell;
                if (action.includes('觀望') || overall === 'neutral') return LANG[currentLang].action_wait;
                return action;
            }

            // 翻譯信號標籤
            function translateSignalLabel(label) {
                if (!label) return '';
                const map = {
                    'OB 反彈': LANG[currentLang].signal_type_ob_entry,
                    'Sweep 確認': LANG[currentLang].signal_type_sweep_confirm,
                    'FVG 支撐': LANG[currentLang].signal_type_fvg_support,
                    '指標共振': LANG[currentLang].signal_type_indicator
                };
                return map[label] || label;
            }

            const strengthPercent = (signals.strength / 3 * 100).toFixed(0);
            const qualityStars = '⭐'.repeat(Math.round(signals.quality_score));

            // 多時間框架信息
            const mtf = signals.multi_timeframe;
            const mtfHtml = mtf ? `
                <div class="signal-card">
                    <div class="signal-header">
                        <span class="signal-name">${LANG[currentLang].mtf_title} <span class="new-feature-badge">NEW</span></span>
                        <span class="signal-badge ${mtf.trend}">${mtf.trend === 'uptrend' ? LANG[currentLang].mtf_uptrend : (mtf.trend === 'downtrend' ? LANG[currentLang].mtf_downtrend : LANG[currentLang].mtf_neutral)}</span>
                    </div>
                    <div class="signal-details">
                        <div class="detail-item">
                            <div class="detail-label">${LANG[currentLang].mtf_timeframe}</div>
                            <div class="detail-value">${mtf.timeframe}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">${LANG[currentLang].mtf_strength}</div>
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
                        <span class="signal-name">${LANG[currentLang].vol_title} <span class="new-feature-badge">NEW</span></span>
                        <span class="signal-badge ${volume.signal}">${volume.signal === 'strong' ? LANG[currentLang].vol_strong : (volume.signal === 'weak' ? LANG[currentLang].vol_weak : LANG[currentLang].vol_normal)}</span>
                    </div>
                    <div class="signal-details">
                        <div class="detail-item">
                            <div class="detail-label">${LANG[currentLang].vol_ratio}</div>
                            <div class="detail-value">${volume.volume_ratio}x</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">${LANG[currentLang].vol_cvd}</div>
                            <div class="detail-value">${volume.cvd_trend === 'bullish' ? LANG[currentLang].vol_cvd_bull : LANG[currentLang].vol_cvd_bear}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">${LANG[currentLang].vol_current}</div>
                            <div class="detail-value">${volume.current_volume.toLocaleString()}</div>
                        </div>
                    </div>
                </div>
            ` : '';

            // 止損止盈
            const sltp = signals.stop_loss_take_profit;
            const sltpHtml = sltp ? `
                <div class="sl-tp-card">
                    <div class="sl-tp-title">${LANG[currentLang].sltp_title}<span class="new-feature-badge">NEW</span></div>
                    <div class="sl-tp-grid">
                        <div class="sl-tp-item">
                            <div class="sl-tp-label">${LANG[currentLang].sltp_sl}</div>
                            <div class="sl-tp-value stop-loss">$${sltp.stop_loss.toLocaleString()}</div>
                            <div class="detail-label" style="margin-top: 5px;">${LANG[currentLang].sltp_risk}: $${sltp.risk_amount}</div>
                        </div>
                        <div class="sl-tp-item">
                            <div class="sl-tp-label">${LANG[currentLang].sltp_tp1}</div>
                            <div class="sl-tp-value take-profit">$${sltp.take_profit_1.toLocaleString()}</div>
                        </div>
                        <div class="sl-tp-item">
                            <div class="sl-tp-label">${LANG[currentLang].sltp_tp2}</div>
                            <div class="sl-tp-value take-profit">$${sltp.take_profit_2.toLocaleString()}</div>
                            <div class="detail-label" style="margin-top: 5px;">${LANG[currentLang].sltp_reward}: $${sltp.reward_amount}</div>
                        </div>
                        <div class="sl-tp-item">
                            <div class="sl-tp-label">${LANG[currentLang].sltp_atr}</div>
                            <div class="sl-tp-value">$${sltp.atr}</div>
                        </div>
                    </div>
                    <div class="rr-ratio">
                        ${LANG[currentLang].rr_ratio} = 1:${sltp.risk_reward_ratio} ${sltp.risk_reward_ratio >= 2 ? '✅' : (sltp.risk_reward_ratio >= 1.5 ? '🟡' : '⚠️')}
                    </div>
                </div>
            ` : '';

            // 🔔 瀏覽器通知 - 高品質信號時觸發
            if (signals.quality_score >= 4 && (overall === 'strong_buy' || overall === 'strong_sell')) {
                sendNotification(
                    `🚨 ${data.symbol} ${currentLang === 'en' ? 'High Quality Signal!' : '高品質信號！'}`,
                    `${translateAction(signals.action)} | ${currentLang === 'en' ? 'Quality' : '品質'}: ${signals.quality_score}/5 ⭐`,
                    `quality_${data.symbol}`
                );
            }

            // 三維評分 HTML
            const trendScore = signals.trend_score || 0;
            const structureScore = signals.structure_score || 0;
            const momentumScore = signals.momentum_score || 0;
            const signalLabel = signals.signal_label;
            const signalStage = signals.signal_stage;
            const preAlert = signals.pre_alert;

            // 信號標籤 & 預警提示
            const signalLabelHtml = signalLabel ? `<span class="signal-label-badge">${translateSignalLabel(signalLabel)}</span>` : '';
            const preAlertHintHtml = signalStage === 'pre_alert' && preAlert
                ? `<div class="pre-alert-hint">${preAlert.alert_message || LANG[currentLang].pre_alert_hint}</div>`
                : '';
            const stageHtml = signalStage === 'confirmed'
                ? `<div style="margin-top: 6px; font-size: 13px;">${LANG[currentLang].signal_stage_confirmed}</div>`
                : (signalStage === 'pre_alert'
                    ? `<div style="margin-top: 6px; font-size: 13px;">${LANG[currentLang].signal_stage_pre_alert}</div>`
                    : '');

            const html = `
                <!-- 🔥 最重要：建議操作放在最上面 -->
                <div class="action-card ${actionClass}">
                    <div class="action-title">${LANG[currentLang].suggested_action}</div>
                    <div class="action-text">${translateAction(signals.action)}</div>
                    ${signalLabelHtml}
                    ${stageHtml}
                    ${preAlertHintHtml}
                    <div class="strength-bar">
                        <div class="strength-fill" style="width: ${strengthPercent}%"></div>
                    </div>
                    <div style="margin-top: 10px; font-size: 14px;">${LANG[currentLang].signal_strength}: ${signals.strength}/3 | ${LANG[currentLang].quality}: ${signals.quality_score}/5</div>
                </div>

                <!-- 價格與品質評分 -->
                <div class="price-display">
                    <div style="font-size: 14px; opacity: 0.9; margin-bottom: 5px;">${data.symbol}</div>
                    <div class="price-value">$${data.price.toLocaleString()}</div>
                    <div class="quality-score">
                        <div class="quality-score-label">${LANG[currentLang].quality_score_label}</div>
                        <div class="quality-score-value">${signals.quality_score}/5</div>
                        <div class="score-stars">${qualityStars}</div>
                    </div>
                </div>

                <!-- 三維評分進度條 -->
                <div class="tri-score-panel">
                    <div class="tri-score-title">${LANG[currentLang].tri_score_title}</div>
                    <div class="tri-score-row">
                        <span class="tri-score-label">${LANG[currentLang].tri_trend}</span>
                        <div class="tri-score-bar"><div class="tri-score-fill trend" style="width: ${trendScore}%"></div></div>
                        <span class="tri-score-val">${trendScore}</span>
                    </div>
                    <div class="tri-score-row">
                        <span class="tri-score-label">${LANG[currentLang].tri_structure}</span>
                        <div class="tri-score-bar"><div class="tri-score-fill structure" style="width: ${structureScore}%"></div></div>
                        <span class="tri-score-val">${structureScore}</span>
                    </div>
                    <div class="tri-score-row">
                        <span class="tri-score-label">${LANG[currentLang].tri_momentum}</span>
                        <div class="tri-score-bar"><div class="tri-score-fill momentum" style="width: ${momentumScore}%"></div></div>
                        <span class="tri-score-val">${momentumScore}</span>
                    </div>
                </div>

                <!-- 止損止盈 -->
                ${sltpHtml}

                <!-- 📸 快照管理按鈕 -->
                <div style="margin: 20px 0; text-align: center; padding: 15px; background: #f0f4ff; border-radius: 12px;">
                    <button onclick="saveSnapshot()" style="width: auto; padding: 12px 30px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); margin-right: 10px; border-radius: 8px; font-weight: 600; cursor: pointer; box-shadow: none;">
                        ${LANG[currentLang].save_snapshot_btn}
                    </button>
                    <button onclick="showSnapshots()" style="width: auto; padding: 12px 30px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); border-radius: 8px; font-weight: 600; cursor: pointer; box-shadow: none;">
                        ${LANG[currentLang].view_snapshot_btn}
                    </button>
                </div>

                <!-- 核心分析指標 -->
                <div class="panel-title collapsible-header" onclick="toggleCollapse('advanced-analysis-content', this)" style="margin-top: 25px; margin-bottom: 15px;">
                    <span>${LANG[currentLang].detail_section}</span>
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
                            <div class="detail-label">${LANG[currentLang].rsi_label}</div>
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
                            <div class="detail-label">${LANG[currentLang].ema_fast_label}</div>
                            <div class="detail-value">${signals.ema.fast || 'N/A'}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">${LANG[currentLang].ema_slow_label}</div>
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
                            <div class="detail-label">${LANG[currentLang].macd_line}</div>
                            <div class="detail-value">${signals.macd.line || 'N/A'}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">${LANG[currentLang].macd_signal_line}</div>
                            <div class="detail-value">${signals.macd.signal || 'N/A'}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">${LANG[currentLang].macd_hist}</div>
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
                            <div class="detail-label">${LANG[currentLang].bb_upper}</div>
                            <div class="detail-value">${signals.bollinger.upper}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">${LANG[currentLang].bb_middle}</div>
                            <div class="detail-value">${signals.bollinger.middle}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">${LANG[currentLang].bb_lower}</div>
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
                            <div class="detail-label">${LANG[currentLang].stoch_state}</div>
                            <div class="detail-value">${signals.stochastic.k < 20 ? LANG[currentLang].stoch_oversold : (signals.stochastic.k > 80 ? LANG[currentLang].stoch_overbought : LANG[currentLang].stoch_neutral)}</div>
                        </div>
                    </div>
                </div>
                ` : ''}

                </div> <!-- 結束 advanced-analysis-content -->

                <div class="timestamp">
                    ${LANG[currentLang].last_updated}: ${new Date(data.timestamp).toLocaleString()}
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
                autoRefreshInterval = setInterval(analyze, currentRefreshSeconds * 1000);
            } else {
                if (autoRefreshInterval) {
                    clearInterval(autoRefreshInterval);
                    autoRefreshInterval = null;
                }
            }
        }

        function toggleRefreshSettings(event) {
            // Deprecated inline version, kept for fallback if anything was bound.
        }

        function toggleGlobalSettings() {
            const modal = document.getElementById('global-settings-modal');
            modal.classList.toggle('show');
            // Ensure inputs correctly reflect state when opening
            if(modal.classList.contains('show')) {
                document.getElementById('refresh_interval_input').value = currentRefreshSeconds;
            }
        }

        // 點擊外部區域關閉 Global Settings 
        document.getElementById('global-settings-modal').addEventListener('click', function(event) {
            if (event.target === this) {
                this.classList.remove('show');
            }
        });

        function updateRefreshInterval() {
            let val = parseInt(document.getElementById('refresh_interval_input').value);
            if (isNaN(val)) return;
            
            // 限制 2~10 秒
            if (val < 2) val = 2;
            if (val > 10) val = 10;
            
            currentRefreshSeconds = val;
            document.getElementById('refresh_sec_display').textContent = val;

            // 如果目前正在運行自動刷新，立刻重設計時器套用新時間
            const checkbox = document.getElementById('auto_refresh');
            if (checkbox.checked && autoRefreshInterval) {
                clearInterval(autoRefreshInterval);
                autoRefreshInterval = setInterval(analyze, currentRefreshSeconds * 1000);
            }
        }

        // 🔔 瀏覽器通知冷卻機制
        const notificationCooldowns = {};
        let NOTIFICATION_COOLDOWN_MS = 60000; // 預設 1 分鐘

        function updateAlertCooldown() {
            NOTIFICATION_COOLDOWN_MS = parseInt(document.getElementById('alert_cooldown_select').value);
        }

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
                    showToast(LANG[currentLang].snap_saved + result.snapshot_id, 'success');
                } else {
                    showToast(LANG[currentLang].snap_save_fail + result.error, 'error');
                }
            } catch (error) {
                showToast(LANG[currentLang].snap_save_fail + error.message, 'error');
            }
        }

        // 📋 顯示快照列表
        async function showSnapshots() {
            try {
                const response = await fetch(APP_PREFIX + '/api/snapshots?limit=20');
                const result = await response.json();

                if (!result.success || result.snapshots.length === 0) {
                    showToast(LANG[currentLang].snap_empty, 'info');
                    return;
                }

                let html = '<div style="max-height: 500px; overflow-y: auto;">';
                html += `<h3 style="margin-bottom: 15px;">${LANG[currentLang].snap_history_title}</h3>`;

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
                                    <div style="font-size: 12px; color: #666; margin-top: 2px;">${LANG[currentLang].snap_strength}: ${snap.strength}/3</div>
                                </div>
                            </div>
                            ${sltp ? `
                            <div style="background: white; padding: 12px; border-radius: 8px; margin-top: 10px;">
                                <div style="font-size: 13px; font-weight: 600; color: #666; margin-bottom: 8px;">${LANG[currentLang].snap_sltp_title}</div>
                                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; font-size: 12px;">
                                    <div>
                                        <div style="color: #999;">${LANG[currentLang].snap_stop_loss}</div>
                                        <div style="color: #ef4444; font-weight: 600;">$${sltp.stop_loss?.toLocaleString()}</div>
                                    </div>
                                    <div>
                                        <div style="color: #999;">${LANG[currentLang].snap_target1}</div>
                                        <div style="color: #10b981; font-weight: 600;">$${sltp.take_profit_1?.toLocaleString()}</div>
                                    </div>
                                    <div>
                                        <div style="color: #999;">${LANG[currentLang].snap_target2}</div>
                                        <div style="color: #10b981; font-weight: 600;">$${sltp.take_profit_2?.toLocaleString()}</div>
                                    </div>
                                </div>
                                <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #e0e0e0; font-size: 11px; color: #666;">
                                    ${LANG[currentLang].snap_risk}: $${sltp.risk_amount} | ${LANG[currentLang].snap_reward}: $${sltp.reward_amount} | R:R = 1:${sltp.risk_reward_ratio}
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
                        <button onclick="this.closest('div').parentElement.remove()" style="width: 100%; margin-top: 15px; background: var(--color-accent);">${LANG[currentLang].snap_close}</button>
                    </div>
                `;
                document.body.appendChild(modal);
            } catch (error) {
                showToast(LANG[currentLang].snap_load_fail + error.message, 'error');
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
                    <h2 style="margin-bottom: 20px;">${LANG[currentLang].snap_mgr_title}</h2>

                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 20px;">
                        <button onclick="exportSnapshots()" style="padding: 10px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); box-shadow: none; font-weight: normal;">
                            ${LANG[currentLang].snap_export}
                        </button>
                        <button onclick="showSearchDialog()" style="padding: 10px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); box-shadow: none; font-weight: normal;">
                            ${LANG[currentLang].snap_search}
                        </button>
                        <button onclick="loadSnapshotsInModal()" style="padding: 10px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); box-shadow: none; font-weight: normal;">
                            ${LANG[currentLang].snap_reload}
                        </button>
                    </div>

                    <div id="snapshotList" style="min-height: 200px;">
                        <p style="text-align: center; color: #666;">${LANG[currentLang].snap_loading}</p>
                    </div>

                    <button onclick="this.closest('div').parentElement.remove()" style="width: 100%; margin-top: 20px; background: var(--color-accent);">${LANG[currentLang].snap_close}</button>
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
                    listDiv.innerHTML = `<p style="text-align: center; color: #666;">${LANG[currentLang].snap_empty}</p>`;
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
                                    ${LANG[currentLang].snap_delete}
                                </button>
                            </div>
                            <div style="font-size: 12px; color: #666;">
                                ${LANG[currentLang].snap_time}: ${new Date(snapshot.timestamp).toLocaleString()}
                            </div>
                            <div style="font-size: 12px; margin-top: 5px;">
                                ${LANG[currentLang].snap_price}: $${snapshot.price} | ${LANG[currentLang].snap_sl}: $${snapshot.signals.stop_loss_take_profit?.stop_loss} | ${LANG[currentLang].snap_tp}: $${snapshot.signals.stop_loss_take_profit?.take_profit_2}
                            </div>
                        </div>
                    `;
                });

                listDiv.innerHTML = html;
            } catch (error) {
                document.getElementById('snapshotList').innerHTML = `<p style="text-align: center; color: #ef4444;">${LANG[currentLang].snap_load_fail}</p>`;
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
            if (!confirm(LANG[currentLang].snap_confirm_delete)) return;

            try {
                const response = await fetch(APP_PREFIX + '/api/snapshot/' + id, { method: 'DELETE' });
                const result = await response.json();

                if (result.success) {
                    showToast(LANG[currentLang].snap_deleted, 'success');
                    loadSnapshotsInModal();
                } else {
                    showToast(LANG[currentLang].snap_delete_fail, 'error');
                }
            } catch (error) {
                showToast(LANG[currentLang].snap_delete_fail + ': ' + error.message, 'error');
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
                    listDiv.innerHTML = `<p style="text-align: center; color: #666;">${LANG[currentLang].snap_no_match}</p>`;
                    return;
                }

                let html = `<p style="color: #10b981; margin-bottom: 15px;">${LANG[currentLang].snap_found} ${result.snapshots.length} ${LANG[currentLang].snap_results}</p>`;
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
                showToast(LANG[currentLang].snap_search_fail + error.message, 'error');
            }
        }

        // 🔔 警報管理器
        function showAlertManager() {
            const modal = document.createElement('div');
            modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 10000; display: flex; align-items: center; justify-content: center; padding: 20px;';
            modal.innerHTML = `
                <div style="background: white; padding: 30px; border-radius: 20px; max-width: 700px; width: 100%; max-height: 90vh; overflow-y: auto;">
                    <h2 style="margin-bottom: 20px;">${LANG[currentLang].alert_mgr_title}</h2>

                    <button onclick="showAddAlertDialog()" style="width: 100%; margin-bottom: 20px; background: var(--color-bg); border: 1px solid var(--color-border); color: var(--color-text-main); box-shadow: none; font-weight: normal;">
                        ${LANG[currentLang].alert_add_btn}
                    </button>

                    <div id="alertList" style="min-height: 200px;">
                        <p style="text-align: center; color: #666;">${LANG[currentLang].alert_loading}</p>
                    </div>

                    <button onclick="this.closest('div').parentElement.remove()" style="width: 100%; margin-top: 20px; background: var(--color-accent);">${LANG[currentLang].alert_close}</button>
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
                    listDiv.innerHTML = `<p style="text-align: center; color: #666;">${LANG[currentLang].alert_empty}</p>`;
                    return;
                }

                let html = '';
                result.alerts.forEach(alert => {
                    const typeText = alert.type === 'price' ? LANG[currentLang].alert_type_price_short : (alert.type === 'quality' ? LANG[currentLang].alert_type_quality_short : LANG[currentLang].alert_type_signal_short);
                    const condText = alert.condition === 'above' ? LANG[currentLang].alert_above : (alert.condition === 'below' ? LANG[currentLang].alert_below : LANG[currentLang].alert_equal);
                    const status = alert.enabled ? LANG[currentLang].alert_enabled : LANG[currentLang].alert_disabled;

                    html += `
                        <div style="border: 2px solid ${alert.enabled ? 'var(--color-buy)' : '#6b7280'}; border-radius: 10px; padding: 15px; margin-bottom: 15px;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <strong>${typeText}</strong> ${condText} ${alert.value}
                                    ${alert.symbol ? '(' + alert.symbol + ')' : LANG[currentLang].alert_all_symbols}
                                </div>
                                <div style="display: flex; gap: 5px;">
                                    <button onclick="toggleAlert(${alert.id}, ${!alert.enabled})" style="padding: 5px 10px; background: ${alert.enabled ? 'var(--color-warning)' : 'var(--color-buy)'}; font-size: 12px;">
                                        ${alert.enabled ? LANG[currentLang].alert_pause : LANG[currentLang].alert_enable}
                                    </button>
                                    <button onclick="deleteAlert(${alert.id})" style="padding: 5px 10px; background: var(--color-sell); font-size: 12px;">
                                        ${LANG[currentLang].alert_delete}
                                    </button>
                                </div>
                            </div>
                            <div style="font-size: 12px; color: #666; margin-top: 5px;">
                                ${LANG[currentLang].alert_triggers}: ${alert.triggered_count || 0} | ${status}
                            </div>
                        </div>
                    `;
                });

                listDiv.innerHTML = html;
            } catch (error) {
                document.getElementById('alertList').innerHTML = `<p style="text-align: center; color: #ef4444;">${LANG[currentLang].alert_load_fail}</p>`;
            }
        }

        function showAddAlertDialog() {
            document.getElementById('add-alert-modal').style.display = 'flex';
            updateAlertConditionOptions(); // 初始化選項與提示
        }

        function updateAlertConditionOptions() {
            const type = document.getElementById('new_alert_type').value;
            const conditionSelect = document.getElementById('new_alert_condition');
            const valueInput = document.getElementById('new_alert_value');
            const valueLabel = document.getElementById('new_alert_value_label');
            const valueHint = document.getElementById('new_alert_value_hint');

            conditionSelect.innerHTML = '';
            
            if (type === 'price') {
                conditionSelect.innerHTML = `
                    <option value="above">${LANG[currentLang].cond_price_above}</option>
                    <option value="below">${LANG[currentLang].cond_price_below}</option>
                `;
                valueLabel.textContent = LANG[currentLang].price_label;
                valueInput.placeholder = LANG[currentLang].price_placeholder;
                valueInput.type = 'number';
                valueInput.step = 'any';
                valueHint.innerHTML = LANG[currentLang].price_hint;
            } else if (type === 'quality') {
                conditionSelect.innerHTML = `
                    <option value="above">${LANG[currentLang].cond_quality_above}</option>
                    <option value="below">${LANG[currentLang].cond_quality_below}</option>
                `;
                valueLabel.textContent = LANG[currentLang].quality_label;
                valueInput.placeholder = LANG[currentLang].quality_placeholder;
                valueInput.type = 'number';
                valueInput.step = '0.5';
                valueInput.min = '0';
                valueInput.max = '5';
                valueHint.innerHTML = LANG[currentLang].quality_hint;
            } else if (type === 'signal') {
                conditionSelect.innerHTML = `
                    <option value="equal">${LANG[currentLang].cond_signal_equal}</option>
                `;
                valueLabel.textContent = LANG[currentLang].signal_label;
                valueInput.type = 'text';
                valueInput.placeholder = LANG[currentLang].signal_placeholder;
                valueHint.innerHTML = LANG[currentLang].signal_hint;
            }
        }

        function submitNewAlert() {
            const type = document.getElementById('new_alert_type').value;
            const symbol = document.getElementById('new_alert_symbol').value.trim().toUpperCase();
            const condition = document.getElementById('new_alert_condition').value;
            const value = document.getElementById('new_alert_value').value.trim();

            if (!value) {
                alert(LANG[currentLang].alert_value_required);
                return;
            }

            // 關閉 Modal 並發送請求
            document.getElementById('add-alert-modal').style.display = 'none';
            addAlert(type, symbol, condition, value);
            
            // 清空表單
            document.getElementById('new_alert_value').value = '';
            document.getElementById('new_alert_symbol').value = '';
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
                    showToast(LANG[currentLang].alert_added, 'success');
                    loadAlertsInModal();
                } else {
                    showToast(LANG[currentLang].alert_add_fail + result.error, 'error');
                }
            } catch (error) {
                showToast(LANG[currentLang].alert_add_fail + error.message, 'error');
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

        let supportedSymbolsLoaded = false;
        async function showAddSymbolDialog() {
            document.getElementById('add-symbol-modal').style.display = 'flex';
            if (!supportedSymbolsLoaded) {
                try {
                    const response = await fetch(APP_PREFIX + '/api/supported_symbols');
                    const result = await response.json();
                    if (result.success && result.supported_symbols) {
                        const datalist = document.getElementById('supported-symbols-list');
                        datalist.innerHTML = '';
                        result.supported_symbols.forEach(symbol => {
                            const option = document.createElement('option');
                            option.value = symbol;
                            datalist.appendChild(option);
                        });
                        supportedSymbolsLoaded = true;
                    }
                } catch (e) {
                    console.error('Failed to load supported symbols', e);
                }
            }
        }

        function submitNewSymbol() {
            const symbol = document.getElementById('new_symbol_code').value.trim().toUpperCase();
            const name = document.getElementById('new_symbol_name').value.trim();

            if (!symbol) {
                alert('❌ 請輸入交易對代碼！');
                return;
            }
            if (!name) {
                alert('❌ 請輸入顯示名稱！');
                return;
            }

            document.getElementById('add-symbol-modal').style.display = 'none';
            addCustomSymbol(symbol, name);
            
            // 清空表單
            document.getElementById('new_symbol_code').value = '';
            document.getElementById('new_symbol_name').value = '';
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
        print(f"✅ 剝頭皮交易分析器 Pro V{VERSION} 已啟動！")
        print(f"🏠 伺服器地址: http://localhost:{PORT}{PREFIX}")
        print(f"✨ V{VERSION} 更新已就緒")
        print(f"  📈 即時 K 線圖表 (TradingView Lightweight Charts)")
        print(f"  🔄 智能重試機制 (指數退避)")
        print(f"  🌐 中文錯誤訊息 + 錯誤分類")
        print(f"  📊 進度指示器 + Toast 通知")
        print(f"")
        print(f"✨ V3 功能:")
        print(f"  📊 Bollinger Bands | 📉 Stochastic")
        print(f"  📸 策略快照 | ➕ 自定義商品 | 🔔 智能警報")
        print(f"")
        print(f"🚀 支援交易對: BTC, ETH, BNB, SOL + 自定義")
        print(f"\n按 Ctrl+C 停止服務\n")
        httpd.serve_forever()
