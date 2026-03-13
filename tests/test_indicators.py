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
