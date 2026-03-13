# Breadth Integration Design

Integrate Pradeep Bonde's Stockbee Market Monitor breadth data into the ATR Levels swing backtest as a regime filter, alongside an earnings blackout filter. Goal: quantify whether market breadth improves the strategy's edge and Sharpe ratio.

## Background

The ATR swing strategy currently runs "macro-blind" — it doesn't know whether the broad market is healthy or deteriorating. Results show 86.8% win rate and Sharpe 3.31 across 242 trades (2018-2026), but tail risk from macro shocks (April 2025 tariffs: -$3,538 in one day) and earnings gaps (~$2,188 in losses) drags performance. Pradeep's breadth indicators classify the market into regimes (EXTREME_BEARISH through EXTREME_BULLISH) and compute a composite breadth health score — both are available as daily signals from a Google Sheet spanning 2018-2026.

## Data

8 years of daily breadth data from Pradeep's Google Sheet, already downloaded to `breadth_data/mm_{year}.csv`. Each row has 15 fields: up4, down4, ratio5, ratio10, quarterUp25, quarterDown25, monthUp25, monthDown25, monthUp50, monthDown50, up13_34, down13_34, t2108, universe, S&P 500. ~2,145 trading days total.

## New Files

### `breadth.py` (~250 lines)

Parses the breadth CSVs and computes two signal layers.

