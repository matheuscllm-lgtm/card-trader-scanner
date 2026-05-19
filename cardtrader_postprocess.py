"""CardTrader Postprocess v2.0 — núcleo simplificado (operador 2026-05-16).

Mudancas vs v1.5:
- REMOVE bucket CORE/HYPE/DEAD classification
- REMOVE fundamental_analysis original (iconicidade/chase/meta heuristicas subjetivas)
- REMOVE long_term tier
- REMOVE coluna "Acao" (substituida por Decisao mecanica)
- ADICIONA Chase Tier (TOP/MID/MODEST/BULK) baseado em rarity oficial PokemonTCG
- ADICIONA Fundamental Score (0-100) derivado de metricas OBJETIVAS (chase + margin + lucro + validation)
- ADICIONA Decisao (COMPRA/REVISAR/NAO) via regra MECANICA (nao opiniao Claude)
- ADICIONA Porque (1 linha factual)
- REDUZ de 10 sheets pra 3 (Deals, All Listings, Summary)
- MANTEM: Hub fee 6% paridade, TG## auto-filter, hyperlinks, alias fixes
- MANTEM: ct_margin_formula (sem shipping; custo = preco_pagina × 1.06)

v2.1 (bug-hunt 2026-05-17):
- #2 Defensive recompute de net_margin/lucro_liq via fórmula 1.06 quando o
  input carrega `live_brl` + `reference_price_brl` válidos. Compara com o
  net_margin do input — drift > 0.5pp → WARN + usa recomputado. Coluna
  `margin_source` ("input" | "recomputed") preserva auditoria.
- #3 Força UTF-8 no stdout/encoding pra eliminar mojibake em headers
  (`Decis�o` → `Decisão`) quando invocado fora do wrapper PS sem
  PYTHONIOENCODING=utf-8. openpyxl pega encoding do interpreter locale.
- #4 Summary separa `Total listings escaneados` (input completo) de
  `Total deals exportados` (COMPRA + REVISAR). Antes o label estava
  errado — número era de deals, não listings totais.

v2.3 Layer 5 (bug-hunt 2026-05-18):
- ALPHA_SUFFIX_RE detecta `153a`, `022a`, `156b` no collector number.
  Tipicamente promo/League variant (1st/2nd/3rd/4th Place ou Prerelease)
  cega pra pokemontcg.io. classify_decision retorna REVISAR antes de
  qualquer outro check.
- Pareado com Scanner v2.8 Layer 4 (foil-aware variant disambiguation
  no provider) — cobre as 2 classes de falsos positivos de variante
  detectados na validação manual do weekly v2.6 (Pichu/Tyranitar e
  Lusamine).

Decisao mecanica (thresholds configuraveis via CLI):
  COMPRA:  net_margin >= 25% AND lucro_liq >= R$50 AND chase_tier in {TOP, MID}
           AND validation_status in {VALIDATED_REAL, VALIDATED_MARKUP}
           AND NOT trainer_gallery_potential_fp
  NAO:     chase_tier == BULK OR net_margin < 20% OR validation_status == STALE
           OR trainer_gallery_potential_fp
  REVISAR: else (zona cinza — margem 20-25% OU chase MODEST com margem alta)

Memorias relevantes respeitadas:
  - ct_margin_formula: frete=0 (Hub depot consolida ~100 cards), custo = preco × 1.06
  - feedback_no_purchase_decisions: Decisao e REGRA mecanica, nao opiniao Claude
  - cardtrader_trainer_gallery_bug: TG## auto-filter mantido
"""
from __future__ import annotations
import argparse, os, re, sys
from dataclasses import dataclass
from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ─── v2.1 fix #3 (bug-hunt 2026-05-17): força UTF-8 no I/O ───────────────────
# openpyxl.Workbook.save() pega encoding do interpreter locale via algum
# caminho interno. Em Windows com locale pt-BR, sys.stdout.encoding default
# é cp1252 → headers UTF-8 são gravados como bytes UTF-8 mas LIDOS como
# latin-1, produzindo mojibake (`Decis�o`, `Pre�o CT`). PYTHONIOENCODING=utf-8
# resolve, mas só quando o invocador seta a var (wrappers PS setam; scripts
# ad-hoc esquecem). Garantia defensiva aqui:
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    # Python <3.7 ou stdout não-reconfigurável (raro). Fallback silencioso.
    pass

