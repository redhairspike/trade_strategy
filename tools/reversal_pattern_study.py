"""
破底翻失敗 → W底 → 反轉  假說驗證
=====================================
觀察假說（Spike 7/2/2026）：
    在「空轉多」的底部反轉點，
    「破底翻失敗後形成W底再反轉」的比例，
    遠高於「一次破底翻就成功（V型）」的比例。

觀察來源：MNQU6 5m 圖
    黃色線 = 第一次破底翻嘗試（失敗）
    紫色線 = 隨後形成的W底
    W底第二低點才是真正反轉點

--------------------------------------------------------------
本版針對交接文件（BACKTEST_HANDOFF.md）列出的 5 個已知問題做修正：

  (1) 破底翻失敗偵測：不再用 np.percentile 亂估支撐，
      改用「最近的局部低點」作為支撐，並以收盤價
      跌破→數根內收回 的完整機制判定一次「嘗試」。

  (2) W底判斷更嚴謹：
      - 兩低點價位容差（W_TOLERANCE）
      - 兩低點之間需有反彈幅度門檻（REBOUND_MIN）
      - 第二低點須在第一低點後至少 MIN_SEPARATION 根

  (3) 完整「破底翻失敗序列」：
      [支撐]→[破底]→[收回]→[再破底(W右腳)]→[收回站穩]→反轉
      逐步驗證，而非只看「有沒有跌破再收回」。

  (4) 多時框對齊：
      先在日K找重大反轉，再到 1h/30m/15m 對齊該時間點附近，
      分析當時的底部微結構。

  (5) 更多統計指標：
      - 第一低→第二低 平均間隔K棒數（含分佈直方圖）
      - W底反彈高度（中間峰值比低點高多少 %）
      - 假陽性率（獨立掃描所有雙底形態，統計形成W底
        但後續繼續下跌、未反轉的比例）

--------------------------------------------------------------
資料來源：Yahoo Finance（需本機安裝 yfinance）
安裝：pip install yfinance scipy matplotlib pandas numpy

執行：
    python reversal_pattern_study.py            # 正常回測（需連網）
    python reversal_pattern_study.py --selftest # 用合成資料自我驗證邏輯（免連網）
"""

import sys
import warnings
warnings.filterwarnings('ignore')

# Windows 主控台預設可能是 cp950，中文與 emoji 會亂碼/報錯，強制 UTF-8 輸出
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except Exception:
        pass

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')          # 無視窗環境也能存圖
import matplotlib.pyplot as plt
import matplotlib.font_manager as _fm

# ---- 自動偵測中文字型 ----
_CJK_CANDIDATES = [
    'Microsoft YaHei', 'MicroSoft YaHei', '微軟雅黑',  # Windows
    'SimHei', 'SimSun', 'NSimSun', 'KaiTi', 'FangSong', # Windows 備選
    'PingFang SC', 'PingFang TC', 'Heiti TC', 'Heiti SC', # macOS
    'Noto Sans CJK SC', 'Noto Sans CJK TC',              # Linux / Android
    'Noto Sans CJK JP', 'WenQuanYi Micro Hei',           # Linux 備選
]
_installed = {f.name for f in _fm.fontManager.ttflist}
_cjk_font = next((f for f in _CJK_CANDIDATES if f in _installed), None)
if _cjk_font:
    matplotlib.rcParams['font.family'] = _cjk_font
    matplotlib.rcParams['axes.unicode_minus'] = False   # 負號正常顯示
else:
    print("⚠️  找不到中文字型，圖表標題可能顯示方塊。"
          "Windows 請確認已安裝微軟雅黑；Linux 可 sudo apt install fonts-noto-cjk")
from scipy.signal import argrelextrema

try:
    import yfinance as yf
    _HAS_YF = True
except Exception:
    _HAS_YF = False


# =========================================================
# 設定
# =========================================================

SYMBOLS = {
    'daily': ('NQ=F', '5y',   '1d'),    # 日K，5年（找重大反轉，作為多時框對齊的錨）
    '1h':    ('NQ=F', '730d', '1h'),    # 1小時，2年
    '30m':   ('NQ=F', '60d',  '30m'),   # 30分，60天（Yahoo 上限）
    '15m':   ('NQ=F', '60d',  '15m'),   # 15分，60天
    '5m':    ('NQ=F', '60d',  '5m'),    # 5分，60天（Spike 主要進場時框）
}

