"""
FinLab 夜盤（盤後）期貨資料來源
================================
補上 TAIFEX 官方來源（sources/taifex.py）沒有的盤後時段：
taifex.py 只抓「一般」（日盤），FinLab 的 futures_price 資料集
另外有「盤後」欄位（如 'TX盤後'），可以拿到夜盤 K 線。

⚠️ 免費帳號限制：FinLab 免費方案的 futures_price 資料集目前只到
   2018-12-28（日盤/夜盤皆同），之後的資料需要付費方案才能取得。
   本模組照常會抓資料，但免費帳號抓到的最新一天會停在 2018-12-28。

需求：
  pip install finlab uv
  第一次使用需登入一次：
    python -c "import finlab; finlab.login()"
  （會開瀏覽器走 Google OAuth，token 存在 ~/.finlab，之後免再登入）
"""

import pandas as pd

STD_COLS = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']

# 標準欄位 -> FinLab futures_price 底下的中文欄位名稱
_FIELDS = {
    'Open':   '開盤價',
    'High':   '最高價',
    'Low':    '最低價',
    'Close':  '收盤價',
    'Volume': '成交量',
}


def available() -> bool:
    try:
        import finlab  # noqa
        return True
    except Exception:
        return False


def fetch_daily(column: str, start: str = '1998-01-01', end: str | None = None) -> pd.DataFrame:
    """下載 FinLab futures_price 某欄位（如 'TX盤後'）的日K。"""
    import finlab
    import finlab.data as data

    finlab.login()  # 已登入過會用快取 token，不會再跳瀏覽器

    series = {}
    for std_name, cn_field in _FIELDS.items():
        df = data.get(f'futures_price:{cn_field}')
        if column not in df.columns:
            raise RuntimeError(f"FinLab futures_price 找不到欄位：{column}（可能商品代碼不對）")
        series[std_name] = df[column]

    out = pd.DataFrame(series)
    out.index.name = 'Date'
    out = out.dropna(subset=['Open', 'High', 'Low', 'Close']).reset_index()
    out['Date'] = pd.to_datetime(out['Date']).dt.strftime('%Y-%m-%d')

    if start:
        out = out[out['Date'] >= start]
    if end:
        out = out[out['Date'] <= end]

    out['Volume'] = pd.to_numeric(out['Volume'], errors='coerce').fillna(0).astype('int64')
    out = out.sort_values('Date').drop_duplicates(subset=['Date']).reset_index(drop=True)

    if len(out) and out['Date'].iloc[-1] < '2019-01-01':
        print("      [FinLab] ⚠ 免費帳號資料上限 2018-12-28，抓不到最新夜盤資料（需付費方案）")

    return out[STD_COLS]
