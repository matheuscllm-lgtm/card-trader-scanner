# launch_weekly.ps1 — dispara run_weekly_local.ps1 como processo detached oculto
#
# v2 (2026-05-17): Start-Process -ArgumentList faz join naive com espaco e
# quebra paths com espaco / & / acento. Trocamos por single-string com path
# escapado via aspas duplas — tecnica que o Windows CreateProcess respeita.
#
# Para uso production prefira launch_weekly_task.ps1 (Task Scheduler detached
# real). Esse aqui eh usado em dev/smoke ad-hoc.

$ps1 = Join-Path $PSScriptRoot 'run_weekly_local.ps1'
if (-not (Test-Path -LiteralPath $ps1)) {
    Write-Error "run_weekly_local.ps1 not found at: $ps1"
    exit 99
}

# Aspas duplas escapadas via backtick. CreateProcess interpreta `"$ps1`" como
# single argument mesmo quando $ps1 contem espacos / & / acento.
$argString = "-NoProfile -ExecutionPolicy Bypass -File `"$ps1`""

$proc = Start-Process -FilePath 'powershell.exe' `
    -ArgumentList $argString `
    -WindowStyle Hidden `
    -PassThru
Start-Sleep -Seconds 2
Write-Host "LAUNCHED_PID=$($proc.Id)"
Write-Host "HasExited=$($proc.HasExited)"
Write-Host "StartTime=$($proc.StartTime)"
Write-Host "TARGET_PS1=$ps1"
