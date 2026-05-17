# run_weekly_local.ps1 - dispara weekly full CT scan + postprocess v2
#
# v3 (2026-05-17, fix definitivo pós-incident weekly 2026-05-16):
#   Endurecimento total dos call-sites de path-quoting + redirect.
#   Trocas vs v2 (eb3948f -> b332287):
#     - Test-Path -> Test-Path -LiteralPath (path com '[','&',espaço, acento)
#     - $rawOut/$finalOut passam por Set-StrictMode-friendly array splat
#     - Postprocess redirect: dropa `1>`/`2>` (que em PS5.1 encodam UTF-16);
#       captura via `*>&1 | Set-Content -LiteralPath -Encoding utf8 -Append`
#       que escreve UTF-8 puro e nao interpreta path como wildcard
#     - DEBUG line antes do call dumpando args completos pra pos-mortem
#     - Se postprocess falhar, dump explicito dos args do array no log
#     - Defensive: $stamp param-izavel pra rerun arbitrario sem hardcode
#
# v2 (2026-05-16 noite, pos-crash de Base Set) -- MANTIDO:
#   - sem Tee-Object (UTF-16 garbled em 20k+ listings)
#   - sem $ErrorActionPreference='Stop' (WriteError matava silenciosamente)
#   - python -u + PYTHONUNBUFFERED=1
#   - CT_LOG_FILE env -> FileHandler nativo Python UTF-8 (sem buffer)
#   - heartbeat por set via scanner v2.5.1
#
# Convencao: threshold e FRACAO (0.30 = 30 percent); Hub fee 6 percent paridade.

param(
    [string]$Stamp = '2026-05-16'
)

$env:PYTHONIOENCODING  = 'utf-8'
$env:PYTHONUNBUFFERED  = '1'

# CT_LOG_FILE: scanner adiciona FileHandler nativo logging em UTF-8 direto.
# Evita pipe PS / cmd /c redirect buffering issues quando rodado via
# Task Scheduler sem console parent. Definido apos $logFile abaixo.

$base = 'C:\Users\mathe\Meu Drive\OBSIDIAN\01 - Projetos\TCG & Exporta' + [char]0xE7 + [char]0xE3 + 'o\CardTrader Scanner'
$repo = $base
if (-not (Test-Path -LiteralPath $repo)) {
    Write-Error "Repo path not found: $repo"
    exit 99
}

$py        = Join-Path $repo '.venv\Scripts\python.exe'
$rawOut    = Join-Path $repo "outputs\weekly_raw_$Stamp.xlsx"
$finalOut  = Join-Path $repo "outputs\weekly_$Stamp.xlsx"
$logFile   = Join-Path $repo "logs\weekly_local_$Stamp.log"
$codesFile = Join-Path $repo 'scripts\all_set_codes.txt'

if (-not (Test-Path -LiteralPath $codesFile)) {
    Write-Error "Codes file missing: $codesFile"
    exit 98
}

if (-not (Test-Path -LiteralPath $py)) {
    Write-Error "Python venv not found: $py"
    exit 97
}

# Scanner usa CT_LOG_FILE env var pra adicionar FileHandler nativo
$env:CT_LOG_FILE = $logFile

Set-Location $repo

# Le os 832 codes (uma linha space-separated) e splita em array
$rawCodes = (Get-Content -Raw -LiteralPath $codesFile).Trim()
$setCodes = $rawCodes -split '\s+' | Where-Object { $_ -ne '' }

# Header pro log (cria/sobrescreve)
$header = @(
    "=== Weekly LOCAL scan dispatch $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===",
    "REPO     = $repo",
    "PY       = $py",
    "RAW      = $rawOut",
    "FINAL    = $finalOut",
    "SET COUNT= $($setCodes.Count)",
    "PID_PS   = $PID",
    "STAMP    = $Stamp",
    "--- STEP 1: scanner full scope ($($setCodes.Count) sets) ---"
)
$header | Set-Content -LiteralPath $logFile -Encoding utf8

# Step 1: scanner com TODOS os codes via --sets
#
# Scanner adiciona FileHandler nativo (UTF-8) ao logging quando ve a env
# CT_LOG_FILE setada. NAO precisamos de redirect PS/cmd (que tinham
# problema de buffering quando rodado via Task Scheduler sem console).
#
# Invocacao: call operator `& $py @args` aceita arrays com espacos.
# Stdout do scanner vai pra console virtual da Task (descartado) — o que
# importa eh o FileHandler.
#
# v4 (2026-05-17 noite, pos-incident weekly 2026-05-17 sd-v crash silencioso):
#   stderr NAO eh mais descartado. Captura em arquivo separado pra evitar
#   o caso de o scanner morrer com traceback antes do FileHandler flushar.
#   Pre-fix: `2>&1 | Out-Null` swallowed qualquer ultima exception.
#   Pos-fix: `2> $stderrFile` preserva stderr puro em UTF-8 raw bytes.
$stderrFile = Join-Path $repo "logs\weekly_local_${Stamp}.stderr.log"
$scannerArgs = @(
    '-u',
    'cardtrader_scanner.py',
    '--threshold', '0.30',
    '--validate-top', '100',
    '--min-net-margin', '0.20',
    '--per-set-timeout', '8',
    '--hub-fee', '0.06',
    '--output', $rawOut,
    '--sets'
) + $setCodes

