#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║  DBS SCANNER — CardTrader → TCGplayer (DRAGON BALL SUPER)            ║
║  Fusion World + DBS Masters · v1.0 (2026-07-17)                      ║
╚══════════════════════════════════════════════════════════════════════╝

Scanner PARALELO ao fluxo Pokémon deste repo (não passa pelo skill /scan):
varre expansões de Dragon Ball Super no CardTrader (game_id 9) com ofertas
AO VIVO do marketplace e compara com o preço market do TCGplayer via
tcgcsv.com (categorias 80 = Fusion World, 27 = DBS Masters).

Direção do fluxo: COMPRAR no CardTrader → VENDER/referenciar no TCGplayer US.

Por que este scanner existe (decisão do operador, 2026-07-17): a frota era
Pokémon-only e deixava passar deals de Dragon Ball (ex.: energy markers Gold
e promos Release Event Winner do set Fusion World Promos).

Invariantes herdados da frota:
  • Margem BRUTA base compra: (TCG_BRL − CT_BRL) / CT_BRL — sem taxa embutida.
  • --threshold em FRAÇÃO (0.30 = 30%) — convenção CardTrader/COMC/Selados.
  • Só Near Mint — match EXATO == "Near Mint" na condição da oferta; nunca
    substring. Graded/assinada nunca entra.
  • Nunca inventar preço: blueprint sem tcg_player_id ou produto sem market
    price → fica FORA com contagem explícita (sem fuzzy por nome).
  • Nunca recomendar compra: buckets são classificação técnica.
  • Entrega = tabela markdown gerada AQUI (build_markdown), 2 links por linha:
    [oferta](cardtrader) · [TCG](tcgplayer).

Join oferta↔referência: DETERMINÍSTICO por blueprint.tcg_player_id ==
productId do tcgcsv (mesma filosofia do join DH por productId da frota).

Uso:
    python dbs_scanner.py --expansions fuspromo fb04 --threshold 0.30
    python dbs_scanner.py --list-expansions          # códigos disponíveis
    python dbs_scanner.py --all --threshold 0.30     # catálogo DBS inteiro (lento)

Requer CT_JWT (env var ou .env deste repo). Câmbio: --fx OU automático
(open.er-api.com) — sem fonte de câmbio o run FALHA ALTO (nunca chuta).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

CT_API = "https://api.cardtrader.com/api/v2"
TCGCSV = "https://tcgcsv.com/tcgplayer"
GAME_ID_DBS = 9                    # "Dragon Ball Super" no CardTrader
TCGCSV_CATEGORIES = (80, 27)       # 80 = Fusion World · 27 = DBS Masters
USER_AGENT = "MasterBox-TCG-Scanner/1.0 (contato via cardtrader.com)"
FX_URL = "https://open.er-api.com/v6/latest/USD"
JUNK_RATIO = 0.5                   # oferta < 50% da ref = possível lixo/scam (padrão da frota)
CT_CALL_SLEEP = 0.5                # gentileza com a API do CT

REPO_DIR = Path(__file__).resolve().parent
CACHE_DIR = REPO_DIR / "outputs" / "dbs_cache"


# ───────────────────────── segredo / HTTP ─────────────────────────

def clean_secret(value: str) -> str:
    """Remove BOM (U+FEFF), zero-width (U+200B) e espaços — erro nº 1 da frota."""
    return (value or "").replace("﻿", "").replace("​", "").strip()


def get_jwt() -> str:
    jwt = clean_secret(os.environ.get("CT_JWT", ""))
    if not jwt:
        env_file = REPO_DIR / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip().startswith("CT_JWT="):
                    jwt = clean_secret(line.split("=", 1)[1])
                    break
    if not jwt:
        sys.exit("ERRO: CT_JWT não configurado (env var ou .env). Nunca rodo sem credencial real.")
    return jwt


def http_json(url: str, headers: dict | None = None, retries: int = 3, timeout: int = 90):
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers or {"User-Agent": USER_AGENT}, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
        except requests.RequestException as exc:  # rede/timeout
            last = repr(exc)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET {url} falhou após {retries} tentativas: {last}")