# ─── Hub fee canônico (ct_margin_formula): custo = preço_CT × 1.06 ───────────
HUB_FEE_RATE = 0.06

# ─── Trainer Gallery filter (preservado de v1.5) ──────────────────────────────
TRAINER_GALLERY_RE = re.compile(r'^TG\d+', re.IGNORECASE)

# ─── Alpha suffix filter (v2.3 Layer 5 — bug-hunt 2026-05-18) ────────────────
# Cards com collector number `\d+[a-zA-Z]+` (ex `153a`, `022a`, `156b`) são
# tipicamente variantes promo/league cegas pra pokemontcg.io:
#   - "1st Place Pokemon League" / "2nd Place" / "3rd Place" / "4th Place"
#   - Prerelease (alguns sets)
#   - Staff variants (Champion's Festival, World Championships)
# Pokemontcg.io agrega TODAS sob o número-base (ex `153`) com o preço da
# variante mais cara → margem inflada 5-30× quando seller CT está vendendo
# a promo barata. Caso histórico operador: Lusamine sm5/153a — scanner
# pegou main set Lusamine ($160) mas seller CT vende 1st Place ($13.77).
#
# Estratégia: REVISAR forçado (operador valida via Link TCG → variant
# selector visual). NÃO marcar NÃO automático pq alguns alpha suffixes
# legítimos existem em sets vintage (Topps Movie, Black Star Promos
# numerados como `TVR_1a`, etc — fora do escopo CT).
#
# NÃO confundir com TG##: TG## tem letras ANTES do número, então a regex
# `^\d+[a-zA-Z]+` não casa. TG## fica com sua flag separada.
ALPHA_SUFFIX_RE = re.compile(r'^\d+[a-zA-Z]+', re.IGNORECASE)

# ─── Unsupported sets filter (v2.2 Layer 3 bug-hunt 2026-05-18) ──────────────
# Sets onde pokemontcg.io tem cobertura ruim OU os codes do CT divergem de
# forma que mesmo com Layer 1 (strict set match) acabamos pegando o set
# errado. Quando um listing CT vem de um destes sets, qualquer Decisão
# automática vira REVISAR_MANUAL — operador valida preço TCG manual antes
# de comprar.
#
# Lista canônica (operador 2026-05-18 pós-debug weekly v2.6):
#   - Promo/legacy sets sem alias em pokemontcg.io: phs, pplf, pupr, xybsp
#   - World Championship decks (não-tradeable na ptcg.io): wcd2004/06/07
#   - Theme deck exclusives sem reverse map: deckexclusives, xytkn
#   - Pokemon TCG Classic reprint set: clb (matched Team Rocket originals)
#   - McDonald's promo sets: m24
UNSUPPORTED_SETS = {
    "clb", "wcd2004", "wcd2006", "wcd2007", "deckexclusives",
    "xytkn", "m24", "phs", "pplf", "xybsp",
}

def _extract_set_code_from_label(set_label: str | None) -> str:
    """Set label vem como 'Jungle (ju)' ou direto 'ju'. Extrai código entre
    parênteses se presente, senão devolve label normalizado."""
    if not set_label:
        return ""
    s = str(set_label).strip()
    m = re.search(r"\(([^)]+)\)\s*$", s)
    if m:
        return m.group(1).strip().lower()
    return s.lower()

# ─── Chase Tier classification ────────────────────────────────────────────────
# Hierarquia objetiva baseada em PokemonTCG official rarities. Substring-aware
# (case-insensitive) pra tolerar variacoes "Special Illustration Rare" vs "SIR".
CHASE_TIER_PATTERNS = {
    "TOP": [
        "special illustration rare", "sir", "illustration rare",
        "special art rare", "sar", "hyper rare", "ultra hyper rare",
        "secret rare", "rara secreta",
    ],
    "MID": [
        "full art", "alt art", "alternate art", "alternative art",
        "rainbow rare", "gold rare", "trainer gallery", "double rare",
        "rara hiper", "ultra rare",
    ],
    "MODEST": [
        "holo rare", "reverse holo", "reverse foil", "promo",
        "rare holo",
    ],
    "BULK": [
        "common", "comum", "uncommon", "incomum",
    ],
}

