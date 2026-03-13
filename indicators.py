# indicators.py
"""
Technical indicator computation for ATR Levels strategy.

Provides IndicatorConfig for parameter profiles (daily vs intraday)
and compute_indicators() for applying all indicators to an OHLCV DataFrame.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IndicatorConfig:
    """Parameters for all technical indicators. Frozen for safety."""
    atr_period: int = 14
    trigger_pct: float = 0.236
    mid_pct: float = 0.618
    full_pct: float = 1.0
    ema_periods: tuple = (8, 9, 21, 34, 50)
    macro_ema: int = 200
    bb_period: int = 20
    bb_mult: float = 2.0
    kc_period: int = 20
    kc_mult: float = 1.5
    vol_avg_period: int = 20
    squeeze_lookback: int = 10


DAILY_CONFIG = IndicatorConfig()
INTRADAY_CONFIG = IndicatorConfig(macro_ema=512, squeeze_lookback=20)


def wilders_atr(high, low, close, period=14):
    """Wilder's ATR — same smoothing method Saty's indicator uses."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = pd.Series(np.nan, index=tr.index)
    atr.iloc[period - 1] = tr.iloc[:period].mean()
    for i in range(period, len(atr)):
        atr.iloc[i] = (atr.iloc[i - 1] * (period - 1) + tr.iloc[i]) / period
    return atr


def compute_emas(close, periods):
    """Compute multiple EMAs and return as a dict."""
    emas = {}
    for p in periods:
        emas[p] = close.ewm(span=p, adjust=False).mean()
    return emas


def ttm_squeeze(high, low, close, bb_period=20, bb_mult=2.0, kc_period=20, kc_mult=1.5):
    """
    TTM Squeeze detection.
    Squeeze is ON when Bollinger Bands are inside Keltner Channels.
    Squeeze FIRES when it transitions from ON to OFF (bands expand).

    Returns:
        squeeze_on: bool series — True when in squeeze
        squeeze_fired: bool series — True on the bar where squeeze releases
    """
    # Bollinger Bands
    bb_mid = close.rolling(bb_period).mean()
    bb_std = close.rolling(bb_period).std()
    bb_upper = bb_mid + bb_mult * bb_std
    bb_lower = bb_mid - bb_mult * bb_std

    # Keltner Channels (using ATR)
    kc_mid = close.rolling(kc_period).mean()
    kc_atr = wilders_atr(high, low, close, kc_period)
    kc_upper = kc_mid + kc_mult * kc_atr
    kc_lower = kc_mid - kc_mult * kc_atr

    # Squeeze is ON when BB is inside KC
    squeeze_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)

    # Squeeze fires when it goes from ON to OFF
    squeeze_fired = squeeze_on.shift(1).fillna(False) & ~squeeze_on

    return squeeze_on, squeeze_fired


def compute_momentum(high, low, close, period=20):
    """
    Momentum oscillator for squeeze direction, approximating TTM Squeeze.

    The real TTM Squeeze Pro uses linear regression of
    (close - midline of Keltner/Donchian). We approximate with
    close minus the average of (highest high + lowest low)/2 and SMA,
    which captures whether price is above or below the "center of gravity."

    Positive = bullish, Negative = bearish.
    """
    # Donchian midline
    highest = high.rolling(period).max()
    lowest = low.rolling(period).min()
    donchian_mid = (highest + lowest) / 2

    # SMA midline
    sma_mid = close.rolling(period).mean()

    # Average of the two midlines (closer to TTM Squeeze Pro approach)
    combined_mid = (donchian_mid + sma_mid) / 2

    return close - combined_mid