# 反轉點篩選參數（依時框調整）
#   swing_order    : argrelextrema 的鄰域大小（越大越少雜訊）
#   min_prior_drop : 低點前需要的跌幅（空頭段）
#   min_post_rally : 低點後需要的漲幅（反轉確認）
#   window         : 前後觀察窗（找第一低、支撐、型態）
PARAMS = {
    'daily': dict(swing_order=5, min_prior_drop=0.030, min_post_rally=0.020, window=20),
    '1h':    dict(swing_order=5, min_prior_drop=0.020, min_post_rally=0.010, window=30),
    '30m':   dict(swing_order=4, min_prior_drop=0.015, min_post_rally=0.008, window=25),
    '15m':   dict(swing_order=4, min_prior_drop=0.012, min_post_rally=0.006, window=30),
    '5m':    dict(swing_order=5, min_prior_drop=0.008, min_post_rally=0.004, window=40),
    # 5m: 跌幅門檻放低（0.8%），漲幅門檻放低（0.4%）；window 放大到 40 根覆蓋更多前後結構
}

# ---- W底 / 破底翻 判定參數 ----
W_TOLERANCE    = 0.006   # 兩低點視為「同一水位」的價位容差（0.6%）
REBOUND_MIN    = 0.005   # 兩低點之間的反彈幅度門檻（中間峰值比低點高 >= 0.5%）
MIN_SEPARATION = 3       # 第二低點至少在第一低點後 N 根K棒
RECOVER_BARS   = 3       # 破底後幾根K棒內「收盤收回支撐之上」才算一次破底翻嘗試
BREAK_TOL      = 0.0008  # 收盤價需跌破 支撐×(1-BREAK_TOL) 才算真的破底（過濾雜訊）
COMPLEX_MIN    = 3       # 測試支撐的低點數 >= 此值 → 複雜底

CHART_OUTPUT   = True     # 是否輸出圖表


# =========================================================
# 1. 資料下載
# =========================================================

def download_data(symbol, period, interval):
    if not _HAS_YF:
        print("    ✗ 未安裝 yfinance，無法下載")
        return None
    print(f"  下載 {symbol} [{interval}] {period}...")
    try:
        df = yf.download(symbol, period=period, interval=interval,
                         progress=False, auto_adjust=True)
        if df is None or len(df) == 0:
            print("    ✗ 回傳空資料")
            return None
        # 修正 MultiIndex 欄位（yfinance 新版）
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
        print(f"    ✓ {len(df)} 根K棒，{df.index[0].date()} → {df.index[-1].date()}")
        return df
    except Exception as e:
        print(f"    ✗ 下載失敗：{e}")
        return None


# =========================================================
# 2. 擺動高/低點偵測
# =========================================================

def _dedupe(idx, order):
    """去除彼此太靠近（< order）的極值，保留第一個。"""
    result, prev = [], -10**9
    for i in idx:
        if i - prev >= order:
            result.append(int(i))
            prev = i
    return result


def find_swing_lows(low: np.ndarray, order: int = 5) -> list:
    idx = argrelextrema(np.asarray(low), np.less_equal, order=order)[0]
    return _dedupe(idx, order)


def find_swing_highs(high: np.ndarray, order: int = 5) -> list:
    idx = argrelextrema(np.asarray(high), np.greater_equal, order=order)[0]
    return _dedupe(idx, order)


# =========================================================
# 3. 重大反轉點判斷
# =========================================================

def is_major_reversal(df, low_i, min_prior_drop, min_post_rally, lookback=20, lookahead=30):
    """
    low_i 是「真正反轉點」的候選（後面接大漲）：
      - 低點前 lookback 根的最高點 → 低點：跌幅 >= min_prior_drop
      - 低點後 lookahead 根的最高點 → 低點：漲幅 >= min_post_rally
    """
    if low_i < lookback or low_i + lookahead >= len(df):
        return False
    low_p = df['Low'].iloc[low_i]
    prior_high = df['High'].iloc[low_i - lookback: low_i].max()
    post_high  = df['High'].iloc[low_i + 1: low_i + lookahead + 1].max()
    if prior_high <= 0 or low_p <= 0:
        return False
    drop  = (prior_high - low_p) / prior_high
    rally = (post_high - low_p) / low_p
    return drop >= min_prior_drop and rally >= min_post_rally


