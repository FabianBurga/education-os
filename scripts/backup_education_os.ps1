param(
    [string]$Database = "education_os",
    [string]$HostName = "localhost",
    [int]$Port = 5432,
    [string]$Username = "education_owner",
    [string]$OutputDirectory = ".\backups"
)

$ErrorActionPreference = "Stop"

function Find-PgTool($Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidate = Get-ChildItem "C:\Program Files\PostgreSQL" -Recurse `
        -Filter "$Name.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1

    if ($candidate) { return $candidate.FullName }
    return $null
}

$pgDump = Find-PgTool "pg_dump"
if (!$pgDump) {
    throw "pg_dump no encontrado."
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$file = Join-Path $OutputDirectory "education_os_$stamp.dump"

& $pgDump -h $HostName -p $Port -U $Username -d $Database -Fc -f $file
if ($LASTEXITCODE -ne 0) {
    throw "pg_dump fallo con codigo $LASTEXITCODE"
}

$hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $([IO.Path]::GetFileName($file))" |
    Set-Content -LiteralPath "$file.sha256" -Encoding ascii

Write-Host "Backup: $file" -ForegroundColor Green
Write-Host "SHA256: $hash"
