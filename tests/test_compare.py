import subprocess


def test_compare_runs_without_error():
    """Integration test: compare.py produces output and exits cleanly."""
    result = subprocess.run(
        ["python", "compare.py"],
        capture_output=True, text=True, timeout=600,
        cwd="/Users/fwang/code/atr-backtest",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Baseline" in result.stdout
    assert "+Regime" in result.stdout
    assert "+Earnings" in result.stdout
    assert "Win Rate" in result.stdout or "win_rate" in result.stdout or "WR%" in result.stdout
    assert "Sharpe" in result.stdout or "sharpe" in result.stdout
