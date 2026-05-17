# tail_weekly_log.ps1 — le o log weekly como UTF-16 (PS *>> default) e
# imprime decodificado. Pode rodar live enquanto scanner escreve.
#
# Uso:
#   .\tail_weekly_log.ps1                # ultimas 30 linhas
#   .\tail_weekly_log.ps1 -Lines 100     # ultimas 100
#   .\tail_weekly_log.ps1 -Follow        # tail -f equivalente
#   .\tail_weekly_log.ps1 -AliveOnly     # so linhas ALIVE/TIMEOUT/Erro
param(
    [int]$Lines = 30,
    [switch]$Follow,
    [switch]$AliveOnly
)

$base = 'C:\Users\mathe\Meu Drive\OBSIDIAN\01 - Projetos\TCG & Exporta' + [char]0xE7 + [char]0xE3 + 'o\CardTrader Scanner'
$logPath = Join-Path $base 'logs\weekly_local_2026-05-16.log'

function Read-LogDecoded {
    param([string]$Path)
    # Copy primeiro pra evitar file-lock conflict com scanner ativo
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        Copy-Item -Path $Path -Destination $tmp -Force
        $bytes = [System.IO.File]::ReadAllBytes($tmp)
        # Detecta: se primeiros bytes sao "===" ASCII (header), eh misto.
        # Se forem FF FE (BOM UTF-16) ou comeca com null byte alternado,
        # tem fragmento UTF-16. Faz best-effort decode UTF-16 + cleanup.
        $content = [System.Text.Encoding]::Unicode.GetString($bytes)
        # Remove caracteres nulos sobrantes
        $content = $content -replace "`0", ""
        return $content
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}

function Show-Tail {
    $content = Read-LogDecoded -Path $logPath
    $allLines = $content -split "`r?`n" | Where-Object { $_ -match '\S' }
    if ($AliveOnly) {
        $allLines | Select-String -Pattern 'ALIVE|TIMEOUT|Erro|RESUMO|salva|DONE|exit=' | ForEach-Object { Write-Host $_.Line }
    } else {
        $tail = if ($allLines.Count -gt $Lines) { $allLines[-$Lines..-1] } else { $allLines }
        $tail | ForEach-Object { Write-Host $_ }
    }
}

if ($Follow) {
    $lastLen = 0
    while ($true) {
        $info = Get-Item $logPath -ErrorAction SilentlyContinue
        if ($info -and $info.Length -ne $lastLen) {
            Clear-Host
            Write-Host "=== $logPath ($($info.Length) bytes, $(Get-Date -Format HH:mm:ss)) ==="
            Show-Tail
            $lastLen = $info.Length
        }
        Start-Sleep -Seconds 5
    }
} else {
    Show-Tail
}
