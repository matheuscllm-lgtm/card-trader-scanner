# launch_weekly_2026-05-19.ps1 — dispatch one-shot via Task Scheduler.
#
# Aponta pra scripts/run_weekly_2026-05-19.ps1 (stack v2.9 + 31 new aliases
# + per-set-timeout 15min). 48h ExecutionTimeLimit conforme operador.

$ErrorActionPreference = 'Stop'

$ps1Path  = Join-Path $PSScriptRoot 'run_weekly_2026-05-19.ps1'
$taskName = 'CT_Weekly_OneShot_2026-05-19'

if (-not (Test-Path -LiteralPath $ps1Path)) {
    Write-Error "Weekly script not found: $ps1Path"
    exit 99
}

# Trigger: 30 segundos a partir de agora
$startAt = (Get-Date).AddSeconds(30)

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ps1Path`""

$trigger = New-ScheduledTaskTrigger -Once -At $startAt

# 48h cap (operador autorizou)
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 48) `
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

# Remove tasks antigas com mesmo nome (idempotente)
try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
} catch { }

Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null

Write-Host "TASK_REGISTERED=$taskName"
Write-Host "START_AT=$($startAt.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "PS1=$ps1Path"
Write-Host "TIMEOUT=48h"

# Cleanup auto 49h depois
$cleanupAt = $startAt.AddHours(49)
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
