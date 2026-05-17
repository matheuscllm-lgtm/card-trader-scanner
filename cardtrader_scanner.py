#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║     CardTrader Arbitrage Scanner — Pokémon TCG Singles             ║
║                                                                      ║
║  Compara preços de singles (EN, Near Mint, não-graded) no           ║
║  cardtrader.com vs preço TCG Player (market price).                 ║
║  Gera planilha .xlsx com alertas de arbitragem (default ≥ 30%).     ║
╚══════════════════════════════════════════════════════════════════════╝

Por que CardTrader em vez de MYP?
    MYP é Brasil (compra em BRL) → o scanner MYP busca cartas baratas no
    Brasil para exportar aos EUA. Já o CardTrader é marketplace europeu
    (Itália) → agregador de sellers da UE com preços em EUR. Oportunidade:
    cartas valorizadas no mercado US que estão desatualizadas na UE.
    Setup inverso, mesma tese.

Modelo operacional (2026-05-12, confirmado por Matheus):
    Cartas compradas vão pro depósito Hub da CardTrader na Europa,
    acumulam ~100 unidades, e só então são enviadas pro Brasil em
    consolidação única. O frete daquele envio dilui per-card a ~R$0.30,
    desprezível. Logo:

        custo final por carta = preço CT * 1.06  (só Hub fee da CT)

    Scanner zera frete por default. Hub fee 6% já vem embutido em
    `live_price_brl` via per-blueprint validation (tier "Hub +6%").
    Override pra cenários sem consolidação: `--shipping-brl X`.

Uso:
    python cardtrader_scanner.py                          # Scan padrão
    python cardtrader_scanner.py --sets sv1 sv2 sv3       # Sets específicos
    python cardtrader_scanner.py --threshold 35           # Margem mín 35%
    python cardtrader_scanner.py --min-price-usd 15       # Preço mín USD
    python cardtrader_scanner.py --dry-run                # Usa só cache
    python cardtrader_scanner.py --provider justtcg       # Troca pricing API

Env vars (arquivo .env na mesma pasta):
    CT_JWT=<JWT do CardTrader: Settings → API Access → Create New Token>
    POKEMONTCG_API_KEY=<opcional, grátis em pokemontcg.io/dev>
    JUSTTCG_API_KEY=<opcional, se usar provider justtcg>

Requisitos:
    pip install requests openpyxl python-dotenv pyyaml

Autor: Elizandra / Claude
Data: 2026-04-20 (v1.0) | 2026-04-29 (v2.1) | 2026-05-12 (v2.2 + v2.3)
Versão: v2.3

Changelog v2.3 (2026-05-12 — alinhamento Hub fee scanner ↔ postprocess):
  - HUB_FEE_RATE = 0.06 promovido a constante; CLI flag --hub-fee
  - validate_per_blueprint agora aplica live_brl × (1 + hub_fee) como custo
    real no recalc de real_margin_pct / real_net_margin_pct / real_lucro_brl
  - Antes scanner era ~6pp otimista vs realidade (apenas postprocess aplicava
    a taxa). Agora margem REAL bate com BUY NOW/REJECT do relatório.
  - hub_fee_rate exportado na aba Stats do XLSX
  - Auto-conversão de --hub-fee > 1.0 (operador pode passar `6` ou `0.06`)

Changelog v2.2 (2026-05-12 — auditoria 9 bugs C/H/M + alinhamento modelo
consolidação):
  - C1: tier markup 30-45% reclassificado como "Alto markup" / VALIDATED_MARKUP
    (era PRICE_CHANGED descartado como erro)
  - C2: clean_collector_number aplicado no fallback bp.version
  - H1: --threshold > 1.0 auto-converte com warning (UX trap "25 vs 0.25")
  - H2: pricing provider agora aceita `foil=` e prioriza variante correta
    (reverseHolofoil vs normal); cache key inclui foil flag
  - M1: filter de validation_status sempre roda quando validate_top > 0
  - M2: opps sempre re-ordenados por real_net_margin_pct após validação
  - M3: SHIPPING_EUR_* promovidas a constantes; flag --shipping-brl
  - M4: log + counter pra moedas exóticas (GBP/JPY) dropadas
  - M5: log de supranumerários (collector_number > set.printedTotal) detecta
    SIR/SAR/HR pra revisão manual
  - Modelo de consolidação: frete default = 0 (cartas consolidadas em
    deposito Hub depot, frete diluído per-card ~R$0.30 → desprezível).
    Override via --shipping-brl X.

Changelog v2.1 (2026-04-29):
  - validate_per_blueprint: validação per-blueprint com tier markup
  - filtro anti-Trainer Gallery (_TRAINER_GALLERY_RE)
  - --validate-top, --min-net-margin CLI flags
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, Optional

import requests
import yaml
from dotenv import load_dotenv
from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ══════════════════════════════════════════════════════════════════════
# LOGGING — saída para stdout E arquivo (auditoria pós-execução)
# ══════════════════════════════════════════════════════════════════════
# Console Windows é cp1252 por padrão e quebra em → ≥ etc — força utf-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Log file path:
#   - CT_LOG_FILE env var (preferido — set pelo wrapper PS antes de invocar)
#   - default cardtrader_scanner.log no cwd
# Por que via env e nao via --log-file CLI?
#   logging.basicConfig roda no IMPORT (antes de argparse). Env var resolve
#   o problema de ordem sem refactor maior.
_LOG_FILE = os.environ.get("CT_LOG_FILE", "cardtrader_scanner.log")
_log_handlers = [
    logging.StreamHandler(sys.stdout),
    logging.FileHandler(_LOG_FILE, encoding="utf-8"),
]
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=_log_handlers,
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# CONFIG — valores default. CLI ou config.yaml sobrescrevem.
# Por que constantes no topo? Uma mudança aqui afeta o scanner inteiro;
# fica fácil ajustar sem ler o código todo.
# ══════════════════════════════════════════════════════════════════════
CT_BASE = "https://api.cardtrader.com/api/v2"
POKEMONTCG_BASE = "https://api.pokemontcg.io/v2"
JUSTTCG_BASE = "https://api.justtcg.com/v1"
FX_BASE = "https://api.frankfurter.app/latest"  # BCE — grátis, sem auth

# Game ID no CardTrader. Pokemon = 5 (MTG=1, Yu-Gi-Oh=4, One Piece=15, etc).
# Descobrível via GET /games se quebrar no futuro.
CT_POKEMON_GAME_ID = 5

# Defaults do scanner (sobrescritos por CLI)
MARGIN_THRESHOLD = 0.30          # 30% margem mínima (requisito do usuário)
MIN_PRICE_USD = 10.0             # filtro extra do usuário
LANGUAGE_FILTER = "en"           # apenas inglês
CONDITION_FILTER = "Near Mint"   # apenas NM
EXCLUDE_GRADED = True            # exclui PSA/BGS/CGC
REQUEST_DELAY_CT = 0.15          # CT tem limite 10/s → 0.15s deixa folga
REQUEST_DELAY_PRICING = 0.1      # pokemontcg.io permite 20k/dia (~0.23/s)
TIMEOUT = 30

# Frete base por tier de seller (EUR — CT é europeu por origem).
# Convertido pra BRL via FX no Scanner._estimate_shipping_brl.
# 2026-05-12 M3 fix: promovido de magic number a constantes.
SHIPPING_EUR_HUB = 5.0           # Hub seller / zero_fee — CT centraliza envio
SHIPPING_EUR_PROFESSIONAL = 10.0 # Professional seller — envia do país do seller
SHIPPING_EUR_PRIVATE = 12.0      # Private seller — envio mais caro

# Hub fee médio sobre preço do site (per-blueprint LIVE). Modelo operacional
# do Matheus 2026-05-12: nem toda listing cobra fee explícita, mas no agregado
# (Hub fee CT + marketplace fee + payment processing variáveis) a média
# converge ~6% sobre o preço exibido na página. Aplicado em validate_per_blueprint
# pra alinhar com cardtrader_postprocess.py (mesma taxa default).
# Custo real da carta = live_brl × (1 + HUB_FEE_RATE).
HUB_FEE_RATE = 0.06              # 6% médio sobre site price (v2.3 fix)

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
CACHE_DB = SCRIPT_DIR / "cache.db"
ENV_FILE = SCRIPT_DIR / ".env"
CONFIG_FILE = SCRIPT_DIR / "config.yaml"

# v2.4: per-set timeout + auto skip-list.
# Run 25898522951 (2026-05-15) cancelou em 30:09 com 5/10 sets processados
# pq o timeout-minutes do GH Actions matou o job, mas o problema mais antigo
# (run 25838570927 de 2026-05-14) foi um set unico travado 24m53s sem progresso.
# Solucao: wall-clock timeout per-set + persistir sets travados em skip-list.
SKIP_LIST_FILE = SCRIPT_DIR / "scanner_skip_list.json"
DEFAULT_PER_SET_TIMEOUT_MIN = 8  # conservador: pior caso medido foi 7min/set

# TTL do cache. Blueprints praticamente não mudam (cartas impressas uma vez).
# Preços mudam diário → refresh.
BLUEPRINT_TTL = timedelta(days=30)
PRICE_TTL = timedelta(hours=24)
FX_TTL = timedelta(hours=12)