# ───────────────────────── câmbio ─────────────────────────

def resolve_rates(fx_flag: float | None) -> dict:
    """Retorna taxas por USD: {"BRL": x, "EUR": y, "USD": 1.0, "_fonte": ...}.
    Com --fx só o BRL é conhecido (ofertas em outras moedas serão puladas com contagem)."""
    if fx_flag:
        return {"BRL": float(fx_flag), "USD": 1.0, "_fonte": f"--fx {fx_flag} (manual)"}
    data = http_json(FX_URL)
    rates = data.get("rates") or {}
    if not rates.get("BRL"):
        raise RuntimeError("Fonte de câmbio sem BRL — abortando (nunca inventar câmbio).")
    out = {k: float(v) for k, v in rates.items()}
    out["_fonte"] = f"open.er-api.com ({data.get('time_last_update_utc', '?')})"
    return out


def to_brl(cents: int, currency: str, rates: dict) -> float | None:
    """Converte preço de oferta para BRL. Moeda sem taxa conhecida → None (pula, conta)."""
    amount = cents / 100.0
    cur = (currency or "").upper()
    if cur == "BRL":
        return amount
    per_usd = rates.get(cur)
    brl_per_usd = rates.get("BRL")
    if per_usd and brl_per_usd:
        return amount / per_usd * brl_per_usd
    return None


# ───────────────────────── CardTrader ─────────────────────────

def fetch_dbs_expansions(headers: dict) -> list[dict]:
    exps = http_json(f"{CT_API}/expansions", headers)
    return [e for e in exps if e.get("game_id") == GAME_ID_DBS]


def fetch_blueprints(exp_id: int, headers: dict) -> list[dict]:
    time.sleep(CT_CALL_SLEEP)
    return http_json(f"{CT_API}/blueprints/export?expansion_id={exp_id}", headers)


def fetch_offers(exp_id: int, headers: dict) -> dict:
    """{blueprint_id(int): [ofertas]} do marketplace ao vivo."""
    time.sleep(CT_CALL_SLEEP)
    raw = http_json(f"{CT_API}/marketplace/products?expansion_id={exp_id}", headers)
    return {int(k): v for k, v in raw.items()}


# ───────────────────── filtros de oferta (puros/testáveis) ─────────────────────

_EN_OK = {"", "en", "english"}


def offer_ok(offer: dict) -> bool:
    """NM EXATO + não-graded + não-assinada + idioma EN (ou ausente) + qty > 0."""
    props = offer.get("properties_hash") or {}
    if props.get("condition") != "Near Mint":
        return False
    if offer.get("graded") or props.get("graded"):
        return False
    if props.get("signed"):
        return False
    for key, val in props.items():
        if "language" in str(key).lower():
            if str(val or "").strip().lower() not in _EN_OK:
                return False
    return int(offer.get("quantity") or 0) > 0


def cheapest_offer_brl(offers: list[dict], rates: dict) -> tuple[float, int, int, int] | None:
    """(preço_BRL, qty, nº ofertas válidas, nº puladas por moeda) da oferta NM mais barata."""
    best = None
    valid = skipped_fx = 0
    for o in offers or []:
        if not offer_ok(o):
            continue
        price = o.get("price") or {}
        brl = to_brl(int(price.get("cents") or 0), price.get("currency"), rates)
        if brl is None:
            skipped_fx += 1
            continue
        valid += 1
        if best is None or brl < best[0]:
            best = (brl, int(o.get("quantity") or 0))
    if best is None:
        return None
    return (best[0], best[1], valid, skipped_fx)


# ───────────────────────── tcgcsv (referência) ─────────────────────────

def _cached_json(url: str, cache_file: Path, cache_hours: float):
    if cache_hours > 0 and cache_file.exists():
        age_h = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_h < cache_hours:
            return json.loads(cache_file.read_text(encoding="utf-8"))
    data = http_json(url)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


