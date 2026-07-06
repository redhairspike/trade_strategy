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

import symbols
from sources import yahoo, taifex, tradingview

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


def fetch_one(inst: symbols.Instrument, start: str, end: str | None):
    """依來源下載單一商品，回傳標準化 DataFrame。"""
    if inst.source == 'yahoo':
        return yahoo.fetch_daily(inst.ticker, start=start, end=end)
    if inst.source == 'taifex':
        tw_start = start if start > '1998-01-01' else '1998-01-01'
        return taifex.fetch_daily(inst.ticker, start=tw_start, end=end)
    raise ValueError(f"未知來源：{inst.source}")


def download(keys, start, end):
    DATA_DIR.mkdir(exist_ok=True)
    summary = []
    for key in keys:
        inst = symbols.REGISTRY[key]
        print(f"\n▶ {key}  {inst.name}  ({inst.source}:{inst.ticker})")
        df = None
        try:
            df = fetch_one(inst, start, end)
        except Exception as e:
            print(f"    ✗ 主來源失敗：{e}")

        # 備援：tvDatafeed
        if (df is None or len(df) == 0) and key in _TV_FALLBACK and tradingview.available():
            sym, exch = _TV_FALLBACK[key]
            print(f"    ↪ 嘗試 tvDatafeed 備援：{exch}:{sym}")
            try:
                df = tradingview.fetch_daily(sym, exch)
            except Exception as e:
                print(f"    ✗ 備援也失敗：{e}")

        if df is None or len(df) == 0:
            print(f"    ⚠ 無資料，略過")
            summary.append((key, 0, '', ''))
            continue

        out = DATA_DIR / f"{key}_1d.csv"
        df.to_csv(out, index=False, encoding='utf-8')
        print(f"    ✓ {len(df)} 根K棒  {df['Date'].iloc[0]} → {df['Date'].iloc[-1]}  → {out.name}")
        summary.append((key, len(df), df['Date'].iloc[0], df['Date'].iloc[-1]))

    print("\n" + "=" * 52)
    print("  下載完成彙總")
    print("=" * 52)
    print(f"  {'商品':<6}{'根數':>8}   {'起':<12}{'迄':<12}")
    for key, n, s, e in summary:
        print(f"  {key:<6}{n:>8}   {s:<12}{e:<12}")
    print(f"\n  CSV 存於：{DATA_DIR}")
    print("  用 `python serve.py` 開啟 K 線 UI 檢視。")


def main():
    ap = argparse.ArgumentParser(description="下載每日 K 棒 CSV")
    ap.add_argument('symbols', nargs='*', help="商品（中英別名，省略=全部）")
    ap.add_argument('--start', default='2005-01-01', help="起始日 YYYY-MM-DD")
    ap.add_argument('--end', default=None, help="結束日 YYYY-MM-DD（預設今天）")
    ap.add_argument('--list', action='store_true', help="列出可用商品")
    args = ap.parse_args()

    if args.list:
        print("可用商品：")
        for k, inst in symbols.REGISTRY.items():
            print(f"  {k:<5} {inst.name:<14} 來源={inst.source:<7} {inst.note}")
        return

    if args.symbols:
        try:
            keys = [symbols.resolve(s).key for s in args.symbols]
        except KeyError as e:
            print(e); sys.exit(1)
    else:
        keys = symbols.all_keys()

    download(keys, args.start, args.end)


if __name__ == '__main__':
    main()
