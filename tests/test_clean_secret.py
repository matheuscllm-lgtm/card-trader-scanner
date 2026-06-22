#!/usr/bin/env python3
"""Família de erro recorrente cross-scanner #1: segredo (CT_JWT / API key) com
BOM/zero-width derruba 100% das chamadas HTTP.

O `requests` codifica headers em latin-1. Um BOM (U+FEFF) grudado no token
(arquivo .env salvo como UTF-8-with-BOM, copy/paste do site) vira
`UnicodeEncodeError: 'latin-1' codec can't encode '\\ufeff'` em TODA chamada →
o scan fica "verde mas vazio". `str.strip()` NÃO remove BOM (U+FEFF não é
whitespace pra Python), por isso `_clean_secret` trata explicitamente.

Os caracteres invisíveis são construídos por codepoint (`chr(0xFEFF)`) de
propósito — NADA de invisível literal no fonte (espelha a nota do teste do MYP).

Roda via pytest E standalone (python tests/test_clean_secret.py).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cardtrader_scanner as sc  # noqa: E402

BOM = chr(0xFEFF)   # U+FEFF byte-order mark
ZWSP = chr(0x200B)  # U+200B zero-width space


def test_strips_bom_prefix():
    assert sc._clean_secret(BOM + "eyJtoken") == "eyJtoken"


def test_strips_zero_width_and_whitespace():
    assert sc._clean_secret("eyJtoken" + ZWSP) == "eyJtoken"
    assert sc._clean_secret("  eyJtoken\n") == "eyJtoken"
    assert sc._clean_secret(BOM + "  eyJtoken  " + ZWSP) == "eyJtoken"


def test_clean_value_unchanged():
    # token válido sem lixo invisível → no-op.
    assert sc._clean_secret("eyJabc.def.ghi") == "eyJabc.def.ghi"


def test_empty_or_none_becomes_none():
    assert sc._clean_secret(None) is None
    assert sc._clean_secret("") is None
    assert sc._clean_secret(BOM) is None          # só BOM → vazio → None
    assert sc._clean_secret("  " + ZWSP) is None   # só lixo → None


def test_cleaned_secret_is_latin1_encodable():
    """O coração do bug: o valor cru com BOM QUEBRA o header latin-1; o limpo NÃO."""
    raw = BOM + "eyJtoken"
    # Fixture válida: o cru REALMENTE quebraria num header HTTP (latin-1).
    raised = False
    try:
        raw.encode("latin-1")
    except UnicodeEncodeError:
        raised = True
    assert raised, "fixture inválida: BOM deveria quebrar latin-1"
    # Pós-fix: o valor limpo é latin-1-encodável (não derruba a chamada).
    sc._clean_secret(raw).encode("latin-1")  # não deve levantar


def _run() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passaram")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
