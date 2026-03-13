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
