#!/usr/bin/env python3
"""v2.17 (2026-06-20) tests — flag --skip-backcatalog (foco em sets recentes).

Cobre:
  - `filter_modern_sets(expansions)`: mantém só os codes em PRIORITY_SET_CODES
    (modernas/curadas), descarta back-catalog; preserva ordem; case-insensitive;
    tolera code ausente/None.
  - O parser registra `--skip-backcatalog` (default False; True quando passado).

Lição operacional (auditoria 2026-06-08): back-catalog = mercado eficiente =
~0 deal acionável → escanear só lançamentos novos. A flag corta ~832 → ~30 sets.

Roda de dois jeitos (espelha test_set_timeout_overrides.py):
    pytest tests/test_skip_backcatalog.py -v
    python tests/test_skip_backcatalog.py     # fallback standalone
"""
from __future__ import annotations

import sys
from pathlib import Path

# Repo root no sys.path (tests/ → ..)
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cardtrader_scanner as sc  # noqa: E402
from cardtrader_scanner import (  # noqa: E402
    PRIORITY_SET_CODES,
    filter_modern_sets,
)


def _exp(*codes):
    """Expansões fake no formato do catálogo CT (só o campo que importa: code)."""
    return [{"code": c, "name": f"set {c}"} for c in codes]


# ── filter_modern_sets ──────────────────────────────────────────────────
def test_keeps_priority_drops_backcatalog():
    """Mantém os modernos (sv1, scr); descarta os antigos (base1, n2, ecard1)."""
    exps = _exp("base1", "sv1", "n2", "scr", "ecard1")
    kept = [e["code"] for e in filter_modern_sets(exps)]
    assert kept == ["sv1", "scr"]


def test_preserves_input_order():
    """Não reordena — mantém a ordem de entrada dos sobreviventes."""
    exps = _exp("scr", "sv1", "par")  # todos priority, fora da ordem da const
    kept = [e["code"] for e in filter_modern_sets(exps)]
    assert kept == ["scr", "sv1", "par"]


def test_case_insensitive():
    """Code em maiúsculas casa com a const (minúscula); preserva o case original."""
    exps = _exp("SV1", "Scr", "BASE1")
    kept = [e["code"] for e in filter_modern_sets(exps)]
    assert kept == ["SV1", "Scr"]


def test_tolerates_missing_or_none_code():
    """code ausente/None/"" não quebra — é descartado (não casa priority)."""
    exps = [{"code": "sv1"}, {"code": None}, {"name": "sem code"}, {"code": ""}]
    kept = [e.get("code") for e in filter_modern_sets(exps)]
    assert kept == ["sv1"]


def test_empty_input_empty_output():
    assert filter_modern_sets([]) == []


def test_all_backcatalog_yields_empty():
    """Lista 100% back-catalog → vazio (não explode)."""
    assert filter_modern_sets(_exp("base1", "base2", "n2", "gym1")) == []


def test_custom_priority_codes_param():
    """O param priority_codes sobrescreve a const default."""
    exps = _exp("aaa", "bbb", "ccc")
    kept = [e["code"] for e in filter_modern_sets(exps, priority_codes=["bbb"])]
    assert kept == ["bbb"]


def test_default_uses_priority_set_codes():
    """Sem param, usa PRIORITY_SET_CODES (sanity: 'sfa' é curado e sobrevive)."""
    assert "sfa" in PRIORITY_SET_CODES  # guarda contra edição acidental da const
    kept = [e["code"] for e in filter_modern_sets(_exp("sfa", "xyzzy"))]
    assert kept == ["sfa"]


# ── argparse: a flag existe e tem o default certo ─────────────────────────
def _parse(argv):
    old = sys.argv
    sys.argv = ["cardtrader_scanner.py", *argv]
    try:
        return sc.parse_args()
    finally:
        sys.argv = old


def test_flag_defaults_false():
    assert _parse([]).skip_backcatalog is False


def test_flag_sets_true():
    assert _parse(["--skip-backcatalog"]).skip_backcatalog is True


def test_flag_combines_with_all_sets():
    args = _parse(["--all-sets", "--skip-backcatalog"])
    assert args.all_sets is True and args.skip_backcatalog is True


# ── standalone runner (espelha os outros testes do repo) ──────────────────
if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
