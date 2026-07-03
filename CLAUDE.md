# CLAUDE.md — guia do scanner CardTrader

> **Este arquivo tem dois leitores:**
> 1. **Você, Matheus** — pra entender o que o scanner faz e como rodá-lo.
> 2. **O assistente de IA (Claude Code)** — que lê este arquivo no começo de
>    cada sessão pra saber como trabalhar neste projeto sem re-descobrir tudo.
>
> Por isso ele mistura linguagem simples com alguns termos técnicos. **Toda
> palavra técnica é explicada entre parênteses na primeira vez que aparece**, e
> há um **glossário no fim**. Vá no seu ritmo — com o tempo os termos ficam
> familiares.

---

## 🛰️ Convenções da frota (cross-scanner)

> **Manual completo** (repo privado): https://github.com/matheuscllm-lgtm/scanners-commons — erros comuns, referências de preço, chaves, GitHub Actions e modelo de entrega de TODOS os scanners. Cópia-mestra local: `C:\Users\mathe\scanners-commons\`.

Invariantes que valem para TODOS os scanners:
- **Margem BRUTA, mínimo 30%** — só `(revenda − compra)/compra`, sem taxa embutida; piso de relevância R$50 (~US$10).
- **Só Near Mint** — condição por match EXATO `== "NM"`, nunca substring (já vazou SP).
- **Nunca inventar preço** — fonte falhou → marca fallback/erro e segue; jamais fabrica número.
- **Entrega = tabela markdown no chat** (nunca XLSX por padrão), gerada pela ferramenta do repo, mostrando TODAS as linhas (aprovadas + rejeitadas). Coluna `Carta` = nome + número; coluna `Links` combinada = `[oferta](url) · [TCG/referência](url)`.
- ⚠️ **Convenção de threshold:** percentual inteiro (`30`) = MYP, Liga, eBay; fração (`0.30`) = CardTrader, COMC, Selados.

Erros recorrentes (3 famílias — detalhe no manual):
1. **Segredo/ambiente:** BOM/zero-width numa chave → crash latin-1 no header → scan "verde mas vazio". Setar sem BOM (`printf '%s' 'KEY' | gh secret set`) **e** sanitizar ao ler no código (`.strip()` NÃO tira BOM).
2. **Git:** galho ou `main` local defasado por squash-merge PARECE pendência. O teste real de "já mergeado" é `git diff --stat origin/main <galho>` estar vazio (não `git merge-base`).
3. **Honestidade de preço:** inflação de referência, fallback tratado como real, NM frouxo → sempre validar versão/condição e rotular fallback.

**Este scanner:** referência de preço = pokemontcg.io com validação per-blueprint (casa NM + variante exata) → **fallback `tcgcsv.com`** (v2.23; só em set que a pokemontcg.io não precifica, ex. `asc`; mesma escada de variante, nunca o mais barato); chaves = `CT_JWT`, `POKEMONTCG_API_KEY`.

## Em uma frase

Este programa compara o **preço de cartas Pokémon** (avulsas, em inglês, estado
Near Mint / "quase perfeita") no site europeu **cardtrader.com** contra o preço
de referência dos EUA (**TCG Player**), e aponta onde dá pra comprar barato na
Europa e revender caro. É o caminho **inverso** do scanner MYP (que garimpa
barato no Brasil).

---

## Onde mora o programa (importante)

- **Pasta oficial:** `C:\Users\mathe\card-trader-scanner` — no **disco do seu
  computador** (HD local), fora do Google Drive.
- Existe uma **cópia na nuvem** no GitHub (um site que guarda código), no
  endereço `github.com/matheuscllm-lgtm/card-trader-scanner`. As duas se
  espelham.

> **Por que saiu do Google Drive (junho/2026):** o Drive ficava mexendo nos
> arquivos internos de controle do programa e corrompia coisas. Mudamos pro HD
> local e **apagamos a pasta antiga do Drive**. Se você vir uma pasta
> "CardTrader Scanner" no Drive, ela é lixo antigo — não use.

---

## Como preparar o computador (só na primeira vez)

São três passos, feitos uma vez por máquina. *"venv" = ambiente virtual: uma
caixinha isolada onde o programa instala as ferramentas que precisa, sem
bagunçar o resto do Windows.*

```bash
python -m venv .venv                 # cria a caixinha
.venv\Scripts\activate               # entra na caixinha
pip install -r requirements.txt      # instala as ferramentas listadas
```

Depois, crie um arquivo chamado `.env` (texto simples) na pasta, com a sua
**senha de acesso ao CardTrader** (chamada de "token" — uma senha longa que o
site gera pra você). Ele fica assim:

```
CT_JWT=<seu token do CardTrader: no site, Settings → API Access → Create New Token>
POKEMONTCG_API_KEY=<opcional, grátis em pokemontcg.io/dev>
```

> ⚠️ O `.env` **nunca** vai pra nuvem (tem sua senha dentro). O programa já está
> configurado pra ignorá-lo.

---

## ⚠️ A pegadinha nº 1 — a "margem mínima" é em fração

