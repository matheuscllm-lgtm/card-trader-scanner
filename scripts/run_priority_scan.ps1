# run_priority_scan.ps1 — priority-ordered weekly CT scan + postprocess v2
#
# Diferenca vs run_weekly_local.ps1:
#   Em vez de processar 832 sets em ordem alfabetica do all_set_codes.txt,
#   prioriza TIER 1 (chase moderno SV/ME), TIER 2 (chase vintage), e so depois
#   varre o resto (TIER 3). Permite operador rodar `peek_deals.py` durante a
#   janela e ja ver oportunidades reais nas primeiras horas — instead of esperar
#   varredura completa.
#
# Mantem infra do run_weekly_local.ps1 v3+v4:
#   - Test-Path -LiteralPath (Google Drive vault path com acento/&/espaco)
#   - PYTHONIOENCODING=utf-8 + python -u (CT_LOG_FILE FileHandler nativo)
#   - stderr capturado em arquivo separado (pos-crash forense)
#   - postprocess via call operator + *>&1 + Add-Content (sem `1>` UTF-16 trap)
#   - checkpoint-every 10 default (crash recovery via .checkpoint.jsonl sidecar)
#
# Uso:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass `
#     -File scripts\run_priority_scan.ps1 -Stamp priority_2026-05-19
#
# Override completo de lista (smoke / scoped):
#   .\scripts\run_priority_scan.ps1 -Sets pupr -Stamp smoke_pupr -TimeoutMin 8
#
# Convencao: threshold e FRACAO (0.30 = 30 percent); Hub fee 6 percent paridade.

param(
    [string]$Stamp = ('priority_' + (Get-Date -Format 'yyyy-MM-dd')),
    [int]$TimeoutMin = 15,
    [double]$Threshold = 0.30,
    [double]$MinNet = 0.20,
    [string[]]$Sets = $null
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
$rawOut    = Join-Path $repo "outputs\priority_raw_$Stamp.xlsx"
$finalOut  = Join-Path $repo "outputs\priority_$Stamp.xlsx"
$logFile   = Join-Path $repo "logs\priority_$Stamp.log"
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

# -------------------------------------------------------------------
# Lista de sets: override via -Sets OU construcao Tier 1 -> 2 -> 3
# -------------------------------------------------------------------
if ($Sets -and $Sets.Count -gt 0) {
    $setCodes = $Sets
    $tierMode = 'OVERRIDE'
} else {
    # Tier 1 — chase moderno SV / Mega Evolution (alta prob deals)
    $tier1 = @(
        'sfa','asc','jtg','dri','blk','wht','ssp','paf','tef','twm','par','sv151'
    )

    # Tier 2 — chase vintage / sets ja maturados com deals confiaveis
    $tier2 = @(
        'pupr','crz','lor','obf','pal','ssh','mew'
    )

    # Tier 3 — todo o resto do all_set_codes.txt, excluindo Tier 1+2
    $rawCodes = (Get-Content -Raw -LiteralPath $codesFile).Trim()
    $allCodes = $rawCodes -split '\s+' | Where-Object { $_ -ne '' }

    $priorSet = New-Object System.Collections.Generic.HashSet[string]
    foreach ($c in $tier1) { [void]$priorSet.Add($c) }
    foreach ($c in $tier2) { [void]$priorSet.Add($c) }

    $tier3 = $allCodes | Where-Object { -not $priorSet.Contains($_) }

    # Compoe ordem final, sem duplicatas (HashSet ja garante via priorSet,
    # mas reforcamos pra defesa em profundidade caso Tier1/Tier2 colidam).
    $seen     = New-Object System.Collections.Generic.HashSet[string]
    $setCodes = @()
    foreach ($c in ($tier1 + $tier2 + $tier3)) {
        if ($seen.Add($c)) { $setCodes += $c }
    }
    $tierMode = "T1=$($tier1.Count) T2=$($tier2.Count) T3=$($tier3.Count)"
}

# -------------------------------------------------------------------
# Header do log
# -------------------------------------------------------------------
$header = @(
    "=== Priority LOCAL scan dispatch $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===",
    "REPO      = $repo",
    "PY        = $py",
    "RAW       = $rawOut",
    "FINAL     = $finalOut",
    "SET COUNT = $($setCodes.Count)",
    "TIER MODE = $tierMode",
    "TIMEOUT   = ${TimeoutMin}min/set",
    "THRESHOLD = $Threshold (fracao)",
    "MIN NET   = $MinNet (fracao)",
    "PID_PS    = $PID",
    "STAMP     = $Stamp",
    "--- STEP 1: scanner priority-ordered ($($setCodes.Count) sets) ---"
)
$header | Set-Content -LiteralPath $logFile -Encoding utf8

# Stderr -> arquivo dedicado; stdout descartado (FileHandler ja escreve log)
$stderrFile = Join-Path $repo "logs\priority_${Stamp}.stderr.log"
$scannerArgs = @(
    '-u',
    'cardtrader_scanner.py',
    '--threshold', "$Threshold",
    '--validate-top', '100',
    '--min-net-margin', "$MinNet",
    '--per-set-timeout', "$TimeoutMin",
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

# -------------------------------------------------------------------
# Step 2: postprocess v2 (paridade run_weekly_local.ps1 v3)
# -------------------------------------------------------------------
# Lesson learned smoke 2026-05-19: postprocess herda env CT_LOG_FILE e
# abre o mesmo log em modo append, gerando race com o Add-Content do PS.
# Desetar antes do postprocess elimina conflito (postprocess so usa stdout).
Remove-Item Env:CT_LOG_FILE -ErrorAction SilentlyContinue

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
