# Breadth Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Pradeep's Stockbee Market Monitor breadth data as a regime filter into the ATR swing backtest, add earnings blackout filter, and compare filtered vs unfiltered results to quantify edge improvement.

**Architecture:** Three new modules (`breadth.py`, `earnings.py`, `compare.py`) that import from the existing `atr_swing_backtest.py`. The backtest gains an optional `entry_filter` callback and `size_mult` field — standalone behavior unchanged. `compare.py` orchestrates 6+ filter configurations and produces a comparison table.

**Tech Stack:** Python, pandas, numpy, yfinance (already installed). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-03-12-breadth-integration-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `breadth.py` | Create | Parse breadth CSVs, compute regime + breadth health + ratio10 bias |
| `tests/test_breadth.py` | Create | Unit tests for parsing, regime classification, breadth health scoring |
| `earnings.py` | Create | Fetch earnings dates from yfinance, provide blackout set |
| `tests/test_earnings.py` | Create | Unit tests for blackout window logic |
| `compare.py` | Create | Run backtest under 6+ filter configs, produce comparison table |
| `tests/test_compare.py` | Create | Integration test: compare runs and produces valid output |
| `atr_swing_backtest.py` | Modify | Add `entry_filter` param to `run_backtest()`, add `size_mult` to Trade |

---

## Task 1: Breadth CSV Parsing

**Files:**
- Create: `breadth.py`
- Create: `tests/test_breadth.py`

- [ ] **Step 1: Write failing test for CSV parsing**

```python
# tests/test_breadth.py
import pandas as pd
from breadth import parse_breadth_csv

def test_parse_single_csv():
    df = parse_breadth_csv("breadth_data/mm_2020.csv")
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 200  # 2020 has ~265 rows (header + data)
    assert "up4" in df.columns
    assert "down4" in df.columns
    assert "ratio10" in df.columns
    assert "quarterUp25" in df.columns
    assert "t2108" in df.columns
    # Date index should be datetime
    assert pd.api.types.is_datetime64_any_dtype(df.index)
    # First row (chronological) should be earliest date
    assert df.index[0] < df.index[-1]
    # Spot check a known value: 12/31/2020 has up4=138
    row = df.loc["2020-12-31"]
    assert row["up4"] == 138
    assert row["down4"] == 188

def test_parse_handles_trailing_empty_columns():
    df = parse_breadth_csv("breadth_data/mm_2018.csv")
    # 2018 CSV has extra trailing empty columns and whitespace in headers
    assert "up4" in df.columns
    assert len(df) > 200

def test_load_breadth_data_combines_all_years():
    from breadth import load_breadth_data
    df = load_breadth_data("breadth_data")
    # Should have data from 2018 through 2026
    assert df.index.min().year <= 2018
    assert df.index.max().year >= 2026
    assert len(df) > 2000  # ~2145 trading days
    # Should be chronological
    assert df.index.is_monotonic_increasing
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fwang/code/atr-backtest && python -m pytest tests/test_breadth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'breadth'`

- [ ] **Step 3: Implement CSV parsing**

