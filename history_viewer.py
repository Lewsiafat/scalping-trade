#!/usr/bin/env python3
"""
history_viewer.py — 歷史 K 線瀏覽器
Scalping Trade Analyzer Pro

用法:
    python3 history_viewer.py               # 預設 port 8181
    python3 history_viewer.py --port 9090   # 自訂 port

功能:
    - 載入 history/ 目錄的歷史資料
    - TradingView Lightweight Charts K 線圖
    - 回播功能（逐根播放、速度控制）
    - 快速跳轉到任意位置
    - 顯示成交量
"""

import json
import os
import sys
import ssl
import argparse
import socketserver
import urllib.parse
from http.server import SimpleHTTPRequestHandler
from datetime import datetime

HISTORY_DIR = "history"
DEFAULT_PORT = 8181

# ─── HTML 前端 ────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>歷史 K 線瀏覽器 — Scalping Trade Analyzer</title>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --green: #3fb950;
    --red: #f85149;
    --blue: #58a6ff;
    --yellow: #d29922;
    --accent: #1f6feb;
  }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

  /* ── HEADER ── */
  .header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 8px 16px; display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
  .header h1 { font-size: 14px; font-weight: 600; color: var(--blue); white-space: nowrap; }
  .sep { color: var(--border); }

  select, input[type=range], button {
    background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 4px 8px; font-size: 12px; font-family: inherit; cursor: pointer;
  }
  select:focus, input:focus { outline: none; border-color: var(--accent); }
  button { padding: 5px 14px; transition: background 0.15s; }
  button:hover:not(:disabled) { background: #1c2128; border-color: var(--blue); }
  button:disabled { opacity: 0.4; cursor: not-allowed; }
  button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  button.primary:hover:not(:disabled) { background: #388bfd; }
  button.danger { background: #b91c1c; border-color: #b91c1c; color: #fff; }

  .header-right { margin-left: auto; display: flex; align-items: center; gap: 8px; }
  .stat { color: var(--muted); font-size: 11px; white-space: nowrap; }
  .stat span { color: var(--text); font-weight: 600; }

  /* ── TOOLBAR ── */
  .toolbar { background: var(--surface); border-bottom: 1px solid var(--border); padding: 6px 16px; display: flex; align-items: center; gap: 10px; flex-shrink: 0; flex-wrap: wrap; }
  .toolbar label { color: var(--muted); font-size: 11px; }

  /* ── MAIN ── */
  .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  #chart-container { flex: 1; position: relative; min-height: 0; }
  #volume-container { height: 100px; flex-shrink: 0; position: relative; }

  /* ── REPLAY BAR ── */
  .replay-bar {
    background: var(--surface); border-top: 1px solid var(--border);
    padding: 8px 16px; display: flex; align-items: center; gap: 10px; flex-shrink: 0;
  }
  .replay-controls { display: flex; gap: 6px; align-items: center; }
  .replay-controls button { padding: 4px 10px; font-size: 18px; min-width: 36px; }
  .timeline-wrap { flex: 1; display: flex; align-items: center; gap: 8px; }
  #timeline { flex: 1; accent-color: var(--blue); }
  .bar-info { color: var(--muted); font-size: 11px; white-space: nowrap; min-width: 180px; }
  .bar-info span { color: var(--text); }
  .speed-wrap { display: flex; align-items: center; gap: 6px; color: var(--muted); font-size: 11px; }
  #speed-display { color: var(--blue); font-weight: 700; min-width: 32px; }

  /* ── OHLCV INFO ── */
  .ohlcv { display: flex; gap: 14px; align-items: center; padding: 4px 16px; background: #0d1117bb; font-size: 11px; flex-shrink: 0; }
  .ohlcv .lbl { color: var(--muted); }
  .ohlcv .val { font-weight: 600; font-variant-numeric: tabular-nums; }
  .up { color: var(--green); }
  .dn { color: var(--red); }

  /* ── STATUS ── */
  #status { color: var(--muted); font-size: 11px; padding: 4px 16px; flex-shrink: 0; min-height: 20px; }

  /* ── LOADING ── */
  #loading { position: fixed; inset: 0; background: #0d1117ee; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; z-index: 100; }
  #loading.hidden { display: none; }
  .spinner { width: 36px; height: 36px; border: 3px solid var(--border); border-top-color: var(--blue); border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  #loading p { color: var(--muted); font-size: 12px; }
</style>
</head>
<body>

<!-- Loading -->
<div id="loading">
  <div class="spinner"></div>
  <p id="loading-msg">載入歷史資料中...</p>
</div>

<!-- Header -->
<div class="header">
  <h1>📈 歷史 K 線瀏覽器</h1>
  <span class="sep">|</span>
  <label style="color:var(--muted);font-size:11px">資料集</label>
  <select id="file-select" style="min-width:260px"></select>
  <button class="primary" onclick="loadSelected()">載入</button>
  <div class="header-right">
    <div class="stat">總 K 線 <span id="stat-total">—</span></div>
    <div class="stat">期間 <span id="stat-range">—</span></div>
  </div>
</div>

<!-- OHLCV info bar -->
<div class="ohlcv" id="ohlcv-bar">
  <span class="lbl">O</span><span class="val" id="o-val">—</span>
  <span class="lbl">H</span><span class="val" id="h-val">—</span>
  <span class="lbl">L</span><span class="val" id="l-val">—</span>
  <span class="lbl">C</span><span class="val" id="c-val">—</span>
  <span class="lbl">Vol</span><span class="val" id="v-val">—</span>
  <span class="lbl" style="margin-left:8px">時間</span><span class="val" id="t-val">—</span>
</div>

<!-- Charts -->
<div class="main">
  <div id="chart-container"></div>
  <div id="volume-container"></div>
</div>

<!-- Replay bar -->
<div class="replay-bar">
  <div class="replay-controls">
    <button onclick="stepBack()" title="上一根" id="btn-back">◀</button>
    <button onclick="togglePlay()" title="播放/暫停" id="btn-play">▶</button>
    <button onclick="stepForward()" title="下一根" id="btn-forward">▶|</button>
    <button onclick="resetReplay()" title="重置" id="btn-reset">⏮</button>
  </div>

  <div class="timeline-wrap">
    <input type="range" id="timeline" min="0" value="0" oninput="seekTo(this.value)" />
    <div class="bar-info">
      Bar <span id="bar-cur">0</span> / <span id="bar-total">0</span>
      &nbsp;·&nbsp; <span id="bar-time">—</span>
    </div>
  </div>

  <div class="speed-wrap">
    速度
    <button onclick="changeSpeed(-1)">−</button>
    <span id="speed-display">1×</span>
    <button onclick="changeSpeed(1)">+</button>
  </div>

  <div style="display:flex;gap:6px;align-items:center">
    <label style="color:var(--muted);font-size:11px">顯示</label>
    <select id="view-mode" onchange="applyViewMode()">
      <option value="replay">回播模式</option>
      <option value="full">全部顯示</option>
    </select>
  </div>
</div>

<div id="status">請選擇資料集並按「載入」</div>

<script>
// ─── STATE ───────────────────────────────────────────────────────────────────
let allKlines = [];
let displayCount = 0;
let isPlaying = false;
let playTimer = null;
let currentBar = 0;
let windowSize = 150; // 回播窗口大小

const SPEEDS = [0.5, 1, 2, 5, 10, 30, 60];
let speedIdx = 1; // default 1×

// ─── CHARTS ──────────────────────────────────────────────────────────────────
const chartOptions = {
  layout: { background: { color: '#0d1117' }, textColor: '#8b949e' },
  grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
  crosshair: { mode: 1 },
  rightPriceScale: { borderColor: '#30363d', scaleMargins: { top: 0.05, bottom: 0.05 } },
  timeScale: { borderColor: '#30363d', timeVisible: true, secondsVisible: false },
};

const chart = LightweightCharts.createChart(document.getElementById('chart-container'), {
  ...chartOptions, width: 0, height: 0,
  rightPriceScale: { ...chartOptions.rightPriceScale },
});

const volChart = LightweightCharts.createChart(document.getElementById('volume-container'), {
  ...chartOptions, width: 0, height: 100,
  rightPriceScale: { ...chartOptions.rightPriceScale, scaleMargins: { top: 0.1, bottom: 0 } },
  timeScale: { visible: false },
  leftPriceScale: { visible: false },
});

const candleSeries = chart.addCandlestickSeries({
  upColor: '#3fb950', downColor: '#f85149',
  borderUpColor: '#3fb950', borderDownColor: '#f85149',
  wickUpColor: '#3fb950', wickDownColor: '#f85149',
});

const volSeries = volChart.addHistogramSeries({
  color: '#58a6ff', priceFormat: { type: 'volume' },
  priceScaleId: 'vol',
});
volChart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });

// Sync time scales
chart.timeScale().subscribeVisibleTimeRangeChange(() => {
  const range = chart.timeScale().getVisibleRange();
  if (range) volChart.timeScale().setVisibleRange(range);
});

// Crosshair sync
chart.subscribeCrosshairMove(param => {
  if (!param || !param.time) return;
  const idx = allKlines.findIndex(k => Math.floor(k[0] / 1000) === param.time);
  if (idx >= 0) updateOhlcv(idx);
});

// Resize
function resizeCharts() {
  const cc = document.getElementById('chart-container');
  const vc = document.getElementById('volume-container');
  chart.resize(cc.clientWidth, cc.clientHeight);
  volChart.resize(vc.clientWidth, vc.clientHeight);
}
const ro = new ResizeObserver(resizeCharts);
ro.observe(document.getElementById('chart-container'));
ro.observe(document.getElementById('volume-container'));

// ─── DATA LOADING ────────────────────────────────────────────────────────────
async function loadFileList() {
  try {
    const res = await fetch('/api/history/list');
    const files = await res.json();
    const sel = document.getElementById('file-select');
    sel.innerHTML = '';
    if (!files.length) {
      sel.innerHTML = '<option disabled>尚無歷史資料，請先執行 data_fetcher.py</option>';
      return;
    }
    files.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f.filename;
      opt.textContent = `${f.filename}  (${(f.bars || 0).toLocaleString()} bars, ${(f.size_kb || 0).toFixed(0)} KB)`;
      sel.appendChild(opt);
    });
    status('已載入 ' + files.length + ' 個資料集');
  } catch (e) {
    status('❌ 無法載入資料集列表: ' + e.message);
  }
}

async function loadSelected() {
  const sel = document.getElementById('file-select');
  if (!sel.value) return;
  showLoading('載入 ' + sel.value + ' ...');
  try {
    const res = await fetch('/api/history/load?file=' + encodeURIComponent(sel.value));
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    allKlines = data.klines || [];
    if (!allKlines.length) throw new Error('資料為空');

    document.getElementById('stat-total').textContent = allKlines.length.toLocaleString();
    const t0 = fmtTime(allKlines[0][0]);
    const t1 = fmtTime(allKlines[allKlines.length - 1][0]);
    document.getElementById('stat-range').textContent = `${t0} ~ ${t1}`;

    document.getElementById('timeline').max = allKlines.length - 1;
    document.getElementById('bar-total').textContent = allKlines.length.toLocaleString();

    stopPlay();
    currentBar = Math.min(windowSize, allKlines.length) - 1;
    applyViewMode();
    status('✅ 載入完成 — ' + allKlines.length.toLocaleString() + ' 根 K 線');
  } catch (e) {
    status('❌ 載入失敗: ' + e.message);
  } finally {
    hideLoading();
  }
}

// ─── CHART RENDERING ─────────────────────────────────────────────────────────
function buildCandles(klines) {
  return klines.map(k => ({
    time: Math.floor(k[0] / 1000),
    open: parseFloat(k[1]),
    high: parseFloat(k[2]),
    low:  parseFloat(k[3]),
    close: parseFloat(k[4]),
  }));
}

function buildVolumes(klines) {
  return klines.map((k, i) => ({
    time: Math.floor(k[0] / 1000),
    value: parseFloat(k[5]),
    color: parseFloat(k[4]) >= parseFloat(k[1]) ? '#2ea04344' : '#f8514944',
  }));
}

function renderBars(upTo) {
  const slice = allKlines.slice(0, upTo + 1);
  const candles = buildCandles(slice);
  const volumes = buildVolumes(slice);
  candleSeries.setData(candles);
  volSeries.setData(volumes);

  // Scroll to latest
  if (candles.length > 0) {
    chart.timeScale().scrollToPosition(0, false);
    chart.timeScale().fitContent();
    volChart.timeScale().fitContent();
  }

  updateOhlcv(upTo);
  updateSeekBar(upTo);
}

function applyViewMode() {
  const mode = document.getElementById('view-mode').value;
  if (mode === 'full') {
    if (allKlines.length) renderBars(allKlines.length - 1);
  } else {
    resetReplay();
  }
}

// ─── OHLCV INFO ──────────────────────────────────────────────────────────────
function updateOhlcv(idx) {
  if (!allKlines[idx]) return;
  const k = allKlines[idx];
  const o = parseFloat(k[1]), h = parseFloat(k[2]);
  const l = parseFloat(k[3]), c = parseFloat(k[4]);
  const v = parseFloat(k[5]);
  const up = c >= o;

  const fmt = n => n.toFixed(n >= 100 ? 2 : n >= 1 ? 4 : 6);
  document.getElementById('o-val').textContent = fmt(o);
  document.getElementById('h-val').className = 'val up';
  document.getElementById('h-val').textContent = fmt(h);
  document.getElementById('l-val').className = 'val dn';
  document.getElementById('l-val').textContent = fmt(l);
  document.getElementById('c-val').className = 'val ' + (up ? 'up' : 'dn');
  document.getElementById('c-val').textContent = fmt(c);
  document.getElementById('v-val').textContent = v >= 1e6 ? (v / 1e6).toFixed(2) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(1) + 'K' : v.toFixed(1);
  document.getElementById('t-val').textContent = fmtTime(k[0]);
}

// ─── REPLAY CONTROLS ─────────────────────────────────────────────────────────
function togglePlay() {
  isPlaying ? stopPlay() : startPlay();
}

function startPlay() {
  if (!allKlines.length) return;
  isPlaying = true;
  document.getElementById('btn-play').textContent = '⏸';
  scheduleNext();
}

function stopPlay() {
  isPlaying = false;
  if (playTimer) { clearTimeout(playTimer); playTimer = null; }
  document.getElementById('btn-play').textContent = '▶';
}

function scheduleNext() {
  if (!isPlaying) return;
  const speed = SPEEDS[speedIdx];
  const delay = Math.max(16, 1000 / speed);
  playTimer = setTimeout(() => {
    if (currentBar < allKlines.length - 1) {
      currentBar++;
      renderBars(currentBar);
      scheduleNext();
    } else {
      stopPlay();
      status('▶ 回播完畢');
    }
  }, delay);
}

function stepForward() {
  stopPlay();
  if (currentBar < allKlines.length - 1) {
    currentBar++;
    renderBars(currentBar);
  }
}

function stepBack() {
  stopPlay();
  if (currentBar > 0) {
    currentBar--;
    renderBars(currentBar);
  }
}

function resetReplay() {
  stopPlay();
  currentBar = Math.min(windowSize - 1, allKlines.length - 1);
  if (allKlines.length) renderBars(currentBar);
}

function seekTo(val) {
  stopPlay();
  currentBar = parseInt(val);
  if (allKlines.length) renderBars(currentBar);
}

function changeSpeed(dir) {
  speedIdx = Math.max(0, Math.min(SPEEDS.length - 1, speedIdx + dir));
  const s = SPEEDS[speedIdx];
  document.getElementById('speed-display').textContent = s >= 1 ? s + '×' : s + '×';
}

function updateSeekBar(idx) {
  document.getElementById('timeline').value = idx;
  document.getElementById('bar-cur').textContent = (idx + 1).toLocaleString();
  const k = allKlines[idx];
  if (k) document.getElementById('bar-time').textContent = fmtTime(k[0]);
}

// ─── UTILS ───────────────────────────────────────────────────────────────────
function fmtTime(ms) {
  const d = new Date(ms);
  return d.toISOString().replace('T', ' ').slice(0, 16);
}

function status(msg) {
  document.getElementById('status').textContent = msg;
}

function showLoading(msg) {
  document.getElementById('loading-msg').textContent = msg || '載入中...';
  document.getElementById('loading').classList.remove('hidden');
}

function hideLoading() {
  document.getElementById('loading').classList.add('hidden');
}

// ─── KEYBOARD ────────────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  switch (e.key) {
    case ' ': e.preventDefault(); togglePlay(); break;
    case 'ArrowRight': e.preventDefault(); stepForward(); break;
    case 'ArrowLeft':  e.preventDefault(); stepBack(); break;
    case 'Home': e.preventDefault(); resetReplay(); break;
    case 'End': e.preventDefault();
      stopPlay(); currentBar = allKlines.length - 1;
      if (allKlines.length) renderBars(currentBar); break;
  }
});

