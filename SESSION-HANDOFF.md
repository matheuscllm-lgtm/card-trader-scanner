# Session Handoff — CT Scanner

> Estado atual + retomada rápida pra próxima sessão.
> **Última atualização:** 2026-05-16 (release v2 oficial).

---

## Estado atual

- **Repo:** `matheuscllm-lgtm/card-trader-scanner` `main` @ `e0281ba` — working tree limpo
- **Scanner:** **v2.5** (per-set timeout + auto skip-list + Rarity persist) — `cardtrader_scanner.py`
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
cd "C:/Users/mathe/Meu Drive/OBSIDIAN/01 - Projetos/TCG & Exportação/CardTrader Scanner"
set -a; source .env; set +a
export PYTHONIOENCODING=utf-8
TS=$(date +%Y%m%d_%H%M)

# Daily scan (11 sets curados, ~30min)
.venv/Scripts/python.exe cardtrader_scanner.py \
  --sets sfa scr par paf tef twm ssp dri blk jtg asc \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --per-set-timeout 8 \
  --output "cardtrader_scan_local_${TS}.xlsx"

# Postprocess v2 (CLI novo: --input único, sem --core/--hype/--dead)
.venv/Scripts/python.exe cardtrader_postprocess.py \
  --input "cardtrader_scan_local_${TS}.xlsx" \
  --output "cardtrader_relatorio_$(date +%Y-%m-%d).xlsx"
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
