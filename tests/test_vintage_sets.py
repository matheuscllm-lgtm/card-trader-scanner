#!/usr/bin/env python3
"""
test_vintage_sets.py — v2.21 (2026-06-21)

Cobre a lista curada vintage core (VINTAGE_SET_CODES), o helper puro
filter_vintage_sets (suporte de --vintage) e os aliases pokemontcg.io novos
(bs→base1, si→si1, bog→bp). Tudo offline (sem rede).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cardtrader_scanner as scanner  # noqa: E402

ALIASES = scanner.PokemonTcgIoProvider.SET_ALIAS_TO_PTCG


def _exps(*codes):
    return [{"code": c, "name": c} for c in codes]


def test_vintage_list_covers_three_eras():
    v = set(scanner.VINTAGE_SET_CODES)
    # WOTC essenciais
    assert {"bs", "ju", "fo", "b2", "tr", "g1", "g2", "n1", "n2", "n3", "n4", "lc"} <= v
    # e-Card trio
    assert {"ex", "aq", "skg"} <= v
    # EX Series completa (16): inclui dr (EX Dragon) e df (Dragon Frontiers)
    assert {"rs", "ss", "dr", "exma", "hl", "rg", "trr", "dx",
            "em", "uf", "ds", "lm", "hp", "cg", "df", "pk"} <= v
    assert len(scanner.VINTAGE_SET_CODES) == len(set(scanner.VINTAGE_SET_CODES)), "sem duplicatas"


def test_filter_keeps_only_vintage():
    exps = _exps("sv1", "hl", "bs", "dr", "df", "par", "xyz")
    out = [e["code"] for e in scanner.filter_vintage_sets(exps)]
    assert set(out) == {"hl", "bs", "dr", "df"}
    assert "sv1" not in out and "par" not in out and "xyz" not in out


def test_filter_preserves_curated_order_not_catalog_order():
    # Catálogo em ordem arbitrária; saída deve seguir VINTAGE_SET_CODES.
    exps = _exps("hl", "bs", "df", "dr")  # bs vem antes de dr/hl/df na lista curada
    out = [e["code"] for e in scanner.filter_vintage_sets(exps)]
    idx = {c: i for i, c in enumerate(scanner.VINTAGE_SET_CODES)}
    assert out == sorted(out, key=lambda c: idx[c])
    assert out[0] == "bs"  # WOTC primeiro


def test_filter_case_insensitive_and_tolerates_missing_code():
    exps = [{"code": "HL"}, {"code": None}, {"name": "no code"}, {"code": "DR"}]
    out = [e.get("code") for e in scanner.filter_vintage_sets(exps)]
    assert out == ["DR", "HL"] or out == ["HL", "DR"] or set(out) == {"HL", "DR"}
    # nenhum None/ausente passa
    assert None not in out


def test_filter_custom_codes_param():
    exps = _exps("hl", "bs", "sv1")
    out = [e["code"] for e in scanner.filter_vintage_sets(exps, vintage_codes=["bs"])]
    assert out == ["bs"]


def test_new_aliases_present_and_correct():
    assert ALIASES.get("bs") == ["base1"]
    assert ALIASES.get("si") == ["si1"]
    assert ALIASES.get("bog") == ["bp"]
    # Pré-existentes que a lista vintage depende
    assert ALIASES.get("dr") == ["ex3"]
    assert ALIASES.get("df") == ["ex15"]
    assert ALIASES.get("wiz") == ["basep"]


def test_vintage_flag_registered():
    assert _parse(["--vintage"]).vintage is True
    assert _parse([]).vintage is False


def test_vintage_and_skip_backcatalog_are_disjoint():
    # As duas listas NÃO podem ter overlap, senão o guard de exclusão mútua
    # estaria escondendo um caso legítimo.
    assert not (set(scanner.VINTAGE_SET_CODES) & set(scanner.PRIORITY_SET_CODES))


def _parse(argv):
    import sys as _sys
    old = _sys.argv
    try:
        _sys.argv = ["cardtrader_scanner.py"] + argv
        return scanner.parse_args()
    finally:
        _sys.argv = old


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
