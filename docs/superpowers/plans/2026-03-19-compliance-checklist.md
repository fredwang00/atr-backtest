# Compliance Checklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add regime-based compliance checking so the scanner shows a pre-trade checklist and the journal flags violations at entry time.

**Architecture:** A new `compliance.py` module encodes the decision matrix rules as data. Both `scanner.py` and `journal.py` import from it. The journal stores a `compliance` column for review analytics.

**Tech Stack:** Python, pandas, pytest

**Spec:** `docs/superpowers/specs/2026-03-19-compliance-checklist-design.md`

---

### Task 1: Create `compliance.py` with REGIME_RULES and check_compliance

**Files:**
- Create: `compliance.py`
- Create: `tests/test_compliance.py`

- [ ] **Step 1: Write failing tests for REGIME_RULES data and check_compliance**

```python
# tests/test_compliance.py
from compliance import REGIME_RULES, BASE_CONTRACTS, check_compliance


def test_all_regimes_covered():
    """REGIME_RULES covers all 7 possible regime values."""
    expected = {
        "EXTREME_BULLISH", "BULLISH", "NEUTRAL", "CAUTIOUS",
        "BEARISH", "EXTREME_BEARISH", "UNKNOWN",
    }
    assert set(REGIME_RULES.keys()) == expected


def test_each_regime_has_required_keys():
    """Every regime entry has allowed_structures, sizing, label, notes."""
    for regime, rules in REGIME_RULES.items():
        assert "allowed_structures" in rules, f"{regime} missing allowed_structures"
        assert "sizing" in rules, f"{regime} missing sizing"
        assert "label" in rules, f"{regime} missing label"
        assert "notes" in rules, f"{regime} missing notes"


def test_base_contracts_default():
    assert BASE_CONTRACTS == 10


def test_compliant_call_spread_in_cautious():
    """Call spread with correct sizing in CAUTIOUS → no violations."""
    violations = check_compliance("CAUTIOUS", spread_type="call", contracts=5)
    assert violations == []


def test_put_spread_blocked_in_cautious():
    """Put spread in CAUTIOUS → violation."""
    violations = check_compliance("CAUTIOUS", spread_type="put", contracts=5)
    assert len(violations) == 1
    assert "put" in violations[0].lower() or "structure" in violations[0].lower()


def test_oversized_in_cautious():
    """10 contracts when max is 5 (0.5x of 10) → violation."""
    violations = check_compliance("CAUTIOUS", spread_type="call", contracts=10)
    assert len(violations) == 1
    assert "size" in violations[0].lower() or "contract" in violations[0].lower()


def test_put_spread_and_oversized_in_cautious():
    """Wrong structure AND oversized → two violations."""
    violations = check_compliance("CAUTIOUS", spread_type="put", contracts=10)
    assert len(violations) == 2


def test_any_spread_blocked_in_bearish():
    """No premium selling in BEARISH regime."""
    assert len(check_compliance("BEARISH", spread_type="call", contracts=1)) >= 1
    assert len(check_compliance("BEARISH", spread_type="put", contracts=1)) >= 1


def test_iron_condor_allowed_in_bullish():
    """Both sides allowed in BULLISH, full size."""
    assert check_compliance("BULLISH", spread_type="call", contracts=10) == []
    assert check_compliance("BULLISH", spread_type="put", contracts=10) == []


def test_unknown_regime_uses_cautious_rules():
    """UNKNOWN falls back to CAUTIOUS rules."""
    assert check_compliance("UNKNOWN", spread_type="put", contracts=5) != []
    assert check_compliance("UNKNOWN", spread_type="call", contracts=5) == []


def test_custom_base_contracts():
    """base_contracts override works."""
    # 0.5x of 20 = 10, so 10 contracts is fine
    violations = check_compliance("CAUTIOUS", spread_type="call", contracts=10, base_contracts=20)
    assert violations == []


def test_no_spread_type_skips_structure_check():
    """If spread_type is None, only sizing is checked."""
    violations = check_compliance("CAUTIOUS", spread_type=None, contracts=5)
    assert violations == []


def test_extreme_bearish_any_contracts_oversized():
    """EXTREME_BEARISH has 0.0 sizing — any contracts should flag oversized."""
    violations = check_compliance("EXTREME_BEARISH", spread_type="call", contracts=1)
    assert any("size" in v.lower() or "oversized" in v.lower() for v in violations)


def test_unrecognized_regime_falls_back_to_unknown():
    """Completely unrecognized regime string uses UNKNOWN (CAUTIOUS) rules."""
    violations = check_compliance("FOOBAR", spread_type="put", contracts=5)
    assert len(violations) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_compliance.py -v`
