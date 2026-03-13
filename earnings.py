"""
Earnings date blackout filter.
Fetches historical earnings dates from yfinance and provides a set of
dates to skip (configurable window around each announcement).
"""

import yfinance as yf
import pandas as pd
import os


CACHE_DIR = os.path.join("breadth_data", "earnings_cache")


def get_earnings_blackout(ticker, start_date, end_date, before=2, after=1):
    """
    Return a set of pd.Timestamp dates that fall within the blackout
    window around earnings announcements.

    before=2, after=1 means: 2 trading days before earnings, the earnings
    date itself, and 1 trading day after (the gap day).
    """
    earnings_dates = _load_earnings_dates(ticker, start_date, end_date)
    if earnings_dates is None or len(earnings_dates) == 0:
        return set()

    price_data = yf.download(ticker, start=start_date, end=end_date, progress=False)
    if isinstance(price_data.columns, pd.MultiIndex):
        price_data.columns = price_data.columns.get_level_values(0)
    trading_days = price_data.index.tolist()

    if not trading_days:
        return set()

    blackout = set()
    for ed in earnings_dates:
        ed_raw = pd.Timestamp(ed)
        ed_ts = (ed_raw.tz_convert(None) if ed_raw.tzinfo else ed_raw).normalize()

        closest_idx = None
        for i, td in enumerate(trading_days):
            if td.normalize() >= ed_ts:
                closest_idx = i
                break
        if closest_idx is None:
            closest_idx = len(trading_days) - 1

        for offset in range(-before, after + 1):
            idx = closest_idx + offset
            if 0 <= idx < len(trading_days):
                blackout.add(trading_days[idx])

    return blackout


def _load_earnings_dates(ticker, start_date, end_date):
    """Load earnings dates, using cache if available."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{ticker}_earnings.csv")

    if os.path.exists(cache_path):
        cached = pd.read_csv(cache_path, parse_dates=["date"])
        return cached["date"].tolist()

    try:
        tk = yf.Ticker(ticker)
        dates_df = tk.get_earnings_dates(limit=100)
        if dates_df is None or len(dates_df) == 0:
            return []

        earnings_dates = dates_df.index.tolist()

        cache_df = pd.DataFrame({"date": earnings_dates})
        cache_df.to_csv(cache_path, index=False)

        return earnings_dates
    except Exception:
        return []
