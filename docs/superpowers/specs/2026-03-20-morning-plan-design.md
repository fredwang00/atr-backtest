# Morning Plan Mode + VIX Pivot

**Date:** 2026-03-20
**Status:** Approved

## Problem

The scanner runs after market close for swing setups. The 0DTE credit spread workflow is a pre-market morning routine: check readiness, identify today's ATR levels as support/resistance, determine VIX directional bias, review regime and allowed structures. Currently this requires looking at TOS charts for levels and running the scanner separately for regime.

## Design

### `morning.py` — Pre-Market Planning Command

A standalone script that mirrors Saty's 5-minute morning routine.

**Usage:**
```
python morning.py                     # today's plan
python morning.py --date 2026-03-19   # historical replay
```

**Output sections (in order):**

1. **Readiness** — biometrics from clearwater daily journal
2. **VIX Pivot** — directional bias signal
3. **SPY ATR Levels** — today's support/resistance levels
4. **QQQ ATR Levels** — same for QQQ
5. **Regime & Checklist** — breadth regime, sizing, allowed/blocked structures

### Readiness Filter

Reads `/Users/fwang/Documents/clearwater/daily/YYYY-MM-DD.md`, parses YAML frontmatter for `sleep_score` and `recovery`.

**Path constant:** `CLEARWATER_DIR = "/Users/fwang/Documents/clearwater/daily"`

**Rules (sleep takes priority):**
- `sleep_score < 70` → `NO TRADING — sleep critically low`
- `sleep_score` 70-77 → `WARNING: poor sleep — consider sitting out or reducing size`
- `recovery < 33` → `WARNING: low recovery — reduce size`
- Otherwise → `OK`

If today's file doesn't exist, prints `No readiness data for today` with no warning or block.

### VIX Pivot

```python
def compute_vix_pivot(vix_close):
    """Round VIX close to nearest 0.5 for pivot level."""
    return round(vix_close * 2) / 2
```

Downloads `^VIX` via `download_ohlcv`, takes yesterday's close, rounds to nearest 0.5. The output shows both the raw close and the pivot so the user can compare to live pre-market VIX on their chart.

**Bias:** VIX above pivot = bearish for SPY. VIX below pivot = bullish.

### ATR Levels Display

Uses existing `download_ohlcv` + `compute_indicators` with `DAILY_CONFIG` for SPY and QQQ. The last row gives today's levels (computed from yesterday's close + ATR):

- `Full_Long` (+1 ATR)
- `Long_Trigger` (call trigger, 0.236)
- `Central_Pivot` (prev close)
- `Short_Trigger` (put trigger, -0.236)
- `Full_Short` (-1 ATR)

No new computation — just formatting existing indicator output.

### Regime & Checklist

Reuses `load_breadth_data` from `breadth.py` and `REGIME_RULES`/`STRUCTURE_NAMES`/`BASE_CONTRACTS` from `compliance.py`. Same display logic as the scanner's breadth dashboard and pre-trade checklist.

## Files Changed

- **New:** `morning.py` — pre-market planning command
- **New:** `tests/test_morning.py` — unit tests for VIX pivot and readiness parsing
