---
tags:
  - tcg
  - arbitragem
  - automação
  - cardtrader
  - pokémon
  - projeto-ativo
date: 2026-04-20
updated: 2026-06-05
status: ativo
version: v2.11
---

# CardTrader Arbitrage Scanner — Pokémon TCG

> 📖 **Para o Matheus (leitura simples):** este é o **manual técnico completo**.
> Se você só quer entender o que o programa faz e como rodá-lo, o lugar certo é
> o **`CLAUDE.md`** (guia em linguagem acessível, com glossário). Aqui embaixo há
> detalhe profundo: as seções marcadas com **🔧** são mais avançadas — pode pular
> sem dó. As seções "Instalação", "Como rodar", "Saída" e "Resolução de
> problemas" foram escritas pra você conseguir acompanhar.
>
> *Termos técnicos que aparecem (repo, branch, venv, flag, token…) estão
> explicados no glossário do `CLAUDE.md`.*

## Objetivo

Achar **oportunidades de compra-e-revenda** ("arbitragem") entre o site europeu
**CardTrader** (preços em euro) e o preço de referência dos EUA (**TCG Player**).
O foco é em cartas avulsas **em inglês, estado Near Mint** ("quase perfeitas"),
**não graduadas** (sem aquele case de avaliação tipo PSA), com lucro **≥ 30%** e
preço mínimo de **$10**.

**Tese:** CardTrader agrega sellers da UE inteira (Itália, Espanha, França, Alemanha…), muitos com precificação desatualizada ou em recuperação cambial. Cartas valorizadas rapidamente no mercado US frequentemente levam semanas para reprecificar na UE → janela de arbitragem.

## 📐 Fórmula canônica da margem (padrão único)

**Decisão operacional 2026-05-12 (reafirmada 2026-05-14):** o cálculo de margem é simples e inequívoco. Sem variações condicionais, sem caso-a-caso por seller.

```
custo  = preço_da_página × 1.06          ← 6% Hub fee médio (constante)
lucro  = TCG_market − custo
margem = lucro ÷ TCG_market              ← divide por preço de venda (revenue basis)
frete  = 0                                ← modelo Hub depot consolida ~100 cards
```

**Variáveis:**
- **preço_da_página** = exatamente o que aparece na ficha do produto no CardTrader (validado per-blueprint, não per-expansion RAW). É o que o comprador paga no checkout, sem deduções.
- **6% Hub fee** = constante assumida como média de fees variáveis CT (Hub fee + marketplace + payment processing). Alguns sellers cobram, outros não. Em vez de modelar caso a caso (instável), assume-se 6% flat.
- **TCG_market** = preço Market do TCGPlayer (em USD, convertido pra BRL via câmbio Frankfurter do dia).
- **frete = 0** porque o modelo operacional é consolidar ~100 cards no Hub depot CT antes do envio único pro Brasil; o frete dilui a ~R$0,30/card e é tratado como custo afundado fora deste cálculo.

**Aplicação no código (paridade alinhada em v2.3):**
- Constante: `HUB_FEE_RATE = 0.06` em `cardtrader_scanner.py`
- Função: `validate_per_blueprint()` linhas ~1067-1071 — `custo_real = live_brl × 1.06`; `real_margin_pct = (tcg_brl − custo_real) / tcg_brl`
- Override (raro, debug): `--hub-fee 0` desativa o ajuste; produz margens ~6pp otimistas vs realidade.
- Postprocess: `cardtrader_postprocess.py` aplica o mesmo `× 1.06` antes da classificação BUY NOW/REJECT (BucketConfig).
- GH Actions: workflow herda default `HUB_FEE_RATE = 0.06` sem precisar passar flag.

**O que NÃO entra no cálculo:**
- ❌ Fee CT específica por seller (assumida no 6% médio)
- ❌ Frete CT→Brasil (modelo Hub depot, custo afundado)
- ❌ Taxas eBay/Amazon de revenda (são da etapa de venda no TCGPlayer, não do scanner de compra)
- ❌ Câmbio variável (já capturado em `usd_brl` do dia via Frankfurter)
- ❌ Markup tier do seller (REAL/Hub+6%/non-VAT+20%) — esse é diagnóstico interno do scanner, não afeta a fórmula; serve só pra garantir que `preço_da_página` é o que o navegador mostra.

**Diferença vs MYP scanner:** MYP usa `(tcg − custo) / custo` (ROI sobre capital). CT usa `(tcg − custo) / tcg` (gross margin sobre receita). Margens não são diretamente comparáveis: CT 15% gross ↔ MYP 17.6% ROI; CT 30% gross ↔ MYP 42.9% ROI. Equivalência: `roi = gross / (1 − gross)`.

## 🔧 Vício conhecido da CT API (técnico — pode pular)
<!-- Resumo simples: o site tem dois jeitos de informar o preço, e um deles vem
     "cru" (sem a taxa). O programa confere os melhores candidatos no preço REAL
     de compra pra não cair em falso positivo. Detalhe abaixo é pro assistente
     de IA / quem mexe no código. -->

A CT API tem **2 endpoints que retornam preços DIFERENTES pra mesma carta**:

| Endpoint | O que retorna | Pra que serve |
|---|---|---|
| `/marketplace/products?expansion_id=X` (per-expansion) | **Preço RAW do seller**, moeda original, **sem markup CT** | Scan rápido (1 chamada/set inteiro) |
| `/marketplace/products?blueprint_id=X` (per-blueprint) | **Preço FINAL com markup embutido** (+6% Hub / +20% non-VAT), na moeda da conta | É o que o navegador mostra ao comprador |

**Sintoma se ignorado:** scanner v1.6 (sem validação per-blueprint) reportava margens 5-20% otimistas. Em scan 2026-04-29: 21 oportunidades reportadas → **só 4 sobreviveram** pós-markup. Taxa de falso positivo: **76%**.

**Markup tiers observados:**
- **+6% (tier Hub / EU normal):** BlackFlameGreece, BTcards, CardsHive, -Retro-Empire-Gaming, UniverseTCG, The Dragoncard
- **+20% (tier non-VAT export / extra-EU):** TheDragonsVault, A2Z TCG, Artkillary, Nostalgium, Fun Gs collections, Gabrielkatsaros95
- **Sellers ausentes no per-blueprint:** alguns não shipam pro BR ou são filtrados server-side. Aparecem como STALE/unreachable.

**Mitigação (v2.0+, integrada no scanner desde 2026-04):**
1. Scan inicial via per-expansion → candidatos com margem bruta ≥ `--threshold`
2. **Validação per-blueprint nos top-30** → pega `live_brl` real do checkout
3. Recalc margem com `× 1.06` em cima do live_brl
4. Filtro final `--min-net-margin`

Função: `validate_per_blueprint()` em `cardtrader_scanner.py` linhas ~973-1080. Stats da sheet "Stats" do XLSX incluem `validated_real` vs `validated_markup` vs `stale`.

**Por que ainda usar a API CT apesar disso:** alternativa seria scraping HTML de milhões de listings em milhares de sellers. Inviável + bloqueado por anti-bot. A API entrega JSON em segundos — o vício do markup é mitigado por chamar BOTH endpoints (per-expansion pra eficiência, per-blueprint pra validar top candidatos).

## Diferença vs Scanner MYP

| Aspecto | MYP Scanner | CardTrader Scanner |
|---|---|---|
| **Fonte de compra** | MYP Cards (Brasil, BRL) | CardTrader (UE, EUR) |
| **Método de coleta** | Web scraping + cloudscraper | API oficial JSON (JWT) |
| **Frete pro fulfillment US** | ~R$ 80-150 por lote | ~€5-15 por pacote (CT Hub) |
| **Rate limit** | Fragilizado por CloudFlare | 10 req/s oficial, tranquilo |
| **Latência de preço** | Diária (site BR) | Horas (API direta) |
| **Margem alvo** | 35% (absorve frete BR→US maior) | 30% (frete UE→US menor) |

## 🔧 Arquitetura (técnico — pode pular)

<!-- Diagrama de como o programa conversa com os sites de preço. Referência
     pra quem desenvolve. -->

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
# Ir para a pasta do scanner (no disco local — desde jun/2026 não é mais no Drive)
cd /c/Users/mathe/card-trader-scanner

# Criar a "caixinha isolada" de ferramentas (virtualenv / venv)
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

**Rodar o scan local do dia a dia** (10 coleções curadas):

```bash
# Bash (Git Bash / WSL / Linux):
set -a; source .env; set +a            # carrega seu token do arquivo .env
export PYTHONIOENCODING=utf-8
.venv/Scripts/python.exe cardtrader_scanner.py \
  --sets sfa scr par paf tef twm ssp dri blk jtg \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output "outputs/cardtrader_scan_local_$(date +%Y%m%d_%H%M).xlsx"

# Depois o relatório organizado (postprocess).
# IMPORTANTE: --input e --output são OBRIGATÓRIOS (interface v2; o antigo
# --core/--hype/--dead foi aposentado).
.venv/Scripts/python.exe cardtrader_postprocess.py \
  --input  outputs/<scan.xlsx> \
  --output outputs/cardtrader_relatorio_$(date +%Y-%m-%d).xlsx
```

Tempo estimado ≈ 30min (medido em 10 coleções, ~2800 itens). Para o **scan
completo** (todas as ~832 coleções), troque `--sets …` por **`--all-sets`** —
mas aí leva horas; rode em segundo plano.

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

## 🔧 Fluxo de dados (técnico — pode pular)

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

> **Status 2026-06-05:** **não há agendamento automático.** Os dois fluxos na
> nuvem (`daily-scan.yml` e `weekly-scan.yml`) rodam **só quando você manda**
> (dispatch manual), por decisão sua — sem horário fixo. A cota mensal de
> processamento na nuvem (GitHub Actions) voltou ao normal em 01/06. Os scans
> avulsos rodam **no seu computador** (pelo `.venv` + `.env`). *("cron" = um
> agendador que dispara tarefas em horários fixos.)*

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

## Resolução de problemas (o que fazer quando dá erro)

| Erro (mensagem na tela) | Causa provável | Solução |
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
