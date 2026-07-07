"""
K 線檢視 UI 的本機伺服器（含線上下載、多時間刻度）
================================================
用 TradingView 官方開源的 Lightweight Charts 呈現 K 棒，
並可直接在網頁上下載（日/60/30/15/5/1分），下載完即時顯示。

用法：
    python serve.py            # 啟動並自動開瀏覽器
    python serve.py --port 8800 --no-open

端點：
    GET  /                              → K 線頁面
    GET  /api/symbols                   → 已下載商品（含各自可用的時間刻度）
    GET  /api/instruments               → 全部支援商品（含來源）
    GET  /api/intervals                 → 支援的時間刻度
    GET  /api/data?symbol=&interval=    → OHLCV（給圖表）
    POST /api/download {symbol,interval,start} → 啟動下載，回 job_id
    POST /api/update_all               → 更新所有已下載的 (商品,刻度)
    GET  /api/download_status?job=ID    → 進度/結果
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
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import symbols
import download as dl
from intervals import INTERVALS, ORDER, label as iv_label, is_intraday

BASE = Path(__file__).parent
DATA = BASE / 'data'
WEB = BASE / 'web'

JOBS: dict[str, dict] = {}
JOB_LOCK = threading.Lock()


class _LogStream(io.TextIOBase):
    def __init__(self, job):
        self.job = job

    def write(self, s):
        s = s.strip()
        if s:
            self.job['log'].append(s)
            self.job['last'] = s
        return len(s)


def _do_one(job, key, interval, start):
    """在已持有 JOB_LOCK 的情況下下載單一 (商品,刻度)。"""
    with contextlib.redirect_stdout(_LogStream(job)):
        n, s, e = dl.download_one(key, interval, start)
    return n, s, e


def _run_download(job, key, interval, start):
    job['state'] = 'queued'
    with JOB_LOCK:
        job['state'] = 'running'
        try:
            n, s, e = _do_one(job, key, interval, start)
            if n == 0:
                job['state'] = 'error'
                job['last'] = job.get('last') or '無資料'
                return
            job['result'] = {'key': key, 'interval': interval, 'rows': n, 'start': s, 'end': e}
            job['state'] = 'done'
            job['last'] = f"完成：{key} [{iv_label(interval)}] {n} 根（{s} → {e}）"
        except Exception as ex:
            job['state'] = 'error'
            job['last'] = f"{type(ex).__name__}: {ex}"


def _run_update_all(job):
    job['state'] = 'queued'
    with JOB_LOCK:
        job['state'] = 'running'
        targets = _downloaded_pairs()
        if not targets:
            job['state'] = 'done'
            job['last'] = '沒有已下載的資料可更新'
            return
        done = 0
        for key, interval in targets:
            job['last'] = f"更新 {key} [{iv_label(interval)}] ...（{done+1}/{len(targets)}）"
            try:
                with contextlib.redirect_stdout(_LogStream(job)):
                    dl.update_one(key, interval)   # 增量更新
                done += 1
            except Exception as ex:
                job['log'].append(f"{key} {interval} 失敗：{ex}")
        job['result'] = {'updated': done, 'total': len(targets)}
        job['state'] = 'done'
        job['last'] = f"完成：更新 {done}/{len(targets)} 筆"


# =========================================================
# 讀取
# =========================================================

def _parse_name(stem):
    """'MNQ_15m' -> ('MNQ','15m')；未知刻度則整串當 key、刻度 1d。"""
    if '_' in stem:
        k, iv = stem.rsplit('_', 1)
        if iv in INTERVALS:
            return k, iv
    return stem, '1d'


def _downloaded_pairs():
    pairs = []
    for f in sorted(DATA.glob('*.csv')):
        k, iv = _parse_name(f.stem)
        pairs.append((k, iv))
    return pairs


def _file_meta(f):
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
    return n, first, last


def list_symbols():
    """回傳每個商品 + 其已下載的各時間刻度。"""
    bykey = {}
    for f in sorted(DATA.glob('*.csv')):
        key, iv = _parse_name(f.stem)
        n, first, last = _file_meta(f)
        name = symbols.REGISTRY[key].name if key in symbols.REGISTRY else key
        note = symbols.REGISTRY[key].note if key in symbols.REGISTRY else ''
        bykey.setdefault(key, {'key': key, 'name': name, 'note': note, 'intervals': {}})
        bykey[key]['intervals'][iv] = {'rows': n, 'start': first, 'end': last}
    # 依 ORDER 排序 intervals（輸出成有序 list）
    out = []
    for key, v in bykey.items():
        ivs = [{'key': iv, 'label': iv_label(iv), **v['intervals'][iv]}
               for iv in ORDER if iv in v['intervals']]
        out.append({**v, 'intervals': ivs})
    return out


def list_instruments():
    downloaded = {k for k, _ in _downloaded_pairs()}
    return [{'key': k, 'name': inst.name, 'source': inst.source,
             'note': inst.note, 'downloaded': k in downloaded}
            for k, inst in symbols.REGISTRY.items()]


def _epoch(s):
    """把 'YYYY-MM-DD HH:MM:SS'（牆上時鐘）轉成 epoch 秒，讓圖表顯示盤中時間。"""
    dt = datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S')
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def load_data(key, interval):
    f = dl.csv_path(key, interval)
    if not f.exists():
        return None
    intraday = is_intraday(interval)
    candles, volumes = [], []
    with open(f, newline='', encoding='utf-8') as fh:
        rd = csv.DictReader(fh)
        tcol = 'Datetime' if 'Datetime' in (rd.fieldnames or []) else 'Date'
        for row in rd:
            try:
                t = _epoch(row[tcol]) if intraday else row[tcol]
                o, h, l, c = (float(row['Open']), float(row['High']),
                              float(row['Low']), float(row['Close']))
                v = int(float(row.get('Volume') or 0))
            except (ValueError, KeyError):
                continue
            candles.append({'time': t, 'open': o, 'high': h, 'low': l, 'close': c})
            up = c >= o
            volumes.append({'time': t, 'value': v,
                            'color': 'rgba(38,166,154,0.5)' if up else 'rgba(239,83,80,0.5)'})
    return {'candles': candles, 'volumes': volumes, 'intraday': intraday}


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

    def _job_status(self, jid):
        job = JOBS.get(jid)
        if not job:
            return self._send(404, {'error': 'job not found'})
        return self._send(200, {'state': job['state'], 'last': job.get('last', ''),
                                'result': job.get('result')})

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ('/', '/index.html'):
            return self._send(200, (WEB / 'index.html').read_text(encoding='utf-8'),
                              'text/html; charset=utf-8')
        if u.path == '/api/symbols':
            return self._send(200, list_symbols())
        if u.path == '/api/instruments':
            return self._send(200, list_instruments())
        if u.path == '/api/intervals':
            return self._send(200, [{'key': k, 'label': iv_label(k),
                                     'intraday': is_intraday(k)} for k in ORDER])
        if u.path == '/api/data':
            key = (q.get('symbol') or [''])[0]
            interval = (q.get('interval') or ['1d'])[0]
            data = load_data(key, interval)
            if data is None:
                return self._send(404, {'error': f'no data for {key} [{interval}]'})
            return self._send(200, data)
        if u.path == '/api/download_status':
            return self._job_status((q.get('job') or [''])[0])
        return self._send(404, {'error': 'not found'})

    def do_POST(self):
        u = urlparse(self.path)
        try:
            length = int(self.headers.get('Content-Length', 0))
            payload = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            payload = {}

        if u.path == '/api/download':
            name = str(payload.get('symbol', '')).strip()
            interval = str(payload.get('interval', '1d')).strip() or '1d'
            start = str(payload.get('start', '') or '2015-01-01').strip()
            if interval not in INTERVALS:
                return self._send(400, {'error': f'未知時間刻度：{interval}'})
            try:
                inst = symbols.resolve(name)
            except KeyError as e:
                return self._send(400, {'error': str(e)})
            jid = uuid.uuid4().hex[:8]
            JOBS[jid] = {'state': 'queued', 'log': [], 'last': '排隊中...'}
            threading.Thread(target=_run_download,
                             args=(JOBS[jid], inst.key, interval, start), daemon=True).start()
            return self._send(200, {'job': jid, 'key': inst.key,
                                    'name': inst.name, 'interval': interval})

        if u.path == '/api/update_all':
            jid = uuid.uuid4().hex[:8]
            JOBS[jid] = {'state': 'queued', 'log': [], 'last': '排隊中...'}
            threading.Thread(target=_run_update_all, args=(JOBS[jid],), daemon=True).start()
            return self._send(200, {'job': jid})

        return self._send(404, {'error': 'not found'})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--no-open', action='store_true')
    args = ap.parse_args()

    url = f"http://127.0.0.1:{args.port}/"
    srv = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f"K 線 UI 已啟動：{url}")
    print("在網頁上就能下載（日/分鐘）與檢視 K 棒。Ctrl+C 結束。")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        srv.shutdown()


if __name__ == '__main__':
    main()
