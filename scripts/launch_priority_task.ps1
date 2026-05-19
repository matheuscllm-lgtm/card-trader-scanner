# launch_priority_task.ps1 — dispatch run_priority_scan.ps1 via Task Scheduler.
#
# Por que Task Scheduler em vez de Start-Process?
#   Sessao Bash do Claude Code termina ao fim de cada turno -> processos
#   child gerados via Start-Process podem ser SIGTERM'd. Task Scheduler cria
#   processo detached gerenciado pelo Windows Service Host, sobrevive logoff.
#
# Espelha launch_weekly_2026-05-19.ps1 + launch_weekly_task.ps1 (timeout 48h
# default, cleanup task agendado 49h depois, principal Interactive Limited).
#
# Uso:
#   .\scripts\launch_priority_task.ps1 -Stamp test1
#   .\scripts\launch_priority_task.ps1 -Stamp big_run -TimeoutMin 20 -Threshold 0.25
#   .\scripts\launch_priority_task.ps1 -Sets pupr -Stamp smoke_pupr  # override 1 set

param(
    [string]$Stamp = ('priority_' + (Get-Date -Format 'yyyy-MM-dd')),
    [int]$TimeoutMin = 15,
    [double]$Threshold = 0.30,
    [double]$MinNet = 0.20,
    [string[]]$Sets = $null,
    [int]$TaskTimeoutHours = 48
)

$ErrorActionPreference = 'Stop'

$ps1Path  = Join-Path $PSScriptRoot 'run_priority_scan.ps1'
$taskName = "CT_Priority_OneShot_$Stamp"

if (-not (Test-Path -LiteralPath $ps1Path)) {
    Write-Error "Priority scan script not found: $ps1Path"
    exit 99
}

# Monta o argumento da PS1 wrapper — operador parametros viram flags do .ps1
$wrapperArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$ps1Path`" " +
               "-Stamp `"$Stamp`" -TimeoutMin $TimeoutMin " +
               "-Threshold $Threshold -MinNet $MinNet"

if ($Sets -and $Sets.Count -gt 0) {
    # -Sets aceita string[] no script alvo. Passar via Task Scheduler exige
    # listar item-a-item (PowerShell parser na invocacao reconstroi array).
    $setsArg = ($Sets | ForEach-Object { '"' + $_ + '"' }) -join ','
    $wrapperArgs += " -Sets $setsArg"
}

# Trigger: 30 segundos a partir de agora
$startAt = (Get-Date).AddSeconds(30)

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument $wrapperArgs

$trigger = New-ScheduledTaskTrigger -Once -At $startAt

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours $TaskTimeoutHours) `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal

try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
} catch { }

Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null

Write-Host "TASK_REGISTERED=$taskName"
Write-Host "START_AT=$($startAt.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "PS1=$ps1Path"
Write-Host "WRAPPER_ARGS=$wrapperArgs"
Write-Host "TIMEOUT=${TaskTimeoutHours}h"

# Cleanup auto $TaskTimeoutHours+1 depois (one-shot real)
$cleanupAt = $startAt.AddHours($TaskTimeoutHours + 1)
$cleanupCmd = "Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
$cleanupAction = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -Command `"$cleanupCmd`""
$cleanupTrigger = New-ScheduledTaskTrigger -Once -At $cleanupAt
$cleanupName = "${taskName}_cleanup"
try {
    Unregister-ScheduledTask -TaskName $cleanupName -Confirm:$false -ErrorAction SilentlyContinue
} catch { }
Register-ScheduledTask `
    -TaskName $cleanupName `
    -Action $cleanupAction `
    -Trigger $cleanupTrigger `
    -Principal $principal `
    -Force | Out-Null
Write-Host "CLEANUP_TASK=$cleanupName at $($cleanupAt.ToString('yyyy-MM-dd HH:mm:ss'))"