# =========================================================
# 4. 破底翻機制（問題 1 + 3 的核心）
# =========================================================

def find_support_before(df, before_i, window, swing_order):
    """
    問題(1)：用「最近的局部低點」當支撐，而非 percentile 亂估。
    回傳 before_i 之前、window 範圍內，最近一個擺動低點的價位（被防守的地板）。
    找不到就回傳 None。
    """
    seg_start = max(0, before_i - window)
    if before_i - seg_start < swing_order * 2 + 1:
        return None
    seg_low = df['Low'].iloc[seg_start:before_i].values
    lows = find_swing_lows(seg_low, order=swing_order)
    if not lows:
        return None
    # 取「最近」的擺動低點作為當下被防守的支撐
    return float(seg_low[lows[-1]])


def breakdown_recovery(df, a, b, support):
    """
    在 [a, b) 區間內尋找一次完整的「破底→收回」：
      收盤跌破 support×(1-BREAK_TOL)  →  RECOVER_BARS 根內 收盤收回 support 之上。
    回傳 (break_i, recover_i) 絕對索引；找不到回傳 None。
    """
    if support is None:
        return None
    a = max(0, a); b = min(len(df), b)
    closes = df['Close'].values
    thresh = support * (1 - BREAK_TOL)
    i = a
    while i < b:
        if closes[i] < thresh:                       # 破底
            j_end = min(len(df), i + RECOVER_BARS + 1)
            for j in range(i + 1, j_end):
                if closes[j] > support:              # 收回
                    return (i, j)
            # 這次破底沒收回，繼續往後找下一次破底
            i = j_end
        else:
            i += 1
    return None


# =========================================================
# 5. 底部型態分類（問題 2 + 3）
# =========================================================

class BottomPattern:
    V_SHAPE  = 'V型（直接破底翻成功）'
    W_BOTTOM = 'W底（失敗後二次測試）'
    COMPLEX  = '複雜底（多次測試）'
    UNCLEAR  = '不明確'


def classify_bottom(df, low_i, params):
    """
    low_i = is_major_reversal 判定出的「真正反轉點」（W底的第二低點）。
    因此往「回」看，找第一低點（第一次試底），驗證 W 結構與破底翻失敗序列。

    回傳 dict，含型態、兩低點、間隔、反彈高度、破底翻失敗旗標與支撐。
    """
    window     = params['window']
    swing_ord  = params['swing_order']
    n = len(df)
    base = dict(pattern=BottomPattern.UNCLEAR, low1_i=None, low2_i=low_i,
                low1_p=None, low2_p=float(df['Low'].iloc[low_i]),
                bars_between=None, rebound_pct=None, n_tests=1,
                has_pdt_fail=False, support=None, timestamp=df.index[low_i])

    if low_i < window or low_i + MIN_SEPARATION >= n:
        return base

    low2_p = float(df['Low'].iloc[low_i])

    # --- 往回找「同水位」的擺動低點作為第一低點 ---
    back_start = max(0, low_i - window)
    seg_low = df['Low'].iloc[back_start:low_i].values
    cand = find_swing_lows(seg_low, order=swing_ord)
    cand_abs = [back_start + c for c in cand]

    tests = []   # 所有落在同一水位的低點（含 low_i），用來分 V/W/複雜
    for ci in cand_abs:
        p = float(df['Low'].iloc[ci])
        if abs(p - low2_p) / low2_p <= W_TOLERANCE and (low_i - ci) >= MIN_SEPARATION:
            tests.append(ci)
    tests.append(low_i)
    tests = sorted(set(tests))

    # 找出「第一低點」= 最靠近 low_i、且中間有足夠反彈的那個同水位低點
    low1_i = None
    rebound_pct = None
    for ci in reversed(tests[:-1]):           # 由近而遠試
        seg_high = df['High'].iloc[ci: low_i + 1].max()
        base_low = max(float(df['Low'].iloc[ci]), low2_p)   # 以較高的低點為基準較保守
        rb = (seg_high - base_low) / base_low
        if rb >= REBOUND_MIN:
            low1_i = ci
            rebound_pct = rb
            break

    if low1_i is None:
        # 沒有合格的第一低點 → V型（單一次觸底即反轉）
        base['pattern'] = BottomPattern.V_SHAPE
        return base

    low1_p = float(df['Low'].iloc[low1_i])

    # 計算「同水位測試次數」以區分 W / 複雜底
    valid_tests = [t for t in tests if t <= low_i]
    n_tests = len(valid_tests)
    pattern = BottomPattern.COMPLEX if n_tests >= COMPLEX_MIN else BottomPattern.W_BOTTOM

    # --- 問題(3)：完整破底翻失敗序列 ---
    #   [支撐]→[破底]→[收回](第一低附近，失敗) →[再破底](第二低/W右腳)→[收回站穩]
    support = find_support_before(df, low1_i, window, swing_ord)
    # 支撐必須「高於第一低」才代表是被跌破的地板；否則視為無有效支撐
    if support is not None and support <= low1_p * (1 + BREAK_TOL):
        support = None
    has_pdt_fail = False
    if support is not None:
        # 第一次嘗試：low1 附近 破底→收回
        first_try = breakdown_recovery(df, low1_i - 1, low1_i + RECOVER_BARS + 1, support)
        if first_try is not None:
            _, rec1 = first_try
            # 再破底：收回之後、到第二低點之間，收盤又跌破支撐（W 右腳）
            re_break = breakdown_recovery(df, rec1 + 1, low_i + 2, support)
            if re_break is not None:
                # 最終站穩：反轉點之後 收盤重新站上支撐（is_major 已保證後續大漲，這裡確認站回）
                after = df['Close'].iloc[low_i: min(n, low_i + RECOVER_BARS + 2)].values
                if (after > support).any():
                    has_pdt_fail = True

    base.update(pattern=pattern, low1_i=low1_i, low1_p=low1_p,
                bars_between=low_i - low1_i, rebound_pct=rebound_pct,
                n_tests=n_tests, has_pdt_fail=has_pdt_fail, support=support)
    return base


