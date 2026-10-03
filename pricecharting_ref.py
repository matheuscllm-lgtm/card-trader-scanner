"""Referência PriceCharting — mediana das vendas REAIS (sold listings) ungraded.

Metodologia aprovada pelo operador em 2026-08-28: pra sets vintage/back-catalog
a referência mais honesta não é o market price do TCGplayer (fino, infla por
variante errada), e sim as VENDAS CONCLUÍDAS que o PriceCharting agrega (eBay +
TCGPlayer). Este módulo busca a página pública da carta e devolve a MEDIANA das
N vendas ungraded mais recentes (mediana, não média — anti-outlier).

Invariantes da frota respeitados:
  - NUNCA inventa preço: busca que não casa nome+número (guarda de slug), página
    sem vendas, ou erro de rede → None. O consumidor mostra "—".
  - É coluna de SANIDADE na entrega (`--pc-refs` no postprocess): não muda a
    margem canônica nem a classificação COMPRA/REVISAR — espelho da coluna DH.

Scrape leve com urllib + cache 24h em disco (padrão validado no
ebay-arbitrage-scanner em 2026-06-09: HTTP 200 sem bloqueio; projetos da frota
não compartilham código — este arquivo adapta o padrão, não importa de lá).
"""
from __future__ import annotations

import gzip
import html
import os
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://www.pricecharting.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip",
}
CACHE_TTL_SECONDS = 24 * 3600
REQUEST_GAP_SECONDS = 2.0   # educação com o site
DEFAULT_CACHE_DIR = os.path.join("outputs", "pc_cache")
MEDIAN_WINDOW = 10          # mediana das 10 vendas mais recentes

_last_request_at = [0.0]


_firecrawl_budget = [0]   # créditos Firecrawl liberados NESTE run (0 = rota paga desligada)
_firecrawl_used = [0]
FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"
FIRECRAWL_RETRY_WAIT_S = 3.0


def set_firecrawl_budget(n: int) -> None:
    """Libera até `n` páginas via Firecrawl quando o PriceCharting bloquear (403/429)."""
    _firecrawl_budget[0] = max(0, int(n or 0))
    _firecrawl_used[0] = 0


def firecrawl_used() -> int:
    return _firecrawl_used[0]


