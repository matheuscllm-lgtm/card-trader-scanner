"""Diagnóstico de match rate no pokemontcg.io.

Para cada um dos 8 sets, pega 1 listing que passaria o filtro (NM, EN,
não-graded, ≥$10 USD) e tenta 3 estratégias de query:
  (A) name + number + set.id         ← comportamento atual do scanner
  (B) name + number                   ← sem filtro de set
  (C) name                            ← só nome

Reporta: hits de cada estratégia + set.id do primeiro match em (B).
Com isso a gente vê se é mismatch de set code, set não-catalogado, ou outra coisa.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

from cardtrader_scanner import (
    CardTraderClient, CT_POKEMON_GAME_ID, POKEMONTCG_BASE,
    get_eur_to_usd, Cache,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SETS = ["pre", "jtg", "dri", "blk", "wht", "meg", "pfl", "asc"]

SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

jwt = os.getenv("CT_JWT", "").strip()
ptcg_key = os.getenv("POKEMONTCG_API_KEY", "").strip()
if not jwt:
    sys.exit("CT_JWT ausente no .env")

ct = CardTraderClient(jwt)
cache = Cache()
eur_usd = get_eur_to_usd(cache)

sess = requests.Session()
if ptcg_key:
    sess.headers["X-Api-Key"] = ptcg_key


def pick_survivor(exp_id: int):
    """Devolve 1 listing do set que passaria NM+EN+!graded+≥$10 USD, com bp fields."""
    blueprints = ct.list_blueprints(exp_id)
    bp_index = {bp["id"]: bp for bp in blueprints}
    listings = ct.list_listings_by_expansion(exp_id, language="en")
    for l in listings:
        props = l.get("properties_hash") or {}
        if props.get("condition") != "Near Mint":
            continue
        if (props.get("pokemon_language") or "").lower() != "en":
            continue
        if l.get("graded"):
            continue
        price = l.get("price", {}) or {}
        cents = price.get("cents", 0) or 0
        currency = (price.get("currency") or "EUR").upper()
        if currency == "EUR":
            price_usd = cents / 100.0 * eur_usd
        elif currency == "USD":
            price_usd = cents / 100.0
        else:
            continue
        if price_usd < 10.0:
            continue
        bp = bp_index.get(l.get("blueprint_id"))
        if not bp:
            continue
        collector = bp.get("collector_number") or bp.get("version", "")
        return {
            "name": bp.get("name", ""),
            "collector_number": collector,
            "number_clean": collector.split("/")[0].strip() if collector else "",
            "price_usd": price_usd,
            "ct_set_code": bp.get("expansion", {}).get("code", "") if isinstance(bp.get("expansion"), dict) else bp.get("expansion_code", ""),
        }
    return None


def search_ptcg(query: str) -> tuple[int, list[dict]]:
    r = sess.get(f"{POKEMONTCG_BASE}/cards",
                 params={"q": query, "pageSize": 3}, timeout=30)
    if r.status_code != 200:
        return -1, []
    data = r.json()
    return data.get("totalCount", 0), data.get("data", [])


print(f"{'SET':<5} {'CARD':<28} {'#':<6}  {'(A) name+num+set':>18}  {'(B) name+num':>14}  {'(C) name':>10}  {'B→first set':<14}")
print("-" * 120)

expansions = ct.list_expansions(CT_POKEMON_GAME_ID)
exp_by_code = {e.get("code", "").lower(): e for e in expansions}

for set_code in SETS:
    exp = exp_by_code.get(set_code)
    if not exp:
        print(f"{set_code:<5} [expansão não encontrada no CT]")
        continue
    card = pick_survivor(exp["id"])
    if not card:
        print(f"{set_code:<5} [sem survivor — set todo caiu no filtro local]")
        continue

    name_safe = card["name"].replace('"', '\\"')
    num = card["number_clean"]

    q_a = f'name:"{name_safe}" number:{num} set.id:{set_code}' if num else f'name:"{name_safe}" set.id:{set_code}'
    q_b = f'name:"{name_safe}" number:{num}' if num else f'name:"{name_safe}"'
    q_c = f'name:"{name_safe}"'

    a_count, _ = search_ptcg(q_a)
    b_count, b_data = search_ptcg(q_b)
    c_count, _ = search_ptcg(q_c)

    b_first = ""
    if b_data:
        first = b_data[0]
        b_first = f'{first.get("set", {}).get("id", "?")}/{first.get("number", "?")}'

    name_short = (card["name"][:26] + "..") if len(card["name"]) > 28 else card["name"]
    print(f"{set_code:<5} {name_short:<28} {card['collector_number']:<6}  "
          f"{a_count:>18}  {b_count:>14}  {c_count:>10}  {b_first:<14}")
