# -*- coding: utf-8 -*-
"""Trava os 5 grupos do skill /scan-dbz (.claude/commands/scan-dbz.md) contra
a fonte de verdade do scanner. O universo dos grupos é EXATAMENTE o mapa
verificado DBZ_SET_TO_TCGCSV (88 códigos CT com referência tcgcsv): se um set
novo ganhar entrada no mapa e não for alocado num grupo, ou um código for
editado de cabeça no skill, a suíte quebra — de propósito (mesmo contrato do
test_scan_skill_profiles.py do /scan Pokémon)."""

import re
from pathlib import Path

from cardtrader_scanner import DBZ_SET_TO_TCGCSV

REPO = Path(__file__).resolve().parent.parent
SKILL = (REPO / ".claude" / "commands" / "scan-dbz.md").read_text(encoding="utf-8")


def _groups():
    """Grupos G1..G5 do skill: linhas `--sets ...` dos code fences, na ordem.
    (Inclui hífen no charset — código real `bt-27`.)"""
    lines = re.findall(r"^\s*--sets ([a-z0-9\- ]+?) \\$", SKILL, re.MULTILINE)
    return [ln.split() for ln in lines]


def test_five_groups_partition_universe_exactly():
    groups = _groups()
    assert len(groups) == 5, f"esperava 5 grupos no skill, achei {len(groups)}"
    allg = [c for g in groups for c in g]
    assert len(allg) == len(set(allg)), "código duplicado entre grupos"
    universe = set(DBZ_SET_TO_TCGCSV)
    assert set(allg) == universe, (
        "grupos != mapa DBZ_SET_TO_TCGCSV: "
        f"faltando {sorted(universe - set(allg))}, "
        f"sobrando {sorted(set(allg) - universe)}"
    )


def test_group_size_cap():
    for n, g in enumerate(_groups(), 1):
        assert 0 < len(g) <= 24, f"G{n} tem {len(g)} sets (cap 24)"


def test_group1_is_fusion_world_completo():
    """G1 = TODO o Fusion World (fb/fs/sb) e NADA de Masters — o jogo quente
    fica num grupo só, priorizável."""
    groups = _groups()
    g1 = set(groups[0])
    fw = {c for c in DBZ_SET_TO_TCGCSV if re.match(r"^(fb|fs|sb|st)", c)}
    assert g1 == fw, f"G1 != Fusion World: faltando {sorted(fw - g1)}, sobrando {sorted(g1 - fw)}"
    for other in groups[1:]:
        assert not set(other) & fw, "set Fusion World fora do G1"


def test_masters_groups_ordered_by_recency():
    """G2 tem os mais novos (bt31); G5 tem a gênese (bt1)."""
    groups = _groups()
    assert "bt31" in groups[1], "bt31 fora do G2 (Masters recente)"
    assert "bt1" in groups[4], "bt1 fora do G5 (gênese)"


def test_canonical_values_present_in_every_scan_command():
    fences = re.findall(r"```bash\n(.*?)```", SKILL, re.DOTALL)
    scan_cmds = [f for f in fences if "cardtrader_scanner.py" in f]
    assert len(scan_cmds) == 5, "esperava exatamente os 5 comandos de grupo"
    for cmd in scan_cmds:
        for flag in ("--game dragonball", "--threshold 0.30",
                     "--validate-top 30", "--min-net-margin 0.20"):
            assert flag in cmd, f"comando sem o valor canônico {flag!r}:\n{cmd}"
    assert "--top-md 50" in SKILL
