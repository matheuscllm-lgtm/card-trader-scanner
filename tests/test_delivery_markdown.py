"""Tabela de ENTREGA no chat (markdown, links clicáveis) — formato 2026-06-09.

Cobre `build_delivery_markdown`:
  - cabeçalho exato (# | Margem % | CT US$ | TCG US$ | Dif | Carta | Set |
    Raridade | Cond | Qtd | Links)
  - Carta = nome + número combinados ("Plusle (193/...)")
  - Links = "[oferta](url_ct) · [TCG](url_tcg)" clicáveis
  - CT US$ convertido de BRL via FX quando não há live_usd
  - TCG US$ nativo (reference_price_usd)
  - filtra só COMPRA/REVISAR (mesma classify_decision do XLSX)
  - pipe no texto vira '/' (não quebra a tabela)
  - vazio → mensagem amigável, não crash

Roda via pytest E standalone (python tests/test_delivery_markdown.py).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import cardtrader_postprocess as pp


def _raw_df():
    """Linhas no formato cru do scanner (nomes de coluna do XLSX Oportunidades)."""
    return pd.DataFrame({
        "Card Name": ["Plusle", "Charizard ex", "Bulk Common"],
        "Nº": [193, 199, 4],
        "Set": ["Paradox Rift (par)", "Obsidian Flames (obf)", "Some Set (xyz)"],
        "Rarity": ["Double Rare", "Special Illustration Rare", "Common"],
        "Condição": ["NM", "NM", "NM"],
        "Qtd": [3, 1, 12],
        "LIVE R$ (real)": [120.0, 600.0, 5.0],
        "TCG Market (BRL)": [240.0, 1000.0, 6.0],
        "TCG Market (USD)": [44.00, 183.50, 1.10],
        "Net Margin % REAL": [0.50, 0.40, 0.05],
        "Lucro R$ REAL": [120.0, 400.0, 1.0],
        "Validation Status": ["VALIDATED_REAL", "VALIDATED_REAL", "STALE"],
        "Link CardTrader": [
            "https://www.cardtrader.com/cards/111",
            "https://www.cardtrader.com/cards/222",
            "https://www.cardtrader.com/cards/333",
        ],
        "Link TCG": [
            "https://prices.pokemontcg.io/tcgplayer/sv4-193",
            "https://prices.pokemontcg.io/tcgplayer/sv3-199",
            "",
        ],
    })


def _enriched(cfg=None):
    cfg = cfg or pp.DecisionConfig()
    return pp.enrich_df(_raw_df(), hub_fee_rate=cfg.hub_fee_rate), cfg


def test_header_exact():
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0)
    expected = ("| # | Margem % | CT US$ | TCG US$ | Dif | Carta | Set | "
                "Raridade | Cond | Qtd | Links |")
    assert expected in md


def test_filters_to_buy_review_only():
    """Bulk Common (STALE, net 5%) deve cair fora — só COMPRA/REVISAR entram."""
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0)
    assert "Plusle" in md
    assert "Charizard ex" in md
    assert "Bulk Common" not in md


def test_carta_combines_name_and_number():
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0)
    # par está no CT_SET_TOTAL (182) → "Plusle (193/182)"
    assert "Plusle (193/182)" in md


def test_links_cell_clickable_both():
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0)
    assert "[oferta](https://www.cardtrader.com/cards/111)" in md
    assert "[TCG](https://prices.pokemontcg.io/tcgplayer/sv4-193)" in md
    assert " · " in md  # separador entre os dois links


def test_ct_usd_converted_from_brl_via_fx():
    """CT US$ = live_brl / fx. 120 / 5.0 = 24.00."""
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0)
    assert "24.00" in md   # CT US$ do Plusle
    assert "44.00" in md   # TCG US$ nativo do Plusle


def test_dif_is_tcg_minus_ct():
    """Dif = TCG US$ − CT US$ = 44.00 − 24.00 = 20.00 (Plusle)."""
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0)
    assert "20.00" in md


def test_no_fx_leaves_ct_usd_blank_not_crash():
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=None)
    # ainda renderiza TCG US$ nativo, mas CT US$ vazio (não inventa câmbio)
    assert "44.00" in md
    assert "Plusle" in md


def test_margem_formatted_as_percent():
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0)
    assert "50%" in md  # net_margin 0.50 → "50%"


def test_pipe_in_text_does_not_break_table():
    raw = _raw_df()
    raw.loc[0, "Card Name"] = "Pipe|Name"
    df = pp.enrich_df(raw, hub_fee_rate=0.0)
    md = pp.build_delivery_markdown(df, pp.DecisionConfig(), fx_usd_brl=5.0)
    # pipe escapado vira '/', cabeçalho continua com 11 colunas
    data_rows = [ln for ln in md.splitlines() if ln.startswith("| 1 |")]
    assert data_rows
    assert data_rows[0].count("|") == 12  # 11 colunas → 12 pipes


def test_empty_deals_friendly_message():
    raw = _raw_df()
    raw["Net Margin % REAL"] = [0.01, 0.02, 0.01]  # nada passa
    raw["Validation Status"] = ["STALE", "STALE", "STALE"]
    df = pp.enrich_df(raw, hub_fee_rate=0.0)
    md = pp.build_delivery_markdown(df, pp.DecisionConfig(), fx_usd_brl=5.0)
    assert "nenhum deal" in md.lower()


def test_top_n_caps_rows():
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0, top_n=1)
    data_rows = [ln for ln in md.splitlines()
                 if ln.startswith("| ") and not ln.startswith("| # |")
                 and not ln.startswith("| --- ")]
    assert len(data_rows) == 1


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"PASS {fn.__name__}")
        except Exception:
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
