---
description: Roda o scan canônico de DRAGON BALL no CardTrader (--game dragonball) por GRUPOS de sets (5 grupos por era — formato padrão da frota, igual ao /scan) e entrega via cardtrader_postprocess.py verbatim. SEMPRE pergunta ao operador quais grupos rodar antes de começar. Argumento = números de grupo (ex. "1 2") OU códigos de set CT (ex. "fb10 bt31").
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion
---

Você foi acionado pelo comando **`/scan-dbz`** do operador. Sua missão é **uma
só**: rodar o scanner do CardTrader em modo **Dragon Ball** (`--game
dragonball`) **por grupos canônicos** — nunca improvisando flags — e entregar
cada grupo no formato obrigatório do postprocess. **Nenhum scan Dragon Ball
roda fora deste runbook.** Se algo aqui divergir do `CLAUDE.md`, ele vence.

**Argumento recebido (grupos ou códigos):** `$ARGUMENTS`

---

## 0. O que este modo cobre (contexto de 1 minuto)

- **Jogo:** Dragon Ball Super Card Game no CardTrader (game_id 9) — tanto o
  jogo clássico (**Masters**: bt1..bt31, decks, expansion sets) quanto o
  **Fusion World** (fb01+, fs*, sb*). O DBZ TCG antigo da Panini NÃO existe no
  CT.
- **Referência de preço:** TCGplayer via `tcgcsv.com` (categorias 27 =
  Masters, 80 = Fusion World) — fonte PRIMÁRIA neste modo; a pokemontcg.io é
  Pokémon-only e nunca é consultada. `POKEMONTCG_API_KEY` NÃO é necessária.
- **Escopo:** os **88 sets** do mapa verificado `DBZ_SET_TO_TCGCSV` (match por
  conteúdo, 2026-07-17). Promos/pre-release e sets sem referência (bt10/bt11 —
  edições ambíguas; st01 — CT ainda sem números) ficam FORA por design.
- **Invariantes da frota inalterados:** NM-only, EN-only, margem BRUTA,
  threshold em FRAÇÃO, piso ~US$10, nunca inventar preço, nunca recomendar
  compra.

## 1. Pré-voo (obrigatório)

1. **Python do ambiente**: Windows local `.venv\Scripts\python.exe`; nuvem/CI
   `python` (instale `requirements.txt` em clone limpo).
2. **Chave**: só `CT_JWT` (ambiente ou `.env`). Cuidado com BOM/zero-width
   (`.strip()` NÃO tira BOM — chave suja crasha o header latin-1 e o scan sai
   "verde mas vazio"). Chave ausente/suja → reporte e pare.
3. **Escopo**: números 1–5 em `$ARGUMENTS` → esses grupos, sem perguntar.
   Códigos de set CT → scan custom (§3, flags canônicas). **Vazio ou genérico
   → SEMPRE pergunte** (AskUserQuestion, multiSelect; grupos 1–4 numa pergunta
   e 5 em "Other"/segunda pergunta se precisar), mostrando a tabela abaixo.
   Nunca escolha grupos sozinho.

## 2. Os 5 grupos (códigos CT VERBATIM — nunca invente/deduza outros)

Universo = os **88 sets com referência tcgcsv verificada por conteúdo**
(chaves de `DBZ_SET_TO_TCGCSV` do scanner). A partição é **travada por teste**
(`tests/test_scan_dbz_skill_profiles.py`) — nunca edite um código de cabeça.
O pricing DBZ é bulk (2 requests por set + lookup em memória), então os runs
são bem mais leves que os de Pokémon; as estimativas abaixo são iniciais —
**anote a duração real de cada grupo pra calibrar**.

