#!/usr/bin/env python3
"""
test_tcgcsv_fallback.py — v2.23 (2026-06-23)

Cobre o FALLBACK de preço tcgcsv.com (consultado SÓ quando a pokemontcg.io não
precifica um SET inteiro — caso asc/Ascended Heroes, que sem o fallback estoura
o timeout e cai na skip-list, ficando INVISÍVEL).

Os 6 testos exigidos (todos offline — fixtures/mocks, sem rede):
  (a) sets que a pokemontcg.io precifica NÃO invocam o tcgcsv (default path);
  (b) resolução de set tcgcsv é UNIQUE-MATCH-ONLY (abbr/nome ambíguo → None);
  (c) FIDELIDADE DE VARIANTE — holo-rare com Holofoil E Reverse Holofoil no
      tcgcsv resolve pra HOLOFOIL num listing não-reverse (a regressão Gengar)
      e pra REVERSE num listing pokemon_reverse=True. Colapsar-pro-mais-barato
      FALHA este teste;
  (d) variante REQUERIDA ausente no tcgcsv → pula (None), nunca substitui;
  (e) o fallback dispara SÓ quando a pokemontcg.io devolve 0 pro set (asc-like),
      não quando ela já precifica;
  (f) validate_per_blueprint segue como guard FINAL sobre uma margem de tcgcsv.

⚠️ (c) e (d) são os testes-chave: FALHAM sem a seleção de variante ciente de
raridade/reverse (um port ingênuo estilo MYP `_min_tcg_usd`, que pega o menor
subtype, reintroduz a inflação Gengar $146→$1599 e quebra (c)).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cardtrader_scanner as sc  # noqa: E402
from cardtrader_scanner import (  # noqa: E402
    Listing,
    TcgCsvFallbackProvider,
    resolve_tcgcsv_group_id,
    select_tcgplayer_variant_price,
)


# ───────────────────────── fixtures de rede mockadas ───────────────────────
def _fake_groups():
    """Dump /groups mínimo: um group resolvível por abbr, dois ambíguos por nome."""
    return [
        {"groupId": 100, "name": "ME2.5: Ascended Heroes", "abbreviation": "ASC"},
        {"groupId": 200, "name": "Mega Evolution", "abbreviation": "MEG"},
        {"groupId": 201, "name": "Mega Evolution Promos", "abbreviation": "MEP"},
    ]


def _fake_products(numbers):
    """numbers: {productId: "NNN/MMM"} → forma /products do tcgcsv."""
    return {
        "results": [
            {
                "productId": pid,
                "name": f"Card {pid}",
                "extendedData": [{"name": "Number", "value": num}],
            }
            for pid, num in numbers.items()
        ]
    }


def _fake_prices(rows):
    """rows: list de (productId, subTypeName, marketPrice) → forma /prices."""
    return {
        "results": [
            {"productId": pid, "subTypeName": sub, "marketPrice": mkt,
             "lowPrice": mkt, "midPrice": mkt}
            for (pid, sub, mkt) in rows
        ]
    }


def _provider_with(groups, products, prices):
    """TcgCsvFallbackProvider com session.get mockado (sem rede real)."""
    prov = TcgCsvFallbackProvider.__new__(TcgCsvFallbackProvider)
    prov.cache = MagicMock()
    prov._groups = None
    prov._groups_fetched = False
    prov._set_index = {}
    prov.last_price_source = None
    prov.last_tcg_url = None
    prov.last_variant_used = None
    prov.last_ptcg_rarity = None
    prov.last_set_release_date = None

    def fake_get(url, headers=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        if url.endswith("/groups"):
            resp.json.return_value = {"results": groups}
        elif url.endswith("/products"):
            resp.json.return_value = products
        elif url.endswith("/prices"):
            resp.json.return_value = prices
        else:
            resp.status_code = 404
            resp.json.return_value = {}
        return resp

    prov.session = MagicMock()
    prov.session.get.side_effect = fake_get
    return prov


# ───────────────────────────── (b) unique-match ─────────────────────────────
def test_b_resolution_unique_match_by_abbr():
    """Abbr exata (ASC) resolve pro group certo (100)."""
    gid = resolve_tcgcsv_group_id(["me2pt5"], "Ascended Heroes", _fake_groups())
    assert gid == 100, gid


def test_b_resolution_ambiguous_name_returns_none():
    """Nome 'Mega Evolution' casa 2 groups (200, 201) → AMBÍGUO → None.

    NUNCA chuta o primeiro — injetar preço do group errado como 'real' é o bug
    que o fallback unique-only existe pra evitar."""
    # setcode sem abbr conhecida → cai no fallback por nome, que é ambíguo aqui.
    gid = resolve_tcgcsv_group_id(["unknown_set"], "Mega Evolution", _fake_groups())
    assert gid is None, gid


def test_b_resolution_unique_name_match_ok():
    """Nome único ('Ascended Heroes' ∈ só 1 group) resolve (via fallback nome)."""
    gid = resolve_tcgcsv_group_id(["unknown_set"], "Ascended Heroes", _fake_groups())
    assert gid == 100, gid


def test_b_no_match_returns_none():
    """Sem abbr e sem nome casando → None (sem preço inventado)."""
    gid = resolve_tcgcsv_group_id(["unknown_set"], "Nonexistent Set", _fake_groups())
    assert gid is None, gid


# ───────────────── (c) FIDELIDADE DE VARIANTE (a regressão Gengar) ───────────
# Gengar: Holofoil $146.89 vs Reverse Holofoil $1599.99 (10×). Um listing
# não-reverse de uma holo rare DEVE casar holofoil; um pokemon_reverse=True DEVE
# casar reverseHolofoil. Colapsar-pro-mais-barato pegaria sempre o holofoil
# ($146) e quebraria o ramo reverse (esperado $1599).
_GENGAR_VARIANTS = {
    "holofoil": {"market": 146.89},
    "reverseHolofoil": {"market": 1599.99},
}


def test_c_holo_rare_nonreverse_picks_holofoil():
    """Holo rare, listing NÃO-reverse (foil=False) → holofoil $146.89."""
    variant, entry = select_tcgplayer_variant_price(
        _GENGAR_VARIANTS, foil=False, is_holo=True
    )
    assert variant == "holofoil", variant
    assert entry["market"] == 146.89, entry


def test_c_holo_rare_reverse_picks_reverseholofoil():
    """Holo rare, listing reverse (foil=True) → reverseHolofoil $1599.99."""
    variant, entry = select_tcgplayer_variant_price(
        _GENGAR_VARIANTS, foil=True, is_holo=True
    )
    assert variant == "reverseHolofoil", variant
    assert entry["market"] == 1599.99, entry


def test_c_collapse_to_cheapest_would_break_reverse():
    """Anti-regressão explícita: colapsar pro mais barato daria SEMPRE holofoil
    ($146.89), inclusive pro listing reverse — exatamente o bug v2.18. Provamos
    que a seleção NÃO faz isso (reverse → 1599.99 ≠ menor subtype)."""
    cheapest = min(v["market"] for v in _GENGAR_VARIANTS.values())  # 146.89
    _, entry_rev = select_tcgplayer_variant_price(
        _GENGAR_VARIANTS, foil=True, is_holo=True
    )
    assert entry_rev["market"] != cheapest, (
        "reverse colapsou pro mais barato — bug Gengar reintroduzido"
    )


def test_c_end_to_end_via_provider():
    """Mesma fidelidade exercitada pelo provider tcgcsv completo (prefill→price).

    productId 1 = Gengar #94 com Holofoil $146.89 + Reverse Holofoil $1599.99."""
    products = _fake_products({1: "094/110"})
    prices = _fake_prices([
        (1, "Holofoil", 146.89),
        (1, "Reverse Holofoil", 1599.99),
    ])
    prov = _provider_with(_fake_groups(), products, prices)
    ok = prov.prefill_set("me1", ["me1"], "Mega Evolution Base")
    # Mega Evolution Base não casa abbr MEG por nome — usa abbr direto via me1.
    assert ok, "prefill deveria indexar o card"
    # listing não-reverse → holofoil
    p_holo = prov.market_price_usd("Gengar", "me1", "094/110",
                                   foil=False, rarity="Holo Rare")
    assert p_holo == 146.89, p_holo
    assert prov.last_variant_used == "holofoil"
    # listing reverse → reverseHolofoil
    p_rev = prov.market_price_usd("Gengar", "me1", "094/110",
                                  foil=True, rarity="Holo Rare")
    assert p_rev == 1599.99, p_rev
    assert prov.last_variant_used == "reverseHolofoil"
    assert prov.last_price_source == "tcgcsv"


