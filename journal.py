"""
Trade journal for ATR swing pilot trades.

Usage:
    python journal.py log      # log a new entry or close a trade
    python journal.py review   # review stats vs backtest expectations
"""

import sys
import os
import pandas as pd
import numpy as np

JOURNAL_PATH = "trades_journal.csv"
JOURNAL_COLUMNS = [
    "date", "ticker", "direction", "entry_price", "size", "size_mult",
    "trigger_level", "mid_target", "full_target", "stop_level",
    "regime", "breadth_trend", "exit_date", "exit_price", "exit_reason",
    "pnl_pct", "notes",
]

BACKTEST_WR = 86.8
BACKTEST_AVG_PNL = 1.10


def load_journal(path=JOURNAL_PATH):
    """Load journal CSV, creating it with headers if it doesn't exist."""
    if not os.path.exists(path):
        df = pd.DataFrame(columns=JOURNAL_COLUMNS)
        df.to_csv(path, index=False)
        return df
    return pd.read_csv(path)


def add_entry(entry_dict, path=JOURNAL_PATH):
    """Append a new trade entry to the journal."""
    df = load_journal(path)
    row = {col: entry_dict.get(col, "") for col in JOURNAL_COLUMNS}
    row["exit_date"] = ""
    row["exit_price"] = ""
    row["exit_reason"] = ""
    row["pnl_pct"] = ""
    new_df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    new_df.to_csv(path, index=False)


def close_trade(trade_idx, exit_price, exit_date, exit_reason, notes="", path=JOURNAL_PATH):
    """Close an open trade by filling exit fields and computing pnl_pct."""
    df = load_journal(path)
    entry_price = float(df.iloc[trade_idx]["entry_price"])
    direction = df.iloc[trade_idx]["direction"]

    if direction == "long":
        pnl_pct = (exit_price - entry_price) / entry_price * 100
    else:
        pnl_pct = (entry_price - exit_price) / entry_price * 100

    df = df.astype(object)
    df.at[trade_idx, "exit_date"] = exit_date
    df.at[trade_idx, "exit_price"] = exit_price
    df.at[trade_idx, "exit_reason"] = exit_reason
    df.at[trade_idx, "pnl_pct"] = round(pnl_pct, 4)
    if notes:
        existing = str(df.at[trade_idx, "notes"])
        df.at[trade_idx, "notes"] = f"{existing}; {notes}" if existing and existing != "nan" else notes
    df.to_csv(path, index=False)


def get_open_trades(path=JOURNAL_PATH):
    """Return DataFrame of trades without exits."""
    df = load_journal(path)
    return df[df["exit_date"].isna() | (df["exit_date"] == "")]


def compute_review_stats(path=JOURNAL_PATH):
    """Compute review statistics from closed trades."""
    df = load_journal(path)
    closed = df[df["exit_price"].notna() & (df["exit_price"] != "")]
    if len(closed) == 0:
        return {"total": 0, "win_rate": 0, "avg_pnl": 0, "profit_factor": 0, "regimes": {}}

    pnls = closed["pnl_pct"].astype(float)
    winners = pnls[pnls > 0]
    losers = pnls[pnls <= 0]

    gross_profit = winners.sum() if len(winners) > 0 else 0
    gross_loss = abs(losers.sum()) if len(losers) > 0 else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    return {
        "total": len(closed),
        "win_rate": len(winners) / len(closed) * 100,
        "avg_pnl": pnls.mean(),
        "profit_factor": pf,
        "regimes": closed["regime"].value_counts().to_dict() if "regime" in closed.columns else {},
    }


