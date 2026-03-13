"""
Stockbee Market Monitor breadth data parser and regime classifier.

Parses Pradeep Bonde's daily breadth CSVs and computes:
- Market regime (EXTREME_BEARISH through EXTREME_BULLISH)
- Breadth health composite score
- Simple ratio10 directional bias
"""

import pandas as pd
import numpy as np
import os
import glob


BREADTH_COLUMNS = [
    "up4", "down4", "ratio5", "ratio10",
    "quarterUp25", "quarterDown25",
    "monthUp25", "monthDown25", "monthUp50", "monthDown50",
    "up13_34", "down13_34",
    "universe", "t2108",
]


def parse_breadth_csv(filepath):
    """Parse a single year's breadth CSV into a DataFrame."""
    df = pd.read_csv(filepath, dtype=str)

    date_col = df.columns[0]
    rows = []

    for _, raw_row in df.iterrows():
        date_str = str(raw_row[date_col]).strip().strip('"')
        if not date_str or date_str.lower() == "nan":
            continue

        try:
            date = pd.to_datetime(date_str, format="mixed")
        except (ValueError, TypeError):
            continue

        nums = []
        for val in raw_row.iloc[1:]:
            val_str = str(val).strip().strip('"')
            if not val_str or val_str.lower() == "nan":
                continue
            val_str = val_str.replace(",", "")
            try:
                nums.append(float(val_str))
            except ValueError:
                continue

        if len(nums) < len(BREADTH_COLUMNS):
            continue

        row_dict = {"date": date}
        for j, col_name in enumerate(BREADTH_COLUMNS):
            row_dict[col_name] = nums[j]
        rows.append(row_dict)

    result = pd.DataFrame(rows)
    result = result.set_index("date").sort_index()
    return result


def get_regime(df, idx):
    """
    Classify market regime. Exact port of getRegime() from
    market-monitor/app/src/App.tsx. Priority-ordered, first match wins.
    """
    row = df.iloc[idx]
    qUp = row["quarterUp25"]
    qDn = row["quarterDown25"]
    r10 = row["ratio10"]
    r5 = row["ratio5"]
    t = row["t2108"]
    d4 = row["down4"]
    u4 = row["up4"]

    # 1. EXTREME_BEARISH
    if qUp < 300 or t < 20:
        return "EXTREME_BEARISH"

    # 2. BEARISH — ratio collapse
    if r10 < 0.5 or r5 < 0.4:
        return "BEARISH"

    # 3. BEARISH — quarterly inversion with weak ratio
    if qDn > qUp and r10 < 1.2:
        return "BEARISH"

    # 4-6 require 5-day lookback
    recent_net_neg = 0
    recent_big_down = 0
    if idx >= 4:
        for j in range(idx - 4, idx + 1):
            r = df.iloc[j]
            if r["down4"] > r["up4"]:
                recent_net_neg += 1
            if r["down4"] > 350:
                recent_big_down += 1

    # 4. BEARISH — persistent heavy selling
    if recent_big_down >= 3:
        return "BEARISH"

    # 5. CAUTIOUS — quarterly spread narrowing
    if qDn > qUp * 0.85 and r10 < 1.5:
        return "CAUTIOUS"

    # 6. CAUTIOUS — recent net-negative clustering
    if recent_net_neg >= 3 and r10 < 1.3:
        return "CAUTIOUS"

    # 7. EXTREME_BULLISH
    if (t > 85 and r10 > 2.5) or (r10 > 3 and r5 > 3):
        return "EXTREME_BULLISH"

    # 8. BULLISH
    if (r10 > 2 and qUp > qDn * 1.3) or (r10 > 1.5 and qUp > 1000 and qUp > qDn * 1.1):
        return "BULLISH"

    # 9. Default
    return "NEUTRAL"


