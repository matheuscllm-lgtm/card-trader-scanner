# Session Handoff — CT Scanner (diário de bordo)

> **O que é este arquivo (pro Matheus):** é o **diário de bordo** do projeto —
> um registro do que foi feito em cada dia de trabalho, pra quem retomar (você
> ou o assistente de IA) saber de onde continuar. As anotações mais abaixo são
> **técnicas** (escritas pro assistente); use o resumo logo abaixo pra
> acompanhar sem precisar decifrar o jargão. Pra entender o programa em si, leia
> o **`CLAUDE.md`** (guia simples).

## 📍 Onde o projeto está agora (em linguagem simples)

- **O programa funciona e está pronto pra rodar** no seu computador
  (`C:\Users\mathe\card-trader-scanner`). A pasta antiga no Google Drive foi
  apagada (estava corrompendo os arquivos de controle).
- **Versão atual: v2.11.** Ela ganhou há pouco a opção de **rastrear todas as
  coleções de uma vez** (pro levantamento semanal) e de **mostrar resultados
  parciais enquanto o rastreio longo ainda roda**.
- **Como rodar:** está explicado em linguagem simples no `CLAUDE.md` e, com mais
  detalhe, no `README.md`.
- **O que ainda está em aberto:** fazer um rastreio completo (semanal) pra
  calibrar os números reais; trocar uma senha de acesso antiga por segurança.
  Nada disso impede o uso normal do dia a dia.

> **Última atualização:** 2026-06-05 (saneamento + linguagem acessível nos docs).

---

> ⬇️ **Daqui pra baixo são as anotações técnicas (registro por data).**

---

## 2026-06-17 — Loop de melhoria contínua (rodada 1)

> **Contexto:** o operador pediu um `/loop` que, a cada rodada, faz **1 melhoria
> pequena e focada** no scanner, sempre verde e com PR. Tudo no branch
> `claude/keen-faraday-w3bq9j`, escopo restrito a este repo. Cadência ~45min via
> heartbeat (`Monitor`) — neste ambiente remoto não há `CronCreate`/`ScheduleWakeup`,
> então a recorrência é melhor-esforço (pode parar se o container for reciclado no
> ocioso; nesse caso, basta pingar pra retomar).

**Rodada 1 — CI de testes offline (`.github/workflows/tests.yml`):**
- Não havia CI rodando a suíte; ela só era validada à mão. Agora todo push/PR roda
  smoke `--help` + `pytest tests/` (90) + `scripts/test_*.py` (8) — offline, sem
  secret. Protege automaticamente as próximas rodadas do loop.
- Gate verde local antes de commitar. Sem mudança de comportamento do scanner.

**Backlog do loop (vivo — marcar conforme for fazendo):**
- [x] CI de testes offline (gate automático) — rodada 1.
- [ ] Flag de **liquidez** no relatório: nº de cópias EN-NM no/perto do preço do deal
  (1 cópia = alto risco de staleness). Origem: auditoria 2026-06-08 #3.
- [ ] **Re-check ao vivo** do preço das top-N do relatório (staleness).
- [ ] Atalho/flag pra **pular back-catalog** (foco em sets recentes; back-catalog deu 0 deal).
- [ ] Investigar cobertura **crz/Galarian Gallery** (~30% não precificadas).
- [ ] (fallback) robustez/cobertura de teste/limpeza identificada lendo o código.

---

## 2026-06-08 — Auditoria de cobertura (sessão de execução, SEM mudança de código)

> Sessão de **investigação/auditoria** no Claude Code on the web (container
> efêmero). `.env` com `CT_JWT` criado local (gitignored, nunca commitado). Sem
> `POKEMONTCG_API_KEY` → throttle pokemontcg.io ~30/min.

**Achados (todos checados com dado real nesta sessão):**

1. **`--min-price-usd 25` foi erro de método.** Subi o piso pra fugir do rate
   limit → escondeu a faixa US$10–25, onde mora a maioria dos deals. Evidência:
   mesmos sets modernos = **12 candidatos a $10 vs 2 a $25**. → **Sempre o piso
   padrão (~$10).**

