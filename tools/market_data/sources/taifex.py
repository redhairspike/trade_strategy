"""
台灣期交所（TAIFEX）官方每日行情下載。
用於大台(TX) / 小台(MTX) / 微台(TMF)。

官方端點每次回傳「某商品在日期區間內、各到期月份、各交易時段」的每日 OHLC。
我們把它整理成一條連續日K：
  1. 只取「一般」交易時段（日盤），排除盤後夜盤，避免同日重複。
  2. 每個交易日挑「成交量最大」的合約月份 = 最活躍近月（近似連續合約，避免換月跳空）。

因期交所單次查詢區間有上限，長歷史會自動逐年分段下載。
"""

import io
import time
import datetime as dt
import pandas as pd
import requests

STD_COLS = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']

_URL = "https://www.taifex.com.tw/cht/3/futDataDown"
_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.taifex.com.tw/cht/3/dlFutDailyMarketView",
}

# 欄位索引（TAIFEX 每日下載固定格式）
_C_DATE, _C_ID, _C_MONTH = 0, 1, 2
_C_OPEN, _C_HIGH, _C_LOW, _C_CLOSE = 3, 4, 5, 6
_C_VOL = 9
_C_SESSION = 17
_REGULAR_SESSION = '一般'


def _to_num(s: str):
    s = (s or '').strip().replace(',', '')
    if s in ('', '-', '--'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _download_range(commodity_id: str, start: dt.date, end: dt.date) -> list[dict]:
    """下載單一區間，回傳一般時段的 raw 列。"""
    data = {
        "down_type": "1",
        "commodity_id": commodity_id,
        "commodity_id2": "",
        "queryStartDate": start.strftime('%Y/%m/%d'),
        "queryEndDate": end.strftime('%Y/%m/%d'),
    }
    r = requests.post(_URL, data=data, headers=_HEADERS, timeout=60)
    r.raise_for_status()
    text = r.content.decode('big5', errors='replace')

    rows = []
    reader = csv_lines(text)
    header_seen = False
    for cols in reader:
        if not header_seen:
            header_seen = True          # 跳過表頭
            continue
        if len(cols) <= _C_SESSION:
            continue
        if cols[_C_SESSION].strip() != _REGULAR_SESSION:
            continue                     # 只要日盤
        o = _to_num(cols[_C_OPEN]); h = _to_num(cols[_C_HIGH])
        l = _to_num(cols[_C_LOW]);  c = _to_num(cols[_C_CLOSE])
        if None in (o, h, l, c):
            continue
        vol = _to_num(cols[_C_VOL]) or 0
        rows.append({
            'Date':  cols[_C_DATE].strip().replace('/', '-'),
            'Month': cols[_C_MONTH].strip(),
            'Open':  o, 'High': h, 'Low': l, 'Close': c,
            'Volume': int(vol),
        })
    return rows


def csv_lines(text: str):
    """用標準 csv 解析（處理可能的引號），逐列回傳欄位 list。"""
    import csv
    return list(csv.reader(io.StringIO(text)))


def _most_active_daily(rows: list[dict]) -> pd.DataFrame:
    """每個交易日挑成交量最大的合約，組成連續日K。"""
    if not rows:
        return pd.DataFrame(columns=STD_COLS)
    df = pd.DataFrame(rows)
    # 同日同商品可能有多個月份 → 取當日成交量最大者
    idx = df.groupby('Date')['Volume'].idxmax()
    day = df.loc[idx].sort_values('Date').reset_index(drop=True)
    return day[STD_COLS]


def _month_ranges(start: dt.date, end: dt.date):
    """產生逐月的 (月初, 月底) 區間 —— TAIFEX 單次查詢上限為 1 個月。"""
    y, m = start.year, start.month
    while dt.date(y, m, 1) <= end:
        first = dt.date(y, m, 1)
        last = dt.date(y + (m == 12), (m % 12) + 1, 1) - dt.timedelta(days=1)
        yield max(first, start), min(last, end)
        y, m = y + (m == 12), (m % 12) + 1


def fetch_daily(commodity_id: str, start: str = '1998-01-01', end: str | None = None) -> pd.DataFrame:
    """下載某台指商品的連續日K（逐月分段，因 TAIFEX 單次查詢上限 1 個月）。"""
    start_d = dt.date.fromisoformat(start)
    end_d = dt.date.today() if end is None else dt.date.fromisoformat(end)

    all_rows: list[dict] = []
    cur_year = None
    for seg_start, seg_end in _month_ranges(start_d, end_d):
        if seg_start.year != cur_year:
            cur_year = seg_start.year
            print(f"      [TAIFEX] {commodity_id} 下載 {cur_year} ...")
        try:
            all_rows.extend(_download_range(commodity_id, seg_start, seg_end))
        except Exception as e:
            print(f"      [TAIFEX] {commodity_id} {seg_start:%Y-%m} 下載失敗：{e}")
        time.sleep(0.25)   # 對官方站客氣一點

    return _most_active_daily(all_rows)
