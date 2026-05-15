# Session Handoff — 2026-05-15 (CT Scanner)

> Preservation note pra continuidade entre sessões. Se contexto colapsar, próximo
> Claude / operador retoma daqui.

## Estado deste momento

- **Repo:** `matheuscllm-lgtm/card-trader-scanner`, branch `main`, HEAD `67b3cb9` (push 2026-05-15)
- **Working tree:** limpo
- **Scanner:** v2.3.1 (postprocess v1.4)
- **Hub fee paridade:** scanner ↔ postprocess intacta (6%)

## O que foi feito nesta sessão (2026-05-15)

1. **MCP cleanup parcial.** Removido `n8n-mcp` local stdio. 14 connectores claude.ai irrelevantes (Wix, Asana, Linear, Slack, Webflow, Canva, Lucid, Notion, Intuit QuickBooks, Zoom, Zapier, Microsoft Learn, Gmail, Google Calendar) pendentes desconectar via https://claude.ai/settings/connectors. GitHub PAT plaintext em `.claude.json` pendente rotação.
2. **Memória `feedback_autonomy_directive` expandida** com seção CardTrader Scanner — escopo técnico-mecânico análoga ao MYP. Mais regra "review+save por tópico" + "operator-timeout 10s" agora oficiais.
3. **Cron daily-scan.yml desabilitado** temporariamente (operador 2026-05-15). Reativação documentada in-file. Commit `67b3cb9`.
4. **Scan ad-hoc disparado** — run `25898522951` via workflow_dispatch ~03:25 UTC, defaults (sets `sfa scr par paf tef twm ssp dri blk jtg`, threshold 0.30, min_net_margin 0.20, validate_top 30). Status quando este handoff foi escrito: queued (~12min de fila).
5. **/fewer-permission-prompts** rodado. 7 MCP read-only oncology adicionados ao `settings.local.json` (PubMed search/metadata/fulltext, Clinical Trials trials/details, Consensus search, related articles).

## Próximo passo claro

Quando run `25898522951` completar:

1. **Verificar XLSX gerado** — esperado: `cardtrader_scan_*.xlsx` + `cardtrader_relatorio_2026-05-15.xlsx`. Baixar artifact via `gh run download 25898522951 -n scan-25898522951` se não estiver no Drive.
2. **Auditoria (checklist):**
   - ✓ Existe relatório + sheet "Decisao Rapida" não-vazio
   - ✓ Grep `^TG\d+` no card_number em BUY NOW (esperado: 0 matches)
   - ✓ Hub fee paridade: sample 3 deals, validar `tcg - ct×1.06 ≈ lucro` (±R$0.10)
   - ✓ Margens >100% sinalizadas (potencial SIR/HR/SAR misread)
   - ✓ Comparar com baseline 2026-05-13 (2 BUY NOW Aipom par + Drampa tef = R$92)
3. **Persistir entrega** — atualizar este handoff com sumário 1-página: top deals, FPs, ressalvas. Commit + push.

## Tasks ativas (TaskList)

- #1 ✓ Validar estado canônico
- #2 ▶ Dispatch scan (in_progress, aguardando run completar)
- #3 ⏸ Auditar XLSX
- #4 ⏸ Persistir entrega + handoff
- #5 ⏸ Context-exhaustion protocol (este arquivo cobre)

## Baseline 13/05 pra comparação

- 12 listings, 2 BUY NOW (CORE):
  - **Aipom (par)** — CT R$96.38, TCG R$150.40, margem líq 32.1%, lucro R$48.24
  - **Drampa (tef)** — CT R$113.81, TCG R$164.57, margem líq 26.7%, lucro R$43.93
- HYPE/DEAD zerados (filtros mais strict)
- FPs todos por `low_gross_margin` (queda pós-validação per-blueprint — comportamento esperado)

## Memórias críticas atualizadas hoje

- `session_log_2026_05_15_mcp_cleanup_and_scan.md` (novo)
- `feedback_autonomy_directive.md` (CT scope expandido + review+save pattern + 10s timeout)
- `MEMORY.md` (entry adicionada)

## Background tasks vivos

- Bash background `be5489xm7`: poll de status do run `25898522951` até `completed`. Output em `tasks/be5489xm7.output`.

## Update 04:42 UTC — first run cancelled, re-dispatched

