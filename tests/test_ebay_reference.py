"""v2.29 — referência eBay (vendas concluídas) como fonte PRINCIPAL da razão.

Pedido do operador (2026-10-03): no screen "carta em outro idioma ≥ 4× mais
barata que a inglesa", a referência da carta INGLESA deve vir do eBay. Fonte:
vendas concluídas `[eBay]` da página pública da carta no PriceCharting (a mesma
que o ebay-arbitrage-scanner usa em `src/pc_sales.py`) — a Browse API oficial
só mostra anúncios ATIVOS, não vendas.

Contratos:
  - só linhas `ebay-*` da tabela ungraded (TCGPlayer fora);
  - título em outro idioma (japanese/chinese/korean...), gradeado (PSA 10...)
    ou lote/pack → fora (a referência é a carta inglesa raw);
  - ≥3 vendas em 365 dias, mediana das 10 mais recentes; senão None (nunca
    inventa);
  - postprocess `--ref-source ebay`: razão = Ref eBay ÷ CT US$; sem ref eBay →
    razão via TCG ROTULADA "fallback TCG"; links carregam [eBay] além dos 2
    obrigatórios.
"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cardtrader_postprocess as pp  # noqa: E402
import pricecharting_ref as pcr  # noqa: E402


def _row(source, sid, date, price, title):
    return (f'<tr id="{source}-{sid}"><td class="date">{date}</td>'
            f'<td class="title"><a>{title}</a> [{ "eBay" if source == "ebay" else "TCGPlayer"}]</td>'
            f'<td class="numeric"><span class="js-price">${price:.2f}</span></td></tr>')


def _page(rows):
    return ('<div class="completed-auctions-used"><table><tbody>'
            + "".join(rows) + "</tbody></table></div>"
            '<div class="completed-auctions-graded"><table><tbody>'
            + _row("ebay", 999, "2026-09-30", 500.0, "Chansey 113/165 PSA 10")
            + "</tbody></table></div>")


TODAY = dt.date(2026, 10, 3)


def test_parse_ebay_sales_keeps_only_ebay_rows_with_title():
    body = _page([
        _row("ebay", 1, "2026-09-20", 1.00, "Pokemon 151 Chansey 113/165 Holo NM"),
        _row("tcgplayer", 2, "2026-09-21", 9.99, "Chansey"),
    ])
    sales = pcr.parse_ebay_sales(body)
    assert [s["price"] for s in sales] == [1.00]
    assert "Chansey" in sales[0]["title"]
    assert sales[0]["source"] == "ebay"


def test_ebay_comparable_drops_foreign_language_graded_and_lots():
    sales = [
        {"date": "2026-09-20", "price": 1.0, "title": "Chansey 113/165 Holo NM", "source": "ebay"},
        {"date": "2026-09-20", "price": 0.2, "title": "Chansey 113/165 Japanese", "source": "ebay"},
        {"date": "2026-09-20", "price": 0.3, "title": "Chansey 113 Chinese 151", "source": "ebay"},
        {"date": "2026-09-20", "price": 40.0, "title": "Chansey 113/165 PSA 10", "source": "ebay"},
        {"date": "2026-09-20", "price": 5.0, "title": "Lot of 10 Chansey 113/165", "source": "ebay"},
    ]
    kept = pcr.ebay_comparable(sales)
    assert [s["price"] for s in kept] == [1.0]


def test_ebay_reference_requires_three_recent_sales_and_uses_median():
    sales = [
        {"date": "2026-09-01", "price": 1.0, "title": "a", "source": "ebay"},
        {"date": "2026-09-10", "price": 2.0, "title": "b", "source": "ebay"},
        {"date": "2026-09-20", "price": 9.0, "title": "c", "source": "ebay"},
        {"date": "2024-01-01", "price": 99.0, "title": "old", "source": "ebay"},  # > 365 d
    ]
    ref = pcr.ebay_median_reference(sales, today=TODAY)
    assert ref["median"] == 2.0 and ref["n_sales"] == 3
    assert ref["oldest"] == "2026-09-01" and ref["newest"] == "2026-09-20"
    assert pcr.ebay_median_reference(sales[:2], today=TODAY) is None   # só 2 → None


# ───────────────────────── postprocess ─────────────────────────
def _raw_df():
    return pd.DataFrame({
        "Card Name": ["Pikachu", "Mew ex"],
        "Nº": [25, 151],
        "Set": ["151 (mew)", "151 (mew)"],
        "Rarity": ["Double Rare", "Double Rare"],
        "Condição": ["NM", "NM"],
        "Idioma": ["ZH-CN", "ZH-CN"],
        "Qtd": [1, 1],
        "LIVE R$ (real)": [10.0, 200.0],          # CT US$ 2.00 / 40.00 (fx 5)
        "TCG Market (BRL)": [15.0, 500.0],
        "TCG Market (USD)": [3.00, 100.00],        # TCG razão 1.5× / 2.5×
        "Net Margin % REAL": [0.33, 0.60],
        "Lucro R$ REAL": [5.0, 300.0],
        "Validation Status": ["VALIDATED_REAL", "VALIDATED_REAL"],
        "Link CardTrader": ["https://www.cardtrader.com/cards/1",
                            "https://www.cardtrader.com/cards/3"],
        "Link TCG": ["https://www.tcgplayer.com/product/1",
                     "https://www.tcgplayer.com/product/3"],
    })


def _fake_resolver(card_name, number, set_label, cache_dir=None, variant=None):
    if "Pikachu" in str(card_name):
        return {"median": 10.0, "n_sales": 7, "url": "https://www.pricecharting.com/game/pokemon-151/pikachu-25",
                "oldest": "2026-08-01", "newest": "2026-09-30"}
    return None   # Mew ex: sem venda eBay comparável


def _enriched_with_ebay():
    cfg = pp.DecisionConfig(min_net_margin=0.25, revisar_min_net=0.20, min_lucro_liq=0.0)
    df = pp.enrich_df(_raw_df(), hub_fee_rate=0.0)
    resolved, attempted = pp.attach_ebay_refs(df, resolver=_fake_resolver)
    assert (resolved, attempted) == (1, 2)
    return df, cfg


def test_ref_source_ebay_ratio_uses_ebay_median_and_labels_columns():
    df, cfg = _enriched_with_ebay()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0, show_ratio=True, ref_source="ebay")
    assert "Razão eBay-EN/ZH-CN" in md
    assert "Ref eBay US$" in md
    pik = [l for l in md.splitlines() if l.startswith("| ") and "Pikachu" in l][0]
    assert "| 5.0× |" in pik                                    # 10.00 / 2.00
    assert "[10.00](https://www.pricecharting.com/game/pokemon-151/pikachu-25)" in pik
    assert "[oferta](https://www.cardtrader.com/cards/1)" in pik
    assert "[TCG](https://www.tcgplayer.com/product/1)" in pik
    assert "[eBay](https://www.pricecharting.com/game/pokemon-151/pikachu-25)" in pik


def test_ref_source_ebay_without_sale_falls_back_to_tcg_labeled():
    df, cfg = _enriched_with_ebay()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0, show_ratio=True, ref_source="ebay")
    mew = [l for l in md.splitlines() if l.startswith("| ") and "Mew ex" in l][0]
    assert "| 2.5× |" in mew                                    # 100 / 40 via TCG
    assert "fallback TCG" in mew


def test_ref_source_ebay_min_ratio_cut_uses_ebay_ratio():
    df, cfg = _enriched_with_ebay()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0, show_ratio=True,
                                    min_ratio=4.0, ref_source="ebay")
    assert "Pikachu" in md          # 5.0× pelo eBay (só 1.5× pelo TCG)
    assert "Mew ex" not in md       # 2.5× (fallback TCG) < 4


def test_postprocess_cli_ref_source_flag():
    from unittest.mock import patch
    with patch.object(sys, "argv", ["cardtrader_postprocess.py", "-i", "a.xlsx", "-o", "b.xlsx",
                                    "--min-ratio", "4", "--ref-source", "ebay"]):
        with patch.object(pp, "write_report") as wr, \
             patch.object(pp.pd, "read_excel", return_value=_raw_df()), \
             patch.object(pp, "_read_fx_usd_brl", return_value=5.0):
            pp.main()
    assert wr.call_args.kwargs.get("ref_source") == "ebay"


# ── Rodada 2 (2026-10-03): PriceCharting 403 neste IP → honestidade + Firecrawl ──
def test_search_paths_accept_entities_and_single_quotes(monkeypatch):
    html_body = ("<a href='https://www.pricecharting.com/game/pokemon-scarlet-&amp;-violet-151/chansey-113'>x</a>"
                 '<a href="/game/pokemon-japanese-scarlet-&amp;-violet-151/chansey-113">y</a>')
    monkeypatch.setattr(pcr, "fetch_page", lambda url, cache_dir=None: html_body)
    paths = pcr.search_card_urls("pokemon 151 chansey 113")
    assert "/game/pokemon-scarlet-&-violet-151/chansey-113" in paths
    assert "/game/pokemon-japanese-scarlet-&-violet-151/chansey-113" in paths


def test_resolve_ebay_ref_reports_source_error_not_none(monkeypatch):
    def boom(url, cache_dir=None):
        raise RuntimeError("HTTP Error 403: Forbidden")
    monkeypatch.setattr(pcr, "fetch_page", boom)
    ref = pcr.resolve_ebay_ref("Chansey", "113", "151 (mew)")
    assert ref is not None and "403" in ref.get("error", "")
    assert ref.get("median") is None


def test_attach_and_delivery_distinguish_source_error_from_no_sale():
    cfg = pp.DecisionConfig(min_net_margin=0.25, revisar_min_net=0.20, min_lucro_liq=0.0)
    df = pp.enrich_df(_raw_df(), hub_fee_rate=0.0)

    def resolver(card_name, *a, **k):
        return {"error": "HTTP Error 403: Forbidden"} if "Pikachu" in str(card_name) else None
    resolved, attempted, errors = pp.attach_ebay_refs(df, resolver=resolver, return_errors=True)
    assert (resolved, attempted, errors) == (0, 2, 1)
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0, show_ratio=True, ref_source="ebay")
    pik = [l for l in md.splitlines() if l.startswith("| ") and "Pikachu" in l][0]
    mew = [l for l in md.splitlines() if l.startswith("| ") and "Mew ex" in l][0]
    assert "eBay indisponível" in pik and "403" in pik
    assert "sem venda eBay" in mew


def test_fetch_page_uses_firecrawl_on_403_within_budget(monkeypatch, tmp_path):
    import urllib.error
    def urlopen_403(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
    calls = []
    monkeypatch.setattr(pcr.urllib.request, "urlopen", urlopen_403)
    monkeypatch.setattr(pcr, "_firecrawl_scrape", lambda url: calls.append(url) or "<html>ok</html>")
    monkeypatch.setattr(pcr, "REQUEST_GAP_SECONDS", 0)
    pcr.set_firecrawl_budget(1)
    assert pcr.fetch_page("https://www.pricecharting.com/game/x/y-1", cache_dir=str(tmp_path)) == "<html>ok</html>"
    assert calls == ["https://www.pricecharting.com/game/x/y-1"]
    # orçamento esgotado → erro alto (nunca silencioso)
    try:
        pcr.fetch_page("https://www.pricecharting.com/game/x/z-2", cache_dir=str(tmp_path))
        raise AssertionError("deveria falhar com orçamento 0")
    except Exception as e:  # noqa: BLE001
        assert "403" in str(e) or "orçamento" in str(e).lower()
    pcr.set_firecrawl_budget(0)


def test_fetch_page_never_uses_firecrawl_by_default(monkeypatch, tmp_path):
    import urllib.error
    monkeypatch.setattr(pcr.urllib.request, "urlopen",
                        lambda req, timeout=30: (_ for _ in ()).throw(
                            urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)))
    monkeypatch.setattr(pcr, "_firecrawl_scrape", lambda url: (_ for _ in ()).throw(AssertionError("pago sem opt-in")))
    monkeypatch.setattr(pcr, "REQUEST_GAP_SECONDS", 0)
    pcr.set_firecrawl_budget(0)
    try:
        pcr.fetch_page("https://www.pricecharting.com/game/x/w-3", cache_dir=str(tmp_path))
        raise AssertionError("deveria propagar o 403")
    except urllib.error.HTTPError as e:
        assert e.code == 403


# ── Rodada 3: console do PC com prefixo de era ("Scarlet & Violet 151" vs CT "151") ──
def test_console_matches_accepts_era_prefix_but_not_language_variants():
    assert pcr.console_matches("/game/pokemon-scarlet-&-violet-151/chansey-113", "151 (mew)")
    assert not pcr.console_matches("/game/pokemon-japanese-scarlet-&-violet-151/chansey-113", "151 (mew)")
    assert not pcr.console_matches("/game/pokemon-chinese-151-collect/chansey-113", "151 (mew)")
    # base set SV continua exato; prefixo não vira coringa pra outro set
    assert pcr.console_matches("/game/pokemon-scarlet-&-violet/pikachu-1", "Scarlet & Violet (svi)")
    assert not pcr.console_matches("/game/pokemon-scarlet-&-violet-151/pikachu-25", "Scarlet & Violet (svi)")
    assert not pcr.console_matches("/game/pokemon-scarlet-&-violet-151/pikachu-25", "Paldea Evolved (pal)")


def test_resolve_ebay_ref_reports_miss_reason(monkeypatch):
    monkeypatch.setattr(pcr, "_resolve_pc_path", lambda *a, **k: None)
    assert pcr.resolve_ebay_ref("X", "1", "151 (mew)") == {"miss": "sem página PriceCharting casada"}
    monkeypatch.setattr(pcr, "_resolve_pc_path", lambda *a, **k: "/game/pokemon-scarlet-&-violet-151/x-1")
    monkeypatch.setattr(pcr, "fetch_page", lambda url, cache_dir=None: "<html></html>")
    assert pcr.resolve_ebay_ref("X", "1", "151 (mew)")["miss"].startswith("<3 vendas eBay")


def test_delivery_labels_miss_reason():
    cfg = pp.DecisionConfig(min_net_margin=0.25, revisar_min_net=0.20, min_lucro_liq=0.0)
    df = pp.enrich_df(_raw_df(), hub_fee_rate=0.0)
    pp.attach_ebay_refs(df, resolver=lambda *a, **k: {"miss": "sem página PriceCharting casada"})
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0, show_ratio=True, ref_source="ebay")
    assert "fallback TCG (sem página PriceCharting casada)" in md


def test_firecrawl_retries_once_then_labels_error(monkeypatch, tmp_path):
    import urllib.error
    monkeypatch.setattr(pcr.urllib.request, "urlopen",
                        lambda req, timeout=30: (_ for _ in ()).throw(
                            urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)))
    attempts = []

    def flaky(url):
        attempts.append(url)
        if len(attempts) == 1:
            raise RuntimeError("HTTP Error 403 (firecrawl)")
        return "<html>ok</html>"
    monkeypatch.setattr(pcr, "_firecrawl_scrape", flaky)
    monkeypatch.setattr(pcr, "REQUEST_GAP_SECONDS", 0)
    monkeypatch.setattr(pcr, "FIRECRAWL_RETRY_WAIT_S", 0)
    pcr.set_firecrawl_budget(5)
    assert pcr.fetch_page("https://www.pricecharting.com/game/x/r-9", cache_dir=str(tmp_path)) == "<html>ok</html>"
    assert len(attempts) == 2 and pcr.firecrawl_used() == 2
    pcr.set_firecrawl_budget(0)