def load_tcg_index(cache_hours: float = 20.0, log=print) -> dict:
    """productId → {"name", "url", "prices": {subTypeName: marketPrice}} (cats 80 + 27)."""
    index: dict[int, dict] = {}
    for cat in TCGCSV_CATEGORIES:
        groups = _cached_json(f"{TCGCSV}/{cat}/groups", CACHE_DIR / f"groups_{cat}.json", cache_hours)
        gids = [g["groupId"] for g in groups.get("results", [])]
        log(f"[tcgcsv] categoria {cat}: {len(gids)} grupos")
        for gid in gids:
            prods = _cached_json(f"{TCGCSV}/{cat}/{gid}/products",
                                 CACHE_DIR / f"products_{cat}_{gid}.json", cache_hours)
            prices = _cached_json(f"{TCGCSV}/{cat}/{gid}/prices",
                                  CACHE_DIR / f"prices_{cat}_{gid}.json", cache_hours)
            for p in prods.get("results", []):
                index[int(p["productId"])] = {"name": p.get("name", ""), "url": p.get("url", ""), "prices": {}}
            for r in prices.get("results", []):
                pid = int(r["productId"])
                if pid in index and r.get("marketPrice") is not None:
                    index[pid]["prices"][r.get("subTypeName") or "?"] = float(r["marketPrice"])
    return index


def pick_subtype(version: str | None, prices: dict) -> tuple[str, float] | None:
    """Escolhe o subtipo TCGplayer coerente com a versão do blueprint CT.
    1 subtipo → ele; 'foil' na versão → Foil/Holofoil; senão Normal; senão o 1º.
    Sem nenhum market price → None (nunca inventa)."""
    avail = {k: v for k, v in (prices or {}).items() if v is not None}
    if not avail:
        return None
    if len(avail) == 1:
        return next(iter(avail.items()))
    ver = (version or "").lower()
    if "foil" in ver:
        for k in ("Foil", "Holofoil"):
            if k in avail:
                return k, avail[k]
    if "Normal" in avail:
        return "Normal", avail["Normal"]
    key = sorted(avail)[0]
    return key, avail[key]


# ───────────────────────── linha / classificação ─────────────────────────

def carta_label(bp: dict) -> str:
    name = bp.get("name", "").strip()
    ver = (bp.get("version") or "").strip()
    num = ((bp.get("fixed_properties") or {}).get("collector_number") or "").strip()
    label = name
    if ver:
        label += f" ({ver})"
    if num and num.lower() not in label.lower():
        label += f" {num}"
    return label


def classify(margin: float, ct_brl: float, tcg_brl: float, threshold: float) -> tuple[str, str]:
    """(bucket, flag). Buckets: compra | revisar | quase | resto."""
    junk = ct_brl < JUNK_RATIO * tcg_brl
    if margin >= threshold:
        if junk:
            return "revisar", "⚠️ possível lixo (<50% da ref)"
        return "compra", ""
    if margin >= threshold / 2:
        return "quase", "abaixo do limiar"
    return "resto", ""


