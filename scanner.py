# scanner.py
"""
Daily scanner: checks ATR swing trade setups after market close.

Usage:
    python scanner.py              # today's scan
    python scanner.py --fetch      # pull latest breadth CSV, then scan
    python scanner.py --date 2024-03-15  # historical replay
"""

import argparse
import pandas as pd
import os
import urllib.request

from atr_swing_backtest import TICKERS, prepare_data, check_entry_conditions
from breadth import load_breadth_data
from compliance import REGIME_RULES, BASE_CONTRACTS, STRUCTURE_NAMES, print_regime_checklist

# Google Sheets export URLs for Pradeep's market monitor data.
# Key: year, Value: gviz CSV export URL.
# The spreadsheet ID below is the same workbook; each year is a separate sheet.
BREADTH_SHEETS = {
    2026: "https://docs.google.com/spreadsheets/d/0Am_cU8NLIU20dEhiQnVHN3Nnc3B1S3J6eGhKZFo0N3c/gviz/tq?tqx=out:csv",
}
BREADTH_DIR = "breadth_data"


def fetch_breadth(years=None):
    """Download latest breadth CSVs from Google Sheets.

    Args:
        years: List of years to fetch, or None for all configured years.
    """
    os.makedirs(BREADTH_DIR, exist_ok=True)
    targets = years or list(BREADTH_SHEETS.keys())
    for year in targets:
        url = BREADTH_SHEETS.get(year)
        if url is None:
            print(f"  No URL configured for {year}, skipping")
            continue
        dest = os.path.join(BREADTH_DIR, f"mm_{year}.csv")
        print(f"  Fetching {year} breadth data...")
        try:
            urllib.request.urlretrieve(url, dest)
            # Quick sanity check
            df = pd.read_csv(dest)
            print(f"  Saved {dest} ({len(df)} rows, latest: {df.iloc[0, 0]})")
        except Exception as e:
            print(f"  ERROR fetching {year}: {e}")


LONG_CONDS = ["squeeze", "momentum_long", "ema_bull", "long_crossover", "volume", "above_macro"]
SHORT_CONDS = ["squeeze", "momentum_short", "ema_bear", "short_crossover", "volume", "below_macro"]
EARNINGS_CACHE_DIR = os.path.join("breadth_data", "earnings_cache")


def classify_ticker(ticker, conds):
    """Classify a ticker into TRIGGERED/NEAR/QUIET based on conditions."""
    long_score = sum(1 for c in LONG_CONDS if conds[c])
    short_score = sum(1 for c in SHORT_CONDS if conds[c])

    if long_score >= short_score:
        best_dir = "long"
        best_score = long_score
        best_conds = LONG_CONDS
    else:
        best_dir = "short"
        best_score = short_score
        best_conds = SHORT_CONDS

    missing = [c for c in best_conds if not conds[c]]

    if best_score == 6:
        bucket = "TRIGGERED"
    elif best_score >= 4:
        bucket = "NEAR"
    else:
        bucket = "QUIET"

    return {
        "ticker": ticker,
        "bucket": bucket,
        "direction": best_dir,
        "score": best_score,
        "missing": missing,
        "conds": conds,
    }


def get_next_earnings(ticker, scan_date):
    """Read earnings cache to find next earnings date after scan_date."""
    cache_path = os.path.join(EARNINGS_CACHE_DIR, f"{ticker}_earnings.csv")
    if not os.path.exists(cache_path):
        return None

    dates = pd.read_csv(cache_path, parse_dates=["date"])["date"].tolist()
    scan_ts = pd.Timestamp(scan_date)
    if scan_ts.tzinfo is not None:
        scan_ts = scan_ts.tz_convert(None)
    scan_ts = scan_ts.normalize()

    def _to_naive(d):
        ts = pd.Timestamp(d)
        if ts.tzinfo is not None:
            ts = ts.tz_convert(None)
        return ts.normalize()

    future = [d for d in dates if _to_naive(d) >= scan_ts]
    if not future:
        return None
    return min(future)


def _days_until(scan_ts, earnings_date):
    """Compute calendar days between scan date and earnings, handling tz."""
    e = pd.Timestamp(earnings_date)
    if e.tzinfo is not None:
        e = e.tz_convert(None)
    s = pd.Timestamp(scan_ts)
    if s.tzinfo is not None:
        s = s.tz_convert(None)
    return (e.normalize() - s.normalize()).days


