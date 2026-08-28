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
import os
import re
import statistics
import time
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
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
    _last_request_at[0] = time.time()
    body = data.decode("utf-8", errors="replace")
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(body)
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


def _name_tokens(card_name) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", str(card_name or "").lower())
            if len(t) >= 2]


def slug_matches(path: str, card_name, number) -> bool:
    """Guarda anti-match-errado: o slug do resultado tem que terminar no MESMO
    número da carta E conter o primeiro token do nome. Falhou → não usa (None).
    """
    slug = path.rstrip("/").rsplit("/", 1)[-1].lower()
    num = norm_number(number)
    if not num or not re.search(rf"(?:^|-){re.escape(num)}$", slug):
        return False
    tokens = _name_tokens(card_name)
    return bool(tokens) and tokens[0] in slug.split("-")


def _set_name_from_label(set_label) -> str:
    """'EX Emerald (em)' → 'EX Emerald'; sem parênteses → o próprio label."""
    s = str(set_label or "").strip()
    return s.rsplit(" (", 1)[0].strip() if " (" in s else s


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
    paths = re.findall(
        r'href="(?:https?://www\.pricecharting\.com)?(/game/[^"#?]+)"', body)
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def resolve_pc_ref(card_name, number, set_label,
                   cache_dir: str | None = None) -> dict | None:
    """Nome+número+set → {'median', 'n_sales', 'url'} ou None (nunca inventa).

    Busca "pokemon <set> <nome> <número>", escolhe o PRIMEIRO resultado cujo
    slug casa nome+número (guarda anti-match-errado) e tira a mediana das
    vendas ungraded recentes. Nenhum resultado casa → None.
    """
    set_name = _set_name_from_label(set_label)
    base_name = re.sub(r"\(.*?\)", "", str(card_name or "")).strip()
    num = norm_number(number)
    query = " ".join(p for p in ("pokemon", set_name, base_name, num) if p)
    try:
        paths = search_card_urls(query, cache_dir=cache_dir)
        matches = [p for p in paths if slug_matches(p, card_name, number)]
        # Entre os que casam nome+número, prefere o slug mais CURTO = versão
        # base ("mr-mime-95" vence "mr-mime-reverse-holo-95") — a oferta CT
        # validada é a variante anunciada; a página base é a referência menos
        # arriscada. Empate → ordem da busca.
        path = min(matches, key=lambda p: len(p.rsplit("/", 1)[-1])) if matches else None
        if not path:
            return None
        page = fetch_page(BASE_URL + path, cache_dir=cache_dir)
    except Exception:  # noqa: BLE001 — rede/parse é best-effort; falha → "—"
        return None
    median, n_sales = median_recent_sold(parse_sold_listings(page))
    if median is None:
        return None
    return {"median": median, "n_sales": n_sales, "url": BASE_URL + path}
