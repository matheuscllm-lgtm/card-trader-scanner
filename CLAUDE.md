# CLAUDE.md — card-trader-scanner

> **Este arquivo tem dois leitores:**
> 1. **Você, Matheus** — pra entender o que o scanner faz e como rodá-lo.
> 2. **Qualquer sessão Claude Code (local ou na nuvem)** — que lê este arquivo
>    no começo de cada sessão pra saber como trabalhar neste projeto sem
>    re-descobrir tudo.
>
> Por isso ele mistura linguagem simples com alguns termos técnicos. **Toda
> palavra técnica é explicada entre parênteses na primeira vez que aparece**, e
> há um **glossário no fim**. Vá no seu ritmo — com o tempo os termos ficam
> familiares. *(Guia reescrito em linguagem acessível em 2026-06-05, decisão do
> operador.)*

**Em uma frase:** este programa compara o **preço de cartas Pokémon** (avulsas,
em inglês, estado Near Mint / "quase perfeita") no site europeu
**cardtrader.com** contra o preço de referência dos EUA (**TCG Player**), e
aponta onde dá pra comprar barato na Europa e revender caro. É o caminho
**inverso** do scanner MYP (que garimpa barato no Brasil).

---

## 🛰️ Convenções da frota (cross-scanner)

> **Manual completo** (repo privado): https://github.com/matheuscllm-lgtm/scanners-commons — erros comuns, referências de preço, chaves, GitHub Actions e modelo de entrega de TODOS os scanners. Cópia-mestra local (PC do operador): `C:\Users\mathe\scanners-commons\`.

Invariantes que valem para TODOS os scanners:

- **Margem BRUTA, mínimo 30%** — só `(revenda − compra)/compra`, sem nenhuma taxa embutida (frete, cartão, IOF — o operador calcula por fora).
- **Piso de relevância R$50 (~US$10) — SÓ para cartas avulsas (singles).** Produtos SELADOS não têm piso (decisão do operador, 2026-06-27); lá o único critério é a margem ≥30%.
- **Só Near Mint** — condição por match EXATO `== "NM"`, nunca substring (já vazou SP).
- **Nunca inventar preço** — fonte falhou → marca fallback/erro e segue; jamais fabrica número.
- **Nunca recomendar compra** — o scanner reporta margem, flags e fontes; a decisão de capital é do operador.
- **Entrega = tabela markdown no chat** (nunca XLSX/CSV por padrão), gerada pela ferramenta do repo — nunca montada à mão —, mostrando TODAS as linhas (aprovadas + rejeitadas). Coluna `Carta` = nome + número; coluna `Links` combinada = `[oferta](url) · [TCG/referência](url)`.
- ⚠️ **Convenção de threshold:** percentual inteiro (`30`) = MYP, Liga, eBay; fração (`0.30`) = CardTrader, COMC, Selados.

Erros recorrentes (3 famílias — detalhe no manual):

1. **Segredo/ambiente:** BOM/zero-width numa chave → crash latin-1 no header → scan "verde mas vazio". Setar sem BOM (`printf '%s' 'KEY' | gh secret set`) **e** sanitizar ao ler no código (`.strip()` NÃO tira BOM).
2. **Git:** branch ou `main` local defasado por squash-merge PARECE pendência. O teste real de "já mergeado" é `git diff --stat origin/main <branch>` estar vazio (não `git merge-base`).
3. **Honestidade de preço:** inflação de referência, fallback tratado como real, NM frouxo → sempre validar versão/condição e rotular fallback.

**Este scanner:** referência de preço = pokemontcg.io com validação per-blueprint (casa NM + variante exata) → **fallback `tcgcsv.com`** (v2.23; só em set que a pokemontcg.io não precifica, ex. `asc`; mesma escada de variante, nunca o mais barato); chaves = `CT_JWT`, `POKEMONTCG_API_KEY`.

---

## Onde mora o programa (importante)

- **Pasta oficial (PC do operador):** `C:\Users\mathe\card-trader-scanner` —
  no **disco do computador** (HD local), fora do Google Drive.
- Existe uma **cópia na nuvem** no GitHub (um site que guarda código), no
  endereço `github.com/matheuscllm-lgtm/card-trader-scanner`. As duas se
  espelham. Sessões Claude Code na nuvem trabalham num **clone** (cópia
  baixada) desse repo.

> **Por que saiu do Google Drive (junho/2026):** o Drive ficava mexendo nos
> arquivos internos de controle do programa e corrompia coisas. Mudamos pro HD
> local e **apagamos a pasta antiga do Drive**. Se você vir uma pasta
> "CardTrader Scanner" no Drive, ela é lixo antigo — não use.

---

## ⚠️ A pegadinha nº 1 — a "margem mínima" é em FRAÇÃO

Quando você manda o programa procurar deals, define uma **margem mínima de
lucro** (`--threshold`, lê-se "thréshould" = limiar). Aqui ela é escrita como
**fração**:

- `--threshold 0.25` quer dizer **25%**.
- Se você escrever `--threshold 25`, o programa entende **2.500%** → não acha
  nada, sem dar erro nenhum.

> O scanner irmão (MYP, repo `myp-arbitrage-scanner`) faz o **oposto** (lá
> `25` = 25%). São dois projetos separados, com regras diferentes — não
> confunda os dois. (Ver a tabela de convenções da frota, acima.)