```python
# breadth.py
"""
Stockbee Market Monitor breadth data parser and regime classifier.

Parses Pradeep Bonde's daily breadth CSVs and computes:
- Market regime (EXTREME_BEARISH through EXTREME_BULLISH)
- Breadth health composite score
- Simple ratio10 directional bias
"""

import pandas as pd
import numpy as np
import os
import glob


# Column names mapped from CSV ordinal position
BREADTH_COLUMNS = [
    "up4", "down4", "ratio5", "ratio10",
    "quarterUp25", "quarterDown25",
    "monthUp25", "monthDown25", "monthUp50", "monthDown50",
    "up13_34", "down13_34",
    "universe", "t2108",
]


def parse_breadth_csv(filepath):
    """Parse a single year's breadth CSV into a DataFrame."""
    df = pd.read_csv(filepath, dtype=str)

    # First column is always the date (may have whitespace in header)
    date_col = df.columns[0]
    rows = []

    for _, raw_row in df.iterrows():
        date_str = str(raw_row[date_col]).strip().strip('"')
        if not date_str or date_str.lower() == "nan":
            continue

        try:
            date = pd.to_datetime(date_str, format="mixed")
        except (ValueError, TypeError):
            continue

        # Extract numeric values by ordinal position (skip date column)
        nums = []
        for val in raw_row.iloc[1:]:
            val_str = str(val).strip().strip('"')
            if not val_str or val_str.lower() == "nan":
                continue
            # Remove commas from numbers like "6,388"
            val_str = val_str.replace(",", "")
            try:
                nums.append(float(val_str))
            except ValueError:
                continue

        if len(nums) < len(BREADTH_COLUMNS):
            continue

        row_dict = {"date": date}
        for j, col_name in enumerate(BREADTH_COLUMNS):
            row_dict[col_name] = nums[j]
        rows.append(row_dict)

    result = pd.DataFrame(rows)
    result = result.set_index("date").sort_index()
    return result


def load_breadth_data(data_dir="breadth_data"):
    """Load all year CSVs, combine, and compute signals."""
    files = sorted(glob.glob(os.path.join(data_dir, "mm_*.csv")))
    if not files:
        raise FileNotFoundError(f"No breadth CSVs found in {data_dir}")

    frames = [parse_breadth_csv(f) for f in files]
    df = pd.concat(frames).sort_index()
    # Remove duplicate dates (year boundaries may overlap)
    df = df[~df.index.duplicated(keep="first")]

    # Compute signals
    regimes = []
    scores = []
    trends = []
    biases = []
    for idx in range(len(df)):
        regimes.append(get_regime(df, idx))
        score, trend = compute_breadth_health(df, idx)
        scores.append(score)
        trends.append(trend)
        biases.append(ratio10_bias(df.iloc[idx]))

    df["regime"] = regimes
    df["breadth_score"] = scores
    df["breadth_trend"] = trends
    df["ratio10_bias"] = biases

    return df
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fwang/code/atr-backtest && python -m pytest tests/test_breadth.py -v`
Expected: PASS (the signal functions don't exist yet but `load_breadth_data` will fail — that's tested separately. Only the parse tests should pass.)

Note: `test_load_breadth_data_combines_all_years` will fail because `get_regime`, `compute_breadth_health`, and `ratio10_bias` don't exist yet. That's expected — they're built in Tasks 2-3.

- [ ] **Step 5: Commit**

```bash
git add breadth.py tests/test_breadth.py
git commit -m "feat: add breadth CSV parser for Stockbee Market Monitor data"
```

---

## Task 2: Regime Classification

**Files:**
- Modify: `breadth.py`
- Modify: `tests/test_breadth.py`

- [ ] **Step 1: Write failing tests for regime classification**

Add to `tests/test_breadth.py`:

```python
from breadth import get_regime

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
    # 5 of 5 days with down4 > 350
    assert get_regime(df, 4) == "BEARISH"

def test_cautious_narrowing_spread():
    rows = [{"quarterUp25": 1000, "quarterDown25": 900, "ratio10": 1.4,
             "ratio5": 1.5, "t2108": 50, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    # quarterDown25 (900) > quarterUp25 * 0.85 (850) AND ratio10 < 1.5
    assert get_regime(df, 4) == "CAUTIOUS"

def test_bullish_strong_ratio():
    rows = [{"quarterUp25": 1500, "quarterDown25": 800, "ratio10": 2.5,
             "ratio5": 1.5, "t2108": 60, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    # ratio10 > 2 AND quarterUp25 > quarterDown25 * 1.3
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
    # quarterUp25 < 300 triggers EXTREME_BEARISH even though ratio10 > 2
    rows = [{"quarterUp25": 200, "quarterDown25": 100, "ratio10": 2.5,
             "ratio5": 1.5, "t2108": 50, "down4": 100, "up4": 200}] * 5
    df = _make_df(rows)
    assert get_regime(df, 4) == "EXTREME_BEARISH"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fwang/code/atr-backtest && python -m pytest tests/test_breadth.py::test_extreme_bearish_low_quarter_up -v`
Expected: FAIL — `ImportError: cannot import name 'get_regime'`

- [ ] **Step 3: Implement regime classification**

Add to `breadth.py`:

```python
def get_regime(df, idx):
    """
    Classify market regime. Exact port of getRegime() from
    market-monitor/app/src/App.tsx. Priority-ordered, first match wins.
    """
    row = df.iloc[idx]
    qUp = row["quarterUp25"]
    qDn = row["quarterDown25"]
    r10 = row["ratio10"]
    r5 = row["ratio5"]
    t = row["t2108"]
    d4 = row["down4"]
    u4 = row["up4"]

    # 1. EXTREME_BEARISH
    if qUp < 300 or t < 20:
        return "EXTREME_BEARISH"

    # 2. BEARISH — ratio collapse
    if r10 < 0.5 or r5 < 0.4:
        return "BEARISH"

    # 3. BEARISH — quarterly inversion with weak ratio
    if qDn > qUp and r10 < 1.2:
        return "BEARISH"

    # 4-6 require 5-day lookback
    recent_net_neg = 0
    recent_big_down = 0
    if idx >= 4:
        for j in range(idx - 4, idx + 1):
            r = df.iloc[j]
            if r["down4"] > r["up4"]:
                recent_net_neg += 1
            if r["down4"] > 350:
                recent_big_down += 1

    # 4. BEARISH — persistent heavy selling
    if recent_big_down >= 3:
        return "BEARISH"

    # 5. CAUTIOUS — quarterly spread narrowing
    if qDn > qUp * 0.85 and r10 < 1.5:
        return "CAUTIOUS"

    # 6. CAUTIOUS — recent net-negative clustering
    if recent_net_neg >= 3 and r10 < 1.3:
        return "CAUTIOUS"

    # 7. EXTREME_BULLISH
    if (t > 85 and r10 > 2.5) or (r10 > 3 and r5 > 3):
        return "EXTREME_BULLISH"

    # 8. BULLISH
    if (r10 > 2 and qUp > qDn * 1.3) or (r10 > 1.5 and qUp > 1000 and qUp > qDn * 1.1):
        return "BULLISH"

    # 9. Default
    return "NEUTRAL"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fwang/code/atr-backtest && python -m pytest tests/test_breadth.py -k "regime or bearish or bullish or neutral or cautious or priority" -v`
Expected: All regime tests PASS

- [ ] **Step 5: Commit**

```bash
git add breadth.py tests/test_breadth.py
git commit -m "feat: add regime classification (port of market-monitor getRegime)"
```

---

## Task 3: Breadth Health Score + ratio10 Bias

**Files:**
- Modify: `breadth.py`
- Modify: `tests/test_breadth.py`

- [ ] **Step 1: Write failing tests for breadth health and ratio10 bias**

Add to `tests/test_breadth.py`:

```python
from breadth import detect_trend, compute_breadth_health, ratio10_bias

def test_detect_trend_up():
    # 6 values, 5 comparisons, all up -> trend = 1
    rows = [{"ratio10": float(i)} for i in range(6)]
    for col in BREADTH_COLUMNS:
        for r in rows:
            r.setdefault(col, 0.0)
    df = _make_df(rows)
    assert detect_trend(df, 5, "ratio10", 5) == 1

def test_detect_trend_down():
    rows = [{"ratio10": float(10 - i)} for i in range(6)]
    for col in BREADTH_COLUMNS:
        for r in rows:
            r.setdefault(col, 0.0)
    df = _make_df(rows)
    assert detect_trend(df, 5, "ratio10", 5) == -1

def test_detect_trend_flat():
    rows = [{"ratio10": 1.5}] * 6
    for col in BREADTH_COLUMNS:
        for r in rows:
            r.setdefault(col, 0.0)
    df = _make_df(rows)
    assert detect_trend(df, 5, "ratio10", 5) == 0

def test_breadth_health_improving():
    # Strong bullish signals: ratio10 trending up, t2108 rising,
    # quarterUp25 expanding, healthy spread, mostly green days
    base = {"up4": 400, "down4": 50, "ratio5": 2.0, "ratio10": 0,
            "quarterUp25": 1500, "quarterDown25": 800,
            "monthUp25": 200, "monthDown25": 50, "monthUp50": 10,
            "monthDown50": 5, "up13_34": 1500, "down13_34": 500,
            "t2108": 0, "universe": 6000}
    rows = []
    for i in range(15):
        r = base.copy()
        r["ratio10"] = 1.5 + i * 0.1  # trending up
        r["t2108"] = 40 + i * 2       # rising
        r["quarterUp25"] = 1200 + i * 30  # expanding
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
        r["ratio10"] = 2.0 - i * 0.1  # trending down
        r["t2108"] = 60 - i * 2       # falling
        r["quarterUp25"] = 1000 - i * 20  # declining
        r["down13_34"] = 1000 + i * 50  # expanding
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
```

Add this import at the top of the test file:

