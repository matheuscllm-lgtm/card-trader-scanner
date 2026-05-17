# Bug Hunt Consolidated Report — 2026-05-17

**Window:** 15:28:15 → 16:20:05 BRT (51.8min runtime, scanner exit=0)
**Scope:** 7 critical sets (evo, upr, hif, cec, swshbs, svpromo, asc)
**Inputs:** runtime log `critical_resscan_bughunt_2026-05-17.log` + Codex review `codex_review_2026-05-17.md`
**Output XLSX:** `outputs/critical_bughunt_2026-05-17.xlsx` (2 deals, ambos REVISAR)

---

## 1. Sumário executivo

- **Veredito geral: minor issues — pipeline ALIVE/exit=0, mas 2 bugs sérios confirmados no código (Hub fee scanner-side incompleto + skip-list race).** Não bloqueia operação atual com `--validate-top > 0`, mas degrada qualquer uso sem validação.
- **Discrepância com o brief: a task fala em "1 timeout", mas o log mostra 7/7 sets COMPLETED, zero timeouts.** Talvez o brief se refira a "1 set perto do cap" (swshbs em 16.6min, 55% do cap de 30min — ainda confortável). Não há `[WARNING] Set X excedeu --per-set-timeout`.
- **Hub fee bug do Codex (High #3) NÃO se manifestou nestes 2 deals** porque ambos passaram pela validação per-blueprint (`--validate-top` ativo). `Net Margin % REAL` confere até 4ª casa decimal com `(tcg − live × 1.06) / tcg`. Bug é real no caminho default sem validação, não nesta run.
- **Cross-ref: variance de rate listings/min de 42 a 194 (4.6×) sugere CT API thrott/cache hits sem heartbeat dentro de chamadas longas.** Confirma Codex M4 (heartbeat só inter-set).
- **Postprocess sanity OK** — 3 sheets (Deals/All Listings/Summary), 15 colunas com Decisão+Porque+Score, 2 hyperlinks por sheet em "Link CT". Mas há header mojibake (`Decis�o`/`Pre�o CT`) — encoding bug separado que Codex não pegou (cosmético).

---

## 2. Status runtime por set

| Set      | EN listings | Após filtros | Tempo  | Rate (filt/min) | Status        |
|----------|-------------|--------------|--------|-----------------|---------------|
| evo      | 18.115      | 294          | 4.0min | 72.6            | completed     |
| upr      | 9.595       | 152          | 3.1min | 49.0            | completed     |
| hif      | 10.232      | 594          | 12.2min| 48.7            | completed     |
| cec      | 15.899      | 326          | 4.5min | 72.7            | completed (1 retry) |
| swshbs   | 12.502      | 695          | 16.6min| 42.0            | completed (stall 500→550 em 4m25s) |
| svpromo  | 13.616      | 876          | 4.5min | **193.9**       | completed (1 retry, suspeito de cache hot) |
| asc      | 25.232      | 486          | 6.8min | 70.9            | completed     |
| **TOTAL**| 105.191     | 3.423        | 51.8min| —               | 7/7 ALIVE     |

Scanner reportou "Scan completo em 3105.3s — 2 oportunidades ≥ 30%" → após `--min-net-margin 20%`: 2 → 2.

---

## 3. Findings runtime

**A1. Variance de pricing rate 4.6× sem causa visível.**
svpromo a 193.9 listings/min vs swshbs a 42.0 listings/min. Possível explicações: (a) cache pokemontcg.io hot pra `svpromo` (sv-* set codes têm cobertura), (b) muitos blueprints reusando mesmo card-id, (c) muitos 404 retornando rápido (não-erro). Log não distingue. **Sem heartbeat intra-call, qualquer stall futuro só será visto pelos progress marks a cada 50.**

**A2. swshbs apresentou stall de ~4min na janela 500→550.**
Linha 79: `Pricing progress: 500/695 listings consultados` às 15:59:53. Linha 80: `Pricing progress: 550/695` às 16:04:18. Quatro minutos e meio pra 50 listings ≈ 11 listings/min — 4× mais lento que a média do próprio set. Compatível com rate limit / `Retry-After` da pokemontcg.io. Não houve retry CT visível no log nesse intervalo.

**A3. 2 retries CT ConnectionError (cec, svpromo, e validação final).**
Ambos resolvidos em 1s. Codex H1 (skip-list race) não foi exercitado porque nenhuma chamada chegou aos 3/3 retries.

**A4. ZERO warnings de TG##, supranumerary, exotic currency, foil mismatch.** Os 2 deals finais são SR/Promo legítimos validados per-blueprint.

**A5. Encoding mojibake no XLSX final** — headers `Decis�o`, `N�`, `Pre�o CT`, `Lucro L�q`, `Valida��o` em vez de UTF-8 limpo. Bug do `cardtrader_postprocess.py` ao escrever sheet names + headers (provavelmente cp1252 fallback no openpyxl path em vez de UTF-8). Codex não detectou (esperava precisar de run). **Confirmado neste runtime.**

---

## 4. Findings Codex (high-priority, ordem de severidade técnica)

1. **High #3 — Hub fee aplicado SÓ em validate_per_blueprint (cardtrader_scanner.py:1191-1194).** Inicial scan computa margem com preço CT raw (linhas 1028-1035). Resultado: scanner sem `--validate-top` é ~6pp otimista. CLI default é `--validate-top 0` (linha 1369). **Mais sério porque inverte o invariante declarado no README.** Esta run usou `--validate-top 100` → não exercitou o bug.

2. **High #1 — Skip-list read-modify-write race (cardtrader_scanner.py:740-766).** `add_to_skip_list()` / `load_skip_list()` / `clear_skip_list()` sem lock. Dois scanners simultâneos podem corromper `scanner_skip_list.json`. Severidade real depende de quantas runs paralelas o operador roda — atualmente 1 daily + 1 weekly + ad-hocs manuais. Risco baixo em volume atual, alto se virar concurrent.

3. **High #2 — Per-set timeout é cooperativo, não wall-clock (cardtrader_scanner.py:966-1002).** Timer começa antes de `list_blueprints()` / `list_listings_by_expansion()`, mas primeira verificação só dentro do pricing loop. Uma hang em CT antes do pricing começar não é interrompida. Esta run não exercitou — todos os CT calls retornaram <10s.

4. **High #4 — Postprocess documenta 1.06 mas não recomputa (cardtrader_postprocess.py:181-323).** Apenas aliasing de colunas `Net Margin % REAL` → `net_margin`. Se scanner output for raw/sem validação, postprocess propaga margem otimista silenciosamente. **Coupling perigoso scanner↔postprocess.** Confirmado: nesta run, postprocess herda `Net Margin % REAL` do scanner; não recalcula.

5. **High #5 — `except Exception` no pricing call silencia falhas (cardtrader_scanner.py:1014-1023).** Log de erro só em DEBUG; produção INFO perde drift de schema, SSL, JSON parse. Deal silenciosamente removido. **Falha invisível.** Esta run não teve drift visível, mas é o caminho mais fácil pra "zero deals" misterioso.

---

## 5. Cross-reference runtime ↔ static

| Codex finding | Manifestou? | Evidência runtime |
|---|---|---|
| H1 skip-list race | Não | Sem timeout, sem skip-list write nesta run |
| H2 timeout cooperativo | Não | swshbs 16.6min < 30min cap; nenhum CT call hangou |
| H3 Hub fee só validate | **Não, mas matematicamente confirmado pelo escape via validate-top** | `(tcg − live×1.06)/tcg` = `Net Margin % REAL` até 4ª casa decimal nos 2 deals. Math do recalc REAL está correto. Bug existe no path SEM validate-top |
| H4 postprocess passthrough | **Sim, parcialmente** | Postprocess copia `Net Margin % REAL` sem recompute. Se scanner enviasse margem raw (sem 1.06), postprocess decidiria COMPRA/REVISAR/NÃO em cima de número errado |
| H5 pricing silent fail | Não (visível) | Mas explica parte da variance 4.6× — listings com erro silencioso são contados como "consultados" no progress |
| M3 TG## bypass variants | Não exercitado | swshbs/svpromo/asc não têm Trainer Gallery |
| M4 heartbeat intra-call | **Sim** | swshbs stall 500→550 (4m25s) só ficou visível pelo progress mark; um hang real entre marks seria invisível por até 4min |
| Encoding (não Codex) | **Sim, novo** | Headers XLSX mojibakeados `Decis�o`, `Pre�o CT`, `Lucro L�q` |

**Math check Hub fee 1.06 (cross-ref H3+H4):**
- Sylveon: `(269.49 − 63.06 × 1.06) / 269.49 = 0.7520` ✓ match XLSX
- Snorlax VMAX: `(317.04 − 106.16 × 1.06) / 317.04 = 0.6451` ✓ match XLSX
- Delta vs `tcg − lucro`: ≤ R$0,01 (rounding float, Codex Low #1 confirmado mas trivial)

**Timeout cap analysis:** swshbs em 16.6min é o pior caso, 55% do cap de 30min. Margem de segurança 13.4min. Cap nominal não foi excedido em nenhum set.

---

## 6. Bugs recomendados pra fix imediato

Priorizado por **severity × frequency × fix complexity**:

1. **H3 Hub fee no scan inicial (severity alta, frequência 100% sem validate-top, complexity baixa ~5 LOC).**
   Aplicar `* (1 + HUB_FEE_RATE)` nas linhas 1028-1035 antes do filtro de threshold. Garante paridade scan↔validate↔postprocess. **Fix mais barato de todos os high.**

2. **H4 postprocess recompute defensivo (severity alta se H3 não for fixado, complexity baixa).**
   Em `cardtrader_postprocess.py`, recomputar `net_margin = (tcg − preco_CT × 1.06) / tcg` em vez de aliasing. Belt-and-suspenders mesmo com H3 fixado.

3. **Encoding XLSX mojibake (severity baixa cosmético, frequência 100%, complexity baixa).**
   Postprocess `writer` deve forçar `engine='openpyxl'` + headers via `df.to_excel(..., encoding='utf-8')` ou pré-encode UTF-8 explícito. Headers `Decis�o`/`Pre�o CT` confundem operador na triagem.

4. **H5 logar pricing failures em WARNING (severity média, complexity baixa ~2 LOC).**
   Mudar `logger.debug(f"Pricing falhou: {e}")` para `logger.warning(...)` e adicionar counter `skipped_pricing_error`. Sem isso, schema drift pokemontcg.io vira "zero deals" silencioso.

5. **M4 heartbeat intra-call CT (severity média, complexity média).**
   Wrapper de `requests.get()` com signal-based timeout + log heartbeat a cada 30s dentro de retry loops. Resolve hang invisível entre progress marks.

---

## 7. Bugs OK pra adiar

- **H1 skip-list race** — risco real só em concurrent runs. Operador roda sequencial (Task Scheduler weekly + daily não overlap). Adiar até primeira corrida paralela ad-hoc.
- **H2 timeout cooperativo** — mitigação atual: per-set cap 30min + watchdog externo do PowerShell wrapper. Não há evidência de hang real-world (10 min de retries CT seria detectado pelo `Retry-After`; pokemontcg.io ratelimit é rápido). Custo de fix (signal/thread-based hard timeout) > benefício atual.
- **M1 contract drift validation** — pokemontcg.io schema estável há ~12 meses; CT JWT válido até 2126. Probabilidade baixa, custo de fix médio.
- **M2 validate-top default 0** — operador sempre usa wrappers com `--validate-top 100`. Mudança de default arriscaria quebrar scripts externos.
- **M3 TG## bypass variants** — não há set TG nos 7 críticos atuais. Implementar quando reativar daily completo (10 sets incluindo Crown Zenith/swsh10/swsh11).
- **M5 PowerShell stderr discard** — exit code + log file são suficientes para o modo atual; melhoria de DX.
- **Low #1 float math** — rounding sub-centavo, irrelevante para decisões R$50+.
- **Low #2 hub-fee Stats sheet stale** — só afeta se operador usar `--hub-fee` custom (nunca usou).
- **Low #3-#6** — cleanup, não bugs.

---

## 8. Postprocess sanity check (XLSX final)

Validado via openpyxl direto (MCP Excel disponível só na próxima sessão).

**Estrutura confirmada:**
- 3 sheets: `Deals` (2 rows), `All Listings` (2 rows), `Summary` (15 rows). ✓ match release v2 spec
- 15 colunas: Decisão / Porque / Chase Tier / Score / Set / Carta / Nº / Idioma / Preço CT (R$) / TCG (R$) / Net % / Lucro Líq (R$) / Validação / Seller / Link CT ✓
- **2 hyperlinks por sheet** na coluna `Link CT` apontando para cardtrader.com/cards/{id} ✓ (atende `feedback_xlsx_card_name_hyperlink`)
- Decisões: 2/2 `REVISAR` (zona cinza MODEST + net alta). 0 COMPRA, 0 NÃO. Coerente com Chase Tier=MODEST nos dois (Promo + Oversized, não chase top-tier).
- Summary line 1: "Total listings escaneados 2" — semanticamente incorreto. Deveria ser "Total deals exportados". 3.423 foi o universo após filtros; 2 foi o resultado pós-margem. Confunde operador sobre cobertura. **Bug de label.**

**Issues encontrados na sanity:**
- Mojibake nos headers (UTF-8 → cp1252 corruption): `Decis�o`, `Pre�o CT (R$)`, `N�`, `Lucro L�q (R$)`, `Valida��o`. Bug postprocess.
- Summary "Total listings escaneados" mislabeled. Bug label.

---

## Anexo: comandos de reprodução

```powershell
# Scanner (este run):
& .venv\Scripts\python.exe cardtrader_scanner.py `
    --sets evo cec upr hif asc svpromo swshbs `
    --threshold 0.30 --validate-top 100 --min-net-margin 0.20 `
    --per-set-timeout 1800 `
    --output outputs\critical_resscan_bughunt_2026-05-17.xlsx

# Postprocess:
$env:PYTHONIOENCODING="utf-8"
& .venv\Scripts\python.exe -u cardtrader_postprocess.py `
    --input  outputs\critical_resscan_bughunt_2026-05-17.xlsx `
    --output outputs\critical_bughunt_2026-05-17.xlsx
```

---

*Report gerado pelo card-agent. Não rankeia compras, não recomenda capital — operador decide.*