def interactive_log():
    """Interactive prompt to log a trade entry or exit."""
    open_trades = get_open_trades()

    print("\n  (1) New entry")
    print("  (2) Close existing trade")

    if len(open_trades) == 0:
        print("  [No open trades — defaulting to new entry]")
        choice = "1"
    else:
        choice = input("\n  Choice [1/2]: ").strip()

    if choice == "2":
        print(f"\n  Open trades:")
        for i, (idx, row) in enumerate(open_trades.iterrows()):
            print(f"    {i+1}. [{idx}] {row['date']} {row['ticker']} {row['direction']} "
                  f"@ ${row['entry_price']}")

        pick = int(input("  Close which trade? [number]: ").strip()) - 1
        trade_idx = open_trades.index[pick]

        exit_price = float(input("  Exit price: $").strip())
        print("  Exit reason: target_full / stop / time / discretionary")
        exit_reason = input("  Reason: ").strip()
        exit_date = input("  Exit date [YYYY-MM-DD, blank=today]: ").strip()
        if not exit_date:
            exit_date = pd.Timestamp.now().strftime("%Y-%m-%d")
        notes = input("  Notes (optional): ").strip()

        close_trade(trade_idx, exit_price, exit_date, exit_reason, notes)
        print(f"\n  Trade closed.")
    else:
        ticker = input("  Ticker: ").strip().upper()
        direction = input("  Direction [long/short]: ").strip().lower()
        entry_price = float(input("  Entry price: $").strip())
        size = float(input("  Position size ($): ").strip())
        notes = input("  Notes (optional): ").strip()

        # Pre-fill levels from current data
        try:
            from atr_swing_backtest import prepare_data
            from breadth import load_breadth_data

            result = prepare_data(ticker)
            if result:
                df, _ = result
                row = df.iloc[-1]
                trigger = float(row["Long_Trigger"] if direction == "long" else row["Short_Trigger"])
                mid = float(row["Mid_Long"] if direction == "long" else row["Mid_Short"])
                full = float(row["Full_Long"] if direction == "long" else row["Full_Short"])
                stop = float(row["Central_Pivot"])
            else:
                trigger = mid = full = stop = 0.0

            breadth_df = load_breadth_data("breadth_data")
            brow = breadth_df.iloc[-1]
            regime = brow["regime"]
            breadth_trend = brow["breadth_trend"]
            size_mult = 0.5 if breadth_trend in {"DETERIORATING", "DETERIORATING_FAST"} else 1.0
        except Exception:
            trigger = mid = full = stop = 0.0
            regime = "UNKNOWN"
            breadth_trend = "UNKNOWN"
            size_mult = 1.0

        entry = {
            "date": pd.Timestamp.now().strftime("%Y-%m-%d"),
            "ticker": ticker, "direction": direction,
            "entry_price": entry_price, "size": size, "size_mult": size_mult,
            "trigger_level": trigger, "mid_target": mid,
            "full_target": full, "stop_level": stop,
            "regime": regime, "breadth_trend": breadth_trend,
            "notes": notes,
        }
        add_entry(entry)
        print(f"\n  Entry logged: {ticker} {direction} @ ${entry_price}")
        print(f"  Regime: {regime} | Trend: {breadth_trend} | Size mult: {size_mult}")


def print_review():
    """Print journal review stats."""
    stats = compute_review_stats()
    open_trades = get_open_trades()

    print(f"\n{'='*60}")
    print(f"  TRADE JOURNAL REVIEW")
    print(f"{'='*60}")

    if stats["total"] == 0:
        print("  No closed trades yet.")
    else:
        print(f"  Closed trades:    {stats['total']}")
        print(f"  Win rate:         {stats['win_rate']:.1f}%")
        print(f"  Avg P&L:          {stats['avg_pnl']:+.2f}%")
        pf_str = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "inf"
        print(f"  Profit factor:    {pf_str}")
        print(f"\n  Backtest expects: {BACKTEST_WR}% WR, +{BACKTEST_AVG_PNL:.2f}% avg")

        if stats["total"] < 20:
            print(f"  [!] {stats['total']} trades — too few to draw conclusions")

        if stats.get("regimes"):
            print(f"\n  Regime distribution:")
            for regime, count in sorted(stats["regimes"].items(), key=lambda x: -x[1]):
                print(f"    {regime:>20s}: {count}")

    if len(open_trades) > 0:
        print(f"\n  Open trades ({len(open_trades)}):")
        for _, row in open_trades.iterrows():
            print(f"    {row['date']} {row['ticker']} {row['direction']} @ ${row['entry_price']}")

    print()


def main():
    if len(sys.argv) < 2:
        print("Usage: python journal.py [log|review]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "log":
        interactive_log()
    elif cmd == "review":
        print_review()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python journal.py [log|review]")
        sys.exit(1)


if __name__ == "__main__":
    main()
