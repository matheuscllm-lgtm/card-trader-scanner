---
description: Roda o scan canônico do CardTrader e entrega o resultado no formato obrigatório — pipeline fixo (scanner → postprocess → colar o .md verbatim no chat). Cobre TODOS os modos via perfis nomeados (padrão/diário, completo, vintage em blocos, total via workflow). Sempre os mesmos passos, sempre o mesmo formato. Argumento = perfil (completo/vintage/total) OU códigos de set CT.
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion
---

Você foi acionado pelo comando **`/scan`** do operador. Sua missão é **uma só**:
rodar o scan do CardTrader **exatamente pelo perfil canônico abaixo** e entregar
o resultado **no formato obrigatório**. Não improvise flags, não invente
formato, não pule etapa. **Nenhum scan do CardTrader roda fora destes perfis.**
Este runbook espelha os workflows do repo (`daily-scan.yml`/`weekly-scan.yml`)
e a regra de entrega do `CLAUDE.md` — se algo divergir do `CLAUDE.md`, ele vence.

**Argumento recebido (perfil ou sets):** `$ARGUMENTS`

---

## 1. Pré-voo (obrigatório)

1. **Python do ambiente**: no Windows local use `.venv\Scripts\python.exe`; na
   nuvem/CI use `python` (instale `requirements.txt` se for clone limpo).
2. **Chaves**: confirme `CT_JWT` e `POKEMONTCG_API_KEY` no ambiente ou no `.env`.
   Ao validar, cuidado com BOM/zero-width (`.strip()` NÃO tira BOM — chave suja
   crasha o header latin-1 e o scan sai "verde mas vazio"). **Chave ausente ou
   suja → reporte e pare.** Nunca invente preço nem rode sem fonte.
3. **Perfil**: resolva `$ARGUMENTS` pela tabela de perfis (§2). Argumento que
   não é um perfil nem parece código de set CT → pergunte ao operador em vez
   de chutar.

## 2. Perfis — caminho único por modo (valores SEMPRE explícitos)

Todos os perfis usam os MESMOS valores canônicos: `--threshold 0.30`
(**FRAÇÃO**; inteiro `30` = 3000% = zero deals sem erro), `--validate-top 30`,
`--min-net-margin 0.20`, output em `outputs/`. Só o ESCOPO muda entre perfis.

### `/scan` (sem argumento) — PADRÃO (diário) · 11 sets · ~50 min

```bash
python cardtrader_scanner.py \
  --sets sfa scr par paf tef twm ssp dri blk jtg asc \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_<AAAAMMDD_HHMM>.xlsx
```

### `/scan <códigos CT>` — sets custom (ex.: `/scan pre ssp`)

Mesmo comando do padrão trocando **apenas** a lista de `--sets`; todas as
outras flags ficam as canônicas.

### `/scan completo` — moderno curado · ~30 sets · est. ~2h15 (um bloco)

```bash
python cardtrader_scanner.py \
  --all-sets --skip-backcatalog \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_completo_<AAAAMMDD_HHMM>.xlsx
```

Roda em **background** e monitore. Se passar de ~2h30 de relógio, anote a
duração real no resumo e proponha re-dividir — não deixe virar run infinito.

### `/scan vintage` — 2 blocos fixos, SEQUENCIAIS, entrega por bloco

Códigos copiados VERBATIM de `VINTAGE_SET_CODES` do scanner (travados por
teste — `tests/test_scan_skill_profiles.py`; **nunca** edite de cabeça). Se o
operador não disser quais blocos, **pergunte** (AskUserQuestion, multiSelect).
Cada bloco tem XLSX próprio e passa pelo postprocess+entrega (§3-4) **assim que
termina** — falha de um bloco não cancela o outro. Sets vintage lentos já têm
timeout interno maior (df 20min; ds/n1/n4 18min) — não mexa em `--per-set-timeout`.

**Bloco V1 — WOTC + e-Card (18 sets):**
```bash
python cardtrader_scanner.py \
  --sets bs ju fo b2 tr g1 g2 n1 n2 n3 n4 si lc wiz bog ex aq skg \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_vintage_v1_<AAAAMMDD_HHMM>.xlsx
```

**Bloco V2 — era EX (16 sets):**
```bash
python cardtrader_scanner.py \
  --sets rs ss dr exma hl rg trr dx em uf ds lm hp cg df pk \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_vintage_v2_<AAAAMMDD_HHMM>.xlsx
```

### `/scan total` — catálogo inteiro (~832 sets) · NUNCA local numa tacada

O caminho canônico é o **workflow `weekly-scan.yml`** (dispatch em
`matheuscllm-lgtm/card-trader-scanner`, ref `main` — ele roda `--all-sets` com
checkpoint recuperável e sobe artifacts). Aguarde o run, baixe o artifact e
entregue colando o `.md` do postprocess que vem nele (se faltar, rode o
postprocess local sobre o XLSX do artifact). Rodar o catálogo inteiro local só
em blocos explícitos, a pedido do operador — lembrando que a auditoria
2026-06-08 deu 0 deal no back-catalog (o gap mora nos lançamentos novos).

## 3. Postprocess obrigatório (a entrega SÓ sai daqui; um por XLSX)

```bash
python cardtrader_postprocess.py \
  --input outputs/scan_<...>.xlsx \
  --output outputs/relatorio_<...>.xlsx \
  --top-md 50
```

Ele imprime a tabela markdown no terminal E grava um `.md` ao lado do XLSX
(mesmo nome, terminação `.md`). Esse `.md` é a entrega — vem de
`build_delivery_markdown`, a única fonte de verdade do formato.

## 4. Entrega (formato OBRIGATÓRIO — não negociável)

- **Cole no chat, VERBATIM, o conteúdo do `.md`** que o postprocess gerou —
  um por bloco/perfil, assim que ficar pronto.
- **PROIBIDO**: montar/reformatar tabela à mão; renomear/reordenar colunas;
  remover um link; entregar XLSX/CSV por anexo (só se o operador pedir
  explicitamente); mostrar amostra curada.
- **Mostre TODAS as linhas** (COMPRA + REVISAR). Se nenhum item passar o limiar,
  a ferramenta já emite os candidatos near-miss marcados "abaixo do limiar" —
  **não existe** o caso "veio vazio, então eu reformato".
- **Não recomende comprar/não comprar.** Você reporta margem, flags e fontes;
  capital é decisão do operador.
- Se a entrega que você vai colar **não saiu do `.md` da ferramenta**, pare e
  gere por ela.

## 5. Honestidade e higiene

- Outputs de scan (`outputs/*.xlsx`, `*.md`, logs) são **gitignored de
  propósito** — NUNCA commite dados de scan.
- Fonte de preço falhou → a linha sai rotulada fallback/erro; relate com a
  saída real. Jamais fabrique número.
- Nunca rode dois scans na mesma pasta de estado ao mesmo tempo (o scanner
  recusa; blocos são SEQUENCIAIS).
- Feche com um resumo curto: perfil/blocos rodados, duração REAL de cada um,
  quantos deals (COMPRA/REVISAR), sets pulados/falhos, e o caminho dos
  XLSX/`.md` de apoio.
