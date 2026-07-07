"""Yahoo Finance 來源（yfinance）。支援日K與分鐘K（美股期貨）。

輸出標準化 DataFrame：
  日K   → 欄位 Date（YYYY-MM-DD）+ OHLCV
  分鐘K → 欄位 Datetime（YYYY-MM-DD HH:MM:SS，交易所當地時間的牆上時鐘）+ OHLCV
"""

import warnings
warnings.filterwarnings('ignore')

import pandas as pd

from intervals import INTERVALS


def fetch(ticker: str, interval_key: str, start: str = '2000-01-01', end: str | None = None) -> pd.DataFrame:
    """依時間刻度下載。回傳標準化 DataFrame（日K 用 Date、分鐘K 用 Datetime 欄位）。"""
    import yfinance as yf
    spec = INTERVALS[interval_key]

    if spec['intraday']:
        df = yf.download(ticker, period=spec['yf_period'], interval=spec['yf'],
                         progress=False, auto_adjust=True)
    else:
        df = yf.download(ticker, start=start, end=end, interval='1d',
                         progress=False, auto_adjust=True)

    if df is None or len(df) == 0:
        raise RuntimeError(f"Yahoo 回傳空資料：{ticker} [{interval_key}]")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    tcol = 'Datetime' if 'Datetime' in df.columns else ('Date' if 'Date' in df.columns else df.columns[0])
    ts = pd.to_datetime(df[tcol])

    base = {
        'Open':   df['Open'].astype(float),
        'High':   df['High'].astype(float),
        'Low':    df['Low'].astype(float),
        'Close':  df['Close'].astype(float),
        'Volume': pd.to_numeric(df['Volume'], errors='coerce').fillna(0).astype('int64'),
    }
    if spec['intraday']:
        # tz-aware → 去除時區但保留「交易所當地牆上時鐘」，方便圖表顯示盤中時間
        if getattr(ts.dt, 'tz', None) is not None:
            ts = ts.dt.tz_localize(None)
        out = pd.DataFrame({'Datetime': ts.dt.strftime('%Y-%m-%d %H:%M:%S'), **base})
        tkey = 'Datetime'
    else:
        out = pd.DataFrame({'Date': ts.dt.strftime('%Y-%m-%d'), **base})
        tkey = 'Date'

    out = out.dropna(subset=['Open', 'High', 'Low', 'Close'])
    out = out.sort_values(tkey).drop_duplicates(subset=[tkey]).reset_index(drop=True)
    return out[[tkey, 'Open', 'High', 'Low', 'Close', 'Volume']]


# 舊介面相容（有些程式可能還呼叫 fetch_daily）
def fetch_daily(ticker: str, start: str = '2000-01-01', end: str | None = None) -> pd.DataFrame:
    return fetch(ticker, '1d', start=start, end=end)
