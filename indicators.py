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


def compute_indicators(df, config=DAILY_CONFIG):
    """Apply all technical indicators to an OHLCV DataFrame.

    Args:
        df: DataFrame with Open, High, Low, Close, Volume columns and DatetimeIndex.
        config: IndicatorConfig with indicator parameters.

    Returns:
        Enriched DataFrame with warmup rows trimmed. Does not modify the input.
    """
    df = df.copy()
    ema_periods = list(config.ema_periods)

    # Core ATR levels
    df["ATR"] = wilders_atr(df["High"], df["Low"], df["Close"], config.atr_period)
    df["Prev_Close"] = df["Close"].shift(1)
    df["Prev_ATR"] = df["ATR"].shift(1)

    df["Long_Trigger"] = df["Prev_Close"] + config.trigger_pct * df["Prev_ATR"]
    df["Short_Trigger"] = df["Prev_Close"] - config.trigger_pct * df["Prev_ATR"]
    df["Mid_Long"] = df["Prev_Close"] + config.mid_pct * df["Prev_ATR"]
    df["Mid_Short"] = df["Prev_Close"] - config.mid_pct * df["Prev_ATR"]
    df["Full_Long"] = df["Prev_Close"] + config.full_pct * df["Prev_ATR"]
    df["Full_Short"] = df["Prev_Close"] - config.full_pct * df["Prev_ATR"]
    df["Central_Pivot"] = df["Prev_Close"]

    # EMAs
    all_ema_periods = ema_periods + [config.macro_ema]
    emas = compute_emas(df["Close"], all_ema_periods)
    for p in all_ema_periods:
        df[f"EMA_{p}"] = emas[p]

    # EMA stack check
    bull_stack = pd.Series(True, index=df.index)
    bear_stack = pd.Series(True, index=df.index)
    for j in range(len(ema_periods) - 1):
        shorter = df[f"EMA_{ema_periods[j]}"]
        longer = df[f"EMA_{ema_periods[j + 1]}"]
        bull_stack = bull_stack & (shorter > longer)
        bear_stack = bear_stack & (shorter < longer)
    df["EMA_Bull_Stack"] = bull_stack
    df["EMA_Bear_Stack"] = bear_stack

    # TTM Squeeze
    df["Squeeze_On"], df["Squeeze_Fired"] = ttm_squeeze(
        df["High"], df["Low"], df["Close"],
        config.bb_period, config.bb_mult, config.kc_period, config.kc_mult
    )

    # Momentum
    df["Momentum"] = compute_momentum(df["High"], df["Low"], df["Close"], config.bb_period)

    # Volume confirmation
    df["Vol_SMA"] = df["Volume"].rolling(config.vol_avg_period).mean()
    df["Vol_Above_Avg"] = df["Volume"] > df["Vol_SMA"]

    # Recent squeeze fire
    df["Recent_Squeeze_Fire"] = (
        df["Squeeze_Fired"].rolling(config.squeeze_lookback).max().fillna(0).astype(bool)
    )

    # Trim warmup rows
    df = df.dropna(subset=["ATR", "Prev_ATR", "Prev_Close", f"EMA_{config.macro_ema}"]).copy()
    warmup = max(all_ema_periods + [config.bb_period, config.atr_period]) + 5
    df = df.iloc[warmup:]

    return df
