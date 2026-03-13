# Scanner & Journal Design

Daily scanner that surfaces ATR swing trade setups after market close, plus a trade journal for logging and reviewing pilot trades.

## Background

The backtest shows 86.8% win rate and Sharpe 3.31 across 242 trades (2018-2026). Breadth-health sizing cuts max drawdown in half (-6.2% vs -10.9%). The user wants to pilot 10-20 real trades with small size, reviewing setups after close each day. Average frequency is ~2-3 trades per month across 10 tickers.

## New Files

### `scanner.py` (~200 lines)

Checks all 10 tickers for entry conditions after market close. Reuses `prepare_data()` from `atr_swing_backtest.py` and `load_breadth_data()` from `breadth.py`.

**Usage:**
```
python scanner.py              # today's scan
python scanner.py --date 2024-03-15  # historical replay
```

**For each ticker**, evaluates the most recent bar against all 6 entry conditions:

1. Recent squeeze fire (within SQUEEZE_LOOKBACK bars)
2. Momentum direction (positive for long, negative for short)
3. EMA stack aligned (bullish or bearish)
4. Price crossed trigger level (crossover: prev close <= prev trigger, today close > today trigger)
5. Volume above 20-period SMA
6. Price above/below 200 EMA

Classifies each ticker into one of three buckets:

**TRIGGERED** — All 6 conditions met. This is a signal the backtest would have taken. Output includes: direction (long/short), entry price (trigger level), mid target (61.8%), full target (100% ATR), stop level (central pivot), ATR at entry.

**NEAR** — 4-5 of 6 conditions met. Shows which conditions passed and which failed, plus distance to trigger level (e.g., "$0.43 below long trigger"). Useful for watchlist — these may trigger tomorrow.

**QUIET** — Fewer than 4 conditions met. Shows tomorrow's ATR levels (prev close +/- ATR * fib percentages) for reference only.

**Breadth dashboard** (printed once, below the ticker scan):
- Current regime (from `breadth.py`)
- Breadth health score and trend label
- Ratio10 value and bias
- Position sizing recommendation: "FULL SIZE" when breadth trend is STEADY or better, "HALF SIZE" when DETERIORATING or DETERIORATING_FAST

**Earnings proximity**: For each ticker, shows days until next earnings date (from `earnings.py` cache). Flags tickers within the blackout window (2 days before through 1 day after).

**Date handling**: Defaults to the most recent trading day in the downloaded data. The `--date` flag allows replaying historical dates for testing the scanner against known backtest signals.

The condition checks reuse the same logic as `run_backtest()` in `atr_swing_backtest.py` but extracted into a helper that returns per-condition pass/fail instead of a binary trade/no-trade. This avoids duplicating the entry logic.

### `journal.py` (~150 lines)

Two modes for managing the trade journal.

**`python journal.py log`** — Interactive prompt to log a trade entry or exit.

For entries, prompts for: ticker, direction, entry price, size, notes. Pre-fills from today's scanner output where possible (reads the ticker's current levels from `prepare_data()`). Automatically captures: date, trigger level, mid/full targets, stop, regime, breadth trend, size_mult recommendation. Appends a row to `trades_journal.csv`.

For exits (when a trade already has an entry but no exit), prompts for: exit price, exit reason (target_mid / target_full / stop / time / discretionary), notes. Computes pnl_pct and updates the existing row.

**`python journal.py review`** — Reads `trades_journal.csv` and prints:
- Trade count, win rate, avg P&L, profit factor
- Comparison line: "Backtest expects: 86.8% WR, +1.10% avg" vs your actuals
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
        "above_macro": row["Close"] > row[f"EMA_200"],
        "below_macro": row["Close"] < row[f"EMA_200"],
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

Long triggers when: squeeze + momentum_long + ema_bull + long_crossover + volume + above_macro.
Short triggers when: squeeze + momentum_short + ema_bear + short_crossover + volume + below_macro.

`run_backtest()` is refactored to use `check_entry_conditions()` internally. Standalone behavior unchanged — verified by running the backtest and confirming 242 trades, 86.8% WR.

## What This Does NOT Include

- Automated order placement or broker integration
- Real-time / intraday scanning
- Notifications (cron, email, Slack)
- Options / credit spread scanner (future iteration)