---

## A conta do lucro (margem BRUTA — você soma as taxas por fora)

**Mudança de 2026-06-06 (v2.12):** o programa mostra só a **margem bruta** — o
desconto puro, sem descontar nenhuma taxa. A conta é a mais simples possível:

```
margem = (preço de referência TCG − preço no site) ÷ preço TCG
```

> **O que isso quer dizer na prática:** o programa pega o preço que aparece na
> ficha da carta no CardTrader e compara com o preço de referência dos EUA
> (TCG Player). O número que aparece na planilha é esse desconto cru. **Você
> (Matheus) é quem soma o Hub fee, o frete, a taxa do cartão e o IOF por fora**,
> manualmente, do seu jeito, pra decidir se vale a pena.

> **Por que mudamos:** antes o programa já tirava 6% sozinho (de "Hub fee").
> Agora ele não mexe em nada — só te dá o número limpo. Fica mais fácil você
> conferir a margem da planilha contra o que vê no site, sem ter que "desfazer"
> a taxa de cabeça.

> ⚠️ **Base do denominador (divergência conhecida com a frota):** a fórmula
> genérica do bloco da frota divide pelo preço de **compra**; **este scanner
> divide pelo preço de REVENDA (TCG)** — confirmado no código:
> `margin = (tcg_brl - custo_brl) / tcg_brl` (`cardtrader_scanner.py`). É a
> mesma divergência já reconhecida no scanner integrado (que recalcula tudo na
> base compra ao unificar as fontes). **Não "corrija" a fórmula daqui** sem
> decisão explícita do operador — a base revenda dá um número menor ou igual,
> então nenhum deal aprovado aqui viraria reprovado na base da frota.

> **Detalhe técnico (pode pular):** o primeiro rastreio usa um preço "cru"
> (*per-expansion*, agregado por coleção); a conferência (`--validate-top`)
> refaz com o preço **real de checkout** (*per-blueprint*, por carta exata).
> **Sempre conferir** — sem isso, no passado **~76% dos "achados" eram falsos**.
> ⚠️ O default de `--validate-top` é **0** (omitir = NENHUMA validação): sempre
> passe o valor canônico `--validate-top 30`.
>
> A opção `--hub-fee` continua existindo nos dois scripts e tem **default 0.0**
> (margem bruta). Se um dia quiser reembutir os 6% antigos, passe `--hub-fee
> 0.06` no scanner **e** no postprocess.

---

## Como rodar

### Preparar o ambiente (só na primeira vez)

São três passos, feitos uma vez por máquina. *"venv" = ambiente virtual: uma
caixinha isolada onde o programa instala as ferramentas que precisa, sem
bagunçar o resto do sistema.*

```bash
# Windows (PC do operador):
python -m venv .venv                 # cria a caixinha
.venv\Scripts\activate               # entra na caixinha
pip install -r requirements.txt      # instala as ferramentas listadas

# Nuvem/Linux (clone limpo): mesmos comandos, com "source .venv/bin/activate"
# no lugar do activate do Windows (ou use o python do ambiente direto).
```

Depois, crie um arquivo chamado `.env` (texto simples) na pasta, com a sua
**senha de acesso ao CardTrader** (chamada de "token" — uma senha longa que o
site gera pra você). Ele fica assim:

```
CT_JWT=<seu token do CardTrader: no site, Settings → API Access → Create New Token>
POKEMONTCG_API_KEY=<opcional, grátis em pokemontcg.io/dev>
```

> ⚠️ O `.env` **nunca** vai pra nuvem (tem sua senha dentro). O programa já está
> configurado pra ignorá-lo. Cuidado com BOM/zero-width ao setar chaves (erro
> recorrente nº 1 da frota, acima).

### 🎯 O caminho canônico de scan é o skill `/scan` — nenhum scan roda fora dele

