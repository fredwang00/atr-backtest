"""
ATR Levels Swing Mode — Rule-Based Backtest
=============================================

Encodes Saty's swing trading strategy into fully mechanical rules:

SETUP CONDITIONS (all must be true):
  1. TTM Squeeze has fired (Bollinger Bands expand outside Keltner Channels)
  2. EMA stack is aligned (8 > 9 > 21 > 34 > 50 for longs, reverse for shorts)
  3. Price crosses the 23.6% ATR trigger level
  4. Volume on the trigger candle is above 20-period SMA of volume

ENTRY:
  - Enter at the trigger level (limit order fill at 23.6% ATR)

EXIT (first one hit wins):
  - Profit Target 1: close half at 61.8% mid-range level
  - Profit Target 2: close remaining half at ±1 ATR (full range)
  - Stop Loss: configurable — default is close below central pivot (prev close)
  - Time Stop: exit after MAX_HOLD_DAYS if neither target nor stop hit

DATA:
  - Uses daily bars (appropriate for swing mode, 1-3 week holds)
  - Pulls data via yfinance

USAGE:
    pip install yfinance pandas numpy matplotlib
    python atr_swing_backtest.py

Author: Built collaboratively in Claude
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dataclasses import dataclass
from typing import Optional
import os
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# CONFIGURATION
# ============================================================

# Tickers to test
TICKERS = ["SPY", "QQQ", "AAPL", "NVDA", "TSLA", "META", "AMZN", "GOOGL", "MSFT", "AMD"]

# Indicator config (imported — these aliases keep existing references working)
from indicators import DAILY_CONFIG, compute_indicators
from data_loaders import download_ohlcv, START_DATE, END_DATE

ATR_PERIOD = DAILY_CONFIG.atr_period
TRIGGER_PCT = DAILY_CONFIG.trigger_pct
MID_PCT = DAILY_CONFIG.mid_pct
FULL_PCT = DAILY_CONFIG.full_pct
EMA_PERIODS = list(DAILY_CONFIG.ema_periods)
MACRO_EMA = DAILY_CONFIG.macro_ema
BB_PERIOD = DAILY_CONFIG.bb_period
BB_MULT = DAILY_CONFIG.bb_mult
KC_PERIOD = DAILY_CONFIG.kc_period
KC_MULT = DAILY_CONFIG.kc_mult
VOL_AVG_PERIOD = DAILY_CONFIG.vol_avg_period
SQUEEZE_LOOKBACK = DAILY_CONFIG.squeeze_lookback

# Trade management
MAX_HOLD_DAYS = 15       # Time stop — exit after this many days
STOP_LOSS_MODE = "pivot" # "pivot" = prev close, "trigger" = trigger level, "ema9" = 9 EMA

# Position sizing (for P&L calculation)
POSITION_SIZE = 10000    # $ per trade

# Output
OUTPUT_DIR = "atr_swing_results"


def prepare_data(ticker, config=DAILY_CONFIG):
    """Download and compute all indicators for a ticker.

    Args:
        ticker: Stock ticker symbol.
        config: IndicatorConfig for indicator parameters.

    Returns:
        (df, {}) tuple where df is the enriched DataFrame,
        or None if download fails.
    """
    df = download_ohlcv(ticker)
    if df is None:
        return None

    df = compute_indicators(df, config)
    return df, {}


# ============================================================
# TRADE LOGIC
# ============================================================

@dataclass
class Trade:
    ticker: str
    direction: str          # "long" or "short"
    entry_date: pd.Timestamp
    entry_price: float
    trigger_level: float
    mid_target: float
    full_target: float
    stop_level: float
    central_pivot: float
    atr_at_entry: float

    exit_date: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    half_exit_date: Optional[pd.Timestamp] = None
    half_exit_price: Optional[float] = None
    pnl_pct: float = 0.0
    hold_days: int = 0
    hit_mid: bool = False
    hit_full: bool = False
    size_mult: float = 1.0


def get_stop_level(df, idx, direction, trade_trigger):
    """
    Compute initial stop loss level based on configured mode.
    For "ema9" mode, this returns the initial value — but the actual
    stop is checked dynamically in simulate_trade() against the live EMA.
    """
    if STOP_LOSS_MODE == "pivot":
        return df["Central_Pivot"].iloc[idx]
    elif STOP_LOSS_MODE == "trigger":
        return trade_trigger
    elif STOP_LOSS_MODE == "ema9":
        # Return initial EMA_9 value; simulate_trade will use live values
        return df["EMA_9"].iloc[idx]
    else:
        return df["Central_Pivot"].iloc[idx]


def check_entry_conditions(df, i):
    """Check all entry conditions for bar i. Returns dict with per-condition results.

    Boolean keys (6 per direction):
      Long:  squeeze, momentum_long, ema_bull, long_crossover, volume, above_macro
      Short: squeeze, momentum_short, ema_bear, short_crossover, volume, below_macro

    Price-level keys (for scanner/journal display):
      long_trigger, short_trigger, mid_long, mid_short, full_long, full_short,
      central_pivot, atr, close
    """
    if i < 1:
        raise ValueError(f"check_entry_conditions requires i >= 1, got {i}")
    row = df.iloc[i]
    prev = df.iloc[i - 1]

    return {
        "squeeze": bool(row["Recent_Squeeze_Fire"]),
        "momentum_long": bool(row["Momentum"] > 0),
        "momentum_short": bool(row["Momentum"] < 0),
        "ema_bull": bool(row["EMA_Bull_Stack"]),
        "ema_bear": bool(row["EMA_Bear_Stack"]),
        "long_crossover": bool(row["Close"] > row["Long_Trigger"] and prev["Close"] <= prev["Long_Trigger"]),
        "short_crossover": bool(row["Close"] < row["Short_Trigger"] and prev["Close"] >= prev["Short_Trigger"]),
        "volume": bool(row["Vol_Above_Avg"]),
        "above_macro": bool(row["Close"] > row[f"EMA_{MACRO_EMA}"]),
        "below_macro": bool(row["Close"] < row[f"EMA_{MACRO_EMA}"]),
        "long_trigger": float(row["Long_Trigger"]),
        "short_trigger": float(row["Short_Trigger"]),
        "mid_long": float(row["Mid_Long"]),
        "mid_short": float(row["Mid_Short"]),
        "full_long": float(row["Full_Long"]),
        "full_short": float(row["Full_Short"]),
        "central_pivot": float(row["Central_Pivot"]),
        "atr": float(row["Prev_ATR"]),
        "close": float(row["Close"]),
    }


def run_backtest(df, entry_filter=None):
    """
    Scan for entries and simulate trades in a single forward pass.
    This ensures we never enter a new trade while one is still active
    (no overlapping positions).
    """
    trades = []
    in_trade = False
    current_trade = None

    for i in range(1, len(df)):
        # If we're in a trade, check if it has exited by this bar
        if in_trade and current_trade is not None:
            if current_trade.exit_date is not None and df.index[i] > current_trade.exit_date:
                in_trade = False
            else:
                continue  # Still in a trade, skip entry scanning

        row = df.iloc[i]

        trade = None

        conds = check_entry_conditions(df, i)

        # --- LONG ---
        # Crossover: today's close is above today's trigger, AND
        # yesterday's close was at or below yesterday's trigger.
        # Each day compared against its OWN trigger level (not today's).
        long_conditions = (
            conds["squeeze"]
            and conds["momentum_long"]
            and conds["ema_bull"]
            and conds["long_crossover"]
            and conds["volume"]
            and conds["above_macro"]
        )

        if long_conditions:
            # Enter at the trigger level (limit order fill), not at close.
            # On volatile days, close can overshoot all targets — entering
            # at trigger ensures targets are always above entry for longs.
            entry_px = row["Long_Trigger"]
            stop = get_stop_level(df, i, "long", row["Long_Trigger"])
            trade = Trade(
                ticker=df.attrs.get("ticker", ""),
                direction="long",
                entry_date=df.index[i],
                entry_price=entry_px,
                trigger_level=row["Long_Trigger"],
                mid_target=row["Mid_Long"],
                full_target=row["Full_Long"],
                stop_level=stop,
                central_pivot=row["Central_Pivot"],
                atr_at_entry=row["Prev_ATR"],
            )

        # --- SHORT (only if no long triggered) ---
        if trade is None:
            short_conditions = (
                conds["squeeze"]
                and conds["momentum_short"]
                and conds["ema_bear"]
                and conds["short_crossover"]
                and conds["volume"]
                and conds["below_macro"]
            )

            if short_conditions:
                entry_px = row["Short_Trigger"]
                stop = get_stop_level(df, i, "short", row["Short_Trigger"])
                trade = Trade(
                    ticker=df.attrs.get("ticker", ""),
                    direction="short",
                    entry_date=df.index[i],
                    entry_price=entry_px,
                    trigger_level=row["Short_Trigger"],
                    mid_target=row["Mid_Short"],
                    full_target=row["Full_Short"],
                    stop_level=stop,
                    central_pivot=row["Central_Pivot"],
                    atr_at_entry=row["Prev_ATR"],
                )

        if trade is not None:
            # Apply external filter if provided
            if entry_filter is not None and not entry_filter(df, i, trade.direction):
                trade = None

        if trade is not None:
            simulate_trade(df, trade)
            trades.append(trade)
            in_trade = True
            current_trade = trade

    return trades


def simulate_trade(df, trade):
    """
    Walk forward from entry and manage the trade.

    For LONG:
      - If high >= mid_target → mark half exit at mid_target
      - If high >= full_target → exit remaining at full_target
      - If close < stop_level → exit at stop (use close, not intraday low)
      - If hold_days >= MAX_HOLD_DAYS → exit at close

    For SHORT (mirror):
      - If low <= mid_target → mark half exit
      - If low <= full_target → exit remaining
      - If close > stop_level → exit at stop
      - If hold_days >= MAX_HOLD_DAYS → exit at close

    P&L is computed as weighted average of the two halves.
    """
    entry_idx = df.index.get_loc(trade.entry_date)
    half_exited = False
    half_pnl_pct = 0.0

    for day in range(1, MAX_HOLD_DAYS + 1):
        idx = entry_idx + day
        if idx >= len(df):
            # Ran out of data — exit at last available close
            trade.exit_date = df.index[-1]
            trade.exit_price = df["Close"].iloc[-1]
            trade.exit_reason = "data_end"
            trade.hold_days = day
            break

        bar = df.iloc[idx]

        # Resolve current stop level (dynamic for ema9 mode)
        if STOP_LOSS_MODE == "ema9":
            current_stop = bar["EMA_9"]
        else:
            current_stop = trade.stop_level

        if trade.direction == "long":
            # On a single daily bar, price could hit both stop and target.
            # With daily data we can't know which came first. Assume:
            # - If open < stop: gapped down, stop hit first
            # - If open >= stop: targets checked first, then stop on close
            gapped_past_stop = bar["Open"] < current_stop

            if gapped_past_stop:
                # Gap down — stopped out at open (or close, conservatively)
                trade.exit_date = df.index[idx]
                trade.exit_price = bar["Close"]
                trade.exit_reason = "stop_loss"
                trade.hold_days = day
                break

            # Check mid target
            if not half_exited and bar["High"] >= trade.mid_target:
                half_exited = True
                trade.hit_mid = True
                trade.half_exit_date = df.index[idx]
                trade.half_exit_price = trade.mid_target
                half_pnl_pct = (trade.mid_target - trade.entry_price) / trade.entry_price

            # Check full target
            if bar["High"] >= trade.full_target:
                trade.hit_full = True
                trade.exit_date = df.index[idx]
                trade.exit_price = trade.full_target
                trade.exit_reason = "full_target"
                trade.hold_days = day
                break

            # Check stop on close (end of day)
            if bar["Close"] < current_stop:
                trade.exit_date = df.index[idx]
                trade.exit_price = bar["Close"]
                trade.exit_reason = "stop_loss"
                trade.hold_days = day
                break

        else:  # short
            # If open > stop: gapped up past stop
            gapped_past_stop = bar["Open"] > current_stop

            if gapped_past_stop:
                trade.exit_date = df.index[idx]
                trade.exit_price = bar["Close"]
                trade.exit_reason = "stop_loss"
                trade.hold_days = day
                break

            if not half_exited and bar["Low"] <= trade.mid_target:
                half_exited = True
                trade.hit_mid = True
                trade.half_exit_date = df.index[idx]
                trade.half_exit_price = trade.mid_target
                half_pnl_pct = (trade.entry_price - trade.mid_target) / trade.entry_price

            if bar["Low"] <= trade.full_target:
                trade.hit_full = True
                trade.exit_date = df.index[idx]
                trade.exit_price = trade.full_target
                trade.exit_reason = "full_target"
                trade.hold_days = day
                break

            # Check stop on close
            if bar["Close"] > current_stop:
                trade.exit_date = df.index[idx]
                trade.exit_price = bar["Close"]
                trade.exit_reason = "stop_loss"
                trade.hold_days = day
                break

    else:
        # Time stop — MAX_HOLD_DAYS reached
        idx = min(entry_idx + MAX_HOLD_DAYS, len(df) - 1)
        trade.exit_date = df.index[idx]
        trade.exit_price = df["Close"].iloc[idx]
        trade.exit_reason = "time_stop"
        trade.hold_days = MAX_HOLD_DAYS

    # Compute P&L
    if trade.exit_price is not None:
        if trade.direction == "long":
            remaining_pnl_pct = (trade.exit_price - trade.entry_price) / trade.entry_price
        else:
            remaining_pnl_pct = (trade.entry_price - trade.exit_price) / trade.entry_price

        if half_exited:
            # 50% exited at mid, 50% exited at final
            trade.pnl_pct = (half_pnl_pct * 0.5 + remaining_pnl_pct * 0.5)
        else:
            trade.pnl_pct = remaining_pnl_pct

    return trade


# ============================================================
# REPORTING
# ============================================================

def print_trade_summary(all_trades, ticker="ALL"):
    """Print comprehensive statistics."""
    if not all_trades:
        print(f"\n  {ticker}: No trades found.")
        return {}

    trades = [t for t in all_trades if t.exit_price is not None]
    if not trades:
        print(f"\n  {ticker}: No completed trades.")
        return {}

    n = len(trades)
    winners = [t for t in trades if t.pnl_pct > 0]
    losers = [t for t in trades if t.pnl_pct <= 0]
    win_rate = len(winners) / n * 100

    pnls = [t.pnl_pct for t in trades]
    avg_pnl = np.mean(pnls) * 100
    median_pnl = np.median(pnls) * 100
    avg_win = np.mean([t.pnl_pct for t in winners]) * 100 if winners else 0
    avg_loss = np.mean([t.pnl_pct for t in losers]) * 100 if losers else 0

    # Profit factor
    gross_profit = sum(t.pnl_pct for t in winners)
    gross_loss = abs(sum(t.pnl_pct for t in losers))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Hold days
    avg_hold = np.mean([t.hold_days for t in trades])

    # Exit reasons
    reasons = {}
    for t in trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1

    # Hit rates
    hit_mid = sum(1 for t in trades if t.hit_mid) / n * 100
    hit_full = sum(1 for t in trades if t.hit_full) / n * 100

    # Direction split
    longs = [t for t in trades if t.direction == "long"]
    shorts = [t for t in trades if t.direction == "short"]
    long_wr = len([t for t in longs if t.pnl_pct > 0]) / max(len(longs), 1) * 100
    short_wr = len([t for t in shorts if t.pnl_pct > 0]) / max(len(shorts), 1) * 100

    # Cumulative P&L for drawdown
    cum_pnl = np.cumsum(pnls)
    cum_max = np.maximum.accumulate(cum_pnl)
    drawdowns = cum_pnl - cum_max
    max_dd = drawdowns.min() * 100

    # Expectancy (avg $ won per $ risked)
    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

    # Sharpe ratio (annualized, assuming ~1.3 day avg hold = ~190 trades/yr capacity)
    # Using per-trade returns, annualized by sqrt of estimated trades per year
    if len(pnls) > 1 and np.std(pnls) > 0:
        # Calculate using actual trade dates for proper annualization
        first_trade = trades[0].entry_date
        last_trade = trades[-1].exit_date or trades[-1].entry_date
        years = (last_trade - first_trade).days / 365.25
        trades_per_year = n / years if years > 0 else n
        sharpe = (np.mean(pnls) / np.std(pnls)) * np.sqrt(trades_per_year)
    else:
        sharpe = 0.0

    print(f"\n{'='*60}")
    print(f"  {ticker} — TRADE SUMMARY")
    print(f"{'='*60}")
    print(f"  Total trades:       {n}")
    print(f"  Longs / Shorts:     {len(longs)} / {len(shorts)}")
    print(f"  Win rate:           {win_rate:.1f}%")
    print(f"    Long win rate:    {long_wr:.1f}% ({len(longs)} trades)")
    print(f"    Short win rate:   {short_wr:.1f}% ({len(shorts)} trades)")
    print(f"  Avg P&L per trade:  {avg_pnl:.2f}%")
    print(f"  Median P&L:         {median_pnl:.2f}%")
    print(f"  Avg winner:         +{avg_win:.2f}%")
    print(f"  Avg loser:          {avg_loss:.2f}%")
    print(f"  Profit factor:      {profit_factor:.2f}")
    print(f"  Sharpe ratio:       {sharpe:.2f}")
    print(f"  Expectancy:         {expectancy:.2f}% per trade")
    print(f"  Max drawdown:       {max_dd:.2f}%")
    print(f"  Avg hold days:      {avg_hold:.1f}")
    print(f"  Hit mid-range:      {hit_mid:.1f}%")
    print(f"  Hit full ATR:       {hit_full:.1f}%")
    print(f"\n  Exit reasons:")
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"    {reason:20s} {count:4d}  ({count/n*100:.1f}%)")

    # Show worst trades
    worst = sorted(trades, key=lambda t: t.pnl_pct)[:5]
    print(f"\n  Worst 5 trades:")
    for t in worst:
        print(f"    {t.entry_date.strftime('%Y-%m-%d')} {t.direction:5s} "
              f"P&L: {t.pnl_pct*100:+.2f}% exit: {t.exit_reason} "
              f"hold: {t.hold_days}d")

    # Show best trades
    best = sorted(trades, key=lambda t: -t.pnl_pct)[:5]
    print(f"\n  Best 5 trades:")
    for t in best:
        print(f"    {t.entry_date.strftime('%Y-%m-%d')} {t.direction:5s} "
              f"P&L: {t.pnl_pct*100:+.2f}% exit: {t.exit_reason} "
              f"hold: {t.hold_days}d")

    return {
        "ticker": ticker,
        "total_trades": n,
        "longs": len(longs),
        "shorts": len(shorts),
        "win_rate": win_rate,
        "long_wr": long_wr,
        "short_wr": short_wr,
        "avg_pnl_pct": avg_pnl,
        "median_pnl_pct": median_pnl,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_dd,
        "avg_hold_days": avg_hold,
        "hit_mid_pct": hit_mid,
        "hit_full_pct": hit_full,
        "reasons": reasons,
    }


def generate_charts(all_trades_by_ticker, output_dir):
    """Generate analysis charts."""
    os.makedirs(output_dir, exist_ok=True)

    # --- Per-ticker equity curves ---
    for ticker, trades in all_trades_by_ticker.items():
        completed = [t for t in trades if t.exit_price is not None]
        if not completed:
            continue

        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        fig.suptitle(f"{ticker} — ATR Swing Backtest Results", fontsize=14, fontweight='bold')

        # 1. Equity curve
        ax = axes[0, 0]
        pnls = [t.pnl_pct * POSITION_SIZE for t in completed]
        dates = [t.exit_date for t in completed]
        cum_pnl = np.cumsum(pnls)
        ax.plot(dates, cum_pnl, color='green', linewidth=1.2)
        ax.fill_between(dates, cum_pnl, alpha=0.1, color='green')
        ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
        ax.set_title(f"Cumulative P&L (${POSITION_SIZE:,} per trade)")
        ax.set_ylabel("$")

        # 2. P&L distribution
        ax = axes[0, 1]
        pnl_pcts = [t.pnl_pct * 100 for t in completed]
        ax.hist(pnl_pcts, bins=30, color='steelblue', alpha=0.7, edgecolor='black', linewidth=0.3)
        ax.axvline(0, color='red', linestyle='--', linewidth=1.5)
        ax.axvline(np.mean(pnl_pcts), color='green', linestyle='--', linewidth=1.5, label=f'Mean: {np.mean(pnl_pcts):.2f}%')
        ax.set_title("P&L Distribution (%)")
        ax.legend()

        # 3. Win rate by direction
        ax = axes[1, 0]
        longs = [t for t in completed if t.direction == "long"]
        shorts = [t for t in completed if t.direction == "short"]
        long_wr = len([t for t in longs if t.pnl_pct > 0]) / max(len(longs), 1) * 100
        short_wr = len([t for t in shorts if t.pnl_pct > 0]) / max(len(shorts), 1) * 100
        bars = ax.bar(["Long", "Short"], [long_wr, short_wr], color=['#2196F3', '#FF5722'])
        ax.set_title("Win Rate by Direction")
        ax.set_ylabel("%")
        ax.set_ylim(0, 100)
        for bar, val in zip(bars, [long_wr, short_wr]):
            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 1,
                    f'{val:.0f}%', ha='center', fontweight='bold')

        # 4. Exit reason breakdown
        ax = axes[1, 1]
        reasons = {}
        for t in completed:
            reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
        if reasons:
            labels = list(reasons.keys())
            values = list(reasons.values())
            colors = {'full_target': '#4CAF50', 'stop_loss': '#F44336',
                      'time_stop': '#FF9800', 'data_end': '#9E9E9E'}
            bar_colors = [colors.get(l, '#607D8B') for l in labels]
            ax.bar(labels, values, color=bar_colors)
            ax.set_title("Exit Reasons")
            ax.set_ylabel("Count")

        plt.tight_layout()
        path = os.path.join(output_dir, f"{ticker}_swing_results.png")
        plt.savefig(path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  Chart saved: {path}")

    # --- Cross-ticker comparison ---
    all_completed = {}
    for ticker, trades in all_trades_by_ticker.items():
        completed = [t for t in trades if t.exit_price is not None]
        if completed:
            all_completed[ticker] = completed

    if len(all_completed) > 1:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        fig.suptitle("Cross-Ticker Comparison", fontsize=14, fontweight='bold')

        tickers_list = list(all_completed.keys())

        # Win rates
        ax = axes[0]
        wrs = [len([t for t in all_completed[tk] if t.pnl_pct > 0]) / len(all_completed[tk]) * 100
               for tk in tickers_list]
        ax.bar(tickers_list, wrs, color='steelblue')
        ax.set_title("Win Rate by Ticker")
        ax.set_ylabel("%")
        ax.axhline(50, color='red', linestyle='--', alpha=0.5)

        # Avg P&L
        ax = axes[1]
        avg_pnls = [np.mean([t.pnl_pct for t in all_completed[tk]]) * 100 for tk in tickers_list]
        colors = ['green' if p > 0 else 'red' for p in avg_pnls]
        ax.bar(tickers_list, avg_pnls, color=colors)
        ax.set_title("Avg P&L per Trade (%)")
        ax.set_ylabel("%")
        ax.axhline(0, color='gray', linestyle='--')

        plt.tight_layout()
        path = os.path.join(output_dir, "cross_ticker_comparison.png")
        plt.savefig(path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  Comparison chart saved: {path}")


# ============================================================
# TRADES TO CSV
# ============================================================

def trades_to_dataframe(trades):
    """Convert list of Trade objects to a DataFrame for export."""
    records = []
    for t in trades:
        records.append({
            "ticker": t.ticker,
            "direction": t.direction,
            "entry_date": t.entry_date,
            "entry_price": round(t.entry_price, 2),
            "trigger_level": round(t.trigger_level, 2),
            "mid_target": round(t.mid_target, 2),
            "full_target": round(t.full_target, 2),
            "stop_level": round(t.stop_level, 2),
            "central_pivot": round(t.central_pivot, 2),
            "atr_at_entry": round(t.atr_at_entry, 2),
            "exit_date": t.exit_date,
            "exit_price": round(t.exit_price, 2) if t.exit_price else None,
            "exit_reason": t.exit_reason,
            "half_exit_date": t.half_exit_date,
            "half_exit_price": round(t.half_exit_price, 2) if t.half_exit_price else None,
            "pnl_pct": round(t.pnl_pct * 100, 4),
            "pnl_dollars": round(t.pnl_pct * POSITION_SIZE, 2),
            "hold_days": t.hold_days,
            "hit_mid": t.hit_mid,
            "hit_full": t.hit_full,
        })
    return pd.DataFrame(records)


# ============================================================
# CREDIT SPREAD BACKTEST
# ============================================================

# Credit spread config
CS_SPREAD_WIDTH_DOLLARS = 5.0   # $5 wide spread (standard for SPY/QQQ)
CS_CREDIT_PCT = 0.30            # ~30% of spread width as credit received
CS_TICKERS = ["SPY", "QQQ"]    # High-liquidity underlyings for credit spreads

def run_credit_spread_backtest():
    """
    Test Saty's credit spread thesis: sell put spreads below -1 ATR,
    sell call spreads above +1 ATR.

    Tests multiple scenarios:
    1. DTE sweep (1, 3, 5, 7 days) — how quickly does containment decay?
    2. Strike distance sweep (1.0, 1.5, 2.0x ATR) — wider strikes = higher win rate
    3. Filtered vs unfiltered — do squeeze/EMA conditions improve the odds?
    """
    print(f"\n  Tickers: {', '.join(CS_TICKERS)}")

    all_cs_results = []

    for ticker in CS_TICKERS:
        result = prepare_data(ticker)
        if result is None:
            continue
        df, _ = result

        # ---- DTE x Strike Distance Matrix ----
        dte_options = [1, 3, 5, 7]
        strike_multipliers = [1.0, 1.5, 2.0]

        print(f"\n  {ticker} — Containment Matrix (% of days price stays within strikes)")
        print(f"  {'DTE':>5s}", end="")
        for mult in strike_multipliers:
            print(f"  {mult:.1f}x ATR", end="")
        print()

        for dte in dte_options:
            print(f"  {dte:>3d}d ", end="")
            for mult in strike_multipliers:
                put_wins = 0
                call_wins = 0
                both_wins = 0
                total = 0

                for i in range(len(df) - dte):
                    row = df.iloc[i]
                    if pd.isna(row["Prev_ATR"]) or pd.isna(row["Prev_Close"]):
                        continue

                    upper = row["Prev_Close"] + mult * row["Prev_ATR"]
                    lower = row["Prev_Close"] - mult * row["Prev_ATR"]

                    future = df.iloc[i+1:i+1+dte]
                    if len(future) < dte:
                        continue

                    max_high = future["High"].max()
                    min_low = future["Low"].min()

                    total += 1
                    put_ok = min_low > lower
                    call_ok = max_high < upper

                    if put_ok:
                        put_wins += 1
                    if call_ok:
                        call_wins += 1
                    if put_ok and call_ok:
                        both_wins += 1

                if total > 0:
                    put_wr = put_wins / total * 100
                    call_wr = call_wins / total * 100
                    both_wr = both_wins / total * 100
                    print(f"  P:{put_wr:4.0f}% C:{call_wr:4.0f}% IC:{both_wr:4.0f}%", end="")

                    all_cs_results.append({
                        "ticker": ticker, "dte": dte, "strike_mult": mult,
                        "put_wr": put_wr, "call_wr": call_wr, "ic_wr": both_wr,
                        "sample_size": total, "filter": "none",
                    })
            print()

        # ---- P&L simulation for the most promising config ----
        # Uses expiration-based model: check closing price on last day of DTE,
        # not whether strike was ever breached (options settle at expiration).
        for dte, mult, label in [(1, 1.0, "1DTE@1.0x"), (5, 1.5, "5DTE@1.5x")]:
            pnls = []
            credit = CS_SPREAD_WIDTH_DOLLARS * CS_CREDIT_PCT

            for i in range(len(df) - dte):
                row = df.iloc[i]
                if pd.isna(row["Prev_ATR"]) or pd.isna(row["Prev_Close"]):
                    continue

                upper = row["Prev_Close"] + mult * row["Prev_ATR"]
                lower = row["Prev_Close"] - mult * row["Prev_ATR"]

                future = df.iloc[i+1:i+1+dte]
                if len(future) < dte:
                    continue

                # Settlement price = close on expiration day
                exp_close = future["Close"].iloc[-1]

                # Iron condor P&L based on where price settles at expiration.
                # Price can only be in one place — at most one side loses.
                put_loss = max(lower - exp_close, 0)  # put spread ITM amount
                call_loss = max(exp_close - upper, 0)  # call spread ITM amount
                # Cap each side's loss at spread width
                put_loss = min(put_loss, CS_SPREAD_WIDTH_DOLLARS)
                call_loss = min(call_loss, CS_SPREAD_WIDTH_DOLLARS)
                pnl = (credit * 2) - put_loss - call_loss
                pnls.append(pnl)

            if pnls:
                arr = np.array(pnls)
                trades_per_year = 252 / dte
                sharpe = (np.mean(arr) / np.std(arr)) * np.sqrt(trades_per_year) if np.std(arr) > 0 else 0
                cum = np.cumsum(pnls)
                cum_max = np.maximum.accumulate(cum)
                max_dd = (cum - cum_max).min()
                win_count = sum(1 for p in pnls if p > 0)

                print(f"\n  {ticker} IC {label} ($5 wide, ${credit:.2f} credit/side):")
                print(f"    Trades:    {len(pnls)}")
                print(f"    Win rate:  {win_count/len(pnls)*100:.1f}%")
                print(f"    Avg P&L:   ${np.mean(pnls):.2f}")
                print(f"    Total P&L: ${np.sum(pnls):.0f}")
                print(f"    Sharpe:    {sharpe:.2f}")
                print(f"    Max DD:    ${max_dd:.0f}")

        # ---- Filtered: only trade when squeeze/EMA setup is active ----
        print(f"\n  {ticker} — FILTERED (squeeze + EMA stack + macro trend):")
        for dte, mult in [(1, 1.0), (3, 1.0), (5, 1.5)]:
            put_pnls = []
            call_pnls = []
            credit = CS_SPREAD_WIDTH_DOLLARS * CS_CREDIT_PCT

            for i in range(len(df) - dte):
                row = df.iloc[i]
                if pd.isna(row["Prev_ATR"]) or pd.isna(row["Prev_Close"]):
                    continue

                # Apply setup conditions
                has_squeeze = row["Recent_Squeeze_Fire"]
                if not has_squeeze:
                    continue

                future = df.iloc[i+1:i+1+dte]
                if len(future) < dte:
                    continue

                # Settlement price at expiration
                exp_close = future["Close"].iloc[-1]

                # Bull put (sell when bullish setup — put is OTM)
                if row["Momentum"] > 0 and row["EMA_Bull_Stack"] and row["Close"] > row[f"EMA_{MACRO_EMA}"]:
                    lower = row["Prev_Close"] - mult * row["Prev_ATR"]
                    itm_amount = max(lower - exp_close, 0)
                    put_pnls.append(credit - min(itm_amount, CS_SPREAD_WIDTH_DOLLARS))

                # Bear call (sell when bearish setup — call is OTM)
                if row["Momentum"] < 0 and row["EMA_Bear_Stack"] and row["Close"] < row[f"EMA_{MACRO_EMA}"]:
                    upper = row["Prev_Close"] + mult * row["Prev_ATR"]
                    itm_amount = max(exp_close - upper, 0)
                    call_pnls.append(credit - min(itm_amount, CS_SPREAD_WIDTH_DOLLARS))

            for side, pnls in [("Bull Put", put_pnls), ("Bear Call", call_pnls)]:
                if not pnls:
                    continue
                arr = np.array(pnls)
                wins = sum(1 for p in pnls if p > 0)
                trades_per_year = len(pnls) / ((df.index[-1] - df.index[0]).days / 365.25)
                sharpe = (np.mean(arr) / np.std(arr)) * np.sqrt(max(trades_per_year, 1)) if np.std(arr) > 0 else 0

                print(f"    {side} {dte}DTE@{mult}x: {len(pnls)} trades, "
                      f"WR={wins/len(pnls)*100:.0f}%, "
                      f"Avg=${np.mean(pnls):.2f}, "
                      f"Sharpe={sharpe:.2f}")

                all_cs_results.append({
                    "ticker": ticker, "dte": dte, "strike_mult": mult,
                    "put_wr" if "Put" in side else "call_wr": wins/len(pnls)*100,
                    "sample_size": len(pnls), "filter": "squeeze+ema",
                    "sharpe": sharpe, "avg_pnl": np.mean(pnls),
                })

    if all_cs_results:
        cs_df = pd.DataFrame(all_cs_results)
        cs_path = os.path.join(OUTPUT_DIR, "credit_spread_stats.csv")
        cs_df.to_csv(cs_path, index=False)
        print(f"\n  Credit spread stats saved: {cs_path}")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("  ATR LEVELS SWING MODE BACKTEST")
    print(f"  Tickers: {', '.join(TICKERS)}")
    print(f"  Period: {START_DATE} to {END_DATE}")
    print(f"  Stop mode: {STOP_LOSS_MODE}")
    print(f"  Max hold: {MAX_HOLD_DAYS} days")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_trades_by_ticker = {}
    all_stats = []
    all_trades_flat = []

    for ticker in TICKERS:
        try:
            result = prepare_data(ticker)
            if result is None:
                continue

            df, _ = result
            df.attrs["ticker"] = ticker

            # Run backtest (scan entries + simulate trades in one pass,
            # ensuring no overlapping positions)
            entries = run_backtest(df)
            print(f"  {ticker}: {len(entries)} trades found")

            all_trades_by_ticker[ticker] = entries
            all_trades_flat.extend(entries)

            # Print per-ticker summary
            stats = print_trade_summary(entries, ticker)
            if stats:
                all_stats.append(stats)

        except Exception as e:
            print(f"  ERROR on {ticker}: {e}")
            import traceback
            traceback.print_exc()

    # Overall summary
    print_trade_summary(all_trades_flat, "ALL TICKERS COMBINED")

    # Generate charts
    print("\nGenerating charts...")
    generate_charts(all_trades_by_ticker, OUTPUT_DIR)

    # Save trades to CSV
    if all_trades_flat:
        trades_df = trades_to_dataframe(all_trades_flat)
        trades_path = os.path.join(OUTPUT_DIR, "all_trades.csv")
        trades_df.to_csv(trades_path, index=False)
        print(f"\nAll trades saved: {trades_path}")

    # Save summary stats
    if all_stats:
        stats_df = pd.DataFrame(all_stats)
        stats_path = os.path.join(OUTPUT_DIR, "summary_stats.csv")
        stats_df.to_csv(stats_path, index=False)
        print(f"Summary stats saved: {stats_path}")

    # ---- CREDIT SPREAD BACKTEST ----
    print("\n" + "=" * 60)
    print("  CREDIT SPREAD BACKTEST (SELLING AT ±1 ATR)")
    print("=" * 60)
    run_credit_spread_backtest()

    # ---- PARAMETER SENSITIVITY HINT ----
    print("\n" + "=" * 60)
    print("  NEXT STEPS — THINGS TO EXPERIMENT WITH")
    print("=" * 60)
    print("""
  The config at the top of this script is where you tweak the rules:

  1. STOP_LOSS_MODE: Try "trigger" or "ema9" instead of "pivot"
     - "pivot" (previous close) is the widest stop
     - "trigger" (the 23.6% level) is tighter
     - "ema9" follows the 9 EMA — dynamic stop

  2. TRIGGER_PCT: Try 0.15 or 0.30 instead of 0.236
     - Lower = more sensitive, earlier entries, more signals
     - Higher = fewer signals but price has more momentum

  3. MAX_HOLD_DAYS: Try 10 or 20 instead of 15
     - Shorter = more disciplined, less exposure
     - Longer = lets winners run further

  4. EMA_PERIODS: Try removing the 34/50 requirement
     - Looser stack = more signals
     - Stricter stack = fewer but higher-conviction

  5. Remove the MACRO_EMA (200) filter entirely
     - You'll get more signals but potentially more noise

  6. SQUEEZE_LOOKBACK: Try 5 or 15 instead of 10
     - How "fresh" does the squeeze fire need to be?

  Run the script multiple times with different configs and compare
  the win rate, profit factor, and max drawdown.
  """)


if __name__ == "__main__":
    main()