```python
from breadth import BREADTH_COLUMNS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fwang/code/atr-backtest && python -m pytest tests/test_breadth.py::test_detect_trend_up -v`
Expected: FAIL — `ImportError: cannot import name 'detect_trend'`

- [ ] **Step 3: Implement detect_trend, compute_breadth_health, ratio10_bias**

Add to `breadth.py`:

```python
def detect_trend(df, idx, field, lookback):
    """
    Check if a field is trending up or down over the lookback period.
    Returns 1 (up), -1 (down), or 0 (flat).
    Threshold: 70% of days must be directionally consistent (4+ of 5).
    """
    if idx < lookback:
        return 0
    vals = [df.iloc[i][field] for i in range(idx - lookback, idx + 1)]
    up = 0
    dn = 0
    for i in range(1, len(vals)):
        if vals[i] > vals[i - 1]:
            up += 1
        elif vals[i] < vals[i - 1]:
            dn += 1
    if up >= lookback * 0.7:
        return 1
    if dn >= lookback * 0.7:
        return -1
    return 0


def compute_breadth_health(df, idx):
    """
    Compute breadth health composite score. Exact port of
    computeBreadthHealth() from market-monitor App.tsx.
    Returns (score, trend_label).
    """
    if idx < 10:
        return 0, "STEADY"

    row = df.iloc[idx]
    score = 0

    # ratio10 trend
    r10_trend = detect_trend(df, idx, "ratio10", 5)
    if r10_trend == 1:
        score += 2
    elif r10_trend == -1:
        score -= 2

    # t2108 trend
    t_trend = detect_trend(df, idx, "t2108", 5)
    if t_trend == 1:
        score += 1
    elif t_trend == -1:
        score -= 1

    # quarterUp25 trend
    q_trend = detect_trend(df, idx, "quarterUp25", 5)
    if q_trend == 1:
        score += 1
    elif q_trend == -1:
        score -= 2

    # Quarterly spread
    q_spread = row["quarterUp25"] - row["quarterDown25"]
    if q_spread > 300:
        score += 1
    elif q_spread < 0:
        score -= 2

    # Last 5 days analysis
    start = max(0, idx - 4)
    last5 = [df.iloc[i] for i in range(start, idx + 1)]

    big_down_count = sum(1 for d in last5 if d["down4"] > 300)
    if big_down_count >= 3:
        score -= 3
    elif big_down_count >= 2:
        score -= 1

    big_up_count = sum(1 for d in last5 if d["up4"] > 300)
    if big_up_count >= 4:
        score += 2

    red_days = sum(1 for d in last5 if d["down4"] > d["up4"])
    if red_days >= 4:
        score -= 2
    elif red_days <= 1 and len(last5) >= 4:
        score += 1

    # Monthly divergence
    if row["monthDown25"] > row["monthUp25"] * 1.5 and row["monthDown25"] > 100:
        score -= 1

    # Froth
    if row["monthUp50"] > 30:
        score -= 1

    # Down 13/34 expansion
    d1334_trend = detect_trend(df, idx, "down13_34", 5)
    if d1334_trend == 1:
        score -= 1

    # Map score to trend label
    if score >= 4:
        trend = "IMPROVING"
    elif score >= 2:
        trend = "SLIGHTLY_IMPROVING"
    elif score >= -1:
        trend = "STEADY"
    elif score >= -3:
        trend = "SLIGHTLY_DETERIORATING"
    elif score >= -5:
        trend = "DETERIORATING"
    else:
        trend = "DETERIORATING_FAST"

    return score, trend


def ratio10_bias(row):
    """Simple directional bias from ratio10."""
    r10 = row["ratio10"]
    if r10 > 1.5:
        return "long"
    elif r10 < 0.8:
        return "short"
    return "neutral"
```

- [ ] **Step 4: Run all breadth tests**

Run: `cd /Users/fwang/code/atr-backtest && python -m pytest tests/test_breadth.py -v`
Expected: ALL PASS (including the `test_load_breadth_data_combines_all_years` test from Task 1, which now has all dependencies)

- [ ] **Step 5: Commit**

```bash
git add breadth.py tests/test_breadth.py
git commit -m "feat: add breadth health scoring and ratio10 bias"
```

---

## Task 4: Earnings Blackout Filter