def _firecrawl_scrape(url: str) -> str:
    """rawHtml da página via Firecrawl (chave em FIRECRAWL_API_KEY; nunca logada)."""
    import json
    key = (os.environ.get("FIRECRAWL_API_KEY") or "").strip().lstrip("﻿")
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY ausente — rota Firecrawl indisponível")
    payload = json.dumps({"url": url, "formats": ["rawHtml"], "onlyMainContent": False,
                          "maxAge": 0}).encode("utf-8")
    req = urllib.request.Request(FIRECRAWL_SCRAPE_URL, data=payload, method="POST",
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        out = json.loads(r.read().decode("utf-8"))
    data = out.get("data") or {}
    status = (data.get("metadata") or {}).get("statusCode")
    html_body = data.get("rawHtml") or ""
    if not out.get("success", True) or not html_body or (status and int(status) >= 400):
        raise RuntimeError(f"Firecrawl falhou p/ {url} (status {status})")
    return html_body


def fetch_page(url: str, cache_dir: str | None = None) -> str:
    """Baixa uma página do PriceCharting com cache em disco (24h)."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", url.lower())[-120:]
    cache_path = os.path.join(cache_dir, slug + ".html")
    if os.path.exists(cache_path):
        if time.time() - os.path.getmtime(cache_path) < CACHE_TTL_SECONDS:
            with open(cache_path, encoding="utf-8") as f:
                return f.read()

    wait = REQUEST_GAP_SECONDS - (time.time() - _last_request_at[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
        body = data.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # v2.29: PriceCharting passou a devolver 403 pra cliente HTTP comum
        # neste IP (2026-10-03, também via curl). Rota paga OPT-IN e COM TETO:
        # Firecrawl (1 crédito/página). Sem orçamento → o erro sobe (o
        # consumidor rotula "indisponível", nunca "sem venda").
        if e.code not in (403, 429) or _firecrawl_budget[0] <= 0:
            raise
        body, last_err = None, None
        for attempt in range(2):            # 1 nova tentativa (escada de desbloqueio)
            if _firecrawl_budget[0] <= 0:
                break
            if attempt:
                time.sleep(FIRECRAWL_RETRY_WAIT_S)
            _firecrawl_budget[0] -= 1
            _firecrawl_used[0] += 1
            try:
                body = _firecrawl_scrape(url)
                break
            except Exception as fe:  # noqa: BLE001
                last_err = fe
        if body is None:
            raise RuntimeError(f"PriceCharting 403 e Firecrawl falhou: {last_err}") from e
    finally:
        # Também em FALHA: senão, durante throttling, cada retry sai sem gap
        # (a espera era calculada do último SUCESSO) e martela o site.
        _last_request_at[0] = time.time()
    # Escrita atômica: processo morto no meio do write deixava um cache torto
    # que seria re-servido por 24h ("—" falso, indistinguível de no-match).
    tmp_path = cache_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(body)
    os.replace(tmp_path, cache_path)
    return body


def parse_sold_listings(body: str) -> list[dict]:
    """Extrai as vendas UNGRADED da página da carta.

    As vendas moram em `<div class="completed-auctions-used">` (as abas graded
    usam outras classes — `completed-auctions-graded` etc. — e ficam fora).
    Cada linha: `<tr id="{fonte}-{id}">` com `<td class="date">YYYY-MM-DD</td>`
    e `<span class="js-price">$NN.NN</span>`.
    """
    m = re.search(
        r'<div class="completed-auctions-used"[^>]*>(.*?)</table>', body, re.S)
    if not m:
        return []
    block = m.group(1)
    rows = re.findall(
        r'<tr id="([a-z]+)-\d+">\s*'
        r'<td class="date">(\d{4}-\d{2}-\d{2})</td>'
        r'.*?<span class="js-price"[^>]*>\s*\$([\d,]+\.\d{2})',
        block, re.S)
    sales = []
    for source, date, price_text in rows:
        try:
            price = float(price_text.replace(",", ""))
        except ValueError:
            continue
        sales.append({"date": date, "source": source, "price": price})
    return sales


def median_recent_sold(sales: list[dict], n: int = MEDIAN_WINDOW):
    """Mediana das `n` vendas mais recentes. Vazio → (None, 0) — nunca inventa."""
    if not sales:
        return None, 0
    recent = sorted(sales, key=lambda s: s["date"], reverse=True)[:n]
    prices = [s["price"] for s in recent]
    return statistics.median(prices), len(prices)


def norm_number(number) -> str:
    """Número CT → dígitos comparáveis com o slug PC.

    '004' → '4'; '95b/147' → '95' (variante a/b do e-Card colapsa no número
    base — o PC tem UMA página por número); '012/107' → '12'. Sem dígito → ''.
    """
    if number is None:
        return ""
    head = str(number).strip().split("/", 1)[0]
    digits = re.sub(r"\D", "", head)
    return digits.lstrip("0") or ("0" if digits else "")


def _norm_token(t: str) -> str:
    """'erika's' → 'erika' (possessivo cai — o PC mantém o apóstrofo no slug,
    ex. /game/pokemon-gym-challenge/erika's-venusaur-4); pontos caem
    ('lv.x' → 'lvx', casa o token do nome)."""
    t = t.lower().strip()
    if t.endswith("'s"):
        t = t[:-2]
    return t.replace("'", "").replace(".", "")


# Sufixo de nível da era DP ("Celebi Lv.39") — display do CT, não identidade da
# carta; o slug PC é só "celebi-7". "Lv.X" NÃO casa (X não é dígito): Lv.X é
# variante REAL que distingue carta e fica no nome.
_LEVEL_SUFFIX_RE = re.compile(r"(?i)\blv\.?\s*\d+\b")


def clean_card_name(card_name) -> str:
    """Nome CT → nome comparável/pesquisável: remove 'Lv.NN' e parênteses."""
    s = re.sub(r"\(.*?\)", "", str(card_name or ""))
    return _LEVEL_SUFFIX_RE.sub(" ", s).strip()


def _name_tokens(card_name) -> list[str]:
    """Tokens do nome, normalizados. Sem filtro de tamanho: 'N' (BW) é nome
    legítimo de 1 letra; o ruído de possessivo já cai no _norm_token."""
    name = clean_card_name(card_name).replace(".", "")
    return [t for t in
            (_norm_token(x) for x in
             re.findall(r"[a-z0-9']+", name.lower()))
            if t]


def slug_matches(path: str, card_name, number) -> bool:
    """Guarda anti-match-errado (por carta):

    1. o slug termina no MESMO número da carta;
    2. o PRIMEIRO token do slug é o primeiro token do nome — mata prefixo de
       outra carta ('dark-charizard-4' não casa 'Charizard');
    3. TODOS os tokens do nome aparecem no slug OU no console — 'charizard-6'
       não casa 'Charizard ex' (falta o 'ex'), mas 'Starmie δ Delta Species' →
       /game/pokemon-delta-species/starmie-30 casa (delta/species no console).

    Falhou → não usa (None). Review 2026-08-28: sem (2)/(3) a mediana entregue
    podia ser de OUTRA carta (ex/V/dark/light no mesmo console).
    """
    parts = path.strip("/").split("/")
    if len(parts) < 3:
        return False
    console_tokens = {_norm_token(t) for t in parts[1].split("-")}
    slug = parts[-1].lower()
    num = norm_number(number)
    if not num or not re.search(rf"(?:^|-){re.escape(num)}$", slug):
        return False
    slug_tokens = [_norm_token(t) for t in slug.split("-")]
    tokens = _name_tokens(card_name)
    if not tokens or not slug_tokens or slug_tokens[0] != tokens[0]:
        return False
    pool = set(slug_tokens) | console_tokens
    return all(t in pool for t in tokens)


def _set_name_from_label(set_label) -> str:
    """'EX Emerald (em)' → 'EX Emerald'; sem parênteses → o próprio label."""
    s = str(set_label or "").strip()
    return s.rsplit(" (", 1)[0].strip() if " (" in s else s


def console_matches(path: str, set_label) -> bool:
    """Guarda de SET: o console do path (/game/{console}/{carta}) tem que conter
    todos os tokens do nome do set CT (o prefixo 'EX' cai — o PC não o usa:
    'EX Hidden Legends' → 'pokemon-hidden-legends').

    Sem isso o smoke de 2026-08-28 casou cross-set: Relicanth Hidden Legends →
    plasma-blast, Porygon Aquapolis → burning-shadows, Fire Energy Emerald →
    japanese-gx-battle-boost. Nome+número baterem em OUTRO set é FP clássico.
    """
    parts = path.strip("/").split("/")
    if len(parts) < 3:
        return False
    console_tokens = {t for t in
                      (re.sub(r"[^a-z0-9]", "", x)
                       for x in parts[1].lower().split("-"))
                      if t} - {"pokemon"}
    set_tokens = {t for t in re.findall(r"[a-z0-9]+",
                                        _set_name_from_label(set_label).lower())
                  if t != "ex"}
    # Bidirecional (review 2026-08-28): além de conter todos os tokens do set,
    # o console não pode ter tokens EXTRAS ('pokemon-japanese-aquapolis' NÃO
    # casa 'Aquapolis' — a mediana da tiragem japonesa corromperia o sinal).
    if not set_tokens:
        return False
    if console_tokens == set_tokens:
        return True
    # v2.29: o PC prefixa sets da era SV com "scarlet-&-violet-" ("Scarlet &
    # Violet 151") e o CT chama só "151". Remove SÓ o prefixo de era e exige
    # igualdade exata do resto — token de idioma (japanese/chinese/korean)
    # continua sobrando e reprova; base set "Scarlet & Violet" segue exato.
    for prefix in _PC_ERA_PREFIXES:
        if prefix <= console_tokens and not (prefix <= set_tokens):
            rest = console_tokens - prefix
            if rest and rest == set_tokens:
                return True
    return False


_PC_ERA_PREFIXES = (frozenset({"scarlet", "violet"}),)


def search_card_urls(query: str, cache_dir: str | None = None) -> list[str]:
    """Busca no PriceCharting e devolve os paths /game/ dos resultados, na ordem.

    Os hrefs da página de busca vêm ABSOLUTOS (https://www.pricecharting.com/
    game/...) — verificado ao vivo em 2026-08-28; aceita relativo também. A carta
    certa pode estar longe da 1ª posição (Gardevoir Emerald apareceu na 41ª), por
    isso devolve TODOS e o chamador escolhe pelo slug.
    """
    q = urllib.parse.quote(query)
    url = f"{BASE_URL}/search-products?q={q}&type=prices"
    body = fetch_page(url, cache_dir=cache_dir)
    # v2.29: aspas simples OU duplas, e `&amp;` desescapado (HTML via Firecrawl
    # vem `pokemon-scarlet-&amp;-violet-151` — o regex antigo não casava).
    paths = [html.unescape(p) for p in re.findall(
        r"""href=["'](?:https?://www\.pricecharting\.com)?(/game/[^"'#?]+)["']""", body)]
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def resolve_pc_ref(card_name, number, set_label,
                   cache_dir: str | None = None, variant=None) -> dict | None:
    """Nome+número+set → {'median', 'n_sales', 'url'} ou None (nunca inventa).

    Busca "pokemon <set> <nome> <número>", escolhe o PRIMEIRO resultado cujo
    slug casa nome+número (guarda anti-match-errado) e tira a mediana das
    vendas ungraded recentes. Nenhum resultado casa → None.

    `variant`: a variante PRICEADA da oferta CT (coluna Variant do raw, ex.
    'reverseHolofoil'). Oferta reverse tem que casar a página REVERSE do PC —
    caso real 2026-08-29: Breloom EX Deoxys reverse (ref TCG $180) saía com a
    mediana da página holo BASE ($15), comparando variantes diferentes.
    """
    path = _resolve_pc_path(card_name, number, set_label, cache_dir, variant)
    if not path:
        return None
    try:
        page = fetch_page(BASE_URL + path, cache_dir=cache_dir)
    except Exception:  # noqa: BLE001 — rede/parse é best-effort; falha → "—"
        return None
    median, n_sales = median_recent_sold(parse_sold_listings(page))
    if median is None:
        return None
    return {"median": median, "n_sales": n_sales, "url": BASE_URL + path}


def _resolve_pc_path(card_name, number, set_label, cache_dir=None, variant=None,
                     raise_errors: bool = False):
    """Busca a página PC da carta com as guardas (slug nome+número, console =
    set, reverse ↔ reverse). Nenhuma casa / erro → None."""
    set_name = _set_name_from_label(set_label)
    base_name = clean_card_name(card_name)
    num = norm_number(number)
    query = " ".join(p for p in ("pokemon", set_name, base_name, num) if p)
    want_reverse = "reverse" in str(variant or "").lower()
    try:
        paths = search_card_urls(query, cache_dir=cache_dir)
        matches = [p for p in paths
                   if slug_matches(p, card_name, number)
                   and console_matches(p, set_label)]
        # Oferta reverse → SÓ página reverse (sem ela, None — nunca compara
        # variantes diferentes). Oferta não-reverse → só páginas sem 'reverse';
        # entre elas o slug mais CURTO = versão base ("mr-mime-95" vence
        # "mr-mime-holo-95"). Empate → ordem da busca.
        if want_reverse:
            matches = [p for p in matches
                       if "reverse" in p.rsplit("/", 1)[-1].lower()]
        else:
            matches = [p for p in matches
                       if "reverse" not in p.rsplit("/", 1)[-1].lower()]
        return min(matches, key=lambda p: len(p.rsplit("/", 1)[-1])) if matches else None
    except Exception:  # noqa: BLE001 — rede/parse é best-effort; falha → None
        if raise_errors:
            raise
        return None


# ─── v2.29: referência eBay (vendas concluídas) — fonte PRINCIPAL da razão ───
# Pedido do operador (2026-10-03): no screen "carta em outro idioma ≥ N× mais
# barata que a inglesa", a referência da carta INGLESA vem do eBay. A Browse API
# oficial só mostra anúncios ATIVOS; as vendas concluídas `[eBay]` estão na
# página pública da carta no PriceCharting (mesma fonte do ebay-arbitrage-scanner,
# `src/pc_sales.py` — adaptado aqui, projetos da frota não importam entre si).
EBAY_MIN_SALES = 3            # < 3 vendas comparáveis → None (nunca inventa)
EBAY_MAX_AGE_DAYS = 365
EBAY_MEDIAN_WINDOW = 10

_EBAY_ROW_RE = re.compile(r'<tr id="ebay-(\d+)">(.*?)</tr>', re.S)
_ROW_DATE_RE = re.compile(r'<td class="date">(\d{4}-\d{2}-\d{2})</td>')
_ROW_PRICE_RE = re.compile(r'class="js-price"[^>]*>\s*\$([\d,]+\.\d{2})')
_ROW_TITLE_RE = re.compile(r'<td class="title">(.*?)</td>', re.S)
_TITLE_NOISE_RE = re.compile(
    r"Time Warp shows photos of completed sales\..*?to see photos\.\s*(?:OK\b)?"
    r"|\[(?:eBay|TCGPlayer)\]", re.I | re.S)
# A referência é a carta INGLESA raw: venda de outro idioma, gradeada ou lote
# nunca é comparável (regras do ebay-arbitrage-scanner, pc_sales.py).
_FOREIGN_LANG_RE = re.compile(
    r"\b(japanese|japan|jpn|chinese|china|korean|korea|german|french|italian|"
    r"spanish|portuguese|thai|indonesian)\b", re.I)
_GRADED_RE = re.compile(
    r"\b(PSA|BGS|BECKETT|CGC|SGC|TAG|ACE|MNT|GMA|HGA|AGS|KSA|RCG|CSG)\s*-?\s*(10|[1-9](?:\.5)?)(?![\d.])"
    r"|\bgraded\b|\bslab\b", re.I)
_LOT_RE = re.compile(
    r"\b(lots?|bundle|playset|booster|sealed|collection|choose|pick|set\s+of|"
    r"x\s*\d{1,}|\d{1,}\s*x)\b|\bpacks?\b(?![\s-]*fresh)", re.I)


def parse_ebay_sales(body: str) -> list[dict]:
    """Vendas `[eBay]` da tabela UNGRADED (`completed-auctions-used`):
    `{date, price, title, source:'ebay', sale_id}`. TCGPlayer e abas graded fora."""
    m = re.search(r'<div class="completed-auctions-used"[^>]*>(.*?)</table>', body, re.S)
    if not m:
        return []
    out, seen = [], set()
    for sale_id, row in _EBAY_ROW_RE.findall(m.group(1)):
        if sale_id in seen:
            continue
        d, p = _ROW_DATE_RE.search(row), _ROW_PRICE_RE.search(row)
        if not d or not p:
            continue
        try:
            price = float(p.group(1).replace(",", ""))
        except ValueError:
            continue
        t = _ROW_TITLE_RE.search(row)
        title = html.unescape(re.sub(r"<[^>]+>", " ", t.group(1) if t else row))
        title = re.sub(r"\s+", " ", _TITLE_NOISE_RE.sub(" ", title)).strip()
        seen.add(sale_id)
        out.append({"date": d.group(1), "price": price, "title": title,
                    "source": "ebay", "sale_id": sale_id})
    return out


def ebay_comparable(sales: list[dict]) -> list[dict]:
    """Só vendas comparáveis à carta INGLESA raw (sem idioma estrangeiro,
    sem nota de gradeadora, sem lote/pack)."""
    return [s for s in sales
            if s.get("source") == "ebay"
            and not _FOREIGN_LANG_RE.search(s.get("title") or "")
            and not _GRADED_RE.search(s.get("title") or "")
            and not _LOT_RE.search(s.get("title") or "")]


def ebay_median_reference(sales: list[dict], today=None) -> dict | None:
    """Mediana das até 10 vendas mais recentes em 365 dias; exige ≥3. Senão None."""
    import datetime as _dt
    today = today or _dt.date.today()
    cutoff = (today - _dt.timedelta(days=EBAY_MAX_AGE_DAYS)).isoformat()
    recent = sorted((s for s in sales if s["date"] >= cutoff),
                    key=lambda s: s["date"], reverse=True)[:EBAY_MEDIAN_WINDOW]
    if len(recent) < EBAY_MIN_SALES:
        return None
    return {"median": statistics.median(s["price"] for s in recent),
            "n_sales": len(recent),
            "oldest": recent[-1]["date"], "newest": recent[0]["date"]}


def resolve_ebay_ref(card_name, number, set_label,
                     cache_dir: str | None = None, variant=None) -> dict | None:
    """Nome+número+set (+variante) → {'median','n_sales','oldest','newest','url'}
    das vendas eBay comparáveis da carta INGLESA, ou None. Mesma guarda de
    página do `resolve_pc_ref` (slug nome+número, console = set, reverse ↔ reverse)."""
    # v2.29: ERRO de fonte (403, rede, Firecrawl sem orçamento) volta como
    # {'error': ...} — o consumidor rotula "eBay indisponível", distinto de
    # "sem venda eBay" (None). Confundir os dois esconde fonte quebrada.
    try:
        path = _resolve_pc_path(card_name, number, set_label, cache_dir, variant,
                                raise_errors=True)
        if not path:
            return {"miss": "sem página PriceCharting casada"}
        page = fetch_page(BASE_URL + path, cache_dir=cache_dir)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"[:120]}
    comps = ebay_comparable(parse_ebay_sales(page))
    ref = ebay_median_reference(comps)
    if not ref or not ref["median"] or ref["median"] <= 0:
        # Motivo explícito (≠ erro de fonte, ≠ página não achada).
        return {"miss": f"<3 vendas eBay comparáveis em 365d ({len(comps)} no total)",
                "url": BASE_URL + path}
    ref["url"] = BASE_URL + path
    return ref
