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
    "rarity": "Rare Holo",
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
    "rarity": "Rare Holo",
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
    "rarity": "Rare Holo",
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


# ── v2.18 regression fixtures: vintage Holo Rare inflation bug ──────────────
# Preços reais observados via pokemontcg.io 2026-06-20. Antes do v2.18, o
# scanner pegava reverseHolofoil (inflado) pra TODA holo rare padrão porque
# `pokemon_reverse` era ignorado (foil sempre False) e holo rare não tem
# variante `normal`.
SHIFTRY_HL = {  # EX Hidden Legends — reverse $42.95 vs holo $19.92 (+116%)
    "id": "ex5-14", "name": "Shiftry", "rarity": "Rare Holo",
    "set": {"id": "ex5", "printedTotal": 101}, "number": "14",
    "tcgplayer": {"url": "https://prices.pokemontcg.io/tcgplayer/ex5-14",
        "prices": {"holofoil": {"market": 19.92},
                   "reverseHolofoil": {"market": 42.95}}},
}
GENGAR_LC = {  # Legendary Collection — reverse $1599.99 vs holo $146.89 (10×!)
    "id": "base6-11", "name": "Gengar", "rarity": "Rare Holo",
    "set": {"id": "base6", "printedTotal": 110}, "number": "11",
    "tcgplayer": {"url": "https://prices.pokemontcg.io/tcgplayer/base6-11",
        "prices": {"holofoil": {"market": 146.89},
                   "reverseHolofoil": {"market": 1599.99}}},
}
# Non-holo common: normal $0.50 vs reverseHolofoil $3.00 — deve usar normal.
PIDGEY_NONHOLO = {
    "id": "xy1-99", "name": "Pidgey", "rarity": "Common",
    "set": {"id": "xy1", "printedTotal": 146}, "number": "99",
    "tcgplayer": {"url": "https://prices.pokemontcg.io/tcgplayer/xy1-99",
        "prices": {"normal": {"market": 0.50},
                   "reverseHolofoil": {"market": 3.00}}},
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
print("\n=== Layer 4 — variant disambiguation (rarity+reverse aware, v2.18) ===")
# v2.18 redefiniu a semântica: `foil` agora = reverse-holo (pokemon_reverse).
#   foil=False + raridade holo → holofoil (printagem holo padrão)
#   foil=True (reverse holo)   → reverseHolofoil
#   foil=False + não-holo      → normal

# Test 1: Pichu Rare Holo, PADRÃO (foil=False) → holofoil $224.99
p = make_provider(PICHU_ECARD1)
m = p.market_price_usd("Pichu", "ecard1", "22", foil=False, rarity="Holo Rare")
assert_eq(m, 224.99, "Pichu ecard1/22 holo padrão → market=$224.99")
assert_eq(p.last_variant_used, "holofoil", "Pichu holo padrão → variant=holofoil")

# Test 2: Pichu Rare Holo, REVERSE (foil=True) → reverseHolofoil $120.57
p = make_provider(PICHU_ECARD1)
m = p.market_price_usd("Pichu", "ecard1", "22", foil=True, rarity="Holo Rare")
assert_eq(m, 120.57, "Pichu ecard1/22 reverse → market=$120.57")
assert_eq(p.last_variant_used, "reverseHolofoil", "Pichu reverse → variant=reverseHolofoil")

# Test 3: Arbok Rare Holo, PADRÃO → holofoil $82.77
p = make_provider(ARBOK_ECARD1)
m = p.market_price_usd("Arbok", "ecard1", "3", foil=False, rarity="Holo Rare")
assert_eq(m, 82.77, "Arbok ecard1/3 holo padrão → market=$82.77")
assert_eq(p.last_variant_used, "holofoil", "Arbok holo padrão → variant=holofoil")

# Test 4: Arbok Rare Holo, REVERSE → reverseHolofoil $27.93
p = make_provider(ARBOK_ECARD1)
m = p.market_price_usd("Arbok", "ecard1", "3", foil=True, rarity="Holo Rare")
assert_eq(m, 27.93, "Arbok ecard1/3 reverse → market=$27.93")
assert_eq(p.last_variant_used, "reverseHolofoil", "Arbok reverse → variant=reverseHolofoil")

# Test 5: Vaporeon base2/12 holo padrão → unlimitedHolofoil $52.25 (sem holofoil, 1stEd excl.)
p = make_provider(VAPOREON_BASE2)
m = p.market_price_usd("Vaporeon", "base2", "12", foil=False, rarity="Holo Rare")
assert_eq(m, 52.25, "Vaporeon base2/12 holo → market=$52.25")
assert_eq(p.last_variant_used, "unlimitedHolofoil", "Vaporeon vintage → unlimitedHolofoil (1stEd excluded)")

# Test 6: 1stEdition NUNCA é escolhida (Pichu tem 1stEd $750 → ignorado)
p = make_provider(PICHU_ECARD1)
p.market_price_usd("Pichu", "ecard1", "22", foil=True, rarity="Holo Rare")
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
p.market_price_usd("Pichu", "ecard1", "22", foil=False, rarity="Holo Rare")
assert_in("ecard1-22", p.last_tcg_url, "tcg_url populated when holofoil chosen")

# ── v2.18 regression: vintage Holo Rare inflation bug ──────────────────────
# Test 8a: Shiftry EX HL holo padrão → holofoil $19.92 (NÃO reverse $42.95)
p = make_provider(SHIFTRY_HL)
m = p.market_price_usd("Shiftry", "ex5", "14", foil=False, rarity="Holo Rare")
assert_eq(m, 19.92, "Shiftry hl holo → holofoil $19.92 (não reverse $42.95)")
assert_eq(p.last_variant_used, "holofoil", "Shiftry hl → variant=holofoil")

# Test 8b: Gengar Legendary Collection holo → holofoil $146.89 (NÃO reverse $1599.99)
p = make_provider(GENGAR_LC)
m = p.market_price_usd("Gengar", "base6", "11", foil=False, rarity="Holo Rare")
assert_eq(m, 146.89, "Gengar LC holo → holofoil $146.89 (não reverse $1599.99!)")
assert_eq(p.last_variant_used, "holofoil", "Gengar LC → variant=holofoil")

# Test 8c: Gengar LC REVERSE (foil=True) → reverseHolofoil $1599.99 (caso legítimo)
p = make_provider(GENGAR_LC)
m = p.market_price_usd("Gengar", "base6", "11", foil=True, rarity="Holo Rare")
assert_eq(m, 1599.99, "Gengar LC reverse → reverseHolofoil $1599.99")
assert_eq(p.last_variant_used, "reverseHolofoil", "Gengar LC reverse → variant=reverseHolofoil")

# Test 8d: Pidgey non-holo common → normal $0.50 (NÃO reverse $3.00)
p = make_provider(PIDGEY_NONHOLO)
m = p.market_price_usd("Pidgey", "xy1", "99", foil=False, rarity="Common")
assert_eq(m, 0.50, "Pidgey common → normal $0.50 (não reverse $3.00)")
assert_eq(p.last_variant_used, "normal", "Pidgey common → variant=normal")

# Test 8e: helper _rarity_is_holo
assert_eq(scanner._rarity_is_holo("Holo Rare"), True, "_rarity_is_holo('Holo Rare')")
assert_eq(scanner._rarity_is_holo("Rare Holo EX"), True, "_rarity_is_holo('Rare Holo EX')")
assert_eq(scanner._rarity_is_holo("Common"), False, "_rarity_is_holo('Common')")
assert_eq(scanner._rarity_is_holo(None, "Rare"), False, "_rarity_is_holo(None,'Rare')")

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
