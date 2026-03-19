# Compliance Checklist & Pre-Trade Guard Rails

**Date:** 2026-03-19
**Status:** Approved

## Problem

The scanner's sizing logic was decoupled from the regime — a BEARISH regime could show FULL SIZE. The journal logs trades without checking whether they conform to the decision matrix rules. There's no systematic feedback loop between regime rules and trade execution.

## Design

### `compliance.py` — Decision Matrix Rules Module

A single source of truth for regime-based trade rules, imported by both `scanner.py` and `journal.py`.

**Data structure:** `REGIME_RULES` dict mapping each regime to:
- `allowed_structures`: list of allowed trade types (`"call_credit"`, `"put_credit"`, `"iron_condor"`)
- `sizing`: multiplier (1.0, 0.75, 0.5, 0.25, 0.0)
- `label`: human-readable sizing string for display
- `notes`: regime-specific guidance from the decision matrix

**Constants:**
- `BASE_CONTRACTS = 10` — default base position size

**Function:** `check_compliance(regime, spread_type=None, contracts=None, base_contracts=None)`
- Returns a list of violation strings. Empty list = compliant.
- Checks:
  1. Whether `spread_type` is in the regime's allowed structures
  2. Whether `contracts` exceeds `base_contracts * sizing` multiplier
  3. Iron condor detection is deferred — requires checking open trades for same-day opposing spreads, which is a journal-level concern

### Scanner Pre-Trade Checklist

Appended to the breadth dashboard output after the sizing line. Prints:
- Allowed trade structures for the current regime
- Blocked structures
- Concrete sizing guidance (e.g., "0.5x base → 5 contracts if base is 10")
- Regime-specific notes from the decision matrix

The existing `REGIME_SIZING` dict in `scanner.py` is replaced by importing `REGIME_RULES[regime]["label"]` from `compliance.py`.

### Journal Compliance at Entry Time

When logging a credit spread via `journal.py log`:
1. After the user enters trade details, call `check_compliance()` with current regime and trade info
2. If violations found: print warnings, prompt "Log anyway? [y/N]"
3. If user confirms: log trade with `compliance` field set to violation descriptions (e.g., `"wrong_structure; oversized"`)
4. If user declines: abort without logging
5. If no violations: log with `compliance` field set to `"compliant"`

A new `compliance` column is added to `JOURNAL_COLUMNS`.

### Review Stats Compliance Breakdown

In `print_review`, after the grade breakdown, add a compliance section splitting closed trades by compliant vs violation — showing trade count, win rate, and avg P&L for each group, plus overall compliance rate.

## Files Changed

- **New:** `compliance.py` — regime rules and compliance checking
- **New:** `tests/test_compliance.py` — unit tests for compliance logic
- **Modified:** `scanner.py` — replace `REGIME_SIZING` with compliance import, add checklist output
- **Modified:** `journal.py` — add compliance column, entry-time checking, review stats breakdown
- **Modified:** `tests/test_journal.py` — update for new compliance column