def classify_chase_tier(rarity: str | None, card_number: str | None = None,
                         markup_tier: str | None = None) -> str:
    """Classifica chase tier baseado em rarity. Fallback para proxies se rarity
    indisponivel (XLSX raw pre v2.5 do scanner nao persiste rarity)."""
    if rarity:
        r = str(rarity).lower().strip()
        for tier, patterns in CHASE_TIER_PATTERNS.items():
            if any(p in r for p in patterns):
                return tier
        # Rarity present but unmapped → default MODEST (conservative)
        return "MODEST"

    # ── Fallback: proxies quando rarity nao foi capturada pelo scanner ──
    num = str(card_number or "").strip()
    # TG## = Trainer Gallery → MID (mas tb gera flag separado abaixo)
    if TRAINER_GALLERY_RE.match(num):
        return "MID"
    # Supranumerary (numero > total set) é sinal de SIR/SAR — TOP
    if "/" in num:
        try:
            n, total = num.split("/")[:2]
            if int("".join(c for c in n if c.isdigit())) > int("".join(c for c in total if c.isdigit())):
                return "TOP"
        except (ValueError, IndexError):
            pass
    # Markup tier non-VAT (+20%) frequentemente sinaliza cards top
    # (sellers profissionais cobrando margem em high-value items)
    mt = str(markup_tier or "").lower()
    if "non-vat" in mt or "+20%" in mt:
        return "MID"
    # Default sem evidencia: MODEST (conservador — nao penaliza muito,
    # mas tb nao aprova compra automatic)
    return "MODEST"

# ─── Decisao mecanica + Porque ────────────────────────────────────────────────
@dataclass
class DecisionConfig:
    min_net_margin: float = 0.25        # 25% net margin pra COMPRA
    min_lucro_liq: float = 50.0          # R$50 lucro minimo pra COMPRA
    revisar_min_net: float = 0.20        # 20-25% → REVISAR
    revisar_chase_modest_min_net: float = 0.30  # MODEST com >=30% → REVISAR

def classify_decision(row, cfg: DecisionConfig):
    """Aplica regra mecanica. Retorna (decisao, porque)."""
    chase = row.get("chase_tier", "MODEST")
    nm = row.get("net_margin", 0)
    profit = row.get("lucro_liq", 0)
    val = str(row.get("validation_status", "")).upper()
    is_tg = bool(row.get("trainer_gallery_potential_fp", False))

    # v2.3 Layer 5 (bug-hunt 2026-05-18): alpha-suffix detect (153a, 022a).
    # Cards com sufixo alfanumérico no collector number são tipicamente
    # promos/league (1st/2nd/3rd/4th Place, Prerelease) cegas pra pokemontcg.io.
    # Operador validou em 2026-05-18: Lusamine sm5/153a — preço scanner $160
    # vs preço real $13.77 (1st Place variant). REVISAR forçado.
    card_num = str(row.get("card_number") or "").strip()
    if ALPHA_SUFFIX_RE.match(card_num) and not TRAINER_GALLERY_RE.match(card_num):
        return ("REVISAR",
                f"Alpha suffix '{card_num}' — provável promo/League variant "
                f"(1st/2nd/3rd/4th Place ou Prerelease); pokemontcg.io cega "
                f"pra essas, valide via Link TCG antes")

    # v2.2 Layer 3 (bug-hunt 2026-05-18): unsupported sets → REVISAR forçado.
    # Mesmo que Layer 1 (strict set match) tenha aceito o pricing, alguns
    # sets têm cobertura ruim no pokemontcg.io OU divergem de forma
    # silenciosa. Operador valida manual antes de comprar.
    set_code = _extract_set_code_from_label(row.get("set_code"))
    if set_code in UNSUPPORTED_SETS:
        return "REVISAR", f"Set {set_code} sem cobertura confiável em pokemontcg.io — valide TCG manual"

    if pd.isna(nm) or pd.isna(profit):
        return "NAO", "Dados insuficientes (margem/lucro ausentes)"

    # NAO (rejeitos definitivos)
    if is_tg:
        return "NAO", "TG## potencial FP (pokemontcg.io infla 5-10x)"
    if val in ("STALE",):
        return "NAO", "Validation STALE — preço inseguro"
    if chase == "BULK":
        return "NAO", f"Chase BULK + net {nm:.0%} (bulk sem liquidez mesmo barato)"
    if nm < cfg.revisar_min_net:
        return "NAO", f"Net margin {nm:.0%} < {cfg.revisar_min_net:.0%} (abaixo do piso)"

    # REVISAR (zona cinza)
    if nm < cfg.min_net_margin:
        return "REVISAR", f"Net {nm:.0%} entre {cfg.revisar_min_net:.0%}-{cfg.min_net_margin:.0%} (borderline)"
    if profit < cfg.min_lucro_liq:
        return "REVISAR", f"Net {nm:.0%} OK mas lucro R${profit:.0f} < R${cfg.min_lucro_liq:.0f}"
    if chase == "MODEST":
        if nm >= cfg.revisar_chase_modest_min_net:
            return "REVISAR", f"MODEST + net alta {nm:.0%} (vale checar liquidez do set)"
        return "NAO", f"MODEST + net {nm:.0%} (precisa >={cfg.revisar_chase_modest_min_net:.0%} pra MODEST)"
    if val == "MARKUP_TIER_ANOMALOUS" or val == "ANOMALOUS_MARKUP":
        return "REVISAR", f"Markup anomalo (>45%); chase {chase} + net {nm:.0%}"
    if val not in ("VALIDATED_REAL", "VALIDATED_MARKUP"):
        return "REVISAR", f"Validation {val or 'ausente'}; chase {chase} + net {nm:.0%}"

    # COMPRA
    return "COMPRA", f"Chase {chase} + net {nm:.0%} + lucro R${profit:.0f}"

