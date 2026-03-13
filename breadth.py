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
