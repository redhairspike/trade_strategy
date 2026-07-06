"""
TradingView 補充來源（非官方 tvDatafeed）。
僅在免費官方來源抓不到時，作為備援。

需要：
  pip install tvDatafeed
  環境變數 TV_USERNAME / TV_PASSWORD（或匿名，但匿名限制較多）

symbol/exchange 例：
  MNQ  → symbol='MNQ1!', exchange='CME_MINI'
  微台 → symbol='TMF1!', exchange='TAIFEX'
"""

import os
import pandas as pd

STD_COLS = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']


def available() -> bool:
    try:
        import tvDatafeed  # noqa
        return True
    except Exception:
        return False


def fetch_daily(symbol: str, exchange: str, n_bars: int = 5000) -> pd.DataFrame:
    from tvDatafeed import TvDatafeed, Interval
    user = os.environ.get('TV_USERNAME')
    pwd = os.environ.get('TV_PASSWORD')
    tv = TvDatafeed(user, pwd) if user and pwd else TvDatafeed()
    df = tv.get_hist(symbol=symbol, exchange=exchange,
                     interval=Interval.in_daily, n_bars=n_bars)
    if df is None or len(df) == 0:
        raise RuntimeError(f"tvDatafeed 回傳空資料：{exchange}:{symbol}")
    df = df.reset_index()
    out = pd.DataFrame({
        'Date':   pd.to_datetime(df['datetime']).dt.strftime('%Y-%m-%d'),
        'Open':   df['open'].astype(float),
        'High':   df['high'].astype(float),
        'Low':    df['low'].astype(float),
        'Close':  df['close'].astype(float),
        'Volume': df.get('volume', 0),
    })
    out['Volume'] = pd.to_numeric(out['Volume'], errors='coerce').fillna(0).astype('int64')
    return out.sort_values('Date').reset_index(drop=True)[STD_COLS]
