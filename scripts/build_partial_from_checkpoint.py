"""Build a partial scanner-format XLSX from in-progress checkpoint JSONL.

Reads `_type: opportunity` events and writes the same column schema produced
by `cardtrader_scanner.py` so postprocess / psa_grading_analysis can consume it.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook


HEADERS = [
    "Card Name", "Set", "Nº", "Rarity", "Condição", "Idioma",
    "Scan R$ (raw)", "Moeda Original CT", "LIVE R$ (real)", "Markup %", "Markup Tier",
    "Validation Status", "TCG Market (BRL)", "TCG Market (USD)",
    "Margem % (scan)", "Margem % REAL", "Net Margin % (scan)", "Net Margin % REAL",
    "Lucro R$ REAL", "Frete Est. R$", "Qtd", "Foil", "Variant",
    "Seller", "Tipo Seller", "Hub",
    "Link CardTrader", "Link TCG", "Scanned At",
]


def build_partial(checkpoint: Path, out: Path, min_net_margin: float | None) -> int:
    wb = Workbook()
    ws = wb.active
    ws.title = "Oportunidades"
    ws.append(HEADERS)

    count = 0
    seen = set()
    with checkpoint.open() as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("_type") != "opportunity":
                continue

            lst = e.get("listing", {})
            # Use real metrics if available, else fall back to scan metrics
            net_real = e.get("real_net_margin_pct")
            net_scan = e.get("net_margin_pct")
            net_used = net_real if net_real is not None else net_scan
            if min_net_margin is not None and (net_used is None or net_used < min_net_margin):
                continue

            blueprint = e.get("blueprint_id")
            seller = lst.get("seller_username")
            cond = lst.get("condition")
            key = (blueprint, seller, cond)
            if key in seen:
                continue
            seen.add(key)

            live_brl = e.get("live_price_brl") or e.get("ct_price_brl")
            scan_brl = e.get("ct_price_brl")
            real_lucro = e.get("real_lucro_brl") or e.get("margin_brl")
            margin_real = e.get("real_margin_pct") if e.get("real_margin_pct") is not None else e.get("margin_pct")

            row = [
                lst.get("card_name"),
                f"{lst.get('set_name')} ({lst.get('set_code')})",
                lst.get("collector_number"),
                lst.get("rarity"),
                cond,
                (lst.get("language") or "").upper() if lst.get("language") else "",
                scan_brl,
                lst.get("price_currency"),
                live_brl,
                e.get("markup_pct"),
                e.get("markup_tier"),
                e.get("validation_status"),
                e.get("tcg_market_brl"),
                e.get("tcg_market_usd"),
                e.get("margin_pct"),
                margin_real,
                net_scan,
                net_real if net_real is not None else net_scan,
                real_lucro,
                e.get("estimated_shipping_brl"),
                lst.get("quantity"),
                "Yes" if lst.get("foil") else "No",
                e.get("price_variant_used"),
                seller,
                lst.get("seller_user_type"),
                "Yes" if lst.get("seller_can_sell_via_hub") else "No",
                lst.get("cardtrader_url"),
                e.get("tcg_url"),
                e.get("scanned_at"),
            ]
            ws.append(row)
            count += 1

    wb.save(out)
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--min-net-margin", type=float, default=None,
                    help="Filtro opcional. Default = sem filtro (mantém raw).")
    args = ap.parse_args()
    n = build_partial(Path(args.checkpoint), Path(args.output), args.min_net_margin)
    print(f"Wrote {n} opportunities to {args.output}")


if __name__ == "__main__":
    main()
