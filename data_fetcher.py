#!/usr/bin/env python3
"""
data_fetcher.py — 歷史 K 線資料爬取先導程式
Scalping Trade Analyzer Pro

用法:
    python3 data_fetcher.py                          # 預設: BTCUSDT 最近30天
    python3 data_fetcher.py -s ETHUSDT -d 60         # ETH 最近60天
    python3 data_fetcher.py -s BTCUSDT -d 30 --dry-run  # 試跑不儲存

功能:
    - 分批請求 Binance K 線（每次 1000 根，自動分頁）
    - 智慧 Rate Limiting（避免被 Binance ban）
    - 進度顯示
    - 資料存至 history/{symbol}_5m_{YYYYMMDD}_{YYYYMMDD}.json
"""

import json
import os
import sys
import time
import ssl
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ─── 設定 ──────────────────────────────────────────────────────────────────────

BINANCE_HOSTS = [
    "https://api.binance.com/api/v3",     # 主節點
    "https://api1.binance.com/api/v3",    # 備用 1
    "https://api2.binance.com/api/v3",    # 備用 2
    "https://api3.binance.com/api/v3",    # 備用 3
    "https://api4.binance.com/api/v3",    # 備用 4
]
BINANCE_API   = BINANCE_HOSTS[0]         # 目前使用節點（自動切換）
INTERVAL      = "5m"
LIMIT_PER_REQ = 1000          # Binance 每次最多 1000 根
DELAY_BETWEEN = 0.4           # 每次請求間隔秒數（安全值，避免 ban）
MAX_RETRIES   = 5
RETRY_DELAY   = 2.0           # 429/5xx 重試等待秒數（指數退避）
HISTORY_DIR   = "history"

_current_host_idx = 0         # 節點輪替索引

# SSL context（與主程式一致）
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode    = ssl.CERT_NONE


# ─── 工具函式 ──────────────────────────────────────────────────────────────────

