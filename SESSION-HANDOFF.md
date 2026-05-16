# Session Handoff — CT Scanner

> Estado atual + retomada rápida pra próxima sessão.
> **Última atualização:** 2026-05-16 (overnight 2026-05-15→16).

---

## Estado atual

- **Repo:** `matheuscllm-lgtm/card-trader-scanner` `main` @ `b4584a8` — working tree limpo
- **Scanner:** **v2.4** (per-set timeout + auto skip-list) — `cardtrader_scanner.py`
- **Postprocess:** **v1.5** (hyperlinks + TG## auto-filter + alias fixes) — `cardtrader_postprocess.py`
- **Hub fee paridade:** scanner ↔ postprocess intacta (6%)
- **Cron GH Actions:** **desabilitado** (em `daily-scan.yml`, reativação documentada in-file)
- **Quota GH Actions:** **exhausted** até 2026-06-01 — runs locais são o caminho até lá

## Quick-start retomada

Próxima sessão começa lendo este arquivo. Pra rodar scan agora:

```bash
cd "C:/Users/mathe/Meu Drive/OBSIDIAN/01 - Projetos/TCG & Exportação/CardTrader Scanner"
set -a; source .env; set +a
export PYTHONIOENCODING=utf-8
TS=$(date +%Y%m%d_%H%M)
.venv/Scripts/python.exe cardtrader_scanner.py \
  --sets sfa scr par paf tef twm ssp dri blk jtg \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --per-set-timeout 8 \
  --output "cardtrader_scan_local_${TS}.xlsx"

# Postprocess (mesmo XLSX nos 3 buckets — scanner pré-filtra)
.venv/Scripts/python.exe cardtrader_postprocess.py \
  --core "cardtrader_scan_local_${TS}.xlsx" \
  --hype "cardtrader_scan_local_${TS}.xlsx" \
  --dead "cardtrader_scan_local_${TS}.xlsx" \
  --output "cardtrader_relatorio_$(date +%Y-%m-%d).xlsx"
```

ETA: ~30min total (medido empiricamente 2026-05-15).

## Última entrega (2026-05-15)

`cardtrader_relatorio_2026-05-15.xlsx` no Drive (sync auto). **1 BUY NOW:**

| Carta | Set | Nº | CT R$ | TCG R$ | Margem Líq | Lucro Líq | Seller |
|---|---|---|---|---|---|---|---|
| Milcery | Stellar Crown (scr) | 152 EN | 58.31 | 88.05 | 29.8% | **R$26.24** | DMB Direct (non-VAT +20%) |

Link: https://www.cardtrader.com/cards/299015 (hyperlink ativo no XLSX). HYPE/DEAD vazios. Audit 100%: TG## 0 leaks, margens >100% 0, Hub fee math confirmada.

## Pendências / opções pra próximas sessões

- **404 consecutive cap** — optimization marginal sobre v2.4. Timeout per-set já cobre o cenário prático.
- **GH Actions quota strategy** — decisão de operador: upgrade plan vs repo público vs self-hosted runner. Bloqueia retomada de cron automático até 2026-06-01.
- **PAT GitHub plaintext** em `~/.claude.json` linha 505 — rotação pendente (segurança).
- **14 connectores claude.ai irrelevantes** — desconectar via https://claude.ai/settings/connectors.
- **Bridge `merge_myp_ct.py`** — pode rodar combinação MYP↔CT quando MYP weekly tiver output (após quota reset).

## Memórias relevantes (carregadas auto pelo MEMORY.md)

- `feedback_autonomy_directive` — postura autônoma + escopo CT explícito
- `ct_scan_timeout_calibration` — pricing rate medido + v2.4 resolved
- `gh_actions_quota_exhausted` — diagnóstico + workarounds locais
- `excel_mcp_setup` — `mcp__excel__*` disponível na próxima sessão
- `cardtrader_trainer_gallery_bug` — TG## filtro implementado
- `feedback_xlsx_card_name_hyperlink` — hyperlinks aplicados

## Commits desta sessão (11)

```
b4584a8 docs: SESSION-HANDOFF overnight summary
233087f feat(scanner v2.4): per-set timeout + auto skip-list
0815c1c docs: CHANGELOG + README polish
09929f5 feat(postprocess): auto-filter TG## → MANUAL REVIEW
62fba69 feat(postprocess): Card Name hyperlink + alias fixes
992895e deliver: 2026-05-15 scan (1 BUY NOW Milcery scr 152)
00e896c docs: quota exhausted, switched to local run
9bc1420 docs: handoff (first run cancelled)
2a9a413 ops: bump timeout 30→60min
4050ffa docs: SESSION-HANDOFF.md inicial
67b3cb9 ops: disable daily cron schedule
```

## Timeline operacional (referência, ordem cronológica)

**2026-05-15 noite (BRT):**
- 22:33 BRT — Operador ativa card-agent. MCP cleanup parcial (n8n-mcp local removido; 14 connectores claude.ai web-only pendentes).
- 23:25 BRT — Cron disabled + scan ad-hoc dispatched (run 25898522951).
- 01:14 BRT — Run cancelled em 30:09 (timeout-minutes 30 subdimensionado). Fix: bump → 60.
- 01:42 BRT — Re-dispatch (`25900649576`) falha em 3s. Quota free tier GH Actions exhausted.
- 01:47 BRT — **Switch para scan LOCAL.** `.env` carregado, venv path.
- 02:16 BRT — Scan local completo em 29min. Postprocess + audit OK. 1 BUY NOW.
- 03:00-05:00 BRT — Overnight features: hyperlinks → TG## → docs → v2.4 timeout+skip-list.

**Estado pré-sessão (2026-05-14):** v2.3.1 (progress logging only), pendências múltiplas em memória.
**Estado pós-sessão (2026-05-16):** v2.4 + v1.5 postprocess, pendências v2.4 fechadas, toolkit ganhou Excel MCP.