# =========================================================
# 6. 假陽性率：獨立掃描所有「雙底形態」（問題 5）
# =========================================================

def scan_double_bottom_outcomes(df, params):
    """
    不看是否真的反轉，先找出所有「兩個同水位低點 + 中間反彈」的雙底形態，
    再往後看它是否真的反轉，統計假陽性率。

    成功（反轉）：第二低點後 lookahead 根內，最高點較第二低點漲幅 >= min_post_rally，
                 且期間收盤未再跌破第二低點 fail_drop 以上。
    失敗（續跌）：第二低點後 收盤跌破第二低點 × (1 - fail_drop)。
    """
    window   = params['window']
    order    = params['swing_order']
    rally_th = params['min_post_rally']
    fail_drop = max(0.004, rally_th * 0.6)     # 跌破此幅度視為假訊號
    lookahead = window

    lows = find_swing_lows(df['Low'].values, order=order)
    formations, success, fail = 0, 0, 0
    for k in range(1, len(lows)):
        i1, i2 = lows[k - 1], lows[k]
        if i2 - i1 < MIN_SEPARATION:
            continue
        p1, p2 = float(df['Low'].iloc[i1]), float(df['Low'].iloc[i2])
        if abs(p1 - p2) / p2 > W_TOLERANCE:
            continue
        mid_high = float(df['High'].iloc[i1:i2 + 1].max())
        if (mid_high - max(p1, p2)) / max(p1, p2) < REBOUND_MIN:
            continue
        if i2 + lookahead >= len(df):
            continue

        formations += 1
        fut_close = df['Close'].iloc[i2 + 1: i2 + lookahead + 1].values
        fut_high  = df['High'].iloc[i2 + 1: i2 + lookahead + 1].values
        broke_down = (fut_close < p2 * (1 - fail_drop))
        reached_rally = (fut_high >= p2 * (1 + rally_th))

        # 先發生哪一個？
        first_break = np.argmax(broke_down) if broke_down.any() else 10**9
        first_rally = np.argmax(reached_rally) if reached_rally.any() else 10**9
        if first_rally < first_break:
            success += 1
        elif first_break < 10**9:
            fail += 1
        # 兩者都沒發生 → 不計（盤整未定）

    fp_rate = (fail / formations) if formations else None
    return dict(formations=formations, success=success, fail=fail, fp_rate=fp_rate)


# =========================================================
# 7. 單一時框主分析
# =========================================================

