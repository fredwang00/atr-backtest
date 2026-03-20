"""
Trade journal for ATR swing and credit spread pilot trades.

Usage:
    python journal.py log      # log a new entry or close a trade
    python journal.py review   # review stats vs backtest expectations
"""

import sys
import os
import pandas as pd

JOURNAL_PATH = "trades_journal.csv"
VALID_SETUP_GRADES = ["A", "B", "C", "D"]
JOURNAL_COLUMNS = [
    "date", "ticker", "direction", "entry_price", "size", "size_mult",
    "trigger_level", "mid_target", "full_target", "stop_level",
    "regime", "breadth_trend", "setup_grade", "compliance",
    "exit_date", "exit_price", "exit_reason",
    "pnl_pct", "pnl_dollars",
    "trade_type", "spread_type", "short_strike", "long_strike",
    "spread_width", "contracts", "credit",
    "notes",
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
    row["pnl_dollars"] = ""
    new_df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    new_df.to_csv(path, index=False)


def close_trade(trade_idx, exit_price, exit_date, exit_reason, notes="", path=JOURNAL_PATH):
    """Close an open trade by filling exit fields and computing P&L."""
    df = load_journal(path)
    row = df.loc[trade_idx]
    trade_type = str(row.get("trade_type", "")).strip()

    if trade_type == "credit_spread":
        credit = float(row["credit"])
        spread_width = float(row["spread_width"])
        contracts = int(float(row["contracts"]))
        max_risk = (spread_width - credit) * contracts * 100
        pnl_dollars = (credit - exit_price) * contracts * 100
        pnl_pct = (pnl_dollars / max_risk * 100) if max_risk > 0 else 0.0
    else:
        entry_price = float(row["entry_price"])
        direction = row["direction"]
        if direction == "long":
            pnl_pct = (exit_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * 100
        size = float(row["size"]) if pd.notna(row.get("size")) and str(row["size"]).strip() else 0
        pnl_dollars = pnl_pct / 100 * size

    df = df.astype(object)
    df.at[trade_idx, "exit_date"] = exit_date
    df.at[trade_idx, "exit_price"] = exit_price
    df.at[trade_idx, "exit_reason"] = exit_reason
    df.at[trade_idx, "pnl_pct"] = round(pnl_pct, 4)
    df.at[trade_idx, "pnl_dollars"] = round(pnl_dollars, 2)
    if notes:
        existing = str(df.at[trade_idx, "notes"])
        df.at[trade_idx, "notes"] = f"{existing}; {notes}" if existing and existing != "nan" else notes
    df.to_csv(path, index=False)


def get_open_trades(path=JOURNAL_PATH):
    """Return DataFrame of trades without exits."""
    df = load_journal(path)
    return df[df["exit_date"].isna() | (df["exit_date"] == "")]


def _group_stats(grp):
    """Compute win rate and avg P&L for a group of trades."""
    pnls = grp["pnl_pct"].astype(float)
    winners = pnls[pnls > 0]
    return {
        "total": len(grp),
        "win_rate": len(winners) / len(grp) * 100 if len(grp) > 0 else 0,
        "avg_pnl": pnls.mean(),
    }


def compute_review_stats(path=JOURNAL_PATH, trade_type=None, df=None):
    """Compute review statistics from closed trades.

    Args:
        path: Path to journal CSV.
        trade_type: Filter to "swing" or "credit_spread". None = all trades.
        df: Pre-loaded DataFrame. If None, reads from path.
    """
    if df is None:
        df = load_journal(path)
    closed = df[df["exit_price"].notna() & (df["exit_price"] != "")]

    if trade_type is not None and len(closed) > 0:
        if "trade_type" in closed.columns:
            tt = closed["trade_type"].fillna("").replace("", "swing")
        else:
            tt = pd.Series("swing", index=closed.index)
        closed = closed[tt == trade_type]

    if len(closed) == 0:
        return {"total": 0, "win_rate": 0, "avg_pnl": 0, "profit_factor": 0,
                "regimes": {}, "grade_stats": {}, "compliance_stats": {}}

    pnls = closed["pnl_pct"].astype(float)
    winners = pnls[pnls > 0]
    losers = pnls[pnls <= 0]

    gross_profit = winners.sum() if len(winners) > 0 else 0
    gross_loss = abs(losers.sum()) if len(losers) > 0 else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    result = {
        "total": len(closed),
        "win_rate": len(winners) / len(closed) * 100,
        "avg_pnl": pnls.mean(),
        "profit_factor": pf,
        "regimes": closed["regime"].value_counts().to_dict() if "regime" in closed.columns else {},
    }

    # Add dollar stats for credit spreads
    if trade_type == "credit_spread" and "pnl_dollars" in closed.columns:
        dollars = closed["pnl_dollars"].astype(float)
        result["avg_pnl_dollars"] = dollars.mean()
        result["total_pnl_dollars"] = dollars.sum()

    # Grade breakdown
    if "setup_grade" in closed.columns:
        grades = closed["setup_grade"].fillna("").replace("", pd.NA).dropna()
        grade_stats = {}
        for grade in grades.unique():
            grade_stats[grade] = _group_stats(closed[closed["setup_grade"] == grade])
        result["grade_stats"] = grade_stats
    else:
        result["grade_stats"] = {}

    # Compliance breakdown
    compliance_stats = {}
    if "compliance" in closed.columns:
        comp = closed["compliance"].fillna("").replace("", "unknown")
        for label in ["compliant", "violation", "unknown"]:
            if label == "violation":
                grp = closed[~comp.isin(["compliant", "unknown", ""])]
            else:
                grp = closed[comp == label]
            if len(grp) > 0:
                compliance_stats[label] = _group_stats(grp)
    result["compliance_stats"] = compliance_stats

    return result


def _prompt_setup_grade():
    """Prompt for setup quality grade (A-D)."""
    print("  Setup grade: A=textbook  B=minor deviation  C=marginal  D=forced")
    while True:
        grade = input("  Grade [A/B/C/D]: ").strip().upper()
        if grade in VALID_SETUP_GRADES:
            return grade
        print(f"  Invalid grade '{grade}'. Enter A, B, C, or D.")


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
            tt = str(row.get("trade_type", "")).strip()
            if tt == "credit_spread":
                side = "C" if row.get("spread_type") == "call" else "P"
                print(f"    {i+1}. [{idx}] {row['date']} {row['ticker']} "
                      f"{row['short_strike']}/{row['long_strike']}{side} "
                      f"x{int(float(row['contracts']))} @ ${row['credit']} credit")
            else:
                print(f"    {i+1}. [{idx}] {row['date']} {row['ticker']} {row['direction']} "
                      f"@ ${row['entry_price']}")

        pick = int(input("  Close which trade? [number]: ").strip()) - 1
        trade_idx = open_trades.index[pick]
        picked_row = open_trades.iloc[pick]
        is_cs = str(picked_row.get("trade_type", "")).strip() == "credit_spread"

        if is_cs:
            cs_reasons = ["expired_otm", "closed", "stop", "rolled"]
            print("  Exit reason: (1) expired_otm  (2) closed  (3) stop  (4) rolled")
            raw = input("  Reason [1-4]: ").strip()
            exit_reason = cs_reasons[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= 4 else raw
            if exit_reason == "expired_otm":
                exit_price = 0.0
            else:
                exit_price = float(input("  Debit paid per spread: $").strip())
        else:
            exit_price = float(input("  Exit price: $").strip())
            swing_reasons = ["target_full", "stop", "time", "discretionary"]
            print("  Exit reason: (1) target_full  (2) stop  (3) time  (4) discretionary")
            raw = input("  Reason [1-4]: ").strip()
            exit_reason = swing_reasons[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= 4 else raw

        exit_date = input("  Exit date [YYYY-MM-DD, blank=today]: ").strip()
        if not exit_date:
            exit_date = pd.Timestamp.now().strftime("%Y-%m-%d")
        notes = input("  Notes (optional): ").strip()

        close_trade(trade_idx, exit_price, exit_date, exit_reason, notes)
        print(f"\n  Trade closed.")
    else:
        print("\n  Trade type?")
        print("  (1) Swing")
        print("  (2) Credit spread")
        tt_choice = input("  Type [1/2]: ").strip()

        # Fetch breadth data once (used by both paths)
        try:
            from breadth import load_breadth_data
            breadth_df = load_breadth_data("breadth_data")
            brow = breadth_df.iloc[-1]
            regime = brow["regime"]
            breadth_trend = brow["breadth_trend"]
        except Exception as e:
            print(f"  [warning] Could not fetch breadth data: {e}")
            regime = "UNKNOWN"
            breadth_trend = "UNKNOWN"

        if tt_choice == "2":
            ticker = input("  Ticker: ").strip().upper()
            spread_type = input("  Spread type [call/put]: ").strip().lower()
            short_strike = float(input("  Short strike: ").strip())
            long_strike = float(input("  Long strike: ").strip())
            contracts = int(input("  Contracts: ").strip())
            credit = float(input("  Net credit per spread (after commissions): $").strip())

            spread_width = abs(long_strike - short_strike)
            if credit >= spread_width:
                print(f"\n  ERROR: Credit ${credit} >= spread width ${spread_width}.")
                print(f"  Enter the per-share option price (e.g., $0.087), not total dollars.")
                return

            setup_grade = _prompt_setup_grade()

            from compliance import check_compliance, REGIME_RULES
            rules = REGIME_RULES.get(regime, REGIME_RULES["UNKNOWN"])
            violations = check_compliance(regime, spread_type=spread_type, contracts=contracts)
            if violations:
                print()
                for vtype, msg in violations:
                    print(f"  ⚠ REGIME VIOLATION: {msg}")
                confirm = input("\n  Log anyway? [y/N]: ").strip().lower()
                if confirm != "y":
                    print("  Trade not logged.")
                    return
                compliance_str = "; ".join(vtype for vtype, _ in violations)
            else:
                compliance_str = "compliant"

            notes = input("  Notes (optional): ").strip()
            max_risk = (spread_width - credit) * contracts * 100

            entry = {
                "date": pd.Timestamp.now().strftime("%Y-%m-%d"),
                "ticker": ticker, "direction": "short",
                "trade_type": "credit_spread", "spread_type": spread_type,
                "short_strike": short_strike, "long_strike": long_strike,
                "spread_width": spread_width, "contracts": contracts,
                "credit": credit, "entry_price": credit,
                "size": max_risk, "size_mult": rules["sizing"],
                "regime": regime, "breadth_trend": breadth_trend,
                "setup_grade": setup_grade,
                "compliance": compliance_str,
                "notes": notes,
            }
            add_entry(entry)
            side = "C" if spread_type == "call" else "P"
            print(f"\n  Logged: {ticker} {short_strike}/{long_strike}{side} x{contracts} "
                  f"@ ${credit} credit (max risk: ${max_risk:.0f})")
            print(f"  Regime: {regime} | Trend: {breadth_trend}")
        else:
            # Existing swing flow
            ticker = input("  Ticker: ").strip().upper()
            direction = input("  Direction [long/short]: ").strip().lower()
            entry_price = float(input("  Entry price: $").strip())
            size = float(input("  Position size ($): ").strip())
            notes = input("  Notes (optional): ").strip()

            try:
                from atr_swing_backtest import prepare_data
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
            except Exception as e:
                print(f"  [warning] Could not fetch price data: {e}")
                trigger = mid = full = stop = 0.0

            setup_grade = _prompt_setup_grade()
            from compliance import REGIME_RULES
            size_mult = REGIME_RULES.get(regime, REGIME_RULES["UNKNOWN"])["sizing"]

            entry = {
                "date": pd.Timestamp.now().strftime("%Y-%m-%d"),
                "ticker": ticker, "direction": direction,
                "trade_type": "swing",
                "entry_price": entry_price, "size": size, "size_mult": size_mult,
                "trigger_level": trigger, "mid_target": mid,
                "full_target": full, "stop_level": stop,
                "regime": regime, "breadth_trend": breadth_trend,
                "setup_grade": setup_grade,
                "notes": notes,
            }
            add_entry(entry)
            print(f"\n  Entry logged: {ticker} {direction} @ ${entry_price}")
            print(f"  Regime: {regime} | Trend: {breadth_trend} | Size mult: {size_mult}")


def print_review():
    """Print journal review stats, split by trade type."""
    open_trades = get_open_trades()

    print(f"\n{'='*60}")
    print(f"  TRADE JOURNAL REVIEW")
    print(f"{'='*60}")

    journal_df = load_journal()
    swing_stats = compute_review_stats(df=journal_df, trade_type="swing")
    cs_stats = compute_review_stats(df=journal_df, trade_type="credit_spread")
    has_any = swing_stats["total"] > 0 or cs_stats["total"] > 0

    if not has_any:
        print("  No closed trades yet.")
    else:
        if swing_stats["total"] > 0:
            print(f"\n  SWING TRADES")
            print(f"  {'-'*56}")
            print(f"  Closed trades:    {swing_stats['total']}")
            print(f"  Win rate:         {swing_stats['win_rate']:.1f}%")
            print(f"  Avg P&L:          {swing_stats['avg_pnl']:+.2f}%")
            pf_str = f"{swing_stats['profit_factor']:.2f}" if swing_stats['profit_factor'] != float('inf') else "inf"
            print(f"  Profit factor:    {pf_str}")
            print(f"\n  Backtest expects: {BACKTEST_WR}% WR, +{BACKTEST_AVG_PNL:.2f}% avg")
            if swing_stats["total"] < 20:
                print(f"  [!] {swing_stats['total']} trades — too few to draw conclusions")

        if cs_stats["total"] > 0:
            print(f"\n  CREDIT SPREADS")
            print(f"  {'-'*56}")
            print(f"  Closed trades:    {cs_stats['total']}")
            print(f"  Win rate:         {cs_stats['win_rate']:.1f}%")
            print(f"  Avg P&L ($):      ${cs_stats.get('avg_pnl_dollars', 0):+.2f}/trade")
            print(f"  Avg RoR:          {cs_stats['avg_pnl']:+.2f}%/trade")
            print(f"  Total P&L:        ${cs_stats.get('total_pnl_dollars', 0):+.2f}")
            pf_str = f"{cs_stats['profit_factor']:.2f}" if cs_stats['profit_factor'] != float('inf') else "inf"
            print(f"  Profit factor:    {pf_str}")
            if cs_stats["total"] < 20:
                print(f"  [!] {cs_stats['total']} trades — too few to draw conclusions")

        # Regime distribution across all trades
        all_stats = compute_review_stats(df=journal_df)
        if all_stats.get("regimes"):
            print(f"\n  Regime distribution (all trades):")
            for regime, count in sorted(all_stats["regimes"].items(), key=lambda x: -x[1]):
                print(f"    {regime:>20s}: {count}")

        # Setup grade breakdown
        grade_stats = all_stats.get("grade_stats", {})
        if grade_stats:
            print(f"\n  Setup grade breakdown (all trades):")
            for grade in VALID_SETUP_GRADES:
                if grade in grade_stats:
                    gs = grade_stats[grade]
                    print(f"    {grade}: {gs['total']} trades, "
                          f"{gs['win_rate']:.0f}% WR, "
                          f"{gs['avg_pnl']:+.2f}% avg")

        # Compliance breakdown
        compliance_stats = all_stats.get("compliance_stats", {})
        compliant = compliance_stats.get("compliant", {})
        violation = compliance_stats.get("violation", {})
        if compliant or violation:
            total_scored = compliant.get("total", 0) + violation.get("total", 0)
            print(f"\n  Compliance:")
            if compliant:
                print(f"    Compliant:   {compliant['total']} trades, "
                      f"{compliant['win_rate']:.0f}% WR, "
                      f"{compliant['avg_pnl']:+.2f}% avg")
            if violation:
                print(f"    Violations:  {violation['total']} trades, "
                      f"{violation['win_rate']:.0f}% WR, "
                      f"{violation['avg_pnl']:+.2f}% avg")
            if total_scored > 0:
                rate = compliant.get("total", 0) / total_scored * 100
                print(f"    Compliance rate: {rate:.0f}%")

    if len(open_trades) > 0:
        print(f"\n  Open trades ({len(open_trades)}):")
        for _, row in open_trades.iterrows():
            tt = str(row.get("trade_type", "")).strip()
            if tt == "credit_spread":
                side = "C" if row.get("spread_type") == "call" else "P"
                print(f"    {row['date']} {row['ticker']} {row['short_strike']}/{row['long_strike']}{side} "
                      f"x{int(float(row['contracts']))} @ ${row['credit']} credit")
            else:
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
