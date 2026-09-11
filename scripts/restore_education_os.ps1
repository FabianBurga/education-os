param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile,

    [Parameter(Mandatory=$true)]
    [string]$TargetDatabase,

    [string]$HostName = "localhost",
    [int]$Port = 5432,
    [string]$Username = "education_owner",

    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"

if (!$ConfirmRestore) {
    throw "Restore bloqueado. Repite con -ConfirmRestore."
}

if (!(Test-Path -LiteralPath $BackupFile)) {
    throw "Backup no encontrado: $BackupFile"
}

$cmd = Get-Command pg_restore -ErrorAction SilentlyContinue
$pgRestore = if ($cmd) { $cmd.Source } else { $null }

if (!$pgRestore) {
    $candidate = Get-ChildItem "C:\Program Files\PostgreSQL" -Recurse `
        -Filter "pg_restore.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($candidate) { $pgRestore = $candidate.FullName }
}

if (!$pgRestore) { throw "pg_restore no encontrado." }

Write-Host "RESTORE TARGET: $TargetDatabase" -ForegroundColor Yellow
& $pgRestore -h $HostName -p $Port -U $Username -d $TargetDatabase `
    --clean --if-exists $BackupFile

if ($LASTEXITCODE -ne 0) {
    throw "pg_restore fallo con codigo $LASTEXITCODE"
}

Write-Host "Restore completed: $TargetDatabase" -ForegroundColor Green
