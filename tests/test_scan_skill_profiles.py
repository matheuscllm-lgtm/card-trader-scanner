# -*- coding: utf-8 -*-
"""Trava os 6 grupos do skill /scan (.claude/commands/scan.md) contra a fonte
de verdade do scanner. O universo dos grupos é derivado por REGRA de
SET_ALIAS_TO_PTCG + VINTAGE_SET_CODES (128 códigos CT com referência de preço
real, sem armadilha): se um set novo ganhar alias no scanner e não for alocado
num grupo, ou um código for editado de cabeça no skill, a suíte quebra — de
propósito. O skill existe pra eliminar heterogeneidade; ele não pode divergir
silenciosamente do que o scanner realmente resolve."""

import re
from pathlib import Path

from cardtrader_scanner import VINTAGE_SET_CODES

REPO = Path(__file__).resolve().parent.parent
SKILL = (REPO / ".claude" / "commands" / "scan.md").read_text(encoding="utf-8")
SRC = (REPO / "cardtrader_scanner.py").read_text(encoding="utf-8")


def _alias_map():
    """Chaves de SET_ALIAS_TO_PTCG (código CT → primeiro alvo ptcg)."""
    i = SRC.index("SET_ALIAS_TO_PTCG = {")
    j = SRC.index("{", i)
    depth = 0
    for k in range(j, len(SRC)):
        if SRC[k] == "{":
            depth += 1
        elif SRC[k] == "}":
            depth -= 1
            if depth == 0:
                break
    body = SRC[j:k + 1]
    pairs = re.findall(r'"([a-z0-9]+)":\s*\[([^\]]*)\]', body)
    return {ct: re.findall(r'"([^"]+)"', v)[0] for ct, v in pairs}


def _universe():
    """Regra canônica do universo dos grupos (ver docstring do módulo)."""
    alias = _alias_map()
    wcd = {c for c in alias if c.startswith("wcd")}
    mcd = {c for c in alias if re.match(r"^mc\d", c)}
    pdup = {c for c in alias
            if c.startswith("p") and c[1:] in alias and alias[c] == alias[c[1:]]}
    return (set(alias) | set(VINTAGE_SET_CODES)) - wcd - mcd - pdup


def _groups():
    """Grupos G1..G6 do skill: linhas `--sets ...` dos code fences, na ordem."""
    lines = re.findall(r"^\s*--sets ([a-z0-9 ]+?) \\$", SKILL, re.MULTILINE)
    return [ln.split() for ln in lines]


def test_six_groups_partition_universe_exactly():
    groups = _groups()
    assert len(groups) == 6, f"esperava 6 grupos no skill, achei {len(groups)}"
    allg = [c for g in groups for c in g]
    assert len(allg) == len(set(allg)), "código duplicado entre grupos"
    universe = _universe()
    assert set(allg) == universe, (
        "grupos != universo canônico: "
        f"faltando {sorted(universe - set(allg))}, "
        f"sobrando {sorted(set(allg) - universe)}"
    )


def test_group_size_cap_fits_2h30():
    for n, g in enumerate(_groups(), 1):
        assert 0 < len(g) <= 22, (
            f"G{n} tem {len(g)} sets (cap 22 ≈ 2h15-2h30 local)"
        )


def test_group1_is_newest_and_includes_chaos_rising():
    g1 = _groups()[0]
    for required in ("cri", "por", "asc", "meg"):
        assert required in g1, f"{required!r} fora do G1 (mais recente)"


def test_canonical_values_present_in_every_scan_command():
    fences = re.findall(r"```bash\n(.*?)```", SKILL, re.DOTALL)
    scan_cmds = [f for f in fences if "cardtrader_scanner.py" in f]
    assert len(scan_cmds) == 6, "esperava exatamente os 6 comandos de grupo"
    for cmd in scan_cmds:
        for flag in ("--threshold 0.30", "--validate-top 30",
                     "--min-net-margin 0.20"):
            assert flag in cmd, f"comando sem o valor canônico {flag!r}:\n{cmd}"
    assert "--top-md 50" in SKILL
