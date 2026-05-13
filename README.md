---
tags:
  - tcg
  - arbitragem
  - automação
  - cardtrader
  - pokémon
  - projeto-ativo
date: 2026-04-20
updated: 2026-04-20
status: ativo
version: v1.0
---

# CardTrader Arbitrage Scanner — Pokémon TCG

## Objetivo

Identificar oportunidades de arbitragem entre **CardTrader** (marketplace europeu com preços em EUR) e o **TCG Player** (market US), focando em singles **Near Mint, inglês, não-graded**, com margem **≥ 30%** e preço mínimo **$10 USD**.

**Tese:** CardTrader agrega sellers da UE inteira (Itália, Espanha, França, Alemanha…), muitos com precificação desatualizada ou em recuperação cambial. Cartas valorizadas rapidamente no mercado US frequentemente levam semanas para reprecificar na UE → janela de arbitragem.

## Diferença vs Scanner MYP

| Aspecto | MYP Scanner | CardTrader Scanner |
|---|---|---|
| **Fonte de compra** | MYP Cards (Brasil, BRL) | CardTrader (UE, EUR) |
| **Método de coleta** | Web scraping + cloudscraper | API oficial JSON (JWT) |
| **Frete pro fulfillment US** | ~R$ 80-150 por lote | ~€5-15 por pacote (CT Hub) |
| **Rate limit** | Fragilizado por CloudFlare | 10 req/s oficial, tranquilo |
| **Latência de preço** | Diária (site BR) | Horas (API direta) |
| **Margem alvo** | 35% (absorve frete BR→US maior) | 30% (frete UE→US menor) |

## Arquitetura

```
┌──────────────────┐   JWT Bearer   ┌──────────────────────┐
│ CardTrader API   │ ◄───────────── │ cardtrader_scanner   │
│ /marketplace     │                │                      │
│ /expansions      │                │  ┌────────────────┐  │
│ /blueprints      │                │  │ Cache SQLite   │  │
└──────────────────┘                │  │ - blueprints   │  │
                                    │  │ - preços TCG   │  │
┌──────────────────┐                │  │ - câmbio       │  │
│ pokemontcg.io    │ ◄──────────────┤  └────────────────┘  │
│ (preços TCGP)    │                │                      │
└──────────────────┘                │  ┌────────────────┐  │
                                    │  │ Filtros        │  │
┌──────────────────┐                │  │ - NM, EN       │  │
│ Frankfurter.app  │ ◄──────────────┤  │ - não-graded   │  │
│ (FX EUR→USD, BCE)│                │  │ - preço ≥ $10  │  │
└──────────────────┘                │  │ - margem ≥ 30% │  │
                                    │  └────────────────┘  │
                                    │         ▼            │
                                    │  ┌────────────────┐  │
                                    │  │ Export .xlsx   │──┼──► Obsidian / Sheets
                                    │  └────────────────┘  │
                                    └──────────────────────┘
```

## ⚠️ Descoberta importante sobre TCGPlayer API

A API oficial do TCGPlayer está **fechada para novos desenvolvedores desde 2024-2025** e continua fechada em 2026. Nossa estratégia é usar **pokemontcg.io** como fonte default — ele agrega e republica os preços do TCGPlayer (mesmo dado market/low/mid) com:

- Grátis (20k req/dia com key, 1k sem key)
- Atualização diária
- Cobertura de 50k+ cartas Pokemon

O scanner usa **Strategy Pattern** — se você conseguir acesso TCGPlayer oficial no futuro (ou assinar JustTCG), troca só 1 parâmetro: `--provider tcgplayer` ou `--provider justtcg`.

## Setup — Passo a passo

### 1. Obter os tokens

