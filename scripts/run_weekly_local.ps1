# run_weekly_local.ps1 - dispara weekly full CT scan + postprocess v2
#
# v2 (2026-05-16 noite, pós-crash de Base Set):
#   - REMOVIDO Tee-Object: causava encoding UTF-16 garbled no log + buffer
#     overflow ao processar 20k+ listings de Base Set
#   - REMOVIDO $ErrorActionPreference='Stop': qualquer WriteError no pipeline
#     matava o scanner silenciosamente
#   - ADICIONADO python -u (unbuffered) pra streaming real no log
#   - stdout E stderr redirecionados pro mesmo arquivo via "2>&1 >> file"
#     direto no nível de processo (não pipeline PowerShell)
#   - Heartbeat por set agora vem do próprio scanner v2.5.1
#
# Convencao: threshold e FRACAO (0.30 = 30 percent); Hub fee 6 percent paridade.

$env:PYTHONIOENCODING  = 'utf-8'
$env:PYTHONUNBUFFERED  = '1'

$base = 'C:\Users\mathe\Meu Drive\OBSIDIAN\01 - Projetos\TCG & Exporta' + [char]0xE7 + [char]0xE3 + 'o\CardTrader Scanner'
$repo = $base
if (-not (Test-Path $repo)) {
    Write-Error "Repo path not found: $repo"
    exit 99
}

$py        = Join-Path $repo '.venv\Scripts\python.exe'
$stamp     = '2026-05-16'
$rawOut    = Join-Path $repo "outputs\weekly_raw_$stamp.xlsx"
$finalOut  = Join-Path $repo "outputs\weekly_$stamp.xlsx"
$logFile   = Join-Path $repo "logs\weekly_local_$stamp.log"
$codesFile = Join-Path $repo 'scripts\all_set_codes.txt'

if (-not (Test-Path $codesFile)) {
    Write-Error "Codes file missing: $codesFile"
    exit 98
}

Set-Location $repo

# Le os 832 codes (uma linha space-separated) e splita em array
$rawCodes = (Get-Content -Raw $codesFile).Trim()
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
    "--- STEP 1: scanner full scope ($($setCodes.Count) sets) ---"
)
$header | Out-File -FilePath $logFile -Encoding utf8

# Step 1: scanner com TODOS os codes via --sets
#
# LOG ENCODING: PS redirect (*>>, Tee-Object, Out-File) converte stdout
# do Python pra UTF-16 (PS interno) e gera log garbled. Solucao: invocar
# via cmd.exe que NAO faz Unicode conversion, redirect file direto:
#   cmd /c "...python.exe ... > log 2>&1"
# Como o Python ja reconfigura stdout pra UTF-8 (cardtrader_scanner.py
# linha 112), o file fica UTF-8 limpo.
#
# Quoting: cmd /c precisa de aspas duplas DENTRO de outer aspas duplas.
# Solucao: monta string com cmd-style quoting (cada arg com espaco
# embrulhado em \"...\").

function Quote-CmdArg([string]$a) {
    if ($a -match '\s|"') { return '"' + ($a -replace '"', '""') + '"' }
    return $a
}

$scannerArgsArr = @(
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

$pyQuoted = Quote-CmdArg $py
$logQuoted = Quote-CmdArg $logFile
$argsJoined = ($scannerArgsArr | ForEach-Object { Quote-CmdArg $_ }) -join ' '

# >> append, 2>&1 merge stderr->stdout. cmd /c roda em subprocess separado.
$cmdLine = "$pyQuoted $argsJoined >> $logQuoted 2>&1"
"--- cmd: $cmdLine" | Out-File -FilePath $logFile -Append -Encoding utf8

& cmd.exe /c $cmdLine
$scannerExit = $LASTEXITCODE

"--- SCANNER exit=$scannerExit ---" | Out-File -FilePath $logFile -Append -Encoding utf8

if ($scannerExit -ne 0) {
    "SCANNER FAILED exit=$scannerExit" | Out-File -FilePath $logFile -Append -Encoding utf8
    exit $scannerExit
}

# Step 2: postprocess v2
"--- STEP 2: postprocess v2 ---" | Out-File -FilePath $logFile -Append -Encoding utf8

if (-not (Test-Path $rawOut)) {
    "RAW XLSX nao encontrado em $rawOut - abortando postprocess" | Out-File -FilePath $logFile -Append -Encoding utf8
    exit 2
}

$postArgsArr = @(
    '-u',
    'cardtrader_postprocess.py',
    '--input',  $rawOut,
    '--output', $finalOut
)
$postArgsJoined = ($postArgsArr | ForEach-Object { Quote-CmdArg $_ }) -join ' '
$postCmdLine = "$pyQuoted $postArgsJoined >> $logQuoted 2>&1"
"--- cmd: $postCmdLine" | Out-File -FilePath $logFile -Append -Encoding utf8

& cmd.exe /c $postCmdLine
$postExit = $LASTEXITCODE

"=== DONE $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') scanner=$scannerExit post=$postExit ===" | Out-File -FilePath $logFile -Append -Encoding utf8
