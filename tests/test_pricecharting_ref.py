"""Referência PriceCharting (mediana de sold listings) — metodologia 2026-08-28.

Cobre `pricecharting_ref.py` (módulo novo) e a integração `--pc-refs` no
postprocess:
  - parse_sold_listings: extrai SÓ as vendas ungraded (data, fonte, preço),
    ignorando as abas graded
  - median_recent_sold: mediana das N vendas mais recentes (anti-outlier),
    vazio → (None, 0) — nunca inventa preço
  - normalização de número CT ("004" → "4", "95b/147" → "95")
  - guarda de slug: URL de busca que não casa nome+número → None (honesto)
  - build_delivery_markdown com colunas "Ref PC US$" / "Margem PC %" + link
    [PC] na célula Links; sem dados PC a saída é IDÊNTICA à atual (regressão)
  - attach_pc_refs: resolver injetável, só nas linhas da entrega, cap N

Tudo offline (fixture `tests/fixtures/pc_sold_listings.html`); rede nunca.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd

import pricecharting_ref as pcr
import cardtrader_postprocess as pp

FIXTURE = Path(__file__).parent / "fixtures" / "pc_sold_listings.html"


def _fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


# ─── parse_sold_listings ─────────────────────────────────────────────────────

def test_parse_extracts_only_ungraded_rows():
    sales = pcr.parse_sold_listings(_fixture_html())
    assert len(sales) == 5  # 3 tcgplayer + 2 ebay; a linha graded ($999.99) fica fora
    assert all(s["price"] != 999.99 for s in sales)


def test_parse_fields_and_sources():
    sales = pcr.parse_sold_listings(_fixture_html())
    by_date = {s["date"]: s for s in sales}
    assert by_date["2026-04-07"]["price"] == 51.76
    assert by_date["2026-04-07"]["source"] == "tcgplayer"
    assert by_date["2026-02-12"]["price"] == 150.26
    assert by_date["2026-02-12"]["source"] == "ebay"


def test_parse_no_ungraded_div_returns_empty():
    assert pcr.parse_sold_listings("<html><body>nada</body></html>") == []


# ─── median_recent_sold ──────────────────────────────────────────────────────

def _sales(prices_by_date):
    return [{"date": d, "price": p, "source": "tcgplayer"}
            for d, p in prices_by_date]


def test_median_odd_count():
    med, n = pcr.median_recent_sold(pcr.parse_sold_listings(_fixture_html()))
    # 5 vendas: 40.00, 42.00, 51.76, 51.78, 150.26 → mediana 51.76
    assert med == 51.76
    assert n == 5


def test_median_even_count():
    sales = _sales([("2026-01-01", 10.0), ("2026-01-02", 20.0),
                    ("2026-01-03", 30.0), ("2026-01-04", 40.0)])
    med, n = pcr.median_recent_sold(sales)
    assert med == 25.0
    assert n == 4


def test_median_caps_at_n_most_recent():
    sales = _sales([("2026-01-01", 1000.0),  # antiga: deve ficar FORA com n=3
                    ("2026-02-01", 10.0), ("2026-03-01", 20.0),
                    ("2026-04-01", 30.0)])
    med, n = pcr.median_recent_sold(sales, n=3)
    assert med == 20.0
    assert n == 3


def test_median_empty_returns_none():
    med, n = pcr.median_recent_sold([])
    assert med is None
    assert n == 0


# ─── normalização de número / guarda de slug ─────────────────────────────────

def test_norm_number_strips_zeros_and_total():
    assert pcr.norm_number("004") == "4"
    assert pcr.norm_number("95b/147") == "95"
    assert pcr.norm_number("012/107") == "12"
    assert pcr.norm_number(None) == ""


def test_slug_guard_accepts_matching_card():
    assert pcr.slug_matches("/game/pokemon-emerald/gardevoir-4", "Gardevoir", "004")
    assert pcr.slug_matches("/game/pokemon-aquapolis/mr-mime-95", "Mr. Mime", "95b/147")


def test_slug_guard_rejects_wrong_number_or_name():
    assert not pcr.slug_matches("/game/pokemon-emerald/kirlia-35", "Gardevoir", "004")
    assert not pcr.slug_matches("/game/pokemon-emerald/gardevoir-9", "Gardevoir", "004")


def test_slug_guard_rejects_different_card_same_number():
    """Review 2026-08-28: 'charizard-6' NÃO é 'Charizard ex' (falta o ex) e
    'dark-charizard-4' NÃO é 'Charizard' (prefixo de OUTRA carta)."""
    assert not pcr.slug_matches("/game/pokemon-base-set/charizard-6",
                                "Charizard ex", "6")
    assert not pcr.slug_matches("/game/pokemon-team-rocket/dark-charizard-4",
                                "Charizard", "4")
    # tokens do nome podem morar no CONSOLE (Starmie δ Delta Species)
    assert pcr.slug_matches("/game/pokemon-delta-species/starmie-30",
                            "Starmie δ Delta Species", "030")


def test_slug_guard_possessive_and_single_letter_names():
    """Review 2026-08-28: Gym era ("Erika's ...") e o Trainer 'N' (1 letra)
    ficavam permanentemente sem cobertura PC."""
    assert pcr.slug_matches("/game/pokemon-gym-challenge/erika's-venusaur-4",
                            "Erika's Venusaur", "4")
    assert pcr.slug_matches("/game/pokemon-noble-victories/n-92", "N", "92/101")


def test_console_guard_rejects_japanese_and_extra_tokens():
    """Review 2026-08-28: 'pokemon-japanese-aquapolis' NÃO casa 'Aquapolis' —
    a mediana da tiragem japonesa (mais barata) corromperia o sinal."""
    assert not pcr.console_matches("/game/pokemon-japanese-aquapolis/mr-mime-95",
                                   "Aquapolis (aq)")
    assert pcr.console_matches("/game/pokemon-aquapolis/mr-mime-95",
                               "Aquapolis (aq)")


def test_resolve_returns_none_on_slug_mismatch(monkeypatch):
    search_html = '<a href="/game/pokemon-emerald/kirlia-35">Kirlia #35</a>'
    monkeypatch.setattr(pcr, "fetch_page", lambda url, cache_dir=None: search_html)
    assert pcr.resolve_pc_ref("Gardevoir", "004", "EX Emerald (em)") is None


def test_resolve_picks_matching_result_not_first(monkeypatch):
    """Busca real devolve hrefs ABSOLUTOS e a carta certa pode vir longe da 1ª
    posição (Gardevoir Emerald: 41ª, 2026-08-28) — escolhe pelo slug, não pela
    ordem."""
    search_html = (
        '<a href="https://www.pricecharting.com/game/pokemon-emerald/kirlia-35">Kirlia</a>'
        '<a href="https://www.pricecharting.com/game/pokemon-emerald/gardevoir-4">Gardevoir #4</a>'
    )
    product_html = _fixture_html()

    def fake_fetch(url, cache_dir=None):
        return search_html if "search-products" in url else product_html

    monkeypatch.setattr(pcr, "fetch_page", fake_fetch)
    ref = pcr.resolve_pc_ref("Gardevoir", "004", "EX Emerald (em)")
    assert ref is not None
    assert ref["url"].endswith("/game/pokemon-emerald/gardevoir-4")


def test_console_guard_accepts_set_variants():
    assert pcr.console_matches("/game/pokemon-emerald/gardevoir-4", "EX Emerald (em)")
    assert pcr.console_matches("/game/pokemon-hidden-legends/relicanth-24",
                               "EX Hidden Legends (hl)")
    assert pcr.console_matches("/game/pokemon-aquapolis/jynx-18", "Aquapolis (aq)")


def test_console_guard_rejects_cross_set():
    """Casos reais do smoke 2026-08-28: nome+número batiam em OUTRO set."""
    assert not pcr.console_matches("/game/pokemon-plasma-blast/relicanth-24",
                                   "EX Hidden Legends (hl)")
    assert not pcr.console_matches("/game/pokemon-burning-shadows/porygon-103",
                                   "Aquapolis (aq)")
    assert not pcr.console_matches(
        "/game/pokemon-japanese-gx-battle-boost/fire-memory-102", "EX Emerald (em)")


def test_resolve_rejects_cross_set_result(monkeypatch):
    search_html = '<a href="/game/pokemon-plasma-blast/relicanth-24">Relicanth</a>'
    monkeypatch.setattr(pcr, "fetch_page", lambda url, cache_dir=None: search_html)
    assert pcr.resolve_pc_ref("Relicanth", "024/101", "EX Hidden Legends (hl)") is None


def test_resolve_prefers_base_variant_slug(monkeypatch):
    """'mr-mime-95' (base) vence 'mr-mime-reverse-holo-95' — a página base é a
    referência menos arriscada (caso real Aquapolis 95b, 2026-08-28)."""
    search_html = (
        '<a href="/game/pokemon-aquapolis/mr-mime-reverse-holo-95">RH</a>'
        '<a href="/game/pokemon-aquapolis/mr-mime-95">base</a>'
    )

    def fake_fetch(url, cache_dir=None):
        return search_html if "search-products" in url else _fixture_html()

    monkeypatch.setattr(pcr, "fetch_page", fake_fetch)
    ref = pcr.resolve_pc_ref("Mr. Mime", "95b/147", "Aquapolis (aq)")
    assert ref["url"].endswith("/game/pokemon-aquapolis/mr-mime-95")


def test_resolve_happy_path(monkeypatch):
    search_html = '<a href="/game/pokemon-emerald/gardevoir-4">Gardevoir #4</a>'
    product_html = _fixture_html()

    def fake_fetch(url, cache_dir=None):
        return search_html if "search-products" in url else product_html

    monkeypatch.setattr(pcr, "fetch_page", fake_fetch)
    ref = pcr.resolve_pc_ref("Gardevoir", "004", "EX Emerald (em)")
    assert ref is not None
    assert ref["median"] == 51.76
    assert ref["n_sales"] == 5
    assert ref["url"].startswith("https://www.pricecharting.com/game/")


def test_resolve_no_sales_returns_none(monkeypatch):
    search_html = '<a href="/game/pokemon-emerald/gardevoir-4">Gardevoir #4</a>'

    def fake_fetch(url, cache_dir=None):
        return search_html if "search-products" in url else "<html></html>"

    monkeypatch.setattr(pcr, "fetch_page", fake_fetch)
    assert pcr.resolve_pc_ref("Gardevoir", "004", "EX Emerald (em)") is None


# ─── integração postprocess ──────────────────────────────────────────────────

def _raw_df():
    """Mesmo shape do raw do scanner (espelho de test_delivery_markdown)."""
    return pd.DataFrame({
        "Card Name": ["Plusle", "Charizard ex"],
        "Nº": [193, 199],
        "Set": ["Paradox Rift (par)", "Obsidian Flames (obf)"],
        "Rarity": ["Double Rare", "Special Illustration Rare"],
        "Condição": ["NM", "NM"],
        "Qtd": [3, 1],
        "LIVE R$ (real)": [120.0, 600.0],
        "TCG Market (BRL)": [240.0, 1000.0],
        "TCG Market (USD)": [44.00, 183.50],
        "Net Margin % REAL": [0.50, 0.40],
        "Lucro R$ REAL": [120.0, 400.0],
        "Validation Status": ["VALIDATED_REAL", "VALIDATED_REAL"],
        "Link CardTrader": ["https://www.cardtrader.com/cards/111",
                            "https://www.cardtrader.com/cards/222"],
        "Link TCG": ["https://prices.pokemontcg.io/tcgplayer/sv4-193",
                     "https://prices.pokemontcg.io/tcgplayer/sv3-199"],
    })


def _enriched(cfg=None):
    cfg = cfg or pp.DecisionConfig()
    return pp.enrich_df(_raw_df(), hub_fee_rate=cfg.hub_fee_rate), cfg


def test_delivery_without_pc_is_unchanged():
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0)
    assert "Ref PC US$" not in md
    assert "Margem PC %" not in md
    assert "[PC]" not in md


def test_attach_pc_refs_uses_injected_resolver_and_caps():
    df, cfg = _enriched()
    calls = []

    def fake_resolver(name, number, set_label, cache_dir=None):
        calls.append(name)
        return {"median": 30.0, "n_sales": 7,
                "url": "https://www.pricecharting.com/game/x/y-1"}

    n, attempted = pp.attach_pc_refs(df, cfg, top_md=50, limit=1,
                                     resolver=fake_resolver)
    assert n == 1
    assert attempted == 1  # denominador honesto: tentadas, não o valor da flag
    assert len(calls) == 1
    assert calls[0] == "Plusle"  # maior margem primeiro
    assert df["pc_median_usd"].notna().sum() == 1


def test_delivery_with_pc_columns_and_link():
    df, cfg = _enriched()

    def fake_resolver(name, number, set_label, cache_dir=None):
        if name == "Plusle":
            return {"median": 30.0, "n_sales": 7,
                    "url": "https://www.pricecharting.com/game/pokemon-paradox-rift/plusle-193"}
        return None  # Charizard: PC não resolveu → célula honesta "—"

    pp.attach_pc_refs(df, cfg, top_md=50, limit=50, resolver=fake_resolver)
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0)
    assert "Ref PC US$" in md and "Margem PC %" in md
    # Plusle: CT US$ 24.00, PC 30.00 → margem PC = (30−24)/30 = 20%
    assert "30.00" in md
    assert "20%" in md
    assert "[PC](https://www.pricecharting.com/game/pokemon-paradox-rift/plusle-193)" in md
    # Charizard sem PC → "—" na coluna e SEM link [PC] na linha dele
    charizard_line = next(l for l in md.splitlines() if "Charizard" in l)
    assert "—" in charizard_line
    assert "[PC]" not in charizard_line
    # contrato de 2 links intacto em toda linha
    for line in md.splitlines():
        if line.startswith("| ") and "oferta" in line:
            assert "[TCG]" in line


def test_delivery_pc_divergence_flag():
    """TCG US$ ≫ mediana PC (>30% acima) → flag 'PC diverge' na linha."""
    df, cfg = _enriched()

    def fake_resolver(name, number, set_label, cache_dir=None):
        # Plusle: TCG 44.00 vs PC 20.00 → 120% acima → diverge
        return ({"median": 20.0, "n_sales": 5,
                 "url": "https://www.pricecharting.com/game/x/plusle-193"}
                if name == "Plusle" else None)

    pp.attach_pc_refs(df, cfg, top_md=50, limit=50, resolver=fake_resolver)
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0)
    plusle_line = next(l for l in md.splitlines() if "Plusle" in l)
    assert "PC diverge" in plusle_line


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
