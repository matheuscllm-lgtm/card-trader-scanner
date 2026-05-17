#!/usr/bin/env python3
"""Test for Bug C (Codex H5): pricing failures must be logged as WARNING +
counted in stats, and a mass-failure threshold should abort the set.

Pre-fix: except Exception → log.debug → tcg_market = None → silent drop.
Schema drift / SSL / JSON parse errors silently removed deals.

Post-fix:
- Network transients (Timeout/ConnectionError) → log.debug + counter
- Unknown errors → log.warning with type+msg+blueprint context + counter
- stats['pricing_failures'] tracks total
- If >50% of a set's listings fail (with min sample 20), abort set + skip-list

Strategy: Build a real Listing dataclass instance, bypass parsing by
monkey-patching `_parse_listing` and `_passes_filters`, then feed the scanner
a synthetic raw_listings list.
"""
from __future__ import annotations

import io
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import cardtrader_scanner as scanner_mod  # noqa: E402
import requests  # noqa: E402
from cardtrader_scanner import CardTraderClient, Listing, Scanner  # noqa: E402


def make_listing(idx: int) -> Listing:
    return Listing(
        product_id=1000 + idx,
        blueprint_id=2000 + idx,
        card_name=f"FakeCard{idx}",
        set_code="fakeset",
        set_name="FakeSet",
        collector_number=f"{idx:03d}",
        condition="Near Mint",
        language="en",
        price_cents=int((100.0 + idx) * 100),
        price_currency="BRL",
        price_brl=100.0 + idx,
        quantity=1,
        foil=False,
        graded=False,
        seller_username=f"seller{idx}",
        seller_can_sell_via_hub=True,
        seller_user_type="zero_fee",
        cardtrader_url=f"https://www.cardtrader.com/cards/{idx}",
        rarity="Rare",
    )


def _build_scanner(per_set_timeout_s: int = 0) -> Scanner:
    ct = CardTraderClient.__new__(CardTraderClient)
    ct.session = MagicMock()
    ct.delay = 0.0
    ct._last_call = 0.0
    pricing = MagicMock()
    cache = MagicMock()
    with patch.object(scanner_mod, "get_usd_to_brl", return_value=5.05), \
         patch.object(scanner_mod, "get_eur_to_brl", return_value=5.50):
        s = Scanner(
            ct=ct,
            pricing=pricing,
            cache=cache,
            per_set_timeout_s=per_set_timeout_s,
            ignore_skip_list=True,
            min_price_usd=0.0,
        )
    return s


def _run_scan_with_listings(s: Scanner, listings: list[Listing]) -> list:
    """Patch CT calls + parsing helpers so scan_expansion processes our
    listings directly."""
    # Stub blueprints + raw listings (content doesn't matter, _parse_listing
    # is also stubbed)
    s.ct.list_blueprints = MagicMock(return_value=[
        {"id": l.blueprint_id} for l in listings
    ])
    s.ct.list_listings_by_expansion = MagicMock(return_value=[
        {"id": l.product_id, "blueprint_id": l.blueprint_id} for l in listings
    ])

    bp_to_listing = {l.blueprint_id: l for l in listings}

    def fake_parse(raw, bp_index):
        return bp_to_listing.get(raw["blueprint_id"])

    def fake_passes(l):
        return True

    s._parse_listing = fake_parse  # type: ignore[assignment]
    s._passes_filters = fake_passes  # type: ignore[assignment]

    return list(s.scan_expansion({"id": 1, "code": "fakeset", "name": "FakeSet"}))


def test_unknown_errors_logged_as_warning_and_counted():
    print("\n[test_unknown_errors_logged_as_warning_and_counted]")
    num_listings = 25
    fail_count = 16  # 16/25 = 64% > 50% threshold

    s = _build_scanner()

    call_idx = {"n": 0}

    def buggy(card_name, set_code, collector_number, foil=False):
        i = call_idx["n"]
        call_idx["n"] += 1
        if i < fail_count:
            raise KeyError(f"unexpected response schema for {card_name}")
        return 10.0

    s.pricing.market_price_usd = buggy

    # Capture WARNING-level log lines
    log_buf = io.StringIO()
    handler = logging.StreamHandler(log_buf)
    handler.setLevel(logging.WARNING)
    scanner_mod.log.addHandler(handler)

    listings = [make_listing(i) for i in range(num_listings)]
    with patch.object(scanner_mod, "add_to_skip_list") as add_mock:
        opps = _run_scan_with_listings(s, listings)

    scanner_mod.log.removeHandler(handler)
    log_text = log_buf.getvalue()
    warning_count = log_text.count("Pricing FAILURE")

    print(f"  listings={num_listings} simulated_fails={fail_count} ({fail_count/num_listings*100:.0f}%)")
    print(f"  stats.pricing_failures={s.stats['pricing_failures']}")
    print(f"  stats.expansions_mass_pricing_abort={s.stats['expansions_mass_pricing_abort']}")
    print(f"  WARNING 'Pricing FAILURE' lines: {warning_count}")
    print(f"  add_to_skip_list.called={add_mock.called}")
    if add_mock.called:
        print(f"    args={add_mock.call_args}")
    print(f"  opps_returned={len(opps)}")

    # The abort triggers when (failures/attempts) > 0.50 AND attempts >= 20.
    # At attempt 21: fails so far = 16, ratio 16/21 = 76% > 50% → abort.
    # So loop processes 21 attempts then aborts. Warning lines = 16.
    assert s.stats["pricing_failures"] >= 15, f"FAIL: pricing_failures={s.stats['pricing_failures']}"
    assert warning_count >= 15, f"FAIL: warning_count={warning_count}"
    assert s.stats["expansions_mass_pricing_abort"] == 1, (
        f"FAIL: mass_abort={s.stats['expansions_mass_pricing_abort']}"
    )
    assert add_mock.called, "FAIL: skip-list not invoked"
    assert "mass_pricing_failure" in add_mock.call_args[0][1], (
        f"FAIL: skip-list reason mismatch: {add_mock.call_args}"
    )
    print("  PASS")


