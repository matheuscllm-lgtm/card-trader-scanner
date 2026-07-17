# -*- coding: utf-8 -*-
"""Contratos do dbs_scanner (Dragon Ball): filtros de oferta, join determinístico,
margem base compra, guarda anti-lixo, threshold em fração e entrega com 2 links.
Tudo offline — nenhuma chamada de rede."""

import pytest

from dbs_scanner import (
    JUNK_RATIO,
    build_markdown,
    build_rows,
    carta_label,
    cheapest_offer_brl,
    classify,
    clean_secret,
    offer_ok,
    pick_subtype,
    to_brl,
)

RATES = {"BRL": 5.0, "USD": 1.0, "EUR": 0.8}


def make_offer(cents=1000, currency="BRL", condition="Near Mint", qty=1, **props):
    ph = {"condition": condition}
    ph.update(props)
    return {"price": {"cents": cents, "currency": currency}, "quantity": qty,
            "properties_hash": ph}


# ── segredo ──

def test_clean_secret_remove_bom_e_zero_width():
    assert clean_secret("﻿abc​ ") == "abc"


# ── filtros de oferta (invariante NM exato / EN / não-graded) ──

def test_offer_ok_aceita_nm_exato():
    assert offer_ok(make_offer())


@pytest.mark.parametrize("cond", ["Slightly Played", "NM/LP", "Mint", "near mint", ""])
def test_offer_ok_rejeita_condicao_nao_nm_exata(cond):
    assert not offer_ok(make_offer(condition=cond))


def test_offer_ok_rejeita_graded_e_assinada():
    graded = make_offer()
    graded["graded"] = True
    assert not offer_ok(graded)
    assert not offer_ok(make_offer(signed=True))


def test_offer_ok_idioma_en_ou_ausente_aceita_outros_rejeita():
    assert offer_ok(make_offer(dbs_card_language="en"))
    assert offer_ok(make_offer())  # sem campo de idioma (ex.: energy markers)
    assert not offer_ok(make_offer(dbs_card_language="it"))
    assert not offer_ok(make_offer(dbs_card_language="jp"))


def test_offer_ok_rejeita_qty_zero():
    assert not offer_ok(make_offer(qty=0))


# ── conversão de moeda / menor oferta ──

def test_to_brl_direto_e_cross():
    assert to_brl(1000, "BRL", RATES) == 10.0
    assert to_brl(1000, "USD", RATES) == 50.0
    assert to_brl(800, "EUR", RATES) == 50.0  # 8 EUR / 0.8 * 5.0
    assert to_brl(1000, "XYZ", RATES) is None  # moeda desconhecida nunca é chutada


def test_cheapest_offer_pega_a_menor_valida_e_conta_puladas():
    offers = [
        make_offer(cents=5000),                       # R$50
        make_offer(cents=3000),                       # R$30 ← menor
        make_offer(cents=100, condition="Played"),    # inválida
        make_offer(cents=100, currency="XYZ"),        # moeda pulada
    ]
    price, qty, n_valid, skipped = cheapest_offer_brl(offers, RATES)
    assert price == 30.0 and qty == 1 and n_valid == 2 and skipped == 1


def test_cheapest_offer_sem_validas_retorna_none():
    assert cheapest_offer_brl([make_offer(condition="Played")], RATES) is None


# ── escolha de subtipo TCGplayer ──

def test_pick_subtype_unico_usa_o_que_existe():
    assert pick_subtype(None, {"Holofoil": 7.5}) == ("Holofoil", 7.5)


def test_pick_subtype_versao_foil_prefere_foil_senao_normal():
    prices = {"Normal": 1.0, "Foil": 2.0}
    assert pick_subtype("Foil", prices) == ("Foil", 2.0)
    assert pick_subtype(None, prices) == ("Normal", 1.0)


def test_pick_subtype_sem_preco_nunca_inventa():
    assert pick_subtype(None, {}) is None
    assert pick_subtype(None, {"Normal": None}) is None


# ── classificação (margem base compra + guarda anti-lixo) ──

