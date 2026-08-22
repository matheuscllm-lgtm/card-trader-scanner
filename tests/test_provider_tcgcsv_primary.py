#!/usr/bin/env python3
"""
test_provider_tcgcsv_primary.py — v2.26 (2026-08-22)

Cobre a promoção do tcgcsv.com a fonte PRIMÁRIA selecionável
(`--provider tcgcsv`), motivada pelo incidente 2026-08-22 (pokemontcg.io
com 500/502 intermitentes; o fallback v2.23 não cobre esse cenário porque só
dispara com ZERO preço no set ou cap de misses). Handoff:
`scanners-commons/HANDOFF-CARDTRADER-FONTE-PRECO.md`.

Contratos exigidos (todos offline — mocks, sem rede):
  (1) registro: PROVIDERS["tcgcsv"] é a TcgCsvFallbackProvider e a classe
      constrói com só o Cache (wiring do main);
  (2) DEFAULT INALTERADO: `--provider` continua "pokemontcg" sem flag — os
      comandos canônicos do skill /scan não mudam;
  (3) primário fim-a-fim: scan_expansion faz o prefill bulk no início do set
      e precifica TODOS os listings via tcgcsv (price_source="tcgcsv"),
      SEM tocar os contadores de fallback (papel primário ≠ resgate);
  (4) set que NÃO resolve no tcgcsv (sem groupId único) → aborta o set SEM
      gravar skip-list (no_coverage_* é permanente; o gap é da fonte, não do
      set — gravaria condenaria o set pros runs pokemontcg também);
  (5) fidelidade de variante preservada no papel primário (holo rare
      não-reverse → holofoil, nunca colapsa pro subtype mais barato).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import cardtrader_scanner as sc  # noqa: E402
from cardtrader_scanner import PROVIDERS, TcgCsvFallbackProvider  # noqa: E402

# Reusa o harness do teste de fallback (fixtures de rede mockadas + builders
# de Listing/Scanner/scan_expansion) — fonte única, sem cópia divergente.
from test_tcgcsv_fallback import (  # noqa: E402
    _fake_groups,
    _fake_prices,
    _fake_products,
    _listing,
    _provider_with,
    _run_scan_expansion,
    _scanner_with,
)


def _scanner_with_tcgcsv_primary(tcgcsv_provider, max_misses=40):
    """Scanner cujo provider PRIMÁRIO é o tcgcsv (papel v2.26).

    Constrói via _scanner_with (mesmos defaults) e troca o pricing pelo
    provider tcgcsv real (session mockada). O slot de fallback fica vazio —
    exatamente como o main monta com --provider tcgcsv (fallback só existe
    quando o primário é pokemontcg)."""
    s = _scanner_with({}, None, [], tcgcsv_fallback=False,
                      max_misses=max_misses)
    s.pricing = tcgcsv_provider
    s.tcgcsv = None
    return s


# ───────────────────────── (1) registro + wiring ─────────────────────────
def test_providers_registry_has_tcgcsv():
    """--provider tcgcsv existe e aponta pra classe já testada do fallback."""
    assert PROVIDERS.get("tcgcsv") is TcgCsvFallbackProvider, PROVIDERS.keys()


def test_tcgcsv_constructs_with_cache_only():
    """Wiring do main: provider_cls(cache) — sem key, sem rede no __init__."""
    prov = TcgCsvFallbackProvider(MagicMock())
    assert prov.name == "tcgcsv"
    assert prov._set_index == {}


# ───────────────────────── (2) default INALTERADO ─────────────────────────
def test_default_provider_still_pokemontcg():
    """Sem flag, --provider segue pokemontcg (comandos canônicos intactos)."""
    with patch.object(sys, "argv", ["cardtrader_scanner.py"]):
        args = sc.parse_args()
    assert args.provider == "pokemontcg", args.provider


def test_provider_tcgcsv_is_accepted_by_cli():
    with patch.object(sys, "argv", ["cardtrader_scanner.py",
                                    "--provider", "tcgcsv"]):
        args = sc.parse_args()
    assert args.provider == "tcgcsv", args.provider


# ──────────────── (3) primário fim-a-fim via scan_expansion ────────────────
def test_primary_tcgcsv_prefills_and_prices_whole_set():
    """Prefill 1× no início do set; todos os listings saem price_source=tcgcsv;
    contadores de FALLBACK ficam zerados (papel primário, não resgate)."""
    listings = [
        _listing("Card A", "001/100", rarity="Holo Rare", price_brl=60),
        _listing("Card B", "002/100", rarity="Holo Rare", price_brl=70),
    ]
    products = _fake_products({1: "001/100", 2: "002/100"})
    prices = _fake_prices([(1, "Holofoil", 50.0), (2, "Holofoil", 60.0)])
    tcgcsv = _provider_with(_fake_groups(), products, prices)
    scanner = _scanner_with_tcgcsv_primary(tcgcsv)
    opps = _run_scan_expansion(scanner, listings)
    assert len(opps) == 2, [o.listing.card_name for o in opps]
    assert all(o.price_source == "tcgcsv" for o in opps), \
        [o.price_source for o in opps]
    # prefill aconteceu (groups + products + prices = 3 GETs, 1× por set)
    assert tcgcsv.session.get.call_count == 3, tcgcsv.session.get.call_count
    # papel primário NÃO é fallback: contadores de resgate intactos
    assert scanner.stats["tcgcsv_fallback_sets"] == 0
    assert scanner.stats["tcgcsv_fallback_priced"] == 0


# ─────────── (4) set sem groupId → aborta SEM gravar skip-list ───────────
def test_primary_tcgcsv_unresolved_set_aborts_without_skiplist():
    """Set que não resolve groupId único no tcgcsv: 0 opps, abort contado,
    e add_to_skip_list NUNCA chamado (no_coverage_* é permanente e
    condenaria o set pros runs pokemontcg que podem cobri-lo)."""
    import dataclasses
    # Set fictício: código zzz não tem alias ptcg/abbr e o nome não casa
    # nenhum group fake (o set_name default do harness, "Ascended Heroes",
    # resolveria — troca via dataclasses.replace).
    listings = [dataclasses.replace(
        _listing("Card A", "001/100", set_code="zzz", rarity="Holo Rare"),
        set_name="Nonexistent Set",
    )]
    tcgcsv = _provider_with(_fake_groups(), _fake_products({}),
                            _fake_prices([]))
    scanner = _scanner_with_tcgcsv_primary(tcgcsv)
    with patch.object(sc, "add_to_skip_list") as add_skip:
        opps = _run_scan_expansion(scanner, listings)
    assert opps == [], [o.listing.card_name for o in opps]
    assert scanner.stats["expansions_no_coverage_abort"] == 1
    add_skip.assert_not_called()


# ─────────── (5) fidelidade de variante preservada no papel primário ───────
def test_primary_tcgcsv_variant_fidelity_gengar():
    """Holo rare não-reverse casa HOLOFOIL ($146.89), nunca o reverse inflado
    ($1599.99) nem colapso pro mais barato — a regressão Gengar não volta
    pelo caminho primário."""
    listings = [
        _listing("Gengar", "094/110", foil=False, rarity="Holo Rare",
                 price_brl=60),
    ]
    products = _fake_products({1: "094/110"})
    prices = _fake_prices([
        (1, "Holofoil", 146.89),
        (1, "Reverse Holofoil", 1599.99),
    ])
    tcgcsv = _provider_with(_fake_groups(), products, prices)
    scanner = _scanner_with_tcgcsv_primary(tcgcsv)
    opps = _run_scan_expansion(scanner, listings)
    assert len(opps) == 1, opps
    assert opps[0].tcg_market_usd == 146.89, opps[0].tcg_market_usd
    assert opps[0].price_variant_used == "holofoil", \
        opps[0].price_variant_used
    assert opps[0].price_source == "tcgcsv"


# ─────────── (6) resolução vintage G6 via abbr curada (v2.26) ───────────
_VINTAGE_GROUPS = [
    # nomes REAIS do tcgcsv (sonda 2026-08-22) — os casos que quebravam o
    # fallback por nome: substring ambígua e "&" vs "and".
    {"groupId": 604, "name": "Base Set", "abbreviation": "BS"},
    {"groupId": 605, "name": "Base Set 2", "abbreviation": "BS2"},
    {"groupId": 1663, "name": "Base Set (Shadowless)", "abbreviation": "BSS"},
    {"groupId": 1376, "name": "EX Dragon", "abbreviation": "DR"},
    {"groupId": 1411, "name": "EX Dragon Frontiers", "abbreviation": "DF"},
    {"groupId": 1373, "name": "Team Rocket", "abbreviation": "TR"},
    {"groupId": 23095, "name": "Ash vs Team Rocket Deck Kit (JP Exclusive)",
     "abbreviation": "AVTR"},
    {"groupId": 1393, "name": "EX Ruby and Sapphire", "abbreviation": "RS"},
    {"groupId": 1375, "name": "Expedition", "abbreviation": "EX"},
    # dois groups de promo com a MESMA abbr PR — razão de wiz/bog ficarem fora
    {"groupId": 1418, "name": "WoTC Promo", "abbreviation": "PR"},
    {"groupId": 1455, "name": "Best of Promos", "abbreviation": "PR"},
]


def test_vintage_g6_abbr_map_resolves_uniquely():
    """Os 5 sets vintage mapeados no v2.26 resolvem pro group CERTO via abbr,
    mesmo onde o fallback por nome é ambíguo ou não casa."""
    from cardtrader_scanner import resolve_tcgcsv_group_id
    cases = [
        (["base1"], "Base Set", 604),          # nome ⊂ "Base Set 2" (ambíguo)
        (["base5"], "Team Rocket", 1373),      # nome ⊂ deck kit JP (ambíguo)
        (["ex3"], "EX Dragon", 1376),          # nome ⊂ "EX Dragon Frontiers"
        (["ex1"], "EX Ruby & Sapphire", 1393),  # "&" vs "and" (nome não casa)
        (["ecard1"], "Expedition Base Set", 1375),  # nome CT ≠ nome tcgcsv
    ]
    for codes, ct_name, expected_gid in cases:
        gid = resolve_tcgcsv_group_id(codes, ct_name, _VINTAGE_GROUPS)
        assert gid == expected_gid, (codes, ct_name, gid)


def test_vintage_name_fallback_alone_would_fail_or_mislead():
    """Prova de que o mapa é NECESSÁRIO: sem abbr conhecida, os mesmos nomes
    não resolvem (ambíguo/no-match) — o v2.26 não depende de sorte."""
    from cardtrader_scanner import resolve_tcgcsv_group_id
    for name in ["Base Set", "Team Rocket", "EX Dragon",
                 "EX Ruby & Sapphire", "Expedition Base Set"]:
        gid = resolve_tcgcsv_group_id(["unknown"], name, _VINTAGE_GROUPS)
        assert gid is None, (name, gid)


def test_wiz_bog_stay_unmapped_shared_pr_abbr():
    """wiz/bog NÃO entram no mapa: abbr PR é compartilhada — mapear chutaria
    um group de promo errado. Ficam sem referência (rotulados, nunca preço
    inventado)."""
    from cardtrader_scanner import PTCG_SETCODE_TO_TCGCSV_ABBR
    mapped_abbrs = set(PTCG_SETCODE_TO_TCGCSV_ABBR.values())
    assert "PR" not in mapped_abbrs, (
        "abbr PR (compartilhada por ~8 groups de promo) mapeada — "
        "unique-match-only violado"
    )


# ─────── (7) chave variant-aware — colisão série H / sufixo a/b (v2.26) ───────
def test_tcgcsv_collector_key_normalization():
    """Chave preserva letras e normaliza zero-padding IGUAL nos dois lados."""
    from cardtrader_scanner import tcgcsv_collector_key as k
    # (raw CT ou tcgcsv) → chave
    cases = [
        ("012/147", "12"),        # regular zero-padded
        ("12", "12"),             # regular sem pad
        ("H12/H32", "H12"),       # série H ≠ regular (a colisão original)
        ("0H2/H32", "H2"),        # formato CT zero-padded da série H
        ("H08/H32", "H8"),        # zero-pad interno do tcgcsv
        ("074a/147", "74A"),      # sufixo a/b preservado
        ("95b/147", "95B"),
        ("SIR | 161/131", "161"),  # string suja com rarity
        ("0", "0"),
        ("", ""),
    ]
    for raw, expected in cases:
        assert k(raw) == expected, (raw, k(raw), expected)


def test_ecard_h_series_no_collision_end_to_end():
    """Cenário REAL do scan 2026-08-22 (Aquapolis): Exeggutor 012/147 e Hypno
    H12/H32 têm o mesmo numerador em dígitos ("12"). Com a chave digits-only o
    last-wins precificava o Exeggutor com a referência do Hypno ($229.99 falso).
    Com a chave variant-aware cada listing casa a SUA carta."""
    products = _fake_products({85354: "012/147", 86248: "H12/H32"})
    prices = _fake_prices([
        (85354, "Normal", 3.50),      # Exeggutor regular
        (86248, "Holofoil", 229.99),  # Hypno H12 (holo)
    ])
    prov = _provider_with(_fake_groups(), products, prices)
    ok = prov.prefill_set("asc", ["me2pt5"], "Ascended Heroes")
    assert ok
    # listing regular → preço do regular, link do regular
    p = prov.market_price_usd("Exeggutor", "asc", "012/147",
                              foil=False, rarity="Rare")
    assert p == 3.50, p
    assert prov.last_tcg_url == "https://www.tcgplayer.com/product/85354"
    # listing série H (formato CT zero-padded "0H12") → preço do H
    p = prov.market_price_usd("Hypno", "asc", "H12/H32",
                              foil=False, rarity="Holo Rare")
    assert p == 229.99, p
    assert prov.last_tcg_url == "https://www.tcgplayer.com/product/86248"


def test_ecard_ab_suffix_no_collision():
    """Sufixos a/b (e-Card): 74a e 74b são cartas distintas com preços
    distintos — nunca compartilham referência."""
    products = _fake_products({1: "074a/147", 2: "074b/147"})
    prices = _fake_prices([(1, "Normal", 5.0), (2, "Normal", 50.0)])
    prov = _provider_with(_fake_groups(), products, prices)
    assert prov.prefill_set("asc", ["me2pt5"], "Ascended Heroes")
    pa = prov.market_price_usd("Drowzee", "asc", "74a/147",
                               foil=False, rarity="Common")
    pb = prov.market_price_usd("Drowzee", "asc", "74b/147",
                               foil=False, rarity="Common")
    assert pa == 5.0 and pb == 50.0, (pa, pb)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
