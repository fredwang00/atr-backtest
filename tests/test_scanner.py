import subprocess

from atr_swing_backtest import check_entry_conditions, prepare_data
from scanner import classify_ticker, LONG_CONDS, SHORT_CONDS


def test_check_entry_conditions_returns_dict():
    result = prepare_data("SPY")
    assert result is not None
    df, _ = result
    conds = check_entry_conditions(df, 100)
    for key in ["squeeze", "momentum_long", "momentum_short",
                "ema_bull", "ema_bear", "long_crossover", "short_crossover",
                "volume", "above_macro", "below_macro"]:
        assert key in conds, f"Missing key: {key}"
        assert isinstance(conds[key], bool), f"{key} should be bool, got {type(conds[key])}"
    for key in ["long_trigger", "short_trigger", "mid_long", "mid_short",
                "full_long", "full_short", "central_pivot", "atr", "close"]:
        assert key in conds, f"Missing key: {key}"
        assert isinstance(conds[key], (int, float)), f"{key} should be numeric"


def test_backtest_produces_trades():
    """Verify run_backtest still works after refactor — produces completed trades."""
    from atr_swing_backtest import run_backtest
    result = prepare_data("SPY")
    assert result is not None
    df, _ = result
    df.attrs["ticker"] = "SPY"
    trades = run_backtest(df)
    assert len(trades) >= 10  # SPY should have meaningful trade count
    for t in trades:
        assert t.exit_price is not None


def test_classify_triggered():
    """All 6 long conditions met → TRIGGERED."""
    conds = {
        "squeeze": True, "momentum_long": True, "ema_bull": True,
        "long_crossover": True, "volume": True, "above_macro": True,
        "momentum_short": False, "ema_bear": False, "short_crossover": False,
        "below_macro": False,
        "long_trigger": 100.0, "short_trigger": 95.0, "mid_long": 103.0,
        "mid_short": 92.0, "full_long": 105.0, "full_short": 90.0,
        "central_pivot": 98.0, "atr": 5.0, "close": 101.0,
    }
    result = classify_ticker("TEST", conds)
    assert result["bucket"] == "TRIGGERED"
    assert result["direction"] == "long"


def test_classify_near():
    """5 of 6 long conditions met → NEAR."""
    conds = {
        "squeeze": True, "momentum_long": True, "ema_bull": True,
        "long_crossover": False, "volume": True, "above_macro": True,
        "momentum_short": False, "ema_bear": False, "short_crossover": False,
        "below_macro": False,
        "long_trigger": 100.0, "short_trigger": 95.0, "mid_long": 103.0,
        "mid_short": 92.0, "full_long": 105.0, "full_short": 90.0,
        "central_pivot": 98.0, "atr": 5.0, "close": 99.5,
    }
    result = classify_ticker("TEST", conds)
    assert result["bucket"] == "NEAR"
    assert result["direction"] == "long"
    assert "long_crossover" in result["missing"]


def test_classify_quiet():
    """Fewer than 4 conditions → QUIET."""
    conds = {
        "squeeze": False, "momentum_long": False, "ema_bull": False,
        "long_crossover": False, "volume": False, "above_macro": True,
        "momentum_short": False, "ema_bear": False, "short_crossover": False,
        "below_macro": False,
        "long_trigger": 100.0, "short_trigger": 95.0, "mid_long": 103.0,
        "mid_short": 92.0, "full_long": 105.0, "full_short": 90.0,
        "central_pivot": 98.0, "atr": 5.0, "close": 97.0,
    }
    result = classify_ticker("TEST", conds)
    assert result["bucket"] == "QUIET"


def test_classify_short_triggered():
    """All 6 short conditions met → TRIGGERED short."""
    conds = {
        "squeeze": True, "momentum_long": False, "ema_bull": False,
        "long_crossover": False, "volume": True, "above_macro": False,
        "momentum_short": True, "ema_bear": True, "short_crossover": True,
        "below_macro": True,
        "long_trigger": 100.0, "short_trigger": 95.0, "mid_long": 103.0,
        "mid_short": 92.0, "full_long": 105.0, "full_short": 90.0,
        "central_pivot": 98.0, "atr": 5.0, "close": 94.0,
    }
    result = classify_ticker("TEST", conds)
    assert result["bucket"] == "TRIGGERED"
    assert result["direction"] == "short"


def test_scanner_runs_without_error():
    """Integration test: scanner.py runs and produces output."""
    result = subprocess.run(
        ["python", "scanner.py", "--date", "2024-06-15"],
        capture_output=True, text=True, timeout=120,
        cwd="/Users/fwang/code/atr-backtest",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "ATR SWING SCANNER" in result.stdout
    assert "REGIME & CHECKLIST" in result.stdout
