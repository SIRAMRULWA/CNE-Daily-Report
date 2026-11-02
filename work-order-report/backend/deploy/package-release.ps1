param(
    [string]$Version = (Get-Date -Format "yyyyMMdd-HHmm")
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$dist = Join-Path $root "dist"
$staging = Join-Path $dist "itil-group-reports-$Version"
$zip = Join-Path $dist "itil-group-reports-$Version.zip"

if (Test-Path $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}
New-Item -ItemType Directory -Path $staging | Out-Null

$include = @(
    "app_core",
    "capabilities",
    "api",
    "config",
    "dbt",
    "deploy",
    "docs",
    "helix",
    "notifications",
    "pipeline",
    "sql",
    "tests",
    "tools",
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "docker-compose.yml",
    "README.md",
    "requirements.txt",
    "__init__.py"
)

foreach ($item in $include) {
    $source = Join-Path $root $item
    if (Test-Path $source) {
        Copy-Item -LiteralPath $source -Destination $staging -Recurse -Force
    }
}

New-Item -ItemType Directory -Path (Join-Path $staging "data/excel_drop") -Force | Out-Null
New-Item -ItemType File -Path (Join-Path $staging "data/excel_drop/.gitkeep") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $staging "output") -Force | Out-Null

Remove-Item -LiteralPath (Join-Path $staging "dbt/target") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $staging "dbt/logs") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $staging "dbt/.user.yml") -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath $staging -Directory -Recurse -Force |
    Where-Object { $_.Name -eq "__pycache__" } |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $staging -File -Recurse -Force |
    Where-Object { $_.Extension -in ".pyc", ".pyo" } |
    Remove-Item -Force

if (Test-Path $zip) {
    Remove-Item -LiteralPath $zip -Force
}

$tar = Get-Command tar -ErrorAction SilentlyContinue
if ($tar) {
    & $tar.Source -a -cf $zip -C $staging .
    if ($LASTEXITCODE -ne 0) {
        throw "tar failed to create $zip"
    }
} else {
    Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zip -Force -ErrorAction Stop
}

Write-Host "Created $zip"
