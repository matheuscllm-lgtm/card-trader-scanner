#!/usr/bin/env python3
"""
test_variant_disambiguation.py — v2.8 Layer 4 + Postprocess v2.3 Layer 5 (2026-05-18)

Verifica o foil-aware variant disambiguation no PokemonTcgIoProvider e o
filtro alpha-suffix no postprocess:

  Layer 4 (scanner):
    1. Pichu Expedition ecard1/22 foil=True  → market = $224.99, variant=holofoil
    2. Pichu Expedition ecard1/22 foil=False → market = $120.57, variant=reverseHolofoil
    3. Arbok Expedition ecard1/3 foil=True   → market = $82.77,  variant=holofoil
    4. Arbok Expedition ecard1/3 foil=False  → market = $27.93,  variant=reverseHolofoil
    5. Vaporeon base2/12 foil=True           → market = $52.25,  variant=unlimitedHolofoil
    6. EXCLUDED 1stEditionHolofoil — nunca retornado mesmo se outras
       variantes ausentes
    7. foil=None preserva v2.7 priority (holofoil primeiro)

  Layer 5 (postprocess):
    8. Card #153a → REVISAR ("Promo/League variant" no porque)
    9. Card #22a  → REVISAR
   10. Card #153  → NÃO disparado por Layer 5
   11. TG01 → flagged como Trainer Gallery, NÃO como alpha suffix
        (TG já tem o seu próprio filtro NÃO em classify_decision)

NÃO faz network call. Mocka pricing fixtures + classify_decision em-process.

Roda:
    .venv/Scripts/python.exe scripts/test_variant_disambiguation.py

Exit code:
    0 = todos os asserts passaram
    1 = pelo menos um assert falhou
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import cardtrader_scanner as scanner  # noqa: E402
import cardtrader_postprocess as postprocess  # noqa: E402

failures: list[str] = []


def assert_eq(actual, expected, label: str):
    ok = actual == expected
    if not ok:
        failures.append(f"FAIL {label}: expected={expected!r} got={actual!r}")
        print(f"  [FAIL] {label}: expected={expected!r} got={actual!r}")
    else:
        print(f"  [ OK ] {label}")


def assert_in(needle, haystack, label: str):
    ok = needle in haystack
    if not ok:
        failures.append(f"FAIL {label}: {needle!r} not in {haystack!r}")
        print(f"  [FAIL] {label}: {needle!r} not in {haystack!r}")
    else:
        print(f"  [ OK ] {label}")


# ── Fixtures: card dicts with TCGPlayer.prices ──────────────────────────────
# Pichu Expedition (real preços observados via pokemontcg.io 2026-05-18)
PICHU_ECARD1 = {
    "id": "ecard1-22",
    "name": "Pichu",
    "set": {"id": "ecard1", "printedTotal": 165},
    "number": "22",
    "tcgplayer": {
        "url": "https://prices.pokemontcg.io/tcgplayer/ecard1-22",
        "prices": {
            "holofoil":          {"low": 200.0, "mid": 220.0, "market": 224.99},
            "reverseHolofoil":   {"low": 100.0, "mid": 118.0, "market": 120.57},
            "1stEditionHolofoil": {"low": 600.0, "mid": 700.0, "market": 750.00},
        },
    },
}
# Arbok Expedition
ARBOK_ECARD1 = {
    "id": "ecard1-3",
    "name": "Arbok",
    "set": {"id": "ecard1", "printedTotal": 165},
    "number": "3",
    "tcgplayer": {
        "url": "https://prices.pokemontcg.io/tcgplayer/ecard1-3",
        "prices": {
            "holofoil":        {"low": 75.0, "mid": 80.0, "market": 82.77},
            "reverseHolofoil": {"low": 25.0, "mid": 27.0, "market": 27.93},
        },
    },
}
# Vaporeon Jungle (base2/12) — vintage sem holofoil ativo, só unlimitedHolofoil
VAPOREON_BASE2 = {
    "id": "base2-12",
    "name": "Vaporeon",
    "set": {"id": "base2", "printedTotal": 64},
    "number": "12",
    "tcgplayer": {
        "url": "https://prices.pokemontcg.io/tcgplayer/base2-12",
        "prices": {
            "unlimitedHolofoil":  {"low": 48.0, "mid": 50.0, "market": 52.25},
            "1stEditionHolofoil": {"low": 160.0, "mid": 165.0, "market": 168.40},
        },
    },
}


class FakeCache:
    """Cache stub que NÃO persiste — força provider a chamar _search sempre."""
    def __init__(self):
        self.store = {}

    def get_price(self, key):
        return None

    def set_price(self, key, market, low, mid, raw):
        self.store[key] = {"market": market, "raw": raw}


def make_provider(card_fixture):
    """Cria provider com _search mockado pra retornar o fixture."""
    cache = FakeCache()
    # Bypass __init__ Network setup, usa atributos diretos
    p = scanner.PokemonTcgIoProvider.__new__(scanner.PokemonTcgIoProvider)
    p.session = MagicMock()
    p.cache = cache
    p.delay = 0
    p._last_call = 0
    p._search = MagicMock(return_value=card_fixture)
    p.last_tcg_url = None
    p.last_variant_used = None
    return p


# ──────────────────────────────────────────────────────────────────────
# Layer 4 — scanner variant disambiguation
# ──────────────────────────────────────────────────────────────────────
print("\n=== Layer 4 — foil-aware variant disambiguation ===")

# Test 1: Pichu foil=True → holofoil $224.99
p = make_provider(PICHU_ECARD1)
m = p.market_price_usd("Pichu", "ecard1", "22", foil=True)
assert_eq(m, 224.99, "Pichu ecard1/22 foil=True → market=$224.99")
assert_eq(p.last_variant_used, "holofoil", "Pichu foil=True → variant=holofoil")

# Test 2: Pichu foil=False → reverseHolofoil $120.57
p = make_provider(PICHU_ECARD1)
m = p.market_price_usd("Pichu", "ecard1", "22", foil=False)
assert_eq(m, 120.57, "Pichu ecard1/22 foil=False → market=$120.57")
assert_eq(p.last_variant_used, "reverseHolofoil", "Pichu foil=False → variant=reverseHolofoil")

# Test 3: Arbok foil=True → holofoil $82.77
p = make_provider(ARBOK_ECARD1)
m = p.market_price_usd("Arbok", "ecard1", "3", foil=True)
assert_eq(m, 82.77, "Arbok ecard1/3 foil=True → market=$82.77")
assert_eq(p.last_variant_used, "holofoil", "Arbok foil=True → variant=holofoil")

# Test 4: Arbok foil=False → reverseHolofoil $27.93
p = make_provider(ARBOK_ECARD1)
m = p.market_price_usd("Arbok", "ecard1", "3", foil=False)
assert_eq(m, 27.93, "Arbok ecard1/3 foil=False → market=$27.93")
assert_eq(p.last_variant_used, "reverseHolofoil", "Arbok foil=False → variant=reverseHolofoil")

# Test 5: Vaporeon base2/12 foil=True → unlimitedHolofoil $52.25 (1stEd excluído)
p = make_provider(VAPOREON_BASE2)
m = p.market_price_usd("Vaporeon", "base2", "12", foil=True)
assert_eq(m, 52.25, "Vaporeon base2/12 foil=True → market=$52.25")
assert_eq(p.last_variant_used, "unlimitedHolofoil", "Vaporeon vintage → variant=unlimitedHolofoil (1stEd excluded)")

# Test 6: 1stEdition NUNCA é escolhida (Pichu tem 1stEd $750 → ignorado)
p = make_provider(PICHU_ECARD1)
p.market_price_usd("Pichu", "ecard1", "22", foil=True)
if p.last_variant_used == "1stEditionHolofoil":
    failures.append("FAIL 1stEditionHolofoil should be excluded")
    print(f"  [FAIL] 1stEditionHolofoil chosen (should be excluded)")
else:
    print(f"  [ OK ] 1stEditionHolofoil never chosen (chose {p.last_variant_used})")

# Test 7: foil=None preserva v2.7 priority (holofoil primeiro)
p = make_provider(PICHU_ECARD1)
m = p.market_price_usd("Pichu", "ecard1", "22", foil=None)
assert_eq(m, 224.99, "foil=None → preserves v2.7 priority (holofoil first)")
assert_eq(p.last_variant_used, "holofoil", "foil=None → variant=holofoil (v2.7 default)")

# Test 8: tcg_url propagated regardless of variant
p = make_provider(PICHU_ECARD1)
p.market_price_usd("Pichu", "ecard1", "22", foil=False)
assert_in("ecard1-22", p.last_tcg_url, "tcg_url populated even when reverseHolofoil chosen")

# ──────────────────────────────────────────────────────────────────────
# Layer 5 — postprocess alpha-suffix filter
# ──────────────────────────────────────────────────────────────────────
print("\n=== Layer 5 — postprocess alpha-suffix filter ===")

cfg = postprocess.DecisionConfig()

def mk_row(card_number, **overrides):
    """Row mínima pra classify_decision não crashar."""
    base = {
        "card_number": card_number,
        "chase_tier": "MID",
        "net_margin": 0.30,
        "lucro_liq": 100.0,
        "validation_status": "VALIDATED_REAL",
        "trainer_gallery_potential_fp": False,
        "set_code": "ecard1",
    }
    base.update(overrides)
    return base

# Test 9: 153a → REVISAR
d, why = postprocess.classify_decision(mk_row("153a"), cfg)
assert_eq(d, "REVISAR", "Card #153a → REVISAR")
assert_in("Alpha suffix", why, "Card #153a porque mentions 'Alpha suffix'")

# Test 10: 22a → REVISAR
d, why = postprocess.classify_decision(mk_row("22a"), cfg)
assert_eq(d, "REVISAR", "Card #22a → REVISAR")

# Test 11: 156b → REVISAR
d, why = postprocess.classify_decision(mk_row("156b"), cfg)
assert_eq(d, "REVISAR", "Card #156b → REVISAR")

# Test 12: 153 (puro numérico) NÃO dispara Layer 5
d, why = postprocess.classify_decision(mk_row("153"), cfg)
triggered_l5 = (d == "REVISAR" and "Alpha suffix" in why)
if triggered_l5:
    failures.append("FAIL Card #153 should NOT trigger Layer 5")
    print(f"  [FAIL] Card #153 disparou Layer 5: {why!r}")
else:
    print(f"  [ OK ] Card #153 → {d!r} (não Layer 5)")

# Test 13: 153/156 (collector with separator) NÃO dispara Layer 5
d, why = postprocess.classify_decision(mk_row("153/156"), cfg)
triggered_l5 = (d == "REVISAR" and "Alpha suffix" in why)
if triggered_l5:
    failures.append("FAIL Card #153/156 should NOT trigger Layer 5")
    print(f"  [FAIL] Card #153/156 disparou Layer 5: {why!r}")
else:
    print(f"  [ OK ] Card #153/156 → {d!r} (não Layer 5)")

# Test 14: TG01 → flagged como Trainer Gallery, NÃO Layer 5
# (TG flag é gerado em enrich_df, mas classify_decision lê a flag direta.
# Aqui forçamos a flag pra verificar que TG é prioritário sobre alpha suffix —
# se um dia alpha começar com TG, TG wins.)
d, why = postprocess.classify_decision(
    mk_row("TG01", trainer_gallery_potential_fp=True), cfg
)
assert_eq(d, "NAO", "Card TG01 + trainer_gallery flag → NÃO (TG check fica antes)")
# TG não casa com ALPHA_SUFFIX_RE (^\d+[a-zA-Z]+ exige dígito primeiro)
import re as _re
assert_eq(bool(postprocess.ALPHA_SUFFIX_RE.match("TG01")), False, "TG01 NÃO casa com ALPHA_SUFFIX_RE")

# Test 15: XY101 (Black Star Promo) NÃO dispara Layer 5 (letras antes)
assert_eq(bool(postprocess.ALPHA_SUFFIX_RE.match("XY101")), False, "XY101 NÃO casa com ALPHA_SUFFIX_RE")

# ──────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────
print(f"\n=== Summary ===")
total = 0  # contagem manual
# Count printed [ OK ] / [FAIL] lines aproximadamente via failures list
n_fail = len(failures)
print(f"Failures: {n_fail}")
if n_fail:
    print("\n".join(failures))
    sys.exit(1)
else:
    print("All asserts passed.")
    sys.exit(0)
