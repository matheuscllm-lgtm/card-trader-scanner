# -*- coding: utf-8 -*-
"""Trava os perfis do skill /scan (.claude/commands/scan.md) contra a fonte de
verdade do código e dos workflows. Se VINTAGE_SET_CODES ganhar/perder um set,
ou o default do daily-scan.yml mudar, o teste quebra até o skill ser realinhado
— de propósito: o skill existe pra eliminar heterogeneidade, então ele não pode
divergir silenciosamente do que o scanner/CI realmente rodam."""

import re
from pathlib import Path

from cardtrader_scanner import VINTAGE_SET_CODES

REPO = Path(__file__).resolve().parent.parent
SKILL = (REPO / ".claude" / "commands" / "scan.md").read_text(encoding="utf-8")
DAILY_YML = (REPO / ".github" / "workflows" / "daily-scan.yml").read_text(
    encoding="utf-8")


def _sets_lines():
    """Toda linha `--sets ...` dos code fences do skill (lista de códigos)."""
    return re.findall(r"^\s*--sets ([a-z0-9 ]+?) \\$", SKILL, re.MULTILINE)


def test_default_profile_sets_match_daily_workflow():
    m = re.search(r"default: '([a-z0-9 ]+)'", DAILY_YML)
    assert m, "default de sets não encontrado no daily-scan.yml"
    daily_default = m.group(1).split()
    lines = _sets_lines()
    assert lines, "nenhuma linha --sets encontrada no skill"
    assert lines[0].split() == daily_default, (
        "perfil padrão do skill != default do daily-scan.yml: "
        f"{lines[0].split()} vs {daily_default}"
    )


def test_vintage_blocks_partition_vintage_set_codes():
    lines = _sets_lines()
    assert len(lines) >= 3, "esperava padrão + 2 blocos vintage no skill"
    v1, v2 = lines[1].split(), lines[2].split()
    union = v1 + v2
    assert len(union) == len(set(union)), "código duplicado entre blocos vintage"
    assert set(union) == set(VINTAGE_SET_CODES), (
        "blocos vintage != VINTAGE_SET_CODES: "
        f"faltando {sorted(set(VINTAGE_SET_CODES) - set(union))}, "
        f"sobrando {sorted(set(union) - set(VINTAGE_SET_CODES))}"
    )


def test_canonical_values_present_in_every_scan_command():
    fences = re.findall(r"```bash\n(.*?)```", SKILL, re.DOTALL)
    scan_cmds = [f for f in fences if "cardtrader_scanner.py" in f]
    assert len(scan_cmds) >= 4, "esperava >=4 comandos de scan (padrão/completo/V1/V2)"
    for cmd in scan_cmds:
        for flag in ("--threshold 0.30", "--validate-top 30",
                     "--min-net-margin 0.20"):
            assert flag in cmd, f"comando de scan sem o valor canônico {flag!r}:\n{cmd}"
    assert "--top-md 50" in SKILL


def test_completo_profile_uses_skip_backcatalog():
    assert "--all-sets --skip-backcatalog" in SKILL