**Files:**
- Create: `earnings.py`
- Create: `tests/test_earnings.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_earnings.py
import pandas as pd
from earnings import get_earnings_blackout

def test_blackout_returns_set_of_timestamps():
    blackout = get_earnings_blackout("AAPL", "2023-01-01", "2024-01-01")
    assert isinstance(blackout, set)
    # AAPL reports quarterly — expect at least 3-4 earnings in a year
    assert len(blackout) >= 12  # 4 earnings * (2 before + 1 earnings + 1 after) = 16

def test_blackout_window_size():
    # Each earnings date produces before + 1 (the date) + after blacked out days
    blackout = get_earnings_blackout("AAPL", "2023-01-01", "2024-01-01", before=2, after=1)
    # At least 4 earnings * 4 days each
    assert len(blackout) >= 12

def test_blackout_dates_are_within_range():
    blackout = get_earnings_blackout("SPY", "2023-01-01", "2024-01-01")
    for dt in blackout:
        # Allow some slack for the window extending beyond range
        assert dt.year >= 2022 and dt.year <= 2025
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fwang/code/atr-backtest && python -m pytest tests/test_earnings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'earnings'`

- [ ] **Step 3: Implement earnings blackout**

```python
# earnings.py
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

    # Build a trading day calendar from yfinance data
    price_data = yf.download(ticker, start=start_date, end=end_date, progress=False)
    if isinstance(price_data.columns, pd.MultiIndex):
        price_data.columns = price_data.columns.get_level_values(0)
    trading_days = price_data.index.tolist()

    if not trading_days:
        return set()

    blackout = set()
    for ed in earnings_dates:
        # Normalize to midnight for comparison
        ed_ts = pd.Timestamp(ed).normalize()

        # Find the closest trading day to this earnings date
        closest_idx = None
        for i, td in enumerate(trading_days):
            if td.normalize() >= ed_ts:
                closest_idx = i
                break
        if closest_idx is None:
            # Earnings date is after our data range
            closest_idx = len(trading_days) - 1

        # Add the blackout window
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

        # Cache for next time
        cache_df = pd.DataFrame({"date": earnings_dates})
        cache_df.to_csv(cache_path, index=False)

        return earnings_dates
    except Exception:
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fwang/code/atr-backtest && python -m pytest tests/test_earnings.py -v`
Expected: PASS (first run will hit yfinance API, subsequent runs use cache)

- [ ] **Step 5: Commit**

```bash
git add earnings.py tests/test_earnings.py
git commit -m "feat: add earnings blackout filter with caching"
```

---

## Task 5: Modify atr_swing_backtest.py — entry_filter + size_mult

**Files:**
- Modify: `atr_swing_backtest.py`

- [ ] **Step 1: Add `entry_filter` parameter to `run_backtest()`**

Change line 290:
```python
def run_backtest(df, entry_filter=None):
```

Add filter check after line 377 (`if trade is not None:`), before `simulate_trade`:
```python
        if trade is not None:
            # Apply external filter if provided
            if entry_filter is not None and not entry_filter(df, i, trade.direction):
                trade = None

        if trade is not None:
            simulate_trade(df, trade)
            trades.append(trade)
            in_trade = True
            current_trade = trade
```

- [ ] **Step 2: Add `size_mult` field to Trade dataclass**

After line 270 (`hit_full: bool = False`), add:
```python
    size_mult: float = 1.0
```

- [ ] **Step 3: Verify standalone backtest still works**

Run: `cd /Users/fwang/code/atr-backtest && python atr_swing_backtest.py 2>&1 | grep "ALL TICKERS COMBINED" -A 5`
Expected: Same results as before (242 trades, 86.8% WR) — `entry_filter=None` preserves behavior.

- [ ] **Step 4: Commit**

```bash
git add atr_swing_backtest.py
git commit -m "feat: add entry_filter and size_mult to backtest for external filtering"
```

---

## Task 6: Comparison Runner

**Files:**
- Create: `compare.py`
- Create: `tests/test_compare.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/test_compare.py
import subprocess

def test_compare_runs_without_error():
    """Integration test: compare.py produces output and exits cleanly."""
    result = subprocess.run(
        ["python", "compare.py"],
        capture_output=True, text=True, timeout=600
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # Should contain the comparison table header
    assert "Baseline" in result.stdout
    assert "+Regime" in result.stdout
    assert "+Earnings" in result.stdout
    # Should contain key metrics
    assert "Win Rate" in result.stdout or "win_rate" in result.stdout
    assert "Sharpe" in result.stdout or "sharpe" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fwang/code/atr-backtest && python -m pytest tests/test_compare.py -v`