def log(msg: str, end="\n"):
    """輸出帶時間戳的訊息"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", end=end, flush=True)


def ms_to_dt(ms: int) -> str:
    """毫秒時間戳 → 可讀字串"""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def progress_bar(current: int, total: int, width: int = 40) -> str:
    """ASCII 進度條"""
    pct   = current / total if total > 0 else 0
    filled = int(width * pct)
    bar   = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct*100:.1f}% ({current:,}/{total:,})"


# ─── Binance 請求 ──────────────────────────────────────────────────────────────

def _next_host():
    """切換到下一個備用節點"""
    global _current_host_idx
    _current_host_idx = (_current_host_idx + 1) % len(BINANCE_HOSTS)
    host = BINANCE_HOSTS[_current_host_idx]
    log(f"🔄 切換節點 → {host}")
    return host


def fetch_klines(symbol: str, start_ms: int, end_ms: int) -> list:
    """
    取得指定時間範圍的 K 線（一次最多 1000 根）
    回傳原始 Binance kline 陣列
    403 時自動切換備用節點
    """
    global _current_host_idx
    base = BINANCE_HOSTS[_current_host_idx]

    qs = f"?symbol={symbol}&interval={INTERVAL}&startTime={start_ms}&endTime={end_ms}&limit={LIMIT_PER_REQ}"

    for attempt in range(1, MAX_RETRIES + 1):
        url = f"{base}/klines{qs}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=_ctx, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                if not isinstance(data, list):
                    raise ValueError(f"非預期回應格式: {data}")
                return data

        except urllib.error.HTTPError as e:
            if e.code == 429:  # Rate limit
                wait = RETRY_DELAY * (2 ** attempt)
                log(f"⚠️  Rate limit (429), 等待 {wait:.0f}s ...")
                time.sleep(wait)
            elif e.code == 403:  # Geo-block，換節點
                log(f"⚠️  HTTP 403 (地區限制)，切換節點 {attempt}/{len(BINANCE_HOSTS)} ...")
                base = _next_host()
                time.sleep(0.5)
            elif e.code == 400:
                log(f"❌ 請求錯誤 (400): {e.read().decode()}")
                raise
            else:
                log(f"⚠️  HTTP {e.code}, 重試 {attempt}/{MAX_RETRIES} ...")
                time.sleep(RETRY_DELAY * attempt)

        except Exception as e:
            log(f"⚠️  請求失敗: {e}, 重試 {attempt}/{MAX_RETRIES} ...")
            time.sleep(RETRY_DELAY * attempt)

    raise RuntimeError(f"所有節點均失敗，超過最大重試次數 ({MAX_RETRIES})")


# ─── 主要爬取邏輯 ──────────────────────────────────────────────────────────────

def fetch_history(symbol: str, days: int, dry_run: bool = False) -> dict:
    """
    爬取指定交易對最近 N 天的 5m K 線

    回傳:
        {
            "symbol": "BTCUSDT",
            "interval": "5m",
            "start_time": "2026-02-27 00:00",
            "end_time":   "2026-03-29 00:00",
            "total_bars": 8640,
            "fetched_at": "2026-03-29T07:30:00Z",
            "klines": [ [open_time, open, high, low, close, volume, ...], ... ]
        }
    """
    now_ms    = int(time.time() * 1000)
    start_ms  = now_ms - days * 24 * 3600 * 1000
    end_ms    = now_ms

    # 估算 bar 數量
    bar_ms      = 5 * 60 * 1000  # 5 分鐘 in ms
    total_est   = (end_ms - start_ms) // bar_ms
    total_reqs  = (total_est + LIMIT_PER_REQ - 1) // LIMIT_PER_REQ

    log(f"📊 {symbol} {INTERVAL} | 最近 {days} 天")
    log(f"   從 {ms_to_dt(start_ms)}  到 {ms_to_dt(end_ms)}")
    log(f"   預估 {total_est:,} 根 K 線，需 {total_reqs} 次請求")
    log(f"   延遲 {DELAY_BETWEEN}s/請求，預計 {total_reqs * DELAY_BETWEEN:.0f}s")

    if dry_run:
        log("🔍 Dry-run 模式，跳過實際請求")
        return {}

    all_klines = []
    cur_start  = start_ms
    req_count  = 0
    last_open  = -1

    log("")
    while cur_start < end_ms:
        batch = fetch_klines(symbol, cur_start, end_ms)
        if not batch:
            break

        # 去重：只加 open_time 比 last_open 大的
        new_bars = [k for k in batch if k[0] > last_open]
        if not new_bars:
            break

        all_klines.extend(new_bars)
        last_open  = new_bars[-1][0]
        cur_start  = last_open + bar_ms   # 下一批從最後一根的下一根開始
        req_count += 1

        # 進度
        pct_done = min(100, (last_open - start_ms) / (end_ms - start_ms) * 100)
        bar_str  = progress_bar(len(all_klines), total_est)
        print(f"\r   {bar_str}  req#{req_count}", end="", flush=True)

        if len(batch) < LIMIT_PER_REQ:
            break  # 最後一批

        time.sleep(DELAY_BETWEEN)

    print()  # 換行
    log(f"✅ 共爬取 {len(all_klines):,} 根 K 線（{req_count} 次請求）")

    return {
        "symbol":     symbol,
        "interval":   INTERVAL,
        "start_time": ms_to_dt(start_ms),
        "end_time":   ms_to_dt(end_ms),
        "days":       days,
        "total_bars": len(all_klines),
        "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
        "klines":     all_klines,
    }


def save_history(data: dict, symbol: str, days: int):
    """儲存至 history/ 目錄"""
    os.makedirs(HISTORY_DIR, exist_ok=True)

    today   = datetime.now().strftime("%Y%m%d")
    start_d = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    fname   = f"{symbol}_{INTERVAL}_{start_d}_{today}.json"
    fpath   = os.path.join(HISTORY_DIR, fname)

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))

    size_kb = os.path.getsize(fpath) / 1024
    log(f"💾 已儲存至 {fpath}（{size_kb:.0f} KB）")
    return fpath


def list_history():
    """列出已有的歷史資料檔案"""
    if not os.path.exists(HISTORY_DIR):
        log("⚠️  history/ 目錄不存在，尚無歷史資料")
        return

    files = sorted([f for f in os.listdir(HISTORY_DIR) if f.endswith(".json")])
    if not files:
        log("⚠️  history/ 目錄為空")
        return

    log(f"📂 歷史資料檔案（{len(files)} 個）：")
    for f in files:
        fpath   = os.path.join(HISTORY_DIR, f)
        size_kb = os.path.getsize(fpath) / 1024
        try:
            with open(fpath, "r") as fp:
                meta = json.load(fp)
            bars = meta.get("total_bars", "?")
            log(f"   {f}  ({bars:,} bars, {size_kb:.0f} KB)")
        except Exception:
            log(f"   {f}  ({size_kb:.0f} KB)")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scalping Trade Analyzer — 歷史 K 線資料爬取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python3 data_fetcher.py                        # BTCUSDT 最近 30 天
  python3 data_fetcher.py -s ETHUSDT -d 60       # ETHUSDT 最近 60 天
  python3 data_fetcher.py -s SOLUSDT -d 14       # SOLUSDT 最近 14 天
  python3 data_fetcher.py --list                 # 列出已下載的檔案
  python3 data_fetcher.py -s BTCUSDT --dry-run   # 試跑（不下載）
        """
    )
    parser.add_argument("-s", "--symbol", default="BTCUSDT",
                        help="交易對（預設: BTCUSDT）")
    parser.add_argument("-d", "--days", type=int, default=30,
                        help="爬取最近幾天（預設: 30）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只顯示預估資訊，不實際下載")
    parser.add_argument("--list", action="store_true",
                        help="列出已有的歷史資料檔案")

    args = parser.parse_args()

    if args.list:
        list_history()
        return

    symbol = args.symbol.upper()

    log(f"🚀 開始爬取歷史資料")
    log(f"   Rate limiting: {DELAY_BETWEEN}s 間隔，最大重試 {MAX_RETRIES} 次")
    log("")

    data = fetch_history(symbol, args.days, dry_run=args.dry_run)

    if not args.dry_run and data:
        save_history(data, symbol, args.days)
        log("")
        log("✨ 完成！使用 python3 history_viewer.py 開啟瀏覽器查看")


if __name__ == "__main__":
    main()
