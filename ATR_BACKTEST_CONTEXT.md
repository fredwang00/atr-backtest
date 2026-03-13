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
- `atr_swing_backtest.py` — Main backtest script (ready to run)
- Uses yfinance for data, tests SPY/QQQ/AAPL/NVDA/TSLA/META/AMZN/GOOGL/MSFT/AMD
- Outputs: charts (PNG), trade log (CSV), summary stats (CSV) to `atr_swing_results/`

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

## Current results (as of 2026-03-12)
- 402 trades across 10 tickers, 2018-2026
- 85% win rate, profit factor 5.03, Sharpe 4.86
- Avg P&L +1.11% per trade, max DD -10.9%
- Tail risk from gap stops (tariff shock, earnings)

## What to do next
1. Integrate Pradeep's market monitor breadth data as a regime filter
2. Add earnings blackout filter
3. Compare filtered vs unfiltered results (breadth.py, earnings.py, compare.py)
4. Parameter sensitivity: vary STOP_LOSS_MODE, TRIGGER_PCT, MAX_HOLD_DAYS, SQUEEZE_LOOKBACK

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
