# run_weekly_2026-05-19.ps1 - dispara weekly full CT scan + postprocess v2.3
#
# Baseado em scripts/run_weekly_local.ps1 v4 (path-quoting hardening +
# stderr capture + UTF-8). Diferenca: --per-set-timeout 15 (era 8) e
# --checkpoint-every 10 (default v2.6, redundante mas explicito).
#
# Stack v2.9 ativo:
#   - Scanner Layer 1 + 1.5 (strict set + alias expansion SWSH/SV/ME 78e4495)
#   - Scanner Layer 2 variant priority (07d42b1)
#   - Scanner Layer 4 foil-aware variant (07d42b1)
#   - Postprocess Layer 3 UNSUPPORTED_SETS forced REVISAR (943c660)
#   - Postprocess Layer 5 alpha-suffix REVISAR (2d3eb64)
#   - Link TCG passthrough (e1f66f3)
#
# Convencao: threshold e FRACAO (0.30 = 30 percent); Hub fee 6 percent.

param(
    [string]$Stamp = '2026-05-19'
)

$env:PYTHONIOENCODING  = 'utf-8'
$env:PYTHONUNBUFFERED  = '1'

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
$stderrFile= Join-Path $repo "logs\weekly_local_${Stamp}.stderr.log"
$codesFile = Join-Path $repo 'scripts\all_set_codes.txt'

if (-not (Test-Path -LiteralPath $codesFile)) {
    Write-Error "Codes file missing: $codesFile"
    exit 98
}

if (-not (Test-Path -LiteralPath $py)) {
    Write-Error "Python venv not found: $py"
    exit 97
}

$env:CT_LOG_FILE = $logFile

Set-Location $repo

$rawCodes = (Get-Content -Raw -LiteralPath $codesFile).Trim()
$setCodes = $rawCodes -split '\s+' | Where-Object { $_ -ne '' }

$header = @(
    "=== Weekly LOCAL scan dispatch $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===",
    "REPO     = $repo",
    "PY       = $py",
    "RAW      = $rawOut",
    "FINAL    = $finalOut",
    "STDERR   = $stderrFile",
    "SET COUNT= $($setCodes.Count)",
    "PID_PS   = $PID",
    "STAMP    = $Stamp",
    "STACK    = scanner v2.9 + postprocess v2.3 Layer 5",
    "PER_SET  = 15 min (matches last successful weekly v2.6)",
    "--- STEP 1: scanner full scope ($($setCodes.Count) sets) ---"
)
$header | Set-Content -LiteralPath $logFile -Encoding utf8

# Scanner args:
#   --threshold 0.30           (gross margin pre-validation)
#   --validate-top 100         (validate top 100 deals via per-blueprint)
#   --min-net-margin 0.20      (post-validation net margin floor)
#   --per-set-timeout 15       (15 min per-set; matches last good weekly)
#   --hub-fee 0.06             (paridade postprocess)
#   --checkpoint-every 10      (default v2.6, JSONL crash-safe)
$scannerArgs = @(
    '-u',
    'cardtrader_scanner.py',
    '--threshold', '0.30',
    '--validate-top', '100',
    '--min-net-margin', '0.20',
    '--per-set-timeout', '15',
    '--hub-fee', '0.06',
    '--checkpoint-every', '10',
    '--output', $rawOut,
    '--sets'
) + $setCodes

& $py @scannerArgs 2> $stderrFile | Out-Null
$scannerExit = $LASTEXITCODE

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

"--- STEP 2: postprocess v2.3 ---" | Add-Content -LiteralPath $logFile -Encoding utf8

if (-not (Test-Path -LiteralPath $rawOut)) {
    "RAW XLSX nao encontrado em '$rawOut' - abortando postprocess" | Add-Content -LiteralPath $logFile -Encoding utf8
    exit 2
}

$postArgs = @(
    '-u',
    'cardtrader_postprocess.py',
    '--input',  $rawOut,
    '--output', $finalOut
)

"DEBUG: postprocess args =" | Add-Content -LiteralPath $logFile -Encoding utf8
for ($i = 0; $i -lt $postArgs.Count; $i++) {
    "  argv[$i] = [$($postArgs[$i])]" | Add-Content -LiteralPath $logFile -Encoding utf8
}
"DEBUG: input  exists = $(Test-Path -LiteralPath $rawOut)" | Add-Content -LiteralPath $logFile -Encoding utf8
"DEBUG: output dir exists = $(Test-Path -LiteralPath (Split-Path -Parent $finalOut))" | Add-Content -LiteralPath $logFile -Encoding utf8

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
