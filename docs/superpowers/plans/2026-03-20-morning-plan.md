# Morning Plan Mode Implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `morning.py` command that shows readiness, VIX pivot, SPY/QQQ ATR levels, and regime checklist for the pre-market 0DTE planning routine.

**Architecture:** New `morning.py` standalone script. Extract shared regime/checklist display from `scanner.py` into `compliance.py`. Reuse existing `download_ohlcv`, `compute_indicators`, `load_breadth_data`.

**Tech Stack:** Python, pandas, yfinance (existing), PyYAML for frontmatter parsing

**Spec:** `docs/superpowers/specs/2026-03-20-morning-plan-design.md`

---

### Task 1: Extract `print_regime_checklist` from scanner into compliance

**Files:**
- Modify: `compliance.py`
- Modify: `scanner.py:211-237`
- Test: `tests/test_compliance.py`

- [ ] **Step 1: Write failing test for print_regime_checklist**

Add to `tests/test_compliance.py`:

```python
from compliance import print_regime_checklist


def test_print_regime_checklist_bearish(capsys):
    """Bearish regime prints no allowed structures and correct sizing."""
    print_regime_checklist("BEARISH", score=-3, trend="SLIGHTLY_DETERIORATING",
                           r10=0.75, bias="short")
    output = capsys.readouterr().out
    assert "BEARISH" in output
    assert "None (no premium selling)" in output
    assert "0.25x" in output


def test_print_regime_checklist_bullish(capsys):
    """Bullish regime prints all structures allowed."""
    print_regime_checklist("BULLISH", score=4, trend="IMPROVING",
                           r10=2.1, bias="long")
    output = capsys.readouterr().out
    assert "FULL SIZE" in output
    assert "Call credit spread" in output
    assert "Put credit spread" in output


def test_print_regime_checklist_unknown_regime(capsys):
    """Unknown regime falls back to CAUTIOUS display."""
    print_regime_checklist("UNKNOWN", score=0, trend="UNKNOWN",
                           r10=0, bias="unknown")
    output = capsys.readouterr().out
    assert "call spreads only" in output.lower() or "Call credit spread" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_compliance.py::test_print_regime_checklist_bearish -v`
Expected: ImportError — `print_regime_checklist` doesn't exist yet

- [ ] **Step 3: Add print_regime_checklist to compliance.py**

Add this function at the end of `compliance.py`:

```python
def print_regime_checklist(regime, score, trend, r10, bias):
    """Print the regime dashboard and pre-trade checklist.

    Shared by scanner.py and morning.py. Displays regime, health,
    ratio10 bias, sizing, allowed/blocked structures, and notes.
    """
    rules = REGIME_RULES.get(regime, REGIME_RULES["UNKNOWN"])
    sizing = rules["label"]

    print(f"\n  {'='*66}")
    print(f"  REGIME & CHECKLIST")
    print(f"  {'-'*66}")
    print(f"  Regime:      {regime}")
    print(f"  Health:      {score:+d} ({trend})")
    print(f"  Ratio10:     {r10:.2f} ({bias})")
    print(f"  Sizing:      {sizing}")

    allowed = rules["allowed_structures"]
    blocked = [v for k, v in STRUCTURE_NAMES.items() if k not in allowed]
    allowed_names = [STRUCTURE_NAMES[s] for s in allowed if s in STRUCTURE_NAMES]
    max_contracts = int(BASE_CONTRACTS * rules["sizing"])

    print(f"\n  PRE-TRADE CHECKLIST")
    print(f"  {'-'*66}")
    if allowed_names:
        for name in allowed_names:
            print(f"    Allowed:    {name}")
    else:
        print(f"    Allowed:    None (no premium selling)")
    if blocked:
        print(f"    Blocked:    {', '.join(blocked)}")
    print(f"    Max size:   {rules['sizing']}x base -> {max_contracts} contracts")
    print(f"    Note:       {rules['notes']}")
    print()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_compliance.py -v`
Expected: All tests pass including the 3 new ones

- [ ] **Step 5: Replace inline display in scanner.py with shared function**

In `scanner.py`, add `print_regime_checklist` to the import:

```python
from compliance import REGIME_RULES, BASE_CONTRACTS, STRUCTURE_NAMES, print_regime_checklist
```

Replace `scanner.py` lines 211-237 (the breadth dashboard + checklist block) with:

```python
    print_regime_checklist(regime, score, trend, r10, bias)
```

Note: The scanner previously printed the header as "BREADTH DASHBOARD". The shared function uses "REGIME & CHECKLIST". This is fine — the morning plan uses the same header, and the scanner's ticker output above it provides sufficient context.

- [ ] **Step 6: Run all tests to verify no regressions**

Run: `python -m pytest -v`
Expected: All tests pass