def build_rows(expansion: dict, blueprints: list[dict], offers_by_bp: dict,
               tcg_index: dict, rates: dict, min_price_usd: float) -> tuple[list[dict], dict, list[dict]]:
    """Cruza blueprints × ofertas × referência.
    Retorna (linhas, contadores honestos, sem_ref) — sem_ref lista todo blueprint
    COM oferta NM viva que ficou sem referência TCG, com o motivo: nada some em
    silêncio (vai pro sidecar _semref.csv para conferência manual)."""
    stats = {"blueprints": 0, "sem_oferta_nm": 0, "sem_ref_tcg": 0,
             "abaixo_piso": 0, "avaliadas": 0, "ofertas_moeda_pulada": 0}
    brl_per_usd = rates["BRL"]
    rows = []
    semref: list[dict] = []
    for bp in blueprints:
        stats["blueprints"] += 1
        cheapest = cheapest_offer_brl(offers_by_bp.get(int(bp["id"]), []), rates)
        if cheapest is None:
            stats["sem_oferta_nm"] += 1
            continue
        ct_brl, qty, n_valid, skipped_fx = cheapest
        stats["ofertas_moeda_pulada"] += skipped_fx
        tcg_pid = bp.get("tcg_player_id")
        product = tcg_index.get(int(tcg_pid)) if tcg_pid else None
        chosen = pick_subtype(bp.get("version"), product["prices"]) if product else None
        if chosen is None:
            stats["sem_ref_tcg"] += 1
            if not tcg_pid:
                motivo = "tcg_player_id vazio no blueprint CT"
            elif product is None:
                motivo = "productId fora do índice tcgcsv"
            else:
                motivo = "produto tcgcsv sem market price"
            semref.append({"set": expansion.get("name", ""), "carta": carta_label(bp),
                           "ct_brl": round(ct_brl, 2), "motivo": motivo,
                           "oferta_url": f"https://www.cardtrader.com/cards/{bp['id']}"})
            continue
        subtype, tcg_usd = chosen
        if tcg_usd < min_price_usd:
            stats["abaixo_piso"] += 1
            continue
        tcg_brl = tcg_usd * brl_per_usd
        margin = (tcg_brl - ct_brl) / ct_brl
        stats["avaliadas"] += 1
        rows.append({
            "carta": carta_label(bp),
            "set": expansion.get("name", ""),
            "raridade": (bp.get("fixed_properties") or {}).get("dragonball_rarity") or "—",
            "ct_brl": ct_brl, "tcg_usd": tcg_usd, "tcg_brl": tcg_brl,
            "dif_brl": tcg_brl - ct_brl, "margem": margin,
            "qtd": qty, "ofertas_nm": n_valid, "subtipo": subtype,
            "oferta_url": f"https://www.cardtrader.com/cards/{bp['id']}",
            "tcg_url": product["url"],
        })
    return rows, stats, semref


# ───────────────────────── entrega ─────────────────────────

def fmt_brl(v: float) -> str:
    return f"R${v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


HEADER = "| # | Margem % | CT R$ | TCG US$ | Dif | Carta | Set | Raridade | Cond | Qtd | Links |"
SEP = "|---|---|---|---|---|---|---|---|---|---|---|"


def _table(rows: list[dict], bold: bool) -> list[str]:
    out = [HEADER, SEP]
    for i, r in enumerate(rows, 1):
        marg = f"{r['margem'] * 100:.1f}%"
        if bold:
            marg = f"**{marg}**"
        links = f"[oferta]({r['oferta_url']}) · [TCG]({r['tcg_url']})"
        out.append(
            f"| {i} | {marg} | {fmt_brl(r['ct_brl'])} | US${r['tcg_usd']:.2f} | "
            f"{fmt_brl(r['dif_brl'])} | {r['carta']} | {r['set']} | {r['raridade']} | NM | "
            f"{r['qtd']} | {links} |"
        )
    return out


