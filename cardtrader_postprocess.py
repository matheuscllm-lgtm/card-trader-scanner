"""CardTrader Postprocess v1.4 — math corrigida + Hub fee homogeneo + sets atualizados.

Mudancas v1.4 (2026-05-12, auditoria pos-fixes do scanner):
- P-C1 fix: gross_margin agora usa convencao de MARGEM (lucro/TCG), nao markup
  (lucro/CT). Era bug semantico — output exibia "Margem TCG %" mas calculava markup.
- P-C2 fix: custo final = preco CT * 1.06 (Hub fee 6% da CardTrader, default).
  FRETE NAO ENTRA NA MATH — modelo operacional real do Matheus: cartas compradas
  ficam no deposito Hub da CT na Europa, acumulam ~100 unidades, e so entao
  sao enviadas pro Brasil em consolidacao unica. O frete daquele envio dilui
  entre todas as cartas (R$0.30-0.50/carta) e fica negligenciavel per-listing.
  Logo: preco final pago = preco CT * 1.06, sem deducao de frete.
- P-H1 fix: markup_tier match agora usa substring (in) em vez de exato (==).
  Antes: scanner produzia "hub (+6%)" mas postprocess buscava "hub" exato → falhava.
- P-H2 fix: status anomalous agora reconhece "price_changed" (string real do scanner).
- P-M1 fix: PRODUCTIVE_SETS agora inclui asc, meg, pfl (sets recentes 2026).
- IMPORTANTE: bucket thresholds (0.30/0.35/0.40) sao NOMINAIS — com fix P-C1, agora
  representam true margin (mais strict que antes que era markup). Retunar se
  output ficar magro demais. Em 29/04 (v1.3) com markup 30% passavam ~5 deals;
  com margem 30% v1.4 a barra é ~43% markup equivalente.

Mudancas v1.3 (2026-04-29 noite, feedback Elizandra):
- Iconicidade em 3 tiers: S (mass appeal +25), A (collectors +15), B (regional +8)
- Raridade chase em 3 niveis: top (SAR/SIR/IR +25), mid (ALT/FA/TG +15), modest (holo +5)
- Snapshot meta competitivo (+5 pra Pokemon meta atual)
- Sets categorizados: anniversary +20, productive +5, maturing 0, dead -15
- Coluna 'Notas Fund.' detalha quais fatores contribuiram

LIMITACOES (TODO futuro - requer integracoes externas):
- Pop report (PSA 10) - escassez certificada
- Historico de preco TCGPlayer market history
- Meta competitivo dinamico (snapshot expira ~jul/26)
"""
from __future__ import annotations
import argparse, sys
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

@dataclass
class BucketConfig:
    name: str; label: str
    min_gross_margin: float; min_net_margin: float; min_profit_brl: float
    sets_expected: list[str] = field(default_factory=list)

BUCKETS: dict[str, BucketConfig] = {
    "core": BucketConfig("core", "CORE / PRODUCTIVE", 0.30, 0.20, 25.0,
                          ["sfa","scr","ssp","dri","blk","jtg","twm","tef"]),
    "hype": BucketConfig("hype", "HYPE / NEW SET", 0.35, 0.25, 40.0, ["pre","ascended-heroes"]),
    "dead": BucketConfig("dead", "DEAD MARKET / REVALIDATION", 0.40, 0.30, 50.0,
                          ["crz","lorg","sit","fst","evs","brs","astr","pal","par"]),
}

