#!/usr/bin/env python3
"""
test_reverse_lowvalue_guard.py — v2.24 (2026-06-26)

Guard de honestidade de preço: common/uncommon NÃO-holo que casa em
`reverseHolofoil` cujo market é um OUTLIER absurdo vs `normal` deve disparar a
flag "Variante Baixa Confiança" → roteada pra REVISAR ("validar manual"), nunca
apresentada como COMPRA limpa.

BUG (confirmado com dados ao vivo, scan vintage 2026-06-26): 16/40 "deals"
referenciados ao reverseHolofoil. Pra commons/uncommons da era EX esses listings
SÃO genuinamente reverse (foil=True), então `select_tcgplayer_variant_price`
acerta ao cair em reverseHolofoil — MAS o `reverseHolofoil.market` da
pokemontcg.io pra vintage barato é um número fino, dirigido por outlier, não uma
âncora líquida. A flag v2.18 NÃO disparava (de propósito, pra não pegar Holo
Rares onde reverse é o fallback intencional). O guard v2.24 fecha esse buraco
via a razão reverse/normal.

Casos reais (pokemontcg.io ao vivo, 2026-06-26):
  Lileep   ex12-56  Common    normal $0.55  vs reverse $37.50 = 68×  → flag
  Slugma   ex8-75   Common    normal $0.45  vs reverse $25.00 = 56×  → flag
  Kakuna   ex6-36   Uncommon  normal $0.65  vs reverse $37.00 = 57×  → flag
  Persian  ex6-44   Uncommon  normal $2.90  vs reverse $65.00 = 22×  → flag
  Volbeat  ex9-42   Uncommon  normal $2.06  vs reverse $29.83 = 14×  → flag
Contra-exemplo legítimo (prêmio reverse Skyridge real, NÃO disparar):
  Zubat    ecard3-118  Common normal $33.47 vs reverse $104.99 = 3.1× → no flag
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cardtrader_scanner as scanner  # noqa: E402
import cardtrader_postprocess as pp  # noqa: E402

RATIO = scanner.REVERSE_NONHOLO_OUTLIER_RATIO


# ─────────────────────────────────────────────────────────────────────────────
# 1) Guard puro: _reverse_nonholo_market_outlier (os 5 casos reais + boundary)
# ─────────────────────────────────────────────────────────────────────────────

def _guard(selected, normal, *, variant="reverseHolofoil", is_holo=False):
    return scanner._reverse_nonholo_market_outlier(variant, is_holo, selected, normal)


def test_ratio_constant_is_5():
    assert scanner.REVERSE_NONHOLO_OUTLIER_RATIO == 5.0


def test_lileep_68x_flags():
    # Lileep ex12-56 Common: normal $0.55 vs reverseHolofoil $37.50 = 68×.
    assert _guard(37.50, 0.55) is True


def test_slugma_56x_flags():
    assert _guard(25.00, 0.45) is True


def test_kakuna_57x_flags():
    assert _guard(37.00, 0.65) is True


def test_persian_22x_flags():
    assert _guard(65.00, 2.90) is True


def test_volbeat_14x_flags():
    # Volbeat ex9-42 Uncommon: normal $2.06 vs reverse $29.83 = 14× → flag.
    assert _guard(29.83, 2.06) is True


def test_zubat_skyridge_3x_does_not_flag():
    # Zubat ecard3-118 Common: normal $33.47 vs reverse $104.99 = 3.1× — prêmio
    # reverse Skyridge GENUÍNO, abaixo do RATIO=5 → NÃO dispara.
    assert _guard(104.99, 33.47) is False


def test_boundary_exactly_5x_does_not_flag():
    # Exatamente 5× → strict `>` → NÃO dispara (limiar é exclusivo).
    assert _guard(5.0 * 2.00, 2.00) is False


def test_boundary_just_above_5x_flags():
    # Logo acima de 5× → dispara.
    assert _guard(5.0 * 2.00 + 0.01, 2.00) is True


def test_holo_rare_with_reverse_normal_absent_does_not_flag():
    # Holo Rare cuja referência caiu em reverseHolofoil mas sem `normal` (None) —
    # caso v2.10 (fallback intencional). normal ausente → guard NÃO dispara.
    assert _guard(1599.99, None) is False


def test_holo_card_does_not_flag_even_with_ratio():
    # Carta intrinsecamente holo (is_holo True) nunca dispara este guard.
    assert _guard(37.50, 0.55, is_holo=True) is False


def test_non_reverse_variant_does_not_flag():
    # Variante escolhida != reverseHolofoil → guard inerte (é outro caminho de flag).
    assert _guard(37.50, 0.55, variant="holofoil") is False


def test_normal_market_zero_does_not_flag():
    # normal.market == 0 (ou falsy) → divisão sem âncora → NÃO dispara.
    assert _guard(37.50, 0.0) is False


# ─────────────────────────────────────────────────────────────────────────────
# 2) Integração no scanner: _build_opportunity seta variant_low_confidence
# ─────────────────────────────────────────────────────────────────────────────

class _FakeProvider:
    """Provider mínimo que expõe o contrato last_* lido por _build_opportunity."""
    name = "pokemontcg"

    def __init__(self, variant, normal_market, rarity="Common"):
        self.last_tcg_url = "https://www.tcgplayer.com/product/123"
        self.last_variant_used = variant
        self.last_ptcg_rarity = rarity
        self.last_set_release_date = "2005/10/31"
        self.last_price_source = "pokemontcg"
        self.last_normal_market = normal_market


def _scanner_stub():
    s = scanner.Scanner.__new__(scanner.Scanner)
    s.usd_brl = 5.0
    s.hub_fee_rate = 0.0
    s.threshold = 0.30
    s.keep_all_priced = True
    s.chase_only = False
    s.shipping_brl_override = 0.0
    s.stats = defaultdict(int)
    return s


def _listing(foil, rarity="Common", ct_brl=10.0):
    return scanner.Listing(
        product_id=1, blueprint_id=999, card_name="Lileep",
        set_code="ex12", set_name="EX Legend Maker",
        collector_number="056", condition="Near Mint", language="en",
        price_cents=int(ct_brl * 100), price_currency="BRL", price_brl=ct_brl,
        quantity=1, foil=foil, graded=False, seller_username="seller",
        seller_can_sell_via_hub=True, seller_user_type="professional",
        cardtrader_url="https://www.cardtrader.com/cards/999",
        rarity=rarity,
    )


def test_build_opportunity_flags_reverse_outlier():
    # Lileep-like: reverse genuíno (foil=True), reverse market 37.50 vs normal 0.55.
    s = _scanner_stub()
    prov = _FakeProvider("reverseHolofoil", normal_market=0.55)
    opp = s._build_opportunity(_listing(foil=True), tcg_market=37.50, source_provider=prov)
    assert opp is not None
    assert opp.variant_low_confidence is True
    # Margem/preço inalterados (sinal-only): margem bruta = (187.5 - 10) / 187.5.
    assert abs(opp.margin_pct - ((37.50 * 5.0 - 10.0) / (37.50 * 5.0))) < 1e-9


def test_build_opportunity_no_flag_for_genuine_skyridge_premium():
    # Zubat-like 3.1× — NÃO dispara, segue COMPRA limpa.
    s = _scanner_stub()
    prov = _FakeProvider("reverseHolofoil", normal_market=33.47)
    opp = s._build_opportunity(_listing(foil=True), tcg_market=104.99, source_provider=prov)
    assert opp is not None
    assert opp.variant_low_confidence is False


def test_build_opportunity_no_flag_for_holo_rare_reverse_normal_absent():
    # Holo Rare reverse sem normal → não dispara (fallback intencional v2.10).
    s = _scanner_stub()
    prov = _FakeProvider("reverseHolofoil", normal_market=None, rarity="Rare Holo")
    opp = s._build_opportunity(
        _listing(foil=True, rarity="Holo Rare"), tcg_market=1599.99, source_provider=prov
    )
    assert opp is not None
    assert opp.variant_low_confidence is False


def test_build_opportunity_preserves_v218_holofoil_flag():
    # Regressão: o caminho v2.18 (não-foil, não-holo, holofoil) segue disparando.
    s = _scanner_stub()
    prov = _FakeProvider("holofoil", normal_market=None)
    opp = s._build_opportunity(_listing(foil=False), tcg_market=146.0, source_provider=prov)
    assert opp is not None
    assert opp.variant_low_confidence is True


# ─────────────────────────────────────────────────────────────────────────────
# 3) Postprocess: a flag roteia COMPRA → REVISAR (nunca "clean COMPRA")
# ─────────────────────────────────────────────────────────────────────────────

def _compra_row(**overrides):
    row = {
        "chase_tier": "TOP",
        "net_margin": 0.55,
        "lucro_liq": 120.0,
        "validation_status": "VALIDATED_REAL",
        "trainer_gallery_potential_fp": False,
        "card_number": "056",
        "set_code": "ex12",
    }
    row.update(overrides)
    return row


def test_postprocess_clean_compra_without_flag():
    cfg = pp.DecisionConfig()
    decisao, _ = pp.classify_decision(_compra_row(), cfg)
    assert decisao == "COMPRA"


def test_postprocess_flag_sim_downgrades_to_revisar():
    cfg = pp.DecisionConfig()
    decisao, porque = pp.classify_decision(
        _compra_row(variant_low_confidence="Sim"), cfg
    )
    assert decisao == "REVISAR"
    assert "Variante Baixa Confiança" in porque


def test_postprocess_flag_empty_stays_compra():
    cfg = pp.DecisionConfig()
    decisao, _ = pp.classify_decision(
        _compra_row(variant_low_confidence=""), cfg
    )
    assert decisao == "COMPRA"


def test_postprocess_flag_does_not_promote_a_nao():
    # Linha que SERIA NAO (net abaixo do piso) NÃO é promovida a REVISAR pela flag.
    cfg = pp.DecisionConfig()
    decisao, _ = pp.classify_decision(
        _compra_row(net_margin=0.05, variant_low_confidence="Sim"), cfg
    )
    assert decisao == "NAO"


def test_is_truthy_flag_variants():
    assert pp._is_truthy_flag("Sim") is True
    assert pp._is_truthy_flag("sim") is True
    assert pp._is_truthy_flag(True) is True
    assert pp._is_truthy_flag("") is False
    assert pp._is_truthy_flag(None) is False
    assert pp._is_truthy_flag(float("nan")) is False
