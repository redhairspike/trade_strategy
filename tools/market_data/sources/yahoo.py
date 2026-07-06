"""Yahoo Finance 來源（yfinance）。用於美股期貨（MNQ→NQ=F 等）。"""

import warnings
warnings.filterwarnings('ignore')

import pandas as pd


STD_COLS = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']


def fetch_daily(ticker: str, start: str = '2000-01-01', end: str | None = None) -> pd.DataFrame:
    """下載日K，回傳標準化 DataFrame。"""
    import yfinance as yf
    df = yf.download(ticker, start=start, end=end, interval='1d',
                     progress=False, auto_adjust=True)
    if df is None or len(df) == 0:
        raise RuntimeError(f"Yahoo 回傳空資料：{ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    # yfinance 的日期欄位可能叫 'Date' 或 'index'
    date_col = 'Date' if 'Date' in df.columns else df.columns[0]
    out = pd.DataFrame({
        'Date':   pd.to_datetime(df[date_col]).dt.strftime('%Y-%m-%d'),
        'Open':   df['Open'].astype(float),
        'High':   df['High'].astype(float),
        'Low':    df['Low'].astype(float),
        'Close':  df['Close'].astype(float),
        'Volume': df['Volume'].fillna(0).astype('int64'),
    })
    out = out.dropna(subset=['Open', 'High', 'Low', 'Close'])
    out = out.sort_values('Date').reset_index(drop=True)
    return out[STD_COLS]
