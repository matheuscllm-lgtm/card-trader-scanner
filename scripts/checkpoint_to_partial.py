#!/usr/bin/env python3
"""
checkpoint_to_partial.py — gerador de PARCIAIS ao vivo (2026-06-02)

Lê o `.checkpoint.jsonl` emitido pelo scanner v2.6+ DURANTE o scan e produz
artefatos leves e legíveis para revisão manual incremental:

    - PARTIAL_DEALS.md  → tabela markdown (renderiza direto no GitHub)
    - partial_deals.csv → todos os candidatos (importável em planilha)

Diferente de `scripts/recover_from_checkpoint.py`, este NÃO depende do módulo
do scanner nem de openpyxl/pandas — é stdlib puro, rápido e seguro pra rodar
a cada poucos minutos dentro do job do GitHub Actions enquanto o scan corre.

⚠️  Os deals do checkpoint são CANDIDATOS pré-validação (margem bruta ≥
threshold). A validação per-blueprint (Hub fee 6% + preço real de checkout) e
a Decisão mecânica só entram no relatório FINAL. Use os parciais para começar
a conferência manual; confirme números no relatório final.

Uso:
    python scripts/checkpoint_to_partial.py \\
        --checkpoint scan-state/scan.xlsx.checkpoint.jsonl \\
        --out-md     partials/PARTIAL_DEALS.md \\
        --out-csv    partials/partial_deals.csv \\
        [--top 80]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _num(v, default=0.0):
    """Coerção tolerante para float (None/'' → default)."""
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def best_net(o: dict) -> float:
    """Melhor margem líquida disponível: REAL validada > net bruta > margem bruta."""
    for k in ("real_net_margin_pct", "net_margin_pct", "margin_pct"):
        v = o.get(k)
        if v is not None:
            return _num(v)
    return 0.0


def best_lucro(o: dict) -> float:
    """Melhor lucro disponível: REAL validado > lucro bruto."""
    v = o.get("real_lucro_brl")
    if v is not None:
        return _num(v)
    return _num(o.get("margin_brl"))


def card_label(lst: dict) -> str:
    """'Nome Número' (ex: 'Minccino 182') pra copiar-e-colar na busca do site."""
    name = (lst.get("card_name") or "").strip()
    num = (str(lst.get("collector_number") or "")).strip()
    if num and num.lower() not in name.lower():
        return f"{name} {num}".strip()
    return name or "(sem nome)"


def parse_checkpoint(path: Path):
    """Parse tolerante do JSONL. Retorna (deals, meta)."""
    deals: list[dict] = []
    header: dict = {}
    sets_complete = 0
    scan_complete = None
    last_progress = None
    bad_lines = 0
    seen_pids: dict = {}

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                o = json.loads(raw)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            typ = o.get("_type")
            if typ == "opportunity":
                lst = o.get("listing") or {}
                pid = lst.get("product_id")
                row = {
                    "card": card_label(lst),
                    "set_code": lst.get("set_code") or o.get("set_code") or "",
                    "set_name": lst.get("set_name") or "",
                    "collector_number": lst.get("collector_number") or "",
                    "rarity": lst.get("rarity") or "",
                    "foil": lst.get("foil"),
                    "quantity": lst.get("quantity"),
                    "language": lst.get("language") or "",
                    "price_ct_brl": _num(o.get("ct_price_brl") or lst.get("price_brl")),
                    "tcg_brl": _num(o.get("tcg_market_brl")),
                    "tcg_usd": _num(o.get("tcg_market_usd")),
                    "margin_pct": _num(o.get("margin_pct")),
                    "net_pct": best_net(o),
                    "lucro_brl": best_lucro(o),
                    "validation": o.get("validation_status") or "NOT_VALIDATED",
                    "markup_tier": o.get("markup_tier") or "",
                    "seller": lst.get("seller_username") or "",
                    "hub": bool(lst.get("seller_can_sell_via_hub")),
                    "url": lst.get("cardtrader_url") or "",
                }
                # Dedup por product_id, mantendo a maior margem bruta.
                if pid is not None and pid in seen_pids:
                    if row["margin_pct"] > seen_pids[pid]["margin_pct"]:
                        seen_pids[pid] = row
                else:
                    if pid is not None:
                        seen_pids[pid] = row
                    else:
                        deals.append(row)
            elif typ == "set_complete":
                sets_complete += 1
            elif typ == "scan_header":
                header = o
            elif typ == "scan_complete":
                scan_complete = o
            elif typ == "set_progress":
                last_progress = o

    deals.extend(seen_pids.values())
    deals.sort(key=lambda r: (r["net_pct"], r["margin_pct"]), reverse=True)

    total_sets = (header.get("total_sets") if header else None)
    meta = {
        "total_sets": total_sets,
        "sets_complete": sets_complete,
        "deals": len(deals),
        "bad_lines": bad_lines,
        "finished": scan_complete is not None,
        "last_progress": last_progress,
        "header_stamp": header.get("stamp") if header else None,
    }
    return deals, meta


def write_csv(deals: list[dict], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "rank", "net_pct", "margin_pct", "lucro_brl", "card", "set_code",
        "set_name", "collector_number", "rarity", "foil", "quantity",
        "language", "price_ct_brl", "tcg_brl", "tcg_usd", "validation",
        "markup_tier", "seller", "hub", "url",
    ]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, r in enumerate(deals, 1):
            w.writerow([
                i, round(r["net_pct"], 4), round(r["margin_pct"], 4),
                round(r["lucro_brl"], 2), r["card"], r["set_code"],
                r["set_name"], r["collector_number"], r["rarity"], r["foil"],
                r["quantity"], r["language"], round(r["price_ct_brl"], 2),
                round(r["tcg_brl"], 2), round(r["tcg_usd"], 2), r["validation"],
                r["markup_tier"], r["seller"], r["hub"], r["url"],
            ])


def write_md(deals: list[dict], meta: dict, out_md: Path, top: int) -> None:
    out_md.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status = "✅ CONCLUÍDO" if meta["finished"] else "🟡 EM ANDAMENTO"
    total_sets = meta["total_sets"] if meta["total_sets"] is not None else "?"
    lp = meta.get("last_progress") or {}
    lp_txt = (
        f"{lp.get('set_code')} (i={lp.get('i')}/{lp.get('total')})"
        if lp else "—"
    )
    lines = []
    lines.append("# Parciais do scan CardTrader — deals encontrados até agora")
    lines.append("")
    lines.append(
        "> ⚠️ **Candidatos PRÉ-validação** (margem bruta ≥ threshold). "
        "O relatório FINAL aplica validação per-blueprint (Hub fee 6% + preço "
        "real de checkout) e a Decisão mecânica. Use esta lista para começar a "
        "conferência manual; confirme os números no relatório final."
    )
    lines.append("")
    lines.append(f"- **Atualizado (UTC):** {now}")
    lines.append(f"- **Status:** {status}")
    lines.append(f"- **Sets concluídos:** {meta['sets_complete']} / {total_sets}")
    lines.append(f"- **Set em progresso:** {lp_txt}")
    lines.append(f"- **Candidatos (deals) até agora:** {meta['deals']}")
    if meta["bad_lines"]:
        lines.append(f"- **Linhas inválidas no checkpoint (ignoradas):** {meta['bad_lines']}")
    lines.append("")
    shown = min(top, len(deals))
    lines.append(f"## Top {shown} candidatos (por margem líquida)")
    lines.append("")
    if not deals:
        lines.append("_Nenhum candidato ainda — scan recém começou ou sets iniciais sem deals._")
    else:
        lines.append("| # | Margem | Lucro R$ | Carta | Set | CT R$ | TCG R$ | Valid. | Seller | Link |")
        lines.append("|--:|--:|--:|---|---|--:|--:|---|---|---|")
        for i, r in enumerate(deals[:top], 1):
            link = f"[abrir]({r['url']})" if r["url"] else "—"
            lines.append(
                f"| {i} | {r['net_pct']*100:.0f}% | {r['lucro_brl']:.0f} | "
                f"{r['card']} | {r['set_code']} | {r['price_ct_brl']:.0f} | "
                f"{r['tcg_brl']:.0f} | {r['validation']} | {r['seller']} | {link} |"
            )
        if len(deals) > top:
            lines.append("")
            lines.append(f"_… +{len(deals) - top} candidatos no `partial_deals.csv`._")
    lines.append("")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="Gera parciais (MD+CSV) do checkpoint JSONL.")
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--out-md", type=Path, required=True)
    p.add_argument("--out-csv", type=Path, required=True)
    p.add_argument("--top", type=int, default=80, help="Linhas na tabela MD (default 80).")
    args = p.parse_args()

    if not args.checkpoint.exists():
        # Sem checkpoint ainda (scan recém-iniciado): emite placeholder, sai 0.
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(
            "# Parciais do scan CardTrader\n\n_Checkpoint ainda não criado "
            "(scan iniciando)._\n", encoding="utf-8",
        )
        print(f"[partial] checkpoint ausente: {args.checkpoint} — placeholder escrito")
        return 0

    deals, meta = parse_checkpoint(args.checkpoint)
    write_csv(deals, args.out_csv)
    write_md(deals, meta, args.out_md, args.top)
    print(
        f"[partial] {meta['deals']} candidatos · sets {meta['sets_complete']}/"
        f"{meta['total_sets']} · finished={meta['finished']} · "
        f"bad_lines={meta['bad_lines']} → {args.out_md}, {args.out_csv}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
