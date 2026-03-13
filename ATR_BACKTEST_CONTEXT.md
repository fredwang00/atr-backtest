# ATR Levels Backtest — Project Context

## What we're doing
Backtesting Saty Mahajan's ATR Levels swing trading strategy to determine if there's a quantifiable edge. The strategy uses ATR (Average True Range) from the prior period's close to plot trading levels, combined with TTM Squeeze, EMA stack confirmation, and volume.

## The strategy (mechanical rules)
**Entry conditions (all must be true for a long — mirror for short):**
1. TTM Squeeze has recently fired (within last 10 bars)
2. Squeeze momentum is positive (bullish)
3. EMAs are stacked bullish: 8 > 9 > 21 > 34 > 50
4. Price closes above the 23.6% ATR trigger level (first crossover)
5. Volume on trigger candle is above 20-period SMA
6. Price is above 200 EMA (macro trend filter)

**Exit rules:**
- Half position off at 61.8% mid-range level
- Remaining half targets full ±1 ATR
- Stop loss: configurable (previous close / trigger level / trailing 9 EMA)
- Time stop: 15 days max hold

**ATR Levels (from previous close ± ATR):**
- Full range: ±100% of ATR
- Mid-range: ±61.8% of ATR (fib level)
- Trigger: ±23.6% of ATR (fib level)
- Central pivot: previous close

## Key files

**Core modules:**
- `indicators.py` — IndicatorConfig dataclass + all indicator computation (ATR levels, EMAs, squeeze, momentum, volume). `compute_indicators(df, config)` is the main entry point. DAILY_CONFIG and INTRADAY_CONFIG presets.
- `data_loaders.py` — Data download functions. Currently `download_ohlcv(ticker)` via yfinance. Designed to be swappable (future: Polygon.io, ThinkorSwim CSV).
- `atr_swing_backtest.py` — Main backtest: `prepare_data(ticker)` → `(df, {})` tuple (dict reserved for future metadata), `check_entry_conditions(df, i)`, `run_backtest(df)`. Imports indicators and data_loaders.

**Analysis & tools:**
- `breadth.py` — Pradeep's market monitor breadth parser + regime classifier
- `earnings.py` — Earnings blackout filter (yfinance-based, cached)
- `compare.py` — Runs 7 filter configurations side-by-side
- `credit_spread_analysis.py` — 0DTE/1DTE credit spread edge analysis at ±1.0/1.25 ATR with regime filtering
- `scanner.py` — Daily setup scanner (run after close)
- `journal.py` — Trade journal logging and review

**Data & outputs:**
- `breadth_data/` — Raw breadth CSVs from Google Sheets (2018-2026)
- `trades_journal.csv` — Pilot trade log (created on first use)
- `atr_swing_results/` — Charts (PNG), trade logs (CSV), summary stats (CSV)
- Uses yfinance for data, tests SPY/QQQ/AAPL/NVDA/TSLA/META/AMZN/GOOGL/MSFT/AMD

## Bugs already fixed (do not reintroduce)
1. Crossover detection compares each day against its OWN trigger level (prev close vs prev trigger, today close vs today trigger)
2. Stop/target ambiguity on daily bars resolved with gap detection (open vs stop)
3. EMA9 stop mode is now dynamic (re-evaluated each bar)
4. ATR shifted by 1 day to avoid look-ahead bias (uses Prev_ATR)
5. Momentum oscillator uses Donchian+SMA midline (closer to TTM Squeeze Pro)
6. SQUEEZE_LOOKBACK is a top-level config constant
7. EMA stack computation is vectorized (not iloc loop)
8. Entry scanning and simulation merged into single forward pass (no overlapping trades)
9. Entry at trigger level (limit order fill), not at close — prevents entry overshoot on volatile days
10. Credit spread P&L uses expiration-based model (settlement close), not intraday touch model
11. Removed vestigial `emas` parameter from `run_backtest()`
12. `END_DATE` was hardcoded to a specific date — changed to `None` so yfinance defaults to today
13. Removed unused `max_loss` variables in credit spread P&L blocks
14. `prepare_data` returns `(df, {})` tuple — the empty dict is a placeholder for future metadata (e.g., data source info). Callers unpack as `df, _ = prepare_data(ticker)`.

## Current results (as of 2026-03-12)
- Baseline: 242 trades, 86.8% WR, profit factor 4.18, Sharpe 3.31, max DD -10.9%
- Breadth comparison (7 configs via compare.py):
  - Baseline:             242 trades, WR 86.8%, Sharpe 3.31, PF 4.18, MaxDD -10.9%
  - +Earnings:            217 trades, WR 86.2%, Sharpe 3.08, PF 4.15, MaxDD -10.9%
  - +Regime:              154 trades, WR 84.4%, Sharpe 2.33, PF 3.61, MaxDD -11.0%
  - +Regime+Earnings:     141 trades, WR 83.7%, Sharpe 2.15, PF 3.47, MaxDD -11.0%
  - +Ratio10:             225 trades, WR 86.2%, Sharpe 3.17, PF 4.22, MaxDD -10.9%
  - +Ratio10+Earnings:    202 trades, WR 85.6%, Sharpe 2.99, PF 4.27, MaxDD -10.9%
  - +Regime+Earn+Sizing:  141 trades, WR 83.7%, Sharpe 3.00, PF 4.59, MaxDD -6.2%

## What to do next
1. Parameter sensitivity: vary STOP_LOSS_MODE, TRIGGER_PCT, MAX_HOLD_DAYS, SQUEEZE_LOOKBACK
2. Walk-forward validation: in-sample (2018-2022) / out-of-sample (2023-2026)
3. 0DTE/1DTE credit spreads with realistic bid/ask pricing
4. Intraday data source integration (Polygon.io REST API, ThinkorSwim CSV export)

## Broader context
- User is learning this strategy alongside VPA (Volume Price Analysis) and market structure
- Has a separate project ("Pradeep's market monitor app") for tracking market conditions
- End goal: determine whether ATR Levels provide real edge or are just a nice visual framework
- Credit spread angle: selling at ±1 ATR levels, ~80% theoretical win rate, but tail risk matters
- The discretionary elements (VPA, "feel") can't be backtested — this tests only the mechanical skeleton

## Source material
- Saty's ATR Levels overview video (YouTube, March 2022): explains the indicator
- Saty's Twitter (@satymahajan): uses ATR levels for credit spreads at ±1 ATR
- Indicator available at satyland.com for ThinkorSwim and TradingView
