# CardTrader Scanner Stack — Changelog

Mudanças cumulativas do `cardtrader_scanner.py` + `cardtrader_postprocess.py`.
Sob git desde 2026-05-13 (`matheuscllm-lgtm/card-trader-scanner`); CHANGELOG
mantido como narrativa adicional além dos commits.

## 2026-05-17 — Scanner v2.6 (partial JSONL checkpoint crash-recovery)

Motivação: incidente weekly local 2026-05-17 17:56→20:21. Scanner crashou
mid-run; 686 sets de dados ficaram in-memory e viraram pó. Output XLSX
nunca chegou a `wb.save()`. Padrão estrutural: scanner v2.5 manteve
`opps: list[Opportunity]` em memória até o fim do `scan()` antes de
gravar XLSX. Single point of failure crítico em runs longas (full weekly
~5-6h, 832 expansões).

### Scanner

- **NOVO:** classe `CheckpointWriter` (append-only JSONL writer)
- **NOVO:** flag `--checkpoint-every N` (default 10, 0 desativa)
- Path sidecar: `<output_path>.checkpoint.jsonl` (próximo do XLSX final)
- Formato linha-a-linha: `scan_header` + `set_complete` + `opportunity`
  + `scan_complete`. Última linha incompleta é descartável em parse.
- Write protocol: `f.write() + f.flush() + os.fsync(f.fileno())` síncrono
  per-set. Garante write-through ao disco antes de continuar próximo set.
- `scan()` agora itera o generator de `scan_expansion()` e grava cada
  Opportunity NO MOMENTO do yield (antes era `opps.extend(generator)` que
  esperava generator esgotar — perdia tudo em crash mid-set).
- `scan_complete` ausente no JSONL = sinal de crash; recovery flagueia.

### Scripts

- **NOVO:** `scripts/recover_from_checkpoint.py` — standalone CLI que
  parseia `.checkpoint.jsonl`, reconstrói `Opportunity` + `Listing`,
  reusa `export_xlsx()` do scanner module pra gerar XLSX equivalente.
  Flags: `--checkpoint`, `--output`, `--min-net-margin`. Skipa linhas
  inválidas com warning. Loga "Recovered N opportunities across M sets".
- **NOVO:** `scripts/test_checkpoint_crash_recovery.py` — regression
  suite com 18 asserts cobrindo: writer order, recovery clean checkpoint,
  recovery com linha truncada (simula crash), recovery de arquivo vazio.
  Roda em ~2s sem network call.

### Smoke test validado

`--sets sfa --threshold 0.30 --validate-top 5 --checkpoint-every 1`:
checkpoint sidecar com 5 linhas (header + 2 opps + set_complete + scan_complete),
recovery regenera XLSX com mesmas 2 opportunities (margens scan-time
idênticas; validation per-blueprint requer re-scan pq roda após o write).

### Limitações conhecidas / v2.7 candidates

- FX rates (usd_brl/eur_brl) não estão no header → recovery grava 0.
  Mover pra header é trivial (next pass).
- Validation per-blueprint state não está no checkpoint pois roda DEPOIS
  do scan loop. Pra preservar, mover write_opportunity post-validation
  ou emitir update-events. Tradeoff: per-set crash safety vs validated
  state preservation. Default escolha = crash safety > validated.

## 2026-05-16 — Release v2.0 (postprocess simplificado + scanner v2.5)

Decisão arquitetural do operador 2026-05-16: "objetivo CT é cartas mais
baratas que TCG nos padrões desejados, remover heurísticas subjetivas,
adicionar análise mecânica de compra".

### Postprocess v1.5 → v2.0

- **REMOVIDO:** bucket CORE/HYPE/DEAD, fundamental subjetivo (iconicidade/
  meta/chase tier hardcoded), long_term tier, coluna `Acao` derivada
- **ADICIONADO:** Chase Tier objetivo (TOP/MID/MODEST/BULK) baseado em
  rarity oficial PokemonTCG; Fundamental Score (0-100) derivado só de
  métricas objetivas (chase + net_margin + lucro + validation); Decisão
  mecânica (COMPRA/REVISAR/NÃO) + Porque (1 linha)
- **REDUZIDO:** 10 sheets → 3 (Deals, All Listings, Summary)

Thresholds default (CLI-tuneável):
- COMPRA: net ≥25% AND lucro ≥R$50 AND chase ≥MID AND validation OK AND NOT TG##
- NÃO: chase BULK OR net <20% OR STALE OR TG##
- REVISAR: zona cinza

Respeita `feedback_no_purchase_decisions`: Decisão é regra reproduzível,
não opinião Claude. Operador define thresholds via CLI.