# ─── Fundamental Score objetivo (0-100) ──────────────────────────────────────
def fundamental_score(row) -> int:
    """Score derivado de 4 metricas objetivas (operador-pedido em 2026-05-16).
    Nao usa heuristicas subjetivas (iconicidade, meta competitivo, etc)."""
    score = 0
    # Chase tier (peso 40)
    chase_pts = {"TOP": 40, "MID": 25, "MODEST": 10, "BULK": 0}
    score += chase_pts.get(row.get("chase_tier", "MODEST"), 0)
    # Net margin (peso 20)
    nm = row.get("net_margin", 0)
    if nm >= 0.40: score += 20
    elif nm >= 0.30: score += 15
    elif nm >= 0.25: score += 10
    elif nm >= 0.20: score += 5
    # Lucro absoluto (peso 25)
    p = row.get("lucro_liq", 0)
    if p >= 200: score += 25
    elif p >= 100: score += 18
    elif p >= 50: score += 12
    elif p >= 25: score += 6
    # Validation status (peso 15)
    val = str(row.get("validation_status", "")).upper()
    if val == "VALIDATED_REAL": score += 15
    elif val == "VALIDATED_MARKUP": score += 10
    elif val == "ANOMALOUS_MARKUP": score += 3
    return min(score, 100)

# ─── Column aliases (preserva v1.5 fixes) ────────────────────────────────────
COLUMN_ALIASES = {
    "card_name": ["card_name","name","card","Card","Name","Card Name","Carta"],
    "card_number": ["card_number","number","Number","Card Number","card_no","No","Numero","Nº","No."],
    "set_code": ["set_code","set","Set","expansion","Expansion","set_id"],
    "rarity": ["rarity","Rarity","Raridade"],
    "variant": ["variant","Variant","version","Version","foil","Foil","Variante"],
    "condition": ["condition","Condition","cond","Cond","Condicao","Condição"],
    "language": ["language","Language","lang","Lang","Idioma"],
    "seller": ["seller","Seller","seller_name"],
    "live_brl": ["live_brl","LIVE R$","LIVE R$ (real)","live_price_brl"],
    "markup_pct": ["markup_pct","Markup %","markup_percent","markup"],
    "markup_tier": ["markup_tier","Markup Tier","tier"],
    "validation_status": ["validation_status","Validation Status","valid_status","status"],
    "reference_price_brl": ["reference_price_brl","TCG Market (BRL)","TCG R$","TCG Market (R$)"],
    "net_margin": ["net_margin","Net Margin % REAL","Net Margin %","Net REAL"],
    "lucro_liq": ["lucro_liq","Lucro R$ REAL","Lucro REAL","Lucro Liq (R$)","Net Profit (R$)"],
    "link_ct": ["link_ct","Link CT","Link CardTrader","CardTrader URL","CardTrader Link","Link"],
    "quantity": ["quantity","Quantity","qty","estoque","Qtd"],
    # v2.7.1 postprocess (2026-05-18): URL TCGPlayer da carta exata
    # matched no pokemontcg.io. Operador valida variante (ex Lusamine 1st Place
    # vs normal) antes de comprar. None aceitável (não-pokemontcg providers).
    "link_tcg": ["link_tcg","Link TCG","tcg_url","TCG URL","TCGPlayer URL","TCGPlayer Link"],
}

