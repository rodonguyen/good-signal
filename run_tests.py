"""
Quick test runner for spike detection feature.
Run this to validate ZScoreIndicator and SpikeDetectionStrategy.
"""

import subprocess
import sys
from pathlib import Path


def run_tests(verbose=True, coverage=False):
    """Run spike detection tests."""

    # Test files
    test_files = ["tests/test_zscore_indicator.py", "tests/test_spike_detection_strategy.py"]

    # Build pytest command
    cmd = [sys.executable, "-m", "pytest"]
    cmd.extend(test_files)

    if verbose:
        cmd.append("-v")

    if coverage:
        cmd.extend(["--cov=src/indicators", "--cov=src/strategies", "--cov-report=term-missing", "--cov-report=html"])

    # Run tests
    print("Running spike detection tests...")
    print(f"Command: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(cmd, check=True)
        print("\n✅ All tests passed!")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Tests failed with exit code {e.returncode}")
        return e.returncode
    except FileNotFoundError:
        print("\n❌ Error: pytest not installed")
        print("Install with: pip install pytest pytest-cov")
        return 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run spike detection tests")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-c", "--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("-q", "--quick", action="store_true", help="Quick mode (no verbose)")

    args = parser.parse_args()

    verbose = args.verbose or not args.quick
    coverage = args.coverage

    sys.exit(run_tests(verbose=verbose, coverage=coverage))
