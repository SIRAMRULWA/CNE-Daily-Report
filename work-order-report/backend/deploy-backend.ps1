param(
    [ValidateSet("QA", "PROD")]
    [string]$Environment = "QA",

    [string]$OverrideServerIP,

    [switch]$SkipUpload,
    [switch]$UseTty,
    [switch]$SkipDbInit,
    [int]$ApiPort = 8000,
    [string]$ContainerName = "itil-backend-api",
    [string]$ReleaseTag = (Get-Date -Format "yyyyMMdd-HHmmss")
)

$ErrorActionPreference = "Stop"

# --- Environment Configuration Mapping ---
$ServerUser = "mdles002"

$EnvironmentIPs = @{
    "QA"   = "10.115.252.35"
    "PROD" = "10.115.X.X"  # Update with actual PROD IP when ready
}

# Determine target IP
if ($OverrideServerIP) {
    $ServerIP = $OverrideServerIP
}
else {
    $ServerIP = $EnvironmentIPs[$Environment]
}

$RemoteBasePath = "/opt/itil-report-stack"
$RemoteRelease = "$RemoteBasePath/releases/$ReleaseTag"
$TarName = "itil-backend-src-$ReleaseTag.tar.gz"
$RemoteScriptPath = "$RemoteBasePath/scripts/deploy-backend.sh"

Write-Host "==========================================================" -ForegroundColor Green
Write-Host " Deploying Backend Target: [$Environment]" -ForegroundColor Green
Write-Host " Server IP:                $ServerIP" -ForegroundColor Green
Write-Host " Release Tag:              $ReleaseTag" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

function Assert-PathExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing $Description`: $Path"
    }
}

# ------------------------------------------------------------
# 1. Package and Upload Source Code
# ------------------------------------------------------------
if (-not $SkipUpload) {
    Write-Host "==> Archiving local backend source files [$ReleaseTag]..." -ForegroundColor Cyan

    if (Test-Path $TarName) {
        Remove-Item $TarName -Force
    }

    # Packages local files while strictly skipping env, virtual environments, and dbt caches
    tar -czf $TarName `
        --exclude="node_modules" `
        --exclude=".git" `
        --exclude=".next" `
        --exclude="dist" `
        --exclude="target" `
        --exclude="logs" `
        --exclude="dbt/logs" `
        --exclude="dbt/target" `
        --exclude="dbt_packages" `
        --exclude="venv" `
        --exclude=".pytest_cache" `
        --exclude="__pycache__" `
        --exclude=".env*" `
        --exclude="*.zip" `
        --exclude="*.tar" `
        --exclude="*.tar.gz" `
        --exclude="*.tgz" `
        .

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create local deployment archive source snapshot."
    }

    Write-Host "==> Syncing files to $Environment server workspace ($ServerIP)..." -ForegroundColor Cyan
    & scp $TarName "${ServerUser}@${ServerIP}:/tmp/$TarName"

    if ($LASTEXITCODE -ne 0) {
        throw "SCP bundle source delivery failed."
    }

    Write-Host "==> Unpacking workspace content remotely into $RemoteRelease..." -ForegroundColor Cyan
    $UnpackCommand = "mkdir -p $RemoteRelease && tar -xzf /tmp/$TarName -C $RemoteRelease --overwrite && rm -f /tmp/$TarName"
    & ssh "${ServerUser}@${ServerIP}" $UnpackCommand

    if ($LASTEXITCODE -ne 0) {
        throw "Remote source unpacking extraction failed."
    }

    Remove-Item $TarName -Force
    Write-Host "OK: Remote application source matching completed." -ForegroundColor Green
}

# ------------------------------------------------------------
# 2. Trigger Container Lifecycle & Rebuild Script
# ------------------------------------------------------------
Write-Host "==> Launching container lifecycle rebuild..." -ForegroundColor Cyan

# Passes RELEASE_TAG so the server script links current -> releases/$ReleaseTag
$RemoteCommand = "set -Eeuo pipefail; " +
"if [ ! -f '$RemoteScriptPath' ]; then echo 'ERROR: missing remote deploy script: $RemoteScriptPath'; exit 20; fi; " +
"chmod +x '$RemoteScriptPath'; " +
"RELEASE_TAG='$ReleaseTag' bash '$RemoteScriptPath'"

if ($UseTty) {
    & ssh -t "${ServerUser}@${ServerIP}" "bash -lc `"$RemoteCommand`""
}
else {
    $ResultText = & ssh "${ServerUser}@${ServerIP}" "bash -lc `"$RemoteCommand 2>&1`""
}

$RemoteExitCode = $LASTEXITCODE

if ($ResultText) {
    $ResultText | ForEach-Object { Write-Host $_ }
}

if ($RemoteExitCode -ne 0) {
    throw "Remote backend deployment script failed with exit code $RemoteExitCode."
}

# ------------------------------------------------------------
# 3. Database Schema Refresh / Migration
# ------------------------------------------------------------
if (-not $SkipDbInit) {
    Write-Host "==> Running remote schema/dbt refresh..." -ForegroundColor Cyan

    $DbInitCommand = "set -Eeuo pipefail; " +
    "if command -v podman >/dev/null 2>&1; then " +
    "podman exec '$ContainerName' bash deploy/init-db.sh; " +
    "elif command -v docker >/dev/null 2>&1; then " +
    "docker exec '$ContainerName' bash deploy/init-db.sh; " +
    "else echo 'ERROR: neither podman nor docker is available on the server.'; exit 21; fi"

    $DbInitText = & ssh "${ServerUser}@${ServerIP}" "bash -lc `"$DbInitCommand 2>&1`"" 2>&1
    $DbInitExitCode = $LASTEXITCODE

    if ($DbInitText) {
        $DbInitText | ForEach-Object { Write-Host $_ }
    }

    if ($DbInitExitCode -ne 0) {
        throw "Remote schema/dbt refresh failed with exit code $DbInitExitCode."
    }
}

