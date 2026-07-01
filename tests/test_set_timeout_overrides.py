#!/usr/bin/env python3
"""v2.14 (2026-06-15) tests — overrides de timeout por SET (vintage churn fix).

Cobre o mecanismo que dá fôlego extra a sets vintage pesados SEM o operador ter
que passar `--per-set-timeout 20` manualmente toda vez.

Problema corrigido: sets como `df` (EX Dragon Frontiers, ~19min p/ 100% das 79
listings) estouravam o per-set-timeout default (8min) SEMPRE, iam pra skip-list,
eram pulados em runs futuros e nunca mais escaneados por completo ("churn").

A solução é um mapa code-level `SET_TIMEOUT_OVERRIDES` + o resolver
`effective_set_timeout_s(exp_code, default_s)`, com as regras:
  - default 0 (timeout global desligado) → 0 pra todos (override não reativa).
  - set com override → max(default, override) (override só ELEVA o teto).
  - set sem override → default (comportamento histórico).
  - código case-insensitive.

Sets confirmados com override: df, ds, n1, n4. NÃO inclui n2 (Neo Discovery),
que é no-coverage genuíno (tratado por --max-consecutive-misses, não timeout).

Roda de dois jeitos (espelha test_skiplist_bom.py):
    pytest tests/test_set_timeout_overrides.py -v
    python tests/test_set_timeout_overrides.py     # fallback standalone
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

# Repo root no sys.path (tests/ → ..)
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cardtrader_scanner as sc  # noqa: E402
from cardtrader_scanner import (  # noqa: E402
    SET_TIMEOUT_OVERRIDES,
    effective_set_timeout_s,
)

# 8 min em segundos — o default histórico (DEFAULT_PER_SET_TIMEOUT_MIN).
_DEFAULT_S = 8 * 60  # 480


# ──────────────────────────────────────────────────────────────────────
# 1. O mapa de overrides em si (fatos confirmados na investigação vintage)
# ──────────────────────────────────────────────────────────────────────
def test_overrides_contain_confirmed_vintage_sets():
    """df/ds/n1/n4 têm override; cada um > o default de 8min (senão é inútil)."""
    for code in ("df", "ds", "n1", "n4"):
        assert code in SET_TIMEOUT_OVERRIDES, f"{code} deveria ter override"
        assert SET_TIMEOUT_OVERRIDES[code] > _DEFAULT_S, (
            f"override de {code} ({SET_TIMEOUT_OVERRIDES[code]}s) não excede o "
            f"default ({_DEFAULT_S}s) — seria inócuo"
        )


def test_df_has_largest_override():
    """df (EX Dragon Frontiers) precisa ~19min → override é o maior (1200s/20min)."""
    assert SET_TIMEOUT_OVERRIDES["df"] == 1200


def test_n2_has_no_timeout_override():
    """n2 (Neo Discovery) é NO-COVERAGE genuíno, não problema de timeout — NÃO
    deve ter override (seria moer chamadas que sempre falham por mais tempo)."""
    assert "n2" not in SET_TIMEOUT_OVERRIDES


def test_cri_has_timeout_override():
    """cri (Chaos Rising/me4): a pokemontcg.io não precifica → 100% via fallback
    tcgcsv (~1 req/listing = lento), mas o tcgcsv REALMENTE precifica (384 rows num
    scan real). Sob o default de 8min estourava e ia pra skip-list → precisa de
    override > default (mesmo remédio dos vintage df/n1/n4)."""
    assert SET_TIMEOUT_OVERRIDES.get("cri") == 1200
    assert SET_TIMEOUT_OVERRIDES["cri"] > _DEFAULT_S
    assert effective_set_timeout_s("cri", _DEFAULT_S) == 1200.0


def test_asc_has_no_override_because_no_coverage():
    """asc (Ascended Heroes/me2pt5) NÃO deve ter override: num scan de 702/901
    listings retornou 0 preço (o tcgcsv não resolve a ASC hoje). É no-coverage
    como n2 — timeout maior só moeria chamadas que sempre falham. Cai no default."""
    assert "asc" not in SET_TIMEOUT_OVERRIDES
    assert effective_set_timeout_s("asc", _DEFAULT_S) == float(_DEFAULT_S)


def test_mega_era_ct_aliases_map_to_ptcg():
    """Causa-raiz do 'Chaos Rising vazio': o matcher casa o code CT contra o
    api_set via SET_ALIAS_TO_PTCG. Sem alias, api_set=me4 ≠ CT 'cri' → TODO card
    rejeitado como set mismatch (0 preço). asc→me2pt5, por→me3, cri→me4 precisam
    existir pra os sets Mega serem precificáveis."""
    aliases = sc.PokemonTcgIoProvider.SET_ALIAS_TO_PTCG
    assert aliases.get("cri") == ["me4"]
    assert aliases.get("asc") == ["me2pt5"]
    assert aliases.get("por") == ["me3"]


# ──────────────────────────────────────────────────────────────────────
# 2. effective_set_timeout_s — a função de resolução
# ──────────────────────────────────────────────────────────────────────
def test_set_with_override_uses_larger_timeout():
    """Set com override + default menor → usa o override."""
    assert effective_set_timeout_s("df", _DEFAULT_S) == 1200.0
    assert effective_set_timeout_s("ds", _DEFAULT_S) == 1080.0
    assert effective_set_timeout_s("n1", _DEFAULT_S) == 1080.0
    assert effective_set_timeout_s("n4", _DEFAULT_S) == 1080.0


def test_set_without_override_uses_default():
    """Set sem override → exatamente o default global (comportamento histórico)."""
    assert effective_set_timeout_s("pre", _DEFAULT_S) == float(_DEFAULT_S)
    assert effective_set_timeout_s("scr", _DEFAULT_S) == float(_DEFAULT_S)
    # n2 cai aqui: sem override → default (o miss-cap é quem trata o no-coverage).
    assert effective_set_timeout_s("n2", _DEFAULT_S) == float(_DEFAULT_S)


def test_override_is_case_insensitive():
    """Código vem do CT às vezes em maiúscula/com espaço — normaliza."""
    assert effective_set_timeout_s("DF", _DEFAULT_S) == 1200.0
    assert effective_set_timeout_s("  Df  ", _DEFAULT_S) == 1200.0


def test_override_only_raises_ceiling_never_lowers():
    """Se o operador passar um --per-set-timeout global MAIOR que o override,
    o global vence (override é piso elevado, não teto fixo)."""
    # global 25min (1500s) > override de df (1200s) → 1500 vence.
    assert effective_set_timeout_s("df", 1500) == 1500.0
    # global 30min (1800s) pra um set SEM override → o próprio global.
    assert effective_set_timeout_s("pre", 1800) == 1800.0


def test_default_zero_disables_for_everyone_including_override():
    """default 0 = timeout global DESLIGADO de propósito. Override não reativa
    (senão um set vintage ficaria com timeout que o operador desligou)."""
    assert effective_set_timeout_s("df", 0) == 0.0
    assert effective_set_timeout_s("pre", 0) == 0.0


def test_empty_or_none_code_falls_back_to_default():
    """Código vazio/None (defensivo) → default, sem crash."""
    assert effective_set_timeout_s("", _DEFAULT_S) == float(_DEFAULT_S)
    assert effective_set_timeout_s(None, _DEFAULT_S) == float(_DEFAULT_S)  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────────────────────
# 3. _check_set_timeout — integração: respeita o timeout EFETIVO passado
# ──────────────────────────────────────────────────────────────────────
class _FakeScanner:
    """Stand-in mínimo p/ exercitar Scanner._check_set_timeout sem rede/CT.
    Só precisa de per_set_timeout_s + stats; o resto do método não toca."""

    def __init__(self, per_set_timeout_s):
        self.per_set_timeout_s = per_set_timeout_s
        self.stats = {"expansions_timed_out": 0}

    _check_set_timeout = sc.Scanner._check_set_timeout


def test_check_set_timeout_uses_explicit_effective_value(monkeypatch):
    """Com timeout_s explícito (override de set), o método NÃO usa o
    per_set_timeout_s default: um set 'velho' há 10min aborta sob default de
    8min, mas NÃO sob override de 20min."""
    added = []
    monkeypatch.setattr(sc, "add_to_skip_list",
                        lambda code, reason: added.append((code, reason)))

    fake = _FakeScanner(per_set_timeout_s=8 * 60)  # default 8min
    # Simula que o set começou 10min atrás.
    set_start = sc.time.monotonic() - (10 * 60)

    # Sob o default (8min): 10min > 8min → aborta.
    aborted_default = fake._check_set_timeout(
        set_start, "df", "EX Dragon Frontiers", "test", timeout_s=8 * 60)
    assert aborted_default is True
    assert added and added[-1][0] == "df"

    # Sob override (20min): 10min < 20min → NÃO aborta.
    aborted_override = fake._check_set_timeout(
        set_start, "df", "EX Dragon Frontiers", "test", timeout_s=20 * 60)
    assert aborted_override is False


def test_check_set_timeout_none_falls_back_to_instance_default(monkeypatch):
    """timeout_s=None (chamadas diretas legadas) → usa self.per_set_timeout_s."""
    monkeypatch.setattr(sc, "add_to_skip_list", lambda code, reason: None)
    fake = _FakeScanner(per_set_timeout_s=8 * 60)
    set_start = sc.time.monotonic() - (10 * 60)  # 10min atrás
    # None → cai no default de 8min do instance → aborta.
    assert fake._check_set_timeout(set_start, "x", "X", "test") is True


# ──────────────────────────────────────────────────────────────────────
# Standalone runner (sem pytest) — espelha test_skiplist_bom.py
# ──────────────────────────────────────────────────────────────────────
class _MonkeyPatch:
    """Mínimo stand-in pra fixture monkeypatch (setattr) com restore."""
    _SENTINEL = object()

    def __init__(self):
        self._saved: list[tuple[object, str, object]] = []

    def setattr(self, target, name, value):
        old = getattr(target, name, self._SENTINEL)
        self._saved.append((target, name, old))
        setattr(target, name, value)

    def undo(self):
        for target, name, old in reversed(self._saved):
            if old is self._SENTINEL:
                delattr(target, name)
            else:
                setattr(target, name, old)
        self._saved.clear()


def _standalone_main() -> int:
    tests = [obj for name, obj in sorted(globals().items())
             if name.startswith("test_") and callable(obj)]
    failed = 0
    passed = 0
    for fn in tests:
        sig = inspect.signature(fn)
        kwargs = {}
        mp = None
        if "monkeypatch" in sig.parameters:
            mp = _MonkeyPatch()
            kwargs["monkeypatch"] = mp
        try:
            fn(**kwargs)
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
        finally:
            if mp is not None:
                mp.undo()

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_standalone_main())