COLUMN_ALIASES: dict[str, list[str]] = {
    "card_name": ["card_name","name","card","Card","Name","Card Name","Carta"],
    "card_number": ["card_number","number","Number","Card Number","card_no","No","Numero"],
    "set_code": ["set_code","set","Set","expansion","Expansion","set_id"],
    "rarity": ["rarity","Rarity","Raridade"],
    "variant": ["variant","Variant","version","Version","foil","Foil","Variante"],
    "condition": ["condition","Condition","cond","Cond","Condicao"],
    "language": ["language","Language","lang","Lang","Idioma"],
    "seller": ["seller","Seller","seller_name"],
    "seller_country": ["seller_country","country","Country"],
    "scan_brl": ["scan_brl","Scan R$","Scan BRL","scan_price_brl","Scan R$ (raw)"],
    "live_brl": ["live_brl","LIVE R$","Live BRL","live_price_brl","LIVE R$ (real)"],
    "markup_pct": ["markup_pct","Markup %","markup_percent","markup"],
    "markup_tier": ["markup_tier","Markup Tier","tier"],
    "validation_status": ["validation_status","Validation Status","valid_status","status"],
    "reference_price_brl": ["reference_price_brl","Reference R$","tcg_price_brl",
                            "TCG R$","TCG Market (BRL)","TCG Market BRL"],
    "gross_margin_real": ["gross_margin_real","Margem REAL","Margem % REAL"],
    "net_margin_real": ["net_margin_real","Net REAL","Net Margin % REAL","Net Margin % REAL c/ frete"],
    "profit_brl_real": ["profit_brl_real","Lucro REAL","Lucro R$ REAL"],
    "link_ct": ["link_ct","Link CT","Link","URL CT","ct_url","cardtrader_url"],
    "link_tcg": ["link_tcg","URL TCGPlayer","TCG URL","tcg_url","tcgplayer_url"],
    "blueprint_id": ["blueprint_id","Blueprint ID","blueprint","bp_id"],
    "quantity": ["quantity","Quantity","qty","estoque","Estoque"],
}

def detect_column(df, logical_name):
    aliases = COLUMN_ALIASES.get(logical_name, [logical_name])
    cols_lower = {c.lower().strip(): c for c in df.columns}
    for alias in aliases:
        if alias in df.columns: return alias
        if alias.lower() in cols_lower: return cols_lower[alias.lower()]
    return None

def normalize_columns(df, source_label):
    rename_map = {}
    missing = []
    critical = ["card_name","live_brl","reference_price_brl"]
    for logical in COLUMN_ALIASES.keys():
        actual = detect_column(df, logical)
        if actual: rename_map[actual] = logical
        elif logical in critical: missing.append(logical)
    if missing:
        print(f"[WARN] [{source_label}] Colunas criticas ausentes: {missing}")
        if "live_brl" in missing:
            scan_col = detect_column(df, "scan_brl")
            if scan_col:
                print(f"       Fallback: '{scan_col}' como live_brl")
                rename_map[scan_col] = "live_brl"
                missing.remove("live_brl")
    if "live_brl" in missing or "reference_price_brl" in missing:
        raise ValueError(f"[{source_label}] Colunas criticas ausentes: {missing}")
    return df.rename(columns=rename_map)

def apply_hub_fee(df, hub_fee_rate):
    """Recalcula margens com Hub fee homogeneo (default 6%) sobre live_brl.

    Modelo operacional (2026-05-12, confirmado por Matheus):
    O comprador NAO paga frete per-listing. As cartas adquiridas ficam no
    deposito do Hub CardTrader na Europa, acumulam ~100 unidades, e so
    entao sao consolidadas e enviadas pro Brasil num unico envio. O frete
    desse envio (~R$30-50 total) se dilui entre as 100+ cartas, dando
    R$0.30-0.50 por carta — desprezivel. Portanto:

        custo final por carta = preco CT * 1.06  (Hub fee da CardTrader)

    Sem deducao de frete. Sem variabilidade FX EUR. Math simples e
    operacionalmente exata para o fluxo de consolidacao.

    v1.4 fix (2026-05-12):
    - P-C1: gross_margin / net_margin_after_hub agora usam convencao de
      MARGEM (lucro / TCG), nao markup (lucro / CT). Alinhado com scanner.
    - P-C2: custo final = live_brl * (1 + hub_fee_rate). Frete nao modelado
      (justificativa acima).
    """
    df = df.copy()
    df["live_brl"] = pd.to_numeric(df["live_brl"], errors="coerce")
    df["reference_price_brl"] = pd.to_numeric(df["reference_price_brl"], errors="coerce")
    df["hub_fee_brl"] = df["live_brl"] * hub_fee_rate
    df["effective_cost_brl"] = df["live_brl"] + df["hub_fee_brl"]
    df["gross_profit_brl"] = df["reference_price_brl"] - df["live_brl"]
    df["net_profit_after_hub_brl"] = df["reference_price_brl"] - df["effective_cost_brl"]
    # P-C1 fix: convencao de margem (divisor = TCG = receita), nao markup (CT = custo)
    df["gross_margin"] = df["gross_profit_brl"] / df["reference_price_brl"]
    df["net_margin_after_hub"] = df["net_profit_after_hub_brl"] / df["reference_price_brl"]
    df["hub_fee_impact_pct"] = (df["hub_fee_brl"] / df["live_brl"]) * 100
    return df

