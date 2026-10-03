"""v2.29 — flag `--language` (idioma das ofertas CT) + coluna "Razão EN/<idioma>".

Contexto (sonda da API em 2026-10-03): o CT expõe o idioma da oferta em
`properties_hash.pokemon_language`; valores reais vistos em `mew` (151):
en/it/de/fr/es/pt/zh-CN (+ None). `?language=zh-CN` no endpoint
/marketplace/products filtra server-side (6 ofertas em `mew`, 0 em `svi`/`paf`).

Contratos travados aqui:
  (a) default INALTERADO: sem flag, o scanner continua só inglês ("en");
  (b) `--language zh-CN` filtra SÓ ofertas chinesas (case-insensitive no
      cliente, valor cru pro servidor) — nas 3 chamadas: filtro, listagem por
      expansão e validação per-blueprint;
  (c) postprocess: `--ratio-column` adiciona "Razão EN/<IDIOMA>" = TCG US$ ÷
      CT US$ (razão de PREÇO — nunca rotulada como margem), `--min-ratio X`
      corta linhas abaixo de X, e o contrato de 2 links por linha fica intacto.
"""
from __future__ import annotations

import inspect
import sys
from collections import defaultdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cardtrader_scanner as sc  # noqa: E402
import cardtrader_postprocess as pp  # noqa: E402


# ───────────────────────── helpers ─────────────────────────
def _listing(language: str, price_brl: float = 100.0, graded: bool = False) -> sc.Listing:
    return sc.Listing(
        product_id=1, blueprint_id=999, card_name="Pikachu",
        set_code="mew", set_name="151",
        collector_number="025", condition="Near Mint", language=language,
        price_cents=int(price_brl * 100), price_currency="BRL", price_brl=price_brl,
        quantity=1, foil=False, graded=graded, seller_username="seller",
        seller_can_sell_via_hub=True, seller_user_type="professional",
        cardtrader_url="https://www.cardtrader.com/cards/999", rarity="Common",
    )


def _stub(language: str | None = None) -> sc.Scanner:
    s = sc.Scanner.__new__(sc.Scanner)
    s.usd_brl = 5.0
    s.eur_brl = 6.0
    s.min_price_usd = 10.0
    s.exclude_graded = True
    s.threshold = 0.30
    s.hub_fee_rate = 0.0
    s.keep_all_priced = True
    s.chase_only = False
    s.ignore_skip_list = True
    s.max_consecutive_misses = 0
    s.shipping_brl_override = 0.0
    s.per_set_timeout_s = 0
    s.tcgcsv = None
    s.tcgcsv_fallback = False
    s.heartbeat = lambda *_: None
    s._checkpoint = None
    s.stats = defaultdict(int)
    if language is not None:
        s.language = language
    return s


# ───────────────── (a) default inalterado ─────────────────
def test_cli_default_language_is_en():
    with patch.object(sys, "argv", ["cardtrader_scanner.py"]):
        args = sc.parse_args()
    assert args.language == "en"


def test_scanner_init_default_language_is_en():
    """Scanner(...) sem `language` = inglês — comandos canônicos intactos."""
    param = inspect.signature(sc.Scanner.__init__).parameters["language"]
    assert param.default == "en"


def test_default_scanner_rejects_zh_cn_listing():
    s = _stub()
    s.language = inspect.signature(sc.Scanner.__init__).parameters["language"].default
    assert s._passes_filters(_listing("en"))
    assert not s._passes_filters(_listing("zh-cn"))
    assert not s._passes_filters(_listing(""))   # sem metadado de idioma → fora


# ───────────── (b) --language zh-CN filtra só chinês ─────────────
def test_cli_accepts_language_zh_cn():
    with patch.object(sys, "argv", ["cardtrader_scanner.py", "--language", "zh-CN"]):
        args = sc.parse_args()
    assert args.language == "zh-CN"


def test_zh_cn_scanner_accepts_only_chinese_listings_case_insensitive():
    """Listing.language chega lowercased ("zh-cn"); a flag pode vir "zh-CN"."""
    s = _stub(language="zh-CN")
    assert s._passes_filters(_listing("zh-cn"))
    assert not s._passes_filters(_listing("en"))
    assert not s._passes_filters(_listing("it"))
    assert not s._passes_filters(_listing("zh-cn", graded=True))  # raw only


def test_scan_expansion_requests_listings_in_configured_language():
    """A listagem por expansão vai ao CT com o idioma configurado (valor cru,
    como aceito pela API), não com a constante "en"."""
    s = _stub(language="zh-CN")
    s.ct = MagicMock()
    s.ct.list_blueprints.return_value = []
    s.ct.list_listings_by_expansion.return_value = []
    s.pricing = MagicMock()
    list(s.scan_expansion({"id": 3403, "code": "mew", "name": "151"}))
    assert s.ct.list_listings_by_expansion.called
    _, kwargs = s.ct.list_listings_by_expansion.call_args
    assert kwargs.get("language") == "zh-CN"


def test_validate_top_requests_per_blueprint_in_configured_language():
    """A validação per-blueprint (--validate-top) também respeita o idioma —
    senão o preço "real" viria da oferta inglesa, não da chinesa."""
    s = _stub(language="zh-CN")
    s.ct = MagicMock()
    s.ct.list_listings_by_blueprint.return_value = []
    opp = MagicMock()
    opp.margin_pct = 0.5
    opp.listing = _listing("zh-cn")
    s.validate_per_blueprint([opp], top_n=1)
    assert s.ct.list_listings_by_blueprint.called
    _, kwargs = s.ct.list_listings_by_blueprint.call_args
    assert kwargs.get("language") == "zh-CN"