Math preservada (`ct_margin_formula`): custo = preço × 1.06, frete = 0.

Arquivos:
- `cardtrader_postprocess.py` agora é v2.0 (era v1.5)
- `cardtrader_postprocess_legacy_v1.5.py` preserva v1.5 pra rollback

### Scanner v2.4 → v2.5

- **ADICIONADO:** coluna `Rarity` no XLSX raw, persistida de
  `bp.fixed_properties.pokemon_rarity` (schema descoberto 2026-05-16
  via inspect — NÃO está no campo raiz `rarity`)
- Permite postprocess calcular Chase Tier preciso (TOP/MID/MODEST/BULK)
  em vez de cair em proxies frágeis (markup tier, supranumerary, TG##)

### Workflows

`daily-scan.yml` e `weekly-scan.yml` atualizados:
- CLI antes: `--core $XLSX --hype $XLSX --dead $XLSX --output ...`
- CLI agora: `--input $XLSX --output ...` (uma chamada só)

### Sequência operacional 6-decisões definida

Roadmap pra maximizar discovery:
1. ✅ Consolidar v2 como production (este commit)
2. Weekly scan completo LOCAL overnight (~5-6h) — pendente
3. Triagem manual + calibrar thresholds
4. Liquidez gate (firecrawl eBay sold count)
5. Daily refinado com 15-20 sets calibrados do weekly
6. Cross-MYP integration (`merge_myp_ct.py` automático)

## 2026-05-15 — Postprocess v1.5 + ops (timeout, quota, hyperlinks, TG##)

Noite de hardening. Operador trabalhando overnight + Excel MCP adicionado
ao toolkit pra audit XLSX sem cair em `venv+pandas` toda vez.

### Postprocess (v1.4 → v1.5)

- **Card Name hyperlink** (commit `62fba69`): coluna `Carta` em todas as
  sheets que listam cartas (Decisao Rapida, CORE/HYPE/DEAD buckets, Top
  Approved, Final Action List) vira hyperlink azul sublinhado apontando
  pra URL CardTrader. Operador-pedido: 1-clique abre produto em vez de
  copy/paste. 32 hyperlinks gerados no relatorio 2026-05-15.
- **TG## auto-filter** (commit `09929f5`): cartas Trainer Gallery (`^TG\d+`
  no card_number) viram automaticamente `MANUAL REVIEW` com motivo
  `trainer_gallery_potential_fp` antes de qualquer check de margem.
  pokemontcg.io reference price infla 5-10x nessas cartas (~76% historic
  FP rate). Antes era operator-side, agora automatizado.
- **Bonus alias fixes**: `COLUMN_ALIASES['card_number']` ganhou `Nº`/`No.`
  e `COLUMN_ALIASES['link_ct']` ganhou `Link CardTrader`/`CardTrader URL`/
  `CardTrader Link`. Antes scanner emitia esses nomes display e o
  postprocess não normalizava → Decisao Rapida mostrava `No`/`Link CT`
  vazios em algumas sheets.

### Ops / infra

- **Cron daily-scan desabilitado** temporariamente (commit `67b3cb9`):
  cron `0 11 * * *` (08:00 BRT) comentado in-file. Instrucoes de reativação
  preservadas no YAML.
- **Workflow `timeout-minutes` 30 → 60** (commit `2a9a413`): run
  25898522951 cancelado em 30:09 com 5/10 sets processados (~1480 listings
  priced). Pricing rate medido 2-10 listings/s; total realista 45-55min.
  Calibração documentada em memória `ct_scan_timeout_calibration`.
- **GH Actions quota exhausted** (memória `gh_actions_quota_exhausted`):
  free tier 2000min/mês bateu 2026-05-15. Cross-scanner — bloqueia também
  `myp-arbitrage-scanner` (mesma conta `matheuscllm-lgtm`). Reset
  esperado 2026-06-01. Mitigação tática: scans LOCAIS via venv com
  `.env`. Decisões longer-term pendentes (upgrade plan / public repo /
  self-hosted runner).

### Delivery

Scan local 01:47-02:16 BRT (29min, 10 sets canônicos):
- 1 BUY NOW (CORE): **Milcery scr 152** EN, seller DMB Direct (non-VAT
  +20%), CT R$58.31 → TCG R$88.05, margem líq 29.8%, lucro R$26.24
- Audit 100%: TG## 0 leaks, margens >100% 0, Hub fee 6% paridade
  confirmada, 10 sets cobertos
- `cardtrader_relatorio_2026-05-15.xlsx` com hyperlinks (commit `992895e`
  delivery + re-gerado pós-hyperlink em `62fba69`)

### Pendência v2.4 ainda aberta

