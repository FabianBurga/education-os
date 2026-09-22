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

function Select-Rector {
    $selected = Invoke-JsonRequest `
        -Method Post `
        -Path "/api/demo/session" `
        -ExpectedStatus 200 `
        -Body @{ alias = "RECTOR" } `
        -SameOrigin

    if ($selected.alias -ne "RECTOR") {
        throw "RECTOR selection failed"
    }

    $status = Invoke-JsonRequest `
        -Method Get `
        -Path "/api/demo/session" `
        -ExpectedStatus 200

    if ($status.entrance -ne $true -or $status.alias -ne "RECTOR") {
        throw "RECTOR session verification failed"
    }
}

function Assert-ValidBriefing {
    param(
        [Parameter(Mandatory = $true)][object]$Run,
        [Parameter(Mandatory = $true)][string]$Focus
    )

    if ($Run.status -ne "COMPLETED" -or
        $Run.agent_key -ne "mentor_institution_briefing" -or
        $null -eq $Run.output) {
        throw "Mentor run envelope is invalid"
    }

    $output = $Run.output
    if ($output.agent_key -ne "mentor_institution_briefing" -or
        $output.briefing_focus -ne $Focus) {
        throw "Mentor output identity or focus is invalid"
    }

    if ([string]::IsNullOrWhiteSpace([string]$output.summary) -or
        ([string]$output.summary).Length -gt 1200) {
        throw "Mentor summary is invalid"
    }

    $findings = @($output.key_findings)
    if ($findings.Count -lt 1 -or $findings.Count -gt 8) {
        throw "Mentor findings count is invalid"
    }

    foreach ($finding in $findings) {
        if ([string]::IsNullOrWhiteSpace([string]$finding.text) -or
            ([string]$finding.text).Length -gt 700) {
            throw "Mentor finding text is invalid"
        }
        $findingRefs = @($finding.evidence_refs)
        if ($findingRefs.Count -ne 1 -or $findingRefs[0] -ne "ev_01") {
            throw "Mentor finding citation is invalid"
        }
    }

    $caveats = @($output.caveats)
    if ($caveats.Count -gt 8 -or
        ($caveats | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }).Count -lt 1) {
        throw "Mentor human-review caveat is missing"
    }

    if ([string]$output.snapshot_date -notmatch "^\d{4}-\d{2}-\d{2}$" -or
        [DateTime]::ParseExact([string]$output.snapshot_date, "yyyy-MM-dd", $null).Year -lt 2000) {
        throw "Mentor snapshot date is invalid"
    }

    if ([string]$output.freshness -notmatch "^(CURRENT|STALE_\d+_DAYS)$") {
        throw "Mentor freshness is invalid"
    }

    if ([string]$output.explanation_mode -notin @("DETERMINISTIC_FALLBACK", "FAKE_PROVIDER")) {
        throw "Mentor explanation mode is invalid"
    }

    if ([string]$output.evidence_manifest_sha256 -notmatch "^[0-9a-f]{64}$") {
        throw "Mentor evidence manifest hash is invalid"
    }

    $evidence = @($output.evidence_refs)
    if ($evidence.Count -ne 1) {
        throw "Mentor evidence reference count is invalid"
    }

    if ($evidence[0].source_module -ne "intelligence" -or
        $evidence[0].source_entity_type -ne "InstitutionIntelligenceDaily") {
        throw "Mentor evidence source is invalid"
    }

    if ([string]::IsNullOrWhiteSpace([string]$output.snapshot_id) -or
        [string]$evidence[0].source_entity_id -ne [string]$output.snapshot_id) {
        throw "Mentor snapshot lineage is invalid"
    }

    $serialized = $output | ConvertTo-Json -Depth 20 -Compress
    if ($serialized -match "Valentina") {
        throw "Student privacy boundary failed"
    }

    return $output
}

