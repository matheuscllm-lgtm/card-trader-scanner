# -*- coding: utf-8 -*-
"""v2.26 — Dragon Ball Super (--game dragonball): provider tcgcsv primário.

Tudo offline (mocks/fixtures — sem rede). O que está travado aqui:

  (a) normalização de número: zero-padding por segmento (CT 'BT08-001' ↔
      tcgcsv 'BT8-1') e separação do sufixo de variante ('BT31-043sr',
      'FB10-013a', 'BT31-151sec');
  (b) FIDELIDADE DE VARIANTE DBZ (o equivalente do teste-chave Gengar do
      v2.23): alt art / SPR / SLR / SCR / GDR são produtos SEPARADOS com o
      MESMO número no tcgcsv, distinguidos pelo marcador '(...)' do nome —
      sufixo CT casa a classe certa; ambiguidade → None (nunca o mais barato);
  (c) subtipo de preço por foil: foil=True exige Foil/Holofoil (ausente →
      None); foil=False usa Normal; impressão ÚNICA (SR/SCR foil-only) usa a
      única existente + last_single_printing (que suprime o flag de variante
      duvidosa SEM afetar Pokémon);
  (d) market None/0 = subtipo INEXISTENTE (low/mid nunca substituem market);
  (e) set fora de DBZ_SET_TO_TCGCSV → prefill vazio → miss honesto;
  (f) mapa: valores (categoria, groupId) únicos, categorias ∈ {27, 80}, e
      NENHUM código promo/pre-release lá dentro;
  (g) GAME_PROFILES: perfil pokemon preserva as chaves históricas
      byte-idênticas; perfil dragonball usa dragonball_*;
  (h) _parse_listing com o perfil dragonball lê dragonball_language/
      dragonball_foil/dragonball_rarity (e o perfil pokemon segue lendo
      pokemon_reverse — regressão);
  (i) _build_opportunity: last_single_printing suprime low_confidence_variant
      só no caso impressão-única; caso Pokémon (sem o atributo) inalterado.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cardtrader_scanner as sc  # noqa: E402
from cardtrader_scanner import (  # noqa: E402
    DBZ_SET_TO_TCGCSV,
    GAME_PROFILES,
    Listing,
    TcgCsvDragonBallProvider,
    dbz_canon_number,
    dbz_marker_class,
    dbz_split_number,
)


# ───────────────────────── (a) normalização de número ───────────────────────
def test_canon_number_zero_padding_por_segmento():
    assert dbz_canon_number("BT08-001") == "BT8-1"
    assert dbz_canon_number("TB01-05") == "TB1-5"
    assert dbz_canon_number("FB10-013") == "FB10-13"
    assert dbz_canon_number("BT31-EM05") == "BT31-EM5"
    assert dbz_canon_number("SD1-05") == "SD1-5"
    # segmento sem dígito puro fica intacto
    assert dbz_canon_number("XYZ") == "XYZ"


def test_split_number_sufixos_reais():
    assert dbz_split_number("BT31-043sr") == ("BT31-43", "sr")
    assert dbz_split_number("FB10-013a") == ("FB10-13", "a")
    assert dbz_split_number("FB10-123sa") == ("FB10-123", "sa")
    assert dbz_split_number("BT31-151sec") == ("BT31-151", "sec")
    assert dbz_split_number("BT31-150") == ("BT31-150", "")
    assert dbz_split_number("BT31-EM05g") == ("BT31-EM5", "g")
    assert dbz_split_number("") == ("", "")


def test_marker_class_do_nome_tcgcsv():
    assert dbz_marker_class("Pan, Adorable Supporter (SPR)") == "spr"
    assert dbz_marker_class("Son Goku & Vegeta // SS Gogeta (SLR)") == "slr"
    assert dbz_marker_class("Vegito - FB10-041 (Alternate Art)") == "alternate art"
    assert dbz_marker_class("Launch // Launch, Transformed") == ""
    # stamps promo viram classes próprias — nunca se misturam com a base
    assert dbz_marker_class("Whis, Invited (Winner)") == "winner"
    # parêntese NO MEIO do nome não é marcador
    assert dbz_marker_class("Commeson // (Duplicate) Vegeta") == ""


# ─────────────────────── provider com session mockada ───────────────────────
def _product(pid, name, number, rarity):
    return {
        "productId": pid,
        "name": name,
        "extendedData": [
            {"name": "Number", "value": number},
            {"name": "Rarity", "value": rarity},
        ],
    }


def _price(pid, sub, market):
    return {"productId": pid, "subTypeName": sub, "marketPrice": market,
            "lowPrice": 0.01, "midPrice": 999.0}


FAKE_PRODUCTS = [
    # carta base com Normal+Foil (ambos com market)
    _product(1, "Krillin, Challenge", "BT31-059", "Common"),
    # líder SLR: mesmo número da base 001
    _product(2, "Son Goku & Vegeta // SS Gogeta", "BT31-001", "Special Leader Rare"),
    _product(3, "Son Goku & Vegeta // SS Gogeta (SLR)", "BT31-001", "Special Leader Rare"),
    # SCR-only (número próprio, uma variante só)
    _product(4, "SSB Kaio-ken Vegito (SCR)", "BT31-150", "Secret Rare"),
    # par SCR+GDR no MESMO número
    _product(5, "SS Vegito & SS3 Gotenks (SCR)", "BT31-151", "Secret Rare"),
    _product(6, "SS Vegito & SS3 Gotenks (GDR)", "BT31-151", "God Rare"),
    # alt art: mesmo número, marcador no nome
    _product(7, "Son Gohan : Youth - BT31-013", "BT31-013", "Uncommon"),
    _product(8, "Son Gohan : Youth - BT31-013 (Alternate Art)", "BT31-013", "Uncommon"),
    # Normal com market None + Foil com market real (market None = ausente)
    _product(9, "Yamcha, Challenge", "BT31-060", "Common"),
    # sealed (sem Number) — ignorado no índice
    {"productId": 10, "name": "Booster Box", "extendedData": []},
    # zero-padding divergente: tcgcsv 'BT31-7' × CT 'BT31-007'
    _product(11, "Play-by-Play Announcer", "BT31-7", "Common"),
    # classe duplicada no mesmo número (dois produtos base) → ambígua
    _product(12, "Duplicado A", "BT31-090", "Rare"),
    _product(13, "Duplicado B", "BT31-090", "Rare"),
    # colisão de CAUDA com BT31-060 (grupos antigos misturam BT+SD)
    _product(14, "Deck Card", "SD31-60", "Common"),
]

FAKE_PRICES = [
    _price(1, "Normal", 12.0), _price(1, "Foil", 30.0),
    _price(2, "Normal", None),          # base do líder sem market → ausente
    _price(3, "Foil", 80.0),            # SLR foil-only
    _price(4, "Foil", 150.0),           # SCR foil-only
    _price(5, "Foil", 200.0),
    _price(6, "Foil", 900.0),
    _price(7, "Normal", 11.0), _price(7, "Foil", 18.0),
    _price(8, "Normal", 55.0),          # alt art (FW-style: um subtipo só)
    _price(9, "Normal", None), _price(9, "Foil", 25.0),
    _price(11, "Normal", 10.5),
    _price(12, "Normal", 13.0), _price(13, "Normal", 14.0),
    _price(14, "Normal", 16.0),
]

FAKE_GROUPS = {"results": [
    {"groupId": 24670, "name": "Impact Beyond Dimensions",
     "abbreviation": "BT31", "publishedOn": "2025-07-11T00:00:00"},
]}


def _dbz_provider(monkeypatch, mapping=None):
    monkeypatch.setattr(
        sc, "DBZ_SET_TO_TCGCSV",
        mapping if mapping is not None else {"bt31": (27, 24670)},
    )
    prov = TcgCsvDragonBallProvider.__new__(TcgCsvDragonBallProvider)
    prov.cache = MagicMock()
    prov._set_index = {}
    prov._tail_index = {}
    prov._set_published = {}
    prov._groups_by_cat = {}
    prov.last_price_source = None
    prov.last_tcg_url = None
    prov.last_variant_used = None
    prov.last_ptcg_rarity = None
    prov.last_set_release_date = None
    prov.last_normal_market = None
    prov.last_single_printing = False

    def fake_get(url, headers=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        if url.endswith("/products"):
            resp.json.return_value = {"results": FAKE_PRODUCTS}
        elif url.endswith("/prices"):
            resp.json.return_value = {"results": FAKE_PRICES}
        elif url.endswith("/groups"):
            resp.json.return_value = FAKE_GROUPS
        else:
            resp.status_code = 404
            resp.json.return_value = {}
        return resp

    prov.session = MagicMock()
    prov.session.get.side_effect = fake_get
    return prov


# ─────────────────────────── (b)+(c) matching/preço ─────────────────────────
def test_base_foil_false_usa_normal(monkeypatch):
    prov = _dbz_provider(monkeypatch)
    price = prov.market_price_usd("Krillin", "bt31", "BT31-059", foil=False,
                                  rarity="Common")
    assert price == 12.0
    assert prov.last_variant_used == "normal"
    assert prov.last_single_printing is False
    assert prov.last_price_source == "tcgcsv"
    assert prov.last_tcg_url == "https://www.tcgplayer.com/product/1"
    assert prov.last_set_release_date == "2025-07-11"
    assert prov.last_normal_market == 12.0


def test_base_foil_true_usa_foil(monkeypatch):
    prov = _dbz_provider(monkeypatch)
    price = prov.market_price_usd("Krillin", "bt31", "BT31-059", foil=True,
                                  rarity="Common")
    assert price == 30.0
    assert prov.last_variant_used == "foil"


def test_foil_true_sem_subtipo_foil_e_none(monkeypatch):
    """Variante requerida ausente → None, NUNCA substitui (fidelidade v2.23)."""
    prov = _dbz_provider(monkeypatch)
    price = prov.market_price_usd("Announcer", "bt31", "BT31-007", foil=True,
                                  rarity="Common")
    assert price is None


def test_sufixo_sr_casa_produto_slr(monkeypatch):
    prov = _dbz_provider(monkeypatch)
    price = prov.market_price_usd("SS Gogeta", "bt31", "BT31-001sr",
                                  foil=False, rarity="Special Rare")
    assert price == 80.0
    assert prov.last_ptcg_rarity == "Special Leader Rare"
    # foil-only na fonte → impressão única sinalizada
    assert prov.last_single_printing is True
    assert prov.last_variant_used == "foil"


def test_numero_sem_sufixo_nao_pega_variante_slr(monkeypatch):
    """'BT31-001' base tem market None → miss; NÃO escorrega pro SLR de $80
    (o análogo DBZ do bug Gengar: nunca substitui variante)."""
    prov = _dbz_provider(monkeypatch)
    price = prov.market_price_usd("SS Gogeta", "bt31", "BT31-001",
                                  foil=False, rarity="Special Leader Rare")
    assert price is None


def test_scr_only_numero_proprio_casa_classe_unica(monkeypatch):
    prov = _dbz_provider(monkeypatch)
    price = prov.market_price_usd("Vegito", "bt31", "BT31-150", foil=False,
                                  rarity="Secret Rare")
    assert price == 150.0
    assert prov.last_single_printing is True


def test_par_scr_gdr_desempata_por_raridade(monkeypatch):
    prov = _dbz_provider(monkeypatch)
    price_gdr = prov.market_price_usd("Vegito", "bt31", "BT31-151",
                                      foil=False, rarity="God Rare")
    assert price_gdr == 900.0
    prov2 = _dbz_provider(monkeypatch)
    price_scr = prov2.market_price_usd("Vegito", "bt31", "BT31-151sec",
                                       foil=False, rarity="Secret Rare")
    assert price_scr == 200.0


def test_par_scr_gdr_sem_raridade_e_ambiguo_none(monkeypatch):
    prov = _dbz_provider(monkeypatch)
    price = prov.market_price_usd("Vegito", "bt31", "BT31-151",
                                  foil=False, rarity="")
    assert price is None


def test_alt_art_sufixo_a(monkeypatch):
    prov = _dbz_provider(monkeypatch)
    price = prov.market_price_usd("Son Gohan", "bt31", "BT31-013a",
                                  foil=False, rarity="Uncommon")
    assert price == 55.0
    assert prov.last_tcg_url == "https://www.tcgplayer.com/product/8"
    # e a base NÃO devolve o preço da alt art
    prov2 = _dbz_provider(monkeypatch)
    assert prov2.market_price_usd("Son Gohan", "bt31", "BT31-013",
                                  foil=False, rarity="Uncommon") == 11.0


# ─────────────────────────── (d) market None/0 ──────────────────────────────
def test_market_none_conta_como_subtipo_ausente(monkeypatch):
    """Normal market=None + Foil real → foil=False usa a ÚNICA impressão com
    market (Foil) e sinaliza single_printing (low/mid nunca substituem)."""
    prov = _dbz_provider(monkeypatch)
    price = prov.market_price_usd("Yamcha", "bt31", "BT31-060", foil=False,
                                  rarity="Common")
    assert price == 25.0
    assert prov.last_variant_used == "foil"
    assert prov.last_single_printing is True


def test_zero_padding_divergente_casa(monkeypatch):
    """CT 'BT31-007' ↔ tcgcsv 'BT31-7' (a classe de miss dos sets antigos)."""
    prov = _dbz_provider(monkeypatch)
    price = prov.market_price_usd("Announcer", "bt31", "BT31-007", foil=False,
                                  rarity="Common")
    assert price == 10.5


def test_classe_duplicada_no_mesmo_numero_e_ambigua(monkeypatch):
    prov = _dbz_provider(monkeypatch)
    price = prov.market_price_usd("Dup", "bt31", "BT31-090", foil=False,
                                  rarity="Rare")
    assert price is None


def test_numero_pelado_resolve_por_cauda_unica(monkeypatch):
    """Sets antigos do CT guardam '059' sem prefixo — a cauda única do group
    resolve pra BT31-59 (verificado no bt1 real: CT '096' × tcgcsv 'BT1-096')."""
    prov = _dbz_provider(monkeypatch)
    price = prov.market_price_usd("Krillin", "bt31", "059", foil=False,
                                  rarity="Common")
    assert price == 12.0
    assert prov.last_tcg_url == "https://www.tcgplayer.com/product/1"


def test_numero_pelado_com_cauda_ambigua_e_none(monkeypatch):
    """Cauda '60' existe em BT31-060 E SD31-60 (grupos antigos misturam BT+SD)
    → número pelado '060' é ambíguo → None. O número COMPLETO segue casando."""
    prov = _dbz_provider(monkeypatch)
    assert prov.market_price_usd("Yamcha", "bt31", "060", foil=False,
                                 rarity="Common") is None
    prov2 = _dbz_provider(monkeypatch)
    assert prov2.market_price_usd("Yamcha", "bt31", "BT31-060", foil=False,
                                  rarity="Common") == 25.0


# ─────────────────────────── (e) set fora do mapa ───────────────────────────
def test_set_nao_mapeado_e_miss_honesto(monkeypatch):
    prov = _dbz_provider(monkeypatch)  # mapa só tem bt31
    assert prov.prefill_set("bt99") is False
    assert prov.market_price_usd("X", "bt99", "BT99-001", foil=False,
                                 rarity="Common") is None
    # e a session nem foi consultada pro set sem mapa (nenhum chute de group)
    assert not any("/bt99" in str(c) for c in prov.session.get.call_args_list)


# ─────────────────────────────── (f) o mapa ─────────────────────────────────
def test_mapa_categorias_validas_e_groups_unicos():
    assert DBZ_SET_TO_TCGCSV, "mapa DBZ vazio"
    cats = {cat for cat, _ in DBZ_SET_TO_TCGCSV.values()}
    assert cats <= {27, 80}, f"categoria inesperada: {cats}"
    # o MESMO group pode atender >1 code CT (starter deck dentro do booster:
    # sd19/sd20 → Dawn of the Z-Legends), mas o par (código→group) é único
    assert len(DBZ_SET_TO_TCGCSV) == len(set(DBZ_SET_TO_TCGCSV))
    assert all(c == c.lower() for c in DBZ_SET_TO_TCGCSV), "codes em minúsculas"


def test_mapa_exclui_promos_prerelease_e_edicoes_ambiguas():
    junk = re.compile(
        r"(?:^(?:promo|prod|jdg.*|rp|wp|op|r|upromo|event|champ|fuspromo|"
        r"bgpromos|fwwfspr)$|p$|-pre$|promo)")
    ofensores = [c for c in DBZ_SET_TO_TCGCSV if junk.search(c)]
    assert not ofensores, f"códigos promo/pre-release no mapa: {ofensores}"
    # bt10/bt11 têm groups gêmeos "(2nd Edition)" no tcgcsv com os MESMOS
    # números e o CT não distingue a edição → referência ambígua, fora do mapa
    # (decisão v2.26 — só reverta com evidência de que o CT separa as edições).
    assert "bt10" not in DBZ_SET_TO_TCGCSV
    assert "bt11" not in DBZ_SET_TO_TCGCSV


# ───────────────────────────── (g) GAME_PROFILES ────────────────────────────
def test_game_profiles_pokemon_preserva_chaves_historicas():
    p = GAME_PROFILES["pokemon"]
    assert p["ct_game_id"] == 5
    assert p["language_key"] == "pokemon_language"
    assert p["rarity_key"] == "pokemon_rarity"
    assert p["foil_keys"] == ("mtg_foil", "foil", "pokemon_reverse")
    # default de classe do Scanner = perfil pokemon (instâncias via __new__,
    # padrão dos testes antigos, seguem byte-idênticas)
    assert sc.Scanner.game_profile is p


def test_game_profiles_dragonball():
    d = GAME_PROFILES["dragonball"]
    assert d["ct_game_id"] == 9
    assert d["language_key"] == "dragonball_language"
    assert d["rarity_key"] == "dragonball_rarity"
    assert "dragonball_foil" in d["foil_keys"]
    assert "pokemon_reverse" not in d["foil_keys"]


# ───────────────────── (h) _parse_listing por perfil ────────────────────────
def _raw_listing(props, bp_id=77):
    return {
        "id": 1, "blueprint_id": bp_id,
        "price": {"cents": 10000, "currency": "BRL"},
        "properties_hash": props,
        "user": {"username": "seller", "can_sell_via_hub": True,
                 "user_type": "professional"},
        "expansion": {"code": "bt31", "name_en": "Impact Beyond Dimensions"},
        "quantity": 2,
    }


def _scanner_stub(profile):
    s = sc.Scanner.__new__(sc.Scanner)
    s.game_profile = profile
    s.usd_brl = 5.0
    s.eur_brl = 5.9
    s.stats = {"skipped_exotic_currency": 0}
    return s


def test_parse_listing_dragonball_le_props_do_jogo():
    s = _scanner_stub(GAME_PROFILES["dragonball"])
    bp = {77: {"id": 77, "name": "Krillin, Challenge",
               "fixed_properties": {"collector_number": "BT31-059",
                                    "dragonball_rarity": "Common"}}}
    l = s._parse_listing(_raw_listing({
        "condition": "Near Mint", "dragonball_language": "en",
        "dragonball_foil": True, "collector_number": "BT31-059",
    }), bp)
    assert isinstance(l, Listing)
    assert l.language == "en"
    assert l.foil is True
    assert l.rarity == "Common"
    assert l.collector_number == "BT31-059"


def test_parse_listing_pokemon_segue_lendo_pokemon_reverse():
    s = _scanner_stub(GAME_PROFILES["pokemon"])
    bp = {77: {"id": 77, "name": "Gengar",
               "fixed_properties": {"pokemon_rarity": "Holo Rare"}}}
    l = s._parse_listing(_raw_listing({
        "condition": "Near Mint", "pokemon_language": "en",
        "pokemon_reverse": True, "collector_number": "007",
    }), bp)
    assert l.foil is True
    assert l.language == "en"
    assert l.rarity == "Holo Rare"
    # e um listing DBZ processado com perfil pokemon NÃO herda idioma (chave
    # errada → language vazio → filtrado) — o perfil importa
    l2 = s._parse_listing(_raw_listing({
        "condition": "Near Mint", "dragonball_language": "en",
    }), bp)
    assert l2.language == ""


# ───────────── (i) _build_opportunity × last_single_printing ────────────────
class _FakeProv:
    name = "tcgcsv-dbz"
    last_tcg_url = "https://www.tcgplayer.com/product/3"
    last_variant_used = "holofoil"
    last_ptcg_rarity = "Super Rare"
    last_price_source = "tcgcsv"
    last_set_release_date = "2025-07-11"
    last_normal_market = None

    def __init__(self, single):
        self.last_single_printing = single


def _opp_scanner():
    s = sc.Scanner.__new__(sc.Scanner)
    s.usd_brl = 5.0
    s.eur_brl = 5.9
    s.threshold = 0.30
    s.keep_all_priced = True
    s.hub_fee_rate = 0.0
    s.shipping_brl_override = 0.0
    s.chase_only = False
    s.stats = {"tcg_price_found": 0, "opportunities_found": 0,
               "priced_below_threshold": 0, "skipped_non_chase": 0}
    return s


def _listing_foil_false():
    return Listing(
        product_id=1, blueprint_id=2, card_name="SS Gogeta",
        set_code="bt31", set_name="Impact Beyond Dimensions",
        collector_number="BT31-001sr", condition="Near Mint", language="en",
        price_cents=10000, price_currency="BRL", price_brl=100.0, quantity=1,
        foil=False, graded=False, seller_username="s",
        seller_can_sell_via_hub=True, seller_user_type="professional",
        cardtrader_url="https://www.cardtrader.com/cards/2",
        rarity="Super Rare",
    )


def test_single_printing_suprime_flag_variante_duvidosa():
    s = _opp_scanner()
    opp = s._build_opportunity(_listing_foil_false(), 80.0, _FakeProv(single=True))
    assert opp is not None
    assert opp.variant_low_confidence is False


def test_sem_single_printing_flag_continua_ligando():
    """Regressão Pokémon: provider SEM o sinal (default False) mantém o flag
    v2.14/v2.18 pra listing não-foil casado em holofoil."""
    s = _opp_scanner()
    opp = s._build_opportunity(_listing_foil_false(), 80.0, _FakeProv(single=False))
    assert opp is not None
    assert opp.variant_low_confidence is True
