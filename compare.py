"""
Comparison runner: tests ATR swing backtest under multiple filter configurations
to quantify whether breadth data and earnings filters improve edge.
"""

import pandas as pd
import numpy as np
import os

from atr_swing_backtest import (
    TICKERS, prepare_data, run_backtest,
    trades_to_dataframe, OUTPUT_DIR,
)
from breadth import load_breadth_data
from earnings import get_earnings_blackout

# Regimes where longs are allowed
LONG_REGIMES = {"NEUTRAL", "BULLISH", "EXTREME_BULLISH"}
# Regimes where shorts are allowed
SHORT_REGIMES = {"NEUTRAL", "BEARISH", "EXTREME_BEARISH"}
# Breadth trends where we reduce size
REDUCE_SIZE_TRENDS = {"DETERIORATING", "DETERIORATING_FAST"}


def make_regime_filter(breadth_df):
    """Create entry filter using full Pradeep regime classification."""
    def entry_filter(df, i, direction):
        date = df.index[i]
        mask = breadth_df.index <= date
        if not mask.any():
            return True
        regime = breadth_df.loc[mask].iloc[-1]["regime"]
        if direction == "long":
            return regime in LONG_REGIMES
        else:
            return regime in SHORT_REGIMES
    return entry_filter


def make_ratio10_filter(breadth_df):
    """Create entry filter using simple ratio10 bias."""
    def entry_filter(df, i, direction):
        date = df.index[i]
        mask = breadth_df.index <= date
        if not mask.any():
            return True
        bias = breadth_df.loc[mask].iloc[-1]["ratio10_bias"]
        if direction == "long":
            return bias in ("long", "neutral")
        else:
            return bias in ("short", "neutral")
    return entry_filter


def make_earnings_filter(blackout_sets):
    """Create entry filter that skips trades near earnings."""
    def entry_filter(df, i, direction):
        date = df.index[i]
        ticker = df.attrs.get("ticker", "")
        if ticker in blackout_sets:
            return date not in blackout_sets[ticker]
        return True
    return entry_filter


def make_combined_filter(*filters):
    """Combine multiple entry filters (all must return True)."""
    def entry_filter(df, i, direction):
        return all(f(df, i, direction) for f in filters)
    return entry_filter


def add_regime_at_entry(trades, breadth_df):
    """Annotate each trade with the breadth regime on entry date."""
    for t in trades:
        mask = breadth_df.index <= t.entry_date
        if mask.any():
            t._regime_at_entry = breadth_df.loc[mask].iloc[-1]["regime"]
        else:
            t._regime_at_entry = "UNKNOWN"


def compute_stats(trades):
    """Compute summary stats for a list of trades."""
    completed = [t for t in trades if t.exit_price is not None]
    if not completed:
        return {
            "trades": 0, "win_rate": 0, "avg_pnl": 0, "sharpe": 0,
            "profit_factor": 0, "max_dd": 0, "longs": 0, "shorts": 0,
        }

    n = len(completed)
    pnls = [t.pnl_pct for t in completed]
    winners = [t for t in completed if t.pnl_pct > 0]
    losers = [t for t in completed if t.pnl_pct <= 0]

    gross_profit = sum(t.pnl_pct for t in winners)
    gross_loss = abs(sum(t.pnl_pct for t in losers))
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    cum = np.cumsum(pnls)
    cum_max = np.maximum.accumulate(cum)
    max_dd = (cum - cum_max).min() * 100

    if len(pnls) > 1 and np.std(pnls) > 0:
        first = completed[0].entry_date
        last = completed[-1].exit_date or completed[-1].entry_date
        years = max((last - first).days / 365.25, 0.1)
        tpy = n / years
        sharpe = (np.mean(pnls) / np.std(pnls)) * np.sqrt(tpy)
    else:
        sharpe = 0.0

    return {
        "trades": n,
        "longs": sum(1 for t in completed if t.direction == "long"),
        "shorts": sum(1 for t in completed if t.direction == "short"),
        "win_rate": len(winners) / n * 100,
        "avg_pnl": np.mean(pnls) * 100,
        "sharpe": sharpe,
        "profit_factor": pf,
        "max_dd": max_dd,
    }


