param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile
)

$ErrorActionPreference = "Stop"

$hashFile = "$BackupFile.sha256"
if (!(Test-Path -LiteralPath $BackupFile)) { throw "Backup no encontrado." }
if (!(Test-Path -LiteralPath $hashFile)) { throw "Archivo .sha256 no encontrado." }

$expected = ((Get-Content -LiteralPath $hashFile | Select-Object -First 1) -split "\s+")[0].ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $BackupFile -Algorithm SHA256).Hash.ToLowerInvariant()

if ($expected -ne $actual) { throw "SHA256 mismatch." }

Write-Host "Backup SHA256: OK" -ForegroundColor Green
