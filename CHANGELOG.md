# CardTrader Scanner Stack — Changelog

Mudanças cumulativas do `cardtrader_scanner.py` + `cardtrader_postprocess.py`.
Sob git desde 2026-05-13 (`matheuscllm-lgtm/card-trader-scanner`); CHANGELOG
mantido como narrativa adicional além dos commits.

## 2026-06-20 — Scanner v2.18: fim da inflação de holo rare vintage (pricing por raridade + reverse)

**Por quê:** a varredura vintage de 2026-06-19 entregou margens lindas (79%, 76%,
70%) — e quase TODAS eram **falso positivo**. Investigando com dado real
(pokemontcg.io 2026-06-20) caiu a ficha de um **bug-raiz** que vinha inflando
sistematicamente toda carta holográfica antiga.

**A causa-raiz:** o parse do listing definia `foil` lendo
`props["mtg_foil"]`/`["foil"]` — campos que **só existem em Magic**, nunca em
Pokémon. O campo Pokémon que diz se a carta é reverse (`pokemon_reverse`) era
**ignorado**. Resultado: **toda** carta Pokémon chegava `foil=False`. Como uma
"Holo Rare" padrão **não tem** variante `normal` na TCGPlayer, a prioridade
`normal → reverseHolofoil → …` escorregava pra **`reverseHolofoil`** — a versão
reverse, mais rara e **bem mais cara**. Referência inflada → margem fake. Reais:

| Carta | holofoil (correto) | reverseHolofoil (pego antes) | inflação |
|---|---|---|---|
| Gengar — Legendary Collection | $146.89 | $1599.99 | **+989%** |
| Claydol — EX Hidden Legends | $14.47 | $44.95 | +211% |
| Shiftry — EX Hidden Legends | $19.92 | $42.95 | +116% |
| Pinsir — EX Hidden Legends | $18.42 | $25.14 | +36% |

O fix v2.10 (normal-first) só corrigia cartas **não-holo** (que têm `normal`); as
**holo rares** continuavam inflando — incluindo o caso "Gengar não-foil $1600".

**Mudanças:**
- **Parse lê `pokemon_reverse`.** `foil=(mtg_foil or foil or pokemon_reverse)`.
  Reverse-holo → `foil=True`; holo padrão → `foil=False`.
- **Seleção de variante ciente de raridade.** Novo helper puro `_rarity_is_holo()`
  + parâmetro `rarity` em `market_price_usd` (alimentado por `l.rarity`). Prioridade:
  - `foil=True` (reverse) → `reverseHolofoil → holofoil → unlimitedHolofoil → normal`
  - `foil=False` + holo → `holofoil → unlimitedHolofoil → normal → reverseHolofoil`
  - `foil=False` + não-holo → `normal → holofoil → unlimitedHolofoil → reverseHolofoil`
  - `foil=None` (legado) → inalterado (v2.7 Layer 2)
- **Flag "Variante Baixa Confiança" recalibrada.** Não dispara pra holo rare
  (`holofoil` é a variante correta); só p/ carta não-holo que casou preço holo.
- **Verificado no data model CardTrader (2026-06-20):** `pokemon_rarity="Holo Rare"`
  + `pokemon_reverse=false` = holo padrão (→ holofoil); `=true` = reverse.
- **Escopo:** afeta holo rares de **todas as eras** (não só vintage); direção
  sempre conservadora (referência menor → menos falso positivo).
- **Testes:** `scripts/test_variant_disambiguation.py` reescrito (rarity+reverse;
  +regressões Shiftry/Gengar LC/Pidgey). Suíte **106/106 verde** + 8 de script.

**Inalterado:** margem bruta 30%, threshold fração, validação per-blueprint,
skip-list, overrides de timeout por set, filtro TG##, `--skip-backcatalog`.

## 2026-06-20 — Scanner v2.17: flag `--skip-backcatalog` (escaneia só coleções modernas)