def test_language_filter_recorded_in_stats():
    """Auditoria: a aba Stats do XLSX deve dizer em que idioma o scan rodou."""
    s = _stub(language="zh-CN")
    s.ct = MagicMock()
    s.ct.list_blueprints.return_value = []
    s.ct.list_listings_by_expansion.return_value = []
    s.pricing = MagicMock()
    list(s.scan_expansion({"id": 3403, "code": "mew", "name": "151"}))
    assert s.stats.get("language_filter") == "zh-CN"


# ───────────── (c) postprocess: coluna de RAZÃO + --min-ratio ─────────────
def _raw_df():
    return pd.DataFrame({
        "Card Name": ["Pikachu", "Charizard ex", "Mew ex"],
        "Nº": [25, 6, 151],
        "Set": ["151 (mew)", "151 (mew)", "151 (mew)"],
        "Rarity": ["Double Rare", "Double Rare", "Double Rare"],
        "Condição": ["NM", "NM", "NM"],
        "Idioma": ["ZH-CN", "ZH-CN", "ZH-CN"],
        "Qtd": [3, 1, 2],
        # CT US$ = LIVE/fx(5.0) → 2.00 / 10.00 / 40.00
        "LIVE R$ (real)": [10.0, 50.0, 200.0],
        "TCG Market (BRL)": [60.0, 250.0, 500.0],
        "TCG Market (USD)": [12.00, 50.00, 100.00],
        # net = (TCG−CT)/TCG → 0.8333 / 0.80 / 0.60  ⇔ razão 6.0× / 5.0× / 2.5×
        "Net Margin % REAL": [0.8333, 0.80, 0.60],
        "Lucro R$ REAL": [50.0, 200.0, 300.0],
        "Validation Status": ["VALIDATED_REAL", "VALIDATED_REAL", "VALIDATED_REAL"],
        "Link CardTrader": [
            "https://www.cardtrader.com/cards/1",
            "https://www.cardtrader.com/cards/2",
            "https://www.cardtrader.com/cards/3",
        ],
        "Link TCG": [
            "https://www.tcgplayer.com/product/1",
            "https://www.tcgplayer.com/product/2",
            "https://www.tcgplayer.com/product/3",
        ],
    })


def _enriched():
    cfg = pp.DecisionConfig(min_net_margin=0.25, revisar_min_net=0.20, min_lucro_liq=0.0)
    return pp.enrich_df(_raw_df(), hub_fee_rate=0.0), cfg


def test_ratio_column_off_by_default_header_unchanged():
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0)
    assert "Razão" not in md
    assert ("| # | Margem % | CT US$ | TCG US$ | Dif | Carta | Set | "
            "Raridade | Cond | Qtd | Flag | Links |") in md


def test_ratio_column_header_named_after_language_and_values_are_tcg_over_ct():
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0, show_ratio=True)
    # Header: coluna logo após "Margem %", nomeada pelo idioma das ofertas.
    assert ("| # | Margem % | Razão EN/ZH-CN | CT US$ | TCG US$ | Dif | Carta | Set | "
            "Raridade | Cond | Qtd | Flag | Links |") in md
    rows = [l for l in md.splitlines() if l.startswith("| ") and "Pikachu" in l]
    assert rows and "| 6.0× |" in rows[0], rows
    rows = [l for l in md.splitlines() if l.startswith("| ") and "Mew ex" in l]
    assert rows and "| 2.5× |" in rows[0], rows
    # Rodapé honesto: é razão de preço, não margem de revenda.
    assert "não é margem" in md.lower()


def test_min_ratio_drops_rows_below_cutoff_and_keeps_two_links():
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0, show_ratio=True, min_ratio=4.0)
    assert "Pikachu" in md and "Charizard ex" in md
    assert "Mew ex" not in md                       # 2.5× < 4.0×
    assert "4.0×" in md                             # título declara o corte
    data_rows = [l for l in md.splitlines() if l.startswith("| ") and "[oferta](" in l]
    assert len(data_rows) == 2
    for row in data_rows:
        assert "[oferta](https://www.cardtrader.com/cards/" in row
        assert "[TCG](https://www.tcgplayer.com/product/" in row


def test_min_ratio_with_nothing_left_is_honest_not_near_miss():
    """Corte deixa 0 linhas → mensagem explícita, NÃO a tabela near-miss (que
    mostraria linhas abaixo do corte como se fossem resultado)."""
    df, cfg = _enriched()
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0, show_ratio=True, min_ratio=10.0)
    assert "Pikachu" not in md and "Mew ex" not in md
    assert "10.0×" in md


def test_postprocess_cli_has_ratio_flags():
    with patch.object(sys, "argv", ["cardtrader_postprocess.py", "-i", "a.xlsx", "-o", "b.xlsx",
                                    "--ratio-column", "--min-ratio", "4"]):
        with patch.object(pp, "write_report") as wr, \
             patch.object(pp.pd, "read_excel", return_value=_raw_df()), \
             patch.object(pp, "_read_fx_usd_brl", return_value=5.0):
            pp.main()
    kwargs = wr.call_args.kwargs
    assert kwargs.get("show_ratio") is True
    assert kwargs.get("min_ratio") == 4.0