def build_markdown(rows: list[dict], stats: dict, meta: dict) -> str:
    """Entrega canônica (padrão MYP): buckets COMPRA / REVISAR / QUASE + contagens honestas."""
    threshold = meta["threshold"]
    buckets = {"compra": [], "revisar": [], "quase": [], "resto": []}
    for r in rows:
        bucket, flag = classify(r["margem"], r["ct_brl"], r["tcg_brl"], threshold)
        r["flag"] = flag
        buckets[bucket].append(r)
    for b in buckets.values():
        b.sort(key=lambda x: -x["margem"])

    out = [f"## Scan DBS CardTrader → TCGplayer — {meta['data']}", ""]
    if meta.get("parcial"):
        out.append(f"⏳ **PARCIAL — {meta['parcial']} expansões varridas** (entrega incremental; "
                   f"a tabela cresce a cada expansão concluída).")
        out.append("")
    out.append(
        f"Expansões: **{meta['expansoes']}** · Referência: TCGplayer market via tcgcsv.com "
        f"(dump {meta.get('tcg_dump', 'n/d')}) · "
        f"Câmbio: US$1 = R${meta['fx']:.4f} ({meta['fx_fonte']}) · "
        f"Threshold: {threshold:.2f} (fração = {threshold * 100:.0f}%) · Piso ref: US${meta['min_price_usd']:.2f} · "
        f"Margem bruta = (TCG R$ − CT R$) ÷ CT R$, sem taxas · Ofertas: menor NM/EN não-graded AO VIVO"
    )
    out.append("")
    out.append(
        f"Cobertura honesta: {stats['blueprints']} blueprints · {stats['sem_oferta_nm']} sem oferta NM · "
        f"{stats['sem_ref_tcg']} sem referência TCG (join `tcg_player_id` vazio ou sem market price — ficam FORA, nunca inventamos) · "
        f"{stats['abaixo_piso']} abaixo do piso · **{stats['avaliadas']} avaliadas**"
    )
    if stats.get("ofertas_moeda_pulada"):
        out.append(f"⚠️ {stats['ofertas_moeda_pulada']} ofertas puladas por moeda sem câmbio conhecido.")
    out.append("")

    out.append(f"### 🟢 COMPRA (margem ≥ {threshold * 100:.0f}%) — {len(buckets['compra'])}")
    out.append("")
    if buckets["compra"]:
        out.extend(_table(buckets["compra"], bold=True))
    else:
        out.append("Nenhum item atinge o corte.")
    out.append("")

    if buckets["revisar"]:
        out.append(f"### 🚨 REVISAR — validar manualmente (margem ≥ corte, mas <50% da ref = possível lixo/scam) — {len(buckets['revisar'])}")
        out.append("")
        out.extend(_table(buckets["revisar"], bold=False))
        out.append("")

    out.append(f"### 🔎 Quase (entre {threshold * 50:.0f}% e {threshold * 100:.0f}%) — {len(buckets['quase'])}")
    out.append("")
    if buckets["quase"]:
        out.extend(_table(buckets["quase"], bold=False))
    else:
        out.append("Nenhum.")
    out.append("")
    out.append(f"_{len(buckets['resto'])} linhas avaliadas abaixo de {threshold * 50:.0f}% ficaram fora da tabela do chat "
               f"(sem corte silencioso: TODAS estão no CSV ao lado do .md)._")
    return "\n".join(out)


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    cols = ["margem", "ct_brl", "tcg_usd", "tcg_brl", "dif_brl", "carta", "set", "raridade",
            "qtd", "ofertas_nm", "subtipo", "flag", "oferta_url", "tcg_url"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: -x["margem"]):
            w.writerow(r)


