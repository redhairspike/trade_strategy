"""
商品註冊表（Symbol Registry）
==============================
把「好記的名字」對應到「資料來源 + 該來源的代碼」。
新增商品只要在 REGISTRY 加一筆即可。

來源說明：
  yahoo  ── Yahoo Finance（yfinance），美股期貨用連續近月代理（NQ=F 等）
  taifex ── 台灣期交所官方每日下載，建構「最活躍合約」連續日K（只有日盤）
  finlab ── FinLab futures_price 資料集，補 TAIFEX 沒有的夜盤（盤後）K線
            ⚠️ 免費帳號資料只到 2018-12-28，需付費方案才有最新資料
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    key: str            # 標準代碼（存檔名用）
    name: str           # 中文名
    source: str         # 'yahoo' | 'taifex'
    ticker: str         # 該來源的實際代碼
    note: str = ''


# key -> Instrument
REGISTRY = {
    # ---- 美股微型期貨（Yahoo，用主連續合約代理，價格走勢與微型相同）----
    'MNQ': Instrument('MNQ', '微型納斯達克', 'yahoo', 'NQ=F', '用 E-mini NQ 連續合約代理'),
    'MGC': Instrument('MGC', '微型黃金',     'yahoo', 'GC=F', '用黃金連續合約代理'),
    'MCL': Instrument('MCL', '微型原油',     'yahoo', 'CL=F', '用原油連續合約代理'),

    # ---- 台指期（TAIFEX 官方，同追蹤加權指數，K 線走勢一致，差在合約規格）----
    'TX':  Instrument('TX',  '大台（臺股期貨）',   'taifex', 'TX',  '1998 上市，歷史最長，回測首選'),
    'MTX': Instrument('MTX', '小台（小型臺指）',   'taifex', 'MTX', '2001 上市，歷史長，回測首選'),
    'TMF': Instrument('TMF', '微台（微型臺指）',   'taifex', 'TMF', '2024 才上市，歷史短，僅供近期實盤對照'),

    # ---- 台指期夜盤（FinLab，補 TAIFEX 官方來源沒有的盤後時段）----
    'TXN':  Instrument('TXN',  '大台夜盤',  'finlab', 'TX盤後',  '⚠️ FinLab 免費帳號僅到 2018-12-28，付費方案才有最新'),
    'MTXN': Instrument('MTXN', '小台夜盤',  'finlab', 'MTX盤後', '⚠️ FinLab 免費帳號僅到 2018-12-28，付費方案才有最新'),
    'TMFN': Instrument('TMFN', '微台夜盤',  'finlab', 'TMF盤後', '⚠️ FinLab 免費帳號僅到 2018-12-28，付費方案才有最新'),
}

# 中文 / 常見別名 -> key
ALIASES = {
    '微型納斯達克': 'MNQ', '微那': 'MNQ', 'NQ': 'MNQ', 'MNQ': 'MNQ',
    '微型黃金': 'MGC', '微金': 'MGC', 'GC': 'MGC', 'MGC': 'MGC',
    '微型原油': 'MCL', '微油': 'MCL', 'CL': 'MCL', 'MCL': 'MCL',
    '大台': 'TX', '臺股期貨': 'TX', '台指期': 'TX', 'TXF': 'TX', 'TX': 'TX',
    '小台': 'MTX', '小型臺指': 'MTX', '小型台指': 'MTX', 'MXF': 'MTX', 'MTX': 'MTX',
    '微台': 'TMF', '微型臺指': 'TMF', '微型台指': 'TMF', 'TMF': 'TMF',
    '大台夜盤': 'TXN', '大台夜盤期貨': 'TXN', 'TXN': 'TXN',
    '小台夜盤': 'MTXN', 'MTXN': 'MTXN',
    '微台夜盤': 'TMFN', 'TMFN': 'TMFN',
}


def resolve(name: str) -> Instrument:
    """把使用者輸入（中英別名）解析成 Instrument。"""
    key = ALIASES.get(name.strip(), name.strip().upper())
    if key not in REGISTRY:
        raise KeyError(f"未知商品：{name}（可用：{', '.join(REGISTRY)}）")
    return REGISTRY[key]


def all_keys():
    return list(REGISTRY.keys())
