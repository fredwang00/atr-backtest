import pandas as pd
from breadth import parse_breadth_csv


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