Expected: ImportError — `compliance` module doesn't exist yet

- [ ] **Step 3: Implement compliance.py**

```python
# compliance.py
"""
Decision matrix rules for 0DTE ATR credit spread strategy.

Encodes regime-based trade rules from the decision matrix. Single source
of truth imported by scanner.py (pre-trade checklist) and journal.py
(entry-time compliance checking).
"""

BASE_CONTRACTS = 10

REGIME_RULES = {
    "EXTREME_BULLISH": {
        "allowed_structures": ["call_credit", "put_credit", "iron_condor"],
        "sizing": 0.75,
        "label": "0.75x — pullback risk",
        "notes": "Put spread further OTM or wider. Call side higher conviction.",
    },
    "BULLISH": {
        "allowed_structures": ["call_credit", "put_credit", "iron_condor"],
        "sizing": 1.0,
        "label": "FULL SIZE (1.0x)",
        "notes": "Best environment for premium selling. Target 50-75% of max credit.",
    },
    "NEUTRAL": {
        "allowed_structures": ["call_credit", "put_credit", "iron_condor"],
        "sizing": 0.75,
        "label": "0.75x — no strong edge",
        "notes": "Wider strikes (±1.25 ATR). Prob.OTM > 90% preferred.",
    },
    "CAUTIOUS": {
        "allowed_structures": ["call_credit"],
        "sizing": 0.5,
        "label": "HALF SIZE (0.5x) — call spreads only",
        "notes": "NO put spreads. Skip if no clean level.",
    },
    "BEARISH": {
        "allowed_structures": [],
        "sizing": 0.25,
        "label": "QUARTER SIZE (0.25x) or FLAT",
        "notes": "Cash is a position. Tiny call spread at +1.25 ATR only if trading.",
    },
    "EXTREME_BEARISH": {
        "allowed_structures": [],
        "sizing": 0.0,
        "label": "FLAT — reversal watch only",
        "notes": "Watch for VPA-confirmed reversal. Risk 1-2% on long calls only.",
    },
    "UNKNOWN": {
        "allowed_structures": ["call_credit"],
        "sizing": 0.5,
        "label": "HALF SIZE (0.5x) — call spreads only",
        "notes": "Unknown regime — defaulting to CAUTIOUS rules.",
    },
}

# Maps journal spread_type values to internal structure names
_SPREAD_TYPE_MAP = {
    "call": "call_credit",
    "put": "put_credit",
}


def check_compliance(regime, spread_type=None, contracts=None, base_contracts=BASE_CONTRACTS):
    """Check a trade against regime rules from the decision matrix.

    Args:
        regime: Market regime string (e.g., "CAUTIOUS", "BULLISH").
        spread_type: Journal spread type ("call" or "put"), or None to skip structure check.
        contracts: Number of contracts in the trade, or None to skip sizing check.
        base_contracts: Base contract count (default BASE_CONTRACTS).

    Returns:
        List of violation description strings. Empty list = compliant.
    """
    rules = REGIME_RULES.get(regime, REGIME_RULES["UNKNOWN"])
    violations = []

    # Structure check
    if spread_type is not None:
        mapped = _SPREAD_TYPE_MAP.get(spread_type, spread_type)
        if mapped not in rules["allowed_structures"]:
            allowed = [s.replace("_", " ") for s in rules["allowed_structures"]]
            allowed_str = ", ".join(allowed) if allowed else "none (no premium selling)"
            violations.append(
                f"Wrong structure: {spread_type} credit spread not allowed in "
                f"{regime} regime. Allowed: {allowed_str}."
            )

    # Sizing check
    if contracts is not None:
        max_contracts = int(base_contracts * rules["sizing"])
        if contracts > max_contracts:
            violations.append(
                f"Oversized: {contracts} contracts exceeds {rules['sizing']}x "
                f"sizing (max {max_contracts} of {base_contracts} base)."
            )

    return violations
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_compliance.py -v`
Expected: All 15 tests PASS

- [ ] **Step 5: Commit**

```bash
git add compliance.py tests/test_compliance.py
git commit -m "feat: add compliance module with decision matrix rules"
```

---

### Task 2: Wire compliance into scanner pre-trade checklist

**Files:**
- Modify: `scanner.py:54-63` (replace REGIME_SIZING dict)
- Modify: `scanner.py:155` (sizing assignment)
- Modify: `scanner.py:219-227` (breadth dashboard output)