def analyze(df, label, params):
    print(f"\n{'='*58}")
    print(f"  分析：{label}")
    print(f"{'='*58}")

    swing_lows = find_swing_lows(df['Low'].values, order=params['swing_order'])
    print(f"  局部低點      ：{len(swing_lows)} 個")

    reversals = [i for i in swing_lows
                 if is_major_reversal(df, i,
                                      params['min_prior_drop'],
                                      params['min_post_rally'],
                                      lookback=params['window'],
                                      lookahead=params['window'])]
    print(f"  重大反轉點    ：{len(reversals)} 個")
    if not reversals:
        print("  資料不足，跳過。")
        return []

    results = [classify_bottom(df, i, params) for i in reversals]
    results = [r for r in results if r['pattern'] != BottomPattern.UNCLEAR]
    total = len(results)
    if total == 0:
        print("  無有效型態，跳過。")
        return []

    v_list  = [r for r in results if r['pattern'] == BottomPattern.V_SHAPE]
    w_list  = [r for r in results if r['pattern'] == BottomPattern.W_BOTTOM]
    cx_list = [r for r in results if r['pattern'] == BottomPattern.COMPLEX]
    wc_list = w_list + cx_list                       # 廣義「需二次以上測試」
    w_pdt   = [r for r in wc_list if r['has_pdt_fail']]

    def pct(x): return f"{x/total*100:4.1f}%"

    print(f"\n  ┌────────────────────────────────────────────┐")
    print(f"  │  有效反轉點               : {total:>4} 個          │")
    print(f"  │  V型（直接破底翻成功）    : {len(v_list):>4} ({pct(len(v_list))})     │")
    print(f"  │  W底（失敗後二次測試）    : {len(w_list):>4} ({pct(len(w_list))})     │")
    print(f"  │  複雜底（多次測試）       : {len(cx_list):>4} ({pct(len(cx_list))})     │")
    if wc_list:
        print(f"  │  ├ 其中含完整破底翻失敗序列: {len(w_pdt):>4} ({len(w_pdt)/len(wc_list)*100:4.1f}% of 二次+) │")
    print(f"  └────────────────────────────────────────────┘")

    # ---- 問題(5) 額外統計指標 ----
    bars = [r['bars_between'] for r in wc_list if r['bars_between'] is not None]
    rebs = [r['rebound_pct']  for r in wc_list if r['rebound_pct']  is not None]
    if bars:
        print(f"\n  第一低→第二低 間隔K棒：平均 {np.mean(bars):.1f}｜中位 {np.median(bars):.0f}"
              f"｜範圍 {min(bars)}~{max(bars)}")
    if rebs:
        print(f"  W底中間反彈高度      ：平均 {np.mean(rebs)*100:.2f}%"
              f"｜中位 {np.median(rebs)*100:.2f}%")

    fp = scan_double_bottom_outcomes(df, params)
    if fp['formations']:
        fpr = f"{fp['fp_rate']*100:.1f}%" if fp['fp_rate'] is not None else "n/a"
        print(f"  雙底形態假陽性率     ：{fp['fail']}/{fp['formations']} = {fpr}"
              f"（成功反轉 {fp['success']}）")

    # ---- 假說結論 ----
    w_share = len(wc_list) / total
    print(f"\n  → 假說驗證：需二次以上測試(W底+複雜底)佔比 = {w_share*100:.1f}%")
    if w_share > 0.5:
        print(f"  ✅ 支持假說：多數反轉點需二次測試才完成（等W底第二低再進）")
    elif w_share > 0.35:
        print(f"  ⚠️  部分支持：W底佔相當比例，但V型仍不少")
    else:
        print(f"  ❌ 不支持：多數反轉為V型，第一次破底翻即可進")

    # 掛上時框標籤，供多時框對齊使用
    for r in results:
        r['tf'] = label
    return results


# =========================================================
# 8. 多時框對齊（問題 4）
# =========================================================

def _naive(ts):
    """統一成 tz-naive（UTC）以便跨時框比較（日K tz-naive、分鐘K tz-aware）。"""
    ts = pd.Timestamp(ts)
    if ts.tzinfo is not None:
        ts = ts.tz_convert('UTC').tz_localize(None)
    return ts