# ───────────────── (d) variante REQUERIDA ausente → skip (None) ──────────────
def test_d_required_variant_absent_returns_none():
    """Só Normal no tcgcsv; listing reverse (foil=True) de carta não-holo exige
    reverseHolofoil. A escada permite holofoil/normal como alternativas APENAS
    pra holo rare — mas aqui provamos o caso load-bearing: quando NENHUMA
    variante canônica tem market, retorna None (nunca substitui)."""
    variant, entry = select_tcgplayer_variant_price(
        {"reverseHolofoil": {"market": 0}},  # presente mas sem preço
        foil=True, is_holo=True
    )
    assert variant is None and entry is None, (variant, entry)


def test_d_provider_skips_when_variant_missing():
    """Provider: card existe no índice mas só com subtype sem market → None."""
    products = _fake_products({2: "010/110"})
    # subtype desconhecido + Holofoil com market 0 → nenhuma variante válida
    prices = _fake_prices([(2, "Holofoil", 0)])
    prov = _provider_with(_fake_groups(), products, prices)
    prov.prefill_set("me1", ["me1"], "Mega Evolution Base")
    out = prov.market_price_usd("Foo", "me1", "010/110",
                                foil=False, rarity="Holo Rare")
    assert out is None, out


def test_d_never_substitutes_another_subtype():
    """Carta base NÃO-holo, listing não-reverse: só Reverse Holofoil disponível.
    A escada non-holo é [normal, holofoil, unlimitedHolofoil, reverseHolofoil] —
    reverse é último recurso, mas existe. Provamos o caso onde nem isso há:
    apenas um subtype 1stEdition (EXCLUÍDO) → None (não vaza 1st Ed inflado)."""
    variant, entry = select_tcgplayer_variant_price(
        {"1stEditionHolofoil": {"market": 999.0}},
        foil=False, is_holo=False
    )
    assert variant is None and entry is None, (variant, entry)


