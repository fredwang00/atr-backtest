# data_loaders.py
"""
Data loading functions for OHLCV market data.

Each loader returns a DataFrame with Open, High, Low, Close, Volume columns
and a DatetimeIndex, or None if insufficient data.
"""

import yfinance as yf
import pandas as pd

START_DATE = "2018-01-01"
END_DATE = "2026-03-12"
MIN_ROWS = 200


def download_ohlcv(ticker, start=START_DATE, end=END_DATE):
    """Download daily OHLCV data from yfinance.

    Args:
        ticker: Stock ticker symbol (e.g., "SPY").
        start: Start date string (YYYY-MM-DD).
        end: End date string (YYYY-MM-DD).

    Returns:
        DataFrame with Open, High, Low, Close, Volume and DatetimeIndex,
        or None if fewer than MIN_ROWS rows available.
    """
    print(f"  Downloading {ticker}...")
    df = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if len(df) < MIN_ROWS:
        print(f"  Not enough data for {ticker}")
        return None

    return df