# ---- Analise Fundamentalista v1.3 (3 tiers iconicidade + meta + raridade granular) -----

# Snapshot do meta competitivo - atualizar a cada ~3 meses
META_SNAPSHOT_DATE = "2026-04-29"

# Tier S: mass appeal global (forte hold)
ICONIC_S_TIER = {
    "charizard","pikachu","mewtwo","mew","rayquaza","lugia","ho-oh",
    "eevee","vaporeon","jolteon","flareon","espeon","umbreon","leafeon","glaceon","sylveon",
}
# Tier A: forte demanda colecionadores
ICONIC_A_TIER = {
    "gengar","lucario","garchomp","dragonite","greninja","snorlax","tyranitar",
    "metagross","blastoise","venusaur","gardevoir","gyarados","scizor","absol",
    "lapras","arcanine","alakazam","machamp","ninetales","houndoom","milotic",
    "zoroark","sceptile","blaziken","swampert",
}
# Tier B: regional/situacional
ICONIC_B_TIER = {
    "magikarp","decidueye","incineroar","primarina","salamence","aggron",
    "ampharos","lopunny","mimikyu","celebi","jirachi","manaphy","shaymin",
    "darkrai","cresselia","keldeo","meloetta","genesect","diancie","hoopa",
    "volcanion","marshadow","zeraora","zacian","zamazenta","calyrex",
}

# Snapshot meta competitivo (validade ~3m)
META_RELEVANT = {
    "charizard","gardevoir","roaring moon","iron hands","miraidon","lugia",
    "giratina","raging bolt","arceus","palkia","dragapult","gholdengo",
    "iron crown","walking wake",
}

# Top chase: raridades mais escassas/valiosas
TOP_CHASE_PATTERNS = [
    "sar","sir","iri","gar","illustration rare","gold star",
    "secret rare alt","rainbow rare","crown rare","cr",
]
# Mid chase: chase decente, mais comum que top
MID_CHASE_PATTERNS = [
    "alt","alternate","full art","fa","hyper rare","ur","ultra rare",
    "trainer gallery","tg","amazing rare","ar",
    "super rare","sr",  # SR = chase em sets modernos (ex SR/EX/V em scr/sfa)
    "double rare","ex","vmax","vstar","v-union","radiant rare",
]
# Modest: foil basico
MODEST_PATTERNS = ["holo rare","reverse holo","reverse foil","holofoil"]

# Sets por categoria (atualizar conforme novos sets saem)
# P-M1 fix (2026-05-12): asc, meg, pfl adicionados a PRODUCTIVE_SETS (sets
# recentes 2026, dentro da janela 6-12m).
ANNIVERSARY_SETS = {"mew","cel","paf","fab","pre"}        # +20
PRODUCTIVE_SETS = {"sfa","scr","ssp","dri","blk","jtg","asc","meg","pfl"}  # +5 (janela 6-12m)
MATURING_SETS = {"twm","tef","par","obf"}                   # +0 (12-24m)
DEAD_SETS = {"evs","brs","astr","lorg","sit","pkmgo","svi","pal","fst"}  # -15

# Aliases para retrocompatibilidade (codigo legacy)
ICONIC_POKEMON = ICONIC_S_TIER | ICONIC_A_TIER | ICONIC_B_TIER
ICONIC_SETS = ANNIVERSARY_SETS | {"crz"}
DEAD_MARKET_SETS = DEAD_SETS
PRODUCTIVE_WINDOW_SETS = PRODUCTIVE_SETS | MATURING_SETS
CHASE_RARITIES_PATTERNS = TOP_CHASE_PATTERNS + MID_CHASE_PATTERNS


