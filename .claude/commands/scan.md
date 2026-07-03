---
description: Roda o scan canônico do CardTrader por GRUPOS de sets (6 grupos por recência, ≤~2h30 cada — formato padrão da frota, igual ao scan-myp) e entrega via cardtrader_postprocess.py verbatim. SEMPRE pergunta ao operador quais grupos rodar antes de começar. Argumento = números de grupo (ex. "1 3") OU códigos de set CT; "total" = catálogo inteiro via workflow semanal.
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion
---

Você foi acionado pelo comando **`/scan`** do operador. Sua missão é **uma só**:
rodar o scanner do CardTrader **por grupos canônicos** — nunca improvisando
flags — e entregar cada grupo no formato obrigatório do postprocess. **Nenhum
scan do CardTrader roda fora deste runbook.** Runs longos morriam sem entregar;
cada grupo cabe em ≤~2h30 e entrega **sozinho** (se o seguinte morrer, o
anterior já foi entregue). Se algo aqui divergir do `CLAUDE.md`, ele vence.

**Argumento recebido (grupos, códigos ou "total"):** `$ARGUMENTS`

---

## 1. Pré-voo (obrigatório)

1. **Python do ambiente**: Windows local `.venv\Scripts\python.exe`; nuvem/CI
   `python` (instale `requirements.txt` em clone limpo).
2. **Chaves**: `CT_JWT` e `POKEMONTCG_API_KEY` no ambiente ou `.env`. Cuidado
   com BOM/zero-width (`.strip()` NÃO tira BOM — chave suja crasha o header
   latin-1 e o scan sai "verde mas vazio"). Chave ausente/suja → reporte e
   pare. Nunca invente preço.
3. **Escopo**: números 1–6 em `$ARGUMENTS` → esses grupos, sem perguntar.
   Códigos de set CT → scan custom (§3, flags canônicas). `total` → §5.
   **Vazio ou genérico → SEMPRE pergunte** (AskUserQuestion, multiSelect; como
   o limite é 4 opções por pergunta, divida em duas: grupos 1–4 e 5–6; seleção
   vazia/"Other: nenhum" = não rodar aquela faixa), mostrando a tabela abaixo.
   Nunca escolha grupos sozinho.

## 2. Os 6 grupos (códigos CT VERBATIM — nunca invente/deduza outros)

