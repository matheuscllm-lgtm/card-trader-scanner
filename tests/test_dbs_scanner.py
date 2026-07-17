# -*- coding: utf-8 -*-
"""Contratos do dbs_scanner (Dragon Ball): filtros de oferta, join determinístico,
margem base compra, guarda anti-lixo, threshold em fração e entrega com 2 links.
Tudo offline — nenhuma chamada de rede."""

import pytest

from dbs_scanner import (
    JUNK_RATIO,
    build_secondary_index,
    _num_tail,
    VOLATILE_REF_RATIO,
    ref_volatile,
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


# ── referência volátil (market vs menor anúncio atual — caso Bulma SB01-057) ──

def test_ref_volatile_simetrica_nas_duas_direcoes():
    assert VOLATILE_REF_RATIO == 2.0
    assert ref_volatile(506.74, 1999.99)      # anúncios MUITO acima do market (Bulma)
    assert ref_volatile(100.0, 40.0)          # anúncios muito abaixo do market
    assert not ref_volatile(100.0, 60.0)      # divergência < 2× = ok
    assert not ref_volatile(100.0, None)      # sem lowPrice → sem flag (não inventa sinal)
    assert not ref_volatile(100.0, 0.0)


def test_ref_volatil_rebaixa_compra_para_revisar():
    tcg_index = {555: {"name": "Bulma", "url": "https://www.tcgplayer.com/product/555/x",
                       "prices": {"Holofoil": 506.74}, "lows": {"Holofoil": 1999.99}}}
    offers = {10: [make_offer(cents=134600)]}  # R$1346 → margem ~88% com RATES BRL=5
    rows, stats, _ = build_rows(EXP, [_bp()], offers, tcg_index, RATES, 10.0)
    assert rows[0]["ref_volatil"] is True
    meta = {"data": "t", "expansoes": "x", "fx": 5.0, "fx_fonte": "teste",
            "threshold": 0.30, "min_price_usd": 10.0}
    md = build_markdown(rows, stats, meta)
    assert "🟢 COMPRA (margem ≥ 30%) — 0" in md          # não sai como compra limpa
    assert "ref volátil" in md                            # vai pro REVISAR com o motivo


def test_ref_estavel_continua_compra_limpa():
    tcg_index = {555: {"name": "x", "url": "https://www.tcgplayer.com/product/555/x",
                       "prices": {"Holofoil": 74.0}, "lows": {"Holofoil": 62.89}}}
    offers = {10: [make_offer(cents=26871)]}  # R$268,71 → ~37.7%% com BRL=5
    rows, stats, _ = build_rows(EXP, [_bp()], offers, tcg_index, RATES, 10.0)
    assert rows[0]["ref_volatil"] is False
    md = build_markdown(rows, stats, {"data": "t", "expansoes": "x", "fx": 5.0,
                                      "fx_fonte": "t", "threshold": 0.30, "min_price_usd": 10.0})
    assert "🟢 COMPRA (margem ≥ 30%) — 1" in md


# ── join determinístico + linhas ──

EXP = {"id": 1, "code": "fuspromo", "name": "Fusion World Promos"}


def _bp(bp_id=10, tcg=555, version=None, num="E-18g", name='"Vegito" Energy Marker'):
    return {"id": bp_id, "name": name, "version": version, "tcg_player_id": tcg,
            "fixed_properties": {"collector_number": num, "dragonball_rarity": "Token"}}


def test_build_rows_join_por_tcg_player_id_e_margem_base_compra():
    tcg_index = {555: {"name": "Energy Marker (E-18) (Gold)", "url": "https://tcg/x",
                       "prices": {"Holofoil": 74.0}}}
    offers = {10: [make_offer(cents=20000)]}  # R$200
    rows, stats, _ = build_rows(EXP, [_bp()], offers, tcg_index, RATES, min_price_usd=10.0)
    assert stats["avaliadas"] == 1
    row = rows[0]
    assert row["tcg_usd"] == 74.0 and row["ct_brl"] == 200.0
    assert row["margem"] == pytest.approx((74.0 * 5.0 - 200.0) / 200.0)
    assert row["oferta_url"].endswith("/cards/10")


def test_build_rows_sem_tcg_player_id_fica_fora_com_contagem():
    rows, stats, semref = build_rows(EXP, [_bp(tcg=None)], {10: [make_offer()]}, {}, RATES, 10.0)
    assert rows == [] and stats["sem_ref_tcg"] == 1
    # sidecar de honestidade: o blueprint COM oferta viva não some em silêncio
    assert len(semref) == 1
    assert semref[0]["motivo"] == "tcg_player_id vazio no blueprint CT"
    assert semref[0]["oferta_url"].endswith("/cards/10")


def test_build_rows_semref_distingue_motivos():
    # tcg_player_id aponta pra produto que não existe no índice
    _, _, semref = build_rows(EXP, [_bp(tcg=999)], {10: [make_offer()]}, {}, RATES, 10.0)
    assert semref[0]["motivo"] == "productId fora do índice tcgcsv"
    # produto existe mas sem nenhum market price
    idx = {555: {"name": "x", "url": "u", "prices": {}}}
    _, _, semref = build_rows(EXP, [_bp()], {10: [make_offer()]}, idx, RATES, 10.0)
    assert semref[0]["motivo"] == "produto tcgcsv sem market price"
    # sem oferta NM viva → não entra no sidecar (não é deal possível)
    _, _, semref = build_rows(EXP, [_bp(tcg=None)], {}, {}, RATES, 10.0)
    assert semref == []


def test_num_tail_normaliza_convencoes():
    assert _num_tail("BT12-041") == "41"
    assert _num_tail("041") == "41"
    assert _num_tail("FB04-130") == "130"
    assert _num_tail("") == ""


def _idx_masters():
    # produto estilo Masters antigo: nome limpo, number completo, sem tcg_player_id no CT
    return {700: {"name": "Gotenks, Battling the Forces of Evil", "number": "BT12-041",
                  "url": "https://www.tcgplayer.com/product/700/x",
                  "prices": {"Normal": 0.64}, "lows": {"Normal": 0.55}}}


def test_join_secundario_resgata_match_unico_sem_versao():
    idx = _idx_masters()
    sec = build_secondary_index(idx)
    bp = _bp(tcg=None, version=None, num="041", name="Gotenks, Battling the Forces of Evil")
    rows, stats, semref = build_rows(EXP, [bp], {10: [make_offer(cents=705)]}, idx, RATES, 0.0,
                                     sec_index=sec)
    assert stats["resgatadas_join2"] == 1 and semref == []
    assert rows[0]["join"] == "nome+numero(unico)"
    assert rows[0]["tcg_usd"] == 0.64


def test_join_secundario_ambiguo_nao_casa_e_registra():
    idx = _idx_masters()
    idx[701] = dict(idx[700], url="u2")  # reprint: mesmo nome+número em outro grupo
    sec = build_secondary_index(idx)
    bp = _bp(tcg=None, version=None, num="041", name="Gotenks, Battling the Forces of Evil")
    rows, stats, semref = build_rows(EXP, [bp], {10: [make_offer()]}, idx, RATES, 0.0,
                                     sec_index=sec)
    assert rows == [] and stats["resgatadas_join2"] == 0
    assert "ambíguo (2 produtos)" in semref[0]["motivo"]


def test_join_secundario_nunca_com_versao_nem_nome_diferente():
    idx = _idx_masters()
    sec = build_secondary_index(idx)
    # blueprint COM versão (Gold etc.) nunca usa o join secundário
    bp_gold = _bp(tcg=None, version="Gold", num="041", name="Gotenks, Battling the Forces of Evil")
    rows, stats, semref = build_rows(EXP, [bp_gold], {10: [make_offer()]}, idx, RATES, 0.0,
                                     sec_index=sec)
    assert rows == [] and stats["resgatadas_join2"] == 0
    # nome diferente não casa (igualdade exata normalizada, nunca fuzzy)
    bp_nome = _bp(tcg=None, version=None, num="041", name="Gotenks the Grim Reaper")
    rows, stats, _ = build_rows(EXP, [bp_nome], {10: [make_offer()]}, idx, RATES, 0.0,
                                sec_index=sec)
    assert rows == [] and stats["resgatadas_join2"] == 0


def test_build_rows_piso_de_referencia():
    tcg_index = {555: {"name": "x", "url": "u", "prices": {"Normal": 3.0}}}
    rows, stats, _ = build_rows(EXP, [_bp()], {10: [make_offer()]}, tcg_index, RATES, 10.0)
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
    rows, stats, _ = build_rows(EXP, [_bp()], offers, tcg_index, RATES, 10.0)
    meta = {"data": "t", "expansoes": "fuspromo", "fx": 5.0, "fx_fonte": "teste",
            "threshold": 0.30, "min_price_usd": 10.0}
    md = build_markdown(rows, stats, meta)
    linhas_de_dado = [l for l in md.splitlines() if l.startswith("| 1 |")]
    assert linhas_de_dado, "tabela sem linhas"
    for linha in linhas_de_dado:
        assert "[oferta](https://www.cardtrader.com/cards/" in linha
        assert "[TCG](https://www.tcgplayer.com/product/" in linha
    assert "COMPRA" in md and "Cobertura honesta" in md


def test_build_markdown_marcador_parcial():
    stats = {"blueprints": 0, "sem_oferta_nm": 0, "sem_ref_tcg": 0,
             "abaixo_piso": 0, "avaliadas": 0, "ofertas_moeda_pulada": 0}
    meta = {"data": "t", "expansoes": "x", "fx": 5.0, "fx_fonte": "teste",
            "threshold": 0.30, "min_price_usd": 10.0}
    assert "PARCIAL" not in build_markdown([], stats, dict(meta))
    md = build_markdown([], stats, dict(meta, parcial="3/10"))
    assert "PARCIAL — 3/10 expansões" in md


def test_pipe_literal_na_celula_e_escapado():
    tcg_index = {555: {"name": "x", "url": "https://www.tcgplayer.com/product/555/x",
                       "prices": {"Holofoil": 74.0}}}
    bp = _bp(version="Tournament Pack 09 | Winner", num="FP-066w", name="Broly")
    rows, stats, _ = build_rows(EXP, [bp], {10: [make_offer(cents=26871)]}, tcg_index, RATES, 10.0)
    md = build_markdown(rows, stats, {"data": "t", "expansoes": "x", "fx": 5.0,
                                      "fx_fonte": "t", "threshold": 0.30, "min_price_usd": 10.0})
    linha = next(l for l in md.splitlines() if l.startswith("| 1 |"))
    assert "Pack 09 \\| Winner" in linha  # escapado — a tabela não quebra


def test_threshold_em_fracao_guard():
    from dbs_scanner import main
    with pytest.raises(SystemExit) as exc:
        main(["--expansions", "fuspromo", "--threshold", "30"])
    assert "FRAÇÃO" in str(exc.value)
