"""
2B（破底翻）/ 頭肩底 / 翻亞當 型態掃描器
==========================================
偵測邏輯依據 D:/AI/Claude_Cowork_Projects/破底翻/破底翻_演算法.md
與 CLAUDE.md 的破底翻 / 亞當理論定義。

  2B：頭部放量破底 → 1~4根內反彈>=0.3% → 右肩縮量測試且不破頭部低點
      → 右肩後收紅K且收盤在支撐之上 = 進場點

  頭肩底：左肩/頭/右肩三個低點，頭部最低且放量，右肩縮量，
          頸線（左右肩高點連線）被收盤突破 = 進場點

  翻亞當（多方/空方）：獨立型態，逐根K棒掃描，
          回傳符合任一翻立條件的K棒及其所有符合條件清單。
          多方條件：長紅K / 創新高 / 突破盤整高點 / 趨勢改變(由空轉多)
          空方條件：長黑K / 創新低 / 跌破盤整低點 / 趨勢改變(由多轉空)
          （不含「過前高」/「破前低」：趨勢延續時幾乎每根都成立，會洗出大量雜訊）

用法：
    python pattern_scanner.py MNQ --interval 5m
"""

import sys
import argparse
from datetime import timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Windows 主控台強制 UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ---- 參數 ----
SWING_ORDER           = 4     # 局部極值左右各看幾根K棒
PRIOR_TREND_BARS      = 8     # 頭部前下跌趨勢檢查根數
REBOUND_MIN           = 0.003 # 頭部後最小反彈幅度（0.3%）
REBOUND_MAX_BARS      = 4     # 反彈需在頭部後幾根K棒內出現
VOLUME_SPIKE_MULT     = 1.2   # 頭部量能門檻：> 近期均量 × 1.2
VOL_AVG_WINDOW        = 20    # 近期均量窗口
RIGHT_SHOULDER_WINDOW = 30    # 右肩/頸線突破搜尋窗口（根數）
SHOULDER_TOLERANCE    = 0.01  # 頭肩底左右肩高度容差（1%）
ADAM_LONG_PCT         = 0.003 # 長紅/長黑K 門檻（0.3%）
ADAM_LOOKBACK         = 20    # 創新高/低 回溯根數


# =========================================================
# 擺動高低點（不依賴 scipy）
# =========================================================

def _dedupe(idx, order):
    result, prev = [], -(10 ** 9)
    for i in idx:
        if i - prev >= order:
            result.append(int(i))
            prev = i
    return result


def find_swing_lows(low: np.ndarray, order: int = SWING_ORDER) -> list:
    n = len(low)
    if n < order * 2 + 1:
        return []
    idx = [i for i in range(order, n - order)
           if low[i] <= low[i - order:i + order + 1].min()]
    return _dedupe(idx, order)


def find_swing_highs(high: np.ndarray, order: int = SWING_ORDER) -> list:
    n = len(high)
    if n < order * 2 + 1:
        return []
    idx = [i for i in range(order, n - order)
           if high[i] >= high[i - order:i + order + 1].max()]
    return _dedupe(idx, order)


# =========================================================
# 共用輔助
# =========================================================

