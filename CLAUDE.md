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

Opções úteis:
- `--all-sets` = **rastreio COMPLETO** (todas as ~832 coleções de uma vez),
  começando pelas mais valiosas — é o modo do rastreio **semanal**. Esse modo é
  demorado (horas).
- `--threshold 0.20` acha ~5× mais deals que `0.30`, mas com mais ruído (mais
  falso positivo pra você filtrar).
- Rastreios longos: rode **em segundo plano** (sem travar o terminal). Nunca
  deixe rodando "preso" numa janela que você pode fechar sem querer.

---

## Cuidados — "achados" que costumam ser falsos

- **Cartas "Trainer Gallery" (código começa com `TG`)**: o preço de referência
  vem inflado (5 a 10×). O relatório já manda essas pra conferência manual, mas
  desconfie.
- **Coleções muito novas**: a base de preços de referência ainda é fraca nelas →
  pode faltar preço ou casar com a coleção errada.

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

*Versão do scanner: v2.12 (margem bruta — sem taxa embutida; 2026-06-06). Este
guia foi reescrito em linguagem acessível em 2026-06-05 — termos técnicos
explicados pra leitura do operador (Matheus).*
