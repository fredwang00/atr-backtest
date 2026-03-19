import os
import pandas as pd
from journal import (
    JOURNAL_PATH, JOURNAL_COLUMNS, VALID_SETUP_GRADES, load_journal,
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
    """Closing a trade fills exit fields and computes pnl_pct and pnl_dollars."""
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
        # pnl_dollars should be computed for swing trades too
        assert "pnl_dollars" in df.columns
        pnl_dollars = float(df.iloc[0]["pnl_dollars"])
        assert abs(pnl_dollars - 50.0) < 0.01  # 5% of $1000 size
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


def test_add_credit_spread_entry():
    """Adding a credit spread entry stores all spread-specific fields."""
    test_path = "test_journal_tmp.csv"
    try:
        entry = {
            "date": "2026-03-16", "ticker": "SPY", "direction": "short",
            "trade_type": "credit_spread", "spread_type": "call",
            "short_strike": 672, "long_strike": 674,
            "spread_width": 2.0, "contracts": 10, "credit": 0.087,
            "entry_price": 0.087,
            "size": 1913.0,
            "regime": "BEARISH", "breadth_trend": "DETERIORATING_FAST",
            "notes": "0DTE, SPY ~669 at entry",
        }
        add_entry(entry, test_path)
        df = load_journal(test_path)
        assert len(df) == 1
        assert df.iloc[0]["trade_type"] == "credit_spread"
        assert df.iloc[0]["spread_type"] == "call"
        assert df.iloc[0]["short_strike"] == 672
        assert df.iloc[0]["long_strike"] == 674
        assert df.iloc[0]["spread_width"] == 2.0
        assert df.iloc[0]["contracts"] == 10
        assert df.iloc[0]["credit"] == 0.087
        assert pd.isna(df.iloc[0]["exit_date"])
        assert pd.isna(df.iloc[0]["pnl_dollars"])
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_close_credit_spread_expired_otm():
    """Credit spread expired OTM: full credit kept, pnl_dollars and pnl_pct correct."""
    test_path = "test_journal_tmp.csv"
    try:
        entry = {
            "date": "2026-03-16", "ticker": "SPY", "direction": "short",
            "trade_type": "credit_spread", "spread_type": "call",
            "short_strike": 672, "long_strike": 674,
            "spread_width": 2.0, "contracts": 10, "credit": 0.087,
            "entry_price": 0.087, "size": 1913.0,
            "regime": "BEARISH", "breadth_trend": "DETERIORATING_FAST",
            "notes": "",
        }
        add_entry(entry, test_path)
        close_trade(0, exit_price=0.0, exit_date="2026-03-16",
                    exit_reason="expired_otm", path=test_path)
        df = load_journal(test_path)
        assert df.iloc[0]["exit_price"] == 0.0
        assert df.iloc[0]["exit_reason"] == "expired_otm"
        # pnl_dollars = (0.087 - 0) * 10 * 100 = $87
        assert abs(float(df.iloc[0]["pnl_dollars"]) - 87.0) < 0.01
        # pnl_pct = 87 / (1.913 * 10 * 100) * 100 = 4.548%
        assert abs(float(df.iloc[0]["pnl_pct"]) - 4.548) < 0.1
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_close_credit_spread_loss():
    """Credit spread closed at a loss: debit > credit."""
    test_path = "test_journal_tmp.csv"
    try:
        entry = {
            "date": "2026-03-16", "ticker": "SPY", "direction": "short",
            "trade_type": "credit_spread", "spread_type": "put",
            "short_strike": 660, "long_strike": 655,
            "spread_width": 5.0, "contracts": 5, "credit": 0.50,
            "entry_price": 0.50, "size": 2250.0,
            "regime": "BEARISH", "breadth_trend": "DETERIORATING_FAST",
            "notes": "",
        }
        add_entry(entry, test_path)
        close_trade(0, exit_price=3.0, exit_date="2026-03-16",
                    exit_reason="stop", path=test_path)
        df = load_journal(test_path)
        # pnl_dollars = (0.50 - 3.0) * 5 * 100 = -$1250
        assert abs(float(df.iloc[0]["pnl_dollars"]) - (-1250.0)) < 0.01
        # pnl_pct = -1250 / ((5.0 - 0.50) * 5 * 100) * 100 = -55.56%
        assert abs(float(df.iloc[0]["pnl_pct"]) - (-55.56)) < 0.1
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_compute_review_stats_by_trade_type():
    """Review stats can be filtered by trade type."""
    test_path = "test_journal_tmp.csv"
    try:
        # Add a swing trade
        add_entry({
            "date": "2026-03-15", "ticker": "SPY", "direction": "long",
            "entry_price": 100.0, "size": 1000, "trade_type": "swing",
            "regime": "NEUTRAL", "breadth_trend": "STEADY", "notes": "",
        }, test_path)
        close_trade(0, exit_price=105.0, exit_date="2026-03-18",
                    exit_reason="target_full", path=test_path)

        # Add a credit spread trade
        add_entry({
            "date": "2026-03-16", "ticker": "SPY", "direction": "short",
            "trade_type": "credit_spread", "spread_type": "call",
            "short_strike": 672, "long_strike": 674,
            "spread_width": 2.0, "contracts": 10, "credit": 0.10,
            "entry_price": 0.10, "size": 1900.0,
            "regime": "BEARISH", "breadth_trend": "DETERIORATING_FAST",
            "notes": "",
        }, test_path)
        close_trade(1, exit_price=0.0, exit_date="2026-03-16",
                    exit_reason="expired_otm", path=test_path)

        # All trades
        all_stats = compute_review_stats(test_path)
        assert all_stats["total"] == 2

        # Swing only
        swing_stats = compute_review_stats(test_path, trade_type="swing")
        assert swing_stats["total"] == 1
        assert swing_stats["win_rate"] == 100.0

        # Credit spread only
        cs_stats = compute_review_stats(test_path, trade_type="credit_spread")
        assert cs_stats["total"] == 1
        assert cs_stats["win_rate"] == 100.0
        assert cs_stats["avg_pnl_dollars"] > 0
        assert cs_stats["total_pnl_dollars"] > 0
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_backward_compat_old_csv_missing_columns():
    """Old CSVs without trade_type/pnl_dollars columns still work."""
    test_path = "test_journal_tmp.csv"
    try:
        # Create a minimal CSV with only old columns (no trade_type, no pnl_dollars)
        old_columns = [
            "date", "ticker", "direction", "entry_price", "size", "size_mult",
            "trigger_level", "mid_target", "full_target", "stop_level",
            "regime", "breadth_trend", "exit_date", "exit_price", "exit_reason",
            "pnl_pct", "notes",
        ]
        df = pd.DataFrame([{
            "date": "2026-03-10", "ticker": "AAPL", "direction": "long",
            "entry_price": 100.0, "size": 1000, "size_mult": 1.0,
            "trigger_level": 98, "mid_target": 103, "full_target": 106,
            "stop_level": 95, "regime": "NEUTRAL", "breadth_trend": "STEADY",
            "exit_date": "2026-03-12", "exit_price": 105.0,
            "exit_reason": "target_full", "pnl_pct": 5.0, "notes": "",
        }], columns=old_columns)
        df.to_csv(test_path, index=False)

        # compute_review_stats should not crash
        stats = compute_review_stats(test_path)
        assert stats["total"] == 1
        assert stats["win_rate"] == 100.0

        # Filtering by swing should find the trade (missing column = swing)
        swing_stats = compute_review_stats(test_path, trade_type="swing")
        assert swing_stats["total"] == 1

        # Filtering by credit_spread should find nothing
        cs_stats = compute_review_stats(test_path, trade_type="credit_spread")
        assert cs_stats["total"] == 0
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


# --- Setup grade tests ---

def test_valid_setup_grades():
    """Valid grades are A through D."""
    assert VALID_SETUP_GRADES == ["A", "B", "C", "D"]


def test_setup_grade_column_exists():
    """setup_grade is part of the journal schema."""
    assert "setup_grade" in JOURNAL_COLUMNS


def test_add_entry_with_setup_grade():
    """Setup grade is stored when provided."""
    test_path = "test_journal_tmp.csv"
    try:
        entry = {
            "date": "2026-03-16", "ticker": "SPY", "direction": "short",
            "trade_type": "credit_spread", "spread_type": "call",
            "short_strike": 672, "long_strike": 674,
            "spread_width": 2.0, "contracts": 10, "credit": 0.10,
            "entry_price": 0.10, "size": 1900.0,
            "regime": "BEARISH", "breadth_trend": "DETERIORATING_FAST",
            "setup_grade": "A",
            "notes": "",
        }
        add_entry(entry, test_path)
        df = load_journal(test_path)
        assert df.iloc[0]["setup_grade"] == "A"
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_add_entry_without_setup_grade():
    """Missing setup_grade defaults to empty string (backward compat)."""
    test_path = "test_journal_tmp.csv"
    try:
        entry = {
            "date": "2026-03-16", "ticker": "SPY", "direction": "long",
            "entry_price": 100.0, "size": 1000,
            "regime": "NEUTRAL", "breadth_trend": "STEADY",
            "notes": "",
        }
        add_entry(entry, test_path)
        df = load_journal(test_path)
        assert pd.isna(df.iloc[0]["setup_grade"]) or df.iloc[0]["setup_grade"] == ""
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_compliance_column_in_schema():
    """compliance is part of the journal schema."""
    assert "compliance" in JOURNAL_COLUMNS


def test_add_entry_with_compliance():
    """Compliance field is stored when provided."""
    test_path = "test_journal_tmp.csv"
    try:
        entry = {
            "date": "2026-03-19", "ticker": "SPX", "direction": "short",
            "trade_type": "credit_spread", "spread_type": "call",
            "short_strike": 6800, "long_strike": 6820,
            "spread_width": 20.0, "contracts": 5, "credit": 0.30,
            "entry_price": 0.30, "size": 9850.0,
            "regime": "CAUTIOUS", "breadth_trend": "SLIGHTLY_DETERIORATING",
            "setup_grade": "A", "compliance": "compliant",
            "notes": "",
        }
        add_entry(entry, test_path)
        df = load_journal(test_path)
        assert df.iloc[0]["compliance"] == "compliant"
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_add_entry_with_violations():
    """Violation descriptions are stored in compliance field."""
    test_path = "test_journal_tmp.csv"
    try:
        entry = {
            "date": "2026-03-19", "ticker": "SPX", "direction": "short",
            "trade_type": "credit_spread", "spread_type": "put",
            "short_strike": 6625, "long_strike": 6605,
            "spread_width": 20.0, "contracts": 10, "credit": 1.35,
            "entry_price": 1.35, "size": 18650.0,
            "regime": "CAUTIOUS", "breadth_trend": "SLIGHTLY_DETERIORATING",
            "setup_grade": "D", "compliance": "wrong_structure; oversized",
            "notes": "Overrode regime warning",
        }
        add_entry(entry, test_path)
        df = load_journal(test_path)
        assert "wrong_structure" in df.iloc[0]["compliance"]
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_review_stats_by_setup_grade():
    """Review stats include win rate broken down by setup grade."""
    test_path = "test_journal_tmp.csv"
    try:
        # A-grade winners
        for i in range(3):
            add_entry({
                "date": f"2026-03-{10+i}", "ticker": "SPY", "direction": "long",
                "entry_price": 100.0, "size": 1000,
                "regime": "BULLISH", "breadth_trend": "IMPROVING",
                "setup_grade": "A", "notes": "",
            }, test_path)
            close_trade(i, exit_price=105.0, exit_date=f"2026-03-{12+i}",
                        exit_reason="target_full", path=test_path)

        # C-grade loser
        add_entry({
            "date": "2026-03-15", "ticker": "SPY", "direction": "long",
            "entry_price": 100.0, "size": 1000,
            "regime": "BEARISH", "breadth_trend": "DETERIORATING",
            "setup_grade": "C", "notes": "forced entry",
        }, test_path)
        close_trade(3, exit_price=97.0, exit_date="2026-03-16",
                    exit_reason="stop", path=test_path)

        stats = compute_review_stats(test_path)
        assert "grade_stats" in stats
        assert stats["grade_stats"]["A"]["total"] == 3
        assert stats["grade_stats"]["A"]["win_rate"] == 100.0
        assert stats["grade_stats"]["C"]["total"] == 1
        assert stats["grade_stats"]["C"]["win_rate"] == 0.0
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)
