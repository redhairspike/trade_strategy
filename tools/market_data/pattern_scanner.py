"""
2B（破底翻）/ 頭肩底 型態掃描器
================================
偵測邏輯依據 `D:/AI/Claude_Cowork_Projects/破底翻/破底翻_演算法.md`
（18張實際進場圖歸納）與 CLAUDE.md 的破底翻定義：

  2B：頭部放量破底 → 1~4根內反彈 >=0.3% → 右肩縮量測試且不破頭部低點
      → 右肩後收紅K（且收盤在支撐之上）= 進場點
      （右肩破頭部低點 = W形態失效，不產生訊號）

  頭肩底：左肩／頭／右肩三個低點，頭部最低且放量創低，右肩縮量（賣壓耗盡），
          左右肩高度相近，頸線（左肩高點—右肩高點連線）被收盤價突破 = 進場點

只依賴 pandas/numpy（market_data 既有依賴，透過 yfinance 間接引入），
不用 scipy，維持獨立可執行、也方便日後打包進 exe。

用法（獨立執行，讀 market_data/data 內的 CSV）：
    python pattern_scanner.py MNQ --interval 5m
"""

import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import download as dl
from intervals import INTERVALS, is_intraday

# Windows 主控台預設可能是 cp950，中文/emoji 會亂碼或報錯，強制 UTF-8 輸出
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ---- 參數 ----
SWING_ORDER = 4              # 局部低點左右各看幾根K棒
PRIOR_TREND_BARS = 8          # 頭部前檢查下跌趨勢的K棒數
REBOUND_MIN = 0.003           # 頭部後最小反彈幅度（0.3%）
REBOUND_MAX_BARS = 4           # 反彈需在頭部後幾根K棒內出現
VOLUME_SPIKE_MULT = 1.2       # 頭部破底K量能門檻：> 近期均量 * 1.2
VOL_AVG_WINDOW = 20            # 近期均量窗口
RIGHT_SHOULDER_WINDOW = 30    # 頭部後找右肩/頸線突破的搜尋窗口（根數）
SHOULDER_TOLERANCE = 0.01     # 頭肩底：左右肩高度相近容差（1%）


# =========================================================
# 擺動低點（不依賴 scipy）
# =========================================================

def _dedupe(idx, order):
    """去除彼此太靠近（< order）的極值，保留第一個。"""
    result, prev = [], -10 ** 9
    for i in idx:
        if i - prev >= order:
            result.append(int(i))
            prev = i
    return result


def find_swing_lows(low: np.ndarray, order: int = SWING_ORDER) -> list:
    """局部低點：該點在前後 order 根範圍內是最低（<=）。"""
    n = len(low)
    if n < order * 2 + 1:
        return []
    idx = []
    for i in range(order, n - order):
        seg = low[i - order:i + order + 1]
        if low[i] <= seg.min():
            idx.append(i)
    return _dedupe(idx, order)


