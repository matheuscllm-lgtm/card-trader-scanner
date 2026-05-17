#!/usr/bin/env python3
"""Test for Bug B (Codex H2): per-set timeout must cover initial CT calls,
not just the pricing loop.

Pre-fix: timer started before list_blueprints/list_listings, but the first
timeout check was inside the pricing loop. A slow CT call (or 429 Retry-After
60s in the middle of a retry) could hold the set 30s+ past --per-set-timeout
before aborting.

Post-fix: deadline_ts propagates into CT._get(), which:
  1. Refuses to issue request if deadline already past
  2. Caps sleep() on retries to remaining-time, raising TimeoutError otherwise
  3. Sets per-request requests.timeout to min(TIMEOUT, remaining)

Test strategy: monkey-patch CT._get() to sleep for `slow_call_s` before returning.
With --per-set-timeout 5s and a slow call of 30s, the call should abort in
≤ 5-7s, NOT 30s+.

Usage:
    python scripts/test_per_set_timeout_initial_calls.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import cardtrader_scanner as scanner_mod  # noqa: E402
from cardtrader_scanner import CardTraderClient, Scanner  # noqa: E402


def test_blueprint_call_respects_deadline():
    """Slow blueprint call should abort via TimeoutError before pricing loop."""
    print("\n[test_blueprint_call_respects_deadline]")
    set_timeout_s = 5.0
    slow_call_s = 30.0
    exp_dict = {"id": 999, "code": "fakeset", "name": "FakeSet"}

    # Real CT client wrapper but with _get mocked to sleep
    ct = CardTraderClient.__new__(CardTraderClient)
    ct.session = MagicMock()
    ct.delay = 0.0
    ct._last_call = 0.0

    def slow_get(path, deadline_ts=None, **params):
        # Simulate a slow upstream that ignores TIMEOUT
        # But the request timeout itself should be reduced by deadline
        if deadline_ts is not None:
            remaining = deadline_ts - time.monotonic()
            if remaining < slow_call_s:
                # In real life requests.get would raise Timeout
                # Here we simulate that by sleeping remaining + raising
                time.sleep(max(0.0, remaining))
                raise TimeoutError(f"simulated slow CT call exceeded remaining {remaining:.1f}s")
        time.sleep(slow_call_s)
        return []

    ct._get = slow_get
    ct.list_blueprints = lambda exp_id, deadline_ts=None: ct._get(
        "/blueprints/export", deadline_ts=deadline_ts, expansion_id=exp_id
    )
    ct.list_listings_by_expansion = lambda exp_id, language="en", deadline_ts=None: ct._get(
        "/marketplace/products", deadline_ts=deadline_ts, expansion_id=exp_id, language=language
    )

    pricing = MagicMock()
    cache = MagicMock()
    # Don't actually hit FX endpoints
    with patch.object(scanner_mod, "get_usd_to_brl", return_value=5.05), \
         patch.object(scanner_mod, "get_eur_to_brl", return_value=5.50):
        s = Scanner(
            ct=ct,
            pricing=pricing,
            cache=cache,
            per_set_timeout_s=set_timeout_s,
            ignore_skip_list=True,
        )

    # Don't actually mutate skip-list during test
    with patch.object(scanner_mod, "add_to_skip_list") as add_mock:
        t0 = time.monotonic()
        result = list(s.scan_expansion(exp_dict))
        elapsed = time.monotonic() - t0

    print(f"  set_timeout={set_timeout_s}s slow_call={slow_call_s}s actual_elapsed={elapsed:.2f}s")
    print(f"  expansions_timed_out={s.stats['expansions_timed_out']}")
    print(f"  add_to_skip_list called={add_mock.called} reason={add_mock.call_args}")

    # Assertions
    assert result == [], f"Expected no opportunities, got {len(result)}"
    assert elapsed < set_timeout_s + 3.0, (
        f"FAIL: elapsed {elapsed:.2f}s should be ≤ {set_timeout_s + 3.0}s "
        f"(timeout cap not enforced)"
    )
    assert s.stats["expansions_timed_out"] == 1, "expansions_timed_out should increment"
    assert add_mock.called, "add_to_skip_list should be called"

    print(f"  PASS")
    return True


def test_429_retry_after_does_not_bypass_deadline():
    """A 429 with Retry-After greater than remaining deadline must abort, not sleep through."""
    print("\n[test_429_retry_after_does_not_bypass_deadline]")
    set_timeout_s = 3.0

    # Hand-built mini-mock requests session
    call_count = {"n": 0}

    class FakeResponse:
        def __init__(self, status_code, headers=None, body=None):
            self.status_code = status_code
            self.headers = headers or {}
            self._body = body or []

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return self._body

    def fake_get(url, params=None, timeout=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Return 429 with Retry-After 60s — much greater than 3s deadline
            return FakeResponse(429, {"Retry-After": "60"})
        return FakeResponse(200, body=[])

    ct = CardTraderClient.__new__(CardTraderClient)
    ct.session = MagicMock()
    ct.session.get = fake_get
    ct.delay = 0.0
    ct._last_call = 0.0

    t0 = time.monotonic()
    try:
        ct._get("/test", deadline_ts=time.monotonic() + set_timeout_s)
        outcome = "no_exception"
    except TimeoutError as e:
        outcome = f"TimeoutError: {e}"
    except Exception as e:
        outcome = f"{type(e).__name__}: {e}"
    elapsed = time.monotonic() - t0

    print(f"  set_timeout={set_timeout_s}s retry_after=60s actual_elapsed={elapsed:.2f}s")
    print(f"  outcome={outcome}")

    assert "TimeoutError" in outcome, f"Expected TimeoutError, got {outcome}"
    assert elapsed < set_timeout_s + 1.0, (
        f"FAIL: elapsed {elapsed:.2f}s > {set_timeout_s + 1.0}s (deadline ignored on 429 sleep)"
    )
    print(f"  PASS")
    return True


def main() -> int:
    failed = 0
    try:
        test_blueprint_call_respects_deadline()
    except AssertionError as e:
        print(f"  ASSERTION FAIL: {e}")
        failed += 1
    except Exception as e:
        print(f"  EXCEPTION: {type(e).__name__}: {e}")
        failed += 1

    try:
        test_429_retry_after_does_not_bypass_deadline()
    except AssertionError as e:
        print(f"  ASSERTION FAIL: {e}")
        failed += 1
    except Exception as e:
        print(f"  EXCEPTION: {type(e).__name__}: {e}")
        failed += 1

    if failed:
        print(f"\nFAIL: {failed} test(s) failed")
        return 1
    print(f"\nPASS: all per-set-timeout tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