**Por quê:** lição operacional mais repetida do projeto (auditoria 2026-06-08):
o **back-catalog** (sets antigos, era Sword & Shield e anteriores) é um mercado
**eficiente** — o preço na Europa já bate com o dos EUA, então quase nunca sobra
deal acionável (a auditoria mostrou **0 deal** em 17 sets SWSH / ~1.000 cartas).
O gap de arbitragem mora em **lançamentos novos**. Antes, pra focar nos modernos
num scan completo, o operador tinha que montar a lista `--sets` à mão. Esta flag
automatiza isso.

**Mudanças:**
- **`cardtrader_scanner.py` — nova flag `--skip-backcatalog`.** Restringe o scan
  às coleções **modernas/curadas** (a lista `PRIORITY_SET_CODES`, que já existia
  pra ordenação no `--all-sets`), pulando o back-catalog. Mais útil com
  `--all-sets`: corta **~832 → ~30 sets**. Combinada com `--sets`, **intersecta**
  com a lista do usuário (e loga quantas foram puladas). Sozinha (sem `--all-sets`
  nem `--sets`), filtra a lista do `config.yaml`.
- **`cardtrader_scanner.py` — helper PURO `filter_modern_sets(expansions,
  priority_codes=PRIORITY_SET_CODES)`.** Mantém só as expansões cujo `code` está
  na lista priority; preserva a ordem de entrada; case-insensitive; tolera `code`
  ausente/None/"". Sem rede → **testável offline**.
- **Testes:** novo `tests/test_skip_backcatalog.py` (11 casos: filtro modern/
  back-catalog, ordem, case, code ausente, param custom, default, registro da
  flag no parser). Suíte completa **106/106 verde** (era 95).
- **Docs:** header inline do scanner v2.15 → v2.17 (v2.16 foi postprocess-only,
  por isso o pulo); CLAUDE.md (Opções úteis + rodapé).
- **INALTERADO:** margem bruta 30%, threshold em fração, `--hub-fee 0.0`,
  validação per-blueprint, skip-list, overrides de timeout por set, filtro TG##,
  NM-only. A flag só **restringe o escopo de coleções** — não toca em preço,
  margem nem classificação.

> **Histórico:** este trabalho foi recuperado do PR #22 (fechado sem merge em
> 2026-06-19). O PR misturava uma Rodada 1 (CI offline, revertida na época) com
> esta Rodada 2; aqui só a Rodada 2 foi reaplicada, limpa, sobre o `main` atual.

## 2026-06-17 — v2.16: entrega = tabela no chat OBRIGATÓRIA + coluna Flag + fix `--help`