def _prior_downtrend(df, i, bars=PRIOR_TREND_BARS):
    """頭部前 N 根K棒高點序列是否向下（前段高點 > 後段高點）。"""
    start = max(0, i - bars)
    if i - start < 4:
        return False
    highs = df['High'].iloc[start:i].to_numpy()
    third = max(1, len(highs) // 3)
    return highs[:third].max() > highs[-third:].max()


def _avg_volume(df, i, window=VOL_AVG_WINDOW):
    start = max(0, i - window)
    if start >= i:
        return None
    return float(df['Volume'].iloc[start:i].mean())


# =========================================================
# 2B（破底翻）偵測
# =========================================================

def detect_2b(df: pd.DataFrame) -> list:
    results = []
    lows = find_swing_lows(df['Low'].to_numpy())
    n = len(df)

    for head_idx in lows:
        if head_idx < PRIOR_TREND_BARS or head_idx + REBOUND_MAX_BARS >= n:
            continue
        if not _prior_downtrend(df, head_idx):
            continue

        head_low = float(df['Low'].iloc[head_idx])
        head_vol = float(df['Volume'].iloc[head_idx])
        avg_vol = _avg_volume(df, head_idx)
        if avg_vol is None or avg_vol <= 0 or head_vol < avg_vol * VOLUME_SPIKE_MULT:
            continue  # 頭部沒放量 = 不是止損獵殺型破底

        # 頭部後 1~4 根內須反彈 >= REBOUND_MIN
        rebound_end = min(n, head_idx + REBOUND_MAX_BARS + 1)
        highs_after = df['High'].iloc[head_idx + 1: rebound_end]
        if highs_after.empty:
            continue
        peak_after = float(highs_after.max())
        if (peak_after - head_low) / head_low < REBOUND_MIN:
            continue  # 4根內不反彈 = 真跌破，不是破底翻
        peak_pos = df.index.get_loc(highs_after.idxmax())

        # 反彈後第一個擺動低點 = 右肩（第二次測試）
        search_end = min(n, head_idx + RIGHT_SHOULDER_WINDOW)
        rs_candidates = [i for i in lows if peak_pos < i < search_end]
        if not rs_candidates:
            continue
        right_shoulder_idx = rs_candidates[0]
        rs_low = float(df['Low'].iloc[right_shoulder_idx])
        if rs_low < head_low:
            continue  # 右肩破頭部低點 = W形態失效

        rs_vol = float(df['Volume'].iloc[right_shoulder_idx])
        volume_ok = rs_vol < head_vol  # 右肩縮量 = 賣壓耗盡

        # 右肩後第一根「收紅K 且收盤在支撐之上」= 進場點
        entry_search_end = min(n, right_shoulder_idx + RIGHT_SHOULDER_WINDOW)
        entry_idx = None
        for j in range(right_shoulder_idx + 1, entry_search_end):
            c, o = df['Close'].iloc[j], df['Open'].iloc[j]
            if c > o and c > head_low:
                entry_idx = j
                break
        if entry_idx is None:
            continue

        results.append(dict(
            pattern_type='2B',
            head_idx=int(head_idx),
            right_shoulder_idx=int(right_shoulder_idx),
            entry_idx=int(entry_idx),
            support_level=head_low,
            head_volume=head_vol,
            right_shoulder_volume=rs_vol,
            volume_ok=bool(volume_ok),
        ))
    return results


# =========================================================
# 頭肩底偵測
# =========================================================

def detect_hns_bottom(df: pd.DataFrame) -> list:
    results = []
    lows = find_swing_lows(df['Low'].to_numpy())
    n = len(df)
    if len(lows) < 3:
        return results

    for k in range(len(lows) - 2):
        ls_idx, head_idx, rs_idx = lows[k], lows[k + 1], lows[k + 2]
        ls_low = float(df['Low'].iloc[ls_idx])
        head_low = float(df['Low'].iloc[head_idx])
        rs_low = float(df['Low'].iloc[rs_idx])

        if not (head_low < ls_low and head_low < rs_low):
            continue  # 頭必須是三者中最低
        if abs(ls_low - rs_low) / ls_low > SHOULDER_TOLERANCE:
            continue  # 左右肩高度需相近

        ls_vol = float(df['Volume'].iloc[ls_idx])
        head_vol = float(df['Volume'].iloc[head_idx])
        rs_vol = float(df['Volume'].iloc[rs_idx])
        if head_vol <= ls_vol:
            continue  # 頭部須放量創低
        volume_ok = rs_vol < head_vol  # 右肩縮量 = 耗盡

        # 頸線 = 左肩高點—右肩高點連線（線性內插，非水平線）
        ls_peak_seg = df['High'].iloc[ls_idx:head_idx + 1]
        rs_peak_seg = df['High'].iloc[head_idx:rs_idx + 1]
        ls_peak_idx = df.index.get_loc(ls_peak_seg.idxmax())
        rs_peak_idx = df.index.get_loc(rs_peak_seg.idxmax())
        ls_peak = float(ls_peak_seg.max())
        rs_peak = float(rs_peak_seg.max())

        def neckline_at(j, _lpi=ls_peak_idx, _rpi=rs_peak_idx, _lp=ls_peak, _rp=rs_peak):
            if _rpi == _lpi:
                return _lp
            t = (j - _lpi) / (_rpi - _lpi)
            return _lp + t * (_rp - _lp)

        entry_search_end = min(n, rs_idx + RIGHT_SHOULDER_WINDOW)
        entry_idx = None
        for j in range(rs_idx + 1, entry_search_end):
            if float(df['Close'].iloc[j]) > neckline_at(j):
                entry_idx = j
                break
        if entry_idx is None:
            continue

        results.append(dict(
            pattern_type='HnS_bottom',
            left_shoulder_idx=int(ls_idx),
            head_idx=int(head_idx),
            right_shoulder_idx=int(rs_idx),
            entry_idx=int(entry_idx),
            support_level=head_low,
            neckline=neckline_at(entry_idx),
            neckline_start_idx=int(ls_peak_idx),
            neckline_end_idx=int(rs_peak_idx),
            neckline_start_price=ls_peak,
            neckline_end_price=rs_peak,
            head_volume=head_vol,
            right_shoulder_volume=rs_vol,
            volume_ok=bool(volume_ok),
        ))
    return results


# 型態註冊表：新增一種型態掃描時，在這裡加一筆 + 對應的 detect_xxx() 函式，
# UI（型態選項彈窗）會自動列出，不用改前端。
PATTERN_LABELS = {
    '2B': '2B（破底翻）',
    'HnS_bottom': '頭肩底',
}
PATTERN_TYPES = tuple(PATTERN_LABELS.keys())


def available_types() -> list:
    return [{'key': k, 'label': v} for k, v in PATTERN_LABELS.items()]


def scan_patterns(df: pd.DataFrame, types: set | None = None) -> list:
    patterns = []
    if types is None or '2B' in types:
        patterns += detect_2b(df)
    if types is None or 'HnS_bottom' in types:
        patterns += detect_hns_bottom(df)
    patterns.sort(key=lambda r: r['entry_idx'])
    return patterns


# =========================================================
# CSV 載入 + 時間格式化（供 server.py /patterns 使用）
# =========================================================

def load_csv_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    tcol = 'Datetime' if 'Datetime' in df.columns else 'Date'
    df[tcol] = pd.to_datetime(df[tcol])
    df = df.set_index(tcol).sort_index()
    for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna(
        subset=['Open', 'High', 'Low', 'Close'])


def _epoch(ts) -> int:
    """牆上時鐘轉 epoch 秒，與 server.py 的 /api/data 一致，讓標記對齊 K 棒。"""
    dt = pd.Timestamp(ts).to_pydatetime()
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def _time_value(ts, intraday: bool):
    return _epoch(ts) if intraday else str(pd.Timestamp(ts).date())


def _annotate(df: pd.DataFrame, patterns: list, intraday: bool) -> list:
    """把 *_idx 轉成前端畫圖用的 *_time / *_price，並確保是可 JSON 序列化的原生型別。"""
    out = []
    point_fields = ['left_shoulder_idx', 'head_idx', 'right_shoulder_idx', 'entry_idx']
    for p in patterns:
        row = dict(p)
        for field in point_fields:
            if field not in row:
                continue
            idx = row[field]
            name = field[:-len('_idx')]
            price = float(df['Close'].iloc[idx]) if name == 'entry' else float(df['Low'].iloc[idx])
            row[f'{name}_time'] = _time_value(df.index[idx], intraday)
            row[f'{name}_price'] = price
        # 頸線端點（頭肩底）：價位已在 detect_hns_bottom 算好，這裡只補時間軸座標
        for end in ('neckline_start', 'neckline_end'):
            idx = row.get(f'{end}_idx')
            if idx is None:
                continue
            row[f'{end}_time'] = _time_value(df.index[idx], intraday)
        out.append(row)
    return out


def scan_from_csv(key: str, interval: str, types: set | None = None) -> list:
    path = dl.find_csv(key, interval)
    if path is None:
        raise FileNotFoundError(f"找不到 {key} [{interval}] 的資料，請先下載")
    df = load_csv_data(path)
    patterns = scan_patterns(df, types=types)
    return _annotate(df, patterns, is_intraday(interval))


# =========================================================
# CLI
# =========================================================

def main():
    ap = argparse.ArgumentParser(description="2B / 頭肩底 型態掃描器")
    ap.add_argument('symbol', help="商品代碼，如 MNQ")
    ap.add_argument('--interval', default='5m', choices=list(INTERVALS.keys()))
    args = ap.parse_args()

    path = dl.find_csv(args.symbol, args.interval)
    if path is None:
        print(f"⚠️  找不到 {args.symbol} [{args.interval}] 的資料，"
              f"先跑：python download.py {args.symbol} --interval {args.interval}")
        return

    df = load_csv_data(path)
    print(f"載入 {len(df)} 根 {args.symbol} [{args.interval}]：{df.index[0]} → {df.index[-1]}")

    patterns = scan_patterns(df)
    print(f"\n偵測到 {len(patterns)} 個型態：")
    for p in patterns:
        vol_flag = '✅右肩縮量' if p['volume_ok'] else '⚠️右肩量未縮'
        entry_ts = df.index[p['entry_idx']]
        print(f"  [{p['pattern_type']}] 進場@{entry_ts}  支撐={p['support_level']:.2f}  "
              f"頭={p['head_idx']} 右肩={p['right_shoulder_idx']} 進場={p['entry_idx']}  {vol_flag}")


if __name__ == '__main__':
    main()