def align_multiframe(all_results):
    """
    先以日K重大反轉為錨，再到 1h/30m/15m 找「時間上鄰近」的反轉點，
    比較同一事件在不同時框的底部微結構。
    （日K 5年 與 分鐘資料 60天 多半不重疊，僅近期會對齊得上。）
    """
    if 'daily' not in all_results:
        return
    daily = all_results['daily'][1]
    if not daily:
        return

    print("\n" + "=" * 58)
    print("  多時框對齊：日K重大反轉 → 對照較小時框底部型態")
    print("=" * 58)

    lower = [(tf, all_results[tf][1]) for tf in ('1h', '30m', '15m') if tf in all_results]
    matched = 0
    for dr in daily:
        d_ts = _naive(dr['timestamp'])
        row = f"  {str(d_ts.date())}  日K:{dr['pattern'][:2]}"
        found = False
        for tf, res in lower:
            # 找同一天（±1.5日）內、時間最近的反轉
            near = [r for r in res
                    if abs((_naive(r['timestamp']) - d_ts).total_seconds()) <= 86400 * 1.5]
            if near:
                near.sort(key=lambda r: abs((_naive(r['timestamp']) - d_ts).total_seconds()))
                m = near[0]
                tag = '★' if m['has_pdt_fail'] else ' '
                row += f" ｜{tf}:{m['pattern'][:2]}{tag}"
                found = True
        if found:
            matched += 1
            print(row)
    if matched == 0:
        print("  （日K反轉點與分鐘資料時間範圍不重疊，無法對齊——")
        print("    Yahoo 分鐘資料僅 60 天。如需完整對齊，需接券商/付費歷史資料。）")
    else:
        print(f"\n  對齊成功 {matched} 個事件（★ = 該時框偵測到完整破底翻失敗序列）")


# =========================================================
# 9. 視覺化
# =========================================================

