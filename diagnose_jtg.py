"""Diagnóstico: inspeciona listings crus de 1 set (jtg) pra entender por que
o filtro zera tudo. Não roda o scanner completo, não altera cache."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from cardtrader_scanner import CardTraderClient, CT_POKEMON_GAME_ID

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SET_CODE = "jtg"

SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

jwt = os.getenv("CT_JWT", "").strip()
if not jwt:
    sys.exit("CT_JWT ausente no .env")

ct = CardTraderClient(jwt)

print(f"→ Procurando expansão '{SET_CODE}' no CardTrader...")
expansions = ct.list_expansions(CT_POKEMON_GAME_ID)
target = next((e for e in expansions if e.get("code", "").lower() == SET_CODE), None)
if not target:
    sys.exit(f"Expansão {SET_CODE} não encontrada. Primeiras 10: "
             + ", ".join(e.get("code", "?") for e in expansions[:10]))

exp_id = target["id"]
exp_name = target.get("name", "?")
print(f"  encontrada: {exp_name} [id={exp_id}]\n")

print("→ Baixando listings (language=en, igual ao scanner)...")
raw = ct.list_listings_by_expansion(exp_id, language="en")
print(f"  {len(raw)} listings\n")

if not raw:
    sys.exit("sem listings — nada a analisar")


def prop(listing: dict, *keys):
    """Busca uma chave em properties_hash ou properties (ambas aparecem na API)."""
    props = listing.get("properties_hash") or listing.get("properties") or {}
    for k in keys:
        if k in props:
            return props.get(k)
    return None


condition_counter: Counter = Counter()
pokemon_lang_counter: Counter = Counter()
mtg_lang_counter: Counter = Counter()
generic_lang_counter: Counter = Counter()
graded_counter: Counter = Counter()
price_buckets = Counter()
currency_counter: Counter = Counter()

for l in raw:
    condition_counter[prop(l, "condition")] += 1
    pokemon_lang_counter[prop(l, "pokemon_language")] += 1
    mtg_lang_counter[prop(l, "mtg_language")] += 1
    generic_lang_counter[prop(l, "language")] += 1
    graded_counter[bool(l.get("graded", False))] += 1

    price = l.get("price", {}) or {}
    cents = price.get("cents", 0) or 0
    currency_counter[price.get("currency")] += 1
    if cents < 100:
        bucket = "<1 EUR"
    elif cents < 500:
        bucket = "1-5 EUR"
    elif cents < 1000:
        bucket = "5-10 EUR"
    elif cents < 2500:
        bucket = "10-25 EUR"
    elif cents < 5000:
        bucket = "25-50 EUR"
    elif cents < 10000:
        bucket = "50-100 EUR"
    else:
        bucket = ">=100 EUR"
    price_buckets[bucket] += 1


def dump(title: str, counter: Counter, top: int = 15):
    print(f"── {title} ──")
    total = sum(counter.values())
    for key, n in counter.most_common(top):
        pct = 100.0 * n / total if total else 0
        print(f"  {str(key)!r:<24} {n:>7}  ({pct:5.1f}%)")
    if len(counter) > top:
        print(f"  ... mais {len(counter) - top} valores únicos")
    print()


dump("condition", condition_counter)
dump("pokemon_language", pokemon_lang_counter)
dump("mtg_language", mtg_lang_counter)
dump("language (genérico)", generic_lang_counter)
dump("graded", graded_counter)
dump("currency", currency_counter)

print("── price_cents buckets ──")
order = ["<1 EUR", "1-5 EUR", "5-10 EUR", "10-25 EUR",
         "25-50 EUR", "50-100 EUR", ">=100 EUR"]
total = sum(price_buckets.values())
for b in order:
    n = price_buckets.get(b, 0)
    pct = 100.0 * n / total if total else 0
    print(f"  {b:<12} {n:>7}  ({pct:5.1f}%)")
print()

print("── 1 listing cru (JSON) ──")
print(json.dumps(raw[0], indent=2, ensure_ascii=False, default=str))