# ------------------------------------------------------------
# 4. Release Retention & Podman Cache Prune
# ------------------------------------------------------------
Write-Host "==> Pruning old releases (retaining latest 3) and dangling Podman images..." -ForegroundColor Cyan
$CleanupCommand = "cd $RemoteBasePath/releases && ls -dt */ 2>/dev/null | tail -n +4 | xargs rm -rf 2>/dev/null || true; " +
"podman image prune -f >/dev/null 2>&1 || true"
& ssh "${ServerUser}@${ServerIP}" "bash -lc `"$CleanupCommand`""

# ------------------------------------------------------------
# 5. Live HTTP Health Verification
# ------------------------------------------------------------
Write-Host "==> Verifying live API health endpoint..." -ForegroundColor Cyan
$HealthUrl = "http://${ServerIP}:${ApiPort}/api/v1/health"
$MaxRetries = 5
$RetryIntervalSeconds = 3
$HealthPassed = $false

for ($i = 1; $i -le $MaxRetries; $i++) {
    try {
        $Response = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 5 -ErrorAction Stop
        Write-Host "OK: API endpoint responded healthy ($HealthUrl)" -ForegroundColor Green
        $HealthPassed = $true
        break
    }
    catch {
        Write-Host "  Attempt $i/${MaxRetries}: Waiting for API to respond at $HealthUrl..." -ForegroundColor Yellow
        Start-Sleep -Seconds $RetryIntervalSeconds
    }
}

if (-not $HealthPassed) {
    throw "Backend health check failed. The API endpoint ($HealthUrl) did not respond within $($MaxRetries * $RetryIntervalSeconds) seconds."
}

Write-Host "==========================================================" -ForegroundColor Green
Write-Host " OK: Backend deployment completely synced to [$Environment]!" -ForegroundColor Green
Write-Host " Release: $ReleaseTag" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green