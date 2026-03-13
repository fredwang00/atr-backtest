import pandas as pd
from earnings import get_earnings_blackout

def test_blackout_returns_set_of_timestamps():
    blackout = get_earnings_blackout("AAPL", "2023-01-01", "2024-01-01")
    assert isinstance(blackout, set)
    assert len(blackout) >= 12  # 4 earnings * (2 before + 1 earnings + 1 after) = 16

def test_blackout_window_size():
    blackout = get_earnings_blackout("AAPL", "2023-01-01", "2024-01-01", before=2, after=1)
    assert len(blackout) >= 12

def test_blackout_dates_are_within_range():
    blackout = get_earnings_blackout("SPY", "2023-01-01", "2024-01-01")
    for dt in blackout:
        assert dt.year >= 2022 and dt.year <= 2025