def _extract_set_code(raw):
    """Extrai codigo CT do set, mesmo se vier como 'Stellar Crown (scr)'.
    Tenta primeiro extrair texto entre parenteses; senao usa string toda."""
    s = str(raw).lower().strip()
    if "(" in s and ")" in s:
        inner = s[s.rfind("(")+1 : s.rfind(")")].strip()
        if inner:
            return inner
    return s


def fundamental_analysis(row):
    """Heuristica v1.3 - 3 tiers iconicidade + meta + raridade granular."""
    score = 50
    notes = []
    name = str(row.get("card_name","")).lower()
    sc = _extract_set_code(row.get("set_code",""))
    rar = str(row.get("rarity","")).lower().strip()
    var = str(row.get("variant","")).lower().strip()

    # 1. Iconicidade (S > A > B)
    if any(p in name for p in ICONIC_S_TIER):
        score += 25; notes.append("S-tier")
    elif any(p in name for p in ICONIC_A_TIER):
        score += 15; notes.append("A-tier")
    elif any(p in name for p in ICONIC_B_TIER):
        score += 8; notes.append("B-tier")

    # 2. Set
    if sc in ANNIVERSARY_SETS:
        score += 20; notes.append("set anniversary")
    elif sc in PRODUCTIVE_SETS:
        score += 5; notes.append("set produtivo 6-12m")
    elif sc in MATURING_SETS:
        notes.append("set maduro 12-24m")
    elif sc in DEAD_SETS:
        score -= 15; notes.append("set morto >36m")

    # 3. Raridade chase (top > mid > modest)
    rt = f"{rar} {var}".strip()
    if any(c in rt for c in TOP_CHASE_PATTERNS):
        score += 25; notes.append("top chase")
    elif any(c in rt for c in MID_CHASE_PATTERNS):
        score += 15; notes.append("mid chase")
    elif any(c in rt for c in MODEST_PATTERNS):
        score += 5; notes.append("modest holo")
    elif rar in ("c","common","comum","u","uncommon","incomum"):
        score -= 10; notes.append("raridade comum")

    # 4. Meta competitivo (snapshot 2026-04-29)
    if any(m in name for m in META_RELEVANT):
        score += 5; notes.append("meta atual")

    score = max(0, min(100, score))

    if score >= 80: label = "HIGH"
    elif score >= 60: label = "MEDIUM"
    elif score >= 40: label = "LOW"
    else: label = "SPECULATIVE"

    note = "; ".join(notes) if notes else "sem flags"
    return score, note, label