def detect_column(df, logical):
    aliases = COLUMN_ALIASES.get(logical, [logical])
    cols_lower = {c.lower().strip(): c for c in df.columns}
    for a in aliases:
        if a in df.columns: return a
        if a.lower() in cols_lower: return cols_lower[a.lower()]
    return None

def normalize_columns(df):
    rename = {}
    for logical in COLUMN_ALIASES:
        actual = detect_column(df, logical)
        if actual: rename[actual] = logical
    return df.rename(columns=rename)

# ─── Hyperlink helper (preservado de v1.5) ────────────────────────────────────
HYPERLINK_FONT = Font(color="0563C1", underline="single")

def apply_card_hyperlinks(ws, df):
    """Aplica hyperlink ativo em Carta → Link CT, e na própria célula Link TCG.

    v2.7.1 (postprocess 2026-05-18): Link TCG (URL TCGPlayer) ganha
    hyperlink no próprio texto (operador clica diretamente). Distinção
    de design vs Link CT: Carta vira link clicável apontando pro CT
    (workflow de compra primário); Link TCG é texto URL clicável
    (workflow de validação de variante secundário).
    """
    cols = list(df.columns)
    # Carta → Link CT
    if "Carta" in cols and "Link CT" in cols:
        carta_idx = cols.index("Carta") + 1
        link_idx = cols.index("Link CT") + 1
        for ri in range(2, len(df) + 2):
            url = ws.cell(row=ri, column=link_idx).value
            if isinstance(url, str) and url.startswith("http"):
                c = ws.cell(row=ri, column=carta_idx)
                c.hyperlink = url
                c.font = HYPERLINK_FONT
    # Link TCG → célula própria (URL clicável)
    if "Link TCG" in cols:
        tcg_idx = cols.index("Link TCG") + 1
        for ri in range(2, len(df) + 2):
            cell = ws.cell(row=ri, column=tcg_idx)
            v = cell.value
            if isinstance(v, str) and v.startswith("http"):
                cell.hyperlink = v
                cell.font = HYPERLINK_FONT

# ─── Main pipeline ────────────────────────────────────────────────────────────
DECISAO_FILL = {
    "COMPRA":  PatternFill("solid", fgColor="C6EFCE"),
    "REVISAR": PatternFill("solid", fgColor="FFEB9C"),
    "NAO":     PatternFill("solid", fgColor="F4CCCC"),
}
CHASE_FILL = {
    "TOP":    PatternFill("solid", fgColor="A9D08E"),
    "MID":    PatternFill("solid", fgColor="FFE699"),
    "MODEST": PatternFill("solid", fgColor="F8CBAD"),
    "BULK":   PatternFill("solid", fgColor="D9D9D9"),
}

