"""v2.29 — códigos CT de sets JAPONESES que colidem com setcodes pokemontcg.io.

Sonda da API CT em 2026-10-03: no CardTrader `sv3/sv6/sv7/sv8/sv9/sv10` são os
sets JP (Ruler of the Black Flame, Mask of Change, Stellar Miracle, Super
Electric Breaker, Battle Partners, The Glory of Team Rocket). O scanner usava o
código CT como setcode pokemontcg.io por identidade → `sv8` virava Surging
Sparks (SSP) e o nº 057 casava **Pikachu ex 057/191** pra uma oferta de
**Palossand ex** JP 057 (caso real do run zh-CN de 2026-10-03, razão 3,6×
falsa). Referência de OUTRA carta = pior classe de erro da frota.

Contrato: esses códigos NUNCA resolvem por identidade — nem no provider
pokemontcg.io, nem na ponte tcgcsv. Sem mapa explícito → sem referência.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cardtrader_scanner as sc  # noqa: E402

JP_COLLISIONS = ["sv3", "sv6", "sv7", "sv8", "sv9", "sv10"]

GROUPS = [
    {"groupId": 23651, "abbreviation": "SSP", "name": "SV08: Surging Sparks"},
    {"groupId": 24073, "abbreviation": "JTG", "name": "SV09: Journey Together"},
    {"groupId": 23237, "abbreviation": "MEW", "name": "SV: Scarlet & Violet 151"},
]


def test_jp_collision_codes_have_no_ptcg_identity():
    s = sc.Scanner.__new__(sc.Scanner)
    for code in JP_COLLISIONS:
        assert s._ptcg_setcodes_for(code) == [], code


def test_jp_collision_codes_resolve_no_tcgcsv_group():
    s = sc.Scanner.__new__(sc.Scanner)
    for code, name in [("sv8", "Super Electric Breaker"), ("sv9", "Battle Partners")]:
        gids = sc.resolve_tcgcsv_group_ids(code, s._ptcg_setcodes_for(code), name, GROUPS)
        assert gids == [], (code, gids)


def test_english_ct_codes_still_resolve():
    s = sc.Scanner.__new__(sc.Scanner)
    assert sc.resolve_tcgcsv_group_ids("ssp", s._ptcg_setcodes_for("ssp"), "Surging Sparks", GROUPS) == [23651]
    assert sc.resolve_tcgcsv_group_ids("mew", s._ptcg_setcodes_for("mew"), "151", GROUPS) == [23237]


def test_pokemontcg_expected_sets_exclude_jp_collision_identity():
    """Provider pokemontcg.io monta `set.id:<x>` a partir destes conjuntos."""
    for code in JP_COLLISIONS:
        assert code not in sc.ptcg_expected_sets(code), code
    assert "sv8" in sc.ptcg_expected_sets("ssp")      # alias EN segue valendo
    assert "ssp" in sc.ptcg_expected_sets("ssp")