**Parsing:** Reads all year CSVs from `breadth_data/`, extracts numeric columns by ordinal position (matching the market-monitor app's parser), handles trailing empty columns and whitespace in headers, combines into a single DataFrame indexed by date in chronological order.

**Regime classification** — exact port of `getRegime()` from `market-monitor/app/src/App.tsx`. Priority-ordered, first match wins:

1. EXTREME_BEARISH: quarterUp25 < 300 OR t2108 < 20
2. BEARISH: ratio10 < 0.5 OR ratio5 < 0.4
3. BEARISH: quarterDown25 > quarterUp25 AND ratio10 < 1.2
4. BEARISH: 3+ of last 5 days with down4 > 350 (recentBigDown >= 3)
5. CAUTIOUS: quarterDown25 > quarterUp25 * 0.85 AND ratio10 < 1.5
6. CAUTIOUS: 3+ of last 5 days where down4 > up4 (net-negative) AND ratio10 < 1.3
7. EXTREME_BULLISH: (t2108 > 85 AND ratio10 > 2.5) OR (ratio10 > 3 AND ratio5 > 3)
8. BULLISH: (ratio10 > 2 AND quarterUp25 > quarterDown25 * 1.3) OR (ratio10 > 1.5 AND quarterUp25 > 1000 AND quarterUp25 > quarterDown25 * 1.1)
9. NEUTRAL: default

Rules 4 and 6 require a 5-day lookback (indices `idx-4` through `idx` inclusive). The two counters (`recentBigDown` and `recentNetNeg`) are computed in a single pass before rules 4-6 are evaluated. Only computed when `idx >= 4`.

**Breadth health score** — exact port of `computeBreadthHealth()`. 11 distinct checks producing up to 16 possible signal contributions via bull/bear sub-branches, using `detectTrend()` helper (5-day lookback, threshold at 70% directional consistency = 4+ of 5 days). Requires `idx >= 10`. Score ranges roughly -15 to +8.

Scoring signals (exact weights):

| Check | Condition | Score |
|-------|-----------|-------|
| ratio10 trending up | detectTrend(ratio10, 5) == 1 | +2 |
| ratio10 trending down | detectTrend(ratio10, 5) == -1 | -2 |
| t2108 rising | detectTrend(t2108, 5) == 1 | +1 |
| t2108 falling | detectTrend(t2108, 5) == -1 | -1 |
| quarterUp25 expanding | detectTrend(quarterUp25, 5) == 1 | +1 |
| quarterUp25 declining | detectTrend(quarterUp25, 5) == -1 | -2 |
| Quarterly spread healthy | quarterUp25 - quarterDown25 > 300 | +1 |
| Quarterly spread inverted | quarterUp25 - quarterDown25 < 0 | -2 |
| 3+ of 5 days with down4 > 300 | bigDownCount >= 3 | -3 |
| 2 of 5 days with down4 > 300 | bigDownCount == 2 | -1 |
| 4+ of 5 days with up4 > 300 | bigUpCount >= 4 | +2 |
| 4+ of 5 red days | down4 > up4 on 4+ days | -2 |
| 4+ of 5 green days | down4 > up4 on <= 1 day | +1 |
| Monthly divergence | monthDown25 > monthUp25 * 1.5 AND monthDown25 > 100 | -1 |
| Froth | monthUp50 > 30 | -1 |
| Down 13/34 expanding | detectTrend(down13_34, 5) == 1 | -1 |

Note: the breadth health `down4 > 300` threshold differs from the regime classification's `down4 > 350`. This is intentional — health scoring is more sensitive.

Score-to-trend mapping:

| Score | Label |
|-------|-------|
| >= 4 | IMPROVING |
| 2 to 3 | SLIGHTLY_IMPROVING |
| -1 to 1 | STEADY |
| -3 to -2 | SLIGHTLY_DETERIORATING |
| -5 to -4 | DETERIORATING |
| < -5 | DETERIORATING_FAST |

Labels use underscores (not spaces) for programmatic use.

**Simple ratio10 bias** — for comparison testing:
- ratio10 > 1.5 -> "long"
- ratio10 < 0.8 -> "short"
- otherwise -> "neutral"

**Public API:**
```python
load_breadth_data(data_dir="breadth_data") -> pd.DataFrame
```
Returns DataFrame indexed by date (chronological), with columns for all raw fields, regime, breadth_score, breadth_trend, ratio10_bias.

### `earnings.py` (~80 lines)

Fetches historical earnings dates from yfinance and provides a blackout filter.

**Logic:** For each ticker, pull earnings dates via `yf.Ticker(symbol).get_earnings_dates()`. Mark a configurable window around each date as blacked out. Default: 2 trading days before the earnings date, plus the earnings date itself, plus 1 day after (the gap day). If earnings report after close on day T, the gap happens on T+1 — "1 after" means T+1 is blacked out.

**Caching:** Saves to `breadth_data/earnings_cache/{ticker}_earnings.csv` so subsequent runs don't hit the API.

**Public API:**
```python
get_earnings_blackout(ticker, start_date, end_date, before=2, after=1) -> Set[pd.Timestamp]
```

### `compare.py` (~200 lines)

Runs the backtest under 6 filter configurations and produces a comparison table.

**Configurations:**

| Label | Regime Filter | Earnings Filter | Description |
|-------|--------------|-----------------|-------------|
| Baseline | None | No | Current strategy unchanged |
| +Earnings | None | Yes | Skip trades near earnings |
| +Regime | Full Pradeep | No | Longs in NEUTRAL/BULLISH/EXTREME_BULLISH only; shorts in NEUTRAL/BEARISH/EXTREME_BEARISH only |
| +Regime+Earnings | Full Pradeep | Yes | Both filters |
| +Ratio10 | ratio10 bias | No | Longs when ratio10 > 1.5; shorts when ratio10 < 0.8 |
| +Ratio10+Earnings | ratio10 bias | Yes | Both filters |

CAUTIOUS regime blocks both longs and shorts — this is intentional. CAUTIOUS means early deterioration; sitting out avoids whipsaw during transitions.

An additional variant tests breadth-health-based sizing: full position when breadth trend is STEADY or better, half position when DETERIORATING or worse.

**Execution:** For each ticker, calls `prepare_data(ticker)` once (breadth data loaded once, shared across tickers). Then runs `run_backtest()` 6+ times per ticker with different filter functions. Each config produces the same summary stats (win rate, avg P&L, Sharpe, profit factor, max DD, trade count). Handles tickers that produce zero trades under strict filters gracefully (skip, don't divide by zero).

**Output:**
- Comparison table to stdout
- `atr_swing_results/comparison.csv`
- Per-config trade logs with a `regime_at_entry` column (the breadth regime on the entry date, included even for the baseline config — useful for post-hoc analysis)

## Changes to Existing Code

### `atr_swing_backtest.py` — 3 minimal changes

1. **`run_backtest(df, entry_filter=None)`** — add optional entry_filter parameter. When provided, called after all existing conditions pass: `entry_filter(df, i, direction) -> bool`. If False, skip the trade. When None, behavior unchanged. The filter is a closure that captures the breadth DataFrame and earnings blackout set. Inside the filter, `df.index[i]` is used to look up the corresponding breadth row by date.

2. **`Trade` dataclass gains `size_mult: float = 1.0`** — for breadth-health-based sizing. Applied in `simulate_trade()` at P&L computation: `trade.pnl_pct *= trade.size_mult`. Default 1.0 preserves existing behavior.

3. **`prepare_data()` works when imported** — no changes needed, already returns (df, emas) tuple.

The standalone `python atr_swing_backtest.py` continues to work exactly as before.

## Date Alignment

Breadth data covers market-wide trading days. Individual ticker DataFrames from yfinance may differ slightly (halts, IPO dates). Strategy: left-join on the ticker's dates, forward-fill breadth data for any missing days (use the most recent available breadth reading). Days before the breadth data begins (pre-2018 warmup rows) get regime=NEUTRAL as a safe default. This alignment happens inside the entry_filter closure, not in the main backtest.

## What This Does NOT Include (Future Iterations)

- **Parameter sweep** — vary stop mode (pivot/trigger/ema9), hold days, trigger %, squeeze lookback across a matrix. Deferred to avoid overfitting; do after breadth integration proves (or disproves) the regime filter adds edge.
- **Walk-forward validation** — split into in-sample (2018-2022) / out-of-sample (2023-2026) to test for overfitting. Year-by-year stability (80-86% WR) gives moderate confidence already, but this is the rigorous check.
- **0DTE/1DTE credit spreads with realistic bid/ask** — filtered 1DTE bull puts showed 84-86% WR and Sharpe 1.7-2.2 in current backtest. Worth modeling with real spread pricing and slippage if the breadth filter also improves the credit spread results.
- Changes to the market-monitor app itself
- Intraday data or real options pricing