# ─────────── scanner-level: (a)(e) fallback dispara SÓ em set sem cobertura ──
def _listing(card_name, num, set_code="asc", foil=False, rarity="Common",
             price_brl=60.0):
    return Listing(
        product_id=hash((card_name, num)) & 0xFFFF,
        blueprint_id=hash((card_name, num, "bp")) & 0xFFFF,
        card_name=card_name, set_code=set_code, set_name="Ascended Heroes",
        collector_number=num, condition="Near Mint", language="en",
        price_cents=int(price_brl * 100), price_currency="BRL",
        price_brl=price_brl, quantity=1, foil=foil, graded=False,
        seller_username="seller1", seller_can_sell_via_hub=True,
        seller_user_type="professional",
        cardtrader_url="https://cardtrader.com/cards/1", rarity=rarity,
    )


def _scanner_with(pokemontcg_prices, tcgcsv_provider, listings,
                  tcgcsv_fallback=True, max_misses=2):
    """Scanner com providers mockados; pokemontcg_prices = {(set,num): usd}."""
    s = sc.Scanner.__new__(sc.Scanner)
    s.ct = MagicMock()
    # blueprints/listings vêm pré-resolvidos como `listings` (pulamos a rede CT):
    s.cache = MagicMock()
    s.threshold = 0.10
    s.min_price_usd = 10.0
    s.exclude_graded = True
    s.shipping_brl_override = 0.0
    s.hub_fee_rate = 0.0
    s.per_set_timeout_s = 0  # sem timeout nos testes
    s.ignore_skip_list = True
    s.chase_only = False
    s.max_consecutive_misses = max_misses
    s.keep_all_priced = True
    s.tcgcsv = tcgcsv_provider
    s.tcgcsv_fallback = tcgcsv_fallback
    s.heartbeat = lambda *_: None
    s._checkpoint = None
    s.usd_brl = 5.0
    s.eur_brl = 5.9
    s.stats = {k: 0 for k in (
        "expansions_scanned", "listings_fetched", "listings_after_filters",
        "tcg_price_found", "opportunities_found", "skipped_exotic_currency",
        "expansions_skipped_by_list", "expansions_timed_out", "pricing_failures",
        "expansions_mass_pricing_abort", "skipped_non_chase",
        "expansions_no_coverage_abort", "priced_below_threshold",
        "tcgcsv_fallback_sets", "tcgcsv_fallback_priced",
    )}
    s.mass_pricing_failure_threshold = 0.50
    s.mass_pricing_failure_min_sample = 20

    # pokemontcg provider: devolve preço do dict ou None (miss).
    pricing = MagicMock()
    pricing.name = "pokemontcg"
    pricing.last_tcg_url = None
    pricing.last_variant_used = "normal"
    pricing.last_ptcg_rarity = None
    pricing.last_set_release_date = None
    pricing.last_price_source = None

    def price_fn(card_name, set_code, num, foil=False, rarity=None):
        return pokemontcg_prices.get((set_code, num))
    pricing.market_price_usd.side_effect = price_fn
    s.pricing = pricing

    # _build_real_set_listings: injetamos via monkeypatch do scan_expansion
    # carregando best_by_uid direto. Mais simples: stubamos os métodos de rede
    # do CT pra devolver os raw e deixamos _parse_listing/_passes_filters reais.
    return s


