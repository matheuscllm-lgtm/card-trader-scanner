"""Resolver OFFLINE de productId TCGplayer p/ linhas precificadas via pokemontcg.io.

POR QUÊ: o scanner grava, nessas linhas, `Link TCG = prices.pokemontcg.io/
tcgplayer/{cardId}` — um redirect keyed pelo cardId do pokemontcg.io, SEM o
productId numérico do TCGplayer. O DoubleHolo é indexado por productId TCGplayer,
então sem resolver o productId a coluna DH nunca casa nessas linhas (a maioria).

COMO: resolução OFFLINE via tcgcsv (bulk por set) — NÃO segue o redirect HTTP do
prices.pokemontcg.io (lento/rate-limit). Reusa os mapas/helpers do scanner
(setcode CT→pokemontcg→tcgcsv, group resolution unique-match-only, normalização
de número, vocabulário de variante). É puramente IDENTIDADE p/ link/join —
NUNCA toca preço, margem, threshold ou seleção de variante de PREÇO.

DESAMBIGUAÇÃO POR VARIANTE + ANTI-INVENÇÃO: na maioria dos casos 1 número casa 1
productId (resolve direto). Quando um número casa >1 productId (ex.: produto
regular vs. uma 2ª entrada com o mesmo "Number"), usa a VARIANTE que o scanner já
escolheu (coluna "Variant" = price_variant_used) pra desambiguar. Se a variante
não resolver pra exatamente 1 productId → retorna None (DH = "—"). Honestidade >
cobertura: nunca chuta.
"""
from __future__ import annotations

import re
from collections import defaultdict

# Trainer/Galarian Gallery (TG##/GG##): mesmo regex que o scanner usa p/ pular
# essas cartas no scan. clean_collector_number colapsaria "TG01" -> "1", então o
# resolver precisa do guard ANTES de normalizar (anti-invenção; ver resolve()).
_GALLERY_NUM_RE = re.compile(r"^(?:TG|GG)\d+", re.IGNORECASE)

# Helpers/mapas reusados do scanner. ⚠️ ATENÇÃO: importar `cardtrader_scanner`
# TEM efeito colateral — o módulo configura logging no nível de módulo
# (`logging.basicConfig` + `FileHandler`, cardtrader_scanner.py:326-354, roda no
# IMPORT por causa da ordem antes do argparse). Logo este import cria um
# `cardtrader_scanner.log` no cwd e mexe no logging raiz. É tolerável aqui (só
# acontece com `--doubleholo` sem `--no-pid-resolve`); refatorar pra import-safe
# exigiria mexer no setup de logging do scanner (fora do escopo da coluna DH).
from cardtrader_scanner import (
    TCGCSV_BASE,
    TCGCSV_SUBTYPE_TO_VARIANT,
    TCGCSV_USER_AGENT,
    clean_collector_number,
    resolve_tcgcsv_group_id,
    tcgcsv_fetch_groups,
    PokemonTcgIoProvider,
)

# Sentinela: (número, variante) que casou >1 productId distinto → ambíguo.
_AMBIGUOUS = object()


def ptcg_setcodes_for(ct_set_code: str) -> list[str]:
    """CT set code → setcodes pokemontcg.io candidatos (CT code + aliases).

    Cópia da lógica de `Scanner._ptcg_setcodes_for` (reusa o MESMO mapa
    SET_ALIAS_TO_PTCG) — 1º salto da ponte CT→tcgcsv."""
    code = (ct_set_code or "").lower()
    out = [code] if code else []
    for alias in PokemonTcgIoProvider.SET_ALIAS_TO_PTCG.get(code, []):
        if alias.lower() not in out:
            out.append(alias.lower())
    return out


