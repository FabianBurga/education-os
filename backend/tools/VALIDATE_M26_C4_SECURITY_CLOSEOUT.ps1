$ErrorActionPreference = "Stop"

$BaseUrl = "https://education-os-investor-demo.onrender.com"
$TempPython = Join-Path $env:TEMP ("m26-c4-security-" + [guid]::NewGuid().ToString("N") + ".py")

function Stop-Hold {
    param([string]$Reason)
    Write-Host "M26_C4_SECURITY_CLOSEOUT: HOLD"
    Write-Host $Reason
    exit 1
}

try {
    Write-Host "M26_C4_SECURITY_CLOSEOUT"

    if (-not $env:RENDER_EXTERNAL_DATABASE_URL) {
        Stop-Hold "admin_database_connection: MISSING"
    }

    if (-not $env:EDUCATION_APP_PASSWORD) {
        Stop-Hold "education_app_password: MISSING"
    }

    try {
        $ready = Invoke-WebRequest `
            -Uri "$BaseUrl/health/ready" `
            -Method Get `
            -UseBasicParsing `
            -MaximumRedirection 0
    }
    catch {
        Stop-Hold "health_ready: FAILED"
    }

    if ($ready.StatusCode -ne 200) {
        Stop-Hold "health_ready: FAILED"
    }
    Write-Host "health_ready: PASS"

    $demoSourcePath = Join-Path $PSScriptRoot "..\app\core\demo.py"
    if (-not (Test-Path -LiteralPath $demoSourcePath)) {
        Stop-Hold "runtime_guard_source: MISSING"
    }

    $demoSource = Get-Content -LiteralPath $demoSourcePath -Raw
    $ownerUrlGuard = $demoSource.Contains("OWNER_DATABASE_URL") -and
        $demoSource.Contains('"education_owner" not in config.DATABASE_URL')
    $ownerRoleGuard = $demoSource.Contains("rolsuper") -and
        $demoSource.Contains("rolbypassrls")

    if (-not $ownerUrlGuard) {
        Stop-Hold "runtime_owner_url_guard: NOT_PROVEN"
    }
    if (-not $ownerRoleGuard) {
        Stop-Hold "runtime_owner_role_guard: NOT_PROVEN"
    }

    @'
import json
import os
import sys

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
except Exception:
    print(json.dumps({"error": "dependency_import_failed"}, sort_keys=True))
    sys.exit(2)


def select_only(sql):
    statement = sql.lstrip().upper()
    if not statement.startswith("SELECT"):
        raise RuntimeError("non_select_statement")
    return text(sql)


def main():
    result = {}
    phase = "admin_url_parse"
    admin_raw = os.environ.get("RENDER_EXTERNAL_DATABASE_URL")
    app_password = os.environ.get("EDUCATION_APP_PASSWORD")
    if not admin_raw:
        result["error"] = "admin_database_connection_missing"
        print(json.dumps(result, sort_keys=True))
        return 2
    if not app_password:
        result["error"] = "education_app_password_missing"
        print(json.dumps(result, sort_keys=True))
        return 2

    admin_engine = None
    app_engine = None
    try:
        admin_url = make_url(admin_raw)
        admin_url = admin_url.set(drivername="postgresql+psycopg")
        admin_query = dict(admin_url.query)
        admin_query["sslmode"] = "require"
        admin_url = admin_url.set(query=admin_query)

        app_url = admin_url.set(username="education_app", password=app_password)

        admin_engine = create_engine(admin_url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
        app_engine = create_engine(app_url, pool_pre_ping=True, connect_args={"connect_timeout": 10})

        role_sql = select_only("""
            SELECT rolname, rolcanlogin, rolsuper, rolbypassrls,
                   rolcreatedb, rolcreaterole, rolinherit
            FROM pg_roles
            WHERE rolname IN ('education_owner', 'education_app')
        """)
        membership_sql = select_only("""
            SELECT pg_has_role('education_app', 'education_owner', 'MEMBER')
        """)

        phase = "admin_connection"
        with admin_engine.connect() as connection:
            phase = "role_catalog"
            rows = connection.execute(role_sql).mappings().all()
            roles = {row["rolname"]: row for row in rows}
            result["owner_exists"] = "education_owner" in roles
            result["app_exists"] = "education_app" in roles
            if result["owner_exists"]:
                owner = roles["education_owner"]
                result["owner_nologin"] = owner["rolcanlogin"] is False
                result["owner_nosuperuser"] = owner["rolsuper"] is False
                result["owner_nobypassrls"] = owner["rolbypassrls"] is False
                result["owner_nocreatedb"] = owner["rolcreatedb"] is False
                result["owner_nocreaterole"] = owner["rolcreaterole"] is False
                result["owner_noinherit"] = owner["rolinherit"] is False
            if result["app_exists"]:
                app = roles["education_app"]
                result["app_login"] = app["rolcanlogin"] is True
                result["app_nosuperuser"] = app["rolsuper"] is False
                result["app_nobypassrls"] = app["rolbypassrls"] is False
                result["app_nocreatedb"] = app["rolcreatedb"] is False
                result["app_nocreaterole"] = app["rolcreaterole"] is False
            phase = "membership_check"
            result["app_not_owner_member"] = connection.execute(membership_sql).scalar() is False

        phase = "restricted_connection"
        with app_engine.connect() as connection:
            phase = "restricted_identity"
            identity = connection.execute(select_only("SELECT current_user, session_user")).one()
            result["restricted_current_user"] = identity[0] == "education_app"
            result["restricted_session_user"] = identity[1] == "education_app"
            phase = "restricted_role_flags"
            flags = connection.execute(select_only("""
                SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
                FROM pg_roles
                WHERE rolname = current_user
            """)).one()
            result["restricted_role_flags"] = all(value is False for value in flags)

        result["error"] = None
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"error": phase + "_failed"}, sort_keys=True))
        return 3
    finally:
        if admin_engine is not None:
            admin_engine.dispose()
        if app_engine is not None:
            app_engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