def classify_row(row, bucket):
    gm = row.get("gross_margin",0); nm = row.get("net_margin_after_hub",0)
    profit = row.get("net_profit_after_hub_brl",0)
    val_status = str(row.get("validation_status","")).lower()
    cond = str(row.get("condition","")).lower()
    lang = str(row.get("language","")).lower()
    variant = str(row.get("variant","")).lower()
    markup_tier = str(row.get("markup_tier","")).lower()
    if pd.isna(gm) or pd.isna(nm) or pd.isna(profit):
        return ("REJECT","insufficient_data","Dados ausentes",0)
    if gm < bucket.min_gross_margin:
        return ("REJECT","low_gross_margin",f"gross={gm:.1%} < {bucket.min_gross_margin:.0%}",5)
    if nm < bucket.min_net_margin:
        return ("REJECT","low_net_margin_after_hub",f"net={nm:.1%} < {bucket.min_net_margin:.0%}",10)
    if profit < bucket.min_profit_brl:
        return ("REJECT","low_absolute_profit",f"R${profit:.0f} < R${bucket.min_profit_brl:.0f}",15)
    if val_status == "stale":
        return ("REJECT","reference_price_unreliable","STALE",10)
    # P-H2 fix (2026-05-12): scanner emite "price_changed" pra markup >45%
    # (era "anomalo" so na imaginacao). Mantemos os 3 strings antigos pra
    # retrocompatibilidade caso outras fontes alimentem o postprocess.
    if val_status in ("price_changed","anomalo","anomalous","anomalous_markup"):
        return ("MANUAL REVIEW","anomalous_markup","Markup anomalo / preco mudou",30)
    if cond and cond not in ("nm","near mint","near_mint","ex","excellent","near-mint"):
        return ("REJECT","condition_mismatch",f"Cond '{cond}' baixa",5)
    if lang and lang in ("pt","portuguese","português","jp","japanese","japonês"):
        return ("MANUAL REVIEW","language_liquidity_concern",f"Idioma '{lang}'",40)
    if any(t in variant for t in ["trainer gallery","tg ","alt art","alternate","full art"]):
        return ("MANUAL REVIEW","variant_ambiguous",f"Variant '{variant}'",50)
    # P-H1 fix (2026-05-12): scanner emite strings tipo "Hub (+6%)" / "non-VAT (+20%)" /
    # "Alto markup (+30%)" / "Real (sem markup)". Match exato falhava — usar substring.
    if "non-vat" in markup_tier:
        risk = "Seller non-VAT (+20%). Confirmar Hub-compatible."
    elif "hub" in markup_tier:
        risk = "Seller Hub (+6%). OK."
    elif "alto markup" in markup_tier:
        risk = "Seller alto markup (30-45%). Avaliar caso, pode ser tier non-Hub legitimo."
    elif "real" in markup_tier or "sem markup" in markup_tier:
        risk = "Seller sem markup. Preco final ~ preco scan."
    else:
        risk = f"Tier: {markup_tier or 'desc'}"
    if bucket.name == "hype":
        return ("MANUAL REVIEW","hype_market_unstable","HYPE: confirmar liquidez. "+risk,65)
    if bucket.name == "dead":
        return ("MANUAL REVIEW","dead_market_needs_thesis","DEAD: tese clara. "+risk,60)
    return ("BUY NOW","passed_all_filters",risk, 90 if markup_tier=="hub" else 75)

def classify_dataframe(df, bucket):
    df = df.copy()
    results = df.apply(lambda r: classify_row(r, bucket), axis=1)
    df["action"] = [r[0] for r in results]
    df["reason"] = [r[1] for r in results]
    df["risk_note"] = [r[2] for r in results]
    df["confidence_score"] = [r[3] for r in results]
    df["bucket"] = bucket.label
    fund = df.apply(lambda r: fundamental_analysis(r), axis=1)
    df["fundamental_score"] = [r[0] for r in fund]
    df["fundamental_note"] = [r[1] for r in fund]
    df["long_term"] = [r[2] for r in fund]
    return df

ACTION_ORDER = ["BUY NOW","WATCH","MANUAL REVIEW","REJECT"]
ACTION_FILL = {
    "BUY NOW": PatternFill("solid", fgColor="C6EFCE"),
    "WATCH": PatternFill("solid", fgColor="FFEB9C"),
    "MANUAL REVIEW": PatternFill("solid", fgColor="FFD966"),
    "REJECT": PatternFill("solid", fgColor="F4CCCC"),
}
LONG_TERM_FILL = {
    "HIGH": PatternFill("solid", fgColor="A9D08E"),
    "MEDIUM": PatternFill("solid", fgColor="FFE699"),
    "LOW": PatternFill("solid", fgColor="F8CBAD"),
    "SPECULATIVE": PatternFill("solid", fgColor="F4B084"),
}

COLUMN_DISPLAY_NAMES = {
    "action":"Acao","bucket":"Bucket","set_code":"Set","card_name":"Carta","card_number":"No",
    "rarity":"Raridade","variant":"Variante","condition":"Condicao","language":"Idioma",
    "seller":"Seller","seller_country":"Pais","live_brl":"Preco CT (R$)",
    "reference_price_brl":"TCG Market (R$)","gross_margin":"Margem TCG %",
    "hub_fee_brl":"Hub Fee (R$)","hub_fee_impact_pct":"Hub Fee Impact %",
    "net_margin_after_hub":"Margem Liq %","net_profit_after_hub_brl":"Lucro Liq (R$)",
    "fundamental_score":"Score Fund.","fundamental_note":"Notas Fund.","long_term":"Long Term",
    "reason":"Motivo","risk_note":"Nota Risco","confidence_score":"Confianca",
    "link_ct":"Link CT","link_tcg":"Link TCGPlayer","blueprint_id":"Blueprint ID","quantity":"Qtd Estoque",
}