def test_low_failure_rate_does_not_abort():
    print("\n[test_low_failure_rate_does_not_abort]")
    num_listings = 25
    fail_count = 5  # 5/25 = 20% < 50%

    s = _build_scanner()
    call_idx = {"n": 0}

    def occasional_fail(card_name, set_code, collector_number, foil=False):
        i = call_idx["n"]
        call_idx["n"] += 1
        if i < fail_count:
            raise ValueError(f"bad response for {card_name}")
        # TCG market USD high enough to produce positive margin:
        # ct_brl ~100 BRL, custo = 106 BRL. Need tcg_brl > ~150 BRL → ~30 USD
        return 50.0

    s.pricing.market_price_usd = occasional_fail

    listings = [make_listing(i) for i in range(num_listings)]
    with patch.object(scanner_mod, "add_to_skip_list") as add_mock:
        opps = _run_scan_with_listings(s, listings)

    print(f"  listings={num_listings} simulated_fails={fail_count} ({fail_count/num_listings*100:.0f}%)")
    print(f"  stats.pricing_failures={s.stats['pricing_failures']}")
    print(f"  stats.tcg_price_found={s.stats['tcg_price_found']}")
    print(f"  stats.expansions_mass_pricing_abort={s.stats['expansions_mass_pricing_abort']}")
    print(f"  add_to_skip_list.called={add_mock.called}")
    print(f"  opps_returned={len(opps)}")

    assert s.stats["pricing_failures"] >= 4, f"FAIL: pricing_failures={s.stats['pricing_failures']}"
    assert s.stats["expansions_mass_pricing_abort"] == 0, (
        f"FAIL: should NOT mass-abort at 20%"
    )
    assert not add_mock.called, "FAIL: skip-list invoked at low failure rate"
    # tcg_price_found = num_listings - fail_count = 20 listings priced OK
    assert s.stats["tcg_price_found"] == num_listings - fail_count, (
        f"FAIL: expected {num_listings - fail_count} priced, got {s.stats['tcg_price_found']}"
    )
    print("  PASS")


def test_network_transients_dont_flood_warnings():
    """ConnectionError/Timeout should hit pricing_failures but NOT log WARNING
    (those are already retried by provider; flooding the operator log is noise).
    """
    print("\n[test_network_transients_dont_flood_warnings]")
    num_listings = 25

    s = _build_scanner()
    call_idx = {"n": 0}

    def transient(card_name, set_code, collector_number, foil=False):
        i = call_idx["n"]
        call_idx["n"] += 1
        if i < 5:
            raise requests.ConnectionError("simulated transient")
        return 10.0

    s.pricing.market_price_usd = transient

    log_buf = io.StringIO()
    handler = logging.StreamHandler(log_buf)
    handler.setLevel(logging.WARNING)
    scanner_mod.log.addHandler(handler)

    listings = [make_listing(i) for i in range(num_listings)]
    with patch.object(scanner_mod, "add_to_skip_list"):
        _run_scan_with_listings(s, listings)

    scanner_mod.log.removeHandler(handler)
    log_text = log_buf.getvalue()
    print(f"  WARNING lines about Pricing FAILURE: {log_text.count('Pricing FAILURE')}")
    print(f"  stats.pricing_failures={s.stats['pricing_failures']}")

    # Network transients should NOT produce 'Pricing FAILURE' WARNINGs
    assert "Pricing FAILURE" not in log_text, (
        "FAIL: transients should be debug-only, not WARNING"
    )
    # But should still be counted
    assert s.stats["pricing_failures"] >= 5, (
        f"FAIL: pricing_failures={s.stats['pricing_failures']}"
    )
    print("  PASS")


def main() -> int:
    failed = 0
    for fn in (
        test_unknown_errors_logged_as_warning_and_counted,
        test_low_failure_rate_does_not_abort,
        test_network_transients_dont_flood_warnings,
    ):
        try:
            fn()
        except AssertionError as e:
            print(f"  ASSERTION FAIL: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  EXCEPTION: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1

    if failed:
        print(f"\nFAIL: {failed} test(s) failed")
        return 1
    print(f"\nPASS: all pricing-failure tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