# Stderr -> arquivo dedicado; stdout descartado (heartbeat ja vai pro FileHandler).
& $py @scannerArgs 2> $stderrFile | Out-Null
$scannerExit = $LASTEXITCODE

# Anexa stderr ao log principal se nao vazio (pos-mortem)
if ((Test-Path -LiteralPath $stderrFile) -and (Get-Item -LiteralPath $stderrFile).Length -gt 0) {
    "--- STDERR (capturado) ---" | Add-Content -LiteralPath $logFile -Encoding utf8
    Get-Content -LiteralPath $stderrFile -Raw -Encoding utf8 | Add-Content -LiteralPath $logFile -Encoding utf8
    "--- FIM STDERR ---" | Add-Content -LiteralPath $logFile -Encoding utf8
}

"--- SCANNER exit=$scannerExit at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ---" | Add-Content -LiteralPath $logFile -Encoding utf8

if ($scannerExit -ne 0) {
    "SCANNER FAILED exit=$scannerExit" | Add-Content -LiteralPath $logFile -Encoding utf8
    exit $scannerExit
}

# Step 2: postprocess v2
"--- STEP 2: postprocess v2 ---" | Add-Content -LiteralPath $logFile -Encoding utf8

# Guard rail: -LiteralPath nao interpreta '[',']','*','?','&',espaco; vital
# pra paths "Meu Drive\OBSIDIAN\01 - Projetos\TCG & Exportação\...".
if (-not (Test-Path -LiteralPath $rawOut)) {
    "RAW XLSX nao encontrado em '$rawOut' - abortando postprocess" | Add-Content -LiteralPath $logFile -Encoding utf8
    exit 2
}

# Postprocess: invocacao via call operator `& $py @postArgs`.
#
# v3 fix (2026-05-17): redirect `1>`/`2>` em PS 5.1 escreve em UTF-16 LE por
# default e quebra paths com '[' como wildcard. Trocamos por captura via
# pipeline `*>&1` + Set-Content -LiteralPath -Encoding utf8 -Append, que:
#   1) preserva o stream UTF-8 do Python (stdout via PYTHONIOENCODING)
#   2) ignora wildcards no path do log (Add-Content -LiteralPath)
#   3) nao precisa de arquivos temp -> menos sites frageis
#
# Historico para evitar regressao:
#   - Start-Process -ArgumentList: quebra paths com espaco (commit eb3948f)
#   - cmd.exe /c '> log 2>&1': buffer stuck em Task Scheduler (commit ee99a8e)
#   - PS `1> $tmp 2> $tmp`: UTF-16 garbled + wildcard interpretation
#   - Call operator + *>&1 + Add-Content -LiteralPath: ATUAL (v3)
$postArgs = @(
    '-u',
    'cardtrader_postprocess.py',
    '--input',  $rawOut,
    '--output', $finalOut
)

# DEBUG: dump dos args antes da chamada (facilita pos-mortem se quebrar)
"DEBUG: postprocess args =" | Add-Content -LiteralPath $logFile -Encoding utf8
for ($i = 0; $i -lt $postArgs.Count; $i++) {
    "  argv[$i] = [$($postArgs[$i])]" | Add-Content -LiteralPath $logFile -Encoding utf8
}
"DEBUG: input  exists = $(Test-Path -LiteralPath $rawOut)" | Add-Content -LiteralPath $logFile -Encoding utf8
"DEBUG: output dir exists = $(Test-Path -LiteralPath (Split-Path -Parent $finalOut))" | Add-Content -LiteralPath $logFile -Encoding utf8

# Captura stdout+stderr unificados via pipeline PS, Set-Content escreve UTF-8.
# Note: `*>&1` redireciona todos os streams (1=stdout, 2=stderr, 3=warning,
# 4=verbose, 5=debug, 6=information) pro success stream antes do pipe.
$postOutput = & $py @postArgs *>&1
$postExit   = $LASTEXITCODE

if ($postOutput) {
    $postOutput | ForEach-Object { $_.ToString() } | Add-Content -LiteralPath $logFile -Encoding utf8
}

if ($postExit -ne 0) {
    "POSTPROCESS FAILED exit=$postExit" | Add-Content -LiteralPath $logFile -Encoding utf8
    "DEBUG (pos-mortem) args repassados:" | Add-Content -LiteralPath $logFile -Encoding utf8
    for ($i = 0; $i -lt $postArgs.Count; $i++) {
        "  argv[$i] = [$($postArgs[$i])]" | Add-Content -LiteralPath $logFile -Encoding utf8
    }
}

"=== DONE $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') scanner=$scannerExit post=$postExit ===" | Add-Content -LiteralPath $logFile -Encoding utf8
