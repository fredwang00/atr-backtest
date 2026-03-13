import pandas as pd
from breadth import parse_breadth_csv, get_regime


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


def test_bearish_quarterly_inversion():
    rows = [{"quarterUp25": 800, "quarterDown25": 900, "ratio10": 1.0,
             "ratio5": 1.5, "t2108": 50, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    assert get_regime(df, 4) == "BEARISH"


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