- Per-set timeout dinâmico (kill após X min sem progresso em UM set)
- Auto skip-list pra sets sem cobertura pokemontcg.io conhecida
- Cap de 404s consecutivos antes de bailout

Timeout global 60min é workaround tático, não solução estrutural — um
único set hanging ainda pode queimar todo o budget.

## 2026-05-14 — Scanner v2.3.1 — Progress logging no pricing loop

CT run no GH Actions (run 25838570927) ficou silenciosa por 24m53s
processando `asc` (Ascended Heroes) após o filter step, sem nenhum log
de progresso. Cancelada manualmente. Causa provável: pokemontcg.io tem
cobertura ruim para sets muito recentes (asc é maio/2026), gerando
muitas queries lentas/falhadas sem feedback.

### Scanner

- Loop de pricing (`Scanner.scan_expansion`, ~linha 920) agora emite
  `INFO: Pricing progress: i/total listings consultados` a cada 50
  listings + no fim. Permite detectar hangs em tempo real (cron + UI
  do GH Actions ou tail do log local).
- Sem mudança de comportamento ou performance — só observabilidade.

### Pendência v2.4 (NÃO APLICADA AINDA — requer design)

- Timeout per-set (kill após X min sem progresso)
- Cap de 404s consecutivos do pokemontcg.io antes de bailout
- Skip-list automática pra sets sem cobertura conhecida (asc, me*, etc)

## 2026-05-12 (noite) — Scanner v2.3 — Alinhamento Hub fee

Auditoria pós v2.2 detectou que o scanner ainda calculava `real_*_margin_pct`
sem aplicar Hub fee, enquanto o postprocess aplicava 6% via `live × 0.06`.
Resultado: scanner stdout/XLSX bruto era ~6pp otimista, só o relatório
consolidado refletia o custo real. Operator clarificou modelo:
**custo real = preço do site × 1,06** (média operacional de Hub fee +
marketplace fee + payment processing que aparecem em algumas listagens e
em outras não).

### Scanner (`cardtrader_scanner.py`)

- **HUB_FEE_RATE = 0.06** promovido a constante (linha ~146-152)
- **CLI `--hub-fee X`** (default 0.06; paridade com `postprocess --hub-fee`).
  Auto-conversão `> 1.0` (`6` → `0.06`) como `--threshold` / `--min-net-margin`.
- **`Scanner.__init__`** aceita `hub_fee_rate` parametrizado.
- **`validate_per_blueprint`** linhas ~1037-1046:
  ```python
  hub_fee_brl = live_brl * self.hub_fee_rate
  custo_real  = live_brl + hub_fee_brl
  o.real_margin_pct      = (tcg_brl - custo_real) / tcg_brl
  o.real_net_margin_pct  = (tcg_brl - custo_real - shipping) / tcg_brl
  o.real_lucro_brl       = tcg_brl - custo_real - shipping
  ```
- **Stats sheet** do XLSX inclui `hub_fee_rate`.
- **Log**: linha "Hub fee aplicado no recalc REAL: 6% (custo = site_price × 1.06)" emitida após o scan.

### Impacto observado (scan 2026-05-12 21:28 v2.2 → re-run v2.3)

| Carta | v2.2 (sem Hub) | v2.3 (com Hub 6%) | Lucro v2.2 | Lucro v2.3 |
|---|---|---|---|---|
| Dachsbun ex (scr 169) | 30.1% net REAL | 25.9% net REAL | R$114.80 | R$98.83 |
| Milcery (scr 152, DMB) | 26.0% net REAL | 21.6% net REAL | R$20.66 | R$17.14 |

Margens caem ~4-5pp em deals típicos. Alguns deals borderline 20-22% caem
abaixo do `--min-net-margin 0.20` (esperado e desejado — eram falsos
positivos da v2.2).

### Modelo final unificado (scanner + postprocess)
- `live_brl` = preço per-blueprint (página do site no idioma do operador)
- `custo_real = live_brl × (1 + hub_fee)` (hub_fee = 0.06 default)
- `frete` = 0 (Hub depot consolida); override via `--shipping-brl`
- `lucro = tcg_market_brl - custo_real - frete`
- `margem_revenue` = `lucro / tcg_market_brl` (scanner convention)
- `margem_cost` = `lucro / custo_real` (postprocess convention — não confundir)

## 2026-05-12 — Scanner v2.2 / Postprocess v1.4

Sessão de auditoria completa: 9 bugs encontrados no scanner via revisão
C/H/M (Critical/High/Medium), 9 bugs encontrados no postprocess via mesma
metodologia. Modelo operacional unificado: consolidação no Hub depot,
custo = preço CT × 1.06, frete não modelado.

### Scanner (`cardtrader_scanner.py`)

