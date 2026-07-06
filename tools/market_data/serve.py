"""
K 線檢視 UI 的本機伺服器（含線上下載）
=====================================
用 TradingView 官方開源的 Lightweight Charts 呈現日K CSV，
並可直接在網頁上觸發下載（後端跑 download.py 的邏輯），下載完即時顯示。

用法：
    python serve.py            # 啟動並自動開瀏覽器
    python serve.py --port 8800 --no-open

端點：
    GET  /                          → K 線頁面
    GET  /api/symbols               → 已下載、可檢視的商品
    GET  /api/instruments           → 全部支援商品（含是否已下載）
    GET  /api/data?symbol=KEY       → 該商品 OHLCV（給圖表）
    POST /api/download {symbol,start}→ 啟動下載，回 job_id
    GET  /api/download_status?job=ID→ 下載進度/結果
"""

import io
import csv
import json
import uuid
import argparse
import threading
import contextlib
import webbrowser
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import symbols
import download as dl   # 重用 fetch_one / DATA_DIR / _TV_FALLBACK

BASE = Path(__file__).parent
DATA = BASE / 'data'
WEB = BASE / 'web'

# ---- 下載 job 狀態 ----
JOBS: dict[str, dict] = {}
JOB_LOCK = threading.Lock()   # 一次只跑一個下載，避免 stdout 重導互相干擾


class _LogStream(io.TextIOBase):
    """把下載過程的 print 收進 job['log']。"""
    def __init__(self, job):
        self.job = job

    def write(self, s):
        s = s.strip()
        if s:
            self.job['log'].append(s)
            self.job['last'] = s
        return len(s)


def _run_download(job, key, start):
    job['state'] = 'queued'
    with JOB_LOCK:
        job['state'] = 'running'
        try:
            inst = symbols.REGISTRY[key]
            with contextlib.redirect_stdout(_LogStream(job)):
                df = dl.fetch_one(inst, start, None)
            if df is None or len(df) == 0:
                job['state'] = 'error'
                job['last'] = '無資料（來源可能無此商品或該區間無交易）'
                return
            DATA.mkdir(exist_ok=True)
            out = DATA / f'{key}_1d.csv'
            df.to_csv(out, index=False, encoding='utf-8')
            job['result'] = {'key': key, 'rows': len(df),
                             'start': df['Date'].iloc[0], 'end': df['Date'].iloc[-1]}
            job['state'] = 'done'
            job['last'] = f"完成：{len(df)} 根K棒（{df['Date'].iloc[0]} → {df['Date'].iloc[-1]}）"
        except Exception as e:
            job['state'] = 'error'
            job['last'] = f"{type(e).__name__}: {e}"


# =========================================================
# 讀取
# =========================================================

def list_symbols():
    out = []
    for f in sorted(DATA.glob('*_1d.csv')):
        key = f.stem[:-3] if f.stem.endswith('_1d') else f.stem
        first = last = ''
        n = 0
        with open(f, newline='', encoding='utf-8') as fh:
            rd = csv.reader(fh)
            next(rd, None)
            for row in rd:
                if not row:
                    continue
                if n == 0:
                    first = row[0]
                last = row[0]
                n += 1
        name = symbols.REGISTRY[key].name if key in symbols.REGISTRY else key
        note = symbols.REGISTRY[key].note if key in symbols.REGISTRY else ''
        out.append({'key': key, 'name': name, 'rows': n,
                    'start': first, 'end': last, 'note': note})
    return out


def list_instruments():
    downloaded = {f.stem[:-3] for f in DATA.glob('*_1d.csv') if f.stem.endswith('_1d')}
    return [{'key': k, 'name': inst.name, 'source': inst.source,
             'note': inst.note, 'downloaded': k in downloaded}
            for k, inst in symbols.REGISTRY.items()]


def load_data(key):
    f = DATA / f'{key}_1d.csv'
    if not f.exists():
        return None
    candles, volumes = [], []
    with open(f, newline='', encoding='utf-8') as fh:
        rd = csv.DictReader(fh)
        for row in rd:
            try:
                t = row['Date']
                o, h, l, c = (float(row['Open']), float(row['High']),
                              float(row['Low']), float(row['Close']))
                v = int(float(row.get('Volume') or 0))
            except (ValueError, KeyError):
                continue
            candles.append({'time': t, 'open': o, 'high': h, 'low': l, 'close': c})
            up = c >= o
            volumes.append({'time': t, 'value': v,
                            'color': 'rgba(38,166,154,0.5)' if up else 'rgba(239,83,80,0.5)'})
    return {'candles': candles, 'volumes': volumes}


# =========================================================
# HTTP handler
# =========================================================

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        elif isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ('/', '/index.html'):
            html = (WEB / 'index.html').read_text(encoding='utf-8')
            return self._send(200, html, 'text/html; charset=utf-8')
        if u.path == '/api/symbols':
            return self._send(200, list_symbols())
        if u.path == '/api/instruments':
            return self._send(200, list_instruments())
        if u.path == '/api/data':
            key = (parse_qs(u.query).get('symbol') or [''])[0]
            data = load_data(key)
            if data is None:
                return self._send(404, {'error': f'no data for {key}'})
            return self._send(200, data)
        if u.path == '/api/download_status':
            jid = (parse_qs(u.query).get('job') or [''])[0]
            job = JOBS.get(jid)
            if not job:
                return self._send(404, {'error': 'job not found'})
            return self._send(200, {'state': job['state'], 'last': job.get('last', ''),
                                    'result': job.get('result')})
        return self._send(404, {'error': 'not found'})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != '/api/download':
            return self._send(404, {'error': 'not found'})
        try:
            length = int(self.headers.get('Content-Length', 0))
            payload = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send(400, {'error': 'bad json'})

        name = str(payload.get('symbol', '')).strip()
        start = str(payload.get('start', '') or '2015-01-01').strip()
        try:
            inst = symbols.resolve(name)
        except KeyError as e:
            return self._send(400, {'error': str(e)})

        jid = uuid.uuid4().hex[:8]
        JOBS[jid] = {'state': 'queued', 'log': [], 'last': '排隊中...'}
        threading.Thread(target=_run_download, args=(JOBS[jid], inst.key, start),
                         daemon=True).start()
        return self._send(200, {'job': jid, 'key': inst.key, 'name': inst.name})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--no-open', action='store_true')
    args = ap.parse_args()

    url = f"http://127.0.0.1:{args.port}/"
    srv = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f"K 線 UI 已啟動：{url}")
    print("在網頁上就能下載與檢視 K 棒。Ctrl+C 結束。")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        srv.shutdown()


if __name__ == '__main__':
    main()
