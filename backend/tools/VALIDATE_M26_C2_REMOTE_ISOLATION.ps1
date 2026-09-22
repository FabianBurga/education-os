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

function Get-ExpectedStatus {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        [object]$Body = $null,
        [switch]$SameOrigin
    )

    $request = @{
        Uri                = "$BaseUrl$Path"
        Method             = $Method
        WebSession         = $Session
        UseBasicParsing    = $true
        MaximumRedirection = 0
        ErrorAction         = "Stop"
    }

    if ($SameOrigin) {
        $request.Headers = @{ Origin = $BaseUrl }
    }

    if ($null -ne $Body) {
        $request.ContentType = "application/json"
        $request.Body = $Body | ConvertTo-Json -Compress
    }

    try {
        return [int](Invoke-WebRequest @request).StatusCode
    }
    catch {
        if ($null -ne $_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode.value__
        }
        throw "HTTP request failed: $Method $Path"
    }
}

function Select-DemoPersona {
    param([Parameter(Mandatory = $true)][string]$Alias)

    $selected = Invoke-JsonRequest `
        -Method Post `
        -Path "/api/demo/session" `
        -ExpectedStatus 200 `
        -Body @{ alias = $Alias } `
        -SameOrigin

    if ($selected.alias -ne $Alias) {
        throw "Persona selection failed"
    }

    $status = Invoke-JsonRequest `
        -Method Get `
        -Path "/api/demo/session" `
        -ExpectedStatus 200

    if ($status.entrance -ne $true -or $status.alias -ne $Alias) {
        throw "Persona session verification failed"
    }
}

function Get-Bootstrap {
    return Invoke-JsonRequest `
        -Method Get `
        -Path "/api/v1/ui/bootstrap" `
        -ExpectedStatus 200
}

function Assert-Role {
    param(
        [object]$Bootstrap,
        [string]$Role,
        [string[]]$RequiredPermissions,
        [string[]]$ForbiddenPermissions = @()
    )

    if ($null -eq $Bootstrap.tenant -or
        $null -eq $Bootstrap.user -or
        $null -eq $Bootstrap.roles -or
        $null -eq $Bootstrap.permissions) {
        throw "Incomplete UI bootstrap"
    }

    if (@($Bootstrap.roles).Count -ne 1 -or $Bootstrap.roles -notcontains $Role) {
        throw "Unexpected role in UI bootstrap"
    }

    foreach ($permission in $RequiredPermissions) {
        if ($Bootstrap.permissions -notcontains $permission) {
            throw "Required permission missing"
        }
    }

    foreach ($permission in $ForbiddenPermissions) {
        if ($Bootstrap.permissions -contains $permission) {
            throw "Forbidden permission present"
        }
    }
}

try {
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
        throw "Demo entrance failed"
    }

    Select-DemoPersona -Alias "RECTOR"
    $rector = Get-Bootstrap
    Assert-Role `
        -Bootstrap $rector `
        -Role "RECTOR" `
        -RequiredPermissions @("agents.use", "agents.view", "intelligence.read")

    Write-Host "M26_C2_REMOTE_ISOLATION"
    Write-Host "rector_role: PASS"
    Write-Host "rector_permissions: PASS"

    Select-DemoPersona -Alias "TEACHER"
    $teacher = Get-Bootstrap
    Assert-Role `
        -Bootstrap $teacher `
        -Role "TEACHER" `
        -RequiredPermissions @("teacher.console.access", "teacher.classes.view", "teacher.attendance.manage", "teacher.grades.manage") `
        -ForbiddenPermissions @("agents.use", "agents.view")

    if ((Get-ExpectedStatus -Method Get -Path "/api/v1/teacher/summary") -ne 200) {
        throw "Teacher allowed endpoint failed"
    }

    $teacherMentorStatus = Get-ExpectedStatus `
        -Method Post `
        -Path "/api/v1/agents/mentor_institution_briefing/runs" `
        -Body @{ briefing_focus = "OVERVIEW" } `
        -SameOrigin

    if ($teacherMentorStatus -ne 403) {
        throw "Teacher Mentor denial did not return 403"
    }

    Write-Host "teacher_role: PASS"
    Write-Host "teacher_allowed_endpoint: PASS"
    Write-Host "teacher_mentor_denied: PASS"

    Select-DemoPersona -Alias "RECTOR"
    $rectorAfterTeacher = Get-Bootstrap
    Assert-Role `
        -Bootstrap $rectorAfterTeacher `
        -Role "RECTOR" `
        -RequiredPermissions @("agents.use", "agents.view", "intelligence.read")

    Select-DemoPersona -Alias "TEACHER"
    $teacherAfterRector = Get-Bootstrap
    Assert-Role `
        -Bootstrap $teacherAfterRector `
        -Role "TEACHER" `
        -RequiredPermissions @("teacher.console.access") `
        -ForbiddenPermissions @("agents.use", "agents.view")

    Write-Host "rector_to_teacher_permission_reset: PASS"

    Select-DemoPersona -Alias "STUDENT"
    $student = Get-Bootstrap
    Assert-Role `
        -Bootstrap $student `
        -Role "STUDENT" `
        -RequiredPermissions @("student.console.access") `
        -ForbiddenPermissions @(
            "teacher.console.access",
            "teacher.classes.view",
            "teacher.attendance.manage",
            "teacher.grades.manage",
            "agents.use",
            "agents.view",
            "intelligence.read"
        )

    if ((Get-ExpectedStatus -Method Get -Path "/api/v1/student/me") -ne 200) {
        throw "Student self endpoint failed"
    }

    $studentIntelligenceStatus = Get-ExpectedStatus `
        -Method Get `
        -Path "/api/v1/intelligence/signals"

    if ($studentIntelligenceStatus -ne 403) {
        throw "Student intelligence denial did not return 403"
    }

    Write-Host "student_role: PASS"
    Write-Host "student_self_access: PASS"
    Write-Host "student_intelligence_denied: PASS"
    Write-Host "teacher_to_student_permission_reset: PASS"

    Select-DemoPersona -Alias "GUARDIAN"
    $guardian = Get-Bootstrap
    Assert-Role `
        -Bootstrap $guardian `
        -Role "GUARDIAN" `
        -RequiredPermissions @("guardian.console.access", "guardian.students.view") `
        -ForbiddenPermissions @("agents.use", "agents.view", "intelligence.read")

    $children = Invoke-JsonRequest `
        -Method Get `
        -Path "/api/v1/guardian/students" `
        -ExpectedStatus 200

    if (@($children).Count -lt 1) {
        throw "Guardian authorized-child scope is empty"
    }

    $authorizedStudentId = [string]$children[0].student_profile_id
    if ([string]::IsNullOrWhiteSpace($authorizedStudentId)) {
        throw "Authorized student identifier missing"
    }

    $randomStudentId = [guid]::NewGuid().ToString()
    $unrelatedStatus = Get-ExpectedStatus `
        -Method Get `
        -Path "/api/v1/guardian/students/$randomStudentId/summary"

    if ($unrelatedStatus -ne 404) {
        throw "Unrelated guardian student was not hidden"
    }

    Write-Host "guardian_role: PASS"
    Write-Host "guardian_link_scope: PASS"
    Write-Host "guardian_unrelated_student_hidden: PASS"
    Write-Host "runtime_restricted_actor_resolution: PASS"
    Write-Host "M26_C2_REMOTE_ISOLATION: PASS"
}
catch {
    Write-Host "M26_C2_REMOTE_ISOLATION: HOLD"
    exit 1
}
finally {
    $Code = $null
    $CodeSecure = $null
    if ($CodeBstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($CodeBstr)
    }
}
