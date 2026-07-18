# -*- coding: utf-8 -*-
"""Contratos do op_scanner (One Piece): filtros de oferta (incl. a chave REAL de
idioma `onepiece_language`, provada com as 15.986 ofertas do OP-01 em 2026-07-18),
filtro de singles por collector_number (selados vêm misturados nos blueprints),
join determinístico, margem base compra, guardas e entrega com 2 links.
Tudo offline — nenhuma chamada de rede. Fixtures com o shape REAL do OP-01."""

import pytest

from op_scanner import (
    JUNK_RATIO,
    VOLATILE_REF_RATIO,
    _num_tail,
    build_markdown,
    build_rows,
    build_secondary_index,
    carta_label,
    cheapest_offer_brl,
    classify,
    clean_secret,
    is_single,
    offer_ok,
    pick_subtype,
    ref_volatile,
    to_brl,
)

RATES = {"BRL": 5.0, "USD": 1.0, "EUR": 0.8}

EXP = {"id": 3332, "code": "op01", "name": "OP-01: Romance Dawn"}


def make_offer(cents=1000, currency="BRL", condition="Near Mint", qty=1, **props):
    ph = {"condition": condition}
    ph.update(props)
    return {"price": {"cents": cents, "currency": currency}, "quantity": qty,
            "properties_hash": ph}


def _bp(bp_id=244442, tcg=454591, version="", num="OP01-064", name="Alvida",
        rarity="Common"):
    """Shape real de single do OP-01 (Alvida OP01-064, Common, tcg 454591)."""
    return {"id": bp_id, "name": name, "version": version, "tcg_player_id": tcg,
            "fixed_properties": {"collector_number": num, "onepiece_rarity": rarity}}


def _bp_booster_box():
    """Shape real do selado misturado nos blueprints do OP-01: booster box COM
    tcg_player_id (por isso, sem o filtro de singles, casaria e viraria linha)."""
    return {"id": 244177, "name": "Romance Dawn Booster Box", "version": "",
            "tcg_player_id": 450086, "fixed_properties": {}}


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


def test_offer_ok_chave_real_onepiece_language():
    """Aceitação obrigatória do handoff (item 2.3): a chave de idioma do game 15
    é `onepiece_language` (presente em TODAS as ofertas do OP-01) e os valores
    reais observados foram en/jp/zh-CN/kr. JP NUNCA pode vazar pra referência EN
    da categoria 68 — no OP-01, 18% das ofertas eram não-EN."""
    assert offer_ok(make_offer(onepiece_language="en"))
    assert not offer_ok(make_offer(onepiece_language="jp"))     # oferta real: Marco OP01-023 US$0,15
    assert not offer_ok(make_offer(onepiece_language="zh-CN"))
    assert not offer_ok(make_offer(onepiece_language="kr"))
    assert offer_ok(make_offer())  # sem campo de idioma (defensivo — hoje o CT sempre manda)


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
        make_offer(cents=5000),                            # R$50
        make_offer(cents=3000),                            # R$30 ← menor
        make_offer(cents=100, condition="Played"),         # inválida
        make_offer(cents=200, onepiece_language="jp"),     # JP barata: NUNCA entra
        make_offer(cents=100, currency="XYZ"),             # moeda pulada
    ]
    price, qty, n_valid, skipped = cheapest_offer_brl(offers, RATES)
    assert price == 30.0 and qty == 1 and n_valid == 2 and skipped == 1


def test_cheapest_offer_sem_validas_retorna_none():
    assert cheapest_offer_brl([make_offer(condition="Played")], RATES) is None


# ── escolha de subtipo TCGplayer ──

def test_pick_subtype_unico_usa_o_que_existe():
    assert pick_subtype(None, {"Foil": 7.5}) == ("Foil", 7.5)


def test_pick_subtype_versao_foil_prefere_foil_senao_normal():
    prices = {"Normal": 1.0, "Foil": 2.0}
    assert pick_subtype("Foil", prices) == ("Foil", 2.0)
    assert pick_subtype(None, prices) == ("Normal", 1.0)


def test_pick_subtype_sem_preco_nunca_inventa():
    assert pick_subtype(None, {}) is None
    assert pick_subtype(None, {"Normal": None}) is None


# ── classificação (margem base compra + guarda anti-lixo) ──