COLUMN_DISPLAY_ORDER = ["action","bucket","set_code","card_name","card_number","rarity",
    "variant","condition","language","seller","seller_country","live_brl","reference_price_brl",
    "gross_margin","hub_fee_brl","hub_fee_impact_pct","net_margin_after_hub",
    "net_profit_after_hub_brl","fundamental_score","long_term","fundamental_note",
    "reason","risk_note","confidence_score","link_ct","link_tcg","blueprint_id","quantity"]

COLUMNS_TO_HIDE_IN_REPORT = {"scan_brl","markup_pct","markup_tier","validation_status",
    "gross_margin_real","net_margin_real","profit_brl_real","action_order","gross_profit_brl"}

COLUMN_NAME_PATTERNS_TO_HIDE = ["frete","shipping","freight","foil","is_foil",
    "hub_only","is_hub","hub flag","tipo seller"]

def select_report_columns(df):
    canonical = [c for c in COLUMN_DISPLAY_ORDER if c in df.columns]
    cs = set(canonical)
    extras = []
    for col in df.columns:
        if col in cs or col in COLUMNS_TO_HIDE_IN_REPORT: continue
        cl = str(col).lower()
        if any(p.lower() in cl for p in COLUMN_NAME_PATTERNS_TO_HIDE): continue
        extras.append(col)
    return canonical + extras

def rename_columns_for_display(df):
    rm = {k:v for k,v in COLUMN_DISPLAY_NAMES.items() if k in df.columns}
    return df.rename(columns=rm)

def build_executive_summary(buckets_data, hub_fee_rate):
    rows = []; total_listings=0; total_approved=0; total_profit=0.0
    for bk, df in buckets_data.items():
        b = BUCKETS[bk]; n = len(df)
        nbuy = (df["action"]=="BUY NOW").sum()
        nw = (df["action"]=="WATCH").sum()
        nr = (df["action"]=="MANUAL REVIEW").sum()
        nrj = (df["action"]=="REJECT").sum()
        prof = df.loc[df["action"]=="BUY NOW","net_profit_after_hub_brl"].sum()
        total_listings += n; total_approved += nbuy; total_profit += prof
        rows.append({"Bucket":b.label,"Listings escaneados":n,"BUY NOW":nbuy,"WATCH":nw,
            "MANUAL REVIEW":nr,"REJECT":nrj,
            "Aprovacao %":f"{(nbuy/n*100) if n else 0:.1f}%",
            "Falsos Positivos %":f"{(nrj/n*100) if n else 0:.1f}%",
            "Lucro Liq Pot. (R$)":f"R$ {prof:,.0f}",
            "Filtros":f"gross>={b.min_gross_margin:.0%} | net>={b.min_net_margin:.0%} | lucro>=R${b.min_profit_brl:.0f}"})
    rows.append({"Bucket":"TOTAL","Listings escaneados":total_listings,"BUY NOW":total_approved,
        "WATCH":sum((d["action"]=="WATCH").sum() for d in buckets_data.values()),
        "MANUAL REVIEW":sum((d["action"]=="MANUAL REVIEW").sum() for d in buckets_data.values()),
        "REJECT":sum((d["action"]=="REJECT").sum() for d in buckets_data.values()),
        "Aprovacao %":f"{(total_approved/total_listings*100) if total_listings else 0:.1f}%",
        "Falsos Positivos %":"-","Lucro Liq Pot. (R$)":f"R$ {total_profit:,.0f}",
        "Filtros":f"Hub fee {hub_fee_rate:.0%}"})
    return pd.DataFrame(rows)