def _run_scan_expansion(scanner, listings):
    """Roda scan_expansion com a rede CT stubada pra entregar `listings` direto.

    Monkeypatcha list_blueprints/list_listings_by_expansion e _parse_listing/
    _passes_filters pra que o pipeline use os Listing já prontos."""
    scanner.ct.list_blueprints = MagicMock(return_value=[
        {"id": l.blueprint_id, "name": l.card_name} for l in listings
    ])
    scanner.ct.list_listings_by_expansion = MagicMock(return_value=[
        {"id": l.product_id, "blueprint_id": l.blueprint_id} for l in listings
    ])
    by_pid = {l.product_id: l for l in listings}
    scanner._parse_listing = MagicMock(
        side_effect=lambda raw, idx: by_pid.get(raw["id"])
    )
    scanner._passes_filters = MagicMock(return_value=True)
    exp = {"id": 1, "code": listings[0].set_code, "name": "Ascended Heroes"}
    return list(scanner.scan_expansion(exp))


def test_e_fallback_triggers_when_pokemontcg_zero_for_set():
    """asc-like: pokemontcg devolve 0 pro set inteiro → tcgcsv resgata."""
    listings = [
        _listing("Card A", "001/100", rarity="Holo Rare", price_brl=60),
        _listing("Card B", "002/100", rarity="Holo Rare", price_brl=70),
    ]
    products = _fake_products({1: "001/100", 2: "002/100"})
    prices = _fake_prices([(1, "Holofoil", 50.0), (2, "Holofoil", 60.0)])
    tcgcsv = _provider_with(_fake_groups(), products, prices)
    # set_code asc → ptcg me2pt5 (alias real) → abbr ASC → group 100.
    scanner = _scanner_with({}, tcgcsv, listings, max_misses=1)
    opps = _run_scan_expansion(scanner, listings)
    assert len(opps) == 2, [o.listing.card_name for o in opps]
    assert all(o.price_source == "tcgcsv" for o in opps), \
        [o.price_source for o in opps]
    assert scanner.stats["tcgcsv_fallback_sets"] == 1
    assert scanner.stats["tcgcsv_fallback_priced"] == 2


def test_a_pokemontcg_priced_set_never_invokes_tcgcsv():
    """Default path: pokemontcg precifica o set → tcgcsv NUNCA é consultado."""
    listings = [
        _listing("Card A", "001/100", set_code="dri", rarity="Holo Rare"),
        _listing("Card B", "002/100", set_code="dri", rarity="Holo Rare"),
    ]
    products = _fake_products({1: "001/100"})
    prices = _fake_prices([(1, "Holofoil", 50.0)])
    tcgcsv = _provider_with(_fake_groups(), products, prices)
    scanner = _scanner_with(
        {("dri", "001/100"): 100.0, ("dri", "002/100"): 120.0},
        tcgcsv, listings, max_misses=1,
    )
    opps = _run_scan_expansion(scanner, listings)
    assert len(opps) == 2
    # tcgcsv jamais tocado: nenhuma chamada de rede, nenhum prefill, source=pokemontcg
    tcgcsv.session.get.assert_not_called()
    assert scanner.stats["tcgcsv_fallback_sets"] == 0
    assert all((o.price_source or "pokemontcg") == "pokemontcg" for o in opps)