| Grupo | Era | Sets | Est. inicial |
|---|---|---|---|
| **G1** | Fusion World completo (o jogo quente — boosters + starter decks + manga boosters) | 24 | ~30–60min |
| **G2** | Masters 2023+ (bt21..bt31, anniversary boxes, csv3) | 17 | ~25–50min |
| **G3** | Masters 2021–22 (Unison final + Zenkai: bt13..bt20, theme/collector's) | 18 | ~25–50min |
| **G4** | Masters 2019–20 (bt6..bt12, draft boxes, expansion sets) | 17 | ~20–40min |
| **G5** | Masters gênese 2017–18 (bt1..bt5, tournament/starter da 1ª leva) | 12 | ~15–30min |

**G1 — Fusion World completo:**
```bash
python cardtrader_scanner.py \
  --game dragonball \
  --sets fb10 fb09 fs12 fs11 fb08 sb02 fs10 fs09 sb01 fb07 fb06 fs08 fb05 fs06 fs07 fb04 fs05 fb03 fb02 fb01 fs04 fs03 fs02 fs01 \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_dbz_g1_<AAAAMMDD_HHMM>.xlsx
```

**G2 — Masters 2023+:**
```bash
python cardtrader_scanner.py \
  --game dragonball \
  --sets bt31 bt30 bt29 bt28 bt-27 bt26 bt25 bt24 bt23 bt22 bt21 sd23 be25 be24 be22 ex22 csv3 \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_dbz_g2_<AAAAMMDD_HHMM>.xlsx
```

**G3 — Masters 2021–22:**
```bash
python cardtrader_scanner.py \
  --game dragonball \
  --sets bt20 bt19 bt18 bt17 bt16 bt15 bt14 bt13 sd19 sd20 ts01 ts02 csv1 csvol2 mb01 vpp3 ex17 ex20 \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_dbz_g3_<AAAAMMDD_HHMM>.xlsx
```

**G4 — Masters 2019–20:**
```bash
python cardtrader_scanner.py \
  --game dragonball \
  --sets bt12 bt9 bt8 bt7 bt6 tb3 db1 db2 db3 eb1 vpp2 ex06 ex07 ex08 ex09 ex10 xd2 \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_dbz_g4_<AAAAMMDD_HHMM>.xlsx
```

**G5 — Masters gênese 2017–18:**
```bash
python cardtrader_scanner.py \
  --game dragonball \
  --sets bt5 bt4 bt3 bt2 bt1 tb01 tb2 sd1 ex01 ex03 ex04 ex05 \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --output outputs/scan_dbz_g5_<AAAAMMDD_HHMM>.xlsx
```

## 3. Rodar (um run por grupo, SEQUENCIAL)

- Valores canônicos em TODO run: `--game dragonball`, `--threshold 0.30`
  (**FRAÇÃO** — inteiro `30` = 3000% = zero deals sem erro),
  `--validate-top 30`, `--min-net-margin 0.20`.
- Scan custom (`/scan-dbz fb10 bt31`): mesmo comando trocando só a lista de
  `--sets`. Código fora do mapa verificado sai no warning "Sets não
  encontrados" — não insista; a inclusão de set novo é por PR (ver §6).
- **Nunca dois runs ao mesmo tempo** (mesma pasta de estado — o scanner
  recusa; vale também contra um run Pokémon simultâneo). Grupos escolhidos
  rodam **em sequência**, cada um em background, monitorado.
- Back-catalog Masters (G4/G5) tende a mercado eficiente (lição Pokémon:
  auditoria SWSH = 0 deal) — o gap costuma morar no Fusion World e nos sets
  recentes. Priorize G1/G2 quando o operador não especificar.
- Grupo que falhar não cancela os demais — registre com a saída real e siga.

## 4. Postprocess + entrega (por grupo, formato OBRIGATÓRIO)

Assim que **cada grupo** terminar (não espere os outros):

```bash
python cardtrader_postprocess.py \
  --input outputs/scan_dbz_g<N>_<stamp>.xlsx \
  --output outputs/relatorio_dbz_g<N>_<stamp>.xlsx \
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

## 5. Cuidados específicos de Dragon Ball

- **Variantes por sufixo no número** (`a` = Alternate Art, `sa` = Super Alt
  Art, `sr` = SPR/SLR, `sec` = SCR): o scanner casa a variante EXATA no
  tcgcsv; ambiguidade vira miss honesto (nunca o subtype mais barato). Linha
  com margem estranha em carta de variante → confira o `[TCG]` antes.
- **Cartas foil-only** (SR/SCR/SLR/leaders): sellers não marcam foil porque a
  carta só existe foil — o scanner usa a única impressão existente SEM flag
  de baixa confiança. Comum/incomum foil marcada usa o subtype Foil.
- **Sets antigos com número "pelado"** (ex.: `096` no bt1): resolvidos por
  cauda numérica única; colisão (BT×SD no mesmo group) vira miss honesto —
  cobertura parcial nesses sets é esperada, não é bug.
- **Staleness vale igual** (cópia barata some rápido): confira o preço ao
  vivo antes de comprar.

## 6. Fechamento e higiene

- Outputs de scan (`outputs/*`) são gitignored — NUNCA commite dados de scan.
- Fonte falhou → linha rotulada/`sem preço`; jamais fabrique número.
- Set DBZ novo no CT (ex.: fb11/bt32 quando lançarem, st01 quando o CT
  preencher os números): entra no mapa `DBZ_SET_TO_TCGCSV` **por PR**, após
  verificar o groupId contra o dump real do tcgcsv (mesmo ritual do mapa
  Pokémon) — e o teste de partição vai exigir alocá-lo num grupo daqui.
- Resumo final: grupos rodados, duração REAL de cada um (pra calibrar as
  estimativas iniciais), deals por classificação, sets pulados/falhos,
  caminhos dos XLSX/`.md` de apoio.