'@ | Set-Content -LiteralPath $TempPython -Encoding UTF8

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $pythonOutput = & ..\.venv\Scripts\python.exe -I $TempPython 2>$null
        $pythonExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if (-not $pythonOutput) {
        Stop-Hold "security_query: NO_RESULT"
    }

    try {
        $result = $pythonOutput | ConvertFrom-Json
    }
    catch {
        Stop-Hold "security_query: INVALID_RESULT"
    }

    if ($null -ne $result.error) {
        Stop-Hold ([string]$result.error)
    }

    if ($pythonExitCode -ne 0) {
        Stop-Hold "security_query: FAILED_WITHOUT_ERROR_CODE"
    }

    $checks = @(
        @{ Name = "education_owner_exists"; Value = $result.owner_exists },
        @{ Name = "education_owner_nologin"; Value = $result.owner_nologin },
        @{ Name = "education_owner_nosuperuser"; Value = $result.owner_nosuperuser },
        @{ Name = "education_owner_nobypassrls"; Value = $result.owner_nobypassrls },
        @{ Name = "education_owner_nocreatedb"; Value = $result.owner_nocreatedb },
        @{ Name = "education_owner_nocreaterole"; Value = $result.owner_nocreaterole },
        @{ Name = "education_owner_noinherit"; Value = $result.owner_noinherit },
        @{ Name = "education_app_exists"; Value = $result.app_exists },
        @{ Name = "education_app_login"; Value = $result.app_login },
        @{ Name = "education_app_nosuperuser"; Value = $result.app_nosuperuser },
        @{ Name = "education_app_nobypassrls"; Value = $result.app_nobypassrls },
        @{ Name = "education_app_nocreatedb"; Value = $result.app_nocreatedb },
        @{ Name = "education_app_nocreaterole"; Value = $result.app_nocreaterole },
        @{ Name = "education_app_not_owner_member"; Value = $result.app_not_owner_member },
        @{ Name = "restricted_connection_current_user"; Value = $result.restricted_current_user },
        @{ Name = "restricted_connection_session_user"; Value = $result.restricted_session_user },
        @{ Name = "restricted_connection_role_flags"; Value = $result.restricted_role_flags }
    )

    foreach ($check in $checks) {
        if ($check.Value -ne $true) {
            Stop-Hold "role_state_mismatch"
        }
    }

    Write-Host "education_owner_exists: PASS"
    Write-Host "education_owner_nologin: PASS"
    Write-Host "education_owner_nosuperuser: PASS"
    Write-Host "education_owner_nobypassrls: PASS"
    Write-Host "education_owner_nocreatedb: PASS"
    Write-Host "education_owner_nocreaterole: PASS"
    Write-Host "education_owner_noinherit: PASS"
    Write-Host "education_app_exists: PASS"
    Write-Host "education_app_login: PASS"
    Write-Host "education_app_nosuperuser: PASS"
    Write-Host "education_app_nobypassrls: PASS"
    Write-Host "education_app_nocreatedb: PASS"
    Write-Host "education_app_nocreaterole: PASS"
    Write-Host "education_app_not_owner_member: PASS"
    Write-Host "restricted_connection_current_user: PASS"
    Write-Host "restricted_connection_session_user: PASS"
    Write-Host "restricted_connection_role_flags: PASS"
    Write-Host "owner_login_impossible_by_role_state: PASS"
    Write-Host "runtime_owner_url_guard: PASS"
    Write-Host "runtime_owner_role_guard: PASS"
    Write-Host "M26_C4_SECURITY_CLOSEOUT: PASS"
}
finally {
    if (Test-Path -LiteralPath $TempPython) {
        Remove-Item -LiteralPath $TempPython -Force -ErrorAction SilentlyContinue
    }
}