2. **Back-catalog = mercado eficiente.** Era Sword & Shield inteira (17 sets,
   ~1.000 cartas precificadas) deu **0 deal acionável** tanto a ≥30% quanto a
   ≥20%/$10. → **Não varrer sets antigos**; deal mora em lançamento novo
   (reafirma o foco em `PRIORITY_SET_CODES`).

3. **Ground-truth (Arceus VSTAR brs 176):**
   - TCGplayer (referência) **bate**: scanner $15.45 vs real $15.63 (#176 Rainbow
     Rare, via pokemontcg.io set `swsh9`). Carta + variante certas. Fonte OK.
   - CardTrader (compra) estava **defasado**: scan R$54 → validação R$62 →
     **real-agora R$75** (EN NM mais barata) → custo R$75×1,06 = R$79,78 vs TCG
     R$79,09 = **prejuízo**. **Liquidez/staleness é o calcanhar de Aquiles** (a
     cópia barata flaggeada some). Reafirma roadmap #4 (liquidity gate).
   - Bônus: cópias mais baratas eram **italianas** (R$38) — scanner ignora de
     propósito (referência TCGplayer é inglesa). Design correto.

4. **`--all-sets` (839) inviável sem `POKEMONTCG_API_KEY`** numa sessão (~30/min,
   1k/dia sem key). `cache.db` ajuda em re-runs. `crz`/Galarian Gallery: ~30%
   não precifica (colisão de número → set mismatch, corretamente rejeitado).

**Outputs (gitignored, não versionados):** scan_principais, scan_sv, scan_swsh
(+`_t20`), scan_swsh_recent_p10, test_evs_p10, relatorios.

**Backlog "devagarinho" (melhorias pequenas, 1 por PR):**
- [ ] **Liquidity flag no relatório**: nº de cópias EN-NM no/perto do preço do
  deal (1 cópia = alto risco de staleness). Vem do achado #3.
- [ ] **Re-check ao vivo** do preço das top-N do relatório.
- [ ] **Atalho/flag pra pular back-catalog** (foco em sets recentes).
- [ ] Investigar cobertura **crz/Galarian Gallery** (~30% não precificadas).

---

## 2026-06-05 — Saneamento estrutural (PR #5 + docs fix)

- **Repo migrado pra disco local:** `C:\Users\mathe\card-trader-scanner` (clone
  limpo do GitHub). A pasta antiga no Google Drive foi **deletada** — o `.git`
  sincronizado corrompia refs (`desktop.ini` em 8 refs). **Não rode mais nada do
  Drive.** Ver memória `cardtrader_scanner_location` + `CLAUDE.md` na raiz.
- **PR #5 merged** @ `a3f152a`: `CLAUDE.md` (front door), `.gitignore` preventivo
  (`outputs/`, `logs/`, scratch `_*`), header `Versão v2.3 → v2.10`,
  `run_weekly_local.ps1 --per-set-timeout` parametrizado.
- **Worktree stale removido**, cópias soltas do `postprocess` deletadas (sobra
  canônico + a do monorepo como ref).
- **`.venv` recriado** (Python 3.12.10, deps de `requirements.txt`). Smoke-test
  OK (`scanner --help` exit 0, `postprocess --help`, imports OK). **Run-ready.**
- **PR #6 merged** @ `387cd40`: fix de docs — comando do postprocess era
  posicional no CLAUDE.md (CLI v2 exige `--input`/`--output`); quick-start do
  handoff apontava pro Drive deletado.
- **PR #7 merged** @ `33ef779` (**v2.11**): integra a feature que estava no
  branch `run-scan` (esquecida, validada no scan de 4h 06-02) re-aplicada sobre
  o main pós-saneamento: `--all-sets` (~832 exp, SV/curados primeiro) +
  `scripts/checkpoint_to_partial.py` (parciais ao vivo) + weekly.yml publica
  parciais no branch `scan-live`. Gatilho `push:run-scan` REMOVIDO (dispatch-only).
  Pendência: deletar branch remoto `run-scan` (harness bloqueou; operador roda
  `git push origin --delete run-scan`).