# Regex para extrair o número do collector de strings sujas tipo
# "Special Illustration Rare | 161/131" → "161". Capturamos o último grupo N/N
# (algumas cartas trazem códigos de promo antes).
_NUMBER_IN_VERSION = re.compile(r"(\d+)\s*/\s*\d+")

# v2.1 — Filtro anti-Trainer Gallery. Cartas com collector_number "TG##" do
# subset Trainer Gallery (era SWSH 2021-2023) produzem falsos positivos massivos
# no pricing pokemontcg.io: a base retorna preços inflados em 5-10× pra essas
# cartas, possivelmente porque bate com variantes secret-rare alt-art com mesmo
# nome. Resultado: 35 de 38 oportunidades em scan SWSH (2026-04-29 madrugada)
# eram falsos positivos com margens "90%+ líq" estatisticamente impossíveis.
# Solução: skipar listings cujo collector_number bate `^TG\d+`.
_TRAINER_GALLERY_RE = re.compile(r"^TG\d+", re.IGNORECASE)


def clean_collector_number(raw: str) -> str:
    """Normaliza um collector_number pra uso em query no pokemontcg.io.
    Entrada pode vir limpa ("007") ou com rarity concatenada ("SIR | 161/131").
    Saída: só o dígito, sem zeros à esquerda ("161", "7").
    """
    if not raw:
        return ""
    m = _NUMBER_IN_VERSION.search(raw)
    if m:
        return m.group(1).lstrip("0") or "0"
    # fallback: separador "/" sem total, ou só o número
    head = raw.split("/")[0].strip()
    # mantém só dígitos se houver sujeira ("TG01", "SWSH123")
    digits = "".join(c for c in head if c.isdigit())
    return digits.lstrip("0") or digits or head


# ══════════════════════════════════════════════════════════════════════
# MODELS — dataclasses em vez de dicts soltos. Por quê?
#   1. Autocompletar no IDE
#   2. Typos viram erro em vez de KeyError em produção
#   3. Serialização fácil para .xlsx/.json
# ══════════════════════════════════════════════════════════════════════
@dataclass
class Listing:
    """Uma oferta ativa em CardTrader (um seller + uma carta + 1 condição)."""
    product_id: int                  # ID do listing no CT
    blueprint_id: int                # ID da carta-molde
    card_name: str
    set_code: str                    # ex: "sv1", "sv3pt5"
    set_name: str
    collector_number: str            # ex: "125/165"
    condition: str                   # "Near Mint", "Slightly Played"...
    language: str                    # "en", "it"...
    price_cents: int                 # centavos no currency original do listing
    price_currency: str              # moeda original do listing ("BRL", "EUR", "USD")
    price_brl: float                 # preço normalizado em BRL (moeda interna)
    quantity: int
    foil: bool
    graded: bool
    seller_username: str
    seller_can_sell_via_hub: bool    # envio centralizado (+rápido, +seguro)
    seller_user_type: str            # "private", "professional", "zero_fee"
    cardtrader_url: str
    # v2.5 (2026-05-16): rarity persistida pra Chase Tier no postprocess v2+.
    # Fonte: blueprint CT (preferido) ou properties_hash. String vazia ""
    # se nem CT nem properties trouxerem (raro mas defensivo).
    rarity: str = ""

    @property
    def uid(self) -> str:
        """Identificador único para dedup: carta + seller + condição."""
        return f"{self.blueprint_id}:{self.seller_username}:{self.condition}"


@dataclass
class Opportunity:
    """Arbitragem detectada: listing CT com preço TCG conhecido e margem.
    Tudo em BRL (moeda interna do scanner). USD market é mantido como
    referência da fonte (TCGPlayer) pra auditoria.

    Campos `_real` / `live_*` / `markup_*` / `validation_status` são preenchidos
    pela v2.0 (validate_per_blueprint) — quando habilitada, faz uma chamada
    ao endpoint per-blueprint (preço com markup CT embutido) pros top N
    candidatos e recalcula margens reais.
    """
    listing: Listing
    tcg_market_usd: float            # preço market do TCGPlayer (fonte original)
    tcg_market_brl: float            # convertido USD→BRL
    ct_price_brl: float              # preço CT normalizado em BRL (per-expansion, RAW)
    margin_pct: float                # (tcg_brl - ct_brl) / tcg_brl
    margin_brl: float                # tcg_brl - ct_brl em R$ absolutos
    estimated_shipping_brl: float    # frete estimado em BRL (default 0 — modelo consolidação)
    net_margin_pct: float            # margem após dedução de frete (= margem bruta quando frete=0)
    scanned_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    # v2.0 — validação per-blueprint (preço REAL com markup CT)
    validation_status: str = "NOT_VALIDATED"
    live_price_brl: Optional[float] = None
    real_margin_pct: Optional[float] = None
    real_net_margin_pct: Optional[float] = None
    real_lucro_brl: Optional[float] = None
    markup_pct: Optional[float] = None
    markup_tier: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════