- [ ] **Step 1: Replace REGIME_SIZING with compliance import in scanner.py**

In `scanner.py`, remove the `REGIME_SIZING` dict (lines 54-63) and replace with:

```python
from compliance import REGIME_RULES, BASE_CONTRACTS
```

Replace line 155:
```python
sizing = REGIME_SIZING.get(regime, "UNKNOWN")
```
with:
```python
rules = REGIME_RULES.get(regime, REGIME_RULES["UNKNOWN"])
sizing = rules["label"]
```

- [ ] **Step 2: Add pre-trade checklist to breadth dashboard output**

After the sizing print line (line 226), add the checklist block:

```python
    # Pre-trade checklist
    all_structures = {"call_credit": "Call credit spread", "put_credit": "Put credit spread",
                      "iron_condor": "Iron condor"}
    allowed = rules["allowed_structures"]
    blocked = [v for k, v in all_structures.items() if k not in allowed]
    allowed_names = [all_structures[s] for s in allowed if s in all_structures]
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
```

- [ ] **Step 3: Verify scanner output looks correct**

Run: `python scanner.py`
Expected: Breadth dashboard shows regime, sizing, and the new PRE-TRADE CHECKLIST section with allowed/blocked structures and sizing guidance.

- [ ] **Step 4: Run all tests to check for regressions**

Run: `pytest -v`
Expected: All tests pass (no scanner tests exist yet, but breadth and journal tests should still pass)

- [ ] **Step 5: Commit**

```bash
git add scanner.py
git commit -m "feat: add pre-trade checklist to scanner breadth dashboard"
```

---

### Task 3: Add compliance column and entry-time checking to journal

**Files:**
- Modify: `journal.py:15-24` (JOURNAL_COLUMNS)
- Modify: `journal.py:233-266` (interactive_log credit spread path)
- Modify: `tests/test_journal.py`

- [ ] **Step 1: Write failing tests for compliance in journal**

Add to `tests/test_journal.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_journal.py::test_compliance_column_in_schema -v`
Expected: FAIL — `compliance` not in JOURNAL_COLUMNS

- [ ] **Step 3: Add compliance column to JOURNAL_COLUMNS**

In `journal.py`, add `"compliance"` to `JOURNAL_COLUMNS` after `"setup_grade"`:

```python
JOURNAL_COLUMNS = [
    "date", "ticker", "direction", "entry_price", "size", "size_mult",
    "trigger_level", "mid_target", "full_target", "stop_level",
    "regime", "breadth_trend", "setup_grade", "compliance",
    "exit_date", "exit_price", "exit_reason",
    "pnl_pct", "pnl_dollars",
    "trade_type", "spread_type", "short_strike", "long_strike",
    "spread_width", "contracts", "credit",
    "notes",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_journal.py -v`
Expected: All tests pass including the two new compliance tests

- [ ] **Step 5: Add compliance checking to interactive_log credit spread path**

In `journal.py`, after the credit spread input is gathered (around line 248, after `setup_grade = _prompt_setup_grade()`) but before `add_entry`, add:

```python
            from compliance import check_compliance
            violations = check_compliance(regime, spread_type=spread_type, contracts=contracts)
            if violations:
                print()
                for v in violations:
                    print(f"  ⚠ REGIME VIOLATION: {v}")
                confirm = input("\n  Log anyway? [y/N]: ").strip().lower()
                if confirm != "y":
                    print("  Trade not logged.")
                    return
                compliance_str = "; ".join(
                    "wrong_structure" if "structure" in v.lower() else "oversized"
                    for v in violations
                )
            else:
                compliance_str = "compliant"
```

Then add `"compliance": compliance_str` to the entry dict.

- [ ] **Step 6: Run all tests**

Run: `pytest -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add journal.py tests/test_journal.py
git commit -m "feat: add compliance column and entry-time violation checking"
```

---

### Task 4: Add compliance breakdown to print_review

**Files:**
- Modify: `journal.py:311-380` (print_review function)
- Modify: `tests/test_journal.py`

- [ ] **Step 1: Write failing test for compliance stats in review**

Add to `tests/test_journal.py`:

```python
def test_review_stats_compliance_breakdown():
    """Review stats include compliance breakdown."""
    test_path = "test_journal_tmp.csv"
    try:
        # Compliant winner
        add_entry({
            "date": "2026-03-18", "ticker": "SPX", "direction": "short",
            "trade_type": "credit_spread", "spread_type": "call",
            "short_strike": 6800, "long_strike": 6820,
            "spread_width": 20.0, "contracts": 5, "credit": 0.30,
            "entry_price": 0.30, "size": 9850.0,
            "regime": "CAUTIOUS", "breadth_trend": "SLIGHTLY_DETERIORATING",
            "compliance": "compliant", "notes": "",
        }, test_path)
        close_trade(0, exit_price=0.0, exit_date="2026-03-18",
                    exit_reason="expired_otm", path=test_path)

        # Violation loser
        add_entry({
            "date": "2026-03-18", "ticker": "SPX", "direction": "short",
            "trade_type": "credit_spread", "spread_type": "put",
            "short_strike": 6625, "long_strike": 6605,
            "spread_width": 20.0, "contracts": 10, "credit": 1.35,
            "entry_price": 1.35, "size": 18650.0,
            "regime": "CAUTIOUS", "breadth_trend": "SLIGHTLY_DETERIORATING",
            "compliance": "wrong_structure; oversized", "notes": "",
        }, test_path)
        close_trade(1, exit_price=5.0, exit_date="2026-03-18",
                    exit_reason="stop", path=test_path)

        stats = compute_review_stats(test_path, trade_type="credit_spread")
        assert "compliance_stats" in stats
        assert stats["compliance_stats"]["compliant"]["total"] == 1
        assert stats["compliance_stats"]["compliant"]["win_rate"] == 100.0
        assert stats["compliance_stats"]["violation"]["total"] == 1
        assert stats["compliance_stats"]["violation"]["win_rate"] == 0.0
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_review_stats_missing_compliance_treated_as_unknown():
    """Trades without compliance column are 'unknown', not compliant or violation."""
    test_path = "test_journal_tmp.csv"
    try:
        add_entry({
            "date": "2026-03-15", "ticker": "SPY", "direction": "long",
            "entry_price": 100.0, "size": 1000,
            "regime": "NEUTRAL", "breadth_trend": "STEADY", "notes": "",
        }, test_path)
        close_trade(0, exit_price=105.0, exit_date="2026-03-18",
                    exit_reason="target_full", path=test_path)

        stats = compute_review_stats(test_path)
        cs = stats.get("compliance_stats", {})
        assert cs.get("compliant", {}).get("total", 0) == 0
        assert cs.get("violation", {}).get("total", 0) == 0
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_journal.py::test_review_stats_compliance_breakdown -v`
Expected: FAIL — `compliance_stats` not in stats dict

- [ ] **Step 3: Add compliance stats to compute_review_stats**

In `journal.py`, inside `compute_review_stats`, after the grade breakdown block (around line 150), add:

```python
    # Compliance breakdown
    compliance_stats = {}
    if "compliance" in closed.columns:
        comp = closed["compliance"].fillna("").replace("", "unknown")
        for label in ["compliant", "violation", "unknown"]:
            if label == "violation":
                grp = closed[~comp.isin(["compliant", "unknown", ""])]
            else:
                grp = closed[comp == label]
            if len(grp) > 0:
                grp_pnls = grp["pnl_pct"].astype(float)
                grp_winners = grp_pnls[grp_pnls > 0]
                compliance_stats[label] = {
                    "total": len(grp),
                    "win_rate": len(grp_winners) / len(grp) * 100 if len(grp) > 0 else 0,
                    "avg_pnl": grp_pnls.mean(),
                }
    result["compliance_stats"] = compliance_stats
```

- [ ] **Step 4: Add compliance section to print_review output**

In `print_review`, after the grade stats block (around line 367), add:

```python
        # Compliance breakdown
        compliance_stats = all_stats.get("compliance_stats", {})
        compliant = compliance_stats.get("compliant", {})
        violation = compliance_stats.get("violation", {})
        if compliant or violation:
            total_scored = compliant.get("total", 0) + violation.get("total", 0)
            print(f"\n  Compliance:")
            if compliant:
                print(f"    Compliant:   {compliant['total']} trades, "
                      f"{compliant['win_rate']:.0f}% WR, "
                      f"{compliant['avg_pnl']:+.2f}% avg")
            if violation:
                print(f"    Violations:  {violation['total']} trades, "
                      f"{violation['win_rate']:.0f}% WR, "
                      f"{violation['avg_pnl']:+.2f}% avg")
            if total_scored > 0:
                rate = compliant.get("total", 0) / total_scored * 100
                print(f"    Compliance rate: {rate:.0f}%")
```

- [ ] **Step 5: Run all tests**

Run: `pytest -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add journal.py tests/test_journal.py
git commit -m "feat: add compliance breakdown to journal review stats"
```
