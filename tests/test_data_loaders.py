# tests/test_data_loaders.py
from unittest.mock import patch
import pandas as pd
import numpy as np


def test_download_ohlcv_returns_dataframe():
    """download_ohlcv returns an OHLCV DataFrame for a valid ticker."""
    from data_loaders import download_ohlcv

    n = 250
    dates = pd.bdate_range("2020-01-01", periods=n)
    mock_df = pd.DataFrame({
        "Open": np.random.randn(n) + 100,
        "High": np.random.randn(n) + 101,
        "Low": np.random.randn(n) + 99,
        "Close": np.random.randn(n) + 100,
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)

    with patch("data_loaders.yf.download", return_value=mock_df):
        result = download_ohlcv("SPY")

    assert result is not None
    assert "Open" in result.columns
    assert "Close" in result.columns
    assert len(result) == n


def test_download_ohlcv_returns_none_for_insufficient_data():
    """download_ohlcv returns None if fewer than MIN_ROWS rows."""
    from data_loaders import download_ohlcv

    mock_df = pd.DataFrame({
        "Open": [100], "High": [101], "Low": [99],
        "Close": [100], "Volume": [1_000_000],
    }, index=pd.bdate_range("2020-01-01", periods=1))

    with patch("data_loaders.yf.download", return_value=mock_df):
        result = download_ohlcv("FAKE")

    assert result is None


def test_download_ohlcv_flattens_multiindex():
    """download_ohlcv handles yfinance MultiIndex columns."""
    from data_loaders import download_ohlcv

    n = 250
    dates = pd.bdate_range("2020-01-01", periods=n)
    arrays = [
        ["Open", "High", "Low", "Close", "Volume"],
        ["SPY", "SPY", "SPY", "SPY", "SPY"],
    ]
    tuples = list(zip(*arrays))
    index = pd.MultiIndex.from_tuples(tuples)
    mock_df = pd.DataFrame(
        np.random.randn(n, 5) + 100,
        columns=index,
        index=dates,
    )

    with patch("data_loaders.yf.download", return_value=mock_df):
        result = download_ohlcv("SPY")

    assert not isinstance(result.columns, pd.MultiIndex)
    assert "Open" in result.columns
