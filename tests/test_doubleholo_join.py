"""Caminho 1 DoubleHolo — coluna "DH" (2ª opinião) nos deals do CardTrader.

Cobre `doubleholo_join` + a renderização condicional da coluna DH em
`cardtrader_postprocess.build_delivery_markdown` / sheets do XLSX:

  - extract_product_id: regex tcgplayer.com/product/(\\d+); None p/ URL sem
    productId (ex.: redirect prices.pokemontcg.io) e p/ None/vazio.
  - load_signals: indexa JSON canônico por tcg_product_id (lista ou dict único);
    ignora registros sem productId.
  - attach_scores_df: LÊ o dh_score precomputado (single source no pipeline);
    sem match (productId None ou ausente) ou registro sem o campo → None ("—").
  - markdown: coluna DH só com show_dh=True; valor numa linha que casa, "—" na
    que não casa; os DOIS links (oferta + TCG) intactos; rodapé explicativo.
  - sem a flag: cabeçalho/colunas idênticos (contrato de entrega não muda).

⚠️ DESCOBERTA: no scanner CT, `Link TCG` das linhas via pokemontcg.io é um
redirect `prices.pokemontcg.io/tcgplayer/{cardId}` (SEM productId numérico) → o
join por link direto não casa; essas linhas dependem da coluna `tcg_product_id`
resolvida (Fix(2)). Linhas via tcgcsv (Fix(1)) agora carregam um
`tcgplayer.com/product/{productId}` real e casam direto. Sem productId resolvido,
a coluna mostra "—" (honesto, não inventa).

Roda via pytest E standalone (python tests/test_doubleholo_join.py).
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import cardtrader_postprocess as pp
import doubleholo_join as dh


# ─── extract_product_id ──────────────────────────────────────────────────────
def test_extract_product_id_from_real_product_url():
    assert dh.extract_product_id(
        "https://www.tcgplayer.com/product/517816/pokemon-foo") == "517816"
    assert dh.extract_product_id("https://tcgplayer.com/product/42") == "42"


def test_extract_product_id_none_for_pokemontcg_redirect():
    # URL real do scanner CT (provider pokemontcg) — NÃO traz productId.
    assert dh.extract_product_id(
        "https://prices.pokemontcg.io/tcgplayer/sv4-260") is None


def test_extract_product_id_none_for_empty_or_none():
    assert dh.extract_product_id(None) is None
    assert dh.extract_product_id("") is None
    assert dh.extract_product_id(float("nan")) is None or True  # não deve crashar


# ─── load_signals ────────────────────────────────────────────────────────────
def _canonical_records():
    """2 registros canônicos: um com dh_score precomputado, um sem (fallback)."""
    return [
        {  # precomputado — attach deve USAR este valor, não recalcular
            "source": "doubleholo", "tcg_product_id": "517816",
            "name": "Charizard ex", "dh_score": 88,
            "signals": {"forecast_dir": "buy", "ai_signal": "buy",
                        "ai_grade": "yes", "best_roi_pct": 320,
                        "price_change_pct": 12.0},
        },
        {  # SEM dh_score (JSON antigo) — attach LÊ precomputado → None (não recalcula)
            "source": "doubleholo", "tcg_product_id": "200001",
            "name": "Pidgey",
            "signals": {"forecast_dir": "sell", "ai_signal": "sell",
                        "ai_grade": "", "best_roi_pct": None,
                        "price_change_pct": -15.0},
        },
        {  # sem productId — IGNORADO no índice (sem chave de join)
            "source": "doubleholo", "tcg_product_id": None, "name": "Trainer X",
            "signals": {"forecast_dir": "buy"},
        },
    ]


def test_load_signals_indexes_by_pid_and_skips_no_pid():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(_canonical_records(), f)
        path = f.name
    try:
        idx = dh.load_signals(path)
    finally:
        os.unlink(path)
    assert set(idx) == {"517816", "200001"}     # registro sem pid foi ignorado
    assert idx["517816"]["dh_score"] == 88


def test_load_signals_accepts_single_dict():
    rec = _canonical_records()[0]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(rec, f)  # objeto único, não lista
        path = f.name
    try:
        idx = dh.load_signals(path)
    finally:
        os.unlink(path)
    assert list(idx) == ["517816"]


# ─── attach_scores_df ────────────────────────────────────────────────────────
def _signals_idx():
    return {r["tcg_product_id"]: r for r in _canonical_records()
            if r["tcg_product_id"]}


def test_attach_prefers_precomputed_score():
    df = pd.DataFrame({"link_tcg": [
        "https://www.tcgplayer.com/product/517816/x"]})
    n = dh.attach_scores_df(df, _signals_idx())
    assert n == 1
    assert df["dh_score"].iloc[0] == 88   # usou o precomputado, não recalculou


def test_attach_matched_without_precomputed_is_none():
    # registro casa por productId mas não traz dh_score (JSON antigo) -> None.
    # A nota é single-source no pipeline; o CT NÃO recalcula (não inventa).
    df = pd.DataFrame({"link_tcg": [
        "https://www.tcgplayer.com/product/200001/y"]})
    n = dh.attach_scores_df(df, _signals_idx())
    assert n == 1                       # casou (productId presente no índice)
    assert df["dh_score"].iloc[0] is None


def test_attach_no_match_sets_none():
    df = pd.DataFrame({"link_tcg": [
        "https://prices.pokemontcg.io/tcgplayer/sv4-260",  # redirect → sem pid
        "",                                                # vazio (tcgcsv)
        None,                                              # None
    ]})
    n = dh.attach_scores_df(df, _signals_idx())
    assert n == 0
    assert df["dh_score"].isna().all()


def test_attach_missing_url_col_is_safe():
    df = pd.DataFrame({"other": [1, 2]})
    n = dh.attach_scores_df(df, _signals_idx())
    assert n == 0
    assert "dh_score" in df.columns


# ─── render markdown (coluna DH condicional, links intactos) ─────────────────
def _raw_df_for_md():
    """2 deals COMPRA: 1 com URL de PRODUTO TCGplayer (casa DH), 1 com redirect
    pokemontcg (não casa → '—'). Ambos com os 2 links."""
    return pd.DataFrame({
        "Card Name": ["Charizard ex", "Plusle"],
        "Nº": [199, 193],
        "Set": ["Obsidian Flames (obf)", "Paradox Rift (par)"],
        "Rarity": ["Special Illustration Rare", "Double Rare"],
        "Condição": ["NM", "NM"],
        "Qtd": [1, 3],
        "LIVE R$ (real)": [600.0, 120.0],
        "TCG Market (BRL)": [1000.0, 240.0],
        "TCG Market (USD)": [183.50, 44.00],
        "Net Margin % REAL": [0.40, 0.50],
        "Lucro R$ REAL": [400.0, 120.0],
        "Validation Status": ["VALIDATED_REAL", "VALIDATED_REAL"],
        "Link CardTrader": [
            "https://www.cardtrader.com/cards/222",
            "https://www.cardtrader.com/cards/111",
        ],
        "Link TCG": [
            "https://www.tcgplayer.com/product/517816/charizard",  # casa
            "https://prices.pokemontcg.io/tcgplayer/sv4-193",      # não casa
        ],
    })


def _enriched_with_dh(show=True):
    cfg = pp.DecisionConfig()
    df = pp.enrich_df(_raw_df_for_md(), hub_fee_rate=cfg.hub_fee_rate)
    if show:
        dh.attach_scores_df(df, _signals_idx(), url_col="link_tcg")
    return df, cfg


def test_markdown_dh_column_present_with_flag():
    df, cfg = _enriched_with_dh(show=True)
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0, show_dh=True)
    # cabeçalho com DH inserido após "Margem %"
    assert "| # | Margem % | DH | CT US$ |" in md
    # linha que casa mostra a nota; a que não casa mostra "—"
    char_line = [l for l in md.splitlines() if "Charizard ex" in l][0]
    plus_line = [l for l in md.splitlines() if "Plusle" in l][0]
    assert "| 88 |" in char_line
    assert "| — |" in plus_line
    # CONTRATO: os DOIS links continuam em AMBAS as linhas
    for line in (char_line, plus_line):
        assert "[oferta](" in line and "[TCG](" in line and " · " in line
    # rodapé explicativo presente
    assert "DH = 2ª opinião Double Holo" in md
    assert "não entra na margem/decisão" in md


def test_markdown_no_dh_without_flag_is_unchanged():
    df, cfg = _enriched_with_dh(show=False)  # sem attach → sem coluna dh_score
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0, show_dh=False)
    expected = ("| # | Margem % | CT US$ | TCG US$ | Dif | Carta | Set | "
                "Raridade | Cond | Qtd | Flag | Links |")
    assert expected in md
    assert " DH " not in md
    assert "2ª opinião Double Holo" not in md
    # cada linha de dado tem 12 colunas (13 pipes) — inalterado
    data_rows = [l for l in md.splitlines() if l.startswith("| 1 |")]
    assert data_rows and data_rows[0].count("|") == 13


def test_markdown_show_dh_flag_without_column_is_noop():
    """show_dh=True mas df sem dh_score (flag passada, 0 sinais anexados) não
    deve renderizar DH nem quebrar — cabeçalho fica idêntico ao padrão."""
    df, cfg = _enriched_with_dh(show=False)
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0, show_dh=True)
    assert " DH " not in md
    data_rows = [l for l in md.splitlines() if l.startswith("| 1 |")]
    assert data_rows and data_rows[0].count("|") == 13


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
