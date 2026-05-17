# test_postprocess_quoting.ps1 — teste end-to-end isolado do STEP 2 do wrapper.
# Replica fielmente o bloco postprocess do run_weekly_local v3 contra um XLSX
# raw existente. NAO dispara o scanner — apenas valida que paths com espaco/
# acento/& nao quebram o postprocess invocation.
#
# Uso: powershell -NoProfile -ExecutionPolicy Bypass -File test_postprocess_quoting.ps1

$env:PYTHONIOENCODING  = 'utf-8'
$env:PYTHONUNBUFFERED  = '1'

$base = 'C:\Users\mathe\Meu Drive\OBSIDIAN\01 - Projetos\TCG & Exporta' + [char]0xE7 + [char]0xE3 + 'o\CardTrader Scanner'
$repo = $base

$py        = Join-Path $repo '.venv\Scripts\python.exe'
$rawOut    = Join-Path $repo 'outputs\weekly_raw_2026-05-16.xlsx'
$finalOut  = Join-Path $repo 'outputs\weekly_2026-05-16.test_wrapper.xlsx'
$logFile   = Join-Path $repo 'logs\test_postprocess_quoting.log'

# Pre-flight
foreach ($p in @($py, $rawOut)) {
    if (-not (Test-Path -LiteralPath $p)) {
        Write-Error "Missing path: $p"
        exit 99
    }
}

@(
    "=== test_postprocess_quoting $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===",
    "REPO  = $repo",
    "PY    = $py",
    "RAW   = $rawOut",
    "FINAL = $finalOut"
) | Set-Content -LiteralPath $logFile -Encoding utf8

Set-Location -LiteralPath $repo

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

"=== DONE exit=$postExit ===" | Add-Content -LiteralPath $logFile -Encoding utf8

Write-Host "exit=$postExit"
Write-Host "log=$logFile"
Write-Host "out=$finalOut"
exit $postExit