**Por quê:** paridade com o reforço feito no MYP (PR #36/v5.11.7). O CT já tinha
o gerador de tabela markdown (`build_delivery_markdown`, PR #16) e uma seção de
entrega no CLAUDE.md, mas faltavam três coisas: (1) o **enquadramento
MANDATÓRIO** ("gere SEMPRE pela ferramenta, nunca à mão; entregue no chat, nunca
XLSX por padrão; mostre TODOS os deals"); (2) **marcação visível de suspeitos**
na própria tabela do chat; (3) a convenção no **README** — que é o canal que
**viaja cross-env** (um Claude Code na nuvem clona o repo e lê README + CLAUDE.md,
não a memória local). Também foi achado e corrigido um bug no `--help`.

**Mudanças:**
- **`cardtrader_postprocess.py` — coluna `Flag` na tabela de entrega.** Nova
  coluna entre `Qtd` e `Links`: reusa a MESMA `classify_decision` (não duplica
  regra) e mostra **"validar manual"** nas linhas `REVISAR` (zona cinza /
  suspeita de margem inflada — `TG##`, sufixo alpha de promo/league, set sem
  cobertura confiável, markup anômalo); vazio em `COMPRA`. Traz pro chat, sem
  abrir o Excel, quais achados pedem conferência manual antes. **É só
  apresentação** — não muda margem, filtro nem classificação.
- **`cardtrader_postprocess.py` — fix do `--help`.** O help do `--hub-fee` tinha
  um `%` literal ("6%") que o argparse tentava interpolar (`help % params`) e
  estourava `TypeError: %i format`. Escapado pra `%%`. Agora `--help` funciona
  (era pré-requisito pra documentar o comando literal com flags verificadas).
- **`CLAUDE.md` — seção de entrega vira REGRA OBRIGATÓRIA.** Bloco imperativo
  pro assistente: (1) gerar pela ferramenta, nunca à mão; (2) entregar no chat,
  nunca XLSX por padrão; (3) mostrar TODOS os deals (`--top-md`); (4) não rankear
  "comprar/não comprar". Documenta a coluna `Flag`. Comando literal verificado.
- **`README.md` — nova seção "Entrega dos resultados (tabela no chat —
  OBRIGATÓRIO)"** + linha no Histórico. É o reforço que viaja cross-env.
- **Testes:** `tests/test_delivery_markdown.py` atualizado (cabeçalho de 12
  colunas, contagem de pipes) + novo `test_flag_marks_revisar_as_validar_manual`.
  12/12 verdes; suíte completa verde (sem regressão).
- **Inalterado:** geração da planilha, filtros, classificação COMPRA/REVISAR/NÃO,
  margem bruta, threshold fração, filtro TG##, todos os comandos do scanner.

## 2026-06-15 — Scanner v2.15: overrides de timeout por SET (fim do "churn" vintage)

**Problema (investigação do ciclo vintage):** alguns sets vintage pesados não
cabem no limite de tempo padrão por coleção (*per-set-timeout* = 8min). Eles
estouravam o tempo **sempre**, eram jogados na lista de pulos automática
(*skip-list*), pulados nos rastreios seguintes e **nunca mais escaneados por
completo**. Vira um ciclo vicioso ("churn"): entra na lista, é pulado, volta a
entrar. O operador teria que lembrar de passar `--per-set-timeout 20` à mão toda
vez — frágil. Casos confirmados:

- `df` (EX Dragon Frontiers) — precisa ~19min p/ cobrir 100% das 79 listings;
  com 8min, cortava sempre.
- `ds` (EX Delta Species), `n1` (Neo Genesis), `n4` (Neo Destiny) — cobertura
  **parcial** cortada por 12min; escaneariam mais com mais fôlego.
- `n2` (Neo Discovery) é **caso diferente** — quase sem preço de referência na
  pokemontcg.io (no-coverage genuíno). Esse é tratado pelo cap de *misses*
  (`--max-consecutive-misses`), **não** por timeout. Não recebe override.

**Solução (`cardtrader_scanner.py`):**
- Novo mapa code-level `SET_TIMEOUT_OVERRIDES` (código CardTrader → segundos) com
  os sets confirmados: `df`=1200s (20min), `ds`/`n1`/`n4`=1080s (18min). É código
  (não config que o operador edita) porque são **fatos estáveis** sobre sets
  específicos — moram ao lado das outras constantes (regex TG, TTLs).
- Novo resolver `effective_set_timeout_s(exp_code, default_s)`. Regras: o
  override **só ELEVA o teto** (`max(default, override)`) — um `--per-set-timeout`
  global ainda maior continua vencendo; se o operador desliga o timeout global
  (`--per-set-timeout 0`), tudo fica sem timeout (override não reativa); set sem
  override = comportamento histórico; código case-insensitive.
- `scan_expansion` resolve o timeout efetivo **uma vez** no topo e o usa em todos
  os pontos de checagem (pré-blueprints, pré-listings, loop de pricing) + na
  `deadline_ts` que governa retries/429-sleeps. Loga quando um override está
  ativo. `_check_set_timeout` ganhou parâmetro opcional `timeout_s` (None =
  retrocompat: cai no default da instância).
- **Inalterado:** flag `--per-set-timeout` (default 8min); mecânica de skip-list;
  cap de misses; mass-pricing-abort; margem bruta; threshold fração; TG##.
- **Estado local (fora do PR):** a skip-list vive em `%LOCALAPPDATA%`; as entradas
  `df/ds/n1/n4` que eram artefato de timeout curto foram limpas manualmente
  (backup feito), preservando `asc`/`paf` (pré-existentes) e `n2` (no-coverage).
- Testes: `tests/test_set_timeout_overrides.py` (11 casos — mapa de overrides,
  resolver em todas as regras, integração com `_check_set_timeout`).

> **Follow-up conhecido (não nesta mudança):** o timeout per-set é checado
> *entre* iterações do loop de listings — uma chamada HTTP travada (*stall*
> intra-call) não é interrompida no meio. (Nota v2.15: o watchdog intra-call de
> 429/Retry-After foi endereçado na v2.14 via truncamento de backoff; um
> watchdog genérico de stall HTTP de qualquer chamada segue como dívida.)

## 2026-06-15 — v2.14: correção + robustez (resultados corretos, sem travar)

Auditoria de correção/robustez (autorizada pelo operador). Cinco frentes; cada
uma com teste. Suíte inteira verde (16 arquivos de teste).

### Scanner (`cardtrader_scanner.py`)
- **Timeout que escapava (corrigido).** Quando o tempo de espera pedido num
  retry (ex.: a API pede "espere 60s") não cabia no limite restante do set, o
  programa às vezes "deixava passar" por uma fração de segundo e tentava de
  novo, escondendo o estouro. Agora, se a espera tem que ser cortada pelo
  limite, o programa aborta de forma previsível. (Um teste que já existia estava
  FALHANDO no main exatamente por isso — agora passa.)
- **Falha de preço silenciosa (corrigida).** Quando a fonte de preços
  (pokemontcg.io) respondia "ocupado" (429) ou "erro de servidor" (5xx), o
  programa tratava como "carta não existe" e seguia em silêncio — sumindo com
  achados de verdade, abortando coleções boas por engano e inflando a taxa de
  falha. Agora ele tenta de novo algumas vezes e, se persistir, registra como
  FALHA VISÍVEL (não como "carta inexistente"). Erro legítimo do servidor (4xx
  que não seja 429) continua sendo tratado como "sem correspondência".
- **Dois scanners ao mesmo tempo (bloqueado).** Se você (ou um agendador) tentar
  rodar dois scanners usando a MESMA pasta de estado, o segundo agora RECUSA
  iniciar com uma mensagem clara — antes os dois brigavam pelo mesmo arquivo de
  cache e a coisa ficava lentíssima (~9s por carta), o que fazia a "lista de
  coleções a pular" ser preenchida com coleções boas por engano. Se você
  realmente precisa rodar dois, use `--allow-concurrent`.
- **Câmbio no arquivo de recuperação (corrigido).** Quando um scan trava no
  meio e é recuperado, o arquivo recuperado agora preserva a cotação do dólar do
  scan original (antes vinha zerado, e a coluna "CT US$" da tabela de entrega
  ficava em branco). A decisão COMPRA/REVISAR nunca foi afetada por isso.
- **Nova coluna "Variante Baixa Confiança".** Marca "Sim" quando uma carta
  vendida como NÃO-brilhante casou preço só com uma versão brilhante cara — sinal
  de que o preço de referência pode ser da versão errada. É só um aviso para você
  conferir; não muda o preço nem a classificação.

### Recovery (`scripts/recover_from_checkpoint.py`)
- Lê a cotação do cabeçalho do checkpoint e reconstrói a célula `usd_brl_rate`.

### Testes novos
- `scripts/test_ptcg_transient_errors.py` (5 casos): 429/5xx viram falha
  visível, não "miss"; 429→200 recupera; 200 vazio e 400 = sem-match sem exceção.
- `scripts/test_run_guard.py` (4 casos): recusa de instância concorrente,
  re-aquisição após release, state-dirs diferentes não conflitam, PID gravado.
- `scripts/test_checkpoint_crash_recovery.py`: +1 caso (FX reconstruído do header).

## 2026-06-09 — Postprocess: tabela de ENTREGA em markdown (links clicáveis)

Padroniza a **apresentação** do resultado no formato aprovado pelo operador
(paridade com o scanner COMC): a entrega é uma **tabela markdown no chat**, não
planilha. Threshold/filtros/classificação **inalterados** — só formato de saída.

### Postprocess (`cardtrader_postprocess.py`)
- Nova função `build_delivery_markdown(df, cfg, fx_usd_brl, top_n)` emite:
  ```
  | # | Margem % | CT US$ | TCG US$ | Dif | Carta | Set | Raridade | Cond | Qtd | Links |
  ```
  - **Carta** = nome + número combinados (reusa `_combine_name_number`).
  - **Links** = `[oferta](url_ct) · [TCG](url_tcg)` — markdown clicável; `[oferta]`
    aponta pro CardTrader, `[TCG]` é o workflow de validação manual do operador.
  - **CT US$** = `live_usd` se houver, senão `live_brl ÷ FX`; **TCG US$** = nativo
    (`reference_price_usd`); **Dif** = TCG US$ − CT US$. Sem FX → CT US$ vazio
    (não inventa câmbio).
  - Filtra só COMPRA/REVISAR via `classify_decision` (mesma regra do XLSX),
    ordena por `net_margin` desc, `--top-md` linhas (default 50).
- `_read_fx_usd_brl()` lê `usd_brl_rate` da aba **Stats** do raw do scanner.
- `write_report` agora **também** grava um `.md` sidecar (mesmo nome do output) e
  imprime a tabela no stdout; retorna o markdown. Nova flag `--top-md`.
- Novo alias de coluna `reference_price_usd` (`TCG Market (USD)`), p/ levar o
  preço USD nativo do raw até a tabela.
- **Inalterado:** XLSX/CSV/JSON seguem **colunares com URLs cruas**; margem
  BRUTA; threshold fração; TG## → MANUAL REVIEW; pisos de preço.
- Testes: `tests/test_delivery_markdown.py` (11 casos — header exato, Carta
  composta, links clicáveis, conversão CT US$ via FX, Dif, filtro COMPRA/REVISAR,
  pipe→`/`, vazio amigável, `--top-md`).

## 2026-06-06 — Scanner v2.12 + Postprocess: margem BRUTA (remove Hub fee do cálculo)

Decisão do operador (regra cross-scanner): o scanner deve reportar **apenas
margem bruta** = `(tcg − preço_página) / tcg`, threshold 30%, **SEM nenhuma taxa
embutida**. O operador calcula Hub fee/frete/cartão/IOF por fora, manualmente.
Isso **SUPERSEDE a fórmula antiga do `× 1.06`** (v2.3, 2026-05-12).

### Scanner (`cardtrader_scanner.py`)
- `--hub-fee` default `0.06` → **`0.0`**. A constante `HUB_FEE_RATE = 0.06`
  permanece apenas como referência histórica / opt-in.
- Construtor `Scanner(hub_fee_rate=...)` default `0.06` → **`0.0`** (paridade
  programática com a CLI).
- Margem inicial e recalc per-blueprint: `custo = live_brl × (1 + hub_fee_rate)`;
  com `0.0`, `custo = preço do site` → margem bruta `(tcg − preço)/tcg`.
- Stats sheet do XLSX agora grava o `hub_fee_rate` **realmente aplicado** (não
  mais a constante) + nova linha `margin_basis` ("BRUTA (sem taxa)").
- Log de startup distingue margem bruta (`--hub-fee 0.0`) de líquida.

### Postprocess (`cardtrader_postprocess.py`)
- `HUB_FEE_RATE` módulo-level `0.06` → **`0.0`**.
- `DecisionConfig.hub_fee_rate` novo campo (default `0.0`), threaded por
  `write_report` → `enrich_df` → `_recompute_margin_with_fee`.
- Recompute de margem: `(tcg − live × (1 + hub_fee_rate)) / tcg`; com `0.0`
  vira margem bruta pura. Paridade scanner ↔ postprocess mantida.
- Nova flag `--hub-fee` (default `0.0`) com auto-conversão `>1.0` (aceita `6`
  ou `0.06`), igual ao scanner.
- Summary sheet ("Math: custo total") reflete a base bruta dinamicamente.

### Inalterado (confirmado)
- `--threshold` segue **fração** `0.30` (=30%). Convenção NÃO mexida.
- `--shipping-brl` segue default `0.0`.
- Piso de preço `$10` (~R$50) MANTIDO — é filtro, não taxa.

## 2026-05-18 — Scanner v2.8 Layer 4 + Postprocess v2.3 Layer 5

Motivação: validação manual dos 10 deals do weekly v2.6 (operador, 2026-05-18)
revelou 3 falsos positivos sistêmicos:

1. **Pichu Expedition #22** — scanner pegou `holofoil` ($224.99) mas seller CT
   vende non-foil → TCG real (Default Landing) é `reverseHolofoil` ($50.41).
   Margem cálculo errado 4×.
2. **Lusamine sm5/153a** — alpha suffix `153a` indica **1st Place Pokemon
   League** variante; scanner matched main set Lusamine sm5/153 ($160) mas
   real é $13.77. Pokemontcg.io cego pra promos com sufixo alfanumérico.
3. **Tyranitar Aquapolis** — mesmo padrão Pichu (Holofoil vs Reverse Holofoil,
   $210 vs $69.99).

Diagnóstico: ~90% dos Holo Rare antigos têm Default Landing = Reverse Holofoil
no TCG Player. Scanner ignorava o foil-flag do listing CT.

### Scanner (v2.8 Layer 4)

- **`market_price_usd` foil-aware** (`PokemonTcgIoProvider`):
  - `foil=True` → priority `holofoil → unlimitedHolofoil → normal →
    reverseHolofoil`
  - `foil=False` → priority `reverseHolofoil → normal → holofoil →
    unlimitedHolofoil`
  - `foil=None` → preserva v2.7 Layer 2 (`holofoil → normal →
    reverseHolofoil → unlimitedHolofoil`)
- **Sempre excluir** `1stEditionHolofoil` + `1stEditionNormal` (inflam 3-10×)
- `PricingProvider.last_variant_used` exposto pra scan_expansion
- `Opportunity.price_variant_used` novo campo
- Cache `set_price` anota `_variant_used` no card dict antes de json.dumps;
  `get_price` extrai pra hidratar cache hits (sem refazer _search)
- XLSX gain coluna **Variant** entre Foil e Seller (operador valida foil-listing
  match com `holofoil`; non-foil com `reverseHolofoil`)

### Postprocess (v2.3 Layer 5 — alpha suffix filter)

- `ALPHA_SUFFIX_RE = ^\d+[a-zA-Z]+` detecta `153a`, `022a`, `156b`, etc.
- Não conflita com TG## (filtrado antes por TRAINER_GALLERY_RE)
- `classify_decision` retorna `REVISAR` + "Promo/League variant — valide TCG manual"
  pra qualquer card com alpha suffix
- Coluna `Link TCG` (v2.7.1) permite operador validar variante em 1 clique

### Test cases validados

- Pichu ecard1/22 foil=True → $224.99 (holofoil) ✓
- Pichu ecard1/22 foil=False → $120.57 (reverseHolofoil) ✓
- Arbok ecard1/3 foil=True → $82.77 (holofoil) ✓
- Arbok ecard1/3 foil=False → $27.93 (reverseHolofoil) ✓
- Vaporeon base2/12 foil=True → $52.25 (mantém ground truth v2.7 Layer 2,
  fallback `unlimitedHolofoil`) ✓
- Lusamine sm5/153a → REVISAR via Layer 5 ✓

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
