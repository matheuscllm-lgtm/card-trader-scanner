#!/usr/bin/env python3
"""Race-condition test for skip-list (Bug A, Codex H1).

Spawns N parallel processes that each add a distinct exp_code to the skip-list.
Without file locking the writes race and the final list misses entries
(last-writer-wins on the read-modify-write).

With portalocker (v2.7+ fix), all N entries should appear.

Usage:
    python scripts/test_skiplist_race.py [--num-workers 8] [--iterations 5]
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

# Make scanner module importable
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from cardtrader_scanner import (  # noqa: E402
    SKIP_LIST_FILE,
    add_to_skip_list,
    clear_skip_list,
    load_skip_list,
)


def worker(exp_code: str, delay: float) -> tuple[str, bool, str]:
    """Add a single entry, returning (code, success, err_msg)."""
    try:
        # Optional micro-delay so workers race more deterministically
        time.sleep(delay)
        add_to_skip_list(exp_code, f"race_test_{exp_code}")
        return (exp_code, True, "")
    except Exception as e:
        return (exp_code, False, f"{type(e).__name__}: {e}")


def run_iteration(num_workers: int, iteration: int) -> tuple[int, int, list[str]]:
    """Returns (expected, actual, missing)."""
    # Clean state
    clear_skip_list()

    codes = [f"race{iteration:02d}_{i:03d}" for i in range(num_workers)]
    with mp.Pool(num_workers) as pool:
        # All workers fire as close to simultaneous as Python's pool startup permits
        results = pool.starmap(worker, [(c, 0.0) for c in codes])

    failures = [(c, msg) for (c, ok, msg) in results if not ok]
    if failures:
        print(f"  [iter {iteration}] WORKER FAILURES: {failures}")

    data = load_skip_list()
    skipped = set(data.get("skipped", []))
    expected_set = set(codes)
    missing = sorted(expected_set - skipped)
    return (len(expected_set), len(expected_set & skipped), missing)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--num-workers", type=int, default=8)
    ap.add_argument("--iterations", type=int, default=5)
    args = ap.parse_args()

    print(f"Race test: {args.iterations} iterations x {args.num_workers} parallel writers")
    print(f"Skip-list file: {SKIP_LIST_FILE}")

    total_missing = 0
    for it in range(args.iterations):
        expected, actual, missing = run_iteration(args.num_workers, it)
        status = "OK" if not missing else "FAIL"
        print(f"  [iter {it}] expected={expected} actual={actual} missing={len(missing)} {status}")
        if missing:
            print(f"    missing codes: {missing[:10]}{'...' if len(missing) > 10 else ''}")
            total_missing += len(missing)

    # Restore clean state
    clear_skip_list()

    if total_missing == 0:
        print(f"\nPASS: zero missing entries across {args.iterations} iterations")
        return 0
    else:
        print(f"\nFAIL: {total_missing} total missing entries (race condition present)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
