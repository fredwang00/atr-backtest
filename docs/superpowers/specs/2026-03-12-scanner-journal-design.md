# Scanner & Journal Design

Daily scanner that surfaces ATR swing trade setups after market close, plus a trade journal for logging and reviewing pilot trades.

## Background

The backtest shows 86.8% win rate and Sharpe 3.31 across 242 trades (2018-2026). Breadth-health sizing cuts max drawdown in half (-6.2% vs -10.9%). The user wants to pilot 10-20 real trades with small size, reviewing setups after close each day. Average frequency is ~2-3 trades per month across 10 tickers.

## New Files

### `scanner.py` (~200 lines)

Checks all 10 tickers for entry conditions after market close. Reuses `prepare_data()` from `atr_swing_backtest.py` (returns `(df, emas)` tuple — only `df` is needed) and `load_breadth_data()` from `breadth.py`.

**Usage:**
```
python scanner.py              # today's scan
python scanner.py --date 2024-03-15  # historical replay
```

**For each ticker**, evaluates the most recent bar against entry conditions per direction. The 6 long conditions are:

1. `squeeze` — Recent squeeze fire (within SQUEEZE_LOOKBACK bars)
2. `momentum_long` — Momentum > 0
3. `ema_bull` — EMA stack bullish (8 > 9 > 21 > 34 > 50)
4. `long_crossover` — Price crossed trigger (prev close <= prev trigger AND today close > today trigger)
5. `volume` — Volume above 20-period SMA
6. `above_macro` — Close > 200 EMA

The 6 short conditions mirror these: `squeeze`, `momentum_short`, `ema_bear`, `short_crossover`, `volume`, `below_macro`.

Each direction is evaluated independently. A ticker's bucket is determined by its best direction:

**TRIGGERED** — All 6 conditions met for long or short (or both, though unlikely). This is a signal the backtest would have taken. Output includes: direction (long/short), entry price (trigger level), mid target (61.8%), full target (100% ATR), stop level (central pivot), ATR at entry.

**NEAR** — 4-5 of 6 conditions met for at least one direction. Shows which conditions passed and which failed for the best direction, plus distance to trigger level (e.g., "$0.43 below long trigger"). Useful for watchlist — these may trigger tomorrow.

**QUIET** — Fewer than 4 conditions met in either direction. Shows today's ATR levels for reference only.

**Breadth dashboard** (printed once, below the ticker scan):
- Current regime (from `breadth.py`)
- Breadth health score and trend label
- Ratio10 value and bias
- Position sizing recommendation based on breadth trend:
  - FULL SIZE: IMPROVING, SLIGHTLY_IMPROVING, STEADY, SLIGHTLY_DETERIORATING
  - HALF SIZE: DETERIORATING, DETERIORATING_FAST

**Earnings proximity**: For each ticker, reads the earnings cache file (`breadth_data/earnings_cache/{ticker}_earnings.csv`) to find the next earnings date after the scan date. Shows days until that date. Flags tickers within the blackout window (2 days before through 1 day after). If no cache file exists, shows "unknown" and suggests running `get_earnings_blackout()` to populate the cache.

**Date handling**: Defaults to the last row in the ticker's DataFrame (the most recent trading day in the downloaded data). The `--date` flag selects the latest trading day on or before the requested date. Errors if the requested date is before the data starts. For weekends/holidays, silently falls back to the prior trading day.

The condition checks reuse the same logic as `run_backtest()` in `atr_swing_backtest.py` but extracted into a helper that returns per-condition pass/fail instead of a binary trade/no-trade. This avoids duplicating the entry logic.

### `journal.py` (~150 lines)

Two modes for managing the trade journal.

**`python journal.py log`** — Interactive prompt to log a trade entry or exit.

First prompt asks: `(1) New entry` or `(2) Close existing trade`. If (2) is selected but no open trades exist, prints a message and falls back to (1).

