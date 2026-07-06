"""
K 線檢視 UI 的本機伺服器
========================
用 TradingView 官方開源的 Lightweight Charts 呈現下載好的日K CSV。

用法：
    python serve.py            # 啟動並自動開瀏覽器
    python serve.py --port 8800 --no-open

端點：
    GET /                      → K 線頁面
    GET /api/symbols           → 目前 data/ 內可用商品清單
    GET /api/data?symbol=KEY   → 該商品的 OHLCV（給圖表）
"""

import csv
import json
import argparse
import threading
import webbrowser
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import symbols

BASE = Path(__file__).parent
DATA = BASE / 'data'
WEB = BASE / 'web'


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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # 靜音

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
        if u.path == '/api/data':
            key = (parse_qs(u.query).get('symbol') or [''])[0]
            data = load_data(key)
            if data is None:
                return self._send(404, {'error': f'no data for {key}'})
            return self._send(200, data)
        return self._send(404, {'error': 'not found'})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--no-open', action='store_true')
    args = ap.parse_args()

    if not any(DATA.glob('*_1d.csv')):
        print("⚠ data/ 內沒有任何 CSV，請先執行：python download.py")
    url = f"http://127.0.0.1:{args.port}/"
    srv = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f"K 線 UI 已啟動：{url}")
    print("Ctrl+C 結束。")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        srv.shutdown()


if __name__ == '__main__':
    main()