def _prior_downtrend(df, i, bars=PRIOR_TREND_BARS):
    start = max(0, i - bars)
    if i - start < 4:
        return False
    highs = df['High'].iloc[start:i].to_numpy()
    third = max(1, len(highs) // 3)
    return highs[:third].max() > highs[-third:].max()


def _avg_volume(df, i, window=VOL_AVG_WINDOW):
    start = max(0, i - window)
    return float(df['Volume'].iloc[start:i].mean()) if i > start else None


# =========================================================
# 亞當翻立條件（回傳所有符合條件的清單，可多個）
# =========================================================

def _adam_conditions_bull(df, i: int) -> list:
    """回傳 i 根K棒符合的所有多方亞當翻立條件。
    不含「過前高」：那個條件在趨勢延續時幾乎每根K棒都成立，會洗出大量雜訊，
    不是真正的翻立事件（CLAUDE.md 的第三關 5m/15m 互換訊號才用得到，不放這裡）。
    """
    conds = []
    c = float(df['Close'].iloc[i])
    o = float(df['Open'].iloc[i])

    # 1. 長紅K
    if o > 0 and (c - o) / o >= ADAM_LONG_PCT:
        conds.append('長紅K')

    # 2. 創新高：close > 前N根最高價
    start = max(0, i - ADAM_LOOKBACK)
    if i > start and c > float(df['High'].iloc[start:i].max()):
        conds.append('創新高')

    # 3. 突破盤整高點：close > 近期擺動高點
    if i > SWING_ORDER * 2 + 1:
        sh = find_swing_highs(df['High'].to_numpy()[:i], order=SWING_ORDER)
        if sh and sh[-1] < i - 1 and c > float(df['High'].iloc[sh[-1]]):
            conds.append('突破盤整高點')

    # 4. 趨勢改變（由空轉多）：近4根 HH + HL
    if i >= 4:
        h4 = df['High'].iloc[i - 4:i + 1].to_numpy()
        l4 = df['Low'].iloc[i - 4:i + 1].to_numpy()
        if h4[-1] > h4[:-1].max() and l4[-1] > l4[:-1].min():
            conds.append('趨勢改變(由空轉多)')

    return conds


def _adam_conditions_bear(df, i: int) -> list:
    """回傳 i 根K棒符合的所有空方亞當翻立條件。
    不含「破前低」：理由同 _adam_conditions_bull。
    """
    conds = []
    c = float(df['Close'].iloc[i])
    o = float(df['Open'].iloc[i])

    # 1. 長黑K
    if o > 0 and (o - c) / o >= ADAM_LONG_PCT:
        conds.append('長黑K')

    # 2. 創新低：close < 前N根最低價
    start = max(0, i - ADAM_LOOKBACK)
    if i > start and c < float(df['Low'].iloc[start:i].min()):
        conds.append('創新低')

    # 3. 跌破盤整低點：close < 近期擺動低點
    if i > SWING_ORDER * 2 + 1:
        sl = find_swing_lows(df['Low'].to_numpy()[:i], order=SWING_ORDER)
        if sl and sl[-1] < i - 1 and c < float(df['Low'].iloc[sl[-1]]):
            conds.append('跌破盤整低點')

    # 4. 趨勢改變（由多轉空）：近4根 LL + LH
    if i >= 4:
        h4 = df['High'].iloc[i - 4:i + 1].to_numpy()
        l4 = df['Low'].iloc[i - 4:i + 1].to_numpy()
        if l4[-1] < l4[:-1].min() and h4[-1] < h4[:-1].max():
            conds.append('趨勢改變(由多轉空)')

    return conds


# =========================================================
# 翻亞當型態掃描（獨立型態）
# =========================================================

def detect_adam_flip(df: pd.DataFrame) -> list:
    """
    逐根K棒掃描多方/空方亞當翻立。
    每筆結果：pattern_type / entry_idx / conditions（所有符合條件清單）
    """
    results = []
    n = len(df)
    min_i = max(ADAM_LOOKBACK, SWING_ORDER * 2 + 2, 4)

    for i in range(min_i, n):
        bull = _adam_conditions_bull(df, i)
        if bull:
            results.append(dict(pattern_type='adam_flip_bull',
                                entry_idx=int(i), conditions=bull))
        bear = _adam_conditions_bear(df, i)
        if bear:
            results.append(dict(pattern_type='adam_flip_bear',
                                entry_idx=int(i), conditions=bear))

    return results


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
        avg_vol  = _avg_volume(df, head_idx)
        if avg_vol is None or avg_vol <= 0 or head_vol < avg_vol * VOLUME_SPIKE_MULT:
            continue

        rebound_end  = min(n, head_idx + REBOUND_MAX_BARS + 1)
        highs_after  = df['High'].iloc[head_idx + 1:rebound_end]
        if highs_after.empty:
            continue
        peak_after = float(highs_after.max())
        if (peak_after - head_low) / head_low < REBOUND_MIN:
            continue
        peak_pos = df.index.get_loc(highs_after.idxmax())

        search_end     = min(n, head_idx + RIGHT_SHOULDER_WINDOW)
        rs_candidates  = [i for i in lows if peak_pos < i < search_end]
        if not rs_candidates:
            continue
        right_shoulder_idx = rs_candidates[0]
        rs_low = float(df['Low'].iloc[right_shoulder_idx])
        if rs_low < head_low:
            continue

        rs_vol     = float(df['Volume'].iloc[right_shoulder_idx])
        volume_ok  = rs_vol < head_vol

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
        ls_low   = float(df['Low'].iloc[ls_idx])
        head_low = float(df['Low'].iloc[head_idx])
        rs_low   = float(df['Low'].iloc[rs_idx])

        if not (head_low < ls_low and head_low < rs_low):
            continue
        if abs(ls_low - rs_low) / ls_low > SHOULDER_TOLERANCE:
            continue

        ls_vol   = float(df['Volume'].iloc[ls_idx])
        head_vol = float(df['Volume'].iloc[head_idx])
        rs_vol   = float(df['Volume'].iloc[rs_idx])
        if head_vol <= ls_vol:
            continue
        volume_ok = rs_vol < head_vol

        ls_peak_seg  = df['High'].iloc[ls_idx:head_idx + 1]
        rs_peak_seg  = df['High'].iloc[head_idx:rs_idx + 1]
        ls_peak_idx  = df.index.get_loc(ls_peak_seg.idxmax())
        rs_peak_idx  = df.index.get_loc(rs_peak_seg.idxmax())
        ls_peak      = float(ls_peak_seg.max())
        rs_peak      = float(rs_peak_seg.max())

        def neckline_at(j, _lpi=ls_peak_idx, _rpi=rs_peak_idx,
                        _lp=ls_peak, _rp=rs_peak):
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


# =========================================================
# 型態註冊表
# =========================================================

PATTERN_LABELS = {
    '2B':             '2B（破底翻）',
    'HnS_bottom':     '頭肩底',
    # 'adam_flip_bull'/'adam_flip_bear' 暫時下架：detect_adam_flip() 邏輯還在（見上方），
    # 但訊號太密集（15m MNQ 單方向 2000+ 筆）且 O(n²) 太慢（13000根K棒要 30~40 秒），
    # 待改成「狀態轉換那一刻才標記」+ 修效能後再重新註冊回來。
}
PATTERN_TYPES = tuple(PATTERN_LABELS.keys())


def available_types() -> list:
    return [{'key': k, 'label': v} for k, v in PATTERN_LABELS.items()]


def scan_patterns(df: pd.DataFrame, types: set | None = None) -> list:
    if types is None:
        types = set(PATTERN_TYPES)   # 預設 = 目前註冊表裡的全部型態
    patterns = []
    if '2B' in types:
        patterns += detect_2b(df)
    if 'HnS_bottom' in types:
        patterns += detect_hns_bottom(df)
    if 'adam_flip_bull' in types or 'adam_flip_bear' in types:
        for p in detect_adam_flip(df):
            if p['pattern_type'] in types:
                patterns.append(p)
    patterns.sort(key=lambda r: r['entry_idx'])
    return patterns


# =========================================================
# CSV 載入 + 時間格式化（供 server.py /patterns 使用）
# =========================================================

def load_csv_data(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    tcol = 'Datetime' if 'Datetime' in df.columns else 'Date'
    df[tcol] = pd.to_datetime(df[tcol])
    df = df.set_index(tcol).sort_index()
    for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna(
        subset=['Open', 'High', 'Low', 'Close'])


def _epoch(ts) -> int:
    dt = pd.Timestamp(ts).to_pydatetime()
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def _time_value(ts, intraday: bool):
    return _epoch(ts) if intraday else str(pd.Timestamp(ts).date())


def _annotate(df: pd.DataFrame, patterns: list, intraday: bool) -> list:
    """把 *_idx 轉成前端畫圖用的 *_time / *_price。"""
    out = []
    point_fields = ['left_shoulder_idx', 'head_idx', 'right_shoulder_idx', 'entry_idx']
    for p in patterns:
        row = dict(p)
        is_adam = row['pattern_type'].startswith('adam_flip')
        for field in point_fields:
            if field not in row:
                continue
            idx  = row[field]
            name = field[:-len('_idx')]
            price = (float(df['Close'].iloc[idx])
                     if (is_adam or name == 'entry')
                     else float(df['Low'].iloc[idx]))
            row[f'{name}_time']  = _time_value(df.index[idx], intraday)
            row[f'{name}_price'] = price
        for end in ('neckline_start', 'neckline_end'):
            idx = row.get(f'{end}_idx')
            if idx is not None:
                row[f'{end}_time'] = _time_value(df.index[idx], intraday)
        out.append(row)
    return out


def scan_from_csv(key: str, interval: str, types: set | None = None) -> list:
    import download as dl
    from intervals import is_intraday
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
    from intervals import INTERVALS
    import download as dl

    ap = argparse.ArgumentParser(description="2B / 頭肩底 / 翻亞當 型態掃描器")
    ap.add_argument('symbol', help="商品代碼，如 MNQ")
    ap.add_argument('--interval', default='5m', choices=list(INTERVALS.keys()))
    args = ap.parse_args()

    path = dl.find_csv(args.symbol, args.interval)
    if path is None:
        print(f"找不到 {args.symbol} [{args.interval}] 資料，"
              f"先跑：python download.py {args.symbol} --interval {args.interval}")
        return

    df = load_csv_data(path)
    print(f"載入 {len(df)} 根 {args.symbol} [{args.interval}]：{df.index[0]} → {df.index[-1]}")

    patterns = scan_patterns(df)
    print(f"\n偵測到 {len(patterns)} 個型態：")
    for p in patterns:
        entry_ts = df.index[p['entry_idx']]
        pt = p['pattern_type']
        if pt.startswith('adam_flip'):
            direction = '多方▲' if pt == 'adam_flip_bull' else '空方▼'
            conds = ' + '.join(p.get('conditions', []))
            print(f"  [翻亞當 {direction}] @{entry_ts}  條件：{conds}")
        else:
            vol_flag = '✅右肩縮量' if p.get('volume_ok') else '⚠️右肩量未縮'
            print(f"  [{pt}] 進場@{entry_ts}  支撐={p['support_level']:.2f}  "
                  f"頭={p['head_idx']} 右肩={p.get('right_shoulder_idx', '-')} "
                  f"進場={p['entry_idx']}  {vol_flag}")


if __name__ == '__main__':
    main()
