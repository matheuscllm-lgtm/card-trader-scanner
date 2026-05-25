"""PSA grading profitability analysis via PriceCharting scrape.

For each card in a scanner XLSX output, fetches Ungraded / PSA 9 / PSA 10
prices from pricecharting.com and reports cards where grading is profitable
(PSA 9 sale price > raw NM price + grading fee).

Usage:
    python psa_grading_analysis.py --input <scan.xlsx> [--input <scan2.xlsx> ...] \
        --output psa_analysis.xlsx [--grading-fee 50] [--rate-limit 1.0]
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests
from openpyxl import Workbook, load_workbook

SCRIPT_DIR = Path(__file__).parent
CACHE_PATH = SCRIPT_DIR / ".pricecharting_cache.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
SEARCH_URL = "https://www.pricecharting.com/search-products?q={q}&type=prices"

PRICE_ID_RE = re.compile(
    r'<td\s+id="([a-z_]+_price)"[^>]*>\s*<span class="price js-price">\s*\$?([\d,\.]+|N/A)',
    re.I,
)
GAME_URL_RE = re.compile(r'href="(https://www\.pricecharting\.com/game/pokemon-[a-z0-9\-]+/[a-z0-9\-]+)"')


PRICE_FIELD_MAP = {
    "used_price": "ungraded",
    "complete_price": "psa7",
    "new_price": "psa8",
    "graded_price": "psa9",
    "box_only_price": "psa95",
    "manual_only_price": "psa10",
}


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


def _clean_set_name(set_name: str) -> str:
    """Strip trailing `(code)` and similar noise from scanner set names."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", set_name).strip()


def search_card_url(card_name: str, set_name: str, session: requests.Session) -> str | None:
    """Search PriceCharting and return the first /game/pokemon-* URL."""
    query = f"{card_name} {_clean_set_name(set_name)}"
    url = SEARCH_URL.format(q=quote_plus(query))
    r = session.get(url, timeout=20)
    if r.status_code != 200:
        return None
    m = GAME_URL_RE.search(r.text)
    return m.group(1) if m else None


def fetch_prices(url: str, session: requests.Session) -> dict:
    """Fetch the card page and parse all price fields by ID."""
    r = session.get(url, timeout=20)
    if r.status_code != 200:
        return {}
    prices: dict[str, float | None] = {}
    for m in PRICE_ID_RE.finditer(r.text):
        field = PRICE_FIELD_MAP.get(m.group(1))
        if not field:
            continue
        raw = m.group(2).replace(",", "")
        try:
            prices[field] = float(raw)
        except ValueError:
            prices[field] = None
    return prices


def get_card_prices(card_name: str, set_name: str, session: requests.Session,
                    cache: dict, rate_limit: float = 1.0) -> dict:
    """Lookup PSA prices for one card, with disk cache."""
    key = f"{card_name}|{set_name}".lower()
    if key in cache:
        return cache[key]

    result = {"card_name": card_name, "set_name": set_name, "url": None, "prices": {}, "error": None}
    try:
        url = search_card_url(card_name, set_name, session)
        if not url:
            result["error"] = "no_search_match"
        else:
            result["url"] = url
            time.sleep(rate_limit)
            result["prices"] = fetch_prices(url, session)
            if not result["prices"]:
                result["error"] = "no_prices_parsed"
    except requests.RequestException as e:
        result["error"] = f"request_error: {type(e).__name__}"

    cache[key] = result
    _save_cache(cache)
    time.sleep(rate_limit)
    return result