- Run `25898522951` cancelado em 30:09 pelo `timeout-minutes: 30` (subdimensionado p/ escopo de 10 sets). 5/10 sets processados.
- Fix aplicado: `timeout-minutes` 30 → 60 (commit `2a9a413`). Calibração documentada em memória `ct_scan_timeout_calibration.md`.
- **Run novo: `25900649576`** (dispatch 04:42 UTC). Estimativa: ~50min de execução + fila.
- Pricing rate medido: 2-10 listings/s. 10 sets × ~280 listings = ~2800 listings total.
- Sets já validados nesse escopo (run cancelled): sfa scr par paf tef. Pendentes no novo run: todos 10 do scratch.

## ENTREGA — 2026-05-15 (CT scan completo, audit OK)

**XLSX gerados (no scanner dir = sync Drive automático):**
- Raw: `cardtrader_scan_local_20260515_0147.xlsx` (7.6 KB)
- Relatório formatado: `cardtrader_relatorio_2026-05-15.xlsx` (21 KB) — ABRIR ESTE
- Log execução: `scan_local_20260515_0147.log`

**Resultado: 1 BUY NOW no CORE**

| Carta | Set | Nº | Idioma | CT R$ | TCG R$ | Margem Líq | Lucro Líq | Seller | Tier |
|---|---|---|---|---|---|---|---|---|---|
| Milcery | Stellar Crown (scr) | 152 | EN | 58.31 | 88.05 | 29.8% | **R$26.24** | DMB Direct | non-VAT (+20%) |

Link CT: https://www.cardtrader.com/cards/299015

**Outros 4 candidatos rejeitados (low_gross_margin no CORE) — pra contexto, não pra ação:**
- Milcery (scr 152) outro seller — gross 28.1% < 30% threshold
- Charmander (paf 109) — gross 24.6% < 30%
- Plusle (par 193) — gross 24.3% < 30%
- Okidogi (sfa 74) — gross 20.2% < 30%

HYPE e DEAD vazios (0 candidatos sequer passaram primeiro filtro).

**Auditoria checklist:**
- ✅ TG## leak: 0 rows
- ✅ Margens >100% (SIR/HR misread): 0 rows
- ✅ Hub fee paridade 6%: math confirmada — 58.31×1.06=61.81; 88.05−61.81=26.24=Lucro Líq
- ✅ Cobertura 10 sets canônicos OK (sfa scr par paf tef twm ssp dri blk jtg)
- ✅ Estrutura XLSX completa (10 sheets incl. Decisao Rapida + Exec Summary + Final Action List)

**Comparação vs baseline 13/05:**
- 13/05: 2 BUY NOW (Aipom par + Drampa tef = R$92 lucro total)
- 15/05: 1 BUY NOW (Milcery scr = R$26 lucro)
- Mercado mais magro hoje — comportamento esperado, scanner saudável.

**Próximo daily scan:**
- Cron GH Actions desabilitado + quota free tier exhausted até 01/06/2026
- Pra rodar manual local: ver bloco "Próximo passo claro" no início deste handoff
- Decisão pendente longer-term: upgrade GH plan / repo public / self-hosted runner

---

## Update 04:48 UTC — GH Actions quota exhausted, switched to LOCAL run

- Runs `25900649576` + `25900778686` falharam imediatamente (3s) sem alocar runner. `runner_name: ""`. Diagnóstico: cota mensal GH Actions free tier (2000min em repo privado) bateu hoje. Detalhes em memória `gh_actions_quota_exhausted.md`.
- **Reset esperado: 01/06/2026.** Cron disable é cosmético até lá; dispatch também falha.
- **Mitigação aplicada: scan LOCAL** rodando agora.
  - Comando: `.venv/Scripts/python.exe cardtrader_scanner.py --sets sfa scr par paf tef twm ssp dri blk jtg --threshold 0.30 --validate-top 30 --min-net-margin 0.20 --output cardtrader_scan_local_<TS>.xlsx`
  - `.env` carregado (CT_JWT + POKEMONTCG_API_KEY)
  - Started 01:47:55 BRT (04:47:55 UTC) — 2 Python processes vivos
  - Log: `scan_local_20260515_0147.log`
  - ETA: ~50min (mesma rate observada GH Actions)
- Poll bg `ba1zfg3o3` monitorando exit dos processos Python.

**Se contexto colapsar agora, retomar com:**
1. `cd "Meu Drive/OBSIDIAN/01 - Projetos/TCG & Exportação/CardTrader Scanner"`
2. `tail -30 scan_local_*.log` — ver onde parou
3. Se processo Python morreu sem XLSX → checar log pra causa
4. Se XLSX existe → rodar postprocess: `.venv/Scripts/python.exe cardtrader_postprocess.py --core <xlsx> --hype <xlsx> --dead <xlsx> --output cardtrader_relatorio_2026-05-15.xlsx`
5. Auditoria conforme checklist na seção "Próximo passo claro"
