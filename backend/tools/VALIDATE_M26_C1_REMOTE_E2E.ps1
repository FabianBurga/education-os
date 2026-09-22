$ErrorActionPreference = "Stop"

$BaseUrl = "https://education-os-investor-demo.onrender.com"
$Session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$Code = $null
$CodeSecure = $null
$CodeBstr = [IntPtr]::Zero

function Invoke-JsonRequest {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][int]$ExpectedStatus,
        [object]$Body = $null,
        [switch]$SameOrigin
    )

    $request = @{
        Uri                = "$BaseUrl$Path"
        Method             = $Method
        WebSession         = $Session
        UseBasicParsing    = $true
        MaximumRedirection = 0
    }

    if ($SameOrigin) {
        $request.Headers = @{ Origin = $BaseUrl }
    }

    if ($null -ne $Body) {
        $request.ContentType = "application/json"
        $request.Body = $Body | ConvertTo-Json -Compress
    }

    try {
        $response = Invoke-WebRequest @request
    }
    catch {
        throw "HTTP request failed: $Method $Path"
    }

    if ($response.StatusCode -ne $ExpectedStatus) {
        throw "Unexpected HTTP status: $Method $Path"
    }

    try {
        return $response.Content | ConvertFrom-Json
    }
    catch {
        throw "Invalid JSON response: $Method $Path"
    }
}

try {
    $live = Invoke-WebRequest `
        -Uri "$BaseUrl/health/live" `
        -Method Get `
        -UseBasicParsing `
        -MaximumRedirection 0

    if ($live.StatusCode -ne 200) {
        throw "health/live failed"
    }
    Write-Host "M26_C1_REMOTE_E2E"
    Write-Host "health_live: PASS"

    $ready = Invoke-WebRequest `
        -Uri "$BaseUrl/health/ready" `
        -Method Get `
        -UseBasicParsing `
        -MaximumRedirection 0

    if ($ready.StatusCode -ne 200) {
        throw "health/ready failed"
    }
    Write-Host "health_ready: PASS"

    $CodeSecure = Read-Host "EDUCATION_OS_DEMO_ACCESS_CODE" -AsSecureString
    $CodeBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($CodeSecure)
    try {
        $Code = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($CodeBstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($CodeBstr)
        $CodeBstr = [IntPtr]::Zero
    }

    $entrance = Invoke-JsonRequest `
        -Method Post `
        -Path "/api/demo/entrance" `
        -ExpectedStatus 200 `
        -Body @{ code = $Code } `
        -SameOrigin

    if ($entrance.entrance -ne $true) {
        throw "Demo entrance was not accepted"
    }
    Write-Host "demo_entrance: PASS"

    $sessionBefore = Invoke-JsonRequest `
        -Method Get `
        -Path "/api/demo/session" `
        -ExpectedStatus 200

    if ($sessionBefore.demo -ne $true -or $sessionBefore.entrance -ne $true) {
        throw "Demo session was not established"
    }

    $selected = Invoke-JsonRequest `
        -Method Post `
        -Path "/api/demo/session" `
        -ExpectedStatus 200 `
        -Body @{ alias = "RECTOR" } `
        -SameOrigin

    if ($selected.alias -ne "RECTOR") {
        throw "RECTOR selection failed"
    }

    $rectorSession = Invoke-JsonRequest `
        -Method Get `
        -Path "/api/demo/session" `
        -ExpectedStatus 200

    if ($rectorSession.entrance -ne $true -or $rectorSession.alias -ne "RECTOR") {
        throw "RECTOR session verification failed"
    }
    Write-Host "rector_session: PASS"

    $bootstrap = Invoke-JsonRequest `
        -Method Get `
        -Path "/api/v1/ui/bootstrap" `
        -ExpectedStatus 200

    if ($null -eq $bootstrap.tenant -or
        $null -eq $bootstrap.user -or
        $null -eq $bootstrap.roles -or
        $null -eq $bootstrap.permissions) {
        throw "UI bootstrap is incomplete"
    }

    foreach ($permission in @("agents.use", "intelligence.read", "agents.view")) {
        if ($bootstrap.permissions -notcontains $permission) {
            throw "Required permission missing from UI bootstrap"
        }
    }
    Write-Host "ui_bootstrap: PASS"

    $run = Invoke-JsonRequest `
        -Method Post `
        -Path "/api/v1/agents/mentor_institution_briefing/runs" `
        -ExpectedStatus 201 `
        -Body @{ briefing_focus = "OVERVIEW" } `
        -SameOrigin

    if ($run.status -ne "COMPLETED") {
        throw "Mentor run did not complete"
    }
    if ($run.agent_key -ne "mentor_institution_briefing") {
        throw "Unexpected Mentor agent"
    }
    if ($null -eq $run.output) {
        throw "Mentor output is missing"
    }
    if ($run.output.briefing_focus -ne "OVERVIEW") {
        throw "Mentor briefing focus mismatch"
    }
    if ([string]::IsNullOrWhiteSpace([string]$run.output.summary)) {
        throw "Mentor summary is empty"
    }
    if ($null -eq $run.output.key_findings -or @($run.output.key_findings).Count -lt 1) {
        throw "Mentor key findings are missing"
    }
    if ($null -eq $run.output.evidence_refs -or @($run.output.evidence_refs).Count -lt 1) {
        throw "Mentor evidence references are missing"
    }
    if ([string]$run.output.snapshot_date -notmatch "^\d{4}-\d{2}-\d{2}$") {
        throw "Mentor snapshot date is invalid"
    }
    if ([string]$run.output.freshness -notmatch "^(CURRENT|STALE_\d+_DAYS)$") {
        throw "Mentor freshness is invalid"
    }
    if ([string]$run.output.explanation_mode -notin @("DETERMINISTIC_FALLBACK", "FAKE_PROVIDER")) {
        throw "Mentor explanation mode is invalid"
    }

    if ([string]::IsNullOrWhiteSpace([string]$run.id)) {
        throw "Mentor run identifier is missing"
    }

    $persisted = Invoke-JsonRequest `
        -Method Get `
        -Path "/api/v1/agents/runs/$($run.id)" `
        -ExpectedStatus 200

    if ($persisted.id -ne $run.id -or
        $persisted.status -ne "COMPLETED" -or
        $persisted.agent_key -ne "mentor_institution_briefing") {
        throw "Persisted Mentor run verification failed"
    }

    Write-Host "mentor_overview: PASS"
    Write-Host "database_backed_response: PASS"
    Write-Host "M26_C1_REMOTE_E2E: PASS"
}
catch {
    Write-Host "M26_C1_REMOTE_E2E: HOLD"
    exit 1
}
finally {
    $Code = $null
    $CodeSecure = $null
    if ($CodeBstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($CodeBstr)
    }
}