try {
    $live = Invoke-WebRequest -Uri "$BaseUrl/health/live" -Method Get -UseBasicParsing -MaximumRedirection 0
    if ($live.StatusCode -ne 200) { throw "health/live failed" }

    $ready = Invoke-WebRequest -Uri "$BaseUrl/health/ready" -Method Get -UseBasicParsing -MaximumRedirection 0
    if ($ready.StatusCode -ne 200) { throw "health/ready failed" }

    $shell = Invoke-WebRequest -Uri "$BaseUrl/app/" -Method Get -UseBasicParsing -MaximumRedirection 0
    if ($shell.StatusCode -ne 200 -or $shell.Content -notmatch "(?i)<html") {
        throw "Application shell failed"
    }

    $CodeSecure = Read-Host "EDUCATION_OS_DEMO_ACCESS_CODE" -AsSecureString
    $CodeBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($CodeSecure)
    try {
        $Code = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($CodeBstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($CodeBstr)
        $CodeBstr = [IntPtr]::Zero
    }

    $entrance = Invoke-JsonRequest -Method Post -Path "/api/demo/entrance" -ExpectedStatus 200 -Body @{ code = $Code } -SameOrigin
    if ($entrance.entrance -ne $true) { throw "Demo entrance failed" }

    Select-Rector
    $bootstrap = Invoke-JsonRequest -Method Get -Path "/api/v1/ui/bootstrap" -ExpectedStatus 200
    if ($null -eq $bootstrap.tenant -or $null -eq $bootstrap.user -or
        @($bootstrap.roles).Count -ne 1 -or $bootstrap.roles -notcontains "RECTOR") {
        throw "RECTOR bootstrap is invalid"
    }
    foreach ($permission in @("agents.use", "agents.view", "intelligence.read")) {
        if ($bootstrap.permissions -notcontains $permission) { throw "RECTOR permission missing" }
    }

    $focuses = @("OVERVIEW", "PRIORITIES", "FOLLOW_UPS")
    $outputs = @{}
    foreach ($focus in $focuses) {
        $run = Invoke-JsonRequest `
            -Method Post `
            -Path "/api/v1/agents/mentor_institution_briefing/runs" `
            -ExpectedStatus 201 `
            -Body @{ briefing_focus = $focus } `
            -SameOrigin

        if ([string]::IsNullOrWhiteSpace([string]$run.id)) { throw "Mentor run identifier missing" }
        $outputs[$focus] = Assert-ValidBriefing -Run $run -Focus $focus

        $readBack = Invoke-JsonRequest `
            -Method Get `
            -Path "/api/v1/agents/runs/$($run.id)" `
            -ExpectedStatus 200

        if ($readBack.id -ne $run.id -or
            $readBack.status -ne "COMPLETED" -or
            $readBack.agent_key -ne "mentor_institution_briefing") {
            throw "Mentor persistence read-back failed"
        }
    }

    $reference = $outputs["OVERVIEW"]
    foreach ($focus in $focuses) {
        if ([string]$outputs[$focus].snapshot_id -ne [string]$reference.snapshot_id -or
            [string]$outputs[$focus].snapshot_date -ne [string]$reference.snapshot_date -or
            [string]$outputs[$focus].evidence_refs[0].source_entity_id -ne [string]$reference.evidence_refs[0].source_entity_id) {
            throw "Mentor snapshot consistency failed"
        }
    }

    Write-Host "M26_C3_RECTOR_MENTOR_JOURNEY"
    Write-Host "health: PASS"
    Write-Host "app_shell: PASS"
    Write-Host "rector_session: PASS"
    Write-Host "rector_bootstrap: PASS"
    Write-Host "mentor_overview: PASS"
    Write-Host "mentor_priorities: PASS"
    Write-Host "mentor_followups: PASS"
    Write-Host "aggregate_evidence_contract: PASS"
    Write-Host "privacy_no_student_pii: PASS"
    Write-Host "human_review_contract: PASS"
    Write-Host "snapshot_consistency: PASS"
    Write-Host "mentor_persistence: PASS"
    Write-Host "M26_C3_RECTOR_MENTOR_JOURNEY: PASS"
}
catch {
    Write-Host "M26_C3_RECTOR_MENTOR_JOURNEY: HOLD"
    exit 1
}
finally {
    $Code = $null
    $CodeSecure = $null
    if ($CodeBstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($CodeBstr)
    }
}