def test_classify_compra_revisar_quase_resto():
    # margem 50% limpa → compra
    assert classify(0.50, ct_brl=100, tcg_brl=150, threshold=0.30)[0] == "compra"
    # margem alta MAS oferta <50% da ref → revisar (nunca compra limpa)
    bucket, flag = classify(2.0, ct_brl=10, tcg_brl=30, threshold=0.30)
    assert bucket == "revisar" and "lixo" in flag
    # entre metade do corte e o corte → quase
    assert classify(0.20, ct_brl=100, tcg_brl=120, threshold=0.30)[0] == "quase"
    assert classify(-0.50, ct_brl=100, tcg_brl=50, threshold=0.30)[0] == "resto"


def test_junk_ratio_e_50_por_cento():
    assert JUNK_RATIO == 0.5


# ── join determinístico + linhas ──

EXP = {"id": 1, "code": "fuspromo", "name": "Fusion World Promos"}


def _bp(bp_id=10, tcg=555, version=None, num="E-18g", name='"Vegito" Energy Marker'):
    return {"id": bp_id, "name": name, "version": version, "tcg_player_id": tcg,
            "fixed_properties": {"collector_number": num, "dragonball_rarity": "Token"}}


def test_build_rows_join_por_tcg_player_id_e_margem_base_compra():
    tcg_index = {555: {"name": "Energy Marker (E-18) (Gold)", "url": "https://tcg/x",
                       "prices": {"Holofoil": 74.0}}}
    offers = {10: [make_offer(cents=20000)]}  # R$200
    rows, stats = build_rows(EXP, [_bp()], offers, tcg_index, RATES, min_price_usd=10.0)
    assert stats["avaliadas"] == 1
    row = rows[0]
    assert row["tcg_usd"] == 74.0 and row["ct_brl"] == 200.0
    assert row["margem"] == pytest.approx((74.0 * 5.0 - 200.0) / 200.0)
    assert row["oferta_url"].endswith("/cards/10")


def test_build_rows_sem_tcg_player_id_fica_fora_com_contagem():
    rows, stats = build_rows(EXP, [_bp(tcg=None)], {10: [make_offer()]}, {}, RATES, 10.0)
    assert rows == [] and stats["sem_ref_tcg"] == 1


def test_build_rows_piso_de_referencia():
    tcg_index = {555: {"name": "x", "url": "u", "prices": {"Normal": 3.0}}}
    rows, stats = build_rows(EXP, [_bp()], {10: [make_offer()]}, tcg_index, RATES, 10.0)
    assert rows == [] and stats["abaixo_piso"] == 1


# ── entrega ──

def test_carta_label_junta_nome_versao_numero_sem_duplicar():
    assert carta_label(_bp(version="Gold | E-18")) == '"Vegito" Energy Marker (Gold | E-18) E-18g'
    bp = _bp(version=None, num="E-18", name="Energy Marker E-18")
    assert carta_label(bp) == "Energy Marker E-18"


def test_build_markdown_todas_as_linhas_tem_os_dois_links():
    tcg_index = {555: {"name": "x", "url": "https://www.tcgplayer.com/product/555/x",
                       "prices": {"Holofoil": 74.0}}}
    offers = {10: [make_offer(cents=20000)]}
    rows, stats = build_rows(EXP, [_bp()], offers, tcg_index, RATES, 10.0)
    meta = {"data": "t", "expansoes": "fuspromo", "fx": 5.0, "fx_fonte": "teste",
            "threshold": 0.30, "min_price_usd": 10.0}
    md = build_markdown(rows, stats, meta)
    linhas_de_dado = [l for l in md.splitlines() if l.startswith("| 1 |")]
    assert linhas_de_dado, "tabela sem linhas"
    for linha in linhas_de_dado:
        assert "[oferta](https://www.cardtrader.com/cards/" in linha
        assert "[TCG](https://www.tcgplayer.com/product/" in linha
    assert "COMPRA" in md and "Cobertura honesta" in md


def test_threshold_em_fracao_guard():
    from dbs_scanner import main
    with pytest.raises(SystemExit) as exc:
        main(["--expansions", "fuspromo", "--threshold", "30"])
    assert "FRAÇÃO" in str(exc.value)
