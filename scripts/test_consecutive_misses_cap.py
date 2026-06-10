#!/usr/bin/env python3
"""Test v2.13 (frente eficiência): --max-consecutive-misses.

Quando N listings consecutivos de um set não casam preço na fonte
(market_price_usd → None: buraco de cobertura, ex sets 2026 / mega evolução),
scan_expansion deve:
  • abortar o set,
  • incrementar stats['expansions_no_coverage_abort'],
  • adicionar o set à skip-list com reason 'no_coverage_...'.

E com cap=0 (default) ou hits intercalados (reset do contador) NÃO deve abortar.

Reusa o harness de scripts/test_pricing_failures.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import cardtrader_scanner as scanner_mod  # noqa: E402
from cardtrader_scanner import CardTraderClient, Listing, Scanner  # noqa: E402


def make_listing(idx: int) -> Listing:
    return Listing(
        product_id=1000 + idx, blueprint_id=2000 + idx,
        card_name=f"FakeCard{idx}", set_code="fakeset", set_name="FakeSet",
        collector_number=f"{idx:03d}", condition="Near Mint", language="en",
        price_cents=int((100.0 + idx) * 100), price_currency="BRL",
        price_brl=100.0 + idx, quantity=1, foil=False, graded=False,
        seller_username=f"seller{idx}", seller_can_sell_via_hub=True,
        seller_user_type="zero_fee",
        cardtrader_url=f"https://www.cardtrader.com/cards/{idx}",
        rarity="Rare",
    )


def _build_scanner(max_consecutive_misses: int = 0) -> Scanner:
    ct = CardTraderClient.__new__(CardTraderClient)
    ct.session = MagicMock()
    ct.delay = 0.0
    ct._last_call = 0.0
    pricing = MagicMock()
    cache = MagicMock()
    with patch.object(scanner_mod, "get_usd_to_brl", return_value=5.05), \
         patch.object(scanner_mod, "get_eur_to_brl", return_value=5.50):
        s = Scanner(
            ct=ct, pricing=pricing, cache=cache,
            per_set_timeout_s=0, ignore_skip_list=True, min_price_usd=0.0,
            max_consecutive_misses=max_consecutive_misses,
        )
    return s


def _run(s: Scanner, listings: list[Listing]) -> list:
    s.ct.list_blueprints = MagicMock(return_value=[{"id": l.blueprint_id} for l in listings])
    s.ct.list_listings_by_expansion = MagicMock(return_value=[
        {"id": l.product_id, "blueprint_id": l.blueprint_id} for l in listings
    ])
    bp_to_listing = {l.blueprint_id: l for l in listings}
    s._parse_listing = lambda raw, bp_index: bp_to_listing.get(raw["blueprint_id"])  # type: ignore
    s._passes_filters = lambda l: True  # type: ignore
    return list(s.scan_expansion({"id": 1, "code": "fakeset", "name": "FakeSet"}))


def test_cap_aborts_after_n_consecutive_misses():
    print("\n[test_cap_aborts_after_n_consecutive_misses]")
    s = _build_scanner(max_consecutive_misses=10)
    # Todos os listings retornam None (sem cobertura).
    s.pricing.market_price_usd = lambda *a, **k: None
    listings = [make_listing(i) for i in range(50)]
    with patch.object(scanner_mod, "add_to_skip_list") as add_mock:
        opps = _run(s, listings)
    print(f"  opps={len(opps)} no_coverage_abort={s.stats['expansions_no_coverage_abort']}")
    print(f"  add_to_skip_list.called={add_mock.called}")
    assert s.stats["expansions_no_coverage_abort"] == 1, "deveria abortar 1 set"
    assert add_mock.called, "skip-list não foi chamada"
    assert "no_coverage" in add_mock.call_args[0][1], add_mock.call_args
    assert len(opps) == 0
    print("  PASS")


def test_cap_zero_never_aborts():
    print("\n[test_cap_zero_never_aborts]")
    s = _build_scanner(max_consecutive_misses=0)  # desativado
    s.pricing.market_price_usd = lambda *a, **k: None
    listings = [make_listing(i) for i in range(50)]
    with patch.object(scanner_mod, "add_to_skip_list") as add_mock:
        _run(s, listings)
    print(f"  no_coverage_abort={s.stats['expansions_no_coverage_abort']} skip_called={add_mock.called}")
    assert s.stats["expansions_no_coverage_abort"] == 0
    assert not add_mock.called
    print("  PASS")


def test_intermittent_hits_reset_counter():
    print("\n[test_intermittent_hits_reset_counter]")
    s = _build_scanner(max_consecutive_misses=5)
    # Padrão: 4 misses, 1 hit, repete → contador nunca chega a 5.
    call_idx = {"n": 0}

    def pattern(*a, **k):
        i = call_idx["n"]
        call_idx["n"] += 1
        return None if (i % 5 != 4) else 50.0  # hit a cada 5º

    s.pricing.market_price_usd = pattern
    listings = [make_listing(i) for i in range(50)]
    with patch.object(scanner_mod, "add_to_skip_list") as add_mock:
        _run(s, listings)
    print(f"  no_coverage_abort={s.stats['expansions_no_coverage_abort']} skip_called={add_mock.called}")
    assert s.stats["expansions_no_coverage_abort"] == 0, "hits intercalados não deveriam abortar"
    assert not add_mock.called
    print("  PASS")


if __name__ == "__main__":
    failures = 0
    for fn in (test_cap_aborts_after_n_consecutive_misses,
               test_cap_zero_never_aborts,
               test_intermittent_hits_reset_counter):
        try:
            fn()
        except AssertionError as e:
            failures += 1
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"\n{3 - failures}/3 passed")
    sys.exit(1 if failures else 0)
