#!/usr/bin/env python3
"""Test (correção/robustez 2026-06-15 — candidato 5): erros TRANSIENTES da
pokemontcg.io (429 rate-limit, 5xx) NÃO podem virar "miss" de cobertura
silencioso. Eles devem:
  - ser retried com backoff bounded
  - se persistirem, levantar requests.Timeout (→ scan loop conta como
    pricing_failure, com detecção de mass-failure própria)
  - NUNCA poluir o contador de "misses consecutivos" (que aborta sets bons
    com no_coverage)

Status legítimo de "carta não existe" = 200 com data vazia → continua None
(miss real). 4xx ≠ 429 (ex 400 query malformada) = resposta legítima do
servidor → tratada como sem-match, sem exceção.

Estratégia: instancia PokemonTcgIoProvider com session/cache mockados e
monkey-patcha session.get pra devolver respostas controladas. Mede:
  - 429 persistente → requests.Timeout levantado por _search
  - 5xx persistente → requests.Timeout
  - 429 seguido de 200 → recupera (retorna match)
  - 200 vazio → None (miss real, sem exceção)
  - 404 → None (sem-match legítimo, sem exceção)

Usage:
    python scripts/test_ptcg_transient_errors.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import requests  # noqa: E402
import cardtrader_scanner as scanner_mod  # noqa: E402
from cardtrader_scanner import PokemonTcgIoProvider  # noqa: E402


class FakeResp:
    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {"data": [], "totalCount": 0}
        self.headers = headers or {}

    def json(self):
        return self._body


def _make_provider(responses):
    """responses: lista de FakeResp consumida em ordem a cada session.get."""
    p = PokemonTcgIoProvider.__new__(PokemonTcgIoProvider)
    p.session = MagicMock()
    p.cache = MagicMock()
    p.cache.get_price.return_value = None
    p.delay = 0.0
    p._last_call = 0.0
    it = iter(responses)
    # Última resposta repete (cobre retries que excedem a lista)
    last = {"r": None}

    def fake_get(url, params=None, timeout=None):
        try:
            last["r"] = next(it)
        except StopIteration:
            pass
        return last["r"]

    p.session.get = fake_get
    return p


# Acelera: zera sleeps reais do backoff durante o teste.
_orig_sleep = time.sleep
def _no_sleep(_s):
    return None


def test_persistent_429_raises_timeout():
    print("\n[test_persistent_429_raises_timeout]")
    p = _make_provider([FakeResp(429, headers={"Retry-After": "1"})] * 5)
    scanner_mod.time.sleep = _no_sleep
    try:
        raised = None
        try:
            p._search("Pikachu", "base1", "58")
        except requests.Timeout as e:
            raised = e
    finally:
        scanner_mod.time.sleep = _orig_sleep
    assert raised is not None, "429 persistente DEVE levantar requests.Timeout"
    print(f"  PASS — levantou {type(raised).__name__}")


def test_persistent_5xx_raises_timeout():
    print("\n[test_persistent_5xx_raises_timeout]")
    p = _make_provider([FakeResp(503)] * 5)
    scanner_mod.time.sleep = _no_sleep
    try:
        raised = None
        try:
            p._search("Charizard", "base1", "4")
        except requests.Timeout as e:
            raised = e
    finally:
        scanner_mod.time.sleep = _orig_sleep
    assert raised is not None, "5xx persistente DEVE levantar requests.Timeout"
    print(f"  PASS — levantou {type(raised).__name__}")


def test_429_then_200_recovers():
    print("\n[test_429_then_200_recovers]")
    hit = {
        "data": [{"id": "base1-58", "name": "Pikachu",
                  "number": "58",
                  "set": {"id": "base1", "printedTotal": 102},
                  "tcgplayer": {"prices": {"normal": {"market": 12.34}}}}],
        "totalCount": 1,
    }
    p = _make_provider([FakeResp(429, headers={"Retry-After": "1"}),
                        FakeResp(200, body=hit)])
    scanner_mod.time.sleep = _no_sleep
    try:
        card = p._search("Pikachu", "base1", "58")
    finally:
        scanner_mod.time.sleep = _orig_sleep
    assert card is not None and card.get("id") == "base1-58", \
        f"429→200 deve recuperar o match, got {card}"
    print("  PASS — recuperou após 1x 429")


def test_empty_200_is_real_miss_no_exception():
    print("\n[test_empty_200_is_real_miss_no_exception]")
    p = _make_provider([FakeResp(200, body={"data": [], "totalCount": 0})] * 5)
    card = p._search("NonexistentCard", "base1", "999")
    assert card is None, "200 vazio = miss real (None), sem exceção"
    print("  PASS — None sem exceção")


def test_400_is_no_match_no_exception():
    print("\n[test_400_is_no_match_no_exception]")
    # 4xx ≠ 429 (ex query malformada) = resposta legítima → sem-match, sem raise.
    p = _make_provider([FakeResp(400)] * 5)
    card = p._search("Weird:Name", "base1", "1")
    assert card is None, "400 = sem-match legítimo (None), sem exceção"
    print("  PASS — None sem exceção")


def main() -> int:
    failed = 0
    for fn in (
        test_persistent_429_raises_timeout,
        test_persistent_5xx_raises_timeout,
        test_429_then_200_recovers,
        test_empty_200_is_real_miss_no_exception,
        test_400_is_no_match_no_exception,
    ):
        try:
            fn()
        except AssertionError as e:
            print(f"  ASSERTION FAIL: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  EXCEPTION: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    if failed:
        print(f"\nFAIL: {failed} test(s) failed")
        return 1
    print(f"\nPASS: all pokemontcg.io transient-error tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
