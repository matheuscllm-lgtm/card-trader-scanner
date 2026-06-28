"""Coluna "DH" — 2ª opinião do Double Holo para os deals do CardTrader scanner.

O que é: uma nota 0-100 que resume a LEITURA DE MERCADO do Double Holo para a
carta (previsão de preço, sinal de IA, ROI de gradação, momentum). É a avaliação
dos DADOS premium do Double Holo — uma **segunda opinião** mostrada numa coluna à
parte. **NÃO entra na margem nem na decisão COMPRA/REVISAR** do scanner — preço de
referência continua sendo o TCGplayer (pokemontcg.io / tcgcsv). 50 = neutro;
>50 = Double Holo otimista; <50 = pessimista.

Fonte dos dados: o JSON canônico produzido por
`~/scanners-commons/tooling/doubleholo_signals.py ingest --json`, que normaliza o
que o DOM-scraper raspa da sessão premium logada. **A nota `dh_score` é calculada
UMA ÚNICA VEZ no pipeline (single source) e vem pronta no JSON** — este módulo só
a LÊ (não recalcula, pra não haver fórmulas que divergem entre repos).

Join determinístico por **productId do TCGplayer**: o `tcg_product_id` do registro
canônico == o productId da linha — vindo da coluna `tcg_product_id` (resolvida via
Fix(1) tcgcsv / Fix(2) ponte offline) ou extraído de `link_tcg` quando já for um
`tcgplayer.com/product/<id>`. Sem casar por nome. Linha sem productId resolvido
fica SEM DH — a coluna mostra "—" (honesto; não inventa).
"""
from __future__ import annotations

import json
import re

# productId do TCGplayer a partir de uma URL tcgplayer.com/product/<id>.
_PRODUCT_ID_RE = re.compile(r"tcgplayer\.com/product/(\d+)")


def extract_product_id(tcg_url) -> str | None:
    """productId TCGplayer (string) de uma `tcg_url`, ou None se não houver.

    None é o caso honesto pra cartas sem entry TCGplayer com productId na URL —
    sem chave de join não casa (não inventa).
    """
    if not tcg_url:
        return None
    m = _PRODUCT_ID_RE.search(str(tcg_url))
    return m.group(1) if m else None


def load_signals(path: str) -> dict[str, dict]:
    """Lê o JSON canônico do pipeline -> {tcg_product_id: registro}.

    Aceita um registro único ou uma lista (saída de `ingest --json`). Ignora
    registros sem product id (sem chave de join não dá pra casar — honesto).
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    out: dict[str, dict] = {}
    for rec in data:
        pid = rec.get("tcg_product_id")
        if pid:
            out[str(pid)] = rec
    return out


def _row_product_id(row, pid_col, url_col) -> str | None:
    """productId de join da linha: PREFERE a coluna explícita `pid_col`
    (resolvida via Fix(1) tcgcsv / Fix(2) ponte offline); FALLBACK = extrair de
    `url_col` (link_tcg que já seja tcgplayer.com/product/<id>)."""
    if pid_col is not None and pid_col in row:
        v = row[pid_col]
        if v is not None:
            s = str(v).strip()
            if s and s.lower() != "nan":
                if s.endswith(".0"):      # coerção float do pandas em col mista
                    s = s[:-2]
                if s.isdigit():
                    return s
    if url_col is not None and url_col in row:
        return extract_product_id(row[url_col])
    return None


def attach_scores_df(df, signals_by_pid: dict[str, dict],
                     url_col: str = "link_tcg",
                     pid_col: str = "tcg_product_id") -> int:
    """Adiciona a coluna `dh_score` ao DataFrame; devolve nº de linhas casadas.

    Chave de join por linha (ver `_row_product_id`): coluna explícita
    `tcg_product_id` quando existir, senão productId extraído de `link_tcg`. Casou
    -> lê o `dh_score` precomputado do registro; sem productId ou sem registro ->
    None (a coluna mostra "—" na entrega).

    Espelha `outlook/doubleholo.py:attach_scores`, mas pela chave resolvida na
    linha em vez de `ScoredCard.card_id` — MESMA chave (productId TCGplayer).
    """
    have_pid = pid_col in df.columns
    have_url = url_col in df.columns
    if not have_pid and not have_url:
        df["dh_score"] = None
        return 0
    scores = []
    n = 0
    for _, row in df.iterrows():
        pid = _row_product_id(row, pid_col if have_pid else None,
                              url_col if have_url else None)
        rec = signals_by_pid.get(pid) if pid else None
        if rec is not None:
            scores.append(rec.get("dh_score"))   # lê precomputado (single source)
            n += 1
        else:
            scores.append(None)
    df["dh_score"] = scores
    return n