Run: `python scanner.py`
Expected: Output looks the same (regime, health, sizing, checklist) with "REGIME & CHECKLIST" header

- [ ] **Step 7: Commit**

```bash
git add compliance.py scanner.py tests/test_compliance.py
git commit -m "refactor: extract print_regime_checklist into compliance module"
```

---

### Task 2: VIX pivot and readiness parsing functions

**Files:**
- Create: `morning.py` (partial — functions only, no main yet)
- Create: `tests/test_morning.py`

- [ ] **Step 1: Write failing tests for VIX pivot and readiness**

Create `tests/test_morning.py`:

```python
import os
import tempfile
from morning import compute_vix_pivot, load_readiness


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_morning.py -v`
Expected: ImportError — `morning` module doesn't exist yet

- [ ] **Step 3: Implement compute_vix_pivot and load_readiness in morning.py**

Create `morning.py`:

```python
# morning.py
"""
Pre-market morning plan for 0DTE ATR credit spread strategy.

Shows readiness, VIX pivot, SPY/QQQ ATR levels, and regime checklist.

Usage:
    python morning.py                     # today's plan
    python morning.py --fetch             # pull latest breadth CSV first
    python morning.py --date 2026-03-19   # historical replay
"""

import argparse
import os

import pandas as pd
import yaml

from data_loaders import download_ohlcv
from indicators import compute_indicators, DAILY_CONFIG
from breadth import load_breadth_data
from compliance import print_regime_checklist

CLEARWATER_DIR = "/Users/fwang/Documents/clearwater/daily"


def compute_vix_pivot(vix_close):
    """Round VIX close to nearest 0.5 for pivot level."""
    return round(vix_close * 2) / 2


def load_readiness(filepath):
    """Parse clearwater daily journal for readiness data.

    Args:
        filepath: Path to a YYYY-MM-DD.md file with YAML frontmatter.

    Returns:
        Dict with biometric keys (sleep_score, recovery, hrv, etc.),
        plus 'status' (OK/WARNING/NO_TRADING) and 'warnings' list.
        Returns None if file doesn't exist.
    """
    if not os.path.exists(filepath):
        return None

    with open(filepath) as f:
        content = f.read()

    # Parse YAML frontmatter between --- markers
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    frontmatter = yaml.safe_load(parts[1])
    if not frontmatter:
        return None

    data = {k: v for k, v in frontmatter.items()}
    warnings = []

    # Sleep rules (take priority)
    sleep = data.get("sleep_score")
    if sleep is not None:
        if sleep < 70:
            warnings.append("NO TRADING — sleep critically low")
        elif sleep < 78:
            warnings.append("Poor sleep — consider sitting out or reducing size")

    # Recovery rule
    recovery = data.get("recovery")
    if recovery is not None and recovery < 33:
        warnings.append("Low recovery — reduce size")

    # Determine status
    if any("NO TRADING" in w for w in warnings):
        data["status"] = "NO_TRADING"
    elif warnings:
        data["status"] = "WARNING"
    else:
        data["status"] = "OK"
    data["warnings"] = warnings

    return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_morning.py -v`
Expected: All 12 tests pass

- [ ] **Step 5: Commit**

```bash
git add morning.py tests/test_morning.py
git commit -m "feat: add VIX pivot and readiness parsing for morning plan"
```

---

### Task 3: Morning plan main command and output

**Files:**
- Modify: `morning.py` (add print functions and main)

- [ ] **Step 1: Add print_morning_plan and main to morning.py**

Add to the end of `morning.py`:

```python
def _get_breadth_for_date(breadth_df, scan_ts):
    """Get breadth data for a given date, matching scanner pattern."""
    mask = breadth_df.index <= scan_ts
    if mask.any():
        brow = breadth_df.loc[mask].iloc[-1]
        return {
            "regime": brow["regime"],
            "score": brow["breadth_score"],
            "trend": brow["breadth_trend"],
            "r10": brow["ratio10"],
            "bias": brow["ratio10_bias"],
        }
    return {
        "regime": "UNKNOWN", "score": 0, "trend": "UNKNOWN",
        "r10": 0, "bias": "unknown",
    }


def _get_levels_for_date(df, target_date=None):
    """Get ATR levels row, optionally filtered to a date."""
    if target_date is not None:
        target = pd.Timestamp(target_date)
        valid = df.index[df.index <= target]
        if len(valid) < 2:
            return None
        return df.loc[valid[-1]]
    return df.iloc[-1]


def print_morning_plan(plan_date, readiness, vix_close, vix_pivot,
                       spy_levels, qqq_levels, breadth):
    """Print the full morning plan output."""
    print(f"\n{'='*70}")
    print(f"  MORNING PLAN — {plan_date}")
    print(f"{'='*70}")

    # Readiness
    print(f"\n  READINESS")
    print(f"  {'-'*66}")
    if readiness is None:
        print(f"    No readiness data for today")
    else:
        parts = []
        if "sleep_score" in readiness:
            parts.append(f"Sleep: {readiness['sleep_score']}")
        if "recovery" in readiness:
            parts.append(f"Recovery: {readiness['recovery']}")
        if "hrv" in readiness:
            parts.append(f"HRV: {readiness['hrv']}")
        if parts:
            print(f"    {' | '.join(parts)}")
        status = readiness["status"]
        if status == "NO_TRADING":
            print(f"    >>> NO TRADING — sleep critically low <<<")
        elif status == "WARNING":
            for w in readiness["warnings"]:
                print(f"    WARNING: {w}")
        else:
            print(f"    Status: OK")

    # VIX Pivot
    print(f"\n  VIX PIVOT")
    print(f"  {'-'*66}")
    if vix_close is not None:
        print(f"    VIX close:  {vix_close:.2f}   Pivot: {vix_pivot:.1f}")
        print(f"    Rule:       Above {vix_pivot:.1f} = bearish | Below {vix_pivot:.1f} = bullish")
    else:
        print(f"    VIX data unavailable")

    # ATR Levels
    for ticker, levels in [("SPY", spy_levels), ("QQQ", qqq_levels)]:
        print(f"\n  {ticker} ATR LEVELS")
        print(f"  {'-'*66}")
        if levels is not None:
            print(f"    +1 ATR:     ${levels['Full_Long']:.2f}     "
                  f"Call trigger: ${levels['Long_Trigger']:.2f}")
            print(f"    Pivot:      ${levels['Central_Pivot']:.2f}     (prev close)")
            print(f"    Put trigger: ${levels['Short_Trigger']:.2f}    "
                  f"-1 ATR: ${levels['Full_Short']:.2f}")
        else:
            print(f"    {ticker} data unavailable")

    # Regime & Checklist
    print_regime_checklist(
        breadth["regime"], breadth["score"], breadth["trend"],
        breadth["r10"], breadth["bias"],
    )


def main():
    parser = argparse.ArgumentParser(description="Pre-market morning plan")
    parser.add_argument("--date", type=str, default=None,
                        help="Plan date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--fetch", action="store_true",
                        help="Pull latest breadth CSV before running.")
    args = parser.parse_args()

    if args.fetch:
        from scanner import fetch_breadth
        print("Fetching breadth data...")
        fetch_breadth()

    plan_date = args.date or pd.Timestamp.now().strftime("%Y-%m-%d")

    # Readiness
    readiness_path = os.path.join(CLEARWATER_DIR, f"{plan_date}.md")
    readiness = load_readiness(readiness_path)

    # VIX
    vix_close = None
    vix_pivot = None
    vix_df = download_ohlcv("^VIX")
    if vix_df is not None:
        vix_row = _get_levels_for_date(vix_df, args.date)
        if vix_row is not None:
            vix_close = float(vix_row["Close"])
            vix_pivot = compute_vix_pivot(vix_close)

    # SPY and QQQ levels
    spy_levels = None
    qqq_levels = None
    for ticker, target in [("SPY", "spy_levels"), ("QQQ", "qqq_levels")]:
        result_df = download_ohlcv(ticker)
        if result_df is not None:
            df = compute_indicators(result_df, DAILY_CONFIG)
            row = _get_levels_for_date(df, args.date)
            if target == "spy_levels":
                spy_levels = row
            else:
                qqq_levels = row

    # Breadth
    breadth_df = load_breadth_data("breadth_data")
    scan_ts = pd.Timestamp(plan_date)
    breadth = _get_breadth_for_date(breadth_df, scan_ts)

    print_morning_plan(plan_date, readiness, vix_close, vix_pivot,
                       spy_levels, qqq_levels, breadth)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add unit tests for Task 3 functions**

Add to `tests/test_morning.py`:

```python
from morning import _get_breadth_for_date, print_morning_plan


def _make_breadth_df():
    """Helper: minimal breadth DataFrame for testing."""
    import pandas as pd
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
```

Run: `python -m pytest tests/test_morning.py -v`
Expected: All 15 tests pass (12 from Task 2 + 3 new)

- [ ] **Step 3: Verify morning plan runs end to end**

Run: `python morning.py`
Expected: Full output with readiness (from today's clearwater file if it exists), VIX pivot, SPY/QQQ ATR levels, and regime checklist.

Run: `python morning.py --date 2026-03-19`
Expected: Same output but with 3/19 data.

- [ ] **Step 3: Run all tests**

Run: `python -m pytest -v`
Expected: All tests pass (existing + new morning tests)

- [ ] **Step 4: Commit**

```bash
git add morning.py
git commit -m "feat: add morning plan command with VIX pivot and readiness filter"
```