def test_classify_compra_revisar_quase_resto():
    assert classify(0.50, ct_brl=100, tcg_brl=150, threshold=0.30)[0] == "compra"
    bucket, flag = classify(2.0, ct_brl=10, tcg_brl=30, threshold=0.30)
    assert bucket == "revisar" and "lixo" in flag
    assert classify(0.20, ct_brl=100, tcg_brl=120, threshold=0.30)[0] == "quase"
    assert classify(-0.50, ct_brl=100, tcg_brl=50, threshold=0.30)[0] == "resto"


def test_junk_ratio_e_50_por_cento():
    assert JUNK_RATIO == 0.5


# ── referência volátil ──

def test_ref_volatile_simetrica_nas_duas_direcoes():
    assert VOLATILE_REF_RATIO == 2.0
    assert ref_volatile(506.74, 1999.99)
    assert ref_volatile(100.0, 40.0)
    assert not ref_volatile(100.0, 60.0)
    assert not ref_volatile(100.0, None)
    assert not ref_volatile(100.0, 0.0)


def test_ref_volatil_rebaixa_compra_para_revisar():
    tcg_index = {454591: {"name": "Alvida", "url": "https://www.tcgplayer.com/product/454591/x",
                          "prices": {"Foil": 506.74}, "lows": {"Foil": 1999.99}}}
    offers = {244442: [make_offer(cents=134600)]}  # R$1346 → margem ~88% com BRL=5
    rows, stats, _ = build_rows(EXP, [_bp()], offers, tcg_index, RATES, 10.0)
    assert rows[0]["ref_volatil"] is True
    meta = {"data": "t", "expansoes": "op01", "fx": 5.0, "fx_fonte": "teste",
            "threshold": 0.30, "min_price_usd": 10.0}
    md = build_markdown(rows, stats, meta)
    assert "🟢 COMPRA (margem ≥ 30%) — 0" in md          # não sai como compra limpa
    assert "ref volátil" in md                            # vai pro REVISAR com o motivo


def test_ref_estavel_continua_compra_limpa():
    tcg_index = {454591: {"name": "x", "url": "https://www.tcgplayer.com/product/454591/x",
                          "prices": {"Foil": 74.0}, "lows": {"Foil": 62.89}}}
    offers = {244442: [make_offer(cents=26871)]}  # R$268,71 → ~37.7% com BRL=5
    rows, stats, _ = build_rows(EXP, [_bp()], offers, tcg_index, RATES, 10.0)
    assert rows[0]["ref_volatil"] is False
    md = build_markdown(rows, stats, {"data": "t", "expansoes": "op01", "fx": 5.0,
                                      "fx_fonte": "t", "threshold": 0.30, "min_price_usd": 10.0})
    assert "🟢 COMPRA (margem ≥ 30%) — 1" in md


# ── filtro de SINGLES (selados misturados nos blueprints — pegadinha nº 1 do handoff) ──

def test_is_single_por_collector_number():
    assert is_single(_bp())
    assert not is_single(_bp_booster_box())                      # fixed_properties vazio
    assert not is_single({"id": 1, "name": "x", "fixed_properties": None})


def test_selado_com_tcg_player_id_e_oferta_viva_nunca_vira_linha():
    """A classe que vazou no scan DBS ('Collector's Selection Vol.2'): selado COM
    tcg_player_id casaria na referência e apareceria como carta. Aqui: booster
    box do OP-01 com oferta viva e referência disponível → NUNCA vira linha,
    NUNCA entra no semref, e é contado como selado pulado."""
    box = _bp_booster_box()
    tcg_index = {450086: {"name": "Romance Dawn Booster Box",
                          "url": "https://www.tcgplayer.com/product/450086/x",
                          "prices": {"Normal": 89.99}, "lows": {"Normal": 80.0}}}
    offers = {244177: [make_offer(cents=20000)]}  # 13 ofertas vivas no probe real
    rows, stats, semref = build_rows(EXP, [box], offers, tcg_index, RATES, 10.0)
    assert rows == [] and semref == []
    assert stats["selados_pulados"] == 1 and stats["avaliadas"] == 0


def test_cobertura_no_markdown_conta_selados_pulados():
    box = _bp_booster_box()
    single = _bp()
    tcg_index = {454591: {"name": "Alvida", "url": "https://www.tcgplayer.com/product/454591/x",
                          "prices": {"Normal": 74.0}}}
    offers = {244442: [make_offer(cents=20000)], 244177: [make_offer(cents=30000)]}
    rows, stats, _ = build_rows(EXP, [box, single], offers, tcg_index, RATES, 10.0)
    md = build_markdown(rows, stats, {"data": "t", "expansoes": "op01", "fx": 5.0,
                                      "fx_fonte": "t", "threshold": 0.30, "min_price_usd": 10.0})
    assert "1 selados/acessórios pulados" in md
    assert "Romance Dawn Booster Box" not in md