def detect_trend(df, idx, field, lookback):
    """
    Check if a field is trending up or down over the lookback period.
    Returns 1 (up), -1 (down), or 0 (flat).
    Threshold: 70% of days must be directionally consistent (4+ of 5).
    """
    if idx < lookback:
        return 0
    vals = [df.iloc[i][field] for i in range(idx - lookback, idx + 1)]
    up = 0
    dn = 0
    for i in range(1, len(vals)):
        if vals[i] > vals[i - 1]:
            up += 1
        elif vals[i] < vals[i - 1]:
            dn += 1
    if up >= lookback * 0.7:
        return 1
    if dn >= lookback * 0.7:
        return -1
    return 0


def compute_breadth_health(df, idx):
    """
    Compute breadth health composite score. Exact port of
    computeBreadthHealth() from market-monitor App.tsx.
    Returns (score, trend_label).
    """
    if idx < 10:
        return 0, "STEADY"

    row = df.iloc[idx]
    score = 0

    # ratio10 trend
    r10_trend = detect_trend(df, idx, "ratio10", 5)
    if r10_trend == 1:
        score += 2
    elif r10_trend == -1:
        score -= 2

    # t2108 trend
    t_trend = detect_trend(df, idx, "t2108", 5)
    if t_trend == 1:
        score += 1
    elif t_trend == -1:
        score -= 1

    # quarterUp25 trend
    q_trend = detect_trend(df, idx, "quarterUp25", 5)
    if q_trend == 1:
        score += 1
    elif q_trend == -1:
        score -= 2

    # Quarterly spread
    q_spread = row["quarterUp25"] - row["quarterDown25"]
    if q_spread > 300:
        score += 1
    elif q_spread < 0:
        score -= 2

    # Last 5 days analysis
    start = max(0, idx - 4)
    last5 = [df.iloc[i] for i in range(start, idx + 1)]

    big_down_count = sum(1 for d in last5 if d["down4"] > 300)
    if big_down_count >= 3:
        score -= 3
    elif big_down_count >= 2:
        score -= 1

    big_up_count = sum(1 for d in last5 if d["up4"] > 300)
    if big_up_count >= 4:
        score += 2

    red_days = sum(1 for d in last5 if d["down4"] > d["up4"])
    if red_days >= 4:
        score -= 2
    elif red_days <= 1 and len(last5) >= 4:
        score += 1

    # Monthly divergence
    if row["monthDown25"] > row["monthUp25"] * 1.5 and row["monthDown25"] > 100:
        score -= 1

    # Froth
    if row["monthUp50"] > 30:
        score -= 1

    # Down 13/34 expansion
    d1334_trend = detect_trend(df, idx, "down13_34", 5)
    if d1334_trend == 1:
        score -= 1

    # Map score to trend label
    if score >= 4:
        trend = "IMPROVING"
    elif score >= 2:
        trend = "SLIGHTLY_IMPROVING"
    elif score >= -1:
        trend = "STEADY"
    elif score >= -3:
        trend = "SLIGHTLY_DETERIORATING"
    elif score >= -5:
        trend = "DETERIORATING"
    else:
        trend = "DETERIORATING_FAST"

    return score, trend


def ratio10_bias(row):
    """Simple directional bias from ratio10."""
    r10 = row["ratio10"]
    if r10 > 1.5:
        return "long"
    elif r10 < 0.8:
        return "short"
    return "neutral"


def load_breadth_data(data_dir="breadth_data"):
    """Load all year CSVs, combine, and compute signals."""
    files = sorted(glob.glob(os.path.join(data_dir, "mm_*.csv")))
    if not files:
        raise FileNotFoundError(f"No breadth CSVs found in {data_dir}")

    frames = [parse_breadth_csv(f) for f in files]
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="first")]

    regimes = []
    scores = []
    trends = []
    biases = []
    for idx in range(len(df)):
        regimes.append(get_regime(df, idx))
        score, trend = compute_breadth_health(df, idx)
        scores.append(score)
        trends.append(trend)
        biases.append(ratio10_bias(df.iloc[idx]))

    df["regime"] = regimes
    df["breadth_score"] = scores
    df["breadth_trend"] = trends
    df["ratio10_bias"] = biases

    return df