Quando você manda o programa procurar deals, define uma **margem mínima de lucro**
(`--threshold`, lê-se "thréshould" = limiar). Aqui ela é escrita como **fração**:

- `--threshold 0.25` quer dizer **25%**.
- Se você escrever `--threshold 25`, o programa entende **2.500%** → não acha
  nada.

> O scanner irmão (MYP) faz o **oposto** (lá `25` = 25%). Não confunda os dois.

---

## A conta do lucro (margem BRUTA — você soma as taxas por fora)

**Mudança de 2026-06-06:** o programa agora mostra só a **margem bruta** — o
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

> **Detalhe técnico (pode pular):** o primeiro rastreio usa um preço "cru"
> (*per-expansion*); a conferência (`--validate-top`) refaz com o preço **real
> de checkout** (*per-blueprint*). **Sempre conferir** — sem isso, no passado
> ~76% dos "achados" eram falsos.
>
> A opção `--hub-fee` continua existindo nos dois scripts e tem **default 0.0**
> (margem bruta). Se um dia quiser reembutir os 6% antigos, passe `--hub-fee 0.06`
> no scanner **e** no postprocess.

---

## Como rodar (o dia a dia)

Um comando tem três partes: **o programa** · **as opções** (começam com `--`,
chamadas "flags") · **os valores**. Exemplo comentado:

```bash
# 1) Rastrear alguns sets e já conferir os melhores candidatos:
.venv\Scripts\python.exe cardtrader_scanner.py \
  --sets sfa scr par paf tef twm ssp dri blk jtg \   # quais coleções (códigos CardTrader)
  --threshold 0.30 \                                  # margem mínima 30%
  --validate-top 30 \                                 # confere os 30 melhores de verdade
  --min-net-margin 0.20 \                             # descarta lucro líquido < 20%
  --output outputs/scan_da_vez.xlsx                   # onde salvar a planilha

# 2) Gerar o relatório organizado (decisão COMPRA/REVISAR/NÃO):
#    Aqui --input e --output são OBRIGATÓRIOS (não dá pra omitir).
.venv\Scripts\python.exe cardtrader_postprocess.py \
  --input outputs/scan_da_vez.xlsx \
  --output outputs/relatorio_da_vez.xlsx
```