def build_quick_decision(buckets_data):
    parts = [df[df["action"]=="BUY NOW"] for df in buckets_data.values() if not df.empty]
    if not parts:
        return pd.DataFrame(columns=["Bucket","Set","Carta","No","Preco CT (R$)",
            "TCG Market (R$)","Margem TCG %","Lucro Liq (R$)","Long Term","Score Fund.","Notas Fund.","Link CT"])
    all_buy = pd.concat(parts, ignore_index=True)
    if all_buy.empty:
        return pd.DataFrame(columns=["Bucket","Set","Carta","No","Preco CT (R$)",
            "TCG Market (R$)","Margem TCG %","Lucro Liq (R$)","Long Term","Score Fund.","Notas Fund.","Link CT"])
    all_buy = all_buy.sort_values("net_profit_after_hub_brl", ascending=False)
    quick = pd.DataFrame()
    quick["Bucket"] = all_buy["bucket"].values
    quick["Set"] = all_buy["set_code"].values if "set_code" in all_buy.columns else ""
    quick["Carta"] = all_buy["card_name"].values if "card_name" in all_buy.columns else ""
    quick["No"] = all_buy["card_number"].values if "card_number" in all_buy.columns else ""
    quick["Preco CT (R$)"] = [f"R$ {v:,.2f}" for v in all_buy["live_brl"].values]
    quick["TCG Market (R$)"] = [f"R$ {v:,.2f}" for v in all_buy["reference_price_brl"].values]
    quick["Margem TCG %"] = [f"{v*100:.1f}%" for v in all_buy["gross_margin"].values]
    quick["Lucro Liq (R$)"] = [f"R$ {v:,.2f}" for v in all_buy["net_profit_after_hub_brl"].values]
    quick["Long Term"] = all_buy["long_term"].values
    quick["Score Fund."] = all_buy["fundamental_score"].values
    quick["Notas Fund."] = all_buy["fundamental_note"].values
    link_col = detect_column(all_buy, "link_ct")
    quick["Link CT"] = all_buy[link_col].values if link_col else ""
    return quick

def style_sheet(ws, df, action_col=None, long_term_col=None):
    for ci in range(1, len(df.columns)+1):
        cell = ws.cell(row=1, column=ci)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="305496")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"
    if action_col and action_col in df.columns:
        ci = list(df.columns).index(action_col)+1
        for ri in range(2, len(df)+2):
            cell = ws.cell(row=ri, column=ci)
            if cell.value in ACTION_FILL:
                cell.fill = ACTION_FILL[cell.value]; cell.font = Font(bold=True)
    if long_term_col and long_term_col in df.columns:
        ci = list(df.columns).index(long_term_col)+1
        for ri in range(2, len(df)+2):
            cell = ws.cell(row=ri, column=ci)
            if cell.value in LONG_TERM_FILL:
                cell.fill = LONG_TERM_FILL[cell.value]; cell.font = Font(bold=True)
    for ci, cn in enumerate(df.columns, 1):
        col_data = df.iloc[:, ci-1].head(50)
        try:
            vals = [str(v) for v in col_data.tolist()]
        except AttributeError:
            vals = [str(col_data.iloc[i]) for i in range(min(50, len(col_data)))]
        ml = max([len(str(cn))] + [len(v) for v in vals]) if vals else len(str(cn))
        ws.column_dimensions[get_column_letter(ci)].width = min(ml+2, 50)

def write_sheet(wb, name, df, action_col=None, lt_col=None):
    ws = wb.create_sheet(name)
    if df.empty:
        ws.cell(row=1, column=1, value="Vazio.")
        return
    for ri, row in enumerate([df.columns.tolist()] + df.values.tolist(), 1):
        for ci, val in enumerate(row, 1):
            ws.cell(row=ri, column=ci, value=val)
    style_sheet(ws, df, action_col=action_col, long_term_col=lt_col)