Universo = os **128 sets com referência de preço real e sem armadilha**,
derivado de `SET_ALIAS_TO_PTCG` + `VINTAGE_SET_CODES` do scanner (excluídos:
`wcd*` — decks de mundial precificados contra o set original = preço-armadilha;
`mc*` McDonald's; variantes `p`-duplicadas). A partição é **travada por teste**
(`tests/test_scan_skill_profiles.py`) — nunca edite um código de cabeça.

| Grupo | Era | Sets | Est. local |
|---|---|---|---|
| **G1** | Mega Evolution (**inclui Chaos Rising**) + era SV | 21 | ~1h35–2h |
| **G2** | era Sword & Shield + Pokémon GO + Detective Pikachu + SM final | 21 | ~1h35–2h |
| **G3** | Sun & Moon restante + XY final | 21 | ~1h35–2h |
| **G4** | XY inicial + era Black & White + HGSS | 21 | ~1h35–2h |
| **G5** | Call of Legends + DP + Platinum + EX tardio (tem sets lentos) | 22 | ~1h50–2h15 |
| **G6** | EX inicial + e-Card + WotC (Base…Neo, Gym, promos) | 22 | ~1h50–2h15 |

**G1 — Mega Evolution + era SV:**
```bash
python cardtrader_scanner.py \
  --sets meg pfl asc por cri blk wht dri pre jtg ssp scr sfa twm tef paf par mew obf pal svi \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_g1_<AAAAMMDD_HHMM>.xlsx
```

**G2 — SWSH + PGO + DET + SM final:**
```bash
python cardtrader_scanner.py \
  --sets crz sit lorg astr brs fst evs cre bst shf viv cpa daa rcl ssh pkmgo det cec unm hif teu \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_g2_<AAAAMMDD_HHMM>.xlsx
```

**G3 — SM restante + XY final:**
```bash
python cardtrader_scanner.py \
  --sets unb lot drm ces fli upr cinv bus slg gri sum evo sts fco bkp bkt aor gen ros prc dcr \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_g3_<AAAAMMDD_HHMM>.xlsx
```

**G4 — XY inicial + BW + HGSS:**
```bash
python cardtrader_scanner.py \
  --sets phf ffi flf kss xybsp ltr plb plf pls bcr drx dex nxd nvi epo blw drv tri und ul hgs \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_g4_<AAAAMMDD_HHMM>.xlsx
```

**G5 — COL + DP + Platinum + EX tardio:**
```bash
python cardtrader_scanner.py \
  --sets clo sft ge sw mt pdp sv rr pl nbsp pk df cg hp lm ds uf em dx trr rg hl \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_g5_<AAAAMMDD_HHMM>.xlsx
```

**G6 — EX inicial + e-Card + WotC:**
```bash
python cardtrader_scanner.py \
  --sets exma dr ss rs skg aq ex lc si n4 n3 n2 n1 g2 g1 tr b2 fo ju bs wiz bog \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_g6_<AAAAMMDD_HHMM>.xlsx
```

## 3. Rodar (um run por grupo, SEQUENCIAL)

- Valores canônicos em TODO run: `--threshold 0.30` (**FRAÇÃO** — inteiro `30`
  = 3000% = zero deals sem erro), `--validate-top 30`, `--min-net-margin 0.20`.
- Scan custom (`/scan pre ssp`): mesmo comando trocando só a lista de `--sets`.
- **Nunca dois runs ao mesmo tempo** (mesma pasta de estado — o scanner
  recusa). Grupos escolhidos rodam **em sequência**, cada um em background,
  monitorado. Sets vintage lentos já têm timeout interno maior (df 20min,
  ds/n1/n4 18min) — não mexa em `--per-set-timeout`.
- Grupo que estourar ~2h30 de relógio: anote a duração real no resumo e
  proponha re-dividir. Grupo que falhar não cancela os demais — registre com a
  saída real e siga.
- **Rota via GitHub (opcional)**: dispatch do workflow `daily-scan.yml` com o
  input `sets` = os códigos do grupo (o timeout do workflow comporta um grupo).
  Baixe o artifact e entregue o `.md` do postprocess que vem nele.

## 4. Postprocess + entrega (por grupo, formato OBRIGATÓRIO)

Assim que **cada grupo** terminar (não espere os outros):

```bash
python cardtrader_postprocess.py \
  --input outputs/scan_g<N>_<stamp>.xlsx \
  --output outputs/relatorio_g<N>_<stamp>.xlsx \
  --top-md 50
```

- **Cole no chat, VERBATIM, o `.md`** que ele gravou/imprimiu
  (`build_delivery_markdown` — única fonte de verdade do formato).
- **PROIBIDO**: tabela à mão; renomear/reordenar colunas; remover link;
  XLSX/CSV por anexo (só a pedido explícito); amostra curada.
- **Todas as linhas** (COMPRA + REVISAR); sem deal acima do limiar, a
  ferramenta emite os near-miss "abaixo do limiar" — não existe "veio vazio,
  então reformato".
- **Não recomende compra** — capital é do operador.

## 5. `/scan total` — catálogo inteiro (~832 sets, incl. sem referência)

Nunca local numa tacada: dispatch do **`weekly-scan.yml`** (checkpoint
recuperável + artifacts), aguardar, baixar o artifact e colar o `.md` do
postprocess. Local só em blocos explícitos a pedido do operador.

## 6. Fechamento e higiene

- Outputs de scan (`outputs/*`) são gitignored — NUNCA commite dados de scan.
- Fonte falhou → linha rotulada fallback/erro; jamais fabrique número.
- Resumo final: grupos rodados, duração REAL de cada um (pra calibrar as
  estimativas), deals por classificação, sets pulados/falhos, caminhos dos
  XLSX/`.md` de apoio.
