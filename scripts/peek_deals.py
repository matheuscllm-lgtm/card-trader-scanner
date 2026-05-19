#!/usr/bin/env python3
"""
peek_deals.py — inspetor de checkpoint JSONL em tempo real.

Le o sidecar .checkpoint.jsonl emitido pelo scanner v2.6+ enquanto o scan
ainda esta rodando. Permite operador ver progresso (sets completados,
oportunidades acumuladas) e top deals correntes sem precisar abrir XLSX
ou esperar o scan terminar.

Uso:
    python scripts/peek_deals.py outputs/priority_raw_<stamp>.xlsx.checkpoint.jsonl
    python scripts/peek_deals.py <checkpoint.jsonl> --top 20 --min-net 0.30

Sai com codigo 0 mesmo se checkpoint vazio (parse incremental, scan ainda em fly).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Garante UTF-8 stdout (paridade com scanner)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def parse_checkpoint(path: Path) -> tuple[dict, list[dict], list[dict]]:
    """Parse JSONL -> (header, set_completes, opportunities).

    Linhas invalidas (truncadas / parse fail) sao puladas silenciosamente —
    arquivo pode estar em meio a um write quando peek roda.
    """
    header: dict = {}
    sets_complete: list[dict] = []
    opps: list[dict] = []

    if not path.exists():
        return header, sets_complete, opps

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # Provavel ultima linha truncada por write em curso
                continue
            t = obj.get("_type")
            if t == "scan_header":
                header = obj
            elif t == "set_complete":
                sets_complete.append(obj)
            elif t == "opportunity":
                opps.append(obj)
            # ignora scan_complete e outros

    return header, sets_complete, opps


def fmt_brl(val: float | None) -> str:
    if val is None:
        return "—"
    return f"R$ {val:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def fmt_pct(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val * 100:5.1f}%"


def deal_profit_brl(opp: dict) -> float:
    """Lucro liquido em BRL pra ranking.

    Prefere `real_lucro_brl` (pos-validacao per-blueprint, com Hub fee 6%).
    Fallback `margin_brl` (pre-validacao, sem Hub fee).
    """
    real = opp.get("real_lucro_brl")
    if isinstance(real, (int, float)):
        return float(real)
    margin_brl = opp.get("margin_brl")
    if isinstance(margin_brl, (int, float)):
        return float(margin_brl)
    return 0.0


def deal_net_pct(opp: dict) -> float | None:
    """Net margin pct preferindo real_net_margin_pct, fallback net_margin_pct."""
    real = opp.get("real_net_margin_pct")
    if isinstance(real, (int, float)):
        return float(real)
    nmp = opp.get("net_margin_pct")
    if isinstance(nmp, (int, float)):
        return float(nmp)
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("checkpoint", type=Path,
                   help="Path do .checkpoint.jsonl emitido pelo scanner.")
    p.add_argument("--top", type=int, default=10,
                   help="Top N deals por lucro liquido (default 10).")
    p.add_argument("--min-net", type=float, default=None,
                   help="Filtra deals por net margin minima (fracao, ex 0.20).")
    args = p.parse_args()

    cp_path: Path = args.checkpoint
    header, sets_complete, opps = parse_checkpoint(cp_path)

    if not header and not sets_complete and not opps:
        print(f"Checkpoint vazio ou nao encontrado: {cp_path}")
        return

    # Header summary
    if header:
        stamp = header.get("stamp", "?")
        a = header.get("args", {})
        total = header.get("total_sets", "?")
        thr = a.get("threshold", "?")
        mnm = a.get("min_net_margin", "?")
        validate = a.get("validate_top", "?")
        print(f"Scan started:  {stamp}")
        print(f"Total sets:    {total}")
        print(f"Threshold:     {thr} (fracao)")
        print(f"Min net:       {mnm} (fracao)")
        print(f"Validate-top:  {validate}")
        print()

    total_sets = header.get("total_sets") if header else None
    done = len(sets_complete)
    if isinstance(total_sets, int) and total_sets > 0:
        pct = 100.0 * done / total_sets
        print(f"Sets completados: {done} / {total_sets}  ({pct:.1f}%)")
    else:
        print(f"Sets completados: {done}")
    print(f"Deals encontrados: {len(opps)}")

    # Filtro opcional
    filt = opps
    if args.min_net is not None:
        filt = [o for o in opps if (deal_net_pct(o) or 0) >= args.min_net]
        print(f"Filtrado por net >= {args.min_net}: {len(filt)} deals")

    if not filt:
        print("\nNenhum deal a exibir.")
        return

    # Top N por lucro liquido
    ranked = sorted(filt, key=deal_profit_brl, reverse=True)[: args.top]

    print(f"\n=== TOP {len(ranked)} deals por lucro liquido ===\n")
    # Header da tabela
    hdr = (
        f"{'#':>3}  "
        f"{'Carta':<32}  "
        f"{'Set':<8}  "
        f"{'CT R$':>10}  "
        f"{'TCG R$':>10}  "
        f"{'Net%':>6}  "
        f"{'Lucro':>10}  "
        f"{'Variant':<14}  "
        f"{'Val':<14}"
    )
    print(hdr)
    print("-" * len(hdr))

    for i, opp in enumerate(ranked, 1):
        listing = opp.get("listing", {}) or {}
        name = (listing.get("card_name") or opp.get("name") or "?")[:32]
        set_code = (listing.get("set_code") or opp.get("set_code") or "?")[:8]
        ct_brl = opp.get("ct_price_brl")
        tcg_brl = opp.get("tcg_market_brl")
        # Live price tem prioridade (pos-validacao)
        live = opp.get("live_price_brl")
        if isinstance(live, (int, float)):
            ct_show = live
        else:
            ct_show = ct_brl
        net = deal_net_pct(opp)
        profit = deal_profit_brl(opp)
        variant = (opp.get("price_variant_used") or "")[:14]
        validation = (opp.get("validation_status") or "?")[:14]

        print(
            f"{i:>3}  "
            f"{name:<32}  "
            f"{set_code:<8}  "
            f"{fmt_brl(ct_show):>10}  "
            f"{fmt_brl(tcg_brl):>10}  "
            f"{fmt_pct(net):>6}  "
            f"{fmt_brl(profit):>10}  "
            f"{variant:<14}  "
            f"{validation:<14}"
        )


if __name__ == "__main__":
    main()
