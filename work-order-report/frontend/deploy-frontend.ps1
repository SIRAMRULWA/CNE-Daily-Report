param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("QA", "PROD")]
    [string]$Environment = "QA",

    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

# The existing archive workflow is retained for the proven QA deployment only.
# Production uses the Linux-built OCI image procedure in
# docs/frontend-deployment-mop.md. This guard prevents a Windows-built
# standalone/node_modules bundle or an unconfirmed backend target from being
# promoted during the first production deployment.
if ($Environment -eq "PROD") {
    throw "PROD deployment is intentionally disabled in this QA archive script. Follow docs/frontend-deployment-mop.md after Infra completes the production values and the backend origin is confirmed."
}

# ------------------------------------------------------------
# Environment Configurations
# ------------------------------------------------------------
$ConfigMap = @{
    QA   = @{
        ServerIP      = "10.115.252.35"
        ServerUser    = "mdles002"
        RemotePath    = "/opt/itil-report-stack/frontend"
        ApiUrl        = "http://10.115.252.35:8000"
        ContainerName = "itil-frontend-ui"
        HostPort      = "3001"
    }
    PROD = @{
        ServerIP      = "mto-vm-tss-prod-server"
        ServerUser    = "svc_itil_reports"
        RemotePath    = "/opt/itil-report-stack/frontend"
        ApiUrl        = "https://itil-reports.vodacom.co.za"
        ContainerName = "itil-frontend-ui"
        HostPort      = "3001"
    }
}

$Cfg = $ConfigMap[$Environment]
$ServerUser = $Cfg.ServerUser
$ServerIP = $Cfg.ServerIP
$RemotePath = $Cfg.RemotePath
$ContainerName = $Cfg.ContainerName
$HostPort = $Cfg.HostPort
$TarName = "itil-frontend-${Environment}.tar.gz"
$BundleDir = "deploy_bundle"

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " Deploying Frontend Container Target: [$Environment] -> ${ServerIP}" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