- **PR #8 merged** @ `b416da2`: `CLAUDE.md` reescrito em linguagem acessível pro
  operador (médico, não-programador) — termos explicados inline + glossário.
  Memória `feedback_docs_linguagem_acessivel` criada (padrão a estender aos
  repos irmãos). README + este handoff acessibilizados na sequência.

---

## 2026-05-29 — PR-G (BOM fix) + merge_myp_ct fix + daily run

- **PR-G mergeado em main** @ `39089d3` (local, **não pushed** — aguarda OK). `_read_skip_file_locked` (L1217) lê skip-list com `utf-8-sig` → tolerante a BOM. 6 testes novos + 23 suite. Worktree/branch limpos. Motivo: `Set-Content -Encoding utf8` no PS 5.1 grava BOM (EF BB BF) que crashava o scan na largada (`json.loads` rejeita BOM).
- **merge_myp_ct.py corrigido** (cópias `Scripts/` + `Documents/tcg-arbitrage-scanners/`): reconhece schema v2 "Deals" (`Preço CT`/`TCG`/`Net %`/`Lucro Líq`/`Validação`/`Link CT`), default `--ct-sheet`=Deals, aliases legados preservados. Testado contra dados reais.
- **PR-H mergeado+pushed** @ `a209bdd`: review de coerência (/gsd-review) — FIX1 conditional-format `Q2:Q`→`R2:R` (verde na margem REAL, não scan); FIX2 `number_format` indices +1 (eram off-by-one pré-coluna "Idioma" → `Net Margin REAL` saía como R$/`LIVE R$` como %); FIX3 recovery preserva `price_variant_used`. 5 testes novos + 28 suite.
- **Daily `CT_Daily_2026-05-29` COMPLETO** (exit=0, ~61min, 10 sets modernos, state-dir `%LOCALAPPDATA%`): **6 deals** (1 COMPRA Plusle#193 par net30%/R$81 [ground-truth validado]; 5 REVISAR — Minccino#182 tef ×2, Milcery#152 scr ×2, Shinx#135 paf — todos lucro<R$50). `outputs\daily_2026-05-29.xlsx`. Task unregistered.
- **PR-I mergeado+pushed** @ `ae137c3`: célula "Carta" agora traz nome+número juntos ("Minccino 182") nas sheets Deals+All Listings (postprocess `_combine_name_number`) — operador copia-e-cola no site de busca. Nº preservado, hyperlink mantido. 6 testes novos, suite 34.
- **Push:** `origin/main` @ `ae137c3` (PR-F + PR-G + PR-H + PR-I todos pushed). ✅
- **~~A verificar~~ RESOLVIDO 2026-05-30:** flag "Threshold COMPRA 20% vs 25%" era falso alarme. `build_summary` mostra `min_net_margin` (default 0.25, regra COMPRA) e `revisar_min_net` (default 0.20, zona cinza REVISAR) em LINHAS SEPARADAS — não há bug, confusão de leitura entre as 2 linhas.

---

## 2026-05-28 — PR-F mergeado em main + lições

**Estado de fechamento:**
- **PR-F mergeado e PUSHED** em `main` @ `47e10d4` (fast-forward de `4541fc3`). `origin/main` atualizado 2026-05-28 após gate de validação cumprido + OK explícito do operador.
- **PR-F = state-dir + heartbeat + flush per-listing (commit `0e46a73`) + skip-list TTL (commit `47e10d4`).** Tira estado mutável (cache.db, checkpoint, heartbeat, skip-list) do Google Drive → `%LOCALAPPDATA%\CardTraderScanner`. XLSX final continua no Drive.
- **Infra VALIDADA end-to-end** num scan real (`scr`/`sfa`, 2026-05-28): state-dir, heartbeat ao vivo, flush per-listing (`set_progress`), skip-list TTL formato `{reason, added_at}`, recovery set_progress-safe, Drive intocado. 17/17 unit tests + não-regressão.
- **LACUNA FECHADA (2026-05-28 22:30):** validação menor `--sets scr` completou ponta-a-ponta (`scanner=0 post=0`) e gerou `outputs\validate2_F_2026-05-28.xlsx` — 2 deals Milcery #152 scr (REVISAR, net 33-34%, lucro <R$50), todas as colunas do postprocess preenchidas (Decisão/Net%/Hub 6%/Validação), math conferida. **Gate p/ push CUMPRIDO.** Push aguarda apenas OK explícito do operador (salvaguarda auto-mode bloqueia push direto a main sem confirmação).

**Lições registradas:**
1. **Kill prematuro = erro de execução do sub-agente, NÃO evidência contra o patch.** O scan de validação estava saudável (heartbeat avançando `scr i=75/186`) quando um sub-agente interpretou mal um heartbeat momentaneamente parado como "travado" e matou. O F estava funcionando; a lacuna do postprocess é consequência do kill, não de bug do patch.
2. **Path com acento quebra `.ps1` em PowerShell 5.1.** O dir tem "Exportação" (ç/ã); embutir o path literal num `.ps1` lido por PS 5.1 corrompe os bytes → path inválido → task falha (`0xFFFD0000`) sem lançar python. Workaround: construir o segmento via `[char]0xE7 + [char]0xE3`, OU `New-ScheduledTaskPrincipal -LogonType Interactive`. (Também em memória `ct_scan_long_run_detached`.)
3. **Scans longos SEMPRE via Task Scheduler detached, trigger ONE-SHOT** (sem `-RepetitionInterval`). Crash silencioso 2026-05-27 (inline, terminal-pai morto) + re-disparo indevido da task recover (trigger recorrente). Ver `logs/INCIDENT-silent-crash-2026-05-27.md`.

---

## Estado atual

- **Repo:** `matheuscllm-lgtm/card-trader-scanner` `main` @ `4713249` (pushed) — PR-F→PR-L aplicados
- **Scanner:** **v2.10** + PR-F (state-dir/heartbeat/flush/skip-list-TTL) + PR-G (utf-8-sig BOM) + PR-H (number_format off-by-one + cond-format R2:R + recovery variant)
- **Postprocess:** **v2.x** + PR-I (Carta=nome+número) + PR-J (price hyperlinks) + PR-K (formato `(NNN/MMM)` MYP-style + 3 sheets novas: Top 50 Margin / Validate Manually / TCG Suspect) + PR-L (EXTREME_NET_PCT constant, _combine docstring, header docstring 6 sheets)
- **Postprocess:** **v2.0** (Chase Tier objetivo + Decisão mecânica + 3 sheets) — `cardtrader_postprocess.py`
- **Legacy preservado:** `cardtrader_postprocess_legacy_v1.5.py` (rollback se v2 mostrar regressão)
- **Hub fee paridade:** scanner ↔ postprocess intacta (6%)
- **Math:** sem shipping (modelo Hub depot, memória `ct_margin_formula`)
- **Crons:** todos removidos (sem agendamento, dispatch manual)
- **Quota GH Actions:** exhausted até 2026-06-01 — runs locais são o caminho até lá

## Pipeline v2 — output esperado

3 sheets no XLSX final:
- **Deals** — só COMPRA + REVISAR, ordenado por lucro líquido absoluto. Colunas: Decisão · Porque · Chase Tier · Score · Set · Carta (hyperlink) · Nº · Idioma · Preço CT · TCG · Net % · Lucro Líq · Validação · Seller · Link CT
- **All Listings** — universo completo (inclui NÃO), mesmas colunas
- **Summary** — métricas globais + thresholds usados + math

Decisão mecânica:
- **COMPRA** se net ≥25% AND lucro ≥R$50 AND chase ≥MID AND validation OK AND NOT TG##
- **NÃO** se chase BULK OR net <20% OR validation STALE OR TG## potencial FP
- **REVISAR** zona cinza (borderline 20-25% OU MODEST + alta margem)

Chase Tier de `rarity` (PokemonTCG oficial):
- **TOP** — Special/Illustration Rare, Hyper Rare, Secret Rare, SAR
- **MID** — Full/Alt Art, Rainbow/Gold Rare, Trainer Gallery, Ultra Rare, Double Rare
- **MODEST** — Holo Rare, Reverse Holo, Promo
- **BULK** — Common, Uncommon, Rare (não-holo)

## Quick-start retomada

```bash
cd /c/Users/mathe/card-trader-scanner   # repo local desde 2026-06-05 (não mais no Drive)
set -a; source .env; set +a
export PYTHONIOENCODING=utf-8
TS=$(date +%Y%m%d_%H%M)

# Daily scan (11 sets curados, ~30min)
.venv/Scripts/python.exe cardtrader_scanner.py \
  --sets sfa scr par paf tef twm ssp dri blk jtg asc \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --per-set-timeout 8 \
  --output "outputs/cardtrader_scan_local_${TS}.xlsx"

# Postprocess v2 (--input/--output OBRIGATÓRIOS, sem --core/--hype/--dead)
.venv/Scripts/python.exe cardtrader_postprocess.py \
  --input "outputs/cardtrader_scan_local_${TS}.xlsx" \
  --output "outputs/cardtrader_relatorio_$(date +%Y-%m-%d).xlsx"
```

**Weekly local (scan completo ~832 expansões, ~5-6h):** omitir `--sets`, bumpar `--validate-top 100`.

## Roadmap operacional (sequência 6-decisões 2026-05-16)

| # | Decisão | Status |
|---|---|---|
| 1 | Consolidar v2 como production | ✅ APLICADO (commit `e0281ba`) |
| 2 | Weekly local overnight (scope completo, first-time com Rarity real) | ⏸ Pendente operador dispatch |
| 3 | Triagem manual + calibrar thresholds reais | ⏸ Depende #2 |
| 4 | Liquidez gate (firecrawl eBay sold ≥3/90d) | ⏸ Depende #3 |
| 5 | Daily refinado com 15-20 sets calibrados | ⏸ Depende #3 |
| 6 | Cross-MYP integration (merge_myp_ct.py automático) | ⏸ Depende quota MYP reset |

## Pendências independentes

- **GH Actions quota** — reset 2026-06-01; decisão longer-term (upgrade vs public vs self-hosted) pendente
- **PAT GitHub plaintext** em `~/.claude.json` — rotação pendente (segurança)
- **14 connectores claude.ai** irrelevantes — desconectar via https://claude.ai/settings/connectors

## Memórias relevantes (auto-loaded via MEMORY.md)

- `session_2026_05_16_ct_v2_release` — sessão release v2 + sequência 6-decisões
- `feedback_autonomy_directive` — postura autônoma + escopo CT explícito
- `ct_scan_timeout_calibration` — pricing rate medido + v2.4 resolved
- `gh_actions_quota_exhausted` — diagnóstico + workarounds locais
- `scanners_no_schedule_2026_05_16` — política sem agendamento
- `ct_margin_formula` — custo = preço × 1.06, frete = 0
- `cardtrader_trainer_gallery_bug` — TG## filtro implementado
- `feedback_no_purchase_decisions` — Decisão mecânica ≠ opinião Claude

## Última entrega (2026-05-15)

`cardtrader_relatorio_2026-05-15.xlsx` — 1 BUY NOW (Milcery scr 152 EN, R$26.24 líq) usando v1.5. **Não regenerado com v2** (operador validar antes). Quando re-rodar com v2, esse Milcery vira **REVISAR** (lucro R$26 < threshold R$50 v2).

## Commits desta sessão (10 commits, ordem cronológica reversa)

```
e0281ba release: promote postprocess v2 → official; archive v1.5 as legacy
6411eab feat(scanner v2.5): persist Rarity column no XLSX raw
39451df feat(postprocess v2.0): núcleo simplificado por pedido operador
42dbd8b ops: drop schedules + add Ascended Heroes (asc) + create weekly full scan
52f470e docs: handoff fixup
2d41595 docs: rewrite SESSION-HANDOFF.md retomada-first layout
b4584a8 docs: SESSION-HANDOFF overnight summary
233087f feat(scanner v2.4): per-set timeout + auto skip-list
0815c1c docs: CHANGELOG entry for 2026-05-15 night + README ops notes
09929f5 feat(postprocess): auto-filter TG## → MANUAL REVIEW
62fba69 feat(postprocess): Card Name hyperlink + alias fixes
992895e deliver: 2026-05-15 scan (1 BUY NOW Milcery scr 152)
```