def _recompute_margin_with_fee(df: pd.DataFrame, drift_threshold_pp: float = 0.005) -> pd.DataFrame:
    """v2.1 #2: defensivamente recomputa net_margin + lucro_liq via fórmula 1.06.

    Antes confiávamos cegamente no input. Se o XLSX vier de scanner antigo
    (pre v2.6) ou raw sem hub fee, o postprocess mentia sobre a fórmula que
    o Summary documenta. Agora:
      1. Se `live_brl` + `reference_price_brl` válidos → recomputa
         `recomputed_net = (tcg - live*1.06) / tcg`
      2. Compara com `net_margin` do input
      3. Se drift > 0.5pp → log WARNING, sobrescreve com recomputado
      4. Marca `margin_source = "input" | "recomputed"`

    Não toca quando colunas faltam (input incompleto — deixa subir o "Dados
    insuficientes" do classify_decision).
    """
    if "live_brl" not in df.columns or "reference_price_brl" not in df.columns:
        df["margin_source"] = "input"
        return df

    live = pd.to_numeric(df["live_brl"], errors="coerce")
    tcg = pd.to_numeric(df["reference_price_brl"], errors="coerce")
    valid = live.notna() & tcg.notna() & (tcg > 0) & (live > 0)

    custo = live * (1.0 + HUB_FEE_RATE)
    recomputed_net = (tcg - custo) / tcg
    recomputed_lucro = tcg - custo

    if "net_margin" not in df.columns:
        df["net_margin"] = recomputed_net
        df["lucro_liq"] = recomputed_lucro
        df["margin_source"] = "recomputed"
        print(f"[postprocess v2.1] net_margin AUSENTE no input — recomputado em {valid.sum()} rows.")
        return df

    input_net = pd.to_numeric(df["net_margin"], errors="coerce")
    drift = (input_net - recomputed_net).abs()
    drifting = valid & drift.gt(drift_threshold_pp)

    source = pd.Series(["input"] * len(df), index=df.index)
    if drifting.any():
        n_drift = int(drifting.sum())
        max_drift_pp = float(drift[drifting].max()) * 100
        print(
            f"[postprocess v2.1] WARNING: net_margin do input diverge da fórmula "
            f"1.06 em {n_drift}/{int(valid.sum())} rows (drift máx {max_drift_pp:.2f}pp). "
            f"Sobrescrevendo com recomputado."
        )
        # Substitui apenas onde driftando
        df.loc[drifting, "net_margin"] = recomputed_net[drifting]
        df.loc[drifting, "lucro_liq"] = recomputed_lucro[drifting]
        source[drifting] = "recomputed"

    df["margin_source"] = source.values
    return df


def enrich_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(raw_df).copy()
    # v2.1 #2 fix: defensive recompute ANTES de classify_decision consumir.
    df = _recompute_margin_with_fee(df)
    # TG## flag
    if "card_number" in df.columns:
        df["trainer_gallery_potential_fp"] = df["card_number"].astype(str).str.match(r"^TG\d+", case=False, na=False)
    else:
        df["trainer_gallery_potential_fp"] = False
    # Chase Tier
    df["chase_tier"] = df.apply(
        lambda r: classify_chase_tier(
            r.get("rarity"), r.get("card_number"), r.get("markup_tier")
        ), axis=1
    )
    # Fundamental Score (derived, after chase_tier)
    df["fundamental_score"] = df.apply(fundamental_score, axis=1)
    return df

def build_deals_sheet(df: pd.DataFrame, cfg: DecisionConfig) -> pd.DataFrame:
    """Sheet principal: deals com Decisao mecanica (COMPRA + REVISAR, ordenado por lucro)."""
    df = df.copy()
    results = df.apply(lambda r: classify_decision(r, cfg), axis=1)
    df["decisao"] = [r[0] for r in results]
    df["porque"] = [r[1] for r in results]
    # Filter COMPRA + REVISAR (NAO fica em All Listings)
    deals = df[df["decisao"].isin(["COMPRA", "REVISAR"])].copy()
    if "lucro_liq" in deals.columns:
        deals = deals.sort_values("lucro_liq", ascending=False)
    # Renomeia pro display
    display_cols = ["decisao", "porque", "chase_tier", "fundamental_score",
                     "set_code", "card_name", "card_number", "language",
                     "live_brl", "reference_price_brl", "net_margin", "lucro_liq",
                     "validation_status", "seller", "link_ct", "link_tcg"]
    display_cols = [c for c in display_cols if c in deals.columns]
    deals = deals[display_cols]
    rename_map = {
        "decisao": "Decisão", "porque": "Porque", "chase_tier": "Chase Tier",
        "fundamental_score": "Score", "set_code": "Set", "card_name": "Carta",
        "card_number": "Nº", "language": "Idioma", "live_brl": "Preço CT (R$)",
        "reference_price_brl": "TCG (R$)", "net_margin": "Net %",
        "lucro_liq": "Lucro Líq (R$)", "validation_status": "Validação",
        "seller": "Seller", "link_ct": "Link CT", "link_tcg": "Link TCG",
    }
    return deals.rename(columns=rename_map)