def plot_sample(df, results, label, n_samples=6):
    if not results or not CHART_OUTPUT:
        return
    w_cases = [r for r in results if r['pattern'] in
               (BottomPattern.W_BOTTOM, BottomPattern.COMPLEX)][:n_samples // 2]
    v_cases = [r for r in results if r['pattern'] == BottomPattern.V_SHAPE][:n_samples - len(w_cases)]
    samples = w_cases + v_cases
    if not samples:
        return

    cols = 3
    rows = max(1, (len(samples) + cols - 1) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(18, rows * 4))
    fig.suptitle(f'{label}  —  底部型態樣本', fontsize=14)
    axes = np.atleast_1d(axes).flatten()

    for ax, r in zip(axes, samples):
        i = r['low2_i']
        start = max(0, i - 25)
        end   = min(len(df), i + 25)
        seg = df.iloc[start:end]
        x = range(len(seg))

        ax.plot(x, seg['Close'].values, color='gray', linewidth=0.9)
        ax.fill_between(x, seg['Low'].values, seg['High'].values, alpha=0.15, color='gray')

        # 支撐線
        if r['support'] is not None:
            ax.axhline(r['support'], color='steelblue', linestyle=':', linewidth=1, label='支撐')

        # 第二低點（真正反轉）— 紫
        i2 = i - start
        ax.scatter(i2, seg['Low'].iloc[i2], color='purple', zorder=5, s=90)
        ax.axvline(i2, color='purple', linestyle='--', linewidth=1.1, label='第二低(反轉)')

        # 第一低點 — 黃
        if r['low1_i'] is not None:
            i1 = r['low1_i'] - start
            if 0 <= i1 < len(seg):
                ax.scatter(i1, seg['Low'].iloc[i1], color='orange', zorder=5, s=90)
                ax.axvline(i1, color='orange', linestyle='--', linewidth=1.1, label='第一低(試底)')

        pdt = '｜含破底翻失敗' if r['has_pdt_fail'] else ''
        title = f"{r['pattern']}{pdt}\n{str(r['timestamp'])[:16]} @{r['low2_p']:.1f}"
        ax.set_title(title, fontsize=8)
        ax.tick_params(labelsize=7)
        ax.legend(fontsize=6, loc='upper left')

    for ax in axes[len(samples):]:
        ax.set_visible(False)

    plt.tight_layout()
    out = f'reversal_patterns_{label.replace(" ", "_")}.png'
    plt.savefig(out, dpi=120, bbox_inches='tight')
    plt.close()
    print(f"  圖表已儲存：{out}")


def plot_interval_histogram(all_results):
    """問題(5)：W底間隔K棒數分佈直方圖（彙總各時框）。"""
    if not CHART_OUTPUT:
        return
    fig, axes = plt.subplots(1, len(all_results), figsize=(5 * len(all_results), 4), squeeze=False)
    plotted = False
    for ax, (tf, (df, res)) in zip(axes[0], all_results.items()):
        bars = [r['bars_between'] for r in res
                if r['pattern'] in (BottomPattern.W_BOTTOM, BottomPattern.COMPLEX)
                and r['bars_between'] is not None]
        if bars:
            ax.hist(bars, bins=range(min(bars), max(bars) + 2), color='mediumpurple',
                    edgecolor='white')
            ax.axvline(np.mean(bars), color='red', linestyle='--',
                       label=f'均值 {np.mean(bars):.1f}')
            ax.legend(fontsize=8)
            plotted = True
        ax.set_title(f'{tf} 第一低→第二低 間隔', fontsize=10)
        ax.set_xlabel('K棒數'); ax.set_ylabel('次數')
    if plotted:
        plt.tight_layout()
        plt.savefig('reversal_interval_hist.png', dpi=120, bbox_inches='tight')
        print("  間隔分佈圖已儲存：reversal_interval_hist.png")
    plt.close()


# =========================================================
# 10. 彙總
# =========================================================

def print_summary(all_results):
    print("\n" + "=" * 58)
    print("  彙總：各時框型態比例")
    print("=" * 58)
    print(f"  {'時框':<6}{'反轉':>6}{'V型%':>9}{'W底%':>9}{'複雜%':>9}{'二次+%':>9}{'破底翻失敗%':>12}")
    print(f"  {'-'*58}")
    agg = dict(total=0, v=0, w=0, cx=0, pdt=0, wc=0)
    for tf, (df, res) in all_results.items():
        if not res:
            continue
        t  = len(res)
        v  = sum(1 for r in res if r['pattern'] == BottomPattern.V_SHAPE)
        w  = sum(1 for r in res if r['pattern'] == BottomPattern.W_BOTTOM)
        cx = sum(1 for r in res if r['pattern'] == BottomPattern.COMPLEX)
        wc = w + cx
        pdt = sum(1 for r in res if r['has_pdt_fail'])
        agg['total'] += t; agg['v'] += v; agg['w'] += w
        agg['cx'] += cx; agg['pdt'] += pdt; agg['wc'] += wc
        pdt_share = f"{pdt/wc*100:.1f}%" if wc else "—"
        print(f"  {tf:<6}{t:>6}{v/t*100:>8.1f}%{w/t*100:>8.1f}%{cx/t*100:>8.1f}%"
              f"{wc/t*100:>8.1f}%{pdt_share:>12}")

    if agg['total']:
        T = agg['total']; WC = agg['wc']
        print(f"  {'-'*58}")
        print(f"  {'合計':<6}{T:>6}{agg['v']/T*100:>8.1f}%{agg['w']/T*100:>8.1f}%"
              f"{agg['cx']/T*100:>8.1f}%{WC/T*100:>8.1f}%"
              f"{(agg['pdt']/WC*100 if WC else 0):>11.1f}%")
        print("\n" + "=" * 58)
        print("  最終結論")
        print("=" * 58)
        print(f"  跨時框 需二次以上測試(W底+複雜底) 佔比 = {WC/T*100:.1f}%")
        print(f"  其中 具完整『破底翻失敗序列』佔二次+的 {(agg['pdt']/WC*100 if WC else 0):.1f}%")
        if WC / T > 0.5:
            print("  ✅ 支持假說 → 建議 trend_filter.md 第三關：不在第一次破底翻進場，")
            print("     等W底第二低點站回支撐再進。")
        elif WC / T > 0.35:
            print("  ⚠️  部分支持 → 建議：第一次破底翻可小倉試單，主倉等W底第二低。")
        else:
            print("  ❌ 不支持 → 維持現行SOP，第一次破底翻即可進場。")


# =========================================================
# 11. 自我驗證（合成資料，免連網）
# =========================================================

def _make_synthetic():
    """造一段含 2個W底、1個V底 的假資料，驗證分類邏輯是否運作。"""
    rng = np.random.default_rng(7)
    seg = []

    def leg(start, end, n):
        return list(np.linspace(start, end, n) + rng.normal(0, start * 0.0008, n))

    price = []
    price += leg(20000, 20000, 20)          # 盤整
    # --- W底 1：支撐→破底→收回→再破底→反轉 ---
    price += leg(20000, 19660, 12)          # 下跌到支撐區
    price += leg(19660, 19650, 6)           # 支撐盤整（形成被防守的地板 ~19650）
    price += leg(19650, 19560, 4)           # 破底（跌破支撐）→ 第一低
    price += leg(19560, 19760, 8)           # 收回站上支撐（第一次破底翻，隨後失敗）
    price += leg(19760, 19555, 8)           # 再破底（W右腳，又跌破支撐）
    price += leg(19555, 19540, 2)           # 第二低
    price += leg(19540, 20200, 25)          # 大反轉
    # --- V底：直接反轉 ---
    price += leg(20200, 19900, 12)          # 下跌
    price += leg(19900, 19880, 2)           # 單一低點
    price += leg(19880, 20500, 25)          # 直接大漲
    # --- W底 2 ---
    price += leg(20500, 20090, 12)
    price += leg(20090, 20080, 6)           # 支撐盤整 ~20080
    price += leg(20080, 20030, 4)           # 破底 → 第一低
    price += leg(20030, 20250, 8)           # 收回站上支撐
    price += leg(20250, 20035, 8)           # 再破底（W右腳）
    price += leg(20035, 20025, 2)           # 第二低
    price += leg(20025, 20700, 25)          # 反轉
    price += leg(20700, 20700, 20)

    close = np.array(price)
    n = len(close)
    high = close + np.abs(rng.normal(0, 8, n)) + 5
    low  = close - np.abs(rng.normal(0, 8, n)) - 5
    open_ = np.r_[close[0], close[:-1]]
    idx = pd.date_range('2026-01-01 09:30', periods=n, freq='5min')
    return pd.DataFrame({'Open': open_, 'High': high, 'Low': low,
                         'Close': close, 'Volume': 1000}, index=idx)


def run_selftest():
    print("=" * 58)
    print("  自我驗證模式（合成資料，免連網）")
    print("=" * 58)
    df = _make_synthetic()
    params = dict(swing_order=3, min_prior_drop=0.012, min_post_rally=0.010, window=25)
    res = analyze(df, 'SYNTHETIC', params)
    patt = [r['pattern'][:2] for r in res]
    print(f"\n  偵測到型態序列：{patt}")
    n_w = sum(1 for r in res if r['pattern'] in (BottomPattern.W_BOTTOM, BottomPattern.COMPLEX))
    n_pdt = sum(1 for r in res if r['has_pdt_fail'])
    ok = n_w >= 2 and n_pdt >= 1
    print(f"  預期：至少2個W底、至少1個破底翻失敗序列")
    print(f"  實得：W/複雜 {n_w} 個、破底翻失敗 {n_pdt} 個  → {'✅ 通過' if ok else '❌ 未通過'}")
    plot_sample(df, res, 'SYNTHETIC')
    return ok


# =========================================================
# 12. 主程式
# =========================================================

def main():
    if '--selftest' in sys.argv:
        run_selftest()
        return

    print("=" * 58)
    print("  破底翻失敗 → W底 → 反轉  假說驗證")
    print("  資料：Yahoo Finance (NQ=F)")
    print("=" * 58)

    all_results = {}
    for tf_label, (symbol, period, interval) in SYMBOLS.items():
        params = PARAMS[tf_label]
        df = download_data(symbol, period, interval)
        if df is None or len(df) < 60:
            print(f"  [{tf_label}] 資料不足，略過")
            continue
        results = analyze(df, tf_label, params)
        all_results[tf_label] = (df, results)
        if CHART_OUTPUT and results:
            plot_sample(df, results, tf_label)

    if not all_results:
        print("\n⚠️  沒有任何時框成功取得資料。")
        print("   （可能是無網路或 Yahoo 限流）可先跑：python reversal_pattern_study.py --selftest")
        return

    align_multiframe(all_results)
    plot_interval_histogram(all_results)
    print_summary(all_results)
    print("\n完成。若 CHART_OUTPUT=True，圖表存在當前目錄。")


if __name__ == '__main__':
    main()
