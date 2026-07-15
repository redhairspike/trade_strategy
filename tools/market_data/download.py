"""
K 棒資料下載器（CLI）
=====================
把每日 K 棒下載成標準 CSV，供回測與 UI 使用。

用法：
    python download.py                    # 下載全部已註冊商品
    python download.py MNQ 大台 小台        # 指定商品（可用中英別名）
    python download.py MNQ --start 2015-01-01
    python download.py --list             # 列出可用商品

輸出：data/<KEY>_1d.csv   欄位=Date,Open,High,Low,Close,Volume

資料來源策略：免費官方為主（Yahoo / TAIFEX），抓不到時若裝了 tvDatafeed 則備援。
"""

import sys
import argparse
from pathlib import Path
from datetime import date, timedelta

import pandas as pd

import symbols
from intervals import INTERVALS, ORDER, is_intraday
from sources import yahoo, taifex, tradingview, finlab_source

if getattr(sys, 'frozen', False):
    # 打包成 exe 後：data 放在 exe 旁邊（可寫、資料能保存）
    DATA_DIR = Path(sys.executable).parent / 'data'
else:
    DATA_DIR = Path(__file__).parent / 'data'

# tvDatafeed 備援對照（僅在主來源失敗時使用）
_TV_FALLBACK = {
    'MNQ': ('MNQ1!', 'CME_MINI'),
    'MGC': ('MGC1!', 'COMEX_MINI'),
    'MCL': ('MCL1!', 'NYMEX'),
    'TX':  ('TXF1!', 'TAIFEX'),
    'MTX': ('MXF1!', 'TAIFEX'),
    'TMF': ('TMF1!', 'TAIFEX'),
}


def fetch_one(inst: symbols.Instrument, interval: str, start: str, end: str | None = None):
    """依來源+時間刻度下載單一商品，回傳標準化 DataFrame。"""
    if interval not in INTERVALS:
        raise ValueError(f"未知時間刻度：{interval}（可用：{', '.join(ORDER)}）")

    if inst.source == 'yahoo':
        return yahoo.fetch(inst.ticker, interval, start=start, end=end)

    if inst.source == 'taifex':
        if is_intraday(interval):
            raise RuntimeError(
                "TAIFEX 免費來源只有日K；台指分鐘資料(60/15/5/1分)需券商 API（如永豐 Shioaji）。")
        tw_start = start if start > '1998-01-01' else '1998-01-01'
        return taifex.fetch_daily(inst.ticker, start=tw_start, end=end)

    if inst.source == 'finlab':
        if is_intraday(interval):
            raise RuntimeError("FinLab 夜盤來源目前只支援日K。")
        if not finlab_source.available():
            raise RuntimeError("未安裝 finlab 套件，執行：pip install finlab")
        return finlab_source.fetch_daily(inst.ticker, start=start, end=end)

    raise ValueError(f"未知來源：{inst.source}")


# ---- CSV 檔名：<商品>_<刻度>_<起>_<迄>.csv（日期為資料的第一/最後一天）----

def csv_glob(key: str, interval: str):
    """同商品同刻度的所有檔（含含日期的新命名）。"""
    return sorted(DATA_DIR.glob(f"{key}_{interval}_*.csv"))


def find_csv(key: str, interval: str):
    """找出該商品該刻度目前的 CSV（優先含日期的新命名，退回舊命名）。找不到回 None。"""
    m = csv_glob(key, interval)
    if m:
        return m[-1]
    legacy = DATA_DIR / f"{key}_{interval}.csv"
    return legacy if legacy.exists() else None


def save_csv(key, interval, df, tcol):
    """存成 <商品>_<刻度>_<起>_<迄>.csv，並刪掉同商品同刻度的舊檔（只留一份）。"""
    start = str(df[tcol].iloc[0])[:10]
    end = str(df[tcol].iloc[-1])[:10]
    out = DATA_DIR / f"{key}_{interval}_{start}_{end}.csv"
    for f in csv_glob(key, interval) + [DATA_DIR / f"{key}_{interval}.csv"]:
        if f != out and f.exists():
            try:
                f.unlink()
            except OSError:
                pass
    df.to_csv(out, index=False, encoding='utf-8')
    return out, start, end