Expected: FAIL — `FileNotFoundError` or `ModuleNotFoundError`

- [ ] **Step 3: Implement compare.py**

```python
# compare.py
"""
Comparison runner: tests ATR swing backtest under multiple filter configurations
to quantify whether breadth data and earnings filters improve edge.
"""

import pandas as pd
import numpy as np
import os

from atr_swing_backtest import (
    TICKERS, prepare_data, run_backtest, print_trade_summary,
    trades_to_dataframe, OUTPUT_DIR, POSITION_SIZE,
)
from breadth import load_breadth_data
from earnings import get_earnings_blackout

# Regimes where longs are allowed
LONG_REGIMES = {"NEUTRAL", "BULLISH", "EXTREME_BULLISH"}
# Regimes where shorts are allowed
SHORT_REGIMES = {"NEUTRAL", "BEARISH", "EXTREME_BEARISH"}
# Breadth trends where we reduce size
REDUCE_SIZE_TRENDS = {"DETERIORATING", "DETERIORATING_FAST"}


def make_regime_filter(breadth_df):
    """Create entry filter using full Pradeep regime classification."""
    def entry_filter(df, i, direction):
        date = df.index[i]
        # Find matching or most recent breadth row
        mask = breadth_df.index <= date
        if not mask.any():
            return True  # No breadth data yet, allow trade
        regime = breadth_df.loc[mask].iloc[-1]["regime"]
        if direction == "long":
            return regime in LONG_REGIMES
        else:
            return regime in SHORT_REGIMES
    return entry_filter


def make_ratio10_filter(breadth_df):
    """Create entry filter using simple ratio10 bias."""
    def entry_filter(df, i, direction):
        date = df.index[i]
        mask = breadth_df.index <= date
        if not mask.any():
            return True
        bias = breadth_df.loc[mask].iloc[-1]["ratio10_bias"]
        if direction == "long":
            return bias in ("long", "neutral")
        else:
            return bias in ("short", "neutral")
    return entry_filter


def make_earnings_filter(blackout_sets):
    """Create entry filter that skips trades near earnings."""
    def entry_filter(df, i, direction):
        date = df.index[i]
        ticker = df.attrs.get("ticker", "")
        if ticker in blackout_sets:
            return date not in blackout_sets[ticker]
        return True
    return entry_filter


def make_combined_filter(*filters):
    """Combine multiple entry filters (all must return True)."""
    def entry_filter(df, i, direction):
        return all(f(df, i, direction) for f in filters)
    return entry_filter


def add_regime_at_entry(trades, breadth_df):
    """Annotate each trade with the breadth regime on entry date."""
    for t in trades:
        mask = breadth_df.index <= t.entry_date
        if mask.any():
            t._regime_at_entry = breadth_df.loc[mask].iloc[-1]["regime"]
        else:
            t._regime_at_entry = "UNKNOWN"


def compute_stats(trades):
    """Compute summary stats for a list of trades."""
    completed = [t for t in trades if t.exit_price is not None]
    if not completed:
        return {
            "trades": 0, "win_rate": 0, "avg_pnl": 0, "sharpe": 0,
            "profit_factor": 0, "max_dd": 0, "longs": 0, "shorts": 0,
        }

    n = len(completed)
    pnls = [t.pnl_pct for t in completed]
    winners = [t for t in completed if t.pnl_pct > 0]
    losers = [t for t in completed if t.pnl_pct <= 0]

    gross_profit = sum(t.pnl_pct for t in winners)
    gross_loss = abs(sum(t.pnl_pct for t in losers))
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    cum = np.cumsum(pnls)
    cum_max = np.maximum.accumulate(cum)
    max_dd = (cum - cum_max).min() * 100

    if len(pnls) > 1 and np.std(pnls) > 0:
        first = completed[0].entry_date
        last = completed[-1].exit_date or completed[-1].entry_date
        years = max((last - first).days / 365.25, 0.1)
        tpy = n / years
        sharpe = (np.mean(pnls) / np.std(pnls)) * np.sqrt(tpy)
    else:
        sharpe = 0.0

    return {
        "trades": n,
        "longs": sum(1 for t in completed if t.direction == "long"),
        "shorts": sum(1 for t in completed if t.direction == "short"),
        "win_rate": len(winners) / n * 100,
        "avg_pnl": np.mean(pnls) * 100,
        "sharpe": sharpe,
        "profit_factor": pf,
        "max_dd": max_dd,
    }


def main():
    print("=" * 70)
    print("  BREADTH INTEGRATION COMPARISON")
    print("=" * 70)

    # Load breadth data once
    print("\nLoading breadth data...")
    breadth_df = load_breadth_data("breadth_data")
    print(f"  {len(breadth_df)} days loaded, {breadth_df.index.min().date()} to {breadth_df.index.max().date()}")

    # Build earnings blackout sets
    print("Loading earnings dates...")
    blackout_sets = {}
    for ticker in TICKERS:
        blackout_sets[ticker] = get_earnings_blackout(ticker, "2018-01-01", "2026-12-31")
        print(f"  {ticker}: {len(blackout_sets[ticker])} blackout days")

    # Build filters
    regime_filter = make_regime_filter(breadth_df)
    ratio10_filter = make_ratio10_filter(breadth_df)
    earnings_filter = make_earnings_filter(blackout_sets)

    configs = [
        ("Baseline", None),
        ("+Earnings", earnings_filter),
        ("+Regime", regime_filter),
        ("+Regime+Earnings", make_combined_filter(regime_filter, earnings_filter)),
        ("+Ratio10", ratio10_filter),
        ("+Ratio10+Earnings", make_combined_filter(ratio10_filter, earnings_filter)),
    ]

    # Run all configs
    all_results = {}
    all_trade_logs = {}

    for config_name, entry_filter in configs:
        print(f"\nRunning: {config_name}...")
        all_trades = []

        for ticker in TICKERS:
            try:
                result = prepare_data(ticker)
                if result is None:
                    continue
                df, _ = result
                df.attrs["ticker"] = ticker
                trades = run_backtest(df, entry_filter=entry_filter)
                add_regime_at_entry(trades, breadth_df)
                all_trades.extend(trades)
            except Exception as e:
                print(f"  ERROR on {ticker}: {e}")

        stats = compute_stats(all_trades)
        all_results[config_name] = stats
        all_trade_logs[config_name] = all_trades
        print(f"  {config_name}: {stats['trades']} trades, "
              f"WR={stats['win_rate']:.1f}%, "
              f"Avg={stats['avg_pnl']:.2f}%, "
              f"Sharpe={stats['sharpe']:.2f}")

    # Print comparison table
    print("\n" + "=" * 70)
    print("  COMPARISON TABLE")
    print("=" * 70)
    header = f"  {'Config':<22s} {'Trades':>6s} {'WR%':>6s} {'AvgP&L':>8s} {'Sharpe':>7s} {'PF':>6s} {'MaxDD':>8s} {'L/S':>8s}"
    print(header)
    print("  " + "-" * 68)
    for name, stats in all_results.items():
        ls = f"{stats['longs']}/{stats['shorts']}"
        pf_str = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "inf"
        print(f"  {name:<22s} {stats['trades']:>6d} {stats['win_rate']:>5.1f}% "
              f"{stats['avg_pnl']:>+7.2f}% {stats['sharpe']:>7.2f} {pf_str:>6s} "
              f"{stats['max_dd']:>+7.2f}% {ls:>8s}")

    # Save comparison CSV
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    comp_df = pd.DataFrame(all_results).T
    comp_df.index.name = "config"
    comp_path = os.path.join(OUTPUT_DIR, "comparison.csv")
    comp_df.to_csv(comp_path)
    print(f"\nComparison saved: {comp_path}")

    # Save per-config trade logs
    for config_name, trades in all_trade_logs.items():
        if trades:
            tdf = trades_to_dataframe(trades)
            tdf["regime_at_entry"] = [getattr(t, "_regime_at_entry", "UNKNOWN") for t in trades]
            safe_name = config_name.replace("+", "plus_").replace(" ", "_").lower()
            path = os.path.join(OUTPUT_DIR, f"trades_{safe_name}.csv")
            tdf.to_csv(path, index=False)

    print(f"\nTrade logs saved to {OUTPUT_DIR}/trades_*.csv")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the integration test**

Run: `cd /Users/fwang/code/atr-backtest && python -m pytest tests/test_compare.py -v --timeout=600`
Expected: PASS

- [ ] **Step 5: Run compare.py manually and review output**

Run: `cd /Users/fwang/code/atr-backtest && python compare.py`
Expected: Comparison table showing all 6 configs with metrics. Verify the baseline matches the standalone backtest results (242 trades, ~86.8% WR).

- [ ] **Step 6: Commit**

```bash
git add compare.py tests/test_compare.py
git commit -m "feat: add comparison runner for breadth-filtered vs baseline backtest"
```

---

## Task 7: Breadth-Health Sizing Variant

**Files:**
- Modify: `compare.py`

- [ ] **Step 1: Add sizing variant to compare.py**

Add a 7th config after the existing 6 in the `configs` list. This one uses the regime filter + earnings filter, but also applies half-sizing when breadth trend is deteriorating.

Add a new filter builder:

```python
def make_regime_with_sizing_filter(breadth_df):
    """Regime filter that also sets size_mult based on breadth health."""
    def entry_filter(df, i, direction):
        date = df.index[i]
        mask = breadth_df.index <= date
        if not mask.any():
            return True
        brow = breadth_df.loc[mask].iloc[-1]
        regime = brow["regime"]

        # Check regime
        if direction == "long" and regime not in LONG_REGIMES:
            return False
        if direction == "short" and regime not in SHORT_REGIMES:
            return False

        return True

    def size_func(df, i):
        date = df.index[i]
        mask = breadth_df.index <= date
        if not mask.any():
            return 1.0
        trend = breadth_df.loc[mask].iloc[-1]["breadth_trend"]
        if trend in REDUCE_SIZE_TRENDS:
            return 0.5
        return 1.0

    return entry_filter, size_func
