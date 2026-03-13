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
