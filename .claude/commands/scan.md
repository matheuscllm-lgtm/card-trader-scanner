---
description: Roda o scan canônico do CardTrader e entrega o resultado no formato obrigatório — pipeline fixo (scanner → postprocess → colar o .md verbatim no chat). Sempre os mesmos passos, sempre o mesmo formato. Argumento opcional = códigos de set CT pra sobrescrever o escopo padrão.
allowed-tools: Bash, Read, Grep, Glob
---

Você foi acionado pelo comando **`/scan`** do operador. Sua missão é **uma só**:
rodar o scan do CardTrader **exatamente do jeito canônico abaixo** e entregar o
resultado **no formato obrigatório**. Não improvise flags, não invente formato,
não pule etapa. Este runbook espelha o `daily-scan.yml` e a regra de entrega do
`CLAUDE.md` — se algo aqui divergir do `CLAUDE.md`, o `CLAUDE.md` vence.

**Argumento recebido (sets opcionais):** `$ARGUMENTS`

---

## 1. Pré-voo (obrigatório)

1. **Python do ambiente**: no Windows local use `.venv\Scripts\python.exe`; na
   nuvem/CI use `python` (instale `requirements.txt` se for clone limpo).
2. **Chaves**: confirme `CT_JWT` e `POKEMONTCG_API_KEY` no ambiente ou no `.env`.
   Ao validar, cuidado com BOM/zero-width (`.strip()` NÃO tira BOM — chave suja
   crasha o header latin-1 e o scan sai "verde mas vazio"). **Chave ausente ou
   suja → reporte e pare.** Nunca invente preço nem rode sem fonte.
3. **Escopo**: se `$ARGUMENTS` vier vazio, use os sets padrão do runbook (passo 2).
   Se vier com códigos CT (ex.: `/scan pre ssp`), eles substituem **apenas** a
   lista de sets — todas as outras flags continuam as canônicas.

## 2. Scan canônico (valores EXPLÍCITOS — nunca dependa de default)

```bash
python cardtrader_scanner.py \
  --sets sfa scr par paf tef twm ssp dri blk jtg asc \
  --threshold 0.30 \
  --validate-top 30 \
  --min-net-margin 0.20 \
  --output outputs/scan_<AAAAMMDD_HHMM>.xlsx
```

- `--threshold` é **FRAÇÃO** (`0.30` = 30%). Inteiro (`30`) = 3000% = zero deals
  sem erro nenhum. Nunca troque a convenção.
- Run demora (~5 min/set; 11 sets ≈ 50 min) → rode **em background** e acompanhe
  o log; não deixe preso num terminal que pode fechar.
- Set que falhar/estourar timeout: o scanner já pula e segue — relate no final,
  não "conserte" fabricando dado.

## 3. Postprocess obrigatório (a entrega SÓ sai daqui)

```bash
python cardtrader_postprocess.py \
  --input outputs/scan_<AAAAMMDD_HHMM>.xlsx \
  --output outputs/relatorio_<AAAAMMDD_HHMM>.xlsx \
  --top-md 50
```

Ele imprime a tabela markdown no terminal E grava um `.md` ao lado do XLSX
(mesmo nome, terminação `.md`). Esse `.md` é a entrega — vem de
`build_delivery_markdown`, a única fonte de verdade do formato.

## 4. Entrega (formato OBRIGATÓRIO — não negociável)

- **Cole no chat, VERBATIM, o conteúdo do `.md`** que o postprocess gerou.
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
- Feche com um resumo curto: sets varridos, quantos deals (COMPRA/REVISAR),
  sets pulados/falhos, e o caminho do XLSX/`.md` de apoio.
