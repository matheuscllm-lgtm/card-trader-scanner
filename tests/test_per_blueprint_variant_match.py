#!/usr/bin/env python3
"""
test_per_blueprint_variant_match.py — v2.19 (2026-06-21)

Regressão do bug em validate_per_blueprint que casava o listing per-blueprint
SÓ pelo vendedor, ignorando condição (NM) e reverse/variante. Caso real
Shiftry hl: o scan achou a NM reverse (~R$140), mas a validação casava a cópia
Poor não-reverse do MESMO vendedor (R$46,46) → comparava preço de carta Poor
contra a referência reverse → falso "79%".

O fix exige condition == listing.condition (Near Mint) E reverse igual; entre
os que batem, pega o mais barato; se nenhum bate → STALE.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cardtrader_scanner as scanner  # noqa: E402


def _make_scanner(listings):
    s = scanner.Scanner.__new__(scanner.Scanner)
    s.ct = MagicMock()
    s.ct.list_listings_by_blueprint = MagicMock(return_value=listings)
    s.usd_brl = 5.16
    s.eur_brl = 5.92
    s.hub_fee_rate = 0.0
    s.stats = {}
    return s


def _listing(seller, price_cents, condition, reverse):
    return {
        "user": {"username": seller},
        "price_cents": price_cents,
        "price_currency": "BRL",
        "properties_hash": {
            "condition": condition,
            "pokemon_reverse": reverse,
            "pokemon_language": "en",
        },
    }


def _opp(foil: bool, ct_brl: float, tcg_usd: float):
    listing = scanner.Listing(
        product_id=1, blueprint_id=116203, card_name="Shiftry",
        set_code="hl", set_name="EX Hidden Legends",
        collector_number="014/101", condition="Near Mint", language="en",
        price_cents=int(ct_brl * 100), price_currency="BRL", price_brl=ct_brl,
        quantity=1, foil=foil, graded=False, seller_username="Monkey_Milano",
        seller_can_sell_via_hub=True, seller_user_type="professional",
        cardtrader_url="https://www.cardtrader.com/cards/116203",
        rarity="Holo Rare",
    )
    return scanner.Opportunity(
        listing=listing, tcg_market_usd=tcg_usd,
        tcg_market_brl=tcg_usd * 5.16, ct_price_brl=ct_brl,
        margin_pct=0.45, margin_brl=0.0, estimated_shipping_brl=0.0,
        net_margin_pct=0.45,
    )


def test_matches_nm_reverse_not_cheaper_poor_copy():
    """Scan achou NM reverse; validação NÃO pode casar a Poor não-reverse barata."""
    listings = [
        _listing("Monkey_Milano", 4646, "Poor", False),       # a armadilha
        _listing("Monkey_Milano", 13970, "Near Mint", True),  # a cópia certa
        _listing("Outro", 8615, "Near Mint", False),
    ]
    s = _make_scanner(listings)
    opp = _opp(foil=True, ct_brl=139.70, tcg_usd=42.94)  # reverse, ref reverse
    s.validate_per_blueprint([opp], top_n=5)
    assert opp.live_price_brl == 139.70, opp.live_price_brl
    # markup ~0 (live == scan) → VALIDATED_REAL, NÃO o falso 79%
    assert opp.validation_status == "VALIDATED_REAL", opp.validation_status
    # margem real = (ref_brl - live)/ref_brl ; ref=42.94*5.16
    assert 0.36 < opp.real_margin_pct < 0.38, opp.real_margin_pct


def test_matches_nm_standard_holo_not_reverse():
    """Scan achou NM holo padrão; não pode casar a cópia reverse do vendedor."""
    listings = [
        _listing("Monkey_Milano", 13970, "Near Mint", True),   # reverse (errada)
        _listing("Monkey_Milano", 8615, "Near Mint", False),   # holo padrão (certa)
    ]
    s = _make_scanner(listings)
    opp = _opp(foil=False, ct_brl=86.15, tcg_usd=20.27)  # holo padrão
    s.validate_per_blueprint([opp], top_n=5)
    assert opp.live_price_brl == 86.15, opp.live_price_brl
    assert opp.validation_status == "VALIDATED_REAL", opp.validation_status


def test_picks_cheapest_among_matching():
    """Múltiplas cópias NM+reverse do mesmo vendedor → pega a mais barata."""
    listings = [
        _listing("Monkey_Milano", 15000, "Near Mint", True),
        _listing("Monkey_Milano", 12000, "Near Mint", True),  # mais barata
        _listing("Monkey_Milano", 4646, "Poor", True),        # Poor, ignorar
    ]
    s = _make_scanner(listings)
    opp = _opp(foil=True, ct_brl=120.00, tcg_usd=42.94)
    s.validate_per_blueprint([opp], top_n=5)
    assert opp.live_price_brl == 120.00, opp.live_price_brl


def test_stale_when_no_matching_variant():
    """Vendedor só tem condição/variante diferente → STALE (não casa errado)."""
    listings = [
        _listing("Monkey_Milano", 4646, "Poor", False),
        _listing("Monkey_Milano", 9000, "Slightly Played", True),
    ]
    s = _make_scanner(listings)
    opp = _opp(foil=True, ct_brl=139.70, tcg_usd=42.94)  # quer NM reverse
    s.validate_per_blueprint([opp], top_n=5)
    assert opp.validation_status == "STALE", opp.validation_status
    assert opp.live_price_brl is None


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