def load_scan_rows(paths: list[Path]) -> list[dict]:
    """Read all scanner XLSX outputs and return a deduped list of cards."""
    seen: set[tuple] = set()
    cards: list[dict] = []
    for p in paths:
        if not p.exists():
            print(f"WARN: missing input {p}", file=sys.stderr)
            continue
        wb = load_workbook(p, read_only=True)
        if "Oportunidades" not in wb.sheetnames:
            print(f"WARN: no Oportunidades sheet in {p}", file=sys.stderr)
            continue
        ws = wb["Oportunidades"]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        headers = [str(h or "").strip() for h in rows[0]]
        idx = {h: i for i, h in enumerate(headers)}

        # Best-effort column resolution
        def col(*candidates):
            for c in candidates:
                if c in idx:
                    return idx[c]
            return None

        i_card = col("Card Name", "Carta", "Card")
        i_set = col("Set", "Expansion", "Expansão")
        i_num = col("Nº", "Number", "Num")
        # v2.x scanner columns: live BRL (markup-adjusted price actually paid) + TCG USD
        i_live_brl = col("LIVE R$ (real)", "Live R$", "LIVE R$")
        i_scan_brl = col("Scan R$ (raw)", "Scan R$")
        i_tcg_usd = col("TCG Market (USD)", "TCG USD")
        i_tcg_brl = col("TCG Market (BRL)", "TCG BRL")
        i_link = col("Link CardTrader", "Link CT", "Link")
        i_seller = col("Seller")
        i_foil = col("Foil")
        i_net = col("Net Margin % REAL", "Net Margin %", "Net %")
        i_rarity = col("Rarity", "Raridade")

        for r in rows[1:]:
            if i_card is None or i_set is None:
                break
            card_name = str(r[i_card] or "").strip()
            set_name = str(r[i_set] or "").strip()
            if not card_name or not set_name:
                continue
            num = str(r[i_num] or "").strip() if i_num is not None else ""
            key = (card_name.lower(), set_name.lower(), num)
            if key in seen:
                continue
            seen.add(key)

            # Compute USD/BRL FX rate from TCG columns (live in scan)
            fx = None
            if i_tcg_usd is not None and i_tcg_brl is not None:
                u = r[i_tcg_usd]
                b = r[i_tcg_brl]
                if u and b:
                    fx = float(b) / float(u)
            # Convert live BRL → USD (the price actually paid by the buyer after markup)
            live_brl = r[i_live_brl] if i_live_brl is not None else None
            scan_brl = r[i_scan_brl] if i_scan_brl is not None else None
            cost_brl = live_brl or scan_brl
            cost_usd = (float(cost_brl) / fx) if (cost_brl and fx) else None

            cards.append({
                "card_name": card_name,
                "set_name": set_name,
                "number": num,
                "rarity": str(r[i_rarity]) if i_rarity is not None and r[i_rarity] else "",
                "price_usd": cost_usd,
                "live_brl": float(live_brl) if live_brl else None,
                "tcg_usd": float(r[i_tcg_usd]) if i_tcg_usd is not None and r[i_tcg_usd] else None,
                "fx_rate": fx,
                "link_ct": str(r[i_link] or "") if i_link is not None else "",
                "seller": str(r[i_seller] or "") if i_seller is not None else "",
                "foil": r[i_foil] if i_foil is not None else None,
                "net_margin_pct": r[i_net] if i_net is not None else None,
                "source_file": p.name,
            })
        wb.close()
    return cards


def build_analysis(cards: list[dict], grading_fee: float, rate_limit: float) -> list[dict]:
    """For each card, fetch PSA prices and compute grading profit."""
    cache = _load_cache()
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    rows: list[dict] = []
    n = len(cards)
    for i, c in enumerate(cards, 1):
        print(f"[{i}/{n}] {c['card_name']} ({c['set_name']})", flush=True)
        pc = get_card_prices(c["card_name"], c["set_name"], session, cache, rate_limit)
        prices = pc.get("prices", {}) or {}
        raw_nm = c.get("price_usd")
        ungraded_pc = prices.get("ungraded")
        psa9 = prices.get("psa9")
        psa10 = prices.get("psa10")

        # Decision threshold: grade if PSA9 sale - raw NM cost - fee > 0
        # i.e. PSA9 > raw_NM + fee
        psa9_profit = None
        psa9_margin_pct = None
        psa10_profit = None
        psa10_margin_pct = None
        grade_worth_it_psa9 = None

        if raw_nm and psa9:
            psa9_profit = psa9 - raw_nm - grading_fee
            psa9_margin_pct = psa9_profit / (raw_nm + grading_fee) * 100 if (raw_nm + grading_fee) else None
            grade_worth_it_psa9 = psa9 > (raw_nm + grading_fee)
        if raw_nm and psa10:
            psa10_profit = psa10 - raw_nm - grading_fee
            psa10_margin_pct = psa10_profit / (raw_nm + grading_fee) * 100 if (raw_nm + grading_fee) else None

        rows.append({
            "card_name": c["card_name"],
            "set_name": c["set_name"],
            "number": c["number"],
            "rarity": c.get("rarity", ""),
            "seller": c["seller"],
            "foil": c["foil"],
            "raw_nm_usd": raw_nm,
            "live_brl": c.get("live_brl"),
            "fx_rate": c.get("fx_rate"),
            "tcg_market_usd": c.get("tcg_usd"),
            "pc_ungraded_usd": ungraded_pc,
            "psa9_usd": psa9,
            "psa9_profit_usd": psa9_profit,
            "psa9_margin_pct": psa9_margin_pct,
            "psa9_worth_grading": grade_worth_it_psa9,
            "psa10_usd": psa10,
            "psa10_profit_usd": psa10_profit,
            "psa10_margin_pct": psa10_margin_pct,
            "link_ct": c["link_ct"],
            "link_pc": pc.get("url") or "",
            "error": pc.get("error"),
            "source_file": c["source_file"],
        })
    return rows