def build_all_listings_sheet(df: pd.DataFrame, cfg: DecisionConfig) -> pd.DataFrame:
    """Sheet completa: TUDO com Decisao + Chase + Score (incluindo NAO)."""
    df = df.copy()
    results = df.apply(lambda r: classify_decision(r, cfg), axis=1)
    df["decisao"] = [r[0] for r in results]
    df["porque"] = [r[1] for r in results]
    display_cols = ["decisao", "porque", "chase_tier", "fundamental_score",
                     "set_code", "card_name", "card_number", "language",
                     "live_brl", "reference_price_brl", "net_margin", "lucro_liq",
                     "validation_status", "seller", "link_ct", "link_tcg"]
    display_cols = [c for c in display_cols if c in df.columns]
    df = df[display_cols]
    rename_map = {
        "decisao": "Decisão", "porque": "Porque", "chase_tier": "Chase Tier",
        "fundamental_score": "Score", "set_code": "Set", "card_name": "Carta",
        "card_number": "Nº", "language": "Idioma", "live_brl": "Preço CT (R$)",
        "reference_price_brl": "TCG (R$)", "net_margin": "Net %",
        "lucro_liq": "Lucro Líq (R$)", "validation_status": "Validação",
        "seller": "Seller", "link_ct": "Link CT", "link_tcg": "Link TCG",
    }
    return df.rename(columns=rename_map)

def build_summary(df: pd.DataFrame, cfg: DecisionConfig) -> pd.DataFrame:
    decisions = df.apply(lambda r: classify_decision(r, cfg), axis=1)
    decisao_col = pd.Series([r[0] for r in decisions])
    total = len(df)
    n_compra = (decisao_col == "COMPRA").sum()
    n_revisar = (decisao_col == "REVISAR").sum()
    n_nao = (decisao_col == "NAO").sum()
    # v2.1 #4: deals exportados = só COMPRA + REVISAR (sheet "Deals" filtra NAO)
    n_deals_exportados = int(n_compra + n_revisar)
    lucro_compra = df.loc[decisao_col == "COMPRA", "lucro_liq"].sum() if "lucro_liq" in df.columns else 0
    rows = [
        ("Total listings escaneados", total),
        ("Total deals exportados (COMPRA + REVISAR)", n_deals_exportados),
        ("COMPRA", f"{n_compra} ({n_compra/total*100:.1f}%)" if total else 0),
        ("REVISAR (zona cinza)", f"{n_revisar} ({n_revisar/total*100:.1f}%)" if total else 0),
        ("NÃO", f"{n_nao} ({n_nao/total*100:.1f}%)" if total else 0),
        ("Lucro líquido potencial (COMPRA)", f"R$ {lucro_compra:,.0f}"),
        ("", ""),
        ("Threshold COMPRA — net margin", f"≥ {cfg.min_net_margin:.0%}"),
        ("Threshold COMPRA — lucro líquido", f"≥ R$ {cfg.min_lucro_liq:.0f}"),
        ("Threshold COMPRA — chase tier", "≥ MID"),
        ("Threshold REVISAR — net margin", f"≥ {cfg.revisar_min_net:.0%}"),
        ("Threshold MODEST → REVISAR", f"net ≥ {cfg.revisar_chase_modest_min_net:.0%}"),
        ("", ""),
        ("Math: custo total", "preço_CT × 1.06 (Hub fee, sem shipping)"),
        ("Math: lucro líquido", "TCG_BRL − custo_total"),
        ("Math: net margin", "lucro_líquido / TCG_BRL"),
    ]
    return pd.DataFrame(rows, columns=["Métrica", "Valor"])

def style_sheet(ws, df, decisao_col=None, chase_col=None):
    # Header style
    for ci in range(1, len(df.columns) + 1):
        c = ws.cell(row=1, column=ci)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="305496")
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"
    # Color rows by Decisao
    if decisao_col and decisao_col in df.columns:
        ci = list(df.columns).index(decisao_col) + 1
        for ri in range(2, len(df) + 2):
            cell = ws.cell(row=ri, column=ci)
            if cell.value in DECISAO_FILL:
                cell.fill = DECISAO_FILL[cell.value]
                cell.font = Font(bold=True)
    # Color Chase Tier column
    if chase_col and chase_col in df.columns:
        ci = list(df.columns).index(chase_col) + 1
        for ri in range(2, len(df) + 2):
            cell = ws.cell(row=ri, column=ci)
            if cell.value in CHASE_FILL:
                cell.fill = CHASE_FILL[cell.value]
                cell.font = Font(bold=True)
    # Column widths
    for ci, cn in enumerate(df.columns, 1):
        try:
            vals = [str(v) for v in df.iloc[:50, ci-1].tolist()]
        except Exception:
            vals = []
        ml = max([len(str(cn))] + [len(v) for v in vals]) if vals else len(str(cn))
        ws.column_dimensions[get_column_letter(ci)].width = min(ml + 2, 50)
    # Hyperlinks na coluna Carta
    apply_card_hyperlinks(ws, df)

