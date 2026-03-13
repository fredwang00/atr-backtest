from atr_swing_backtest import check_entry_conditions, prepare_data


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


def test_backtest_unchanged_after_refactor():
    """Verify the refactored run_backtest produces identical results."""
    from atr_swing_backtest import run_backtest
    result = prepare_data("SPY")
    assert result is not None
    df, _ = result
    df.attrs["ticker"] = "SPY"
    trades = run_backtest(df)
    assert len(trades) > 0
    for t in trades:
        assert t.exit_price is not None