def download_one(key, interval, start, end=None):
    """下載單一 (商品, 時間刻度) 並存檔，回傳 (根數, 起, 迄)。"""
    DATA_DIR.mkdir(exist_ok=True)
    inst = symbols.REGISTRY[key]
    df = None
    try:
        df = fetch_one(inst, interval, start, end)
    except Exception as e:
        print(f"    ✗ 主來源失敗：{e}")

    # 備援：tvDatafeed（僅日K）
    if (df is None or len(df) == 0) and interval == '1d' \
            and key in _TV_FALLBACK and tradingview.available():
        sym, exch = _TV_FALLBACK[key]
        print(f"    ↪ 嘗試 tvDatafeed 備援：{exch}:{sym}")
        try:
            df = tradingview.fetch_daily(sym, exch)
        except Exception as e:
            print(f"    ✗ 備援也失敗：{e}")

    if df is None or len(df) == 0:
        print(f"    ⚠ 無資料")
        return (0, '', '')

    tcol = 'Datetime' if 'Datetime' in df.columns else 'Date'
    out, s, e = save_csv(key, interval, df, tcol)
    print(f"    ✓ {len(df)} 根K棒  {df[tcol].iloc[0]} → {df[tcol].iloc[-1]}  → {out.name}")
    return (len(df), str(df[tcol].iloc[0]), str(df[tcol].iloc[-1]))


def update_one(key, interval):
    """增量更新：只抓最近的資料，與現有 CSV 合併（保留歷史、不重複），存成新的起訖檔名。"""
    DATA_DIR.mkdir(exist_ok=True)
    inst = symbols.REGISTRY[key]
    tcol = 'Datetime' if is_intraday(interval) else 'Date'
    path = find_csv(key, interval)

    old = None
    if path is not None and path.exists():
        try:
            old = pd.read_csv(path)
        except Exception:
            old = None

    # 有舊資料就從最後日期往前留幾天重疊；沒有就抓全部
    if old is not None and len(old) and tcol in old.columns:
        last = str(old[tcol].iloc[-1])[:10]
        start = (date.fromisoformat(last) - timedelta(days=5)).isoformat()
    else:
        start = '2000-01-01'

    new = fetch_one(inst, interval, start)   # 分鐘K 由來源自身期間限制，start 只影響日K
    if new is None or len(new) == 0:
        n, s, e = _meta(old, tcol)
        print(f"    ⚠ 無新資料（維持 {n} 根）")
        return n, s, e

    combined = new if old is None else pd.concat([old, new], ignore_index=True)
    combined = combined.drop_duplicates(subset=[tcol], keep='last').sort_values(tcol)
    out, s, e = save_csv(key, interval, combined, tcol)
    n = len(combined)
    print(f"    ✓ {n} 根K棒（{s} → {e}）→ {out.name}")
    return n, str(combined[tcol].iloc[0]), str(combined[tcol].iloc[-1])


def _meta(df, tcol):
    if df is None or len(df) == 0:
        return 0, '', ''
    return len(df), str(df[tcol].iloc[0]), str(df[tcol].iloc[-1])


def download(keys, interval, start, end):
    summary = []
    for key in keys:
        inst = symbols.REGISTRY[key]
        print(f"\n▶ {key}  {inst.name} [{interval}]  ({inst.source}:{inst.ticker})")
        n, s, e = download_one(key, interval, start, end)
        summary.append((key, n, s, e))

    print("\n" + "=" * 52)
    print("  下載完成彙總")
    print("=" * 52)
    print(f"  {'商品':<6}{'根數':>8}   {'起':<20}{'迄':<20}")
    for key, n, s, e in summary:
        print(f"  {key:<6}{n:>8}   {s:<20}{e:<20}")
    print(f"\n  CSV 存於：{DATA_DIR}")
    print("  用 `python server.py` 開啟 K 線 UI 檢視。")


def main():
    ap = argparse.ArgumentParser(description="下載 K 棒 CSV")
    ap.add_argument('symbols', nargs='*', help="商品（中英別名，省略=全部）")
    ap.add_argument('--interval', default='1d', choices=list(INTERVALS.keys()),
                    help="時間刻度（1d/60m/30m/15m/5m/1m，預設 1d）")
    ap.add_argument('--start', default='2005-01-01', help="起始日 YYYY-MM-DD（日K 用）")
    ap.add_argument('--end', default=None, help="結束日 YYYY-MM-DD（預設今天）")
    ap.add_argument('--list', action='store_true', help="列出可用商品")
    args = ap.parse_args()

    if args.list:
        print("可用商品：")
        for k, inst in symbols.REGISTRY.items():
            print(f"  {k:<5} {inst.name:<14} 來源={inst.source:<7} {inst.note}")
        print("\n可用時間刻度：", ', '.join(INTERVALS.keys()))
        return

    if args.symbols:
        try:
            keys = [symbols.resolve(s).key for s in args.symbols]
        except KeyError as e:
            print(e); sys.exit(1)
    else:
        keys = symbols.all_keys()

    download(keys, args.interval, args.start, args.end)


if __name__ == '__main__':
    main()
