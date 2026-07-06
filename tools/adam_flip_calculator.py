"""
翻亞當計算器（Adam Flip / Second Mirror Image Calculator）
==========================================================
用途：評估走勢滿足距離（出場目標區）與走勢可能結束的區域

依據：Jack Li 亞當理論新手練習系列
核心：翻亞當是「計畫工具」，不是進場依據。進場仍靠破底翻訊號。

使用方式：
    calc = AdamFlipCalculator(df)
    flip = calc.calculate(flip_idx=100, direction='bearish', mode='auto')
    print(flip.summary())
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Literal

Direction = Literal['bullish', 'bearish']
MeasureMode = Literal['consolidation', 'n_pattern', 'gap', 'auto']


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Consolidation:
    high: float
    low: float
    start_idx: int
    end_idx: int

    @property
    def height(self) -> float:
        return self.high - self.low


@dataclass
class AdamFlipResult:
    direction: Direction
    flip_idx: int
    flip_close: float           # 翻立K 收盤（翻立點）
    measure_mode: MeasureMode   # 使用哪種量測模式
    origin_high: float          # 量測基準上緣
    origin_low: float           # 量測基準下緣
    measurement: float          # 基準距離
    target: float               # 滿足區中心目標
    zone_high: float            # 滿足區上緣
    zone_low: float             # 滿足區下緣
    confidence: int             # 0-3 信心分
    sr_levels: List[float] = field(default_factory=list)  # 重合的S/R水位

    # ------------------------------------------------------------------ #
    def summary(self) -> str:
        mode_labels = {
            'consolidation': '盤整翻盤整',
            'n_pattern':     'N字型轉折',
            'gap':           '缺口/大K棒（實體配對）',
        }
        conf_labels = {0: '低', 1: '中', 2: '高', 3: '極高（多重確認）'}
        arrow = '↓' if self.direction == 'bearish' else '↑'

        lines = [
            '=' * 50,
            f'翻亞當結果 [{self.direction.upper()}]  {arrow}',
            '=' * 50,
            f'翻立K 索引    : #{self.flip_idx}',
            f'翻立K 收盤    : {self.flip_close:.2f}',
            f'量測模式      : {mode_labels.get(self.measure_mode, self.measure_mode)}',
            f'基準範圍      : {self.origin_low:.2f} ~ {self.origin_high:.2f}',
            f'基準距離      : {self.measurement:.2f} 點',
            '',
            f'🎯 滿足區目標 : {self.target:.2f}',
            f'   滿足區上緣 : {self.zone_high:.2f}',
            f'   滿足區下緣 : {self.zone_low:.2f}',
            '',
            f'信心評分      : {self.confidence}/3 ({conf_labels[self.confidence]})',
        ]
        if self.sr_levels:
            lines.append(f'重合S/R水位  : {[round(x, 2) for x in self.sr_levels]}')
        lines.append('=' * 50)
        return '\n'.join(lines)

    def exit_plan(self) -> str:
        """產生出場計畫文字"""
        is_bear = self.direction == 'bearish'

        lines = ['--- 出場計畫 ---']
        if is_bear:
            lines += [
                f'目標區間 : {self.zone_low:.2f} ~ {self.zone_high:.2f}',
                f'持有策略 : 下跌過程不提前出場，等進入目標區',
                f'到達目標 : 觀察多方翻立訊號（破底翻機會）',
            ]
        else:
            lines += [
                f'目標區間 : {self.zone_low:.2f} ~ {self.zone_high:.2f}',
                f'持有策略 : 上漲過程不提前出場，等進入目標區',
                f'到達目標 : 觀察空方翻立訊號（出場或轉空）',
            ]

        if self.confidence >= 2:
            lines.append(f'⚡ 高信心區 ({self.confidence}/3)：可全倉出場，同時準備反向進場')
        else:
            lines.append(f'部分出場   ：到達目標出 1/2，剩餘單等下一個翻立確認')

        return '\n'.join(lines)


@dataclass
class MultiTFResult:
    small_flip: AdamFlipResult
    large_flip: AdamFlipResult
    overlap: bool
    overlap_zone: Optional[Tuple[float, float]]

    def summary(self) -> str:
        lines = ['=== 多時框疊加結果 ===']
        lines.append(f'小時框目標 : {self.small_flip.target:.2f}')
        lines.append(f'大時框目標 : {self.large_flip.target:.2f}')
        if self.overlap:
            low, high = self.overlap_zone
            lines += [
                '',
                '⚠️  大小亞當滿足區重合！',
                f'   強力區間 : {low:.2f} ~ {high:.2f}',
                '   → 容易亂掃洗盤，建議提前縮停損或部分出場',
                '   → 到達此區先出 1/2，等翻立訊號再決定全出/反向',
            ]
        else:
            lines += [
                '',
                '→ 分兩段出場策略：',
                f'   第一目標（小時框）: {self.small_flip.target:.2f} → 出 1/2',
                f'   第二目標（大時框）: {self.large_flip.target:.2f} → 全出',
            ]
        return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main Calculator
# ---------------------------------------------------------------------------

class AdamFlipCalculator:
    """
    翻亞當（第二映像圖）計算器

    Parameters
    ----------
    df : pd.DataFrame
        OHLC 資料，欄位需包含 ['open', 'high', 'low', 'close']
        選填：['volume', 'ma20', 'ma60', 'ma240']
    swing_n : int
        擺動高低點的回望K棒數（左右各 n 根確認）
    consolidation_min : int
        盤整最少需幾根 K 棒
    consolidation_ratio : float
        盤整判斷：total_range / (avg_candle_range * candle_count) ≤ ratio
    zone_buffer : float
        滿足區緩衝帶（預設 0.003 = 0.3%）
    sr_tolerance : float
        S/R 對齊容差（預設 0.005 = 0.5%）
    """

    def __init__(
        self,
        df: pd.DataFrame,
        swing_n: int = 3,
        consolidation_min: int = 3,
        consolidation_ratio: float = 0.6,
        zone_buffer: float = 0.003,
        sr_tolerance: float = 0.005,
        large_candle_mult: float = 3.0,
    ):
        self.df = df.copy().reset_index(drop=True)
        self.swing_n = swing_n
        self.consolidation_min = consolidation_min
        self.consolidation_ratio = consolidation_ratio
        self.zone_buffer = zone_buffer
        self.sr_tolerance = sr_tolerance
        self.large_candle_mult = large_candle_mult

        # 預計算擺動點
        self._compute_swings()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def calculate(
        self,
        flip_idx: int,
        direction: Direction,
        mode: MeasureMode = 'auto',
    ) -> AdamFlipResult:
        """
        計算翻亞當目標

        Parameters
        ----------
        flip_idx : int
            翻立訊號的 K 棒索引（第一根實體明確突破關鍵位的那根）
        direction : 'bullish' | 'bearish'
            翻立方向
        mode : 'auto' | 'consolidation' | 'n_pattern' | 'gap'
            量測模式。'auto' 自動選擇。

        Returns
        -------
        AdamFlipResult
        """
        candle = self.df.iloc[flip_idx]
        flip_close = candle['close']

        # --- Step 1: 決定量測模式 ---
        if mode == 'auto':
            if self._is_gap_or_large(flip_idx):
                mode = 'gap'
            else:
                con = self._find_consolidation(flip_idx)
                if con is not None:
                    mode = 'consolidation'
                else:
                    mode = 'n_pattern'

        # --- Step 2: 量測 ---
        if mode == 'consolidation':
            con = self._find_consolidation(flip_idx)
            if con is None:
                # fallback
                mode = 'n_pattern'
            else:
                measurement = con.height
                origin_high = con.high
                origin_low = con.low
                # 翻立點 = 被突破的邊界
                flip_level = con.low if direction == 'bearish' else con.high

        if mode == 'n_pattern':
            swing = self._find_n_pattern_swing(flip_idx, direction)
            if swing is None:
                # 最後 fallback：用翻立K 實體大小
                mode = 'gap'
            else:
                A, B = swing
                measurement = abs(A - B)
                if direction == 'bearish':
                    origin_high = A
                    origin_low = B
                    flip_level = B
                else:
                    origin_low = A
                    origin_high = B
                    flip_level = B

        if mode == 'gap':
            body_high = max(candle['open'], candle['close'])
            body_low = min(candle['open'], candle['close'])
            measurement = body_high - body_low
            origin_high = body_high
            origin_low = body_low
            flip_level = body_low if direction == 'bearish' else body_high

        # --- Step 3: 計算目標 ---
        if direction == 'bearish':
            target = flip_level - measurement
        else:
            target = flip_level + measurement

        zone_high = target * (1 + self.zone_buffer)
        zone_low = target * (1 - self.zone_buffer)

        # --- Step 4: 信心評分 ---
        confidence, sr_levels = self._score_confidence(target, flip_idx)

        return AdamFlipResult(
            direction=direction,
            flip_idx=flip_idx,
            flip_close=flip_close,
            measure_mode=mode,
            origin_high=origin_high,
            origin_low=origin_low,
            measurement=measurement,
            target=target,
            zone_high=zone_high,
            zone_low=zone_low,
            confidence=confidence,
            sr_levels=sr_levels,
        )

    def multi_timeframe(
        self,
        small_flip: AdamFlipResult,
        large_flip: AdamFlipResult,
        overlap_threshold: float = 0.005,
    ) -> MultiTFResult:
        """
        檢查大小時框亞當目標是否重合

        Parameters
        ----------
        small_flip : AdamFlipResult
            小時框（5m / 15m）翻亞當結果
        large_flip : AdamFlipResult
            大時框（60m / 日K）翻亞當結果
        overlap_threshold : float
            目標差距 / 平均值 ≤ threshold 視為重合（預設 0.5%）
        """
        avg = (small_flip.target + large_flip.target) / 2
        distance_ratio = abs(small_flip.target - large_flip.target) / avg

        overlap = distance_ratio <= overlap_threshold
        overlap_zone = None
        if overlap:
            overlap_zone = (
                min(small_flip.zone_low, large_flip.zone_low),
                max(small_flip.zone_high, large_flip.zone_high),
            )

        return MultiTFResult(
            small_flip=small_flip,
            large_flip=large_flip,
            overlap=overlap,
            overlap_zone=overlap_zone,
        )

    # ------------------------------------------------------------------ #
    # 批次掃描：自動找翻立訊號（簡化版）
    # ------------------------------------------------------------------ #

    def scan_flips(
        self,
        direction: Direction,
        lookback: int = 200,
        mode: MeasureMode = 'auto',
    ) -> List[AdamFlipResult]:
        """
        在最近 lookback 根 K 棒內掃描翻立訊號並計算目標

        翻立判斷（簡化）：
        - bearish: 收盤創近期新低（比過去 swing_n 根低）
        - bullish: 收盤創近期新高（比過去 swing_n 根高）
        """
        results = []
        start = max(self.swing_n + 1, len(self.df) - lookback)

        for i in range(start, len(self.df) - self.swing_n):
            candle = self.df.iloc[i]
            prev_closes = self.df['close'].iloc[i - self.swing_n: i]

            triggered = False
            if direction == 'bearish' and candle['close'] < prev_closes.min():
                triggered = True
            elif direction == 'bullish' and candle['close'] > prev_closes.max():
                triggered = True

            if triggered:
                result = self.calculate(i, direction, mode)
                results.append(result)

        return results

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _compute_swings(self):
        n = self.swing_n
        highs = self.df['high']
        lows = self.df['low']
        swing_h = [False] * len(self.df)
        swing_l = [False] * len(self.df)

        for i in range(n, len(self.df) - n):
            if (highs.iloc[i] == highs.iloc[i-n:i+n+1].max()):
                swing_h[i] = True
            if (lows.iloc[i] == lows.iloc[i-n:i+n+1].min()):
                swing_l[i] = True

        self.df['swing_high'] = swing_h
        self.df['swing_low'] = swing_l

    def _is_gap_or_large(self, idx: int) -> bool:
        if idx == 0:
            return False
        c = self.df.iloc[idx]
        p = self.df.iloc[idx - 1]

        # 缺口
        gap = c['open'] > p['high'] or c['open'] < p['low']

        # 超大K棒
        body = abs(c['close'] - c['open'])
        window = self.df.iloc[max(0, idx-20): idx]
        avg_body = abs(window['close'] - window['open']).mean()
        large = (body > self.large_candle_mult * avg_body) if avg_body > 0 else False

        return gap or large

    def _find_consolidation(
        self, idx: int, lookback: int = 30
    ) -> Optional[Consolidation]:
        """
        往回找最近的盤整結構（>=consolidation_min 根K棒，range 相對偏小）
        """
        start = max(0, idx - lookback)
        window = self.df.iloc[start:idx]
        if len(window) < self.consolidation_min:
            return None

        best: Optional[Consolidation] = None
        best_score = -1

        for i in range(len(window)):
            for j in range(i + self.consolidation_min, len(window) + 1):
                seg = window.iloc[i:j]
                seg_high = seg['high'].max()
                seg_low = seg['low'].min()
                seg_range = seg_high - seg_low
                avg_candle_range = (seg['high'] - seg['low']).mean()
                if avg_candle_range == 0:
                    continue
                ratio = seg_range / (avg_candle_range * len(seg))

                if ratio <= self.consolidation_ratio:
                    score = (j - i) / (ratio + 0.01)   # 越長越緊越好
                    if score > best_score:
                        best_score = score
                        best = Consolidation(
                            high=seg_high,
                            low=seg_low,
                            start_idx=start + i,
                            end_idx=start + j - 1,
                        )
        return best

    def _find_n_pattern_swing(
        self, idx: int, direction: Direction, lookback: int = 50
    ) -> Optional[Tuple[float, float]]:
        """
        找 N字型基準點 (A, B)
        bearish: A = 最近 swing_high，B = flip_idx 的 low（翻立低點）
        bullish: A = 最近 swing_low，B = flip_idx 的 high（翻立高點）
        """
        start = max(0, idx - lookback)
        window = self.df.iloc[start:idx]

        if direction == 'bearish':
            sh = window[window['swing_high']]['high']
            if sh.empty:
                return None
            A = sh.iloc[-1]
            B = self.df.iloc[idx]['low']
            if A <= B:
                return None
            return (A, B)
        else:
            sl = window[window['swing_low']]['low']
            if sl.empty:
                return None
            A = sl.iloc[-1]
            B = self.df.iloc[idx]['high']
            if A >= B:
                return None
            return (A, B)

    def _score_confidence(
        self, target: float, flip_idx: int, lookback: int = 100
    ) -> Tuple[int, List[float]]:
        """
        計算信心分（0-3）和重合的S/R水位列表
        """
        score = 0
        sr_levels: List[float] = []
        start = max(0, flip_idx - lookback)
        history = self.df.iloc[start:flip_idx]

        # 歷史擺動高低點
        swing_h_vals = history[history['swing_high']]['high'].tolist()
        swing_l_vals = history[history['swing_low']]['low'].tolist()
        all_levels = swing_h_vals + swing_l_vals

        for level in all_levels:
            if abs(level - target) / target < self.sr_tolerance:
                score += 1
                sr_levels.append(level)
                if score >= 3:
                    break

        # 均線（若有）
        for ma_col in ['ma20', 'ma60', 'ma240']:
            if ma_col in self.df.columns and score < 3:
                ma_val = self.df[ma_col].iloc[flip_idx]
                if pd.notna(ma_val) and abs(ma_val - target) / target < self.sr_tolerance:
                    score += 1
                    sr_levels.append(ma_val)

        return min(score, 3), sr_levels


# ---------------------------------------------------------------------------
# 使用範例
# ---------------------------------------------------------------------------

def example_mnq():
    """
    MNQ 實際使用範例

    假設你從 Tradovate 匯出 CSV，欄位：
    datetime, open, high, low, close, volume
    """
    # 1. 載入資料
    # df = pd.read_csv('mnq_5m.csv', parse_dates=['datetime'])
    # df = df.rename(columns={'DateTime': 'datetime'}).set_index('datetime')

    # 2. 加上均線（選填，提升信心評分精度）
    # df['ma20'] = df['close'].rolling(20).mean()
    # df['ma60'] = df['close'].rolling(60).mean()
    # df['ma240'] = df['close'].rolling(240).mean()

    # ---- 以下用模擬資料展示 ----
    np.random.seed(42)
    n = 300
    close = 30000 + np.cumsum(np.random.randn(n) * 5)
    df = pd.DataFrame({
        'open':  close - np.abs(np.random.randn(n) * 3),
        'high':  close + np.abs(np.random.randn(n) * 8),
        'low':   close - np.abs(np.random.randn(n) * 8),
        'close': close,
        'volume': np.random.randint(100, 1000, n),
    })

    # 3. 初始化計算器
    calc = AdamFlipCalculator(df, swing_n=3, consolidation_min=4)

    # 4a. 手動指定翻立K索引
    flip_idx = 150   # <-- 換成你在圖上看到的翻立K索引
    flip = calc.calculate(flip_idx=flip_idx, direction='bearish', mode='auto')
    print(flip.summary())
    print()
    print(flip.exit_plan())

    # 4b. 多時框疊加（需有兩個不同時框的 calc 實例）
    # small_tf_calc = AdamFlipCalculator(df_5m)
    # large_tf_calc = AdamFlipCalculator(df_60m)
    # flip_5m  = small_tf_calc.calculate(100, 'bearish')
    # flip_60m = large_tf_calc.calculate(20,  'bearish')
    # mtf = small_tf_calc.multi_timeframe(flip_5m, flip_60m)
    # print(mtf.summary())

    # 4c. 批次掃描最近的空方翻立
    # results = calc.scan_flips(direction='bearish', lookback=200)
    # for r in results[-3:]:   # 只看最近 3 個
    #     print(r.summary())

    return flip


if __name__ == '__main__':
    example_mnq()