For new entries, prompts for: ticker, direction, entry price, size, notes. Calls `prepare_data(ticker)` for the specified ticker (one yfinance download, ~2 seconds) to pre-fill levels. Automatically captures: date, trigger level, mid/full targets, stop, regime, breadth trend, size_mult recommendation. Appends a row to `trades_journal.csv`.

For closing trades, lists all open trades (entries without exits) numbered for selection. After the user picks one, prompts for: exit price, exit reason (target_full / stop / time / discretionary), notes. Computes pnl_pct as `(exit_price - entry_price) / entry_price` for longs (mirror for shorts). This is a simplification vs the backtest's two-leg model (half at mid, half at full) — real pilot trades use a single exit to keep journaling simple. The user can note partial exits in the notes field. Updates the existing row in-place.

**`python journal.py review`** — Reads `trades_journal.csv` and prints:
- Trade count, win rate, avg P&L, profit factor
- Comparison line: "Backtest expects: 86.8% WR, +1.10% avg" vs your actuals (equal-weighted — `size_mult` is informational, not applied to journal stats)
- Sample size warning when < 20 trades ("too few trades to draw conclusions")
- Regime distribution of your trades vs the backtest's regime distribution
- List of open trades (entries without exits)

### `trades_journal.csv`

The journal file, stored in repo root. Columns:

```
date,ticker,direction,entry_price,size,size_mult,trigger_level,mid_target,full_target,stop_level,regime,breadth_trend,exit_date,exit_price,exit_reason,pnl_pct,notes
```

Created with headers on first `journal.py log` invocation. Blank exit fields until trade is closed. `pnl_pct` computed automatically when exit is logged.

## Changes to Existing Code

### `atr_swing_backtest.py` — 1 change

Extract a `check_entry_conditions(df, i)` helper that returns a dict of per-condition results instead of a boolean. The existing `run_backtest()` calls this helper internally (no behavior change). The scanner imports and uses the same helper.

```python
def check_entry_conditions(df, i):
    """Check all entry conditions for bar i. Returns dict with per-condition results."""
    row = df.iloc[i]
    prev = df.iloc[i - 1]

    return {
        "squeeze": bool(row["Recent_Squeeze_Fire"]),
        "momentum_long": row["Momentum"] > 0,
        "momentum_short": row["Momentum"] < 0,
        "ema_bull": bool(row["EMA_Bull_Stack"]),
        "ema_bear": bool(row["EMA_Bear_Stack"]),
        "long_crossover": row["Close"] > row["Long_Trigger"] and prev["Close"] <= prev["Long_Trigger"],
        "short_crossover": row["Close"] < row["Short_Trigger"] and prev["Close"] >= prev["Short_Trigger"],
        "volume": bool(row["Vol_Above_Avg"]),
        "above_macro": row["Close"] > row["EMA_200"],
        "below_macro": row["Close"] < row["EMA_200"],
        "long_trigger": row["Long_Trigger"],
        "short_trigger": row["Short_Trigger"],
        "mid_long": row["Mid_Long"],
        "mid_short": row["Mid_Short"],
        "full_long": row["Full_Long"],
        "full_short": row["Full_Short"],
        "central_pivot": row["Central_Pivot"],
        "atr": row["Prev_ATR"],
        "close": row["Close"],
    }
```

The 6 long conditions are: `squeeze`, `momentum_long`, `ema_bull`, `long_crossover`, `volume`, `above_macro`.
The 6 short conditions are: `squeeze`, `momentum_short`, `ema_bear`, `short_crossover`, `volume`, `below_macro`.

The price-level keys (`long_trigger`, `mid_long`, etc.) are used by the scanner and journal for display; `run_backtest()` continues reading those values from `df` directly.

`run_backtest()` is refactored to use `check_entry_conditions()` for the boolean conditions only. Standalone behavior unchanged — verified by running the backtest and confirming 242 trades, 86.8% WR.

## What This Does NOT Include

- Automated order placement or broker integration
- Real-time / intraday scanning
- Notifications (cron, email, Slack)
- Options / credit spread scanner (future iteration)
- Two-leg exit tracking in journal (simplification: single exit per trade)