class ProductIdResolver:
    """Resolve productId TCGplayer por (set CT, número, variante) via tcgcsv.

    `fetch_json` e `fetch_groups` são injetáveis pra teste offline. Em produção
    usam a sessão `requests` real contra o tcgcsv (categoria 3 = Pokémon)."""

    def __init__(self, fetch_json=None, fetch_groups=None, session=None):
        self._session = session
        self._fetch_json = fetch_json or self._default_fetch_json
        self._fetch_groups = fetch_groups or self._default_fetch_groups
        self._groups = None
        self._groups_fetched = False
        # ct_set_code -> {"vpid": {key: {variant: pid|_AMBIGUOUS}}, "pids": {key: set()}}
        self._set_cache: dict[str, dict | None] = {}

    # — fetchers reais (default) ————————————————————————————————————————————
    def _ensure_session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def _default_fetch_groups(self):
        return tcgcsv_fetch_groups(self._ensure_session())

    def _default_fetch_json(self, path: str):
        try:
            r = self._ensure_session().get(
                f"{TCGCSV_BASE}/{path}",
                headers={"User-Agent": TCGCSV_USER_AGENT}, timeout=20)
            if r.status_code != 200:
                return None
            return r.json()
        except Exception:  # noqa: BLE001 — rede falhou → sem productId (honesto)
            return None

    # — construção do índice por set ————————————————————————————————————————
    def _build_set_index(self, ct_set_code: str, set_name: str) -> dict | None:
        if not self._groups_fetched:
            self._groups = self._fetch_groups()
            self._groups_fetched = True
        if not self._groups:
            return None
        group_id = resolve_tcgcsv_group_id(
            ptcg_setcodes_for(ct_set_code), set_name, self._groups)
        if not group_id:
            return None
        products = self._fetch_json(f"{group_id}/products")
        prices = self._fetch_json(f"{group_id}/prices")
        if not products or not prices:
            return None

        # productId → numerador (extendedData "Number")
        num_by_pid: dict[int, str] = {}
        for p in products.get("results") or []:
            pid = p.get("productId")
            if pid is None:
                continue
            for ed in p.get("extendedData") or []:
                if ed.get("name") == "Number" and ed.get("value"):
                    num_by_pid[pid] = str(ed["value"])
                    break

        # productId → conjunto de variantes (MESMO vocabulário do scanner)
        variants_by_pid: dict[int, set] = defaultdict(set)
        for r in prices.get("results") or []:
            pid = r.get("productId")
            if pid is None:
                continue
            variant = TCGCSV_SUBTYPE_TO_VARIANT.get(r.get("subTypeName"))
            if variant:
                variants_by_pid[pid].add(variant)

        vpid: dict[str, dict] = defaultdict(dict)
        pids: dict[str, set] = defaultdict(set)
        for pid, num_raw in num_by_pid.items():
            numerator = str(num_raw).split("/")[0].strip()
            digits = "".join(c for c in numerator if c.isdigit())
            if not digits:
                continue  # TG##/promo não-numérico → fora (sem chave estável)
            key = digits.lstrip("0") or "0"
            variants = variants_by_pid.get(pid)
            if not variants:
                continue
            pids[key].add(pid)
            for v in variants:
                if v in vpid[key] and vpid[key][v] != pid:
                    vpid[key][v] = _AMBIGUOUS  # 2 produtos, mesma (num,variante)
                else:
                    vpid[key].setdefault(v, pid)
        return {"vpid": vpid, "pids": pids}

    def _set_index(self, ct_set_code: str, set_name: str) -> dict | None:
        if ct_set_code not in self._set_cache:
            self._set_cache[ct_set_code] = self._build_set_index(ct_set_code, set_name)
        return self._set_cache[ct_set_code]

    # — resolução por linha —————————————————————————————————————————————————
    def resolve(self, ct_set_code: str, set_name: str, number,
                variant: str | None) -> str | None:
        """productId TCGplayer (str) ou None se não resolver UNICAMENTE."""
        idx = self._set_index(ct_set_code, set_name)
        if not idx:
            return None
        # ANTI-INVENÇÃO: número Trainer/Galarian Gallery (TG##/GG##) NÃO resolve.
        # clean_collector_number tira o prefixo alfa ("TG01" → "1"), então sem este
        # guard um TG/GG casaria o productId da carta REGULAR de mesmo numerador
        # (productId errado → DH fabricada). O scanner já pula TG/GG no scan (mesmo
        # regex); aqui é a barreira p/ linhas que escapem (XLSX antigo / near-miss).
        if _GALLERY_NUM_RE.match(str(number or "").strip()):
            return None
        key = clean_collector_number(str(number) if number is not None else "")
        if not key:
            return None
        pids = idx["pids"].get(key)
        if not pids:
            return None
        if len(pids) == 1:  # 1 produto p/ este número → inequívoco
            return str(next(iter(pids)))
        # >1 produto com o mesmo número → desambigua pela variante priceada
        v = (variant or "").strip()
        if not v:
            return None  # sem variante p/ desambiguar → não inventa
        pid = idx["vpid"].get(key, {}).get(v)
        if pid is None or pid is _AMBIGUOUS:
            return None
        return str(pid)
