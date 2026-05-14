"""Diagnóstico: por que 0 deals em sfa+scr+paf hoje?

Roda o scan normal MAS exporta TODOS os 634 listings com preço TCG —
não só os que passam o threshold. Salva em CSV ordenado por margem desc.

Com isso conseguimos ver:
  - Qual é a margem MÁXIMA observada (pra calibrar threshold real)
  - Distribuição de margens (histograma)
  - Cards específicos que deveriam estar dando deal e não estão
  - Se há preço TCG sendo lido errado (ex: low ao invés de market)
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

from cardtrader_scanner import (
    CardTraderClient, Cache, Scanner, PokemonTcgIoProvider,
    get_eur_to_brl, get_usd_to_brl, CT_POKEMON_GAME_ID,
)

SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

jwt = os.getenv("CT_JWT", "").strip()
ptcg_key = os.getenv("POKEMONTCG_API_KEY", "").strip()
if not jwt:
    sys.exit("CT_JWT ausente no .env")

SETS_TO_DIAGNOSE = ["sfa", "scr", "paf"]
OUT_CSV = SCRIPT_DIR.parent / "runs-ct" / "2026-05-10" / "diagnostico_listings_2026-05-10.csv"

ct = CardTraderClient(jwt)
cache = Cache()
eur_brl = get_eur_to_brl(cache)
usd_brl = get_usd_to_brl(cache)
pricing = PokemonTcgIoProvider(api_key=ptcg_key or None, cache=cache)

print(f"FX: USD/BRL={usd_brl}, EUR/BRL={eur_brl}")
print(f"Sets: {SETS_TO_DIAGNOSE}")
print(f"Output: {OUT_CSV}")
print()

# Carrega expansions e filtra os 3 que queremos
exps = ct.list_expansions(CT_POKEMON_GAME_ID)
exp_by_code = {e.get("code", "").lower(): e for e in exps}
target_exps = []
for code in SETS_TO_DIAGNOSE:
    e = exp_by_code.get(code)
    if not e:
        print(f"  !! Set '{code}' não encontrado nas expansions CT")
        continue
    target_exps.append(e)
    print(f"  ✓ {code} → id={e['id']} ({e['name']})")

if not target_exps:
    sys.exit("Nenhum set válido")

# Instancia scanner com threshold artificialmente baixo (-100%) pra capturar tudo
scanner = Scanner(
    ct=ct, pricing=pricing, cache=cache,
    threshold=-1.0,           # captura QUALQUER coisa, mesmo margem negativa
    min_price_usd=10.0,
    exclude_graded=True,
)

print()
print("Escaneando — isso vai capturar TODOS os listings com TCG price, sem filtro de margem...")
print()

# Roda o scan padrão mas com threshold=-1 pra pegar tudo
all_opps = scanner.scan(target_exps)
print(f"Total opportunities (sem filtro): {len(all_opps)}")
print()

# Estatísticas de margem
margins = [o.margin_pct for o in all_opps]
if margins:
    margins_sorted = sorted(margins, reverse=True)
    print("Distribuição de margens brutas (raw scan):")
    print(f"  Máxima: {margins_sorted[0]:.1%}")
    print(f"  Top 5: {[f'{m:.1%}' for m in margins_sorted[:5]]}")
    print(f"  Mediana: {margins_sorted[len(margins_sorted)//2]:.1%}")
    print(f"  Mínima: {margins_sorted[-1]:.1%}")
    print()
    # Buckets
    buckets = {
        ">25%": sum(1 for m in margins if m >= 0.25),
        "15-25%": sum(1 for m in margins if 0.15 <= m < 0.25),
        "5-15%": sum(1 for m in margins if 0.05 <= m < 0.15),
        "0-5%": sum(1 for m in margins if 0 <= m < 0.05),
        "neg (<0)": sum(1 for m in margins if m < 0),
    }
    print("Buckets de margem bruta:")
    for k, v in buckets.items():
        print(f"  {k:>12s}: {v}")
    print()

# Exporta CSV completo
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow([
        "card_name", "set_code", "collector_number", "condition", "language",
        "price_cents", "price_currency", "ct_price_brl",
        "tcg_market_usd", "tcg_market_brl",
        "margin_pct", "margin_brl", "net_margin_pct",
        "seller_username", "seller_user_type", "can_sell_via_hub",
        "cardtrader_url",
    ])
    # Ordena por margem desc pra ver os "quase deals" primeiro
    for o in sorted(all_opps, key=lambda x: x.margin_pct, reverse=True):
        l = o.listing
        w.writerow([
            l.card_name, l.set_code, l.collector_number, l.condition, l.language,
            l.price_cents, l.price_currency, round(o.ct_price_brl, 2),
            round(o.tcg_market_usd, 2), round(o.tcg_market_brl, 2),
            round(o.margin_pct, 4), round(o.margin_brl, 2), round(o.net_margin_pct, 4),
            l.seller_username, l.seller_user_type, l.seller_can_sell_via_hub,
            l.cardtrader_url,
        ])

print(f"CSV salvo: {OUT_CSV}")
print(f"Stats finais: {scanner.stats}")
