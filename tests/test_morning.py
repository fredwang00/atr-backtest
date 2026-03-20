import os
import tempfile
from morning import compute_vix_pivot, load_readiness


def test_vix_pivot_rounds_down():
    """17.23 rounds to 17.0."""
    assert compute_vix_pivot(17.23) == 17.0


def test_vix_pivot_rounds_up():
    """17.38 rounds to 17.5."""
    assert compute_vix_pivot(17.38) == 17.5


def test_vix_pivot_exact_half():
    """17.5 stays 17.5."""
    assert compute_vix_pivot(17.5) == 17.5


def test_vix_pivot_exact_whole():
    """17.0 stays 17.0."""
    assert compute_vix_pivot(17.0) == 17.0


def test_readiness_ok():
    """Good sleep and recovery returns OK status."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 85\nrecovery: 60\nhrv: 40\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["sleep_score"] == 85
            assert data["recovery"] == 60
            assert data["status"] == "OK"
            assert data["warnings"] == []
        finally:
            os.unlink(f.name)


def test_readiness_no_trading():
    """Sleep below 70 returns NO_TRADING."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 65\nrecovery: 50\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["status"] == "NO_TRADING"
            assert any("sleep" in w.lower() for w in data["warnings"])
        finally:
            os.unlink(f.name)


def test_readiness_poor_sleep_warning():
    """Sleep 70-77 returns WARNING."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 73\nrecovery: 60\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["status"] == "WARNING"
            assert any("sleep" in w.lower() for w in data["warnings"])
        finally:
            os.unlink(f.name)


def test_readiness_low_recovery_warning():
    """Recovery below 33 returns WARNING."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 85\nrecovery: 25\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["status"] == "WARNING"
            assert any("recovery" in w.lower() for w in data["warnings"])
        finally:
            os.unlink(f.name)


def test_readiness_missing_key():
    """Missing recovery key skips that rule."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 85\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["status"] == "OK"
            assert "recovery" not in data
        finally:
            os.unlink(f.name)


def test_readiness_sleep_boundary_77_warns():
    """Sleep score 77 is in warning range (70-77 inclusive)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 77\nrecovery: 60\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["status"] == "WARNING"
        finally:
            os.unlink(f.name)


def test_readiness_sleep_boundary_78_ok():
    """Sleep score 78 is OK (above warning range)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ndate: 2026-03-20\nsleep_score: 78\nrecovery: 60\n---\n")
        f.flush()
        try:
            data = load_readiness(f.name)
            assert data["status"] == "OK"
        finally:
            os.unlink(f.name)


def test_readiness_file_not_found():
    """Missing file returns None."""
    assert load_readiness("/nonexistent/path.md") is None