**Críticos**
- **C1**: tier markup 30-45% reclassificado como `Alto markup` /
  `VALIDATED_MARKUP`. Antes vinha como `Anômalo (+30%)` /
  `PRICE_CHANGED` e era filtrado como erro de preço. Validação ao vivo
  com Horsea TheDragonsVault confirmou tier legítimo. Linhas ~885-905.
- **C2**: `clean_collector_number()` aplicado no fallback `bp.version`
  no `_parse_listing`. Antes, quando `props.collector_number` e
  `bp.collector_number` vazios, a string suja "Rare | 169/142" ia
  direto pro pricing. Linha ~680.

**Altos**
- **H1**: `--threshold > 1.0` e `--min-net-margin > 1.0` auto-convertem
  com warning. Resolve trap UX (`--threshold 25` interpretado como 2500%
  filtro impossível, zerava scans silenciosamente). Linhas ~1090-1106.
- **H2**: `market_price_usd()` agora aceita `foil=` e prioriza variante
  correta no pokemontcg.io. Antes priority fixa `holofoil > normal > RH`
  ignorava o foil flag do listing, gerando falso negativo em commons
  reverse holo. Linhas ~437, 512, 569, 583, 769. Cache key inclui foil.

**Médios**
- **M1**: filtro de `validation_status` sempre roda quando
  `validate_top > 0`, independente de `min_net_margin`. Antes, com
  `min_net_margin = 0` deixava `STALE`, `API_ERROR`, `PRICE_CHANGED`
  vazarem pro XLSX. Linhas ~1155-1183.
- **M2**: opps sempre re-ordenados por `real_net_margin_pct` desc após
  validação per-blueprint, não só quando `min_net_margin > 0`.
- **M3**: `SHIPPING_EUR_HUB/PROFESSIONAL/PRIVATE` promovidas a
  constantes top-level. Flag `--shipping-brl X` adicionada para override.
  `_estimate_shipping_brl(units=N)` amortiza por unidades.
- **M4**: `log.debug` + stat counter `skipped_exotic_currency` quando
  listing vem em moeda não BRL/EUR/USD (GBP/JPY/etc). Antes silenciava.
- **M5**: log de supranumerário quando `card.number > set.printedTotal`
  no resultado pokemontcg.io. Sinaliza SIR/SAR/HR pra revisão manual
  (padrão idêntico ao bug rarity="Comum" do scanner MYP).

**Modelo de consolidação (Hub depot)**
Confirmado por Matheus: cartas compradas acumulam no depósito CT na
Europa, ~100 unidades, então consolidadas e enviadas pro Brasil em
envio único. Frete daquele envio dilui per-card a ~R$0.30 → desprezível.

Consequências no scanner:
- `--shipping-brl` default = `0.0`
- `_estimate_shipping_brl` retorna o override (0 default)
- `_legacy_shipping_eur_estimate_unused` preservada como referência
- XLSX column "Net Margin % REAL c/ frete" → **"Net Margin % REAL"**
- TOP 5 console: sufixo " c/ frete (R$X)" só aparece quando override > 0
- Header docstring inclui seção "Modelo operacional"

### Postprocess (`cardtrader_postprocess.py`)

- **P-C1**: `gross_margin` agora usa convenção de MARGEM (lucro/TCG),
  não markup (lucro/CT). Antes filtros tipo `min_gross_margin: 0.30`
  significavam "30% markup" (~23% margem real) e a coluna exibia
  "Margem TCG %" com valor de markup → operador confundido.
- **P-C2**: custo efetivo = `live_brl * (1 + hub_fee_rate)`. Default
  6%. Frete não modelado (consolidação Hub depot — explicado acima).
  Antes ignorava frete real (R$29/listing) sem dizer.
- **P-H1**: `markup_tier` match usa substring (`"hub" in tier`) em vez
  de exato. Antes scanner produzia `"Hub (+6%)"` mas postprocess
  testava `== "hub"` → todo row caía no else.
- **P-H2**: status `"price_changed"` reconhecido como anomalous.
  Antes testava `"anomalo"` que scanner nunca produzia.
- **P-M1**: `PRODUCTIVE_SETS` inclui `asc`, `meg`, `pfl` (sets 2026).

### Sync vault ↔ Scripts

Cópias de `cardtrader_postprocess.py` em vault e `C:\Users\mathe\Scripts\`
sincronizadas (`diff -q` retorna idênticas). Antes divergentes em 13
linhas (vault tinha fix v1.3 que Scripts não tinha).

---

## 2026-04-29 — Scanner v2.1 / Postprocess v1.3

Histórico capturado em CLAUDE.md do vault e memórias de Claude. Não
detalhado aqui — esta entrada é o ponto de partida do diff acima.