# ── join determinístico + linhas ──

def test_build_rows_join_por_tcg_player_id_e_margem_base_compra():
    tcg_index = {454591: {"name": "Alvida", "url": "https://tcg/x",
                          "prices": {"Foil": 74.0}}}
    offers = {244442: [make_offer(cents=20000)]}  # R$200
    rows, stats, _ = build_rows(EXP, [_bp()], offers, tcg_index, RATES, min_price_usd=10.0)
    assert stats["avaliadas"] == 1
    row = rows[0]
    assert row["tcg_usd"] == 74.0 and row["ct_brl"] == 200.0
    assert row["margem"] == pytest.approx((74.0 * 5.0 - 200.0) / 200.0)
    assert row["oferta_url"].endswith("/cards/244442")
    assert row["raridade"] == "Common"  # de fixed_properties["onepiece_rarity"]


def test_build_rows_sem_tcg_player_id_fica_fora_com_contagem():
    rows, stats, semref = build_rows(EXP, [_bp(tcg=None)], {244442: [make_offer()]}, {}, RATES, 10.0)
    assert rows == [] and stats["sem_ref_tcg"] == 1
    assert len(semref) == 1
    assert semref[0]["motivo"] == "tcg_player_id vazio no blueprint CT"
    assert semref[0]["oferta_url"].endswith("/cards/244442")


def test_build_rows_semref_distingue_motivos():
    _, _, semref = build_rows(EXP, [_bp(tcg=999)], {244442: [make_offer()]}, {}, RATES, 10.0)
    assert semref[0]["motivo"] == "productId fora do índice tcgcsv"
    idx = {454591: {"name": "x", "url": "u", "prices": {}}}
    _, _, semref = build_rows(EXP, [_bp()], {244442: [make_offer()]}, idx, RATES, 10.0)
    assert semref[0]["motivo"] == "produto tcgcsv sem market price"
    _, _, semref = build_rows(EXP, [_bp(tcg=None)], {}, {}, RATES, 10.0)
    assert semref == []


def test_num_tail_normaliza_convencoes_op():
    assert _num_tail("OP01-064") == "64"
    assert _num_tail("064") == "64"
    assert _num_tail("OP01-121") == "121"
    # sufixo de alt art é PRESERVADO — a alt art nunca colapsa na carta base
    assert _num_tail("OP01-064b") == "64B"
    assert _num_tail("OP01-001a") == "1A"
    assert _num_tail("") == ""


def _idx_op():
    return {700: {"name": "Nami", "number": "OP01-016",
                  "url": "https://www.tcgplayer.com/product/700/x",
                  "prices": {"Normal": 12.5}, "lows": {"Normal": 11.0}}}


def test_join_secundario_resgata_match_unico_sem_versao():
    idx = _idx_op()
    sec = build_secondary_index(idx)
    bp = _bp(tcg=None, version="", num="OP01-016", name="Nami")
    rows, stats, semref = build_rows(EXP, [bp], {244442: [make_offer(cents=705)]}, idx, RATES, 0.0,
                                     sec_index=sec)
    assert stats["resgatadas_join2"] == 1 and semref == []
    assert rows[0]["join"] == "nome+numero(unico)"
    assert rows[0]["tcg_usd"] == 12.5


def test_join_secundario_ambiguo_nao_casa_e_registra():
    idx = _idx_op()
    idx[701] = dict(idx[700], url="u2")  # reprint: mesmo nome+número em outro grupo
    sec = build_secondary_index(idx)
    bp = _bp(tcg=None, version="", num="OP01-016", name="Nami")
    rows, stats, semref = build_rows(EXP, [bp], {244442: [make_offer()]}, idx, RATES, 0.0,
                                     sec_index=sec)
    assert rows == [] and stats["resgatadas_join2"] == 0
    assert "ambíguo (2 produtos)" in semref[0]["motivo"]