def write_report(df: pd.DataFrame, cfg: DecisionConfig, output_path: Path):
    df = enrich_df(df)
    wb = Workbook(); wb.remove(wb.active)

    # v2.7.1: helper pra escrever NaN/None como célula vazia em vez de "nan".
    # Pandas serializa None em coluna object via NaN; openpyxl escreve "nan"
    # se passar pd.NA/float('nan') sem tratamento. Importa especialmente pra
    # nova coluna Link TCG (None aceitável quando provider != pokemontcg).
    def _safe_val(val):
        try:
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return None
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        return val

    deals = build_deals_sheet(df, cfg)
    ws = wb.create_sheet("Deals")
    if deals.empty:
        ws.cell(row=1, column=1, value="Nenhum deal (COMPRA ou REVISAR) encontrado.")
    else:
        for ri, row in enumerate([deals.columns.tolist()] + deals.values.tolist(), 1):
            for ci, val in enumerate(row, 1):
                ws.cell(row=ri, column=ci, value=_safe_val(val) if ri > 1 else val)
        style_sheet(ws, deals, decisao_col="Decisão", chase_col="Chase Tier")

    all_l = build_all_listings_sheet(df, cfg)
    ws = wb.create_sheet("All Listings")
    if all_l.empty:
        ws.cell(row=1, column=1, value="Vazio.")
    else:
        for ri, row in enumerate([all_l.columns.tolist()] + all_l.values.tolist(), 1):
            for ci, val in enumerate(row, 1):
                ws.cell(row=ri, column=ci, value=_safe_val(val) if ri > 1 else val)
        style_sheet(ws, all_l, decisao_col="Decisão", chase_col="Chase Tier")

    summary = build_summary(df, cfg)
    ws = wb.create_sheet("Summary")
    for ri, row in enumerate([summary.columns.tolist()] + summary.values.tolist(), 1):
        for ci, val in enumerate(row, 1):
            ws.cell(row=ri, column=ci, value=val)
    # Style summary
    for ci in range(1, len(summary.columns) + 1):
        c = ws.cell(row=1, column=ci)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="305496")
    for ci, cn in enumerate(summary.columns, 1):
        ws.column_dimensions[get_column_letter(ci)].width = 40

    wb.save(output_path)
    print(f"OK: {output_path}")

def main():
    p = argparse.ArgumentParser(description="CardTrader postprocess v2.0 — simplificado")
    p.add_argument("--input", "-i", required=True, help="XLSX raw do scanner")
    p.add_argument("--output", "-o", required=True, help="XLSX relatorio destino")
    p.add_argument("--min-net-margin", type=float, default=0.25,
                   help="Net margin minimo pra COMPRA (default 0.25)")
    p.add_argument("--min-lucro", type=float, default=50.0,
                   help="Lucro liquido R$ minimo pra COMPRA (default 50)")
    p.add_argument("--revisar-min-net", type=float, default=0.20,
                   help="Net margin minimo pra zona REVISAR (default 0.20)")
    p.add_argument("--revisar-modest-min", type=float, default=0.30,
                   help="MODEST so vai REVISAR se net >= X (default 0.30)")
    args = p.parse_args()

    cfg = DecisionConfig(
        min_net_margin=args.min_net_margin,
        min_lucro_liq=args.min_lucro,
        revisar_min_net=args.revisar_min_net,
        revisar_chase_modest_min_net=args.revisar_modest_min,
    )
    df = pd.read_excel(args.input)
    print(f"Carregado: {args.input} | {len(df)} rows | cols: {len(df.columns)}")
    write_report(df, cfg, Path(args.output))

if __name__ == "__main__":
    main()
