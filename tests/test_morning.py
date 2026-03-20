import os
import tempfile

import pandas as pd

from morning import compute_vix_pivot, load_readiness, _get_breadth_for_date, print_morning_plan


def test_vix_pivot_rounds_down():
    """17.23 rounds to 17.0."""
    assert compute_vix_pivot(17.23) == 17.0


def test_vix_pivot_rounds_up():
    """17.38 rounds to 17.5."""
    assert compute_vix_pivot(17.38) == 17.5


def test_vix_pivot_exact_half():
    """17.5 stays 17.5."""
    assert compute_vix_pivot(17.5) == 17.5


def test_vix_pivot_exact_whole():
    """17.0 stays 17.0."""
    assert compute_vix_pivot(17.0) == 17.0


def test_readiness_ok():
    """Good sleep and recovery returns OK status."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 85\nrecovery: 60\nhrv: 40\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["sleep_score"] == 85
            assert data["recovery"] == 60
            assert data["status"] == "OK"
            assert data["warnings"] == []
        finally:
            os.unlink(f.name)


def test_readiness_no_trading():
    """Sleep below 70 returns NO_TRADING."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 65\nrecovery: 50\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["status"] == "NO_TRADING"
            assert any("sleep" in w.lower() for w in data["warnings"])
        finally:
            os.unlink(f.name)


def test_readiness_poor_sleep_warning():
    """Sleep 70-77 returns WARNING."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 73\nrecovery: 60\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["status"] == "WARNING"
            assert any("sleep" in w.lower() for w in data["warnings"])
        finally:
            os.unlink(f.name)


def test_readiness_low_recovery_warning():
    """Recovery below 33 returns WARNING."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 85\nrecovery: 25\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["status"] == "WARNING"
            assert any("recovery" in w.lower() for w in data["warnings"])
        finally:
            os.unlink(f.name)


def test_readiness_missing_key():
    """Missing recovery key skips that rule."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 85\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["status"] == "OK"
            assert "recovery" not in data
        finally:
            os.unlink(f.name)


def test_readiness_sleep_boundary_77_warns():
    """Sleep score 77 is in warning range (70-77 inclusive)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 77\nrecovery: 60\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["status"] == "WARNING"
        finally:
            os.unlink(f.name)


def test_readiness_sleep_boundary_78_ok():
    """Sleep score 78 is OK (above warning range)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 78\nrecovery: 60\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["status"] == "OK"
        finally:
            os.unlink(f.name)


def test_readiness_file_not_found():
    """Missing file returns None."""
    assert load_readiness("/nonexistent/path.md") is None


def _make_breadth_df():
    """Helper: minimal breadth DataFrame for testing."""
    df = pd.DataFrame({
        "regime": ["BEARISH"],
        "breadth_score": [-3],
        "breadth_trend": ["SLIGHTLY_DETERIORATING"],
        "ratio10": [0.75],
        "ratio10_bias": ["short"],
    }, index=pd.to_datetime(["2026-03-19"]))
    return df


def test_get_breadth_for_date_found():
    """Returns breadth data when date is in range."""
    df = _make_breadth_df()
    result = _get_breadth_for_date(df, pd.Timestamp("2026-03-19"))
    assert result["regime"] == "BEARISH"
    assert result["score"] == -3


def test_get_breadth_for_date_empty():
    """Returns UNKNOWN when date is before all data."""
    df = _make_breadth_df()
    result = _get_breadth_for_date(df, pd.Timestamp("2010-01-01"))
    assert result["regime"] == "UNKNOWN"


def test_print_morning_plan_smoke(capsys):
    """Smoke test: print_morning_plan runs without error and prints key sections."""
    print_morning_plan(
        plan_date="2026-03-20",
        readiness={"sleep_score": 85, "recovery": 50, "hrv": 31.7,
                   "status": "OK", "warnings": []},
        vix_close=17.23,
        vix_pivot=17.0,
        spy_levels=None,
        qqq_levels=None,
        breadth={"regime": "BEARISH", "score": -3,
                 "trend": "SLIGHTLY_DETERIORATING", "r10": 0.75, "bias": "short"},
    )
    output = capsys.readouterr().out
    assert "MORNING PLAN" in output
    assert "READINESS" in output
    assert "VIX PIVOT" in output
    assert "17.0" in output
    assert "BEARISH" in output
