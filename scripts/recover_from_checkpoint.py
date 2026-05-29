#!/usr/bin/env python3
"""
recover_from_checkpoint.py — v2.6 (2026-05-17)

Reconstrói XLSX equivalente a partir de um .checkpoint.jsonl emitido pelo
scanner v2.6+. Use quando o scan crashou mid-run e queremos salvar o que
foi processado até o ponto de falha.

Uso:
    python scripts/recover_from_checkpoint.py \\
        --checkpoint outputs/weekly.xlsx.checkpoint.jsonl \\
        --output     outputs/weekly.recovered.xlsx \\
        [--min-net-margin 0.20]

Comportamento:
- Parse JSONL linha-a-linha. Linhas inválidas (parse fail / partial last
  line) são contadas + logadas mas não interrompem recovery.
- Reconstrói lista de Opportunity equivalente preservando todos os campos
  serializados pelo CheckpointWriter.
- Reusa `export_xlsx()` do scanner module pra gerar XLSX idêntico em
  schema ao output canônico (mesmas colunas/formatação).
- Aplica filtro `--min-net-margin` opcional (post-recovery) pra alinhar
  com fluxo `--min-net-margin` do scan original.

NÃO faz:
- Validação per-blueprint (precisa CT_JWT + nova rodada API). Status fica
  como foi gravado no checkpoint — sem validation se scan crashou antes
  da fase 3.
- Cross-check vs CT live. O JSONL é a verdade do que foi visto durante
  o scan.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Garante UTF-8 stdout (paridade com scanner)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Path do scanner principal (mesmo dir do parent, scripts/ → ..)
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import lazy — depende de venv com openpyxl etc. instalado.
from cardtrader_scanner import (  # noqa: E402
    Listing,
    Opportunity,
    export_xlsx,
)


def parse_checkpoint(checkpoint_path: Path) -> tuple[list[Opportunity], dict, dict]:
    """Parse JSONL → (opportunities, header, stats_summary).

    Retorna:
        opportunities: lista reconstruída de Opportunity
        header: dict do scan_header (ou {} se ausente)
        stats_summary: contadores agregados (sets_complete, opps_count, etc)
    """
    opportunities: list[Opportunity] = []
    header: dict = {}
    sets_complete: list[dict] = []
    scan_complete: dict = {}
    bad_lines = 0
    total_lines = 0

    with open(checkpoint_path, "r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            total_lines += 1
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as e:
                bad_lines += 1
                log.warning(
                    f"Linha {line_no} JSON inválido (skipando): {e} "
                    f"[raw={raw[:80]}...]"
                )
                continue

            typ = obj.get("_type")
            if typ == "scan_header":
                header = obj
            elif typ == "set_complete":
                sets_complete.append(obj)
            elif typ == "scan_complete":
                scan_complete = obj
            elif typ == "set_progress":
                # PR-F (2026-05-28): telemetria de progresso intra-set (heartbeat
                # JSONL). NÃO é um deal — ignora silenciosamente no recovery.
                continue
            elif typ == "opportunity":
                try:
                    opp = _reconstruct_opportunity(obj)
                    opportunities.append(opp)
                except Exception as e:
                    bad_lines += 1
                    log.warning(
                        f"Linha {line_no} opportunity malformed (skipando): "
                        f"{type(e).__name__}: {e}"
                    )
            else:
                log.warning(f"Linha {line_no} _type desconhecido: {typ!r}")

    stats_summary = {
        "total_lines": total_lines,
        "bad_lines": bad_lines,
        "sets_complete": len(sets_complete),
        "opps_recovered": len(opportunities),
        "scan_finished_cleanly": bool(scan_complete),
    }
    return opportunities, header, stats_summary


def _reconstruct_opportunity(d: dict) -> Opportunity:
    """Rebuild Opportunity from asdict()-serialized dict.

    CheckpointWriter denormalizou alguns campos no topo (set_code,
    blueprint_id, name) — esses são redundantes com o nested `listing`
    e ignorados aqui.
    """
    listing_d = d["listing"]
    listing = Listing(
        product_id=listing_d["product_id"],
        blueprint_id=listing_d["blueprint_id"],
        card_name=listing_d["card_name"],
        set_code=listing_d["set_code"],
        set_name=listing_d["set_name"],
        collector_number=listing_d["collector_number"],
        condition=listing_d["condition"],
        language=listing_d["language"],
        price_cents=listing_d["price_cents"],
        price_currency=listing_d["price_currency"],
        price_brl=listing_d["price_brl"],
        quantity=listing_d["quantity"],
        foil=listing_d["foil"],
        graded=listing_d["graded"],
        seller_username=listing_d["seller_username"],
        seller_can_sell_via_hub=listing_d["seller_can_sell_via_hub"],
        seller_user_type=listing_d["seller_user_type"],
        cardtrader_url=listing_d["cardtrader_url"],
        rarity=listing_d.get("rarity", ""),
    )
    return Opportunity(
        listing=listing,
        tcg_market_usd=d["tcg_market_usd"],
        tcg_market_brl=d["tcg_market_brl"],
        ct_price_brl=d["ct_price_brl"],
        margin_pct=d["margin_pct"],
        margin_brl=d["margin_brl"],
        estimated_shipping_brl=d["estimated_shipping_brl"],
        net_margin_pct=d["net_margin_pct"],
        scanned_at=d.get("scanned_at", datetime.now().isoformat(timespec="seconds")),
        validation_status=d.get("validation_status", "NOT_VALIDATED"),
        live_price_brl=d.get("live_price_brl"),
        real_margin_pct=d.get("real_margin_pct"),
        real_net_margin_pct=d.get("real_net_margin_pct"),
        real_lucro_brl=d.get("real_lucro_brl"),
        markup_pct=d.get("markup_pct"),
        markup_tier=d.get("markup_tier"),
        # v2.7.1 (2026-05-18): backward-compat com checkpoints pré-v2.7.1.
        # Get com default None — checkpoints antigos não tinham este campo.
        tcg_url=d.get("tcg_url"),
        # v2.8 Layer 4: variante TCGPlayer usada no cálculo. Get com default
        # None — checkpoints pré-v2.8 não tinham. Sem isso o recovery perdia
        # a coluna Variant (operador não conseguia validar foil/holofoil).
        price_variant_used=d.get("price_variant_used"),
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description="Recover XLSX from scanner v2.6 .checkpoint.jsonl",
    )
    p.add_argument("--checkpoint", type=Path, required=True,
                   help="Path para o .checkpoint.jsonl (sidecar do scan crashado)")
    p.add_argument("--output", type=Path, required=True,
                   help="Path para o XLSX de saída")
    p.add_argument("--min-net-margin", type=float, default=0.0,
                   help="Filtro pós-recovery por margem REAL líq (fração, ex 0.20)")
    p.add_argument("--threshold", type=float, default=0.0,
                   help="Threshold informativo gravado no XLSX Stats (default 0)")
    args = p.parse_args()

    if not args.checkpoint.exists():
        log.error(f"Checkpoint não encontrado: {args.checkpoint}")
        return 2

    # Auto-converte threshold/min_net_margin se vier como percent (>1)
    if args.min_net_margin > 1.0:
        log.warning(
            f"--min-net-margin {args.min_net_margin} > 1.0 parece percentual, "
            f"convertendo: {args.min_net_margin/100}"
        )
        args.min_net_margin = args.min_net_margin / 100.0
    if args.threshold > 1.0:
        log.warning(
            f"--threshold {args.threshold} > 1.0 parece percentual, "
            f"convertendo: {args.threshold/100}"
        )
        args.threshold = args.threshold / 100.0

    log.info(f"Parsing {args.checkpoint}")
    opps, header, summary = parse_checkpoint(args.checkpoint)
    log.info(
        f"Recovered {summary['opps_recovered']} opportunities across "
        f"{summary['sets_complete']} sets from checkpoint "
        f"({summary['total_lines']} lines, {summary['bad_lines']} skipped)"
    )

    if header:
        log.info(
            f"Header: stamp={header.get('stamp')} "
            f"total_sets={header.get('total_sets')} "
            f"args={list((header.get('args') or {}).keys())[:6]}..."
        )

    if not summary["scan_finished_cleanly"]:
        log.warning(
            "scan_complete line não presente — checkpoint parece de um scan "
            "que NÃO terminou normalmente (crash, ctrl-c, OOM). Recovery "
            "produzirá XLSX com dados parciais."
        )

    if args.min_net_margin > 0:
        before = len(opps)
        opps = [o for o in opps if (o.real_net_margin_pct or o.net_margin_pct or 0) >= args.min_net_margin]
        log.info(f"Filtro --min-net-margin {args.min_net_margin:.0%}: {before} → {len(opps)}")

    # Re-sort por margem líq REAL (fallback margem bruta) — comportamento equiv
    # ao scanner pós-validação.
    def _key(o: Opportunity) -> float:
        return o.real_net_margin_pct if o.real_net_margin_pct is not None else o.margin_pct
    opps.sort(key=_key, reverse=True)

    # FX rates — não temos os exatos do scan original (não estão no JSONL).
    # Usa placeholders e flagueia na sheet Stats. Se quiser fidelidade total,
    # gravar usd_brl / eur_brl no header é uma melhoria futura.
    stats_for_xlsx = {
        "recovered_from_checkpoint": str(args.checkpoint.name),
        "opps_recovered": summary["opps_recovered"],
        "sets_complete_in_checkpoint": summary["sets_complete"],
        "bad_lines_in_checkpoint": summary["bad_lines"],
        "scan_finished_cleanly": summary["scan_finished_cleanly"],
    }
    # Mescla header args como string info no stats
    if header.get("args"):
        stats_for_xlsx["original_scan_args"] = json.dumps(
            {k: header["args"][k] for k in sorted(header["args"]) if header["args"][k] is not None},
            ensure_ascii=False,
        )[:200]

    log.info(f"Gerando XLSX: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # FX rate placeholder: melhor seria gravar no header do checkpoint
    # (TODO v2.7). Aqui usa 0 — sheet Stats fica explícita sobre isso.
    export_xlsx(
        opps,
        stats_for_xlsx,
        args.output,
        usd_brl=0.0,
        eur_brl=0.0,
        threshold=args.threshold,
    )
    log.info(
        f"✓ Recovered {len(opps)} opportunities across "
        f"{summary['sets_complete']} sets from checkpoint"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
