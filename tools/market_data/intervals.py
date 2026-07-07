"""
時間刻度註冊表（Interval Registry）
===================================
定義支援的 K 棒週期，以及各來源的下載參數與歷史限制。

Yahoo 分鐘資料的歷史限制（yfinance）：
  60m → 最近 ~730 天
  30m / 15m / 5m → 最近 ~60 天
  1m → 最近 ~7 天
（台指 TAIFEX 免費來源只有日K，分鐘需券商 API。）
"""

# key -> 設定
INTERVALS = {
    '1d':  dict(label='日',   yf='1d',  yf_period=None,  intraday=False),
    '60m': dict(label='60分', yf='60m', yf_period='730d', intraday=True),
    '30m': dict(label='30分', yf='30m', yf_period='60d',  intraday=True),
    '15m': dict(label='15分', yf='15m', yf_period='60d',  intraday=True),
    '5m':  dict(label='5分',  yf='5m',  yf_period='60d',  intraday=True),
    '1m':  dict(label='1分',  yf='1m',  yf_period='7d',   intraday=True),
}

# 顯示/選單順序（大到小）
ORDER = ['1d', '60m', '30m', '15m', '5m', '1m']


def label(key: str) -> str:
    return INTERVALS.get(key, {}).get('label', key)


def is_intraday(key: str) -> bool:
    return INTERVALS.get(key, {}).get('intraday', False)
