# launch_weekly_task.ps1 — dispara run_weekly_local.ps1 via Windows Task
# Scheduler ONE-SHOT.
#
# Por que Task Scheduler em vez de Start-Process?
#   - Start-Process com -WindowStyle Hidden ainda eh CHILD do PowerShell parent.
#     Se a sessao Bash do Claude Code que invocou esse launcher terminar (e
#     ela termina ao fim de cada turno!), Windows pode propagar SIGTERM ao
#     processo filho.
#   - Task Scheduler cria processo TOTALMENTE detached, gerenciado pelo
#     Windows Service Host. Sobrevive a logoff, terminal close, etc.
#
# Uso:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File launch_weekly_task.ps1

$ErrorActionPreference = 'Stop'

$ps1Path  = Join-Path $PSScriptRoot 'run_weekly_local.ps1'
$taskName = 'CT_Weekly_OneShot_' + (Get-Date -Format 'yyyyMMddHHmmss')

# Trigger: 30 segundos a partir de agora
$startAt = (Get-Date).AddSeconds(30)

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ps1Path`""

$trigger = New-ScheduledTaskTrigger -Once -At $startAt

# Settings: limite alto pra nao matar scan longo
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 24) `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

# Roda como usuario interativo (necessario pra usar Google Drive mount)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal

Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null

Write-Host "TASK_REGISTERED=$taskName"
Write-Host "START_AT=$($startAt.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "PS1=$ps1Path"
Write-Host ""
Write-Host "Auto-cleanup: a task se autodestroi 25h apos start (pra nao acumular)."

# Agenda cleanup da task 25h depois (one-shot real)
$cleanupAt = $startAt.AddHours(25)
$cleanupCmd = "Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
$cleanupAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -Command `"$cleanupCmd`""
$cleanupTrigger = New-ScheduledTaskTrigger -Once -At $cleanupAt
$cleanupName = "${taskName}_cleanup"
Register-ScheduledTask -TaskName $cleanupName -Action $cleanupAction -Trigger $cleanupTrigger -Principal $principal -Force | Out-Null
Write-Host "CLEANUP_TASK=$cleanupName at $($cleanupAt.ToString('yyyy-MM-dd HH:mm:ss'))"
