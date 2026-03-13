import os
import pandas as pd
from journal import (
    JOURNAL_PATH, JOURNAL_COLUMNS, load_journal,
    add_entry, close_trade, compute_review_stats,
)


def test_load_journal_creates_file():
    """First load creates the CSV with headers."""
    test_path = "test_journal_tmp.csv"
    try:
        df = load_journal(test_path)
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == JOURNAL_COLUMNS
        assert len(df) == 0
        assert os.path.exists(test_path)
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_add_entry():
    """Adding an entry appends a row with blank exit fields."""
    test_path = "test_journal_tmp.csv"
    try:
        entry = {
            "date": "2024-03-15", "ticker": "NVDA", "direction": "long",
            "entry_price": 142.37, "size": 1000, "size_mult": 1.0,
            "trigger_level": 141.50, "mid_target": 145.00,
            "full_target": 148.00, "stop_level": 139.00,
            "regime": "BULLISH", "breadth_trend": "IMPROVING",
            "notes": "Strong squeeze fire",
        }
        add_entry(entry, test_path)
        df = load_journal(test_path)
        assert len(df) == 1
        assert df.iloc[0]["ticker"] == "NVDA"
        assert df.iloc[0]["direction"] == "long"
        assert pd.isna(df.iloc[0]["exit_date"])
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_close_trade():
    """Closing a trade fills exit fields and computes pnl_pct."""
    test_path = "test_journal_tmp.csv"
    try:
        entry = {
            "date": "2024-03-15", "ticker": "NVDA", "direction": "long",
            "entry_price": 100.0, "size": 1000, "size_mult": 1.0,
            "trigger_level": 100.0, "mid_target": 103.0,
            "full_target": 105.0, "stop_level": 98.0,
            "regime": "BULLISH", "breadth_trend": "STEADY",
            "notes": "",
        }
        add_entry(entry, test_path)
        close_trade(0, exit_price=105.0, exit_date="2024-03-18",
                    exit_reason="target_full", notes="Hit full target",
                    path=test_path)
        df = load_journal(test_path)
        assert df.iloc[0]["exit_price"] == 105.0
        assert df.iloc[0]["exit_reason"] == "target_full"
        assert abs(df.iloc[0]["pnl_pct"] - 5.0) < 0.01
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_close_short_trade():
    """Short trade pnl is (entry - exit) / entry."""
    test_path = "test_journal_tmp.csv"
    try:
        entry = {
            "date": "2024-03-15", "ticker": "TSLA", "direction": "short",
            "entry_price": 200.0, "size": 1000, "size_mult": 1.0,
            "trigger_level": 200.0, "mid_target": 195.0,
            "full_target": 190.0, "stop_level": 203.0,
            "regime": "BEARISH", "breadth_trend": "DETERIORATING",
            "notes": "",
        }
        add_entry(entry, test_path)
        close_trade(0, exit_price=190.0, exit_date="2024-03-18",
                    exit_reason="target_full", notes="",
                    path=test_path)
        df = load_journal(test_path)
        assert abs(df.iloc[0]["pnl_pct"] - 5.0) < 0.01
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_compute_review_stats():
    """Review stats compute correctly from journal data."""
    test_path = "test_journal_tmp.csv"
    try:
        for i, pnl in enumerate([5.0, 3.0, -2.0, 4.0]):
            entry_price = 100.0
            exit_price = entry_price * (1 + pnl / 100)
            entry = {
                "date": f"2024-03-{15+i}", "ticker": "SPY", "direction": "long",
                "entry_price": entry_price, "size": 1000, "size_mult": 1.0,
                "trigger_level": 100.0, "mid_target": 103.0,
                "full_target": 105.0, "stop_level": 98.0,
                "regime": "NEUTRAL", "breadth_trend": "STEADY",
                "notes": "",
            }
            add_entry(entry, test_path)
            close_trade(i, exit_price=exit_price, exit_date=f"2024-03-{17+i}",
                        exit_reason="target_full", notes="", path=test_path)

        stats = compute_review_stats(test_path)
        assert stats["total"] == 4
        assert stats["win_rate"] == 75.0
        assert abs(stats["avg_pnl"] - 2.5) < 0.01
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)