def main():
    print("=" * 70)
    print("  BREADTH INTEGRATION COMPARISON")
    print("=" * 70)

    print("\nLoading breadth data...")
    breadth_df = load_breadth_data("breadth_data")
    print(f"  {len(breadth_df)} days loaded, {breadth_df.index.min().date()} to {breadth_df.index.max().date()}")

    print("Loading earnings dates...")
    blackout_sets = {}
    for ticker in TICKERS:
        blackout_sets[ticker] = get_earnings_blackout(ticker, "2018-01-01", "2026-12-31")
        print(f"  {ticker}: {len(blackout_sets[ticker])} blackout days")

    regime_filter = make_regime_filter(breadth_df)
    ratio10_filter = make_ratio10_filter(breadth_df)
    earnings_filter = make_earnings_filter(blackout_sets)

    configs = [
        ("Baseline", None),
        ("+Earnings", earnings_filter),
        ("+Regime", regime_filter),
        ("+Regime+Earnings", make_combined_filter(regime_filter, earnings_filter)),
        ("+Ratio10", ratio10_filter),
        ("+Ratio10+Earnings", make_combined_filter(ratio10_filter, earnings_filter)),
        ("+Regime+Earn+Sizing", make_combined_filter(regime_filter, earnings_filter)),
    ]

    # Prepare data once per ticker (avoid redundant yfinance downloads)
    print("\nPreparing ticker data...")
    ticker_data = {}
    for ticker in TICKERS:
        try:
            result = prepare_data(ticker)
            if result is not None:
                df, _ = result
                df.attrs["ticker"] = ticker
                ticker_data[ticker] = df
        except Exception as e:
            print(f"  ERROR on {ticker}: {e}")

    all_results = {}
    all_trade_logs = {}

    for config_name, entry_filter in configs:
        print(f"\nRunning: {config_name}...")
        all_trades = []

        for ticker, df in ticker_data.items():
            trades = run_backtest(df, entry_filter=entry_filter)
            add_regime_at_entry(trades, breadth_df)
            all_trades.extend(trades)

        # Apply half-sizing when breadth trend is deteriorating
        if "Sizing" in config_name:
            for t in all_trades:
                mask = breadth_df.index <= t.entry_date
                if mask.any():
                    trend = breadth_df.loc[mask].iloc[-1]["breadth_trend"]
                    if trend in REDUCE_SIZE_TRENDS:
                        t.size_mult = 0.5
                        t.pnl_pct *= 0.5

        stats = compute_stats(all_trades)
        all_results[config_name] = stats
        all_trade_logs[config_name] = all_trades
        print(f"  {config_name}: {stats['trades']} trades, "
              f"WR={stats['win_rate']:.1f}%, "
              f"Avg={stats['avg_pnl']:.2f}%, "
              f"Sharpe={stats['sharpe']:.2f}")

    print("\n" + "=" * 70)
    print("  COMPARISON TABLE")
    print("=" * 70)
    header = f"  {'Config':<22s} {'Trades':>6s} {'WR%':>6s} {'AvgP&L':>8s} {'Sharpe':>7s} {'PF':>6s} {'MaxDD':>8s} {'L/S':>8s}"
    print(header)
    print("  " + "-" * 68)
    for name, stats in all_results.items():
        ls = f"{stats['longs']}/{stats['shorts']}"
        pf_str = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "inf"
        print(f"  {name:<22s} {stats['trades']:>6d} {stats['win_rate']:>5.1f}% "
              f"{stats['avg_pnl']:>+7.2f}% {stats['sharpe']:>7.2f} {pf_str:>6s} "
              f"{stats['max_dd']:>+7.2f}% {ls:>8s}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    comp_df = pd.DataFrame(all_results).T
    comp_df.index.name = "config"
    comp_path = os.path.join(OUTPUT_DIR, "comparison.csv")
    comp_df.to_csv(comp_path)
    print(f"\nComparison saved: {comp_path}")

    for config_name, trades in all_trade_logs.items():
        if trades:
            tdf = trades_to_dataframe(trades)
            tdf["regime_at_entry"] = [getattr(t, "_regime_at_entry", "UNKNOWN") for t in trades]
            safe_name = config_name.replace("+", "plus_").replace(" ", "_").lower()
            path = os.path.join(OUTPUT_DIR, f"trades_{safe_name}.csv")
            tdf.to_csv(path, index=False)

    print(f"\nTrade logs saved to {OUTPUT_DIR}/trades_*.csv")


if __name__ == "__main__":
    main()