> **Skill `/scan`** (`.claude/commands/scan.md`, jul/2026): o jeito canônico de
> pedir um scan ao assistente — formato padrão da frota, igual ao `scan-myp`.
> Os **128 sets com preço de referência real** (derivados de
> `SET_ALIAS_TO_PTCG` + `VINTAGE_SET_CODES`, sem os `wcd*`/McDonald's/duplicatas)
> estão divididos em **6 grupos por recência** (G1 = Mega Evolution até Chaos
> Rising + era SV … G6 = EX inicial + e-Card + WotC), cada um ≤~2h30 de scan —
> runs mais longos morriam sem entregar. O skill **sempre pergunta quais grupos
> rodar**, roda um por vez (nunca em paralelo) com os valores canônicos
> (threshold 0.30, validate-top 30, min-net-margin 0.20) e entrega **cada grupo**
> pela tabela do postprocess assim que termina. `/scan pre ssp` = sets custom;
> `/scan total` = catálogo inteiro via workflow semanal. **Nenhum scan roda
> fora do skill**; a partição é travada por teste
> (`tests/test_scan_skill_profiles.py`) contra o mapa do scanner.

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
- `--threshold 0.20` acha ~5× mais deals que `0.30`, mas com mais ruído (mais
  falso positivo pra você filtrar).
- Rastreios longos: rode **em segundo plano** (sem travar o terminal). Nunca
  deixe rodando "preso" numa janela que você pode fechar sem querer.

---

## Como o resultado é ENTREGUE (tabela no chat, com links pra clicar) — REGRA OBRIGATÓRIA

> **Regra do operador (jun/2026):** a entrega do resultado é uma **tabela no
> chat** — **não** uma planilha. A planilha (`.xlsx`) continua sendo gerada e
> guardada na pasta `outputs/`, mas é arquivo de apoio, não a entrega.

> **⚠️ Instrução MANDATÓRIA pro assistente (Claude Code) — não opcional:**
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
> suspeitos de margem inflada (lembre: no passado ~76% dos "achados" eram
> falsos sem validação per-blueprint).

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

## Cuidados — "achados" que costumam ser falsos

- **Cartas "Trainer Gallery" (código começa com `TG`)**: o preço de referência
  vem inflado (5 a 10×). O relatório já manda essas pra conferência manual, mas
  desconfie.
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
> jun/2026 o programa **recusa** iniciar um segundo scanner que use a mesma pasta
> de estado (ele avisa com uma mensagem clara), porque dois ao mesmo tempo
> brigavam pelo mesmo arquivo de cache e ficavam lentíssimos. Se algum dia você
> precisar mesmo rodar dois, use pastas de estado diferentes (`--state-dir`) ou a
> opção `--allow-concurrent`.

---

## Coleções vintage demoram mais (e o programa já sabe disso)

O programa tem um **limite de tempo por coleção** (chamado *per-set-timeout*):
se uma coleção demora demais pra ser rastreada, ele desiste dela pra não travar
o rastreio inteiro, e a coloca numa **lista de pulos** (*skip-list*) pra não
tentar de novo logo em seguida. O padrão é **8 minutos por coleção**.

O problema (descoberto em jun/2026): algumas coleções **vintage** (antigas, com
muitas cartas) precisam de bem mais que 8 minutos. Elas estouravam o tempo
**toda vez**, entravam na lista de pulos e **nunca eram rastreadas por completo**
— um ciclo sem fim. Era preciso lembrar de mandar um tempo maior à mão toda vez.

**O conserto (v2.15):** o programa agora guarda, no próprio código, um **tempo
maior só pra essas coleções específicas** — você não precisa lembrar de nada.
Hoje a lista é: `df` (EX Dragon Frontiers, 20min), `ds` / `n1` / `n4` (18min). Se
um dia você quiser dar ainda mais tempo a todas, o `--per-set-timeout 25` (em
minutos) ainda vale e vence o ajuste interno. (`n2` = Neo Discovery é caso
diferente: a base de preços quase não tem essa coleção, então o problema dela
não é tempo — é falta de referência mesmo.)

---

## Quando algo é alterado no código

- Os resultados (planilhas `.xlsx`, registros de execução) **não** vão pra nuvem
  — são dados, não programa.
- Toda mudança no programa segue um ritual de segurança: cria-se uma **cópia de
  trabalho** ("branch"), faz-se a alteração lá, abre-se um **pedido de revisão**
  ("PR" = pull request) e só então junta-se ao oficial ("main"). O assistente de
  IA nunca altera o oficial direto. *(Você não precisa fazer isso à mão — é como
  o trabalho técnico é organizado.)*

---

## Não confundir com o outro scanner

Existe um programa **irmão**, o **MYP** (pasta `myp-arbitrage-scanner`), que
garimpa cartas baratas no **Brasil**. Ele é um projeto **separado**, com regras
diferentes (inclusive a margem mínima, que lá é em número inteiro). São dois
programas distintos.

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
| **threshold** | a margem mínima de lucro pra um deal aparecer (aqui em **fração**) |
| **postprocess** | a etapa que pega o rastreio cru e gera o relatório organizado |
| **outputs/** | a pasta onde as planilhas de resultado são salvas |

---

*Versão do scanner: v2.24 (guard reverse-outlier — common/uncommon NÃO-holo que
casa no `reverseHolofoil` da pokemontcg.io com razão reverse/normal absurda (>5×,
ex. Lileep ex12-56 68×) dispara "Variante Baixa Confiança" e é rebaixada COMPRA→
REVISAR no postprocess; sinal-only, margem/preço/bucket inalterados; constante
`REVERSE_NONHOLO_OUTLIER_RATIO=5.0`; 172 testes; 2026-06-26). Inclui v2.23
(fonte de FALLBACK tcgcsv.com — preenche SÓ os sets
que a pokemontcg.io não precifica, ex.: asc/Ascended Heroes, que sem isso ficava
invisível; resolução de set unique-match-only, MESMA seleção de variante da
pokemontcg.io — sem colapsar pro subtype mais barato —, validação per-blueprint
como guard final, fonte rotulada via `price_source`/coluna `Fonte Preço`, opt-out
`--no-tcgcsv-fallback`; 150 testes; 2026-06-23). Inclui v2.22 (contrato de entrega
scanner→postprocess — fim da "entrega vazia": o scanner persiste todo listing
precificado no XLSX e o threshold vira classificação downstream com fallback
near-miss; 2026-06-22.
Pós-v2.22 mergeados: GG## pulado em scan time igual TG## (regex `^(?:TG|GG)\d+`,
#36) e write_xlsx garante o diretório-alvo antes de salvar — fim do
FileNotFoundError em clone limpo sem `outputs/`, #37). Inclui v2.21 (lista
curada "vintage core" + flag `--vintage`; 2026-06-21), v2.18-v2.20 (fim da
inflação holo rare vintage + validação per-blueprint NM+reverse + cache-bust;
2026-06-20/21). Inclui v2.17 (flag `--skip-backcatalog` — escaneia só as ~30
coleções modernas/curadas, pulando o back-catalog que não rende deal; 2026-06-20).
Inclui v2.16 (entrega = tabela no chat OBRIGATÓRIA via a ferramenta
do repo, nunca à mão / nunca XLSX por padrão; coluna Flag "validar manual" nas
linhas REVISAR; fix do `--help` do postprocess; 2026-06-17). Inclui v2.15
(overrides de timeout por coleção pra sets vintage pesados; 2026-06-15) e v2.14
(correção + robustez — 2026-06-15: timeout
que escapava corrigido, falha de preço silenciosa corrigida, bloqueio de
scanners concorrentes, câmbio preservado na recuperação, coluna "Variante Baixa
Confiança"). Margem bruta — sem taxa embutida (v2.12, 2026-06-06). Este guia foi
reescrito em linguagem acessível em 2026-06-05 — termos técnicos explicados pra
leitura do operador (Matheus).*
