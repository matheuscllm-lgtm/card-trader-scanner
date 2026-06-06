# CLAUDE.md — instruções para agentes (Claude Code) neste repo

> Objetivo: "rodar o CardTrader scanner" tem **um caminho só**. Siga este
> arquivo e evite re-descobrir coisas que já estão resolvidas no código.

## Este é o repo canônico

`matheuscllm-lgtm/card-trader-scanner` é a **fonte de verdade única** do
CardTrader scanner. Se você encontrar um `cardtrader_scanner.py` ou
`cardtrader_postprocess.py` em qualquer outro lugar (monorepo
`tcg-arbitrage-scanners`, `Scripts/`, cópia solta em Drive/Obsidian, scratch de
sessão de agente), é **STALE** — não rode. Confira o cabeçalho do scanner:
`Versão: v2.10` (ou superior). O `cardtrader_postprocess.py` canônico tem ~40k.

> **Nota de localização (2026-06-05):** o repo canônico mora em **disco local**
> (`~/card-trader-scanner`), fora do Google Drive. A pasta antiga no Drive
> (`…\TCG & Exportação\CardTrader Scanner\`) tinha o `.git` dentro do Drive
> sincronizado, o que corrompia refs (`desktop.ini`). Ela foi aposentada como
> repo — se ainda existir, é só arquivo de outputs, **não** rode git lá.

## O que é (e por que CardTrader, não MYP)

Compara singles Pokémon (EN, Near Mint, não-graded) no **cardtrader.com**
(marketplace europeu, EUR) vs **preço TCG Player** (market price US). Tese:
cartas valorizadas no mercado US desatualizadas na UE. É o setup **inverso** do
MYP (que compra barato no Brasil em BRL). Acesso via **JWT API** (`CT_JWT`),
**não** scraping → sem problema de Cloudflare.

## Setup (env novo)

```bash
python -m venv .venv
.venv\Scripts\activate              # PowerShell;  bash: source .venv/bin/activate
pip install -r requirements.txt     # requests, openpyxl, python-dotenv, PyYAML, pandas, numpy, portalocker
```

`.env` na raiz do repo (NÃO commitar — é gitignored):

```
CT_JWT=<CardTrader: Settings → API Access → Create New Token>   # obrigatório
POKEMONTCG_API_KEY=<opcional, grátis em pokemontcg.io/dev>
JUSTTCG_API_KEY=<opcional, se usar --provider justtcg>
```

`pandas`/`numpy` são pro **postprocess**; rode-o sempre pelo `.venv` do scanner.

## ⚠️ Gotcha #1 — `--threshold` é FRAÇÃO (oposto do MYP)

No CardTrader, `--threshold 0.25` = 25%. Passar `--threshold 25` significa
**2500%** → zero deals. Mesma convenção fracionária vale pra `--min-net-margin`
(`0.20` = 20%). O scanner auto-converte `> 1.0` com warning desde a v2.2, mas
**não conte com isso** — passe sempre a fração.

> O scanner **irmão MYP** (repo `myp-arbitrage-scanner`) usa o oposto:
> `--threshold` é **percent integer** (`25` = 25%). Não misture os dois.

## Modelo de custo (Hub fee 6%)

Operador acumula ~100 cards no **depósito Hub da CardTrader** na UE antes de
enviar consolidado pro Brasil → frete dilui per-card (~R$0,30, desprezível).
Logo:

```
custo final por carta = preço CT × 1.06   (só Hub fee 6%)
margem = (tcg − custo) / tcg              frete = 0 por default
```

O scanner aplica o `× 1.06` via **validação per-blueprint** (preço REAL com
markup CT), e o `cardtrader_postprocess.py` aplica o **mesmo** `× 1.06` antes da
classificação BUY NOW/REJECT (paridade scanner ↔ postprocess). Override pra
cenário sem consolidação: `--shipping-brl X`.

> **per-expansion vs per-blueprint:** o scan inicial usa preço per-expansion
> (RAW, sem markup); a validação (`--validate-top N`) refaz per-blueprint (preço
> final com tier markup +6%/+20%). **Sempre valide** — sem isso o histórico teve
> ~76% de falsos positivos.

## Rodar

```bash
# Scan + validação:
.venv\Scripts\python.exe cardtrader_scanner.py \
  --sets sfa scr par paf tef twm ssp dri blk jtg \
  --threshold 0.30 --validate-top 30 --min-net-margin 0.20 \
  --hub-fee 0.06 --output outputs/scan_<stamp>.xlsx

# Depois postprocess (relatório classificado):
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python.exe cardtrader_postprocess.py outputs/scan_<stamp>.xlsx
```

- `--sets` aceita codes CT (ex.: `scr`, `sfa`). Aliases CT↔pokemontcg.io estão
  mapeados no scanner (`SET_ALIAS_TO_PTCG`).
- `--threshold 0.20` destrava ~5× mais deals que `0.30` (mais ruído).
- Scan largo (`--max-expansions` alto / weekly completo) pode passar de 1h. Para
  runs longos, rode **detached/background** (Task Scheduler), nunca inline.
- `--dry-run` usa só cache; `--no-cache` força refetch.

## Falsos positivos conhecidos (verificar manual)

- **Trainer Gallery (`TG##`)**: preço pokemontcg.io infla 5-10×. O postprocess já
  manda esses pra MANUAL REVIEW automático (regex `^TG\d+`), mas confira.
- **Sets novos**: cobertura ruim do pokemontcg.io em expansões recentes → pode
  faltar preço ou casar set errado (Layer 1 strict + aliases mitigam).

## Saída e commit

- Outputs vão pra `outputs/` (gitignored — é dado, não código). O que entra no
  repo é o **código** + eventualmente um resumo `.md`. Não commite `.xlsx`,
  logs, skip-list backups, nem scripts scratch `_*.ps1`/`_*.py`.
- `scanner_skip_list.json` é **estado operacional local** (gitignored): cada
  máquina tem cobertura/rede diferente.
- Workflow = **branch + PR**. Não dê push direto em `main` (gateado).

## Não confundir

Existe um scanner irmão de **MYP** (repo `myp-arbitrage-scanner`, usa
`cloudscraper`/Cloudflare, threshold **percent integer**). É outro projeto.