**CardTrader JWT:**
1. Login em [cardtrader.com](https://www.cardtrader.com)
2. Menu usuário → **Settings** → **API Access**
3. Clicar **Create New Token**, nomear ex: "MasterBox Scanner"
4. **Copiar imediatamente** — o token não é mostrado de novo
5. Guardar no password manager (Bitwarden/1Password)

**Pokemon TCG API key (opcional mas recomendado):**
1. Criar conta em [pokemontcg.io/dev](https://pokemontcg.io/dev)
2. Copiar a API key

### 2. Configurar ambiente

```bash
# Ir para a pasta do scanner
cd "01 - Projetos/TCG & Exportação/CardTrader Scanner"

# Criar virtualenv (isolamento de dependências)
python -m venv .venv

# Ativar (Windows)
.venv\Scripts\activate
# Ativar (macOS/Linux)
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt

# Copiar .env.example para .env e preencher
copy .env.example .env     # Windows
cp .env.example .env       # Mac/Linux
```

Abrir `.env` e preencher `CT_JWT` e `POKEMONTCG_API_KEY`.

### 3. Rodar o scanner

```bash
# Scan padrão (usa sets definidos em config.yaml)
python cardtrader_scanner.py

# Teste rápido: 2 sets, mostra se tudo funciona (~5 min)
python cardtrader_scanner.py --sets sv8pt5 sv9 --max-expansions 2

# Margem customizada
python cardtrader_scanner.py --threshold 0.35 --min-price-usd 15

# Incluir cartas graded (PSA/BGS/CGC) — não recomendado
python cardtrader_scanner.py --include-graded

# Output para arquivo específico
python cardtrader_scanner.py -o scan_semanal_abril.xlsx
```

### 4. Saída

- **Planilha `.xlsx`** — duas abas:
  - `Oportunidades`: uma linha por deal, ordenado por margem desc, formatação condicional (verde > 40%, amarelo 30-40%)
  - `Stats`: funnel de filtragem (quantas listings → quantas passaram cada filtro → quantas viraram oportunidade)
- **Log `cardtrader_scanner.log`** — histórico textual para auditoria
- **Cache `cache.db`** — SQLite local com blueprints e preços (acelera runs subsequentes)

## Filtros ativos

| Filtro | Regra | Por quê |
|---|---|---|
| Idioma | `en` (Inglês) apenas | Liquidez no mercado US — onde vamos revender |
| Condição | `Near Mint` apenas | Padrão de venda rápida no TCGPlayer |
| Graded | Excluído (PSA/BGS/CGC) | TCGPlayer market price compara cartas cruas; graded tem precificação própria |
| Preço mínimo | ≥ **$10 USD** | 30% de $5 = $1.50, não cobre frete/taxas |
| Margem bruta | ≥ **30%** | Absorve ~15% taxas eBay/Amazon + frete + câmbio |
| Moeda | EUR apenas | CT permite sellers em USD/GBP; ignorados por ora para simplicidade FX |

## Fluxo de dados (runtime)

1. **Lista expansões** — 1 call: `GET /expansions` (cacheada)
2. **Para cada set escolhido:**
   - `GET /blueprints/export?expansion_id=X` — todas as cartas-molde do set
   - `GET /marketplace/products?expansion_id=X&language=en` — todos os listings EN de uma vez (muito mais eficiente que por blueprint)
3. **Parse + filtros locais** — NM, não-graded, preço, dedup por `(blueprint, seller, condição)` mantendo menor preço
4. **Para cada listing filtrado:**
   - Busca preço TCG Player via pokemontcg.io (cacheado 24h)
   - Converte EUR→USD via ECB (cacheado 12h)
   - Calcula margem bruta e líquida (com frete estimado)
5. **Ordena por margem desc → exporta .xlsx**

## Colunas da planilha

| Coluna | O que é | Interpretação |
|---|---|---|
| Card Name, Set, Nº | Identificação da carta | — |
| Condição / Idioma | Sempre NM / EN com filtros padrão | — |
| Preço CT (EUR) | Preço do seller no CardTrader | Custo de aquisição antes de frete |
| Preço CT (USD) | Convertido pelo câmbio do dia | Base de comparação |
| **TCG Market (USD)** | Preço market do TCGPlayer | Referência de venda nos EUA |
| **Margem %** | `(TCG - CT) / TCG` | Desconto em relação ao mercado US |
| Margem $ | `TCG - CT` em dólares | Lucro bruto por unidade |
| **Net Margin %** | Margem após frete estimado | Realidade pós-logística |
| Qtd | Estoque do seller | Escalabilidade da compra |
| Foil | Se é holo/foil | Pode alterar precificação TCG |
| Seller / Tipo / Hub | Reputação e envio | Hub = envio centralizado CT (+rápido) |
| Link CardTrader | URL direta da carta | 1 click e tá lá |

## Agendamento (cron/Task Scheduler)

**Recomendação:** rodar 2x/dia, manhã e tarde. CardTrader refresca com frequência, mas 2x/dia pega as melhores janelas antes dos concorrentes.

### Linux/macOS (cron)

```bash
crontab -e
```

Adicionar:
```cron
# Scan CardTrader 09:00 e 17:00 BRT
0 9,17 * * * cd "/path/to/CardTrader Scanner" && /path/to/.venv/bin/python cardtrader_scanner.py >> scanner.log 2>&1
```

### Windows (Task Scheduler)

Criar tarefa com ação:
- Programa: `C:\caminho\para\.venv\Scripts\python.exe`
- Argumentos: `cardtrader_scanner.py`
- Iniciar em: `C:\caminho\para\CardTrader Scanner`

### VPS (recomendação para 24/7)

Hetzner CX11 (€4.50/mês) ou DigitalOcean Basic ($6/mês):
- Ubuntu 24.04, Python 3.12+
- `systemd` timer em vez de cron (logs melhores, retry)
- Planilhas via `rsync` ou upload S3/GDrive pro vault

## Custos operacionais

| Item | Custo |
|---|---|
| CardTrader JWT | **Grátis** |
| pokemontcg.io | **Grátis** (20k req/dia com key) |
| Frankfurter FX | **Grátis** (BCE) |
| VPS (opcional) | **€4.50/mês** (Hetzner CX11) |
| JustTCG (alternativa premium) | **$19-49/mês** |
| **Total mínimo** | **€0-5/mês** |

## Troubleshooting

| Erro | Causa provável | Solução |
|---|---|---|
| `CT_JWT não definido` | `.env` não preenchido | Copiar `.env.example` → `.env` e colar token |
| `401 Unauthorized` | Token expirou ou inválido | Gerar novo em CardTrader Settings |
| `429 Too Many Requests` | Rate limit | Aumentar `REQUEST_DELAY_CT` no código |
| `pokemontcg.io erro 403` | Sem API key → limite 1k/dia batido | Criar conta grátis e preencher `POKEMONTCG_API_KEY` |
| Lista vazia de oportunidades | Threshold alto demais / filtros restritivos | `--threshold 0.25` ou `--min-price-usd 5` pra ver se gera volume |

## Próximos passos

- [x] MVP single-file com filtros do usuário
- [x] Pluggable pricing provider (pokemontcg, justtcg, tcgplayer)
- [x] Cache SQLite (blueprints + preços + FX)
- [x] Export .xlsx com formatação condicional
- [ ] Export automático para Google Sheets (via `gspread`)
- [ ] Notificação Telegram ao encontrar oportunidade > 40%
- [ ] Integração com workflow N8N (webhook na conclusão)
- [ ] Filtro por reputação de seller
- [ ] Match manual override: tabela `user_matches` para casos onde match automático falha
- [ ] Suporte a MTG, One Piece, Lorcana (só mudar `CT_POKEMON_GAME_ID`)

## Relacionados

- [[MYP Arbitrage Scanner - Projeto|Scanner MYP]] — fluxo inverso (Brasil → US)
- [[Estratégia — Scanner Automatizado MYP Cards|Estratégia geral de arbitragem]]
- [[GUIA - Como Rodar o Scanner]] — passo a passo MYP, muita coisa reutilizável

## Histórico

| Data | Versão | Evento |
|---|---|---|
| 2026-04-20 | v1.0 | Projeto criado. MVP com pokemontcg.io, cache SQLite, 3 providers pluggable, filtros NM/EN/não-graded/≥$10, margem 30% default |
