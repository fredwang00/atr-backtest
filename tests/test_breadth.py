import pandas as pd
from breadth import parse_breadth_csv, get_regime
from breadth import detect_trend, compute_breadth_health, ratio10_bias, BREADTH_COLUMNS


def test_parse_single_csv():
    df = parse_breadth_csv("breadth_data/mm_2020.csv")
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 200
    assert "up4" in df.columns
    assert "down4" in df.columns
    assert "ratio10" in df.columns
    assert "quarterUp25" in df.columns
    assert "t2108" in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df.index)
    assert df.index[0] < df.index[-1]
    row = df.loc["2020-12-31"]
    assert row["up4"] == 138
    assert row["down4"] == 188


def test_parse_handles_trailing_empty_columns():
    df = parse_breadth_csv("breadth_data/mm_2018.csv")
    assert "up4" in df.columns
    assert len(df) > 200


def _make_df(rows):
    """Helper: build a breadth DataFrame from dicts."""
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2020-01-01", periods=len(rows), freq="B")
    return df


def test_extreme_bearish_low_quarter_up():
    rows = [{"quarterUp25": 250, "quarterDown25": 500, "ratio10": 1.5,
             "ratio5": 1.5, "t2108": 50, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    assert get_regime(df, 4) == "EXTREME_BEARISH"


def test_extreme_bearish_low_t2108():
    rows = [{"quarterUp25": 1000, "quarterDown25": 500, "ratio10": 1.5,
             "ratio5": 1.5, "t2108": 15, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    assert get_regime(df, 4) == "EXTREME_BEARISH"


def test_bearish_ratio_collapse():
    rows = [{"quarterUp25": 1000, "quarterDown25": 500, "ratio10": 0.3,
             "ratio5": 1.5, "t2108": 50, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    assert get_regime(df, 4) == "BEARISH"


def test_bearish_deep_quarterly_inversion():
    """Deep quarterly inversion (30%+) with weak ratio → BEARISH."""
    rows = [{"quarterUp25": 600, "quarterDown25": 900, "ratio10": 0.6,
             "ratio5": 1.0, "t2108": 50, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    assert get_regime(df, 4) == "BEARISH"


def test_mild_quarterly_inversion_is_cautious():
    """Mild quarterly inversion with neutral ratio → CAUTIOUS, not BEARISH."""
    rows = [{"quarterUp25": 800, "quarterDown25": 900, "ratio10": 1.0,
             "ratio5": 1.5, "t2108": 50, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    assert get_regime(df, 4) == "CAUTIOUS"


def test_bearish_persistent_selling():
    rows = [{"quarterUp25": 1000, "quarterDown25": 500, "ratio10": 1.5,
             "ratio5": 1.5, "t2108": 50, "down4": 400, "up4": 200}] * 5
    df = _make_df(rows)
    assert get_regime(df, 4) == "BEARISH"


def test_cautious_narrowing_spread():
    rows = [{"quarterUp25": 1000, "quarterDown25": 900, "ratio10": 1.4,
             "ratio5": 1.5, "t2108": 50, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    assert get_regime(df, 4) == "CAUTIOUS"


def test_bullish_strong_ratio():
    rows = [{"quarterUp25": 1500, "quarterDown25": 800, "ratio10": 2.5,
             "ratio5": 1.5, "t2108": 60, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    assert get_regime(df, 4) == "BULLISH"


def test_extreme_bullish():
    rows = [{"quarterUp25": 1500, "quarterDown25": 800, "ratio10": 3.5,
             "ratio5": 3.5, "t2108": 60, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    assert get_regime(df, 4) == "EXTREME_BULLISH"


def test_neutral_default():
    rows = [{"quarterUp25": 1000, "quarterDown25": 700, "ratio10": 1.3,
             "ratio5": 1.3, "t2108": 50, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    assert get_regime(df, 4) == "NEUTRAL"


def test_priority_order_extreme_bearish_beats_bullish():
    rows = [{"quarterUp25": 200, "quarterDown25": 100, "ratio10": 2.5,
             "ratio5": 1.5, "t2108": 50, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    assert get_regime(df, 4) == "EXTREME_BEARISH"


def _full_row(overrides):
    """Return a dict with all BREADTH_COLUMNS defaulted to 0.0, plus overrides."""
    base = {col: 0.0 for col in BREADTH_COLUMNS}
    base.update(overrides)
    return base


def test_detect_trend_up():
    rows = [_full_row({"ratio10": float(i)}) for i in range(6)]
    df = _make_df(rows)
    assert detect_trend(df, 5, "ratio10", 5) == 1


def test_detect_trend_down():
    rows = [_full_row({"ratio10": float(10 - i)}) for i in range(6)]
    df = _make_df(rows)
    assert detect_trend(df, 5, "ratio10", 5) == -1


def test_detect_trend_flat():
    rows = [_full_row({"ratio10": 1.5})] * 6
    df = _make_df(rows)
    assert detect_trend(df, 5, "ratio10", 5) == 0


def test_breadth_health_improving():
    base = {"up4": 400, "down4": 50, "ratio5": 2.0, "ratio10": 0,
            "quarterUp25": 1500, "quarterDown25": 800,
            "monthUp25": 200, "monthDown25": 50, "monthUp50": 10,
            "monthDown50": 5, "up13_34": 1500, "down13_34": 500,
            "t2108": 0, "universe": 6000}
    rows = []
    for i in range(15):
        r = base.copy()
        r["ratio10"] = 1.5 + i * 0.1
        r["t2108"] = 40 + i * 2
        r["quarterUp25"] = 1200 + i * 30
        rows.append(r)
    df = _make_df(rows)
    score, trend = compute_breadth_health(df, 14)
    assert score >= 4
    assert trend == "IMPROVING"


def test_breadth_health_deteriorating_fast():
    base = {"up4": 50, "down4": 500, "ratio5": 0.5, "ratio10": 0,
            "quarterUp25": 800, "quarterDown25": 1200,
            "monthUp25": 50, "monthDown25": 200, "monthUp50": 5,
            "monthDown50": 20, "up13_34": 500, "down13_34": 0,
            "t2108": 0, "universe": 6000}
    rows = []
    for i in range(15):
        r = base.copy()
        r["ratio10"] = 2.0 - i * 0.1
        r["t2108"] = 60 - i * 2
        r["quarterUp25"] = 1000 - i * 20
        r["down13_34"] = 1000 + i * 50
        rows.append(r)
    df = _make_df(rows)
    score, trend = compute_breadth_health(df, 14)
    assert score <= -5
    assert trend == "DETERIORATING_FAST"


def test_ratio10_bias():
    row = pd.Series({"ratio10": 2.0})
    assert ratio10_bias(row) == "long"
    row = pd.Series({"ratio10": 0.5})
    assert ratio10_bias(row) == "short"
    row = pd.Series({"ratio10": 1.0})
    assert ratio10_bias(row) == "neutral"


def test_load_breadth_data_combines_all_years():
    from breadth import load_breadth_data
    df = load_breadth_data("breadth_data")
    assert df.index.min().year <= 2018
    assert df.index.max().year >= 2026
    assert len(df) > 2000
    assert df.index.is_monotonic_increasing
    assert "regime" in df.columns
    assert "breadth_score" in df.columns
    assert "breadth_trend" in df.columns
    assert "ratio10_bias" in df.columns
