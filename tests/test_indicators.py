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


def test_compute_indicators_produces_expected_columns():
    """compute_indicators adds all ATR level, EMA, squeeze, and volume columns."""
    from indicators import compute_indicators, DAILY_CONFIG

    np.random.seed(42)
    n = 300
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    dates = pd.bdate_range("2020-01-01", periods=n)

    df = pd.DataFrame({
        "Open": close + np.random.randn(n) * 0.1,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)

    result = compute_indicators(df, config=DAILY_CONFIG)

    for col in ["ATR", "Prev_ATR", "Prev_Close", "Central_Pivot",
                 "Long_Trigger", "Short_Trigger", "Mid_Long", "Mid_Short",
                 "Full_Long", "Full_Short"]:
        assert col in result.columns, f"Missing column: {col}"

    for p in list(DAILY_CONFIG.ema_periods) + [DAILY_CONFIG.macro_ema]:
        assert f"EMA_{p}" in result.columns

    assert "EMA_Bull_Stack" in result.columns
    assert "EMA_Bear_Stack" in result.columns
    assert "Squeeze_On" in result.columns
    assert "Squeeze_Fired" in result.columns
    assert "Recent_Squeeze_Fire" in result.columns
    assert "Momentum" in result.columns
    assert "Vol_SMA" in result.columns
    assert "Vol_Above_Avg" in result.columns

    assert len(result) < n
    assert len(result) > 0
    assert not result["Prev_ATR"].isna().any()
    assert not result[f"EMA_{DAILY_CONFIG.macro_ema}"].isna().any()


def test_compute_indicators_uses_config():
    """Passing a custom config changes which EMAs are computed."""
    from indicators import compute_indicators, IndicatorConfig

    np.random.seed(42)
    n = 300
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    dates = pd.bdate_range("2020-01-01", periods=n)

    df = pd.DataFrame({
        "Open": close + np.random.randn(n) * 0.1,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)

    custom = IndicatorConfig(macro_ema=512)
    result = compute_indicators(df, config=custom)
    assert "EMA_512" in result.columns
    assert "EMA_200" not in result.columns


def _make_mock_ohlcv(n=300):
    """Create synthetic OHLCV data for testing."""
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    dates = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame({
        "Open": close + np.random.randn(n) * 0.1,
        "High": close + np.abs(np.random.randn(n) * 0.3),
        "Low": close - np.abs(np.random.randn(n) * 0.3),
        "Close": close,
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)


def test_prepare_data_returns_tuple():
    """prepare_data still returns (df, dict) tuple for backward compat."""
    from unittest.mock import patch
    from atr_swing_backtest import prepare_data

    mock_df = _make_mock_ohlcv()
    with patch("data_loaders.yf.download", return_value=mock_df):
        result = prepare_data("SPY")

    assert result is not None
    df, extra = result
    assert isinstance(df, pd.DataFrame)
    assert isinstance(extra, dict)
    assert "Full_Long" in df.columns
    assert "EMA_200" in df.columns
    assert "Recent_Squeeze_Fire" in df.columns
