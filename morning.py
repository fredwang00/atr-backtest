# morning.py
"""
Pre-market morning plan for 0DTE ATR credit spread strategy.

Shows readiness, VIX pivot, SPY/QQQ ATR levels, and regime checklist.

Usage:
    python morning.py                     # today's plan
    python morning.py --fetch             # pull latest breadth CSV first
    python morning.py --date 2026-03-19   # historical replay
"""

import argparse
import os

import pandas as pd
import yaml

from data_loaders import download_ohlcv
from indicators import compute_indicators, DAILY_CONFIG
from breadth import load_breadth_data
from compliance import print_regime_checklist

CLEARWATER_DIR = "/Users/fwang/Documents/clearwater/daily"


def compute_vix_pivot(vix_close):
    """Round VIX close to nearest 0.5 for pivot level."""
    return round(vix_close * 2) / 2


def load_readiness(filepath):
    """Parse clearwater daily journal for readiness data.

    Args:
        filepath: Path to a YYYY-MM-DD.md file with YAML frontmatter.

    Returns:
        Dict with biometric keys (sleep_score, recovery, hrv, etc.),
        plus 'status' (OK/WARNING/NO_TRADING) and 'warnings' list.
        Returns None if file doesn't exist.
    """
    if not os.path.exists(filepath):
        return None

    with open(filepath) as f:
        content = f.read()

    # Parse YAML frontmatter between --- markers
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    frontmatter = yaml.safe_load(parts[1])
    if not frontmatter:
        return None

    data = {k: v for k, v in frontmatter.items()}
    warnings = []

    # Sleep rules (take priority)
    sleep = data.get("sleep_score")
    if sleep is not None:
        if sleep < 70:
            warnings.append("NO TRADING — sleep critically low")
        elif sleep < 78:
            warnings.append("Poor sleep — consider sitting out or reducing size")

    # Recovery rule
    recovery = data.get("recovery")
    if recovery is not None and recovery < 33:
        warnings.append("Low recovery — reduce size")

    # Determine status
    if any("NO TRADING" in w for w in warnings):
        data["status"] = "NO_TRADING"
    elif warnings:
        data["status"] = "WARNING"
    else:
        data["status"] = "OK"
    data["warnings"] = warnings

    return data


def _get_breadth_for_date(breadth_df, scan_ts):
    """Get breadth data for a given date, matching scanner pattern."""
    mask = breadth_df.index <= scan_ts
    if mask.any():
        brow = breadth_df.loc[mask].iloc[-1]
        return {
            "regime": brow["regime"],
            "score": brow["breadth_score"],
            "trend": brow["breadth_trend"],
            "r10": brow["ratio10"],
            "bias": brow["ratio10_bias"],
        }
    return {
        "regime": "UNKNOWN", "score": 0, "trend": "UNKNOWN",
        "r10": 0, "bias": "unknown",
    }


def _get_levels_for_date(df, target_date=None):
    """Get ATR levels row, optionally filtered to a date."""
    if target_date is not None:
        target = pd.Timestamp(target_date)
        valid = df.index[df.index <= target]
        if len(valid) < 2:
            return None
        return df.loc[valid[-1]]
    return df.iloc[-1]


def print_morning_plan(plan_date, readiness, vix_close, vix_pivot,
                       spy_levels, qqq_levels, breadth):
    """Print the full morning plan output."""
    print(f"\n{'='*70}")
    print(f"  MORNING PLAN — {plan_date}")
    print(f"{'='*70}")

    # Readiness
    print(f"\n  READINESS")
    print(f"  {'-'*66}")
    if readiness is None:
        print(f"    No readiness data for today")
    else:
        parts = []
        if "sleep_score" in readiness:
            parts.append(f"Sleep: {readiness['sleep_score']}")
        if "recovery" in readiness:
            parts.append(f"Recovery: {readiness['recovery']}")
        if "hrv" in readiness:
            parts.append(f"HRV: {readiness['hrv']}")
        if parts:
            print(f"    {' | '.join(parts)}")
        status = readiness["status"]
        if status == "NO_TRADING":
            print(f"    >>> NO TRADING — sleep critically low <<<")
        elif status == "WARNING":
            for w in readiness["warnings"]:
                print(f"    WARNING: {w}")
        else:
            print(f"    Status: OK")

    # VIX Pivot
    print(f"\n  VIX PIVOT")
    print(f"  {'-'*66}")
    if vix_close is not None:
        print(f"    VIX close:  {vix_close:.2f}   Pivot: {vix_pivot:.1f}")
        print(f"    Rule:       Above {vix_pivot:.1f} = bearish | Below {vix_pivot:.1f} = bullish")
    else:
        print(f"    VIX data unavailable")

    # ATR Levels
    for ticker, levels in [("SPY", spy_levels), ("QQQ", qqq_levels)]:
        print(f"\n  {ticker} ATR LEVELS")
        print(f"  {'-'*66}")
        if levels is not None:
            print(f"    +1 ATR:     ${levels['Full_Long']:.2f}     "
                  f"Call trigger: ${levels['Long_Trigger']:.2f}")
            print(f"    Pivot:      ${levels['Central_Pivot']:.2f}     (prev close)")
            print(f"    Put trigger: ${levels['Short_Trigger']:.2f}    "
                  f"-1 ATR: ${levels['Full_Short']:.2f}")
        else:
            print(f"    {ticker} data unavailable")

    # Regime & Checklist
    print_regime_checklist(
        breadth["regime"], breadth["score"], breadth["trend"],
        breadth["r10"], breadth["bias"],
    )


def main():
    parser = argparse.ArgumentParser(description="Pre-market morning plan")
    parser.add_argument("--date", type=str, default=None,
                        help="Plan date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--fetch", action="store_true",
                        help="Pull latest breadth CSV before running.")
    args = parser.parse_args()

    if args.fetch:
        from scanner import fetch_breadth
        print("Fetching breadth data...")
        fetch_breadth()

    plan_date = args.date or pd.Timestamp.now().strftime("%Y-%m-%d")

    # Readiness
    readiness_path = os.path.join(CLEARWATER_DIR, f"{plan_date}.md")
    readiness = load_readiness(readiness_path)

    # VIX
    vix_close = None
    vix_pivot = None
    vix_df = download_ohlcv("^VIX")
    if vix_df is not None:
        vix_row = _get_levels_for_date(vix_df, args.date)
        if vix_row is not None:
            vix_close = float(vix_row["Close"])
            vix_pivot = compute_vix_pivot(vix_close)

    # SPY and QQQ levels
    spy_levels = None
    qqq_levels = None
    for ticker, target in [("SPY", "spy_levels"), ("QQQ", "qqq_levels")]:
        result_df = download_ohlcv(ticker)
        if result_df is not None:
            df = compute_indicators(result_df, DAILY_CONFIG)
            row = _get_levels_for_date(df, args.date)
            if target == "spy_levels":
                spy_levels = row
            else:
                qqq_levels = row

    # Breadth
    breadth_df = load_breadth_data("breadth_data")
    scan_ts = pd.Timestamp(plan_date)
    breadth = _get_breadth_for_date(breadth_df, scan_ts)

    print_morning_plan(plan_date, readiness, vix_close, vix_pivot,
                       spy_levels, qqq_levels, breadth)


if __name__ == "__main__":
    main()
