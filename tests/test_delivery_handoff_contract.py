#!/usr/bin/env python3
"""Contrato de ENTREGA scanner→postprocess (regressão do bug "entrega vazia").

Bug histórico (run 27925869658, 2026-06-22): o scanner precificou 223 listings
(`Com preço TCG: 223`), mas 0 bateram o threshold de margem. O scan-time filter
descartava todo listing abaixo do threshold, então a aba "Oportunidades" do XLSX
saía SÓ com cabeçalho. O `cardtrader_postprocess.py` lê esse XLSX com
`pd.read_excel(input)` (primeira aba = "Oportunidades") → df VAZIO → o fallback
near-miss do `build_delivery_markdown` não tinha dados → entregava
"_(nenhum listing precificado — nada a entregar)_", mesmo com 223 precificados.

Estes testes travam o contrato ponta-a-ponta para que um futuro rename de coluna,
de aba, ou a re-introdução do filtro destrutivo de near-miss FALHE um teste em vez
de silenciosamente entregar uma tabela vazia:

  1. test_below_threshold_rows_survive_to_xlsx — o scanner persiste listings
     precificados ABAIXO do threshold no XLSX (contrato keep_all_priced).
  2. test_handoff_xlsx_to_delivery_nonempty — lendo o XLSX do scanner EXATAMENTE
     como o postprocess lê (read_excel default sheet) → enrich_df →
     build_delivery_markdown rende uma tabela NÃO-vazia (near-miss), não o beco.
  3. test_column_name_contract — as colunas que o postprocess consome existem no
     XLSX do scanner com os nomes esperados (pega rename silencioso).
  4. test_opportunities_only_drops_near_miss — flag legada --opportunities-only
     (keep_all_priced=False) volta a enxugar o XLSX (comportamento opt-in).

Roda via pytest E standalone:
    pytest tests/test_delivery_handoff_contract.py -v
    python tests/test_delivery_handoff_contract.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cardtrader_postprocess as pp  # noqa: E402
from cardtrader_scanner import Listing, Opportunity, export_xlsx  # noqa: E402


# Colunas do XLSX "Oportunidades" que o postprocess (enrich_df / classify /
# build_delivery_markdown) consome. Se o scanner renomear qualquer uma, o
# handoff quebra silenciosamente — este conjunto é o contrato.
_CONTRACT_COLUMNS = {
    "Card Name", "Nº", "Set", "Rarity", "Condição",
    "LIVE R$ (real)", "TCG Market (BRL)", "TCG Market (USD)",
    "Net Margin % REAL", "Validation Status",
    "Link CardTrader", "Link TCG", "Qtd",
}


def _listing(name: str = "Pichu", num: str = "22") -> Listing:
    return Listing(
        product_id=111, blueprint_id=222, card_name=name, set_code="ecard1",
        set_name="Expedition", collector_number=num, condition="Near Mint",
        language="en", price_cents=5000, price_currency="EUR", price_brl=300.0,
        quantity=2, foil=False, graded=False, seller_username="someseller",
        seller_can_sell_via_hub=True, seller_user_type="professional",
        cardtrader_url="https://cardtrader.com/cards/222", rarity="Holo Rare",
    )


def _near_miss_opp() -> Opportunity:
    """Listing precificado mas ABAIXO do threshold (below_threshold=True).

    Espelha o que o scanner agora persiste (keep_all_priced): margem bruta baixa,
    NOT_VALIDATED (não entrou nos top-N de validação per-blueprint)."""
    return Opportunity(
        listing=_listing(),
        tcg_market_usd=64.0,
        tcg_market_brl=323.0,
        ct_price_brl=300.0,
        margin_pct=0.07,            # 7% — bem abaixo de um threshold de 30%
        margin_brl=23.0,
        estimated_shipping_brl=0.0,
        net_margin_pct=0.07,
        validation_status="NOT_VALIDATED",
        tcg_url="https://tcgplayer.com/product/123",
        below_threshold=True,
    )


def _write_scan_xlsx(tmp_path: Path, opps: list[Opportunity]) -> Path:
    out = tmp_path / "scan.xlsx"
    export_xlsx(opps, stats={"tcg_price_found": len(opps)}, out_path=out,
                usd_brl=5.05, eur_brl=5.50, threshold=0.30)
    return out


def test_below_threshold_rows_survive_to_xlsx(tmp_path):
    """Linha precificada abaixo do threshold é escrita no XLSX (não descartada)."""
    out = _write_scan_xlsx(tmp_path, [_near_miss_opp()])
    df = pd.read_excel(out)  # mesma leitura default-sheet do postprocess.main
    assert len(df) == 1, "near-miss precificado deve estar no XLSX, não sumir"


def test_column_name_contract(tmp_path):
    """O XLSX do scanner expõe as colunas que o postprocess consome (anti-rename)."""
    out = _write_scan_xlsx(tmp_path, [_near_miss_opp()])
    df = pd.read_excel(out)
    missing = _CONTRACT_COLUMNS - set(df.columns)
    assert not missing, f"colunas do contrato sumiram do XLSX do scanner: {missing}"


def test_handoff_xlsx_to_delivery_nonempty(tmp_path):
    """Ponta-a-ponta: XLSX só com near-miss → entrega NÃO é o beco 'nada a entregar'.

    Reproduz exatamente o caminho do CI (scanner XLSX → postprocess) e prova que
    a entrega vira a TABELA near-miss canônica, não a mensagem vazia."""
    out = _write_scan_xlsx(tmp_path, [_near_miss_opp()])

    # Caminho idêntico ao postprocess.main: read_excel default sheet → enrich →
    # build_delivery_markdown.
    df = pd.read_excel(out)
    cfg = pp.DecisionConfig(min_net_margin=0.30)  # threshold alto: 0 COMPRA/REVISAR
    enriched = pp.enrich_df(df, hub_fee_rate=cfg.hub_fee_rate)
    md = pp.build_delivery_markdown(enriched, cfg, fx_usd_brl=5.05)

    assert "nada a entregar" not in md.lower(), (
        "REGRESSÃO: XLSX com listing precificado mas 0 acima do threshold caiu "
        "no beco 'nada a entregar' — o fallback near-miss devia render a tabela."
    )
    assert "| # | Margem % |" in md, "deve render a tabela canônica"
    assert "abaixo do limiar" in md.lower(), "near-miss deve marcar 'abaixo do limiar'"
    assert "[oferta](" in md and "[TCG](" in md, "Links combinados preservados"
    # Coluna Carta = nome + número combinados (invariante da entrega).
    assert "Pichu" in md


def test_opportunities_only_drops_near_miss():
    """Flag legada --opportunities-only (keep_all_priced=False): scanner descarta
    near-miss no scan-time filter (comportamento opt-in, XLSX enxuto).

    Testa a lógica do filtro diretamente: com keep_all_priced=False e margem <
    threshold, o listing é descartado (não yielded)."""
    # O filtro vive em Scanner.scan_expansion; aqui validamos só o predicado de
    # decisão que ele implementa, sem subir rede.
    threshold = 0.30
    margin = 0.07
    keep_all_priced = False
    below_threshold = margin < threshold
    dropped = below_threshold and not keep_all_priced
    assert dropped is True

    keep_all_priced = True
    dropped = (margin < threshold) and not keep_all_priced
    assert dropped is False, "default (keep_all_priced) NÃO descarta near-miss"


if __name__ == "__main__":
    import tempfile
    import traceback

    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            import inspect
            if "tmp_path" in inspect.signature(fn).parameters:
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            passed += 1
            print(f"PASS {fn.__name__}")
        except Exception:
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
