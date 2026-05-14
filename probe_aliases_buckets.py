"""Probe aliases CT para 'ascended heroes' e 'fusion strike'.

Roda via .venv do scanner (mesma config .env).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(ENV_FILE)

CT_BASE = "https://api.cardtrader.com/api/v2"
CT_POKEMON_GAME_ID = 5

jwt = os.getenv("CT_JWT", "").strip()
if not jwt:
    print("ERRO: CT_JWT não definido em .env", file=sys.stderr)
    sys.exit(1)

s = requests.Session()
s.headers.update({
    "Authorization": f"Bearer {jwt}",
    "Accept": "application/json",
    "User-Agent": "MasterBox-TCG-Scanner/1.0 probe",
})

r = s.get(f"{CT_BASE}/expansions", timeout=30)
r.raise_for_status()
data = r.json()
pokemon_exps = [e for e in data if e.get("game_id") == CT_POKEMON_GAME_ID]
print(f"Total expansions Pokémon: {len(pokemon_exps)}")
print()

queries = [
    ("ascended heroes", ["ascended", "heroes"]),
    ("fusion strike", ["fusion", "strike"]),
]

for label, terms in queries:
    print(f"=== Busca: {label} ===")
    matches = []
    for e in pokemon_exps:
        name = (e.get("name", "") or "").lower()
        code = (e.get("code", "") or "").lower()
        if all(t in name for t in terms) or any(t == code for t in terms):
            matches.append(e)
    if not matches:
        print(f"  NENHUM MATCH para '{label}'")
    else:
        for m in matches:
            print(f"  id={m.get('id')}  code={m.get('code')!r}  name={m.get('name')!r}")
    print()

# Confirmar codes que já estão na memória (asc, fst)
print("=== Confirmação de códigos esperados ===")
for code_check in ["asc", "fst", "pre", "lorg", "astr", "pal", "par", "tef", "twm",
                    "sfa", "scr", "ssp", "dri", "blk", "jtg", "crz", "sit",
                    "evs", "brs"]:
    found = [e for e in pokemon_exps if (e.get("code") or "").lower() == code_check]
    if found:
        e = found[0]
        print(f"  {code_check:6s} -> id={e.get('id')}  name={e.get('name')!r}")
    else:
        print(f"  {code_check:6s} -> NÃO ENCONTRADO")