def write_xlsx(rows: list[dict], path: Path, grading_fee: float) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "PSA Analysis"
    headers = [
        "Card", "Set", "Nº", "Rarity", "Seller", "Foil",
        "Raw NM (USD)", "TCG Mkt (USD)", "PC Ungraded (USD)",
        "PSA 9 (USD)", "PSA 9 Lucro (USD)", "PSA 9 Margem %", "PSA 9 vale graded?",
        "PSA 10 (USD)", "PSA 10 Lucro (USD)", "PSA 10 Margem %",
        "Link CT", "Link PriceCharting", "Erro", "Origem",
    ]
    ws.append(headers)
    for r in rows:
        ws.append([
            r["card_name"], r["set_name"], r["number"], r.get("rarity", ""), r["seller"], r["foil"],
            round(r["raw_nm_usd"], 2) if r["raw_nm_usd"] else None,
            r.get("tcg_market_usd"),
            r["pc_ungraded_usd"],
            r["psa9_usd"], round(r["psa9_profit_usd"], 2) if r["psa9_profit_usd"] is not None else None,
            f"{r['psa9_margin_pct']:.1f}%" if r["psa9_margin_pct"] is not None else None,
            "SIM" if r["psa9_worth_grading"] else ("NÃO" if r["psa9_worth_grading"] is False else None),
            r["psa10_usd"], round(r["psa10_profit_usd"], 2) if r["psa10_profit_usd"] is not None else None,
            f"{r['psa10_margin_pct']:.1f}%" if r["psa10_margin_pct"] is not None else None,
            r["link_ct"], r["link_pc"], r["error"], r["source_file"],
        ])

    info_ws = wb.create_sheet("Info")
    info_ws.append(["Parâmetros"])
    info_ws.append(["Grading fee (USD)", grading_fee])
    info_ws.append(["Total cards", len(rows)])
    info_ws.append(["Decisão SIM = PSA 9 > Raw NM + Grading Fee"])
    info_ws.append(["Fonte preços graded", "pricecharting.com"])

    wb.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", nargs="+", required=True, help="Scanner XLSX outputs")
    ap.add_argument("--output", required=True, help="Resultado XLSX")
    ap.add_argument("--grading-fee", type=float, default=50.0,
                    help="Custo de grading em USD (default 50)")
    ap.add_argument("--rate-limit", type=float, default=1.5,
                    help="Segundos entre requests PriceCharting (default 1.5)")
    args = ap.parse_args()

    paths = [Path(p) for p in args.input]
    out = Path(args.output)

    cards = load_scan_rows(paths)
    print(f"Loaded {len(cards)} unique cards from {len(paths)} input file(s)")

    if not cards:
        print("Nothing to analyze.")
        return

    rows = build_analysis(cards, args.grading_fee, args.rate_limit)
    write_xlsx(rows, out, args.grading_fee)
    print(f"Wrote {out}")

    # Console summary
    worth = [r for r in rows if r["psa9_worth_grading"]]
    print(f"\n=== {len(worth)}/{len(rows)} cards onde PSA 9 > Raw NM + ${args.grading_fee:.0f} ===\n")
    for r in sorted(worth, key=lambda x: x.get("psa9_profit_usd") or 0, reverse=True):
        psa9_str = f"${r['psa9_usd']:.2f}" if r['psa9_usd'] else "-"
        psa10_str = f"${r['psa10_usd']:.2f}" if r['psa10_usd'] else "-"
        raw = f"${r['raw_nm_usd']:.2f}" if r['raw_nm_usd'] else "-"
        prof9 = f"+${r['psa9_profit_usd']:.2f}" if r['psa9_profit_usd'] else "-"
        prof10 = f"+${r['psa10_profit_usd']:.2f}" if r['psa10_profit_usd'] else "-"
        print(f"  {r['card_name']:30} {r['set_name']:25} raw={raw}  PSA9={psa9_str} ({prof9})  PSA10={psa10_str} ({prof10})")


if __name__ == "__main__":
    main()