def print_scan(results, breadth_df, scan_date):
    """Print the scanner output."""
    scan_ts = pd.Timestamp(scan_date)

    # Get breadth for scan date
    mask = breadth_df.index <= scan_ts
    if mask.any():
        brow = breadth_df.loc[mask].iloc[-1]
        regime = brow["regime"]
        score = brow["breadth_score"]
        trend = brow["breadth_trend"]
        r10 = brow["ratio10"]
        bias = brow["ratio10_bias"]
    else:
        regime = "UNKNOWN"
        score = 0
        trend = "UNKNOWN"
        r10 = 0
        bias = "unknown"

    rules = REGIME_RULES.get(regime, REGIME_RULES["UNKNOWN"])
    sizing = rules["label"]

    print(f"\n{'='*70}")
    print(f"  ATR SWING SCANNER — {scan_ts.strftime('%Y-%m-%d')}")
    print(f"{'='*70}")

    # Group by bucket
    triggered = [r for r in results if r["bucket"] == "TRIGGERED"]
    near = [r for r in results if r["bucket"] == "NEAR"]
    quiet = [r for r in results if r["bucket"] == "QUIET"]

    if triggered:
        print(f"\n  TRIGGERED ({len(triggered)}):")
        print(f"  {'-'*66}")
        for r in triggered:
            c = r["conds"]
            d = r["direction"]
            trigger = c["long_trigger"] if d == "long" else c["short_trigger"]
            mid = c["mid_long"] if d == "long" else c["mid_short"]
            full = c["full_long"] if d == "long" else c["full_short"]
            earnings = get_next_earnings(r["ticker"], scan_date)
            earn_str = ""
            if earnings:
                days = _days_until(scan_ts, earnings)
                if days <= 3:
                    earn_str = f" ⚠ EARNINGS IN {days}d"
                else:
                    earn_str = f" (earn: {days}d)"

            print(f"  {r['ticker']:>6s}  {d.upper():>5s}  entry: ${trigger:.2f}  "
                  f"mid: ${mid:.2f}  full: ${full:.2f}  "
                  f"stop: ${c['central_pivot']:.2f}  ATR: ${c['atr']:.2f}{earn_str}")
    else:
        print(f"\n  TRIGGERED: None")

    if near:
        print(f"\n  NEAR ({len(near)}):")
        print(f"  {'-'*66}")
        for r in near:
            c = r["conds"]
            d = r["direction"]
            trigger = c["long_trigger"] if d == "long" else c["short_trigger"]
            dist = abs(c["close"] - trigger)
            missing_str = ", ".join(r["missing"])
            earnings = get_next_earnings(r["ticker"], scan_date)
            earn_str = ""
            if earnings:
                days = _days_until(scan_ts, earnings)
                if days <= 3:
                    earn_str = f" ⚠ EARNINGS IN {days}d"

            print(f"  {r['ticker']:>6s}  {d.upper():>5s}  {r['score']}/6  "
                  f"${dist:.2f} from trigger  missing: {missing_str}{earn_str}")

    if quiet:
        print(f"\n  QUIET ({len(quiet)}):")
        print(f"  {'-'*66}")
        for r in quiet:
            c = r["conds"]
            print(f"  {r['ticker']:>6s}  levels: "
                  f"short ${c['full_short']:.2f} / ${c['short_trigger']:.2f} | "
                  f"pivot ${c['central_pivot']:.2f} | "
                  f"${c['long_trigger']:.2f} / ${c['full_long']:.2f} long")

    print_regime_checklist(regime, score, trend, r10, bias)


def main():
    parser = argparse.ArgumentParser(description="ATR Swing Scanner")
    parser.add_argument("--date", type=str, default=None,
                        help="Scan date (YYYY-MM-DD). Defaults to most recent trading day.")
    parser.add_argument("--fetch", action="store_true",
                        help="Pull latest breadth CSV from Google Sheets before scanning.")
    args = parser.parse_args()

    if args.fetch:
        print("Fetching breadth data...")
        fetch_breadth()

    print("Loading breadth data...")
    breadth_df = load_breadth_data("breadth_data")

    results = []
    scan_date = None
    for ticker in TICKERS:
        result = prepare_data(ticker)
        if result is None:
            continue
        df, _ = result

        if args.date:
            target = pd.Timestamp(args.date)
            valid = df.index[df.index <= target]
            if len(valid) < 2:
                print(f"  {ticker}: no data for {args.date}")
                continue
            idx = df.index.get_loc(valid[-1])
        else:
            idx = len(df) - 1

        if idx < 1:
            continue

        if scan_date is None:
            scan_date = df.index[idx]
        conds = check_entry_conditions(df, idx)
        results.append(classify_ticker(ticker, conds))

    if results and scan_date is not None:
        print_scan(results, breadth_df, scan_date)


if __name__ == "__main__":
    main()
