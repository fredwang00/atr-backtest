"""
Decision matrix rules for 0DTE ATR credit spread strategy.

Encodes regime-based trade rules from the decision matrix. Single source
of truth imported by scanner.py (pre-trade checklist) and journal.py
(entry-time compliance checking).
"""

BASE_CONTRACTS = 10

REGIME_RULES = {
    "EXTREME_BULLISH": {
        "allowed_structures": ["call_credit", "put_credit", "iron_condor"],
        "sizing": 0.75,
        "label": "0.75x — pullback risk",
        "notes": "Put spread further OTM or wider. Call side higher conviction.",
    },
    "BULLISH": {
        "allowed_structures": ["call_credit", "put_credit", "iron_condor"],
        "sizing": 1.0,
        "label": "FULL SIZE (1.0x)",
        "notes": "Best environment for premium selling. Target 50-75% of max credit.",
    },
    "NEUTRAL": {
        "allowed_structures": ["call_credit", "put_credit", "iron_condor"],
        "sizing": 0.75,
        "label": "0.75x — no strong edge",
        "notes": "Wider strikes (±1.25 ATR). Prob.OTM > 90% preferred.",
    },
    "CAUTIOUS": {
        "allowed_structures": ["call_credit"],
        "sizing": 0.5,
        "label": "HALF SIZE (0.5x) — call spreads only",
        "notes": "NO put spreads. Skip if no clean level.",
    },
    "BEARISH": {
        "allowed_structures": [],
        "sizing": 0.25,
        "label": "QUARTER SIZE (0.25x) or FLAT",
        "notes": "Cash is a position. Tiny call spread at +1.25 ATR only if trading.",
    },
    "EXTREME_BEARISH": {
        "allowed_structures": [],
        "sizing": 0.0,
        "label": "FLAT — reversal watch only",
        "notes": "Watch for VPA-confirmed reversal. Risk 1-2% on long calls only.",
    },
    "UNKNOWN": {
        "allowed_structures": ["call_credit"],
        "sizing": 0.5,
        "label": "HALF SIZE (0.5x) — call spreads only",
        "notes": "Unknown regime — defaulting to CAUTIOUS rules.",
    },
}

STRUCTURE_NAMES = {
    "call_credit": "Call credit spread",
    "put_credit": "Put credit spread",
    "iron_condor": "Iron condor",
}

VIOLATION_WRONG_STRUCTURE = "wrong_structure"
VIOLATION_OVERSIZED = "oversized"

_SPREAD_TYPE_MAP = {
    "call": "call_credit",
    "put": "put_credit",
}


def check_compliance(regime, spread_type=None, contracts=None, base_contracts=BASE_CONTRACTS):
    """Check a trade against regime rules from the decision matrix.

    Args:
        regime: Market regime string (e.g., "CAUTIOUS", "BULLISH").
        spread_type: Journal spread type ("call" or "put"), or None to skip structure check.
        contracts: Number of contracts in the trade, or None to skip sizing check.
        base_contracts: Base contract count (default BASE_CONTRACTS).

    Returns:
        List of (violation_type, message) tuples. Empty list = compliant.
        violation_type is VIOLATION_WRONG_STRUCTURE or VIOLATION_OVERSIZED.
    """
    rules = REGIME_RULES.get(regime, REGIME_RULES["UNKNOWN"])
    violations = []

    if spread_type is not None:
        mapped = _SPREAD_TYPE_MAP.get(spread_type, spread_type)
        if mapped not in rules["allowed_structures"]:
            allowed_names = [STRUCTURE_NAMES.get(s, s) for s in rules["allowed_structures"]]
            allowed_str = ", ".join(allowed_names) if allowed_names else "none (no premium selling)"
            violations.append((
                VIOLATION_WRONG_STRUCTURE,
                f"{spread_type} credit spread not allowed in "
                f"{regime} regime. Allowed: {allowed_str}.",
            ))

    if contracts is not None:
        max_contracts = int(base_contracts * rules["sizing"])
        if contracts > max_contracts:
            violations.append((
                VIOLATION_OVERSIZED,
                f"{contracts} contracts exceeds {rules['sizing']}x "
                f"sizing (max {max_contracts} of {base_contracts} base).",
            ))

    return violations
