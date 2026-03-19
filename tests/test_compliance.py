from compliance import REGIME_RULES, BASE_CONTRACTS, check_compliance


def test_all_regimes_covered():
    """REGIME_RULES covers all 7 possible regime values."""
    expected = {
        "EXTREME_BULLISH", "BULLISH", "NEUTRAL", "CAUTIOUS",
        "BEARISH", "EXTREME_BEARISH", "UNKNOWN",
    }
    assert set(REGIME_RULES.keys()) == expected


def test_each_regime_has_required_keys():
    """Every regime entry has allowed_structures, sizing, label, notes."""
    for regime, rules in REGIME_RULES.items():
        assert "allowed_structures" in rules, f"{regime} missing allowed_structures"
        assert "sizing" in rules, f"{regime} missing sizing"
        assert "label" in rules, f"{regime} missing label"
        assert "notes" in rules, f"{regime} missing notes"


def test_base_contracts_default():
    assert BASE_CONTRACTS == 10


def test_compliant_call_spread_in_cautious():
    """Call spread with correct sizing in CAUTIOUS → no violations."""
    violations = check_compliance("CAUTIOUS", spread_type="call", contracts=5)
    assert violations == []


def test_put_spread_blocked_in_cautious():
    """Put spread in CAUTIOUS → violation."""
    violations = check_compliance("CAUTIOUS", spread_type="put", contracts=5)
    assert len(violations) == 1
    assert "put" in violations[0].lower() or "structure" in violations[0].lower()


def test_oversized_in_cautious():
    """10 contracts when max is 5 (0.5x of 10) → violation."""
    violations = check_compliance("CAUTIOUS", spread_type="call", contracts=10)
    assert len(violations) == 1
    assert "size" in violations[0].lower() or "contract" in violations[0].lower()


def test_put_spread_and_oversized_in_cautious():
    """Wrong structure AND oversized → two violations."""
    violations = check_compliance("CAUTIOUS", spread_type="put", contracts=10)
    assert len(violations) == 2


def test_any_spread_blocked_in_bearish():
    """No premium selling in BEARISH regime."""
    assert len(check_compliance("BEARISH", spread_type="call", contracts=1)) >= 1
    assert len(check_compliance("BEARISH", spread_type="put", contracts=1)) >= 1


def test_iron_condor_allowed_in_bullish():
    """Both sides allowed in BULLISH, full size."""
    assert check_compliance("BULLISH", spread_type="call", contracts=10) == []
    assert check_compliance("BULLISH", spread_type="put", contracts=10) == []


def test_unknown_regime_uses_cautious_rules():
    """UNKNOWN falls back to CAUTIOUS rules."""
    assert check_compliance("UNKNOWN", spread_type="put", contracts=5) != []
    assert check_compliance("UNKNOWN", spread_type="call", contracts=5) == []


def test_custom_base_contracts():
    """base_contracts override works."""
    # 0.5x of 20 = 10, so 10 contracts is fine
    violations = check_compliance("CAUTIOUS", spread_type="call", contracts=10, base_contracts=20)
    assert violations == []


def test_no_spread_type_skips_structure_check():
    """If spread_type is None, only sizing is checked."""
    violations = check_compliance("CAUTIOUS", spread_type=None, contracts=5)
    assert violations == []


def test_extreme_bearish_any_contracts_oversized():
    """EXTREME_BEARISH has 0.0 sizing — any contracts should flag oversized."""
    violations = check_compliance("EXTREME_BEARISH", spread_type="call", contracts=1)
    assert any("size" in v.lower() or "oversized" in v.lower() for v in violations)


def test_unrecognized_regime_falls_back_to_unknown():
    """Completely unrecognized regime string uses UNKNOWN (CAUTIOUS) rules."""
    violations = check_compliance("FOOBAR", spread_type="put", contracts=5)
    assert len(violations) >= 1
