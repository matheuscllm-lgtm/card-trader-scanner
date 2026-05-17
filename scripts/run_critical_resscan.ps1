# run_critical_resscan.ps1 - one-shot re-scan dos 4 sets críticos skipados no weekly 2026-05-16
#
# Sets: asc cec hif evo (Ascended Heroes, Cosmic Eclipse, Hidden Fates, Evolutions)
# Timeout: 20min por set (vs 8min default do weekly)
# Skip-list: --ignore-skip-list pra retentar mesmo com entry persistida em scanner_skip_list.json
#
# Output: outputs/critical_resscan_$stamp.xlsx (raw) -> outputs/critical_$stamp.xlsx (final)
# Log: logs/critical_resscan_$stamp.log
#
# v2 (2026-05-17): mesmos fixes definitivos de quoting/path do run_weekly_local v3
# (-LiteralPath em Test-Path/Add-Content, *>&1 + Set-Content -LiteralPath em vez de
# `1> $tmp 2> $tmp`, DEBUG dump dos args pra postprocess, paramz $Stamp/$Sets/$Timeout)

param(
    [string]$Stamp   = '2026-05-17',
    [string[]]$Sets  = @('asc','cec','hif','evo'),
    [int]$TimeoutMin = 20
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
$rawOut    = Join-Path $repo "outputs\critical_resscan_$Stamp.xlsx"
$finalOut  = Join-Path $repo "outputs\critical_$Stamp.xlsx"
$logFile   = Join-Path $repo "logs\critical_resscan_$Stamp.log"

if (-not (Test-Path -LiteralPath $py)) {
    Write-Error "Python venv not found: $py"
    exit 97
}

$env:CT_LOG_FILE = $logFile

Set-Location -LiteralPath $repo

$header = @(
    "=== CRITICAL re-scan dispatch $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===",
    "REPO     = $repo",
    "PY       = $py",
    "RAW      = $rawOut",
    "FINAL    = $finalOut",
    "SETS     = $($Sets -join ' ')",
    "TIMEOUT  = $($TimeoutMin)min/set",
    "PID_PS   = $PID",
    "STAMP    = $Stamp",
    "--- STEP 1: scanner critical scope ---"
)
$header | Set-Content -LiteralPath $logFile -Encoding utf8

$scannerArgs = @(
    '-u',
    'cardtrader_scanner.py',
    '--sets'
) + $Sets + @(
    '--threshold', '0.30',
    '--validate-top', '100',
    '--min-net-margin', '0.20',
    '--per-set-timeout', "$TimeoutMin",
    '--hub-fee', '0.06',
    '--ignore-skip-list',
    '--output', $rawOut
)

& $py @scannerArgs 2>&1 | Out-Null
$scannerExit = $LASTEXITCODE

"--- SCANNER exit=$scannerExit at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ---" | Add-Content -LiteralPath $logFile -Encoding utf8

if ($scannerExit -ne 0) {
    "SCANNER FAILED exit=$scannerExit" | Add-Content -LiteralPath $logFile -Encoding utf8
    exit $scannerExit
}

# Step 2: postprocess v2
"--- STEP 2: postprocess v2 ---" | Add-Content -LiteralPath $logFile -Encoding utf8

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

# DEBUG dump (mesmo padrao do run_weekly_local v3)
"DEBUG: postprocess args =" | Add-Content -LiteralPath $logFile -Encoding utf8
for ($i = 0; $i -lt $postArgs.Count; $i++) {
    "  argv[$i] = [$($postArgs[$i])]" | Add-Content -LiteralPath $logFile -Encoding utf8
}
"DEBUG: input  exists = $(Test-Path -LiteralPath $rawOut)" | Add-Content -LiteralPath $logFile -Encoding utf8
"DEBUG: output dir exists = $(Test-Path -LiteralPath (Split-Path -Parent $finalOut))" | Add-Content -LiteralPath $logFile -Encoding utf8

# Captura via *>&1 + Add-Content -LiteralPath (UTF-8 puro, sem wildcard interp)
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
