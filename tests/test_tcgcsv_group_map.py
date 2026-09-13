#!/usr/bin/env python3
"""
test_tcgcsv_group_map.py — v2.28 (2026-09-12)

Incidente 2026-09-12: com a pokemontcg.io em 500/502, o scan rodou com
`--provider tcgcsv` e 4 sets saíram SEM referência de preço — svi (Scarlet &
Violet), kss (XY Kalos Starter Set), gen (Generations) e evo (Evolutions).
Causa: o CT só tinha abreviação tcgcsv pra ~21 dos ~130 sets do universo; o
resto dependia do fallback por NOME, que é ambíguo justamente nesses casos
("Evolutions" ⊂ "Prismatic Evolutions"; "Scarlet & Violet" ⊂ vários groups SV;
"XY Kalos Starter Set" ≠ "Kalos Starter Set"; GEN = 2 groups). O MYP não sofria
porque tem o mapa de abreviações ampliado (v5.16, 106 entradas) + complemento
pokemontcg.io no modo `auto`.

Contratos (offline — fixture = snapshot real de /groups em
tests/fixtures/tcgcsv_groups_pokemon.json):
  (1) COBERTURA: todo código CT do universo dos grupos do /scan (+ menu do
      skill card-trader-scan) tem groupId(s) explícito(s) OU está na lista de
      exclusão documentada (com motivo);
  (2) todo groupId mapeado EXISTE no snapshot de /groups;
  (3) regressão do incidente: svi/kss/evo/gen resolvem com os nomes CT reais;
  (4) abreviação compartilhada por >1 group NÃO pega o primeiro (unique-only);
  (5) set multi-group (gen = Generations + Radiant Collection) é mesclado; um
      número de colecionador presente em >1 group é DESCARTADO (nunca chuta).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
for p in (REPO_ROOT, TESTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import cardtrader_scanner as sc  # noqa: E402
from cardtrader_scanner import (  # noqa: E402
    CT_SET_TO_TCGCSV_GROUP_IDS,
    TCGCSV_EXCLUDED_CT_SETS,
    TcgCsvFallbackProvider,
    resolve_tcgcsv_group_id,
    resolve_tcgcsv_group_ids,
)
from test_scan_skill_profiles import _universe  # noqa: E402

FIXTURE = TESTS_DIR / "fixtures" / "tcgcsv_groups_pokemon.json"

# Códigos do menu do skill user-level card-trader-scan que não têm alias
# pokemontcg.io (por isso fora do _universe()) mas são rastreados pelo operador.
SKILL_MENU_EXTRA = {"ar", "c25", "dp", "la", "md"}


def _groups():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["results"]


def _names_by_id():
    return {g["groupId"]: g["name"] for g in _groups()}


# ───────────────────────────── (1) cobertura ────────────────────────────────
def test_every_universe_code_has_explicit_groups_or_documented_exclusion():
    universe = set(_universe()) | SKILL_MENU_EXTRA
    missing = sorted(
        c for c in universe
        if c not in CT_SET_TO_TCGCSV_GROUP_IDS and c not in TCGCSV_EXCLUDED_CT_SETS
    )
    assert not missing, f"códigos sem groupId tcgcsv explícito nem exclusão: {missing}"


def test_exclusions_have_reason_and_do_not_overlap_map():
    for code, reason in TCGCSV_EXCLUDED_CT_SETS.items():
        assert isinstance(reason, str) and len(reason) > 10, code
        assert code not in CT_SET_TO_TCGCSV_GROUP_IDS, code


# ───────────────────────────── (2) ids existem ──────────────────────────────
def test_every_mapped_group_id_exists_in_groups_snapshot():
    names = _names_by_id()
    bad = {c: ids for c, ids in CT_SET_TO_TCGCSV_GROUP_IDS.items()
           if not ids or any(i not in names for i in ids)}
    assert not bad, f"groupIds inexistentes no /groups: {bad}"


# ─────────────────────── (3) regressão do incidente ─────────────────────────
def test_incident_sets_resolve_to_the_right_groups():
    groups = _groups()
    names = _names_by_id()
    cases = {
        # código CT: (ptcg setcodes, nome CT real do log, nomes tcgcsv esperados)
        "svi": (["sv1"], "Scarlet & Violet", ["SV01: Scarlet & Violet Base Set"]),
        "kss": (["xy0"], "XY Kalos Starter Set", ["Kalos Starter Set"]),
        "evo": (["xy12"], "Evolutions", ["XY - Evolutions"]),
        "gen": (["g1"], "Generations",
                ["Generations", "Generations: Radiant Collection"]),
    }
    for code, (ptcg, ct_name, expected) in cases.items():
        ids = resolve_tcgcsv_group_ids(code, ptcg, ct_name, groups)
        assert [names[i] for i in ids] == expected, (code, ids)


def test_subset_split_sets_include_their_prefixed_subset_groups():
    """Sets cujo subset o TCGplayer separa em outro group, com numeração
    prefixada própria (RC##, SV##) que o CT lista sob o MESMO código:
    gen/ltr (Radiant Collection) e hif/shf (Shiny Vault — as listings caras do
    set; ver memória de 2026-07-06: abortavam por 40 misses)."""
    names = _names_by_id()
    expected = {
        "gen": ["Generations", "Generations: Radiant Collection"],
        "ltr": ["Legendary Treasures", "Legendary Treasures: Radiant Collection"],
        "hif": ["Hidden Fates", "Hidden Fates: Shiny Vault"],
        "shf": ["Shining Fates", "Shining Fates: Shiny Vault"],
    }
    for code, want in expected.items():
        assert [names[i] for i in CT_SET_TO_TCGCSV_GROUP_IDS[code]] == want, code
    # a mesclagem só é segura porque a chave preserva o prefixo do subset
    assert sc.tcgcsv_collector_key("SV001/SV122") == "SV1" != sc.tcgcsv_collector_key("1/72")
    assert sc.tcgcsv_collector_key("RC11/RC32") == "RC11" != sc.tcgcsv_collector_key("11/83")


def test_productid_resolver_uses_explicit_map_single_group_only():
    """tcgcsv_productid (join DH) usa a MESMA resolução explícita — mas a chave
    dele é só-dígitos (SV1 → 1), então set multi-group fica sem productId
    (honesto) em vez de misturar subset com set base."""
    import tcgcsv_productid as tpid

    groups = _groups()
    products = {"results": [
        {"productId": 555, "extendedData": [{"name": "Number", "value": "11/108"}]},
    ]}
    prices = {"results": [
        {"productId": 555, "subTypeName": "Holofoil", "marketPrice": 100.0},
    ]}
    calls = []

    def fetch_json(path):
        calls.append(path)
        return products if path.endswith("/products") else prices

    r = tpid.ProductIdResolver(fetch_json=fetch_json, fetch_groups=lambda: groups)
    # evo: CT "Evolutions" é ambíguo por nome; o id explícito 1842 resolve.
    assert r.resolve("evo", "Evolutions", "011/108", "holofoil") == "555"
    assert calls[0] == "1842/products"
    # gen: 2 groups → sem productId (nunca mistura RC com o set base)
    assert r.resolve("gen", "Generations", "11/83", "holofoil") is None


def test_ambiguous_abbr_sets_resolve_by_explicit_id():
    """Abbr compartilhada no /groups: RR, BKP, CL, LTR — o id explícito decide."""
    groups = _groups()
    names = _names_by_id()
    assert [names[i] for i in resolve_tcgcsv_group_ids("rr", ["pl2"], "Rising Rivals", groups)] \
        == ["Rising Rivals"]
    assert [names[i] for i in resolve_tcgcsv_group_ids("trr", ["ex7"], "Team Rocket Returns", groups)] \
        == ["EX Team Rocket Returns"]
    assert [names[i] for i in resolve_tcgcsv_group_ids("bkp", ["xy9"], "BREAKpoint", groups)] \
        == ["XY - BREAKpoint"]
    assert [names[i] for i in resolve_tcgcsv_group_ids("clo", ["col1"], "Call of Legends", groups)] \
        == ["Call of Legends"]


def test_unmapped_code_keeps_legacy_single_group_resolution():
    """Código fora do mapa explícito cai no resolvedor legado (abbr/nome único)."""
    groups = [{"groupId": 100, "name": "ME: Ascended Heroes", "abbreviation": "ASC"}]
    assert resolve_tcgcsv_group_ids("zzz", ["me2pt5"], "Ascended Heroes", groups) == [100]
    assert resolve_tcgcsv_group_ids("zzz", ["nope"], "Nada", groups) == []


def test_explicit_id_missing_from_groups_falls_back_never_invented():
    groups = [{"groupId": 1842, "name": "XY - Evolutions", "abbreviation": "EVO"}]
    assert resolve_tcgcsv_group_ids("evo", ["xy12"], "Evolutions", groups) == [1842]
    assert resolve_tcgcsv_group_ids("evo", ["xy12"], "Evolutions", []) == []
    # id explícito ausente (dump renumerado) → cai no legado unique-only
    renum = [{"groupId": 9999, "name": "XY - Evolutions", "abbreviation": "EVO"}]
    assert resolve_tcgcsv_group_ids("evo", ["xy12"], "Evolutions", renum) == [9999]
    # multi-group pela metade → legado; "Generations" casa 1 group só aqui
    half = [{"groupId": 1728, "name": "Generations", "abbreviation": "GEN"}]
    assert resolve_tcgcsv_group_ids("gen", ["g1"], "Generations", half) == [1728]


def test_excluded_set_never_resolves_even_with_unique_name():
    groups = [{"groupId": 2867, "name": "Celebrations", "abbreviation": "CLB"}]
    assert resolve_tcgcsv_group_ids("c25", [], "Celebrations", groups) == []


# ────────────────────── (4) abbr compartilhada = unique ─────────────────────
def test_shared_abbr_does_not_pick_first_group(monkeypatch):
    groups = [
        {"groupId": 1728, "name": "Generations", "abbreviation": "GEN"},
        {"groupId": 1729, "name": "Generations: Radiant Collection", "abbreviation": "GEN"},
    ]
    monkeypatch.setitem(sc.PTCG_SETCODE_TO_TCGCSV_ABBR, "g1", "GEN")
    # abbr GEN casa 2 groups → não é match único; nome "Generations" também
    # casa 2 → None (antes: devolvia 1728 silenciosamente).
    assert resolve_tcgcsv_group_id(["g1"], "Generations", groups) is None


# ─────────────────── (5) multi-group mesclado + colisão ─────────────────────
def _multi_group_provider(groups, per_group):
    """per_group: {groupId: (products_json, prices_json)} — session.get mockado."""
    prov = TcgCsvFallbackProvider.__new__(TcgCsvFallbackProvider)
    prov.cache = MagicMock()
    prov._groups = None
    prov._groups_fetched = False
    prov._set_index = {}
    prov._pid_index = {}
    prov.last_price_source = None
    prov.last_tcg_url = None
    prov.last_variant_used = None
    prov.last_ptcg_rarity = None
    prov.last_set_release_date = None
    prov.last_normal_market = None

    def fake_get(url, headers=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        if url.endswith("/groups"):
            resp.json.return_value = {"results": groups}
            return resp
        gid = int(url.rstrip("/").split("/")[-2])
        kind = url.rstrip("/").split("/")[-1]
        products, prices = per_group[gid]
        resp.json.return_value = products if kind == "products" else prices
        return resp

    prov.session = MagicMock()
    prov.session.get.side_effect = fake_get
    return prov


def _products(numbers):
    return {"results": [
        {"productId": pid, "name": f"Card {pid}",
         "extendedData": [{"name": "Number", "value": num}]}
        for pid, num in numbers.items()
    ]}


def _prices(rows):
    return {"results": [
        {"productId": pid, "subTypeName": sub, "marketPrice": mkt,
         "lowPrice": mkt, "midPrice": mkt}
        for (pid, sub, mkt) in rows
    ]}


def test_gen_prefill_merges_main_and_radiant_collection():
    groups = [
        {"groupId": 1728, "name": "Generations", "abbreviation": "GEN"},
        {"groupId": 1729, "name": "Generations: Radiant Collection", "abbreviation": "GEN"},
    ]
    per_group = {
        1728: (_products({1: "11/83"}), _prices([(1, "Holofoil", 12.0)])),
        1729: (_products({2: "RC11/RC32"}), _prices([(2, "Holofoil", 30.0)])),
    }
    prov = _multi_group_provider(groups, per_group)
    assert prov.prefill_set("gen", ["g1"], "Generations") is True
    assert prov.market_price_usd("X", "gen", "11/83", rarity="Rare Holo") == 12.0
    assert prov.market_price_usd("Y", "gen", "RC11/RC32", rarity="Rare Holo") == 30.0
    assert prov.last_tcg_url == "https://www.tcgplayer.com/product/2"


def test_multi_group_colliding_collector_key_is_dropped(monkeypatch):
    groups = [
        {"groupId": 1, "name": "Main", "abbreviation": "AAA"},
        {"groupId": 2, "name": "Sub", "abbreviation": "BBB"},
    ]
    monkeypatch.setitem(sc.CT_SET_TO_TCGCSV_GROUP_IDS, "zz", (1, 2))
    per_group = {
        1: (_products({10: "4/25", 11: "5/25"}),
            _prices([(10, "Holofoil", 5.0), (11, "Holofoil", 6.0)])),
        2: (_products({20: "4/102"}), _prices([(20, "Holofoil", 400.0)])),
    }
    prov = _multi_group_provider(groups, per_group)
    assert prov.prefill_set("zz", [], "Whatever") is True
    # "4" existe nos dois groups → ambíguo → sem preço (nunca 5.0 nem 400.0)
    assert prov.market_price_usd("A", "zz", "4/25", rarity="Rare Holo") is None
    assert prov.market_price_usd("B", "zz", "5/25", rarity="Rare Holo") == 6.0
