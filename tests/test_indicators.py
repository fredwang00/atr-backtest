# tests/test_indicators.py
import numpy as np
import pandas as pd

from indicators import IndicatorConfig, DAILY_CONFIG, INTRADAY_CONFIG


def test_daily_config_defaults():
    """DAILY_CONFIG has the standard daily bar parameters."""
    assert DAILY_CONFIG.atr_period == 14
    assert DAILY_CONFIG.macro_ema == 200
    assert DAILY_CONFIG.ema_periods == (8, 9, 21, 34, 50)
    assert DAILY_CONFIG.squeeze_lookback == 10


def test_intraday_config_overrides():
    """INTRADAY_CONFIG uses 512 EMA and wider squeeze lookback."""
    assert INTRADAY_CONFIG.macro_ema == 512
    assert INTRADAY_CONFIG.squeeze_lookback == 20
    assert INTRADAY_CONFIG.atr_period == 14
    assert INTRADAY_CONFIG.ema_periods == (8, 9, 21, 34, 50)


def test_config_is_frozen():
    """Config instances are immutable."""
    import pytest
    with pytest.raises(AttributeError):
        DAILY_CONFIG.atr_period = 20


def test_wilders_atr_length():
    """wilders_atr returns a Series the same length as input."""
    from indicators import wilders_atr
    high = pd.Series([10, 11, 12, 11, 13, 14, 12, 15, 14, 13,
                       12, 11, 14, 15, 16, 13, 12, 11, 14, 15])
    low = pd.Series([9, 10, 10, 9, 11, 12, 10, 13, 12, 11,
                      10, 9, 12, 13, 14, 11, 10, 9, 12, 13])
    close = pd.Series([9.5, 10.5, 11, 10, 12, 13, 11, 14, 13, 12,
                        11, 10, 13, 14, 15, 12, 11, 10, 13, 14])
    atr = wilders_atr(high, low, close, period=14)
    assert len(atr) == len(high)
    assert atr.iloc[:13].isna().all()
    assert not np.isnan(atr.iloc[13])