// ─── INIT ─────────────────────────────────────────────────────────────────────
loadFileList().then(hideLoading);
</script>
</body>
</html>"""


# ─── HTTP Handler ─────────────────────────────────────────────────────────────

class ViewerHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 靜音 access log

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "":
            self._send_html(HTML)

        elif path == "/api/history/list":
            self._send_json(self._list_history())

        elif path == "/api/history/load":
            fname = params.get("file", [""])[0]
            self._send_json(self._load_file(fname))

        else:
            self.send_error(404, "Not Found")

    def _list_history(self):
        result = []
        if not os.path.exists(HISTORY_DIR):
            return result
        for fname in sorted(os.listdir(HISTORY_DIR)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(HISTORY_DIR, fname)
            size_kb = os.path.getsize(fpath) / 1024
            bars = 0
            try:
                with open(fpath, "r") as f:
                    meta = json.load(f)
                    bars = meta.get("total_bars", len(meta.get("klines", [])))
            except Exception:
                pass
            result.append({"filename": fname, "bars": bars, "size_kb": round(size_kb, 1)})
        return result

    def _load_file(self, fname: str):
        if not fname or ".." in fname or "/" in fname:
            return {"error": "無效檔名"}
        fpath = os.path.join(HISTORY_DIR, fname)
        if not os.path.exists(fpath):
            return {"error": f"找不到檔案: {fname}"}
        try:
            with open(fpath, "r") as f:
                return json.load(f)
        except Exception as e:
            return {"error": str(e)}

    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="歷史 K 線瀏覽器")
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", args.port), ViewerHandler) as httpd:
        print(f"📈 歷史 K 線瀏覽器")
        print(f"   http://localhost:{args.port}")
        print(f"   history/ 目錄: {os.path.abspath(HISTORY_DIR)}")
        print(f"   按 Ctrl+C 停止")
        print()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")


if __name__ == "__main__":
    main()