# CACHE — SQLite local. Por quê?
#   - Evita hammer nas APIs (reduz custo em planos pagos, reduz banimento)
#   - Retomada em caso de crash
#   - Permite --dry-run para testar filtros sem re-buscar tudo
#   - 1 arquivo, zero setup (vs Redis/Postgres)
# ══════════════════════════════════════════════════════════════════════
class Cache:
    def __init__(self, db_path: Path = CACHE_DB):
        self.db = sqlite3.connect(db_path)
        self.db.execute("PRAGMA journal_mode=WAL")  # melhor concorrência
        self._init_schema()

    def _init_schema(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS blueprints (
            ct_blueprint_id INTEGER PRIMARY KEY,
            ct_expansion_code TEXT,
            name TEXT,
            collector_number TEXT,
            raw_json TEXT,
            fetched_at TEXT
        );
        CREATE TABLE IF NOT EXISTS price_cache (
            key TEXT PRIMARY KEY,    -- "pokemontcg:<tcg_id>" ou similar
            market_usd REAL,
            low_usd REAL,
            mid_usd REAL,
            raw_json TEXT,
            fetched_at TEXT
        );
        CREATE TABLE IF NOT EXISTS fx_cache (
            pair TEXT PRIMARY KEY,   -- "USD_BRL", "EUR_BRL"
            rate REAL,
            fetched_at TEXT
        );
        CREATE TABLE IF NOT EXISTS blueprint_to_pricing (
            -- mapping CT blueprint → pricing provider product ID
            ct_blueprint_id INTEGER,
            provider TEXT,           -- "pokemontcg", "justtcg", "tcgplayer"
            provider_product_id TEXT,
            confidence REAL,         -- 0-1, quão confiante o match é
            matched_at TEXT,
            PRIMARY KEY (ct_blueprint_id, provider)
        );
        CREATE INDEX IF NOT EXISTS idx_bp_exp ON blueprints(ct_expansion_code);
        """)
        self.db.commit()

    def get_fx(self, pair: str) -> Optional[float]:
        row = self.db.execute(
            "SELECT rate, fetched_at FROM fx_cache WHERE pair = ?", (pair,)
        ).fetchone()
        if not row:
            return None
        rate, fetched_at = row
        if datetime.fromisoformat(fetched_at) < datetime.now() - FX_TTL:
            return None
        return rate

    def set_fx(self, pair: str, rate: float):
        self.db.execute(
            "INSERT OR REPLACE INTO fx_cache VALUES (?, ?, ?)",
            (pair, rate, datetime.now().isoformat()),
        )
        self.db.commit()

    def get_price(self, key: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT market_usd, low_usd, mid_usd, fetched_at FROM price_cache WHERE key = ?",
            (key,),
        ).fetchone()
        if not row:
            return None
        market, low, mid, fetched_at = row
        if datetime.fromisoformat(fetched_at) < datetime.now() - PRICE_TTL:
            return None
        return {"market_usd": market, "low_usd": low, "mid_usd": mid}

    def set_price(self, key: str, market: float, low: float, mid: float, raw: dict):
        self.db.execute(
            "INSERT OR REPLACE INTO price_cache VALUES (?, ?, ?, ?, ?, ?)",
            (key, market, low, mid, json.dumps(raw), datetime.now().isoformat()),
        )
        self.db.commit()

    def get_mapping(self, blueprint_id: int, provider: str) -> Optional[str]:
        row = self.db.execute(
            "SELECT provider_product_id FROM blueprint_to_pricing WHERE ct_blueprint_id=? AND provider=?",
            (blueprint_id, provider),
        ).fetchone()
        return row[0] if row else None

    def set_mapping(self, blueprint_id: int, provider: str, product_id: str, confidence: float):
        self.db.execute(
            "INSERT OR REPLACE INTO blueprint_to_pricing VALUES (?, ?, ?, ?, ?)",
            (blueprint_id, provider, product_id, confidence, datetime.now().isoformat()),
        )
        self.db.commit()

    def clear_prices(self):
        """Limpa caches voláteis (preços TCG e FX). Útil pra --no-cache em
        cenários de arbitragem time-sensitive onde 24h TTL é tempo demais."""
        self.db.execute("DELETE FROM price_cache")
        self.db.execute("DELETE FROM fx_cache")
        self.db.commit()


# ══════════════════════════════════════════════════════════════════════
# FX — Frankfurter API (BCE, grátis, sem auth). Moeda interna = BRL.
# ══════════════════════════════════════════════════════════════════════
def _fetch_fx(pair: str, frm: str, to: str, cache: Cache) -> float:
    cached = cache.get_fx(pair)
    if cached is not None:
        return cached
    r = requests.get(f"{FX_BASE}?from={frm}&to={to}", timeout=TIMEOUT)
    r.raise_for_status()
    rate = r.json()["rates"][to]
    cache.set_fx(pair, rate)
    log.info(f"FX {frm}→{to} atualizado: {rate:.4f}")
    return rate

def get_usd_to_brl(cache: Cache) -> float:
    return _fetch_fx("USD_BRL", "USD", "BRL", cache)

def get_eur_to_brl(cache: Cache) -> float:
    return _fetch_fx("EUR_BRL", "EUR", "BRL", cache)


# ══════════════════════════════════════════════════════════════════════
# CARDTRADER CLIENT — API oficial, JSON REST, JWT Bearer.
# Rate limit (confirmado na docs):
#   - 10 req/s por endpoint
#   - 200 req / 10s no total
# Estratégia: delay de 0.15s entre requests (~6.7/s, folga de 30%)
# ══════════════════════════════════════════════════════════════════════
class CardTraderClient:
    def __init__(self, jwt: str, delay: float = REQUEST_DELAY_CT):
        if not jwt:
            raise ValueError("CT_JWT não configurado no .env")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {jwt}",
            "Accept": "application/json",
            "User-Agent": "MasterBox-TCG-Scanner/1.0 (contato via cardtrader.com)",
        })
        self.delay = delay
        self._last_call = 0.0

    def _get(self, path: str, **params) -> dict | list:
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        url = f"{CT_BASE}{path}"

        # Retry com backoff 2/4/8s pra erros transientes (connection reset, 5xx,
        # rate limit). Descoberto em 2026-04-20 quando scan de 7 sets crashou
        # no 4º por ConnectionResetError no /blueprints/export.
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                r = self.session.get(url, params=params, timeout=TIMEOUT)
                self._last_call = time.time()
                if r.status_code == 429:
                    retry_after = int(r.headers.get("Retry-After", "5"))
                    log.warning(f"Rate limit CT, esperando {retry_after}s...")
                    time.sleep(retry_after)
                    continue
                if 500 <= r.status_code < 600:
                    backoff = 2 ** attempt
                    log.warning(f"CT {r.status_code}, retry em {backoff}s...")
                    time.sleep(backoff)
                    continue
                r.raise_for_status()
                return r.json()
            except (requests.ConnectionError, requests.Timeout) as e:
                last_err = e
                backoff = 2 ** attempt
                log.warning(f"CT {type(e).__name__}, retry em {backoff}s... ({attempt+1}/3)")
                time.sleep(backoff)
        if last_err:
            raise last_err
        raise requests.ConnectionError("CT: esgotou 3 tentativas")

    def list_expansions(self, game_id: int = CT_POKEMON_GAME_ID) -> list[dict]:
        """Lista todas as expansões (sets) de Pokemon no CT."""
        data = self._get("/expansions")
        # API retorna TODAS as expansões de TODOS os jogos; filtra por game_id
        return [e for e in data if e.get("game_id") == game_id]

    def list_blueprints(self, expansion_id: int) -> list[dict]:
        """Lista blueprints (cartas-molde) de uma expansão."""
        # Nota: /blueprints/export retorna tudo de uma vez; /blueprints paginado.
        # Usamos /blueprints/export por simplicidade.
        return self._get("/blueprints/export", expansion_id=expansion_id)

    def list_listings_by_blueprint(self, blueprint_id: int, language: str = "en") -> list[dict]:
        """Lista TODAS as ofertas ativas para um blueprint."""
        return self._get("/marketplace/products",
                         blueprint_id=blueprint_id,
                         language=language)

    def list_listings_by_expansion(self, expansion_id: int, language: str = "en") -> list[dict]:
        """Lista TODAS as ofertas de uma expansão inteira (bem mais eficiente)."""
        data = self._get("/marketplace/products",
                         expansion_id=expansion_id,
                         language=language)
        # API retorna dict[blueprint_id, list[listing]] — flatten para list
        if isinstance(data, dict):
            return [l for listings in data.values() for l in listings]
        return data


# ══════════════════════════════════════════════════════════════════════
# PRICING PROVIDERS — abstração. Trocar fonte = trocar 1 classe.
# Por que interface abstrata (Strategy Pattern)?
#   - TCGPlayer API oficial está fechada em 2026 → precisamos de plano B
#   - JustTCG cobra, pokemontcg.io é grátis → quer escolher dinamicamente
#   - Testabilidade: mock em testes sem chamar API real
# ══════════════════════════════════════════════════════════════════════
class PricingProvider(ABC):
    name: str = "base"

    @abstractmethod
    def market_price_usd(self, card_name: str, set_code: str,
                         collector_number: str,
                         foil: bool = False) -> Optional[float]:
        """Retorna preço market em USD ou None se não achar.

        `foil`: indica se o listing CT é foil. Provider usa pra priorizar
        a variante correta (reverseHolofoil vs normal) no agregador
        pokemontcg.io e evitar falso negativo em commons Reverse Holo
        (fix H2, 2026-05-11).
        """
        ...


class PokemonTcgIoProvider(PricingProvider):
    """
    pokemontcg.io v2 — GRÁTIS.
    Inclui campo `tcgplayer.prices.{variant}.market` (USD, TCGPlayer).
    Atualização diária. Limite: 20k req/dia com key grátis, 1k sem.

    Por que esse é o default? Porque a API oficial do TCGPlayer está
    fechada para novos devs, e esse agregador entrega o MESMO dado
    (preço market TCGPlayer) com zero custo.
    """
    name = "pokemontcg"

    def __init__(self, api_key: Optional[str], cache: Cache,
                 delay: float = REQUEST_DELAY_PRICING):
        self.session = requests.Session()
        if api_key:
            self.session.headers["X-Api-Key"] = api_key
        self.cache = cache
        self.delay = delay
        self._last_call = 0.0

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def _search(self, card_name: str, set_code: str, number: str) -> Optional[dict]:
        """Busca carta e retorna o primeiro match.
        Estratégia em cascata: primeiro tenta com set.id (mais específico, menor
        risco de falso-match entre reprints). Se retornar 0, tenta sem set.id
        (set codes divergem entre CT e pokemontcg.io — ex: CT `pre` = ptcg
        `sv8pt5`). Na segunda tentativa fica nome+número, que é razoavelmente
        único pra singles.
        """
        num_clean = clean_collector_number(number)
        safe_name = card_name.replace('"', '\\"')
        base_q = f'name:"{safe_name}"'
        if num_clean:
            base_q += f" number:{num_clean}"

        # Cada tupla: (query, ambiguous_prone). Ambiguous_prone=True significa
        # que a query não restringe set, então múltiplos candidatos de sets
        # diferentes podem voltar — preferimos rejeitar a pegar o primeiro.
        queries: list[tuple[str, bool]] = []
        if set_code:
            queries.append((f'{base_q} set.id:{set_code}', False))
        queries.append((base_q, True))

        for q, ambiguous_prone in queries:
            self._rate_limit()
            r = self.session.get(f"{POKEMONTCG_BASE}/cards",
                                 params={"q": q, "pageSize": 5}, timeout=TIMEOUT)
            if r.status_code != 200:
                log.debug(f"pokemontcg.io erro {r.status_code} para {q}")
                continue
            resp = r.json()
            results = resp.get("data", [])
            total = resp.get("totalCount", len(results))
            if not results:
                continue
            if ambiguous_prone and total > 1:
                # Ex.: "Mawile #246" existe em sm11 (2019) e me2pt5 (2026).
                # Sem set.id pra desambiguar, não dá pra saber qual é a certa.
                log.debug(f"match ambíguo ({total} candidatos) para '{q}' — rejeitado")
                continue
            return results[0]
        return None

    def market_price_usd(self, card_name: str, set_code: str,
                         collector_number: str,
                         foil: bool = False) -> Optional[float]:
        # Cache inclui foil pra evitar colisão entre versão normal e RH
        # do mesmo card (2026-05-11 H2 fix).
        cache_key = f"pokemontcg:{set_code}:{collector_number}:{card_name}:foil={foil}"
        cached = self.cache.get_price(cache_key)
        if cached:
            return cached["market_usd"]

        card = self._search(card_name, set_code, collector_number)
        if not card:
            return None

        # M5 fix (2026-05-12): instrumentação supranumerários.
        # Detecta quando o match retornado é SIR/SAR/HR/Gold/Rainbow (collector
        # number > printedTotal do set). Não muda comportamento — só sinaliza
        # pra operador investigar possíveis falso positivo de pricing inflado.
        # Padrão observado no MYP scanner irmão: SIR aparecendo como "Comum"
        # gera margem >100% falsa. CT pode ter caso análogo.
        try:
            card_num_int = int("".join(c for c in str(card.get("number", "")) if c.isdigit()) or "0")
            printed_total = int((card.get("set") or {}).get("printedTotal") or 0)
        except (TypeError, ValueError):
            card_num_int, printed_total = 0, 0
        if printed_total and card_num_int > printed_total:
            log.debug(
                f"supranumerary match: {card.get('name')} #{card_num_int} > "
                f"set.printedTotal={printed_total} "
                f"(set={card.get('set', {}).get('id')}, rarity={card.get('rarity')}). "
                f"Possível SIR/SAR/HR — validar match contra rarity do listing CT."
            )

        tcg = card.get("tcgplayer", {}).get("prices", {})
        if not tcg:
            return None

        # Escolhe a variante relevante baseado no foil flag do listing CT.
        # 2026-05-11 H2 fix: antes a priority era fixa em [holofoil, normal,
        # reverseHolofoil, ...], independente do listing. Isso quebrava em
        # commons Reverse Holo (priority pegava `normal.market` quando o
        # listing era RH, gerando margem aparente errada).
        # - foil=True (listing CT é foil): pode ser holofoil de rare ou
        #   reverseHolofoil de common. Tenta holofoil primeiro (rares só
        #   têm essa variante), depois reverseHolofoil (commons RH), depois
        #   normal como fallback.
        # - foil=False: prioriza normal (versão não-foil), depois holofoil
        #   (caso o card seja só holo no DB), depois reverseHolofoil.
        if foil:
            priority = ["holofoil", "reverseHolofoil", "normal",
                        "1stEditionHolofoil", "unlimitedHolofoil"]
        else:
            priority = ["normal", "holofoil", "reverseHolofoil",
                        "1stEditionHolofoil", "unlimitedHolofoil"]
        chosen = None
        for variant in priority:
            if variant in tcg and tcg[variant].get("market"):
                chosen = tcg[variant]
                break
        if not chosen:
            # fallback: primeira variante disponível
            for v in tcg.values():
                if v.get("market"):
                    chosen = v
                    break
        if not chosen:
            return None

        market = chosen.get("market") or 0.0
        low = chosen.get("low") or 0.0
        mid = chosen.get("mid") or 0.0
        self.cache.set_price(cache_key, market, low, mid, card)
        return market


class JustTcgProvider(PricingProvider):
    """
    JustTCG — PAGO (~$19-49/mês). Atualiza várias vezes ao dia.
    Stub: habilita quando/se você assinar. Troca no CLI: --provider justtcg
    """
    name = "justtcg"

    def __init__(self, api_key: Optional[str], cache: Cache,
                 delay: float = REQUEST_DELAY_PRICING):
        if not api_key:
            raise ValueError("JUSTTCG_API_KEY não configurado")
        self.session = requests.Session()
        self.session.headers["X-API-Key"] = api_key
        self.cache = cache
        self.delay = delay

    def market_price_usd(self, card_name: str, set_code: str,
                         collector_number: str,
                         foil: bool = False) -> Optional[float]:
        # TODO: implementar quando assinar JustTCG.
        # Endpoint: GET /cards?name=X&set=Y → prices.tcgplayer.marketPrice
        raise NotImplementedError("JustTCG provider: implementar ao assinar")


class TcgPlayerOfficialProvider(PricingProvider):
    """
    TCGPlayer API OFICIAL — FECHADA para novos devs em 2026.
    Stub: se você conseguir credenciais no futuro, só implementar aqui.
    """
    name = "tcgplayer"

    def market_price_usd(self, card_name: str, set_code: str,
                         collector_number: str,
                         foil: bool = False) -> Optional[float]:
        raise NotImplementedError(
            "TCGPlayer API oficial está fechada para novos devs em 2026. "
            "Quando obter credenciais (OAuth2 com public/private key), "
            "implementar aqui: POST /token → GET /pricing/product/{id}"
        )


PROVIDERS = {
    "pokemontcg": PokemonTcgIoProvider,
    "justtcg": JustTcgProvider,
    "tcgplayer": TcgPlayerOfficialProvider,
}


# ══════════════════════════════════════════════════════════════════════
# SCANNER — orquestração do pipeline de arbitragem.
# Fluxo:
#   1. Buscar expansões Pokemon no CT
#   2. Filtrar só as que interessam (via config ou --sets)
#   3. Para cada expansão, puxar TODAS listings EN
#   4. Aplicar filtros (NM, não-graded, preço mín)
#   5. Para cada listing, buscar preço TCG via pricing provider
#   6. Calcular margem bruta e líquida (default frete=0 modelo consolidação Hub)
#   7. Dedup: mantém só melhor oferta por (carta + condição)
# ══════════════════════════════════════════════════════════════════════
# --- v2.4 skip-list helpers (module-level) ---

def load_skip_list() -> dict:
    """Le scanner_skip_list.json. Retorna dict com chaves 'skipped' (list[str])
    e 'updated_at'/'reasons'. Vazio se arquivo nao existe."""
    if not SKIP_LIST_FILE.exists():
        return {"skipped": [], "reasons": {}, "updated_at": None}
    try:
        return json.loads(SKIP_LIST_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"Skip-list inválida ({SKIP_LIST_FILE}): {e}. Tratando como vazia.")
        return {"skipped": [], "reasons": {}, "updated_at": None}


def add_to_skip_list(exp_code: str, reason: str) -> None:
    """Adiciona um exp_code à skip-list com motivo + timestamp. Idempotente."""
    data = load_skip_list()
    skipped = set(data.get("skipped", []))
    skipped.add(exp_code)
    reasons = data.get("reasons") or {}
    reasons[exp_code] = reason
    payload = {
        "skipped": sorted(skipped),
        "reasons": reasons,
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    SKIP_LIST_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    log.warning(f"  Adicionado à skip-list: {exp_code} (motivo: {reason})")


def clear_skip_list() -> None:
    """Apaga skip-list (no proximo scan todos os sets sao retentados)."""
    if SKIP_LIST_FILE.exists():
        SKIP_LIST_FILE.unlink()
        log.info(f"Skip-list apagada: {SKIP_LIST_FILE.name}")


class Scanner:
    def __init__(self, ct: CardTraderClient, pricing: PricingProvider, cache: Cache,
                 threshold: float = MARGIN_THRESHOLD,
                 min_price_usd: float = MIN_PRICE_USD,
                 exclude_graded: bool = EXCLUDE_GRADED,
                 shipping_brl_override: float = 0.0,
                 hub_fee_rate: float = HUB_FEE_RATE,
                 per_set_timeout_s: float = DEFAULT_PER_SET_TIMEOUT_MIN * 60,
                 ignore_skip_list: bool = False):
        self.ct = ct
        self.pricing = pricing
        self.cache = cache
        self.threshold = threshold
        self.min_price_usd = min_price_usd
        self.exclude_graded = exclude_graded
        # 2026-05-12: modelo operacional de consolidacao no Hub depot. Frete
        # default = 0 (cartas acumulam no deposito CT ~100 unidades e sao
        # enviadas em consolacao unica → frete dilui pra ~R$0.30/card).
        # Override via CLI --shipping-brl X pra simular envio direto.
        self.shipping_brl_override = shipping_brl_override
        # v2.3 fix: hub fee médio aplicado sobre live_brl no recalc REAL.
        # Default 0.06 (paridade com cardtrader_postprocess.py). Override via
        # --hub-fee X pra recalibrar quando taxas CT mudarem.
        self.hub_fee_rate = hub_fee_rate
        # v2.4 (2026-05-15): per-set wall-clock timeout (segundos). Default 8min.
        # Quando excedido, scan_expansion aborta + adiciona o set à skip-list.
        self.per_set_timeout_s = per_set_timeout_s
        self.ignore_skip_list = ignore_skip_list
        self.usd_brl = get_usd_to_brl(cache)
        self.eur_brl = get_eur_to_brl(cache)
        self.stats = {
            "expansions_scanned": 0,
            "listings_fetched": 0,
            "listings_after_filters": 0,
            "tcg_price_found": 0,
            "opportunities_found": 0,
            "skipped_exotic_currency": 0,  # M4 fix: contador de listings em moedas exóticas (GBP/JPY/etc)
            "expansions_skipped_by_list": 0,  # v2.4: sets pulados via skip-list
            "expansions_timed_out": 0,        # v2.4: sets que estouraram per_set_timeout
        }

    def _parse_listing(self, raw: dict, bp_index: dict) -> Optional[Listing]:
        """Converte o dict da API para dataclass Listing.
        `bp_index`: {blueprint_id: blueprint_dict} pré-carregado.
        """
        bp = bp_index.get(raw.get("blueprint_id"))
        if not bp:
            return None

        # Preço: CT retorna centavos + currency. Em 2026-04-29 descobrimos
        # que contas com país=Brasil recebem listings já convertidos pra BRL
        # pela API CT (independente do país do seller). Antes tudo vinha em EUR.
        # Estratégia: BRL é a moeda interna do scanner, com fallback EUR/USD
        # via Frankfurter pra sellers que ainda enviam moeda original.
        price = raw.get("price", {})
        cents = price.get("cents", 0)
        currency = (price.get("currency") or "BRL").upper()
        if currency == "BRL":
            price_brl_val = cents / 100.0
        elif currency == "EUR":
            price_brl_val = (cents / 100.0) * self.eur_brl
        elif currency == "USD":
            price_brl_val = (cents / 100.0) * self.usd_brl
        else:
            # GBP, JPY etc — raro, ignorado até termos demanda.
            # M4 fix (2026-05-11): log + stat counter pra não perder cobertura
            # silenciosa caso CT habilite GBP/JPY nativo no futuro.
            log.debug(
                f"moeda exótica ignorada: {currency} no listing "
                f"{raw.get('id')} (bp={raw.get('blueprint_id')})"
            )
            self.stats["skipped_exotic_currency"] += 1
            return None

        props = raw.get("properties_hash") or raw.get("properties") or {}
        user = raw.get("user", {})

        # Set code/name: blueprint só traz `expansion_id` numérico (sem dict
        # nested), então a fonte confiável é o próprio listing, que vem com
        # `expansion: {code, name_en, id}`. Descoberto em 2026-04-20 após
        # Mawile falso-positivo com set_code vazio.
        listing_exp = raw.get("expansion") or {}
        resolved_set_code = listing_exp.get("code") or ""
        resolved_set_name = listing_exp.get("name_en") or listing_exp.get("name") or ""

        return Listing(
            product_id=raw["id"],
            blueprint_id=raw["blueprint_id"],
            card_name=bp.get("name", ""),
            set_code=resolved_set_code,
            set_name=resolved_set_name,
            # Fonte preferida: properties_hash do listing, que traz "007" limpo.
            # Blueprint costuma ter collector_number vazio e cair em `version`
            # formatado como "Rarity | N/total" → aplicamos clean só nesse
            # fallback pra extrair o dígito via regex sem mexer nos paths
            # limpos (2026-05-11 fix).
            collector_number=(
                props.get("collector_number")
                or bp.get("collector_number")
                or clean_collector_number(bp.get("version", ""))
                or ""
            ),
            condition=props.get("condition", "Unknown"),
            # Pokemon usa sempre properties_hash.pokemon_language; mtg_language
            # é sempre None pra cartas Pokemon. Sem valor → string vazia (não "en")
            # para não deixar passar carta sem metadados de idioma.
            language=(props.get("pokemon_language") or "").lower(),
            price_cents=cents,
            price_currency=currency,
            price_brl=price_brl_val,
            quantity=raw.get("quantity", 0),
            foil=props.get("mtg_foil", False) or props.get("foil", False),
            graded=raw.get("graded", False),
            seller_username=user.get("username", ""),
            seller_can_sell_via_hub=user.get("can_sell_via_hub", False),
            seller_user_type=user.get("user_type", "private"),
            cardtrader_url=f"https://www.cardtrader.com/cards/{raw['blueprint_id']}",
            # 2026-05-16: Schema CT blueprint tem rarity em fixed_properties.pokemon_rarity,
            # NÃO no campo `rarity` raiz (verificado via inspect do bp[0] de sfa).
            # Patterns esperados: "Common"/"Uncommon"/"Rare"/"Ultra Rare"/"Secret Rare"/etc.
            # Vazio = sealed product (booster, ETB) — não-card, será filtrado downstream.
            rarity=(
                (bp.get("fixed_properties") or {}).get("pokemon_rarity")
                or bp.get("rarity")
                or props.get("pokemon_rarity")
                or props.get("rarity")
                or ""
            ).strip(),
        )

    def _passes_filters(self, l: Listing) -> bool:
        if l.condition != CONDITION_FILTER:
            return False
        if LANGUAGE_FILTER and l.language != LANGUAGE_FILTER:
            return False
        if self.exclude_graded and l.graded:
            return False
        # v2.1 — anti-Trainer Gallery: skipa cartas TG## (subset SWSH com
        # pricing corrompido no pokemontcg.io). Ver _TRAINER_GALLERY_RE.
        if l.collector_number and _TRAINER_GALLERY_RE.match(l.collector_number):
            return False
        # Filtro min_price_usd: converte BRL→USD via FX pra manter o threshold
        # em USD (referência TCGPlayer), sem importar a moeda do listing.
        price_usd_equiv = l.price_brl / self.usd_brl
        if price_usd_equiv < self.min_price_usd:
            return False
        return True

    def _estimate_shipping_brl(self, listing: Listing, units: int = 1) -> float:
        """Frete em BRL por listing. Default 0 (modelo de consolidacao no Hub depot).

        Modelo operacional 2026-05-12 (confirmado por Matheus):
        - Compras CT vao pro deposito Hub na Europa
        - Acumulam ~100 cartas
        - Enviadas em consolidacao unica pro Brasil
        - Frete daquele envio (~R$30-50) dilui entre as 100 cartas
        - Resultado per-card: R$0.30-0.50 → desprezivel

        Logo o scanner zera frete por default. Hub fee 6% e o unico custo
        adicional alem do preco CT, e ja vem embutido em `live_price_brl`
        via per-blueprint validation (markup_tier "Hub +6%").

        Override (`--shipping-brl X`): pra simular cenarios sem
        consolidacao (compra urgente, sellers non-Hub que enviam direto).
        Valor passa direto, dividido por `units` se compra multipla do
        mesmo listing.

        Implementacao antiga (estimativa EUR-based por tier) preservada
        como `_legacy_shipping_eur_estimate_unused` para referencia futura.
        """
        return self.shipping_brl_override / max(units, 1)

    def _legacy_shipping_eur_estimate_unused(self, listing: Listing) -> float:
        """[INATIVO desde 2026-05-12] Estimativa de frete baseada em EUR + FX.

        Calculo pre-consolidacao: tier de seller (Hub/Pro/Private) → base em
        EUR (5/10/12) → multiplicado por FX EUR→BRL → frete per-listing
        ~R$28-69.

        Substituido por shipping=0 default quando o modelo operacional de
        consolidacao foi confirmado. Mantido como referencia: se o fluxo de
        consolidacao mudar (ex: virar envio direto), reativar essa logica.
        """
        if listing.seller_user_type == "zero_fee" or listing.seller_can_sell_via_hub:
            base_eur = SHIPPING_EUR_HUB
        elif listing.seller_user_type == "professional":
            base_eur = SHIPPING_EUR_PROFESSIONAL
        else:
            base_eur = SHIPPING_EUR_PRIVATE
        return base_eur * self.eur_brl

    def scan_expansion(self, expansion: dict) -> Iterator[Opportunity]:
        exp_id = expansion["id"]
        exp_code = expansion.get("code", "")
        exp_name = expansion.get("name", "")
        log.info(f"→ Scan: {exp_name} ({exp_code}) [id={exp_id}]")
        # v2.4: marca início pra wall-clock timeout no pricing loop
        set_start = time.monotonic()

        # Carrega blueprints da expansão (indexa para O(1) lookup)
        blueprints = self.ct.list_blueprints(exp_id)
        bp_index = {bp["id"]: bp for bp in blueprints}
        log.info(f"  {len(blueprints)} blueprints carregados")

        # Puxa todas listings EN da expansão de uma vez (muito + eficiente que
        # 1 chamada por blueprint — economiza de 400+ calls para 1)
        raw_listings = self.ct.list_listings_by_expansion(exp_id, language=LANGUAGE_FILTER)
        self.stats["listings_fetched"] += len(raw_listings)
        log.info(f"  {len(raw_listings)} listings EN encontrados")

        # Dedup por (blueprint + seller + condição): mantém o menor preço.
        # Comparação é em BRL (não em cents) porque listings podem vir em
        # moedas diferentes — comparar cents direto seria errado (1 cent BRL
        # ≠ 1 cent EUR).
        best_by_uid: dict[str, Listing] = {}
        for raw in raw_listings:
            l = self._parse_listing(raw, bp_index)
            if not l:
                continue
            if not self._passes_filters(l):
                continue
            existing = best_by_uid.get(l.uid)
            if not existing or l.price_brl < existing.price_brl:
                best_by_uid[l.uid] = l

        self.stats["listings_after_filters"] += len(best_by_uid)
        log.info(f"  {len(best_by_uid)} listings após filtros (NM, EN, não-graded, ≥${self.min_price_usd})")

        # Para cada listing filtrado, busca preço TCG e calcula margem
        total_listings = len(best_by_uid)
        for i, l in enumerate(best_by_uid.values(), 1):
            # v2.4: wall-clock timeout check antes de cada call de pricing
            if self.per_set_timeout_s and (time.monotonic() - set_start) > self.per_set_timeout_s:
                elapsed = time.monotonic() - set_start
                log.error(
                    f"  ⏱️  TIMEOUT set {exp_code} ({exp_name}): {elapsed/60:.1f}min "
                    f"> {self.per_set_timeout_s/60:.1f}min limite. Abortando após "
                    f"{i-1}/{total_listings} listings priced."
                )
                self.stats["expansions_timed_out"] += 1
                add_to_skip_list(exp_code, f"per_set_timeout_{int(self.per_set_timeout_s)}s_at_{i-1}_of_{total_listings}")
                return
            if i % 50 == 0 or i == total_listings:
                log.info(f"  Pricing progress: {i}/{total_listings} listings consultados")
            try:
                tcg_market = self.pricing.market_price_usd(
                    l.card_name, l.set_code, l.collector_number,
                    foil=l.foil,  # H2 fix: foil-aware variant selection
                )
            except Exception as e:
                log.debug(f"  Erro pricing {l.card_name}: {e}")
                tcg_market = None
            if not tcg_market or tcg_market <= 0:
                continue
            self.stats["tcg_price_found"] += 1

            # Margem calculada em BRL (a verdade operacional pro Matheus).
            # TCGPlayer market vem em USD → converte via Frankfurter.
            # v2.6 (bug-hunt 2026-05-17 #1): custo inclui Hub fee 6% mesmo
            # quando --validate-top=0. Antes a margem inicial era 6pp otimista
            # vs a fórmula canônica `custo = preço_CT × 1.06`. Mantém
            # ct_price_brl como preço cru de página (Scan R$ raw); margens
            # e net_margin já refletem o custo real.
            tcg_brl = tcg_market * self.usd_brl
            ct_brl = l.price_brl
            custo_brl = ct_brl * (1.0 + self.hub_fee_rate)
            margin = (tcg_brl - custo_brl) / tcg_brl
            if margin < self.threshold:
                continue

            shipping_brl = self._estimate_shipping_brl(l)
            net_margin = (tcg_brl - custo_brl - shipping_brl) / tcg_brl

            self.stats["opportunities_found"] += 1
            yield Opportunity(
                listing=l,
                tcg_market_usd=tcg_market,
                tcg_market_brl=tcg_brl,
                ct_price_brl=ct_brl,
                margin_pct=margin,
                margin_brl=tcg_brl - custo_brl,
                estimated_shipping_brl=shipping_brl,
                net_margin_pct=net_margin,
            )

        self.stats["expansions_scanned"] += 1

    def scan(self, expansions: list[dict]) -> list[Opportunity]:
        opps: list[Opportunity] = []
        # v2.4: carrega skip-list (sets que estouraram timeout em runs anteriores)
        skip_data = load_skip_list() if not self.ignore_skip_list else {"skipped": [], "reasons": {}}
        skip_set = set(skip_data.get("skipped", []))
        if skip_set:
            log.info(
                f"Skip-list ativa ({SKIP_LIST_FILE.name}): {len(skip_set)} sets serão pulados "
                f"({', '.join(sorted(skip_set))}). Use --ignore-skip-list pra forçar."
            )
        # v2.5.1 (2026-05-16 night): heartbeat por set + total elapsed.
        # Operador pediu detectabilidade de stall: agora cada set loga
        # "ALIVE [HH:MM:SS] set N/TOTAL exp_code elapsed=Xmin" antes de scan_expansion.
        # Também captura Exception genérica (não só HTTPError) pra não matar
        # o loop inteiro se um set lançar algo inesperado.
        run_start = time.monotonic()
        total_sets = len(expansions)
        for idx, exp in enumerate(expansions, 1):
            exp_code = exp.get("code", "")
            elapsed_min = (time.monotonic() - run_start) / 60.0
            log.info(
                f"ALIVE [{datetime.now().strftime('%H:%M:%S')}] set {idx}/{total_sets} "
                f"({exp_code}) total_elapsed={elapsed_min:.1f}min"
            )
            if exp_code in skip_set:
                self.stats["expansions_skipped_by_list"] += 1
                reason = (skip_data.get("reasons") or {}).get(exp_code, "?")
                log.warning(f"⏭️  Pulando {exp.get('name')} ({exp_code}) — skip-list (motivo: {reason})")
                continue
            try:
                opps.extend(self.scan_expansion(exp))
            except requests.HTTPError as e:
                log.error(f"Falha em {exp.get('name')}: {e}")
                continue
            except Exception as e:
                # v2.5.1: nunca deixa exceção genérica matar o full scan
                log.error(
                    f"Erro inesperado em {exp.get('name')} ({exp_code}): "
                    f"{type(e).__name__}: {e}. Continuando próximos sets."
                )
                add_to_skip_list(exp_code, f"unexpected_error_{type(e).__name__}")
                continue
        # Ordena por margem bruta desc (maior oportunidade primeiro)
        opps.sort(key=lambda o: o.margin_pct, reverse=True)
        return opps

    def validate_per_blueprint(self, opps: list[Opportunity], top_n: int = 30) -> None:
        """Fase 3 / v2.0 — Valida top N candidatos via endpoint per-blueprint.

        A API CT retorna preços diferentes nos endpoints per-expansion (RAW do
        seller, sem markup) e per-blueprint (preço FINAL com markup CT embutido,
        +6% tier Hub ou +20% tier non-VAT). O scanner usa per-expansion por
        eficiência (1 chamada por set vs 1 por carta), mas isso infla margens
        em 5-20% vs o preço que o comprador realmente paga.

        Esta validação faz chamadas per-blueprint pros top N por margem bruta,
        encontra o seller correspondente, e enriquece a Opportunity com:
          - live_price_brl (preço REAL com markup)
          - markup_pct, markup_tier (Hub +6% / non-VAT +20% / anômalo)
          - real_margin_pct, real_net_margin_pct, real_lucro_brl
          - validation_status (VALIDATED_REAL, VALIDATED_MARKUP, STALE,
            PRICE_CHANGED, API_ERROR)

        Mutate in place. Não filtra — caller decide threshold via min_net_margin.
        """
        if not opps:
            return
        # Top N por margem bruta (a mesma ordem do scan default)
        sorted_opps = sorted(opps, key=lambda o: o.margin_pct, reverse=True)
        candidates = sorted_opps[:top_n]
        unique_bp_ids = {o.listing.blueprint_id for o in candidates}
        log.info(f"v2.0: validando top {len(candidates)} candidatos ({len(unique_bp_ids)} blueprints únicos) per-blueprint...")

        # Cache resultado per-blueprint (uma chamada por bp_id, mesmo se múltiplos sellers do mesmo card)
        bp_listings: dict[int, Optional[list[dict]]] = {}
        for bp_id in unique_bp_ids:
            try:
                listings = self.ct.list_listings_by_blueprint(bp_id, language=LANGUAGE_FILTER)
                if isinstance(listings, dict):
                    listings = [l for sub in listings.values() for l in sub]
                bp_listings[bp_id] = listings
            except Exception as e:
                log.warning(f"v2.0: per-blueprint falhou bp={bp_id}: {e}")
                bp_listings[bp_id] = None

        # Enriquece cada candidato
        for o in candidates:
            bp_id = o.listing.blueprint_id
            seller = o.listing.seller_username
            listings = bp_listings.get(bp_id)
            if listings is None:
                o.validation_status = "API_ERROR"
                continue
            match = next((l for l in listings if (l.get("user") or {}).get("username") == seller), None)
            if not match:
                o.validation_status = "STALE"
                continue
            # Live BRL (per-blueprint sempre retorna na moeda da conta = BRL pra Matheus,
            # mas tratamos as 3 moedas pra robustez)
            live_cents = match.get("price_cents", 0)
            live_currency = (match.get("price_currency") or "BRL").upper()
            if live_currency == "BRL":
                live_brl = live_cents / 100.0
            elif live_currency == "EUR":
                live_brl = (live_cents / 100.0) * self.eur_brl
            elif live_currency == "USD":
                live_brl = (live_cents / 100.0) * self.usd_brl
            else:
                o.validation_status = "API_ERROR"
                continue

            o.live_price_brl = live_brl
            markup = (live_brl - o.ct_price_brl) / o.ct_price_brl if o.ct_price_brl > 0 else 0.0
            o.markup_pct = markup
            # Classificação tier (com base no padrão observado 2026-04-29 e refinado 2026-05-11)
            if markup < 0.02:
                o.markup_tier = "Real (sem markup)"
                o.validation_status = "VALIDATED_REAL"
            elif markup < 0.12:
                o.markup_tier = "Hub (+6%)"
                o.validation_status = "VALIDATED_MARKUP"
            elif markup < 0.30:
                o.markup_tier = "non-VAT (+20%)"
                o.validation_status = "VALIDATED_MARKUP"
            elif markup < 0.45:
                # 2026-05-11: tiers 30-45% (TheDragonsVault, A2Z TCG, Fun Gs)
                # parecem legítimos — provavelmente non-Hub VAT-exempt ou
                # categoria comissionada alta. Validados, não erro de preço.
                o.markup_tier = f"Alto markup ({markup*100:+.0f}%)"
                o.validation_status = "VALIDATED_MARKUP"
            else:
                # markup ≥45% — provavelmente preço mudou entre scan e validate
                o.markup_tier = f"Anômalo ({markup*100:+.0f}%)"
                o.validation_status = "PRICE_CHANGED"

            # Recalc margens com preço LIVE + Hub fee médio (v2.3 fix 2026-05-12).
            # Custo real = live_brl × (1 + hub_fee_rate). Modelo: site price é o
            # que o operador vê na página, mas fees CT (Hub fee + marketplace +
            # payment) somam ~6% em média no checkout. Sem esse ajuste, scanner
            # ficava 6pp otimista vs realidade. Alinha com postprocess.
            hub_fee_brl = live_brl * self.hub_fee_rate
            custo_real = live_brl + hub_fee_brl
            o.real_margin_pct = (o.tcg_market_brl - custo_real) / o.tcg_market_brl
            o.real_net_margin_pct = (o.tcg_market_brl - custo_real - o.estimated_shipping_brl) / o.tcg_market_brl
            o.real_lucro_brl = o.tcg_market_brl - custo_real - o.estimated_shipping_brl

        # Stats sumarizadas
        validated_real = sum(1 for o in candidates if o.validation_status == "VALIDATED_REAL")
        validated_markup = sum(1 for o in candidates if o.validation_status == "VALIDATED_MARKUP")
        stale = sum(1 for o in candidates if o.validation_status == "STALE")
        log.info(f"v2.0: {validated_real} REAL, {validated_markup} com markup, {stale} STALE, {len(candidates) - validated_real - validated_markup - stale} outros")
        self.stats["v2_validated"] = validated_real + validated_markup
        self.stats["v2_stale"] = stale


# ══════════════════════════════════════════════════════════════════════
# EXCEL EXPORT — openpyxl para compatibilidade com MYP scanner.
# Layout:
#   - Aba "Oportunidades": uma linha por deal, ordenado por margem desc
#   - Aba "Stats": métricas da execução (funnel de filtragem)
# Formatação condicional: margem >= 40% fica verde forte, <30% vermelho.
# ══════════════════════════════════════════════════════════════════════
def export_xlsx(opportunities: list[Opportunity], stats: dict,
                out_path: Path, usd_brl: float, eur_brl: float,
                threshold: float) -> Path:
    wb = Workbook()

    # Aba 1: Oportunidades
    ws = wb.active
    ws.title = "Oportunidades"

    headers = [
        "Card Name", "Set", "Nº", "Rarity", "Condição", "Idioma",
        "Scan R$ (raw)", "Moeda Original CT", "LIVE R$ (real)", "Markup %", "Markup Tier",
        "Validation Status",
        "TCG Market (BRL)", "TCG Market (USD)",
        "Margem % (scan)", "Margem % REAL", "Net Margin % (scan)", "Net Margin % REAL",
        "Lucro R$ REAL", "Frete Est. R$",
        "Qtd", "Foil", "Seller", "Tipo Seller", "Hub",
        "Link CardTrader", "Scanned At",
    ]
    ws.append(headers)

    for opp in opportunities:
        l = opp.listing
        ws.append([
            l.card_name,
            f"{l.set_name} ({l.set_code})",
            l.collector_number,
            l.rarity,
            l.condition,
            l.language.upper(),
            round(opp.ct_price_brl, 2),
            l.price_currency,
            round(opp.live_price_brl, 2) if opp.live_price_brl is not None else None,
            round(opp.markup_pct, 4) if opp.markup_pct is not None else None,
            opp.markup_tier or "",
            opp.validation_status,
            round(opp.tcg_market_brl, 2),
            round(opp.tcg_market_usd, 2),
            round(opp.margin_pct, 4),
            round(opp.real_margin_pct, 4) if opp.real_margin_pct is not None else None,
            round(opp.net_margin_pct, 4),
            round(opp.real_net_margin_pct, 4) if opp.real_net_margin_pct is not None else None,
            round(opp.real_lucro_brl, 2) if opp.real_lucro_brl is not None else None,
            round(opp.estimated_shipping_brl, 2),
            l.quantity,
            "Yes" if l.foil else "No",
            l.seller_username,
            l.seller_user_type,
            "Yes" if l.seller_can_sell_via_hub else "No",
            l.cardtrader_url,
            opp.scanned_at,
        ])

    # ─── Formatação ───
    header_fill = PatternFill("solid", fgColor="1F2937")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    border = Border(*(Side(border_style="thin", color="D1D5DB"),) * 4)

    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Larguras de coluna ajustadas à leitura
    widths = [
        28, 28, 8, 12, 8,         # A-E: card/set/num/cond/idioma
        12, 10, 12, 9, 18,        # F-J: scan/moeda/live/markup%/markup_tier
        18,                       # K: validation_status
        14, 14,                   # L-M: TCG BRL/USD
        12, 12, 12, 16,           # N-Q: margem scan/real/net scan/net REAL
        12, 10,                   # R-S: lucro REAL / frete
        6, 6, 20, 14, 6,          # T-X: qtd/foil/seller/tipo/hub
        40, 18,                   # Y-Z: link/scanned_at
    ]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Formato número/percentual/moeda
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.border = border
        # Colunas monetárias (índices 0-based)
        row[5].number_format = '"R$"#,##0.00'   # F: Scan R$
        row[7].number_format = '"R$"#,##0.00'   # H: LIVE R$
        row[8].number_format = "0.00%"          # I: Markup %
        row[11].number_format = '"R$"#,##0.00'  # L: TCG Market BRL
        row[12].number_format = "$#,##0.00"     # M: TCG Market USD
        row[13].number_format = "0.00%"         # N: Margem % scan
        row[14].number_format = "0.00%"         # O: Margem % REAL
        row[15].number_format = "0.00%"         # P: Net scan
        row[16].number_format = "0.00%"         # Q: Net REAL
        row[17].number_format = '"R$"#,##0.00'  # R: Lucro R$ REAL
        row[18].number_format = '"R$"#,##0.00'  # S: Frete R$

    # Freeze header + filtro
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # Formatação condicional na coluna Net Margin REAL (Q): verde forte = oportunidade real
    if ws.max_row > 1:
        ws.conditional_formatting.add(
            f"Q2:Q{ws.max_row}",
            ColorScaleRule(
                start_type="num", start_value=0, start_color="FEE2E2",
                mid_type="num", mid_value=0.15, mid_color="FEF3C7",
                end_type="num", end_value=0.30, end_color="86EFAC",
            ),
        )

    # Aba 2: Stats (auditoria do funnel)
    ws2 = wb.create_sheet("Stats")
    ws2.append(["Métrica", "Valor"])
    for k, v in stats.items():
        ws2.append([k, v])
    ws2.append(["usd_brl_rate", round(usd_brl, 4)])
    ws2.append(["eur_brl_rate", round(eur_brl, 4)])
    ws2.append(["threshold_margin", f"{threshold:.0%}"])
    ws2.append(["hub_fee_rate", f"{HUB_FEE_RATE:.0%}"])
    ws2.append(["scanned_at", datetime.now().isoformat(timespec="seconds")])
    ws2.column_dimensions["A"].width = 30
    ws2.column_dimensions["B"].width = 20
    for cell in ws2[1]:
        cell.fill = header_fill
        cell.font = header_font

    wb.save(out_path)
    log.info(f"✓ Planilha salva: {out_path}")
    return out_path


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════
def parse_args():
    p = argparse.ArgumentParser(
        description="CardTrader Arbitrage Scanner — Pokémon TCG Singles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--sets", nargs="*", help="Códigos de expansão CT (ex: sv1 sv3pt5). Default: todas do config.yaml")
    p.add_argument("--threshold", type=float, default=MARGIN_THRESHOLD,
                   help=f"Margem mínima bruta (default: {MARGIN_THRESHOLD})")
    p.add_argument("--min-price-usd", type=float, default=MIN_PRICE_USD,
                   help=f"Preço mínimo por carta em USD (default: {MIN_PRICE_USD})")
    p.add_argument("--include-graded", action="store_true",
                   help="Incluir cartas graded (PSA/BGS/CGC). Default: excluir")
    p.add_argument("--provider", choices=list(PROVIDERS.keys()), default="pokemontcg",
                   help="Fonte de preços TCG (default: pokemontcg)")
    p.add_argument("--output", "-o", type=str, default=None,
                   help="Arquivo de saída .xlsx (default: cardtrader_scan_<timestamp>.xlsx)")
    p.add_argument("--dry-run", action="store_true",
                   help="Usa só cache, não chama APIs (debug)")
    p.add_argument("--no-cache", action="store_true",
                   help="Limpa caches voláteis (preços TCG + FX) antes de rodar — força refresh em janelas de arbitragem urgente")
    p.add_argument("--max-expansions", type=int, default=None,
                   help="Limita o número de expansões (teste rápido)")
    p.add_argument("--validate-top", type=int, default=0,
                   help="v2.0: valida os top N candidatos via per-blueprint (preço REAL com markup CT). 0 = desativado. Recomendado: 30")
    p.add_argument("--min-net-margin", type=float, default=0.0,
                   help="v2.0: filtra apenas oportunidades com margem liq REAL >= X apos validacao. Ex: 0.20 = so 20%% liq+")
    p.add_argument("--shipping-brl", type=float, default=0.0,
                   help="Frete fixo per-listing em BRL (default 0 — modelo de "
                        "consolidacao no Hub depot, frete dilui per-card). "
                        "Override pra simular envio direto: ex --shipping-brl 28.84")
    p.add_argument("--hub-fee", type=float, default=HUB_FEE_RATE,
                   help=("Taxa media sobre preco do site (Hub fee + marketplace + "
                         "payment processing) aplicada no recalc REAL. Default "
                         f"{int(HUB_FEE_RATE*100)}%%. Paridade com cardtrader_postprocess.py. "
                         "Custo real = live_brl x (1 + hub_fee)."))
    # v2.4: per-set timeout + skip-list controls
    p.add_argument("--per-set-timeout", type=float, default=DEFAULT_PER_SET_TIMEOUT_MIN,
                   help=(f"v2.4: wall-clock timeout per set (minutos). Default "
                         f"{DEFAULT_PER_SET_TIMEOUT_MIN}. Quando excedido durante pricing loop, "
                         f"set é abortado e adicionado à skip-list. 0 = desativado."))
    p.add_argument("--ignore-skip-list", action="store_true",
                   help="v2.4: ignora scanner_skip_list.json (retenta sets que travaram em runs anteriores).")
    p.add_argument("--clear-skip-list", action="store_true",
                   help="v2.4: apaga scanner_skip_list.json antes de rodar (reset total).")
    return p.parse_args()


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def main():
    args = parse_args()

    # Sanity check: --threshold e --min-net-margin são frações (0.30 = 30%).
    # Trap recorrente: usuário passa "25" achando que é percent → 2500%, scan
    # zera silenciosamente. Auto-converte com warning (2026-05-11 fix).
    if args.threshold > 1.0:
        log.warning(
            f"--threshold {args.threshold} > 1.0 parece percentual, "
            f"convertendo para fração: {args.threshold/100}"
        )
        args.threshold = args.threshold / 100.0
    if args.min_net_margin > 1.0:
        log.warning(
            f"--min-net-margin {args.min_net_margin} > 1.0 parece percentual, "
            f"convertendo para fração: {args.min_net_margin/100}"
        )
        args.min_net_margin = args.min_net_margin / 100.0
    # v2.3: mesma proteção para --hub-fee. Operador pode passar `6` ou `0.06`.
    if args.hub_fee > 1.0:
        log.warning(
            f"--hub-fee {args.hub_fee} > 1.0 parece percentual, "
            f"convertendo para fração: {args.hub_fee/100}"
        )
        args.hub_fee = args.hub_fee / 100.0

    load_dotenv(ENV_FILE)
    cfg = load_config()

    ct_jwt = os.getenv("CT_JWT", "").strip()
    if not ct_jwt:
        log.error("CT_JWT não definido. Configure no arquivo .env")
        log.error("Como obter: CardTrader → Settings → API Access → Create New Token")
        sys.exit(1)

    cache = Cache()
    if args.no_cache:
        log.info("--no-cache: limpando price_cache e fx_cache (forçando refresh)...")
        cache.clear_prices()
    ct = CardTraderClient(ct_jwt)

    # Pricing provider
    provider_cls = PROVIDERS[args.provider]
    if args.provider == "pokemontcg":
        pricing = provider_cls(os.getenv("POKEMONTCG_API_KEY"), cache)
    elif args.provider == "justtcg":
        pricing = provider_cls(os.getenv("JUSTTCG_API_KEY"), cache)
    else:
        pricing = provider_cls()
    log.info(f"Pricing provider: {pricing.name}")

    # Seleção de expansões
    log.info("Listando expansões Pokemon no CardTrader...")
    all_expansions = ct.list_expansions(CT_POKEMON_GAME_ID)
    log.info(f"Total: {len(all_expansions)} expansões")

    sets_cfg = args.sets or cfg.get("sets")
    if sets_cfg:
        wanted = {s.lower() for s in sets_cfg}
        expansions = [e for e in all_expansions if e.get("code", "").lower() in wanted]
        missing = wanted - {e.get("code", "").lower() for e in expansions}
        if missing:
            log.warning(f"Sets não encontrados: {missing}")
    else:
        expansions = all_expansions

    if args.max_expansions:
        expansions = expansions[: args.max_expansions]
    log.info(f"Scan em {len(expansions)} expansões")

    # v2.4: gerencia skip-list antes de criar o Scanner
    if args.clear_skip_list:
        clear_skip_list()
    per_set_timeout_s = args.per_set_timeout * 60 if args.per_set_timeout and args.per_set_timeout > 0 else 0

    # Scanner
    scanner = Scanner(
        ct=ct,
        pricing=pricing,
        cache=cache,
        threshold=args.threshold,
        min_price_usd=args.min_price_usd,
        exclude_graded=not args.include_graded,
        shipping_brl_override=args.shipping_brl,
        hub_fee_rate=args.hub_fee,
        per_set_timeout_s=per_set_timeout_s,
        ignore_skip_list=args.ignore_skip_list,
    )

    t0 = time.time()
    opps = scanner.scan(expansions)
    dt = time.time() - t0
    log.info(f"Scan completo em {dt:.1f}s — {len(opps)} oportunidades ≥ {args.threshold:.0%}")
    log.info(f"Hub fee aplicado no recalc REAL: {args.hub_fee:.0%} (custo = site_price × {1 + args.hub_fee:.2f})")

    # v2.0 — validação per-blueprint dos top N
    if args.validate_top > 0 and opps:
        t1 = time.time()
        scanner.validate_per_blueprint(opps, top_n=args.validate_top)
        log.info(f"Validação per-blueprint completa em {time.time()-t1:.1f}s")

        # M1 fix (2026-05-11): sempre filtra status inválidos (STALE, API_ERROR,
        # PRICE_CHANGED) quando há validação, independente do min_net_margin.
        # Antes só rodava quando min_net_margin > 0, deixando lixo no XLSX.
        before_status = len(opps)
        opps = [
            o for o in opps
            if o.validation_status in ("VALIDATED_REAL", "VALIDATED_MARKUP")
        ]
        dropped = before_status - len(opps)
        if dropped > 0:
            log.info(f"Filtro de status (STALE/API_ERROR/PRICE_CHANGED): {before_status} → {len(opps)} oportunidades")

        # Filtro adicional por margem líq REAL (só se min_net_margin > 0)
        if args.min_net_margin > 0:
            before = len(opps)
            opps = [
                o for o in opps
                if (o.real_net_margin_pct or 0) >= args.min_net_margin
            ]
            log.info(f"Filtro --min-net-margin {args.min_net_margin:.0%}: {before} → {len(opps)} oportunidades")

        # M2 fix (2026-05-11): sempre re-ordena por margem líq REAL desc
        # quando houve validação, não só quando min_net_margin > 0.
        opps.sort(key=lambda o: o.real_net_margin_pct or -999, reverse=True)

    # Export
    out_path = Path(args.output) if args.output else (
        SCRIPT_DIR / f"cardtrader_scan_{datetime.now():%Y%m%d_%H%M}.xlsx"
    )
    export_xlsx(opps, scanner.stats, out_path,
                usd_brl=scanner.usd_brl, eur_brl=scanner.eur_brl,
                threshold=args.threshold)

    # Top 5 por margem líquida REAL se validado, senão líquida estimada
    def net_key(o: Opportunity) -> float:
        return o.real_net_margin_pct if o.real_net_margin_pct is not None else o.net_margin_pct
    opps_by_net = sorted(opps, key=net_key, reverse=True)

    # Resumo no terminal
    print("\n" + "═" * 60)
    print(f"  RESUMO — {datetime.now():%Y-%m-%d %H:%M}")
    print("═" * 60)
    print(f"  Expansões escaneadas   : {scanner.stats['expansions_scanned']}")
    print(f"  Listings baixados       : {scanner.stats['listings_fetched']}")
    print(f"  Após filtros           : {scanner.stats['listings_after_filters']}")
    print(f"  Com preço TCG          : {scanner.stats['tcg_price_found']}")
    print(f"  Oportunidades ≥ {args.threshold:.0%}   : {scanner.stats['opportunities_found']}")
    print(f"  Câmbio USD→BRL          : {scanner.usd_brl:.4f}")
    print(f"  Câmbio EUR→BRL          : {scanner.eur_brl:.4f}")
    print(f"  Planilha                : {out_path}")
    print("═" * 60)

    if opps_by_net:
        validated_label = " (validadas v2.0)" if args.validate_top > 0 else ""
        print(f"\n  TOP 5 OPORTUNIDADES{validated_label}:\n")
        for i, o in enumerate(opps_by_net[:5], 1):
            l = o.listing
            # Frete: por default = 0 (modelo consolidação Hub depot). Mostra
            # parêntese só quando há override via --shipping-brl > 0.
            freight_suffix = (
                f" c/ frete (R${o.estimated_shipping_brl:.2f})"
                if o.estimated_shipping_brl > 0 else ""
            )
            print(f"  {i}. {l.card_name} ({l.set_code} {l.collector_number})")
            if o.live_price_brl is not None:
                print(f"     Scan R${o.ct_price_brl:.2f} → LIVE R${o.live_price_brl:.2f}  [{o.markup_tier}]")
                print(f"     TCG: R${o.tcg_market_brl:.2f} (${o.tcg_market_usd:.2f})  | Lucro REAL: R${o.real_lucro_brl:.2f}")
                print(f"     Margem REAL: {o.real_margin_pct:.1%} bruta | {o.real_net_margin_pct:.1%} líquida{freight_suffix}")
            else:
                print(f"     CT: R${o.ct_price_brl:.2f} ({l.price_currency})  →  TCG: R${o.tcg_market_brl:.2f} (${o.tcg_market_usd:.2f})")
                print(f"     Margem: {o.margin_pct:.1%} bruta | {o.net_margin_pct:.1%} líquida{freight_suffix}  [não validado]")
            print(f"     Seller: {l.seller_username} ({l.seller_user_type})")
            print(f"     Link: {l.cardtrader_url}\n")


if __name__ == "__main__":
    main()