**Skill `/scan`** (`.claude/commands/scan.md`, jul/2026): o jeito canônico de
pedir um scan ao assistente — formato padrão da frota, igual ao `scan-myp`.
Os **128 sets com preço de referência real** (derivados de
`SET_ALIAS_TO_PTCG` + `VINTAGE_SET_CODES`, sem os `wcd*`/McDonald's/duplicatas)
estão divididos em **6 grupos por recência** (G1 = Mega Evolution até Chaos
Rising + era SV … G6 = EX inicial + e-Card + WotC), cada um ≤~2h30 de scan —
runs mais longos morriam sem entregar. O skill **sempre pergunta quais grupos
rodar**, roda um por vez (nunca em paralelo) com os valores canônicos
(threshold 0.30, validate-top 30, min-net-margin 0.20) e entrega **cada grupo**
pela tabela do postprocess assim que termina. `/scan pre ssp` = sets custom;
`/scan total` = catálogo inteiro via workflow semanal. A partição é travada por
teste (`tests/test_scan_skill_profiles.py`) contra o mapa do scanner. **Nenhum
scan do CardTrader roda fora do skill.**

Existe também o skill **`/auto`** (`.claude/commands/auto.md`): modo autônomo
de trabalho no repo (tarefas de código/manutenção ponta a ponta, com os freios
duros descritos nele). Ele **não** substitui o `/scan` para scans.

### Os comandos que o skill executa (referência — pra manutenção e debug)

Um comando tem três partes: **o programa** · **as opções** (começam com `--`,
chamadas "flags") · **os valores**. Se algum dia precisar rodar à mão (debug),
use exatamente os valores canônicos:

```bash
# 1) Rastrear alguns sets e já conferir os melhores candidatos:
.venv\Scripts\python.exe cardtrader_scanner.py \
  --sets sfa scr par paf tef twm ssp dri blk jtg \   # quais coleções (códigos CardTrader)
  --threshold 0.30 \                                  # margem mínima 30% (FRAÇÃO!)
  --validate-top 30 \                                 # confere os 30 melhores de verdade
  --min-net-margin 0.20 \                             # descarta lucro líquido < 20%
  --output outputs/scan_da_vez.xlsx                   # onde salvar a planilha

# 2) Gerar o relatório organizado (decisão COMPRA/REVISAR/NÃO):
#    Aqui --input e --output são OBRIGATÓRIOS (não dá pra omitir).
.venv\Scripts\python.exe cardtrader_postprocess.py \
  --input outputs/scan_da_vez.xlsx \
  --output outputs/relatorio_da_vez.xlsx
```

(Na nuvem/Linux, troque `.venv\Scripts\python.exe` por `python`.)

**Defaults que enganam (documentados de propósito):**

- `--validate-top` default **0** = sem validação per-blueprint se omitido —
  crítico, dado os ~76% de falsos sem ela. Canônico = `30`.
- `--min-net-margin`: default **0.0 no scanner** e **0.25 no postprocess** —
  o comando canônico passa `0.20` explícito no scanner; no postprocess, quem
  quiser o mesmo corte precisa passar explicitamente.

Opções úteis:

- `--all-sets` = **rastreio COMPLETO** (todas as ~832 coleções de uma vez),
  começando pelas mais valiosas — é o modo do rastreio **semanal**. Esse modo é
  demorado (horas).
- `--skip-backcatalog` = **só as coleções modernas/curadas** (~30, em vez de
  ~832). Pula o **back-catalog** (sets antigos, era Sword & Shield e anteriores),
  que é mercado eficiente e quase nunca rende deal (a auditoria de 2026-06-08 deu
  **0 deal** em 17 sets SWSH). Use junto com `--all-sets` pra um scan completo
  **muito mais rápido**, focado em lançamentos novos — que é onde o gap aparece.
  Se combinar com `--sets`, ele cruza a sua lista com as modernas (fica só a
  interseção).
- `--vintage` (v2.21) = a lista curada "vintage core" de sets antigos.
- `--threshold 0.20` acha ~5× mais deals que `0.30`, mas com mais ruído (mais
  falso positivo pra você filtrar).
- Rastreios longos: rode **em segundo plano** (sem travar o terminal). Nunca
  deixe rodando "preso" numa janela que você pode fechar sem querer.
- Outras flags existem (`--provider`, `--include-graded`, `--dry-run`,
  `--no-cache`, `--max-expansions`, `--shipping-brl`, `--ignore-skip-list`,
  `--clear-skip-list`, `--chase-only`, `--opportunities-only`,
  `--checkpoint-every`, `--flush-every-listings`, `--max-consecutive-misses`,
  `--per-set-timeout`, `--state-dir`, `--allow-concurrent`,
  `--no-tcgcsv-fallback`; no postprocess: `--revisar-min-net`,
  `--revisar-modest-min`, `--min-lucro`, `--top-md`, `--doubleholo`,
  `--no-pid-resolve`) — `--help` de cada script lista tudo.

> ⚠️ **Gotcha do fallback tcgcsv (registrado 2026-07-06):** o fallback
> `tcgcsv.com` (v2.23) tem **dois gatilhos**: o cap de misses consecutivos
> (`--max-consecutive-misses > 0`) e um **resgate de fim de set** (set que
> completa o loop de pricing com 0 hit na pokemontcg.io e listings pendentes
> tenta o tcgcsv para todos os misses — mesmo com o cap em 0). Na prática o
> resgate só vale se o set completar o loop dentro do per-set-timeout — e num
> set como `asc` (Ascended Heroes, que só o tcgcsv precifica) o per-listing
> lento da pokemontcg.io historicamente estourava o timeout antes do resgate.
> Um comentário no código (`SET_TIMEOUT_OVERRIDES`) diz que a skill passa `40`,
> mas o `scan.md` atual **NÃO passa essa flag** — discrepância aberta entre
> código e skill. Consequência prática: num scan que inclua `asc`, sem a flag o
> set **pode sair com 0 preço** apesar de o tcgcsv ter os dados. Se for rodar
> `asc` à mão, passe `--max-consecutive-misses 40`; a correção definitiva
> (alinhar skill ↔ código) deve ir por PR.

### Workflows do GitHub Actions (nuvem)

Três workflows em `.github/workflows/`:

- **`tests.yml`** ("tests"): roda a suíte de testes em todo push na `main`,
  em todo PR e por dispatch manual.
- **`daily-scan.yml`** ("Daily CT Scan"): apesar do nome, **só roda por
  dispatch manual** (`workflow_dispatch` — decisão do operador 2026-05-16: sem
  agendamento; runs autônomos rodam LOCAL via venv + `.env`). Aceita inputs
  `sets`, `threshold` (fração), `min_net_margin` e `validate_top`.
- **`weekly-scan.yml`** ("Weekly Scan (full scope)"): rastreio completo, **só
  dispatch manual**. Desde 2026-06-18 (higiene de repo público) os resultados
  saem **apenas como artifacts** do workflow (ficam atrás da aba Actions e
  expiram sozinhos) — o antigo mecanismo de "live partials" numa branch pública
  foi aposentado porque publicaria a lista de deals. Resultado totalmente
  privado = rodar local. É este workflow que o `/scan total` usa.

Os secrets `CT_JWT` e `POKEMONTCG_API_KEY` moram nos Secrets do repo (Actions);
nunca em arquivo versionado.

---

## 📤 Como o resultado é ENTREGUE (tabela no chat, com links pra clicar) — REGRA OBRIGATÓRIA

> **Regra do operador (jun/2026):** a entrega do resultado é uma **tabela no
> chat** — **não** uma planilha. A planilha (`.xlsx`) continua sendo gerada e
> guardada na pasta `outputs/`, mas é arquivo de apoio, não a entrega.

> **⚠️ Instrução MANDATÓRIA pro assistente — não opcional:**
> Sempre que for entregar resultados deste scanner ao operador, você **DEVE**:
> 1. **Gerar a tabela pela ferramenta do repo** (`cardtrader_postprocess.py`,
>    que chama `build_delivery_markdown`). **NUNCA monte a tabela à mão** nem
>    reformate números/links você mesmo — a ferramenta garante o formato, os
>    links clicáveis e a classificação coerente com a planilha.
> 2. **Colar a tabela markdown no chat** (terminal ou app). **NUNCA** entregar
>    XLSX/CSV por anexo como padrão. Só mande arquivo se o operador **pedir
>    explicitamente**.
> 3. **Mostrar TODOS os deals** (COMPRA + REVISAR) — não uma amostra curada.
>    Se forem muitos, use `--top-md N` com N alto o bastante pra cobrir todos
>    (o default 50 já cobre a grande maioria das runs); a planilha sempre traz
>    todos sem corte.
> 4. **Não rankear "comprar/não comprar".** Você reporta margem, flags e fontes;
>    quem decide capital é o operador.
> 5. **NUNCA monte tabela à mão, nem mesmo quando "não há deal".** A ferramenta
>    **sempre** entrega uma tabela no formato canônico: se nenhum item passa o
>    limiar, ela mostra os **candidatos mais próximos por margem** marcados
>    *"abaixo do limiar"* (fallback near-miss). Logo **não existe** o caso "veio
>    vazio, então eu reformato" — esse era o erro recorrente. Se a entrega que
>    você vai colar **não saiu do `.md` da ferramenta**, pare e gere por ela.

**Para explorar abaixo do threshold padrão** (ver o que está "perto"), rebaixe os
limiares **na própria ferramenta** — nunca leia o XLSX e monte à mão:

```bash
.venv\Scripts\python.exe cardtrader_postprocess.py \
  --input outputs/scan_da_vez.xlsx --output outputs/relatorio.xlsx \
  --min-net-margin 0.20 --revisar-min-net 0.10 --min-lucro 0
```

O comando literal de entrega (passo 2 do "Como rodar") **já produz a tabela** —
ele imprime no terminal E grava um arquivo `.md` ao lado da planilha:

```bash
.venv\Scripts\python.exe cardtrader_postprocess.py \
  --input outputs/scan_da_vez.xlsx \
  --output outputs/relatorio_da_vez.xlsx \
  --top-md 50                                 # quantas linhas na tabela do chat
```

A tabela tem as colunas:

```
| # | Margem % | CT US$ | TCG US$ | Dif | Carta | Set | Raridade | Cond | Qtd | Flag | Links |
```

O que cada coluna quer dizer:

| Coluna | O que é |
|---|---|
| **#** | posição no ranking (1 = maior margem) |
| **Margem %** | o desconto bruto (preço EUA − preço Europa) ÷ preço EUA |
| **CT US$** | preço no CardTrader, **em dólar** (convertido do real pela cotação do dia, que o programa lê da planilha) |
| **TCG US$** | preço de referência dos EUA (TCG Player), em dólar |
| **Dif** | a diferença em dólar (TCG US$ − CT US$) — quanto "sobra" antes das taxas |
| **Carta** | nome **+ número** numa célula só (ex.: `Hitmonlee (013/110)`). Se o nome já tem o número, não duplica |
| **Set** | a coleção (código do CardTrader) |
| **Raridade** / **Cond** | raridade oficial e condição (sempre Near Mint) |
| **Qtd** | quantas unidades o vendedor tem (você importa em lote) |
| **Flag** | aviso de cautela por linha: **"validar manual"** quando a carta caiu na zona REVISAR (margem borderline OU suspeita de inflada — `TG`, sufixo de promo/league, set sem cobertura confiável, markup anômalo). Vazio = COMPRA limpa. **É só um aviso**, não muda a margem |
| **Links** | **dois links pra clicar:** `[oferta]` abre a página da carta no CardTrader · `[TCG]` abre a página do TCG Player **pra você conferir o preço à mão** |

> **Por que a coluna Flag:** ela traz pro chat a mesma classificação que a
> planilha faz (`COMPRA` / `REVISAR`). Assim, sem abrir o Excel, você já vê
> quais achados são "limpos" e quais pedem **conferência manual** antes — os
> suspeitos de margem inflada (lembre dos ~76% de falsos sem validação
> per-blueprint, na seção "A conta do lucro").

> **Por que dois links:** o `[TCG]` é o seu jeito padrão de **conferir** o preço
> antes de comprar. O `[oferta]` te leva direto à carta no CardTrader.

A tabela aparece **na tela** quando o postprocess roda, e também é salva num
arquivo de texto `.md` ao lado da planilha (mesmo nome, terminação `.md`) — é só
copiar e colar no chat.

> **Detalhe técnico (pode pular):** a tabela do chat **junta** colunas (Carta =
> nome+número; Links = oferta+TCG) só pra ficar legível. A planilha (`.xlsx`) e
> os arquivos `.csv`/`.json` continuam com **colunas separadas e os endereços
> (URLs) crus**, do jeito que ferramentas de importação esperam. Margem, filtros
> e classificação (COMPRA/REVISAR/NÃO) **não mudaram** — só a apresentação.

---

## Coluna DH — 2ª opinião do Double Holo (opcional)

O postprocess aceita `--doubleholo <arquivo.json>`: adiciona uma coluna **DH**
(nota 0-100; 50 = neutro; >50 = Double Holo otimista) que resume a leitura de
mercado do Double Holo pra carta (previsão de preço, sinal de IA, ROI de
gradação, momentum). Regras duras:

- **NÃO entra na margem nem na decisão COMPRA/REVISAR** — o preço de referência
  continua sendo o TCGplayer (pokemontcg.io/tcgcsv). É coluna **extra**, uma
  segunda opinião.
- O JSON canônico vem de `scanners-commons/tooling/doubleholo_signals.py ingest
  --json` (a nota `dh_score` é calculada UMA vez lá; `doubleholo_join.py` daqui
  só a **lê**, nunca recalcula — pra não haver fórmulas divergindo entre repos).
- **Join determinístico por productId do TCGplayer** — nunca por nome. Linha
  sem productId resolvido mostra "—" (honesto; não inventa).
- Pras linhas precificadas via pokemontcg.io (cujo Link TCG é um redirect por
  cardId, sem productId), o resolver offline `tcgcsv_productid.py` resolve o
  productId via tcgcsv (bulk por set, sem seguir redirect HTTP), com
  desambiguação por variante; se não resolver pra exatamente 1 productId →
  `None` → "—". Honestidade > cobertura: nunca chuta. `--no-pid-resolve`
  desliga esse resolver (só tem efeito junto com `--doubleholo`).
- Se o JSON falhar ao carregar, o postprocess avisa ("--doubleholo ignorado") e
  a entrega segue **sem** a coluna DH, idêntica ao comportamento sem a flag.

---

## Cuidados — "achados" que costumam ser falsos

- **Cartas "Trainer Gallery" (código começa com `TG`)**: o preço de referência
  vem inflado (5 a 10×). O relatório já manda essas pra conferência manual, mas
  desconfie. (Desde o pós-v2.22/#36, `TG##` **e** `GG##` são pulados já em scan
  time — regex `^(?:TG|GG)\d+`.)
- **Coleções muito novas**: a base de preços de referência ainda é fraca nelas →
  pode faltar preço ou casar com a coleção errada.
- **Sets antigos (back-catalog)**: mercado já "eficiente" — o preço na Europa
  costuma bater com o dos EUA, então quase nunca sobra deal. Auditoria de
  2026-06-08: toda a era Sword & Shield (17 sets, ~1.000 cartas) deu **0 deal**.
  Gaste energia em **lançamentos novos** — é onde o gap aparece.
- **Use o piso de preço padrão (≈US$10)**: subir o piso (ex.: `--min-price-usd
  25`) esconde a faixa barata (US$10–25), que é justamente onde **a maioria dos
  deals mora**. No teste de 06-08, subir pra $25 derrubou os achados de 12 → 2.
- **A cópia barata pode já ter sumido ("staleness")**: o número que o scanner
  mostra é o preço de *quando ele rastreou*. Cópias baratas vendem rápido —
  quando você for comprar, pode só restar a cara. **Confira o preço ao vivo
  antes de comprar.** (Ex. 06-08: Arceus VSTAR scan R$54 → real R$75 → virou
  prejuízo.)
- **Coluna "Variante Baixa Confiança" (jun/2026; reforçada em v2.24)**: quando
  aparece "Sim", a carta foi anunciada como **não-brilhante** mas o único preço
  de referência encontrado era de uma versão **brilhante cara** — OU (novo em
  v2.24) é uma comum/incomum **reverse** cujo preço de referência reverse é um
  número **fino e fora da curva** vs a versão normal (mais de 5× o normal; ex.:
  Lileep ex12-56 normal US$0,55 vs reverse US$37,50 = 68×). Em ambos os casos o
  preço pode ser da versão errada / de pouca liquidez → a margem pode estar
  inflada. **Confira a versão no Link TCG antes de comprar.** A margem e o preço
  **não mudam** — mas a partir de **v2.24** essa linha é **rebaixada de COMPRA
  para REVISAR** ("validar manual"): nunca mais aparece como COMPRA limpa. (Não
  rebaixa o que já era NÃO: margem baixa, TG##, STALE seguem NÃO.)

> **Não rode dois scanners na mesma pasta de estado ao mesmo tempo.** A partir de
> jun/2026 (v2.14) o programa **recusa** iniciar um segundo scanner que use a
> mesma pasta de estado (ele avisa com uma mensagem clara), porque dois ao mesmo
> tempo brigavam pelo mesmo arquivo de cache e ficavam lentíssimos. Se algum dia
> você precisar mesmo rodar dois, use pastas de estado diferentes (`--state-dir`)
> ou a opção `--allow-concurrent`.

---

## Coleções vintage (e ME) demoram mais — e o programa já sabe disso

O programa tem um **limite de tempo por coleção** (chamado *per-set-timeout*):
se uma coleção demora demais pra ser rastreada, ele desiste dela pra não travar
o rastreio inteiro, e a coloca numa **lista de pulos** (*skip-list*) pra não
tentar de novo logo em seguida. O padrão é **8 minutos por coleção**.

O problema (descoberto em jun/2026): algumas coleções **vintage** (antigas, com
muitas cartas) precisam de bem mais que 8 minutos. Elas estouravam o tempo
**toda vez**, entravam na lista de pulos e **nunca eram rastreadas por completo**
— um ciclo sem fim. Era preciso lembrar de mandar um tempo maior à mão toda vez.

**O conserto (v2.15):** o programa guarda, no próprio código
(`SET_TIMEOUT_OVERRIDES`), um **tempo maior só pra essas coleções específicas**
— você não precisa lembrar de nada. Lista atual (verificada no código):

- `df` (EX Dragon Frontiers) — **20 min**;
- `ds` / `n1` / `n4` — **18 min**;
- `cri` (Chaos Rising, era Mega Evolution / me4 — adicionado no #47) —
  **20 min**: a pokemontcg.io não precifica o set, então ele cai no fallback
  tcgcsv per-listing, que é lento.

Se um dia você quiser dar ainda mais tempo a todas, o `--per-set-timeout 25`
(em minutos) ainda vale e vence o ajuste interno. Notas:

- `n2` (Neo Discovery) **NÃO** recebe override de propósito: a base de preços
  quase não tem essa coleção — o problema dela não é tempo, é falta de
  referência (tratado pelo cap de `--max-consecutive-misses`, não por timeout).
- `asc` (Ascended Heroes) também **NÃO** precisa de override: o resgate tcgcsv
  dele é um bulk único, não per-listing — mas exige o gotcha do
  `--max-consecutive-misses > 0` (ver "Como rodar").

---

## Scanner paralelo: Dragon Ball Super (`dbs_scanner.py`)

> **Decisão do operador (2026-07-17):** a frota era Pokémon-only e deixava passar
> deals de Dragon Ball no CardTrader (ex.: energy markers **Gold** e promos
> **Release Event/Tournament Winner** do set Fusion World Promos — caso real que
> motivou a ferramenta). O `dbs_scanner.py` cobre esse buraco SEM tocar o fluxo
> Pokémon: é um script separado, que **não** passa pelo skill `/scan` (que segue
> Pokémon-only) e não usa pokemontcg.io.

- **O que faz:** varre expansões de **Dragon Ball Super** no CardTrader
  (game_id 9 — Fusion World `fb*`/`fs*`/`fuspromo` + Masters `bt*`) com ofertas
  **AO VIVO** do marketplace (menor NM inglês não-graded) e compara com o
  **market price do TCGplayer** via tcgcsv.com (categorias 80 + 27).
- **Join oferta↔referência DETERMINÍSTICO:** `blueprint.tcg_player_id` ==
  `productId` do tcgcsv (mesma filosofia do join DH por productId). Blueprint sem
  `tcg_player_id` (comum nos sets Masters antigos) passa por um **join
  SECUNDÁRIO** também determinístico: nome EXATO normalizado + cauda do número,
  **match único obrigatório e só blueprint SEM versão** (variante Gold/Alt Art
  nunca entra) — rotulado por linha na coluna `join` do CSV. O que sobrar fica
  **FORA com contagem explícita** — nunca fuzzy por nome, nunca preço inventado.
- **Convenções:** margem BRUTA base compra `(TCG_BRL − CT_BRL)/CT_BRL`;
  `--threshold` em **FRAÇÃO** (0.30; passar `30` aborta com erro); piso de
  relevância na referência (`--min-price-usd 10`); NM por match **EXATO**
  `== "Near Mint"`; graded/assinada nunca entram; oferta <50% da referência vai
  pro bucket 🚨 REVISAR (possível lixo/scam), nunca vira COMPRA limpa.
- **Câmbio:** `--fx` manual OU automático (open.er-api.com) — sem fonte real o
  run **falha alto** (nunca chuta). Ofertas em moeda sem taxa conhecida são
  puladas e contadas.
- **Entrega:** tabela markdown canônica da frota gerada pelo próprio script
  (buckets 🟢 COMPRA / 🚨 REVISAR / 🔎 Quase + contagens honestas de cobertura;
  `Links` = `[oferta](cardtrader) · [TCG](tcgplayer)` em toda linha) + CSV com
  TODAS as linhas avaliadas em `outputs/` (gitignored). Cache tcgcsv em
  `outputs/dbs_cache/` (TTL 20h).
- **Run longo nunca fica mudo:** o `.md`/`.csv` são regravados CUMULATIVAMENTE a
  cada expansão concluída, com marcador `⏳ PARCIAL — N/M expansões` no cabeçalho
  até o fim (dá pra entregar parcial no chat a qualquer momento). No `--all` a
  varredura vai das expansões mais novas pras antigas. Sidecar
  `<out>_semref.csv` lista todo blueprint COM oferta NM viva que ficou sem
  referência TCG, com o motivo — nada some em silêncio.
- **Como rodar:**

  ```bash
  python dbs_scanner.py --list-expansions              # códigos disponíveis
  python dbs_scanner.py --expansions fuspromo --threshold 0.30
  python dbs_scanner.py --all --threshold 0.30         # catálogo DBS inteiro (lento)
  ```

- **Contratos travados em teste:** `tests/test_dbs_scanner.py` (34 testes
  offline — filtros NM/EN/graded, conversão de moeda, joins por tcg_player_id e
  secundário nome+número, piso, guardas anti-lixo e de referência volátil,
  fração no threshold, marcador PARCIAL, motivos do semref, 2 links por linha).
- Primeira prova real (2026-07-17, `fuspromo`): 545 blueprints → 163 avaliadas →
  21 COMPRA ≥30%, incluindo os casos que motivaram a ferramenta.

## Testes

```bash
python -m pytest              # Windows: .venv\Scripts\python.exe -m pytest
```

- **243 testes** coletados (verificado com `pytest --collect-only -q` em
  2026-07-17, após `pip install -r requirements.txt`).
- O `pytest.ini` escopa a coleta a `testpaths=tests` **de propósito**: os
  `scripts/test_*.py` são run-scripts standalone (testes operacionais rodados à
  mão), deliberadamente fora da suíte do pytest.
- Testes que travam contratos importantes: `tests/test_scan_skill_profiles.py`
  (partição dos 6 grupos do `/scan`) e `tests/test_doubleholo_join.py`
  (join da coluna DH).

---

## Arquitetura (o que é cada arquivo)

```
cardtrader_scanner.py       o scanner: varre o CardTrader, precifica (pokemontcg.io → fallback tcgcsv) e grava o XLSX cru
cardtrader_postprocess.py   o relatório: classifica COMPRA/REVISAR/NÃO e gera a tabela de ENTREGA (build_delivery_markdown)
dbs_scanner.py              scanner PARALELO de DRAGON BALL (Fusion World/Masters): CT ao vivo vs TCGplayer — ver seção própria
doubleholo_join.py          coluna DH (2ª opinião Double Holo) — só lê a nota do JSON canônico, join por productId
tcgcsv_productid.py         resolver offline de productId TCGplayer (pro join DH; identidade, nunca toca preço)
config.yaml                 configuração
CHANGELOG.md                histórico narrativo completo (desde 2026-04-29)
pytest.ini                  escopo da suíte (testpaths=tests)
tests/                      a suíte do pytest (243 testes)
scripts/                    utilitários operacionais: recover_from_checkpoint.py, checkpoint_to_partial.py,
                            peek_deals.py, launchers .ps1 do PC do operador, e run-scripts test_*.py (fora do pytest)
diagnose_*.py (raiz)        scripts de diagnóstico pontual (jtg, no_deals, pricing)
.claude/commands/           skills /scan (canônico de scan) e /auto (modo autônomo)
.github/workflows/          tests.yml, daily-scan.yml, weekly-scan.yml (ver "Workflows")
outputs/                    planilhas/relatórios locais (gitignored — dados, não programa)
cardtrader_postprocess_legacy_v1.5.py   versão antiga preservada por referência
```

---

## Fluxo de desenvolvimento e segurança

- Os resultados (planilhas `.xlsx`, registros de execução) **não** vão pra nuvem
  — são dados, não programa. O repo é **público**: lista de deals nunca entra
  nele (nem em branch — por isso o weekly entrega por artifacts, 2026-06-18).
- Toda mudança no programa segue um ritual de segurança: cria-se uma **cópia de
  trabalho** ("branch"), faz-se a alteração lá, abre-se um **pedido de revisão**
  ("PR" = pull request) e só então junta-se ao oficial ("main"). O assistente
  nunca altera o oficial direto. *(Você não precisa fazer isso à mão — é como o
  trabalho técnico é organizado.)*
- Chaves (`CT_JWT`, `POKEMONTCG_API_KEY`) moram no `.env` local (gitignored) ou
  nos Secrets do GitHub Actions — **nunca** em arquivo versionado.

---

## Glossário (as palavras técnicas que aparecem aqui)

| Palavra | O que é, em simples |
|---|---|
| **scanner** | o programa que "varre" os preços procurando oportunidades |
| **repositório / repo** | a pasta do projeto, com todo o código e histórico |
| **GitHub** | site que guarda o código na nuvem e seu histórico de versões |
| **clone** | uma cópia do projeto baixada do GitHub pro seu computador |
| **branch** | uma "cópia de trabalho" paralela, pra mexer sem afetar o oficial |
| **main** | a versão **oficial** do código |
| **commit** | um "salvar com etiqueta" — registra uma mudança no histórico |
| **push** | enviar suas mudanças pro GitHub (nuvem) |
| **PR (pull request)** | pedido pra juntar uma branch ao oficial, depois de revisar |
| **venv** | a "caixinha" isolada com as ferramentas do programa |
| **flag / opção** | um ajuste no comando, começa com `--` (ex.: `--threshold`) |
| **token** | uma senha longa que um site gera pra programas acessarem sua conta |
| **threshold** | a margem mínima de lucro pra um deal aparecer (aqui em **fração** — ver "A pegadinha nº 1") |
| **postprocess** | a etapa que pega o rastreio cru e gera o relatório organizado |
| **skill** | um runbook pronto que o assistente segue (ex.: `/scan`) |
| **workflow (Actions)** | um "robô" do GitHub que roda comandos na nuvem quando disparado |
| **artifact** | o arquivo de resultado que um workflow guarda (expira sozinho) |
| **outputs/** | a pasta onde as planilhas de resultado são salvas |

---

## Estado, pendências e histórico de versões

**Versão declarada no cabeçalho do `cardtrader_scanner.py`: v2.24** — mas o
`main` já contém código **pós-v2.24 mergeado**, incluindo um fix rotulado
**v2.25** no postprocess. Pendência de bookkeeping: registrar o v2.25 no
`CHANGELOG.md` e atualizar o cabeçalho. Uma linha por versão (o detalhe
narrativo completo vive no `CHANGELOG.md`):

- **v2.25** (2026-07-03, #52 — rotulado no código do postprocess; ainda fora do
  CHANGELOG): linhas near-miss chegam do scanner **sem `lucro_liq`** e caíam
  todas em "Dados insuficientes" no `classify_decision`, mesmo com
  `--revisar-min-net` rebaixado; agora `net_margin`/`lucro_liq` são recomputados
  **só onde faltam** (linhas validadas, que já têm valor real, não mudam).
- **Pós-v2.24 mergeados** (sem bump de versão): coluna **DH** / integração
  Double Holo (`--doubleholo`, `doubleholo_join.py`, `tcgcsv_productid.py`);
  alias `cri`→me4 + timeout override do `cri` (#47); skill `/scan` v1–v3
  (#48–#50).
- **v2.24** (2026-06-26): guard reverse-outlier — common/uncommon NÃO-holo que
  casa no `reverseHolofoil` da pokemontcg.io com razão reverse/normal absurda
  (>5×, ex. Lileep ex12-56 = 68×) dispara "Variante Baixa Confiança" e é
  rebaixada COMPRA→REVISAR no postprocess; sinal-only, margem/preço/bucket
  inalterados; constante `REVERSE_NONHOLO_OUTLIER_RATIO=5.0`.
- **v2.23** (2026-06-23): fonte de FALLBACK `tcgcsv.com` — preenche SÓ os sets
  que a pokemontcg.io não precifica (ex.: `asc`, que sem isso ficava invisível);
  resolução de set unique-match-only; MESMA seleção de variante da pokemontcg.io
  (sem colapsar pro subtype mais barato); validação per-blueprint como guard
  final; fonte rotulada via `price_source`/coluna `Fonte Preço`; opt-out
  `--no-tcgcsv-fallback`.
- **Pós-v2.22** (#36, #37): `GG##` pulado em scan time igual `TG##` (regex
  `^(?:TG|GG)\d+`); `write_xlsx` garante o diretório-alvo antes de salvar (fim
  do FileNotFoundError em clone limpo sem `outputs/`).
- **v2.22** (2026-06-22): contrato de entrega scanner→postprocess — fim da
  "entrega vazia": o scanner persiste todo listing precificado no XLSX e o
  threshold vira classificação downstream, com fallback near-miss.
- **v2.21** (2026-06-21): lista curada "vintage core" + flag `--vintage`.
- **v2.18–v2.20** (2026-06-20/21): fim da inflação de holo rare vintage;
  validação per-blueprint casa NM + reverse/variante; cache-bust do pricing.
- **v2.17** (2026-06-20): flag `--skip-backcatalog` (só as ~30 coleções
  modernas/curadas).
- **v2.16** (2026-06-17): entrega = tabela no chat OBRIGATÓRIA via a ferramenta
  do repo, nunca à mão / nunca XLSX por padrão; coluna Flag "validar manual" nas
  linhas REVISAR; fix do `--help` do postprocess.
- **v2.15** (2026-06-15): overrides de timeout por coleção pra sets vintage
  pesados.
- **v2.14** (2026-06-15): correção + robustez — timeout que escapava corrigido,
  falha de preço silenciosa corrigida, bloqueio de scanners concorrentes,
  câmbio preservado na recuperação, coluna "Variante Baixa Confiança".
- **v2.12** (2026-06-06): margem BRUTA — sem taxa embutida.
- **2026-06-05**: este guia reescrito em linguagem acessível pro operador.

**Pendências vivas:** (a) registrar o v2.25 no CHANGELOG e no cabeçalho de
versão; (b) resolver a discrepância skill↔código do `--max-consecutive-misses`
no fallback tcgcsv (ver o gotcha em "Como rodar").