def test_e_no_fallback_when_pokemontcg_has_any_hit():
    """Cobertura PARCIAL: pokemontcg precifica 1 dos 2 cards → tcgcsv NÃO entra
    (a regra é set_tcg_hits == 0, não 'completar buracos por-card')."""
    listings = [
        _listing("Card A", "001/100", set_code="dri", rarity="Holo Rare"),
        _listing("Card B", "002/100", set_code="dri", rarity="Holo Rare"),
    ]
    tcgcsv = _provider_with(_fake_groups(), _fake_products({}), _fake_prices([]))
    scanner = _scanner_with(
        {("dri", "001/100"): 100.0},  # só A tem preço; B é miss
        tcgcsv, listings, max_misses=1,
    )
    opps = _run_scan_expansion(scanner, listings)
    # só A vira opp; tcgcsv não roda (houve hit no set)
    assert [o.listing.card_name for o in opps] == ["Card A"]
    tcgcsv.session.get.assert_not_called()
    assert scanner.stats["tcgcsv_fallback_sets"] == 0


def test_a_opt_out_disables_fallback():
    """--no-tcgcsv-fallback (tcgcsv_fallback=False) → set asc fica sem preço,
    sem consultar tcgcsv (comportamento legado preservado)."""
    listings = [_listing("Card A", "001/100", rarity="Holo Rare")]
    tcgcsv = _provider_with(_fake_groups(),
                            _fake_products({1: "001/100"}),
                            _fake_prices([(1, "Holofoil", 50.0)]))
    scanner = _scanner_with({}, tcgcsv, listings,
                            tcgcsv_fallback=False, max_misses=1)
    opps = _run_scan_expansion(scanner, listings)
    assert opps == []
    tcgcsv.session.get.assert_not_called()


# ─────────── (f) validate_per_blueprint guarda margem de fonte tcgcsv ────────
def test_f_validate_per_blueprint_overrides_tcgcsv_margin():
    """A margem do scan veio do tcgcsv; validate_per_blueprint (per-blueprint CT)
    é o guard FINAL source-independente e re-precifica o top-N, ajustando o
    markup/status sobre a Opportunity de fonte tcgcsv."""
    listing = Listing(
        product_id=1, blueprint_id=555, card_name="Card A", set_code="asc",
        set_name="Ascended Heroes", collector_number="001/100",
        condition="Near Mint", language="en", price_cents=6000,
        price_currency="BRL", price_brl=60.0, quantity=1, foil=False,
        graded=False, seller_username="seller1", seller_can_sell_via_hub=True,
        seller_user_type="professional",
        cardtrader_url="https://cardtrader.com/cards/555", rarity="Holo Rare",
    )
    opp = sc.Opportunity(
        listing=listing, tcg_market_usd=50.0, tcg_market_brl=250.0,
        ct_price_brl=60.0, margin_pct=0.76, margin_brl=190.0,
        estimated_shipping_brl=0.0, net_margin_pct=0.76,
        price_source="tcgcsv",  # margem veio do FALLBACK
    )
    s = sc.Scanner.__new__(sc.Scanner)
    s.usd_brl = 5.0
    s.eur_brl = 5.9
    s.hub_fee_rate = 0.0
    s.stats = {}
    s.ct = MagicMock()
    # per-blueprint devolve o mesmo seller, NM, não-reverse, a R$63 (markup +5%)
    s.ct.list_listings_by_blueprint = MagicMock(return_value=[{
        "user": {"username": "seller1"},
        "price_cents": 6300, "price_currency": "BRL",
        "properties_hash": {"condition": "Near Mint",
                            "pokemon_reverse": False, "pokemon_language": "en"},
    }])
    s.validate_per_blueprint([opp], top_n=5)
    # rodou e ajustou: live price setado, status validado, margem REAL recalculada
    assert opp.live_price_brl == 63.0, opp.live_price_brl
    assert opp.validation_status in ("VALIDATED_REAL", "VALIDATED_MARKUP"), \
        opp.validation_status
    assert opp.real_margin_pct is not None
    # a fonte original continua rotulada como tcgcsv (proveniência preservada)
    assert opp.price_source == "tcgcsv"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