def write_report(buckets_data, hub_fee_rate, output_path):
    wb = Workbook(); wb.remove(wb.active)
    write_sheet(wb, "Decisao Rapida", build_quick_decision(buckets_data), lt_col="Long Term")
    write_sheet(wb, "A. Executive Summary", build_executive_summary(buckets_data, hub_fee_rate))
    for bk, df in buckets_data.items():
        b = BUCKETS[bk]; bs = b.name.upper()
        for action in ACTION_ORDER:
            sub = df[df["action"]==action].copy()
            if sub.empty: continue
            sub = sub.sort_values("net_profit_after_hub_brl", ascending=False)
            cols = select_report_columns(sub)
            sub = rename_columns_for_display(sub[cols])
            write_sheet(wb, f"{bs} - {action}"[:31], sub, action_col="Acao", lt_col="Long Term")
    parts_buy = [df[df["action"]=="BUY NOW"] for df in buckets_data.values() if not df.empty]
    if parts_buy:
        all_a = pd.concat(parts_buy, ignore_index=True)
        if not all_a.empty:
            all_a = all_a.sort_values("net_profit_after_hub_brl", ascending=False)
            cols = select_report_columns(all_a)
            all_a = rename_columns_for_display(all_a[cols])
            write_sheet(wb, "C. Top Approved Deals", all_a, action_col="Acao", lt_col="Long Term")
    parts_rj = [df[df["action"]=="REJECT"] for df in buckets_data.values() if not df.empty]
    if parts_rj:
        all_rj = pd.concat(parts_rj, ignore_index=True)
        if not all_rj.empty:
            rs = (all_rj.groupby(["bucket","reason"]).size().reset_index(name="count")
                  .sort_values("count", ascending=False))
            rs = rs.rename(columns={"bucket":"Bucket","reason":"Motivo","count":"Qtd"})
            write_sheet(wb, "D. False Positives", rs)
    parts_all = [df for df in buckets_data.values() if not df.empty]
    if parts_all:
        all_data = pd.concat(parts_all, ignore_index=True)
        all_data["action_order"] = all_data["action"].map({a:i for i,a in enumerate(ACTION_ORDER)})
        all_data = all_data.sort_values(["action_order","net_profit_after_hub_brl"],
                                          ascending=[True,False])
        cols = select_report_columns(all_data)
        all_data = rename_columns_for_display(all_data[cols])
        write_sheet(wb, "E. Final Action List", all_data, action_col="Acao", lt_col="Long Term")
    wb.save(output_path)

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--core", type=Path, required=True)
    p.add_argument("--hype", type=Path, required=True)
    p.add_argument("--dead", type=Path, required=True)
    p.add_argument("--hub-fee", type=float, default=0.06,
                   help="Hub fee da CardTrader sobre preco CT (default 6%%). "
                        "Frete nao modelado: cartas consolidadas no deposito "
                        "CT (~100 cards) tornam frete per-card negligenciavel. v1.4.")
    p.add_argument("--output", type=Path, required=True)
    return p.parse_args()

def load_bucket(path, bucket_key):
    if not path.exists(): raise FileNotFoundError(f"{path}")
    df = pd.read_excel(path)
    print(f"[{bucket_key.upper()}] {path.name}: {len(df)} linhas, {len(df.columns)} colunas")
    return normalize_columns(df, source_label=bucket_key)

def main():
    args = parse_args()
    print(f"CardTrader Postprocess v1.4 | Surcharge = {args.hub_fee:.0%} | Meta snapshot {META_SNAPSHOT_DATE}")
    print("-"*70)
    bd = {}
    for bk, path in [("core",args.core),("hype",args.hype),("dead",args.dead)]:
        b = BUCKETS[bk]
        try: df = load_bucket(path, bk)
        except (FileNotFoundError, ValueError) as e:
            print(f"[ERRO] {bk}: {e}"); return 1
        df = apply_hub_fee(df, args.hub_fee)
        df = classify_dataframe(df, b)
        nb = (df["action"]=="BUY NOW").sum()
        nw = (df["action"]=="WATCH").sum()
        nr = (df["action"]=="MANUAL REVIEW").sum()
        nrj = (df["action"]=="REJECT").sum()
        pr = df.loc[df["action"]=="BUY NOW","net_profit_after_hub_brl"].sum()
        if nb > 0:
            ltd = df[df["action"]=="BUY NOW"]["long_term"].value_counts().to_dict()
            lts = ", ".join([f"{k}:{v}" for k,v in ltd.items()])
        else: lts = "-"
        print(f"  BUY NOW: {nb} | WATCH: {nw} | REVIEW: {nr} | REJECT: {nrj}")
        print(f"  Lucro liquido potencial: R$ {pr:,.2f}")
        print(f"  Long-term mix: {lts}")
        bd[bk] = df
    print("-"*70)
    print(f"Gerando relatorio: {args.output}")
    write_report(bd, args.hub_fee, args.output)
    print(f"OK: {args.output}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