function Assert-PathExists {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Description
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing $Description`: $Path"
    }
}

function Invoke-RemoteBash {
    param(
        [Parameter(Mandatory = $true)][string]$Script
    )

    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $ExitCode = 1

    try {
        $Output = $Script | & ssh "${ServerUser}@${ServerIP}" "bash -s" 2>&1
        $ExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }

    [PSCustomObject]@{
        ExitCode = $ExitCode
        Output   = $Output
    }
}

# ------------------------------------------------------------
# 1. Local Build & Environment Injection
# ------------------------------------------------------------
if (-not $SkipBuild) {
    Write-Host "==> Configuring same-origin API proxy to: $($Cfg.ApiUrl)..." -ForegroundColor Cyan
    $env:NEXT_PUBLIC_API_URL = ""
    $env:API_PROXY_URL = $Cfg.ApiUrl

    Write-Host "==> Cleaning previous Next.js build..." -ForegroundColor Cyan
    if (Test-Path ".next") {
        Remove-Item ".next" -Recurse -Force
    }

    Write-Host "==> Running npm run build..." -ForegroundColor Cyan
    & npm.cmd run build

    if ($LASTEXITCODE -ne 0) {
        throw "npm run build failed with exit code $LASTEXITCODE"
    }
}

# ------------------------------------------------------------
# 2. Validate standalone output
# ------------------------------------------------------------
Write-Host "==> Validating Next.js standalone output..." -ForegroundColor Cyan

Assert-PathExists -Path ".next\standalone" -Description "standalone output directory"
Assert-PathExists -Path ".next\standalone\server.js" -Description "standalone server.js"
Assert-PathExists -Path ".next\standalone\node_modules\next\package.json" -Description "Next.js runtime package"
Assert-PathExists -Path ".next\static" -Description "Next.js static assets"

# ------------------------------------------------------------
# 3. Construct deployment bundle
# ------------------------------------------------------------
Write-Host "==> Constructing deployment bundle..." -ForegroundColor Cyan

if (Test-Path $BundleDir) {
    Remove-Item $BundleDir -Recurse -Force
}

New-Item -ItemType Directory -Path $BundleDir | Out-Null

Get-ChildItem -LiteralPath ".next\standalone" -Force |
Copy-Item -Destination $BundleDir -Recurse -Force

$StaticDestination = Join-Path $BundleDir ".next\static"
New-Item -ItemType Directory -Path $StaticDestination -Force | Out-Null
Copy-Item -Path ".next\static\*" -Destination $StaticDestination -Recurse -Force

if (Test-Path "public") {
    $PublicDestination = Join-Path $BundleDir "public"
    New-Item -ItemType Directory -Path $PublicDestination -Force | Out-Null
    Copy-Item -Path "public\*" -Destination $PublicDestination -Recurse -Force
}

# ------------------------------------------------------------
# 4. Create & Upload Archive
# ------------------------------------------------------------
Write-Host "==> Packaging archive..." -ForegroundColor Cyan

if (Test-Path $TarName) {
    Remove-Item $TarName -Force
}

tar -czf $TarName -C $BundleDir .
Remove-Item $BundleDir -Recurse -Force

Write-Host "==> Uploading archive to ${ServerIP}..." -ForegroundColor Cyan
& scp $TarName "${ServerUser}@${ServerIP}:/tmp/$TarName"

if ($LASTEXITCODE -ne 0) {
    throw "SCP upload failed."
}

# ------------------------------------------------------------
# 5. Extract, Switch Release & Restart Podman Container
# ------------------------------------------------------------
Write-Host "==> Deploying Podman Container on Server..." -ForegroundColor Cyan

$InstallScript = @"
set -euo pipefail

REMOTE_PATH="$RemotePath"
ARCHIVE="/tmp/$TarName"
NEW_RELEASE="`$REMOTE_PATH/standalone.new"
CURRENT_RELEASE="`$REMOTE_PATH/standalone"
BACKUP_RELEASE="`$REMOTE_PATH/standalone.bak"

mkdir -p "`$REMOTE_PATH"

if [ -e "`$NEW_RELEASE" ]; then
    rm -rf "`$NEW_RELEASE"
fi

mkdir -p "`$NEW_RELEASE"
tar -xzf "`$ARCHIVE" -C "`$NEW_RELEASE"

chmod -R 755 "`$NEW_RELEASE"

if [ -d "`$BACKUP_RELEASE" ]; then
    rm -rf "`$BACKUP_RELEASE"
fi

if [ -d "`$CURRENT_RELEASE" ]; then
    mv "`$CURRENT_RELEASE" "`$BACKUP_RELEASE"
fi

mv "`$NEW_RELEASE" "`$CURRENT_RELEASE"
rm -f "`$ARCHIVE"

echo "Replacing Podman Container ($ContainerName)..."
podman stop $ContainerName 2>/dev/null || true
podman rm $ContainerName 2>/dev/null || true

# Ensure custom network exists
podman network create itil-net 2>/dev/null || true

podman run -d \
  --name $ContainerName \
  --net itil-net \
  --restart always \
  -p ${HostPort}:3000 \
  -e PORT=3000 \
  -e HOSTNAME="0.0.0.0" \
  -v "`$CURRENT_RELEASE:/app:Z" \
  -w /app \
  docker.io/library/node:22-alpine \
  node server.js

echo "Verifying container status and health..."
sleep 3
podman ps --filter name=$ContainerName
curl -f -s "http://127.0.0.1:${HostPort}/healthz"

echo "DEPLOYMENT_SUCCESSFUL"
"@

$InstallResult = Invoke-RemoteBash -Script $InstallScript

if ($InstallResult.Output) {
    $InstallResult.Output | ForEach-Object { Write-Host $_ }
}

$DeploymentInstalled = [bool]($InstallResult.Output | Select-String -SimpleMatch "DEPLOYMENT_SUCCESSFUL")

if ($InstallResult.ExitCode -ne 0 -or -not $DeploymentInstalled) {
    throw "Remote installation failed. See remote output above."
}

Remove-Item $TarName -Force

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host " SUCCESS: Frontend Container Deployed & Healthy on [$Environment]!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
