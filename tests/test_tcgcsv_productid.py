"""Fix(2) — resolver OFFLINE de productId TCGplayer (ponte tcgcsv) + integração no
postprocess (`attach_product_ids`). Tudo offline (fetchers injetados, sem rede).

Cobre:
  - resolução direta quando 1 número casa 1 productId (regardless de variante);
  - desambiguação por variante quando 1 número casa >1 productId;
  - ANTI-INVENÇÃO: número multi-produto sem variante OU variante ambígua → None;
  - número desconhecido / groups indisponíveis → None (sem chute);
  - ptcg_setcodes_for inclui aliases do mapa do scanner;
  - attach_product_ids: link tcgplayer.com/product (Fix(1)) NÃO chama o resolver;
    linha pokemontcg-redirect usa o resolver; sem resolução → None;
  - end-to-end: DH casa numa linha pokemontcg-redirect via productId resolvido.

Roda via pytest E standalone.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import cardtrader_postprocess as pp
import doubleholo_join as dh
import tcgcsv_productid as tpid


# ─── fixtures tcgcsv sintéticas (offline) ────────────────────────────────────
_GROUPS = [{"groupId": 999, "name": "My Test Set", "abbreviation": "ZZZ"}]

# productId → "Number"
_PRODUCTS = {"results": [
    {"productId": 100, "extendedData": [{"name": "Number", "value": "199/197"}]},
    {"productId": 215, "extendedData": [{"name": "Number", "value": "215/197"}]},
    # número 55 compartilhado por 2 produtos (regular vs. variante)
    {"productId": 300, "extendedData": [{"name": "Number", "value": "055/197"}]},
    {"productId": 301, "extendedData": [{"name": "Number", "value": "055/197"}]},
    # número 77 compartilhado por 2 produtos com a MESMA variante → ambíguo
    {"productId": 400, "extendedData": [{"name": "Number", "value": "077/197"}]},
    {"productId": 401, "extendedData": [{"name": "Number", "value": "077/197"}]},
]}
_PRICES = {"results": [
    {"productId": 100, "subTypeName": "Holofoil", "marketPrice": 5},
    {"productId": 215, "subTypeName": "Holofoil", "marketPrice": 9},
    {"productId": 300, "subTypeName": "Normal", "marketPrice": 1},
    {"productId": 300, "subTypeName": "Reverse Holofoil", "marketPrice": 2},
    {"productId": 301, "subTypeName": "Holofoil", "marketPrice": 3},
    {"productId": 400, "subTypeName": "Holofoil", "marketPrice": 4},
    {"productId": 401, "subTypeName": "Holofoil", "marketPrice": 6},
]}


def _resolver(groups=_GROUPS, products=_PRODUCTS, prices=_PRICES):
    def fetch_json(path):
        if path.endswith("/products"):
            return products
        if path.endswith("/prices"):
            return prices
        return None
    return tpid.ProductIdResolver(fetch_json=fetch_json,
                                  fetch_groups=lambda: groups)


# ⚠️ usar set_name único (não em nenhum mapa de abbr) → força o fallback-por-nome
_NAME = "My Test Set"
_CODE = "zzztest"  # não está em SET_ALIAS_TO_PTCG nem PTCG_SETCODE_TO_TCGCSV_ABBR


# ─── resolução ───────────────────────────────────────────────────────────────
def test_single_product_number_resolves_regardless_of_variant():
    r = _resolver()
    assert r.resolve(_CODE, _NAME, "199", "holofoil") == "100"
    # 1 só produto p/ o número → resolve mesmo sem variante
    assert r.resolve(_CODE, _NAME, "199", "") == "100"
    assert r.resolve(_CODE, _NAME, "215", None) == "215"


def test_multi_product_number_disambiguated_by_variant():
    r = _resolver()
    # número 55: reverse → 300; holofoil → 301
    assert r.resolve(_CODE, _NAME, "055", "reverseHolofoil") == "300"
    assert r.resolve(_CODE, _NAME, "55", "normal") == "300"
    assert r.resolve(_CODE, _NAME, "55", "holofoil") == "301"


def test_multi_product_no_variant_returns_none():
    r = _resolver()
    assert r.resolve(_CODE, _NAME, "55", "") is None
    assert r.resolve(_CODE, _NAME, "55", None) is None


def test_ambiguous_same_variant_returns_none():
    r = _resolver()
    # número 77: dois produtos, ambos Holofoil → não dá pra desambiguar → None
    assert r.resolve(_CODE, _NAME, "77", "holofoil") is None


def test_unknown_number_returns_none():
    r = _resolver()
    assert r.resolve(_CODE, _NAME, "9999", "holofoil") is None


def test_no_groups_returns_none():
    r = _resolver(groups=None)
    assert r.resolve(_CODE, _NAME, "199", "holofoil") is None


def test_unresolvable_set_name_returns_none():
    r = _resolver()
    assert r.resolve("nope", "Totally Unknown Set Name", "199", "holofoil") is None


def test_ptcg_setcodes_includes_aliases():
    codes = tpid.ptcg_setcodes_for("asc")
    assert "asc" in codes and len(codes) >= 1


# ─── attach_product_ids (postprocess) ────────────────────────────────────────
class _SpyResolver:
    """Resolver fake que conta chamadas e devolve pid fixo por número."""
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def resolve(self, code, name, number, variant):
        self.calls.append((code, name, str(number), variant))
        return self.mapping.get(str(number))


def _rows():
    return pd.DataFrame({
        "set_code": ["Obsidian Flames (obf)", "Paradox Rift (par)", "Asc (asc)"],
        "card_number": [199, 193, 5],
        "Variant": ["holofoil", "reverseHolofoil", "holofoil"],
        "link_tcg": [
            "https://www.tcgplayer.com/product/517816/x",  # Fix(1): pid direto
            "https://prices.pokemontcg.io/tcgplayer/sv4-193",  # Fix(2): resolver
            "",  # sem link → resolver (mas mapping não tem 5 → None)
        ],
    })


def _pid_list(df):
    return [None if (v is None or (isinstance(v, float) and pd.isna(v))) else v
            for v in df["tcg_product_id"]]


def test_attach_product_ids_prefers_direct_link_skips_resolver():
    df = _rows()
    spy = _SpyResolver({"193": "900001"})
    n = pp.attach_product_ids(df, spy)
    assert _pid_list(df) == ["517816", "900001", None]
    assert n == 2
    # a linha com link tcgplayer.com/product NÃO foi ao resolver
    assert "199" not in [c[2] for c in spy.calls]
    # as outras duas (sem product-link) foram
    assert {"193", "5"} == {c[2] for c in spy.calls}


def test_attach_product_ids_no_resolver_only_direct_links():
    df = _rows()
    n = pp.attach_product_ids(df, None)  # sem resolver → só Fix(1)
    assert _pid_list(df) == ["517816", None, None]
    assert n == 1


def test_attach_product_ids_mask_gates_resolver_to_deal_rows():
    """Follow-up #4: o resolver OFFLINE (I/O via tcgcsv) só roda nas linhas que
    viram deal (resolve_mask). Linhas fora da máscara NÃO vão ao resolver — mas
    o Fix(1) (productId direto do link, sem I/O) continua valendo p/ TODAS."""
    df = _rows()
    spy = _SpyResolver({"193": "900001", "5": "700002"})
    mask = [True, True, False]  # row2 (número 5) fora da máscara
    n = pp.attach_product_ids(df, spy, resolve_mask=mask)
    # row0 = Fix(1) link direto (sem resolver); row1 = resolver; row2 = mascarada → None
    assert _pid_list(df) == ["517816", "900001", None]
    assert n == 2
    # resolver chamado SÓ p/ a linha 1 (número 193); a linha 2 (número 5) foi pulada
    assert [c[2] for c in spy.calls] == ["193"]


def test_attach_product_ids_mask_none_resolves_all_rows():
    """resolve_mask=None (default) preserva o comportamento antigo: resolve todas."""
    df = _rows()
    spy = _SpyResolver({"193": "900001", "5": "700002"})
    n = pp.attach_product_ids(df, spy, resolve_mask=None)
    assert _pid_list(df) == ["517816", "900001", "700002"]
    assert n == 3
    assert {"193", "5"} == {c[2] for c in spy.calls}


def test_attach_product_ids_mask_aligns_on_noncontiguous_index():
    """Regressão: o gating é POSICIONAL (enumerate(iterrows()) vs list(mask)). Com
    índice do pandas NÃO contíguo (df filtrado), a máscara ainda casa a linha certa
    porque ambos iteram em ORDEM DE LINHA — não pelo rótulo do índice. Sem isto, um
    df com índice [10, 11, 12] gatearia a linha errada."""
    df = _rows()
    df.index = [10, 11, 12]  # índice não-contíguo, como num df filtrado/concatenado
    spy = _SpyResolver({"193": "900001", "5": "700002"})
    mask = [True, True, False]  # 1ª e 2ª linhas (ordem), NÃO a 3ª
    n = pp.attach_product_ids(df, spy, resolve_mask=mask)
    assert _pid_list(df) == ["517816", "900001", None]
    assert n == 2
    assert [c[2] for c in spy.calls] == ["193"]  # só a 2ª linha (número 193)


# ─── end-to-end: DH casa via productId resolvido (linha pokemontcg) ──────────
def _raw_for_md():
    return pd.DataFrame({
        "Card Name": ["Plusle"],
        "Nº": [193],
        "Set": ["Paradox Rift (par)"],
        "Rarity": ["Double Rare"],
        "Condição": ["NM"],
        "Variant": ["reverseHolofoil"],
        "Qtd": [3],
        "LIVE R$ (real)": [120.0],
        "TCG Market (BRL)": [240.0],
        "TCG Market (USD)": [44.0],
        "Net Margin % REAL": [0.50],
        "Lucro R$ REAL": [120.0],
        "Validation Status": ["VALIDATED_REAL"],
        "Link CardTrader": ["https://www.cardtrader.com/cards/111"],
        # redirect pokemontcg (sem productId) — só o resolver faz casar
        "Link TCG": ["https://prices.pokemontcg.io/tcgplayer/sv4-193"],
    })


def test_delivery_resolve_mask_uses_deals_when_present():
    """Com COMPRA/REVISAR, a máscara de resolução = exatamente os deals."""
    raw = pd.DataFrame({
        "Card Name": ["A", "B", "C"], "Nº": [1, 2, 3],
        "Set": ["X (x)"] * 3, "Rarity": ["Double Rare"] * 3, "Condição": ["NM"] * 3,
        "Qtd": [1, 1, 1], "LIVE R$ (real)": [100, 100, 100],
        "TCG Market (BRL)": [200, 110, 105], "TCG Market (USD)": [40, 22, 21],
        "Net Margin % REAL": [0.50, 0.05, 0.03],  # só a 1ª é deal
        "Lucro R$ REAL": [100, 10, 5], "Validation Status": ["VALIDATED_REAL"] * 3,
        "Link CardTrader": ["c"] * 3, "Link TCG": ["t"] * 3,
    })
    cfg = pp.DecisionConfig()
    df = pp.enrich_df(raw, hub_fee_rate=cfg.hub_fee_rate)
    mask = list(pp._delivery_resolve_mask(df, cfg, top_md=50))
    assert mask == [True, False, False]  # só o deal


def test_delivery_resolve_mask_near_miss_covers_topN_by_margin():
    """Sem nenhum deal (near-miss), a máscara cobre os top_md por margem — as
    MESMAS linhas que a entrega markdown mostra. Sem isto, o resolver rodaria em
    ZERO linhas e a tabela near-miss perderia a coluna DH (regressão do gating)."""
    raw = pd.DataFrame({
        "Card Name": ["A", "B", "C"], "Nº": [1, 2, 3],
        "Set": ["X (x)"] * 3, "Rarity": ["Double Rare"] * 3, "Condição": ["NM"] * 3,
        "Qtd": [1, 1, 1], "LIVE R$ (real)": [100, 100, 100],
        "TCG Market (BRL)": [118, 112, 105], "TCG Market (USD)": [23, 22, 21],
        "Net Margin % REAL": [0.18, 0.12, 0.05],  # TODAS NÃO (< 0.20)
        "Lucro R$ REAL": [18, 12, 5], "Validation Status": ["VALIDATED_REAL"] * 3,
        "Link CardTrader": ["c"] * 3, "Link TCG": ["t"] * 3,
    })
    cfg = pp.DecisionConfig()
    df = pp.enrich_df(raw, hub_fee_rate=cfg.hub_fee_rate)
    mask = list(pp._delivery_resolve_mask(df, cfg, top_md=2))
    assert mask == [True, True, False]  # top-2 por margem (0.18, 0.12), não a 0.05


def test_dh_binds_on_pokemontcg_row_via_resolved_pid():
    cfg = pp.DecisionConfig()
    df = pp.enrich_df(_raw_for_md(), hub_fee_rate=cfg.hub_fee_rate)
    spy = _SpyResolver({"193": "900001"})
    pp.attach_product_ids(df, spy)
    signals = {"900001": {"tcg_product_id": "900001", "dh_score": 73,
                          "signals": {"forecast_dir": "buy"}}}
    matched = dh.attach_scores_df(df, signals,
                                  url_col="link_tcg", pid_col="tcg_product_id")
    assert matched == 1
    md = pp.build_delivery_markdown(df, cfg, fx_usd_brl=5.0, show_dh=True)
    plus_line = [l for l in md.splitlines() if "Plusle" in l][0]
    assert "| 73 |" in plus_line                       # DH casou via resolver
    assert "[oferta](" in plus_line and "[TCG](" in plus_line  # 2 links intactos


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