def write_semref(semref: list[dict], path: Path) -> None:
    """Sidecar de honestidade: blueprints com oferta NM viva mas SEM referência TCG."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["set", "carta", "ct_brl", "motivo", "oferta_url"])
        w.writeheader()
        for r in semref:
            w.writerow(r)


# ───────────────────────── main ─────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scanner Dragon Ball Super: CardTrader → TCGplayer")
    ap.add_argument("--expansions", nargs="*", default=[],
                    help="códigos de expansão do CT (ex.: fuspromo fb04 bt31)")
    ap.add_argument("--all", action="store_true", help="todas as expansões DBS do CT (lento)")
    ap.add_argument("--list-expansions", action="store_true", help="lista códigos e sai")
    ap.add_argument("--threshold", type=float, default=0.30,
                    help="margem mínima em FRAÇÃO (0.30 = 30%%; convenção CT/COMC/Selados)")
    ap.add_argument("--min-price-usd", type=float, default=10.0,
                    help="piso de relevância da referência TCG (frota: ~US$10 p/ singles)")
    ap.add_argument("--fx", type=float, default=None, help="câmbio USD→BRL manual (senão: open.er-api.com)")
    ap.add_argument("--cache-hours", type=float, default=20.0, help="TTL do cache tcgcsv (0 = sem cache)")
    ap.add_argument("--out", default=None, help="prefixo de saída (default outputs/dbs_scan_<ts>)")
    args = ap.parse_args(argv)

    if args.threshold > 1.5:
        sys.exit(f"ERRO: --threshold aqui é FRAÇÃO (0.30 = 30%). Recebi {args.threshold} — "
                 f"isso seria {args.threshold * 100:.0f}%. (Pegadinha nº 1 da frota.)")

    headers = {"Authorization": f"Bearer {get_jwt()}", "User-Agent": USER_AGENT}
    print("[ct] baixando expansões DBS…")
    exps = fetch_dbs_expansions(headers)
    by_code = {e.get("code"): e for e in exps}

    if args.list_expansions:
        for e in sorted(exps, key=lambda x: x.get("code") or ""):
            print(f"{e.get('code'):<12} {e.get('name')}")
        return 0

    if args.all:
        # mais novas primeiro: parciais entregam cedo onde os deals costumam morar
        targets = sorted(exps, key=lambda e: -(e.get("id") or 0))
    else:
        if not args.expansions:
            sys.exit("ERRO: informe --expansions <codes> (ou --all, ou --list-expansions).")
        missing = [c for c in args.expansions if c not in by_code]
        if missing:
            sys.exit(f"ERRO: expansões não encontradas no CT: {missing} (use --list-expansions).")
        targets = [by_code[c] for c in args.expansions]

    rates = resolve_rates(args.fx)
    print(f"[fx] US$1 = R${rates['BRL']:.4f} ({rates['_fonte']})")
    print("[tcgcsv] carregando índice de referência (cats 80 + 27)…")
    tcg_index = load_tcg_index(cache_hours=args.cache_hours)
    print(f"[tcgcsv] {len(tcg_index)} produtos indexados")

    try:
        tcg_dump = requests.get("https://tcgcsv.com/last-updated.txt",
                                headers={"User-Agent": USER_AGENT}, timeout=15).text.strip()
    except requests.RequestException:
        tcg_dump = "n/d"

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = Path(args.out) if args.out else REPO_DIR / "outputs" / f"dbs_scan_{stamp}"
    prefix.parent.mkdir(parents=True, exist_ok=True)
    md_path = prefix.with_suffix(".md")

    meta = {
        "data": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "expansoes": (", ".join(e.get("code") or "?" for e in targets)
                      if len(targets) <= 12 else f"{len(targets)} expansões DBS (--all)"),
        "fx": rates["BRL"], "fx_fonte": rates["_fonte"],
        "threshold": args.threshold, "min_price_usd": args.min_price_usd,
        "tcg_dump": tcg_dump,
    }

    all_rows: list[dict] = []
    all_semref: list[dict] = []
    total_stats = {"blueprints": 0, "sem_oferta_nm": 0, "sem_ref_tcg": 0,
                   "abaixo_piso": 0, "avaliadas": 0, "ofertas_moeda_pulada": 0}
    for i, exp in enumerate(targets, 1):
        print(f"[scan] ({i}/{len(targets)}) {exp.get('code')} — {exp.get('name')}…", flush=True)
        bps = fetch_blueprints(exp["id"], headers)
        offers = fetch_offers(exp["id"], headers)
        rows, stats, semref = build_rows(exp, bps, offers, tcg_index, rates, args.min_price_usd)
        for k in total_stats:
            total_stats[k] += stats[k]
        all_rows.extend(rows)
        all_semref.extend(semref)
        # entrega PARCIAL cumulativa a cada expansão — run longo nunca fica mudo
        meta["parcial"] = f"{i}/{len(targets)}" if i < len(targets) else None
        md_path.write_text(build_markdown(all_rows, total_stats, meta), encoding="utf-8")
        write_csv(all_rows, prefix.with_suffix(".csv"))
        write_semref(all_semref, Path(str(prefix) + "_semref.csv"))
        print(f"       {stats['avaliadas']} avaliadas / {stats['blueprints']} blueprints "
              f"(acum.: {total_stats['avaliadas']} avaliadas) → parcial em {md_path}", flush=True)

    md = md_path.read_text(encoding="utf-8")
    print("\n" + md)
    print(f"\n[out] {md_path} + {prefix.with_suffix('.csv')} + {Path(str(prefix) + '_semref.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