def test_join_secundario_nunca_com_versao_nem_nome_diferente():
    idx = _idx_op()
    sec = build_secondary_index(idx)
    # blueprint COM versão (Alternate Art etc.) nunca usa o join secundário
    bp_alt = _bp(tcg=None, version="Alternate Art", num="OP01-016", name="Nami")
    rows, stats, _ = build_rows(EXP, [bp_alt], {244442: [make_offer()]}, idx, RATES, 0.0,
                                sec_index=sec)
    assert rows == [] and stats["resgatadas_join2"] == 0
    # nome diferente não casa (igualdade exata normalizada, nunca fuzzy)
    bp_nome = _bp(tcg=None, version="", num="OP01-016", name="Nami (Wanted Poster)")
    rows, stats, _ = build_rows(EXP, [bp_nome], {244442: [make_offer()]}, idx, RATES, 0.0,
                                sec_index=sec)
    assert rows == [] and stats["resgatadas_join2"] == 0
    # sufixo de alt art no número NUNCA casa com o número base no join secundário
    bp_sufixo = _bp(tcg=None, version="", num="OP01-016a", name="Nami")
    rows, stats, _ = build_rows(EXP, [bp_sufixo], {244442: [make_offer()]}, idx, RATES, 0.0,
                                sec_index=sec)
    assert rows == [] and stats["resgatadas_join2"] == 0


def test_build_rows_piso_de_referencia():
    tcg_index = {454591: {"name": "x", "url": "u", "prices": {"Normal": 3.0}}}
    rows, stats, _ = build_rows(EXP, [_bp()], {244442: [make_offer()]}, tcg_index, RATES, 10.0)
    assert rows == [] and stats["abaixo_piso"] == 1


# ── entrega ──

def test_carta_label_junta_nome_versao_numero_sem_duplicar():
    alt = _bp(version="Alternate Art | Fixed Reprint", num="OP01-064b")
    assert carta_label(alt) == "Alvida (Alternate Art | Fixed Reprint) OP01-064b"
    assert carta_label(_bp()) == "Alvida OP01-064"
    bp = _bp(version="", num="OP01-013", name="Monkey.D.Luffy OP01-013")
    assert carta_label(bp) == "Monkey.D.Luffy OP01-013"  # número já no nome: não duplica


def test_build_markdown_todas_as_linhas_tem_os_dois_links():
    tcg_index = {454591: {"name": "x", "url": "https://www.tcgplayer.com/product/454591/x",
                          "prices": {"Foil": 74.0}}}
    offers = {244442: [make_offer(cents=20000)]}
    rows, stats, _ = build_rows(EXP, [_bp()], offers, tcg_index, RATES, 10.0)
    meta = {"data": "t", "expansoes": "op01", "fx": 5.0, "fx_fonte": "teste",
            "threshold": 0.30, "min_price_usd": 10.0}
    md = build_markdown(rows, stats, meta)
    linhas_de_dado = [l for l in md.splitlines() if l.startswith("| 1 |")]
    assert linhas_de_dado, "tabela sem linhas"
    for linha in linhas_de_dado:
        assert "[oferta](https://www.cardtrader.com/cards/" in linha
        assert "[TCG](https://www.tcgplayer.com/product/" in linha
    assert "COMPRA" in md and "Cobertura honesta" in md and "ONE PIECE" in md


def test_build_markdown_marcador_parcial():
    stats = {"blueprints": 0, "selados_pulados": 0, "sem_oferta_nm": 0, "sem_ref_tcg": 0,
             "abaixo_piso": 0, "avaliadas": 0, "ofertas_moeda_pulada": 0}
    meta = {"data": "t", "expansoes": "op01", "fx": 5.0, "fx_fonte": "teste",
            "threshold": 0.30, "min_price_usd": 10.0}
    assert "PARCIAL" not in build_markdown([], stats, dict(meta))
    md = build_markdown([], stats, dict(meta, parcial="3/10"))
    assert "PARCIAL — 3/10 expansões" in md


def test_pipe_literal_na_celula_e_escapado():
    tcg_index = {454591: {"name": "x", "url": "https://www.tcgplayer.com/product/454591/x",
                          "prices": {"Foil": 74.0}}}
    bp = _bp(version="Alternate Art | Fixed Reprint", num="OP01-064b")
    rows, stats, _ = build_rows(EXP, [bp], {244442: [make_offer(cents=26871)]}, tcg_index, RATES, 10.0)
    md = build_markdown(rows, stats, {"data": "t", "expansoes": "op01", "fx": 5.0,
                                      "fx_fonte": "t", "threshold": 0.30, "min_price_usd": 10.0})
    linha = next(l for l in md.splitlines() if l.startswith("| 1 |"))
    assert "Alternate Art \\| Fixed Reprint" in linha  # escapado — a tabela não quebra


def test_threshold_em_fracao_guard():
    from op_scanner import main
    with pytest.raises(SystemExit) as exc:
        main(["--expansions", "op01", "--threshold", "30"])
    assert "FRAÇÃO" in str(exc.value)