```

This requires modifying `run_backtest` to accept an optional `size_func` parameter — or applying the size after the trade is created. The simpler approach: apply sizing in `compare.py` after `run_backtest` returns, by adjusting `trade.size_mult` before stats are computed.

After the backtest loop in `main()`, before `compute_stats`, add a sizing pass for the 7th config:

```python
    # Add regime+earnings+sizing config
    regime_entry, size_fn = make_regime_with_sizing_filter(breadth_df)
    combined_filter = make_combined_filter(regime_entry, earnings_filter)
    configs.append(("+Regime+Earn+Sizing", combined_filter))
```

Then after trades are collected for this config, apply sizing:

```python
        # Apply sizing for the sizing variant
        if "Sizing" in config_name:
            _, size_fn = make_regime_with_sizing_filter(breadth_df)
            for t in all_trades:
                date = t.entry_date
                mask = breadth_df.index <= date
                if mask.any():
                    trend = breadth_df.loc[mask].iloc[-1]["breadth_trend"]
                    if trend in REDUCE_SIZE_TRENDS:
                        t.size_mult = 0.5
                        t.pnl_pct *= 0.5
```

- [ ] **Step 2: Run compare.py to verify the 7th config appears**

Run: `cd /Users/fwang/code/atr-backtest && python compare.py 2>&1 | grep "Sizing"`
Expected: One row showing the sizing variant's results.

- [ ] **Step 3: Commit**

```bash
git add compare.py
git commit -m "feat: add breadth-health sizing variant to comparison runner"
```

---

## Task 8: Final Verification

- [ ] **Step 1: Run all tests**

Run: `cd /Users/fwang/code/atr-backtest && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Run standalone backtest to verify no regression**

Run: `cd /Users/fwang/code/atr-backtest && python atr_swing_backtest.py 2>&1 | grep "ALL TICKERS COMBINED" -A 5`
Expected: 242 trades, ~86.8% win rate (unchanged)

- [ ] **Step 3: Run full comparison**

Run: `cd /Users/fwang/code/atr-backtest && python compare.py`
Expected: Complete comparison table with 7 configs. Review for:
- Baseline matches standalone results
- Regime filter reduces trade count (trades in CAUTIOUS/wrong-direction regimes removed)
- Earnings filter removes a subset of trades
- Combined filter is the most selective
- Sharpe and win rate for filtered configs should be >= baseline

- [ ] **Step 4: Update context doc**

Add to `ATR_BACKTEST_CONTEXT.md` under "Key files":
```
- `breadth.py` — Pradeep's market monitor breadth parser + regime classifier
- `earnings.py` — Earnings blackout filter (yfinance-based, cached)
- `compare.py` — Runs 7 filter configurations side-by-side
- `breadth_data/` — Raw breadth CSVs from Google Sheets (2018-2026)
```

- [ ] **Step 5: Commit everything**

```bash
git add -A
git commit -m "docs: update context doc with new breadth integration files"
```
