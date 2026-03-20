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
